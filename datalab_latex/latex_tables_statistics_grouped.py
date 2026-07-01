from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from datalab_core.statistics_grouped import validate_statistics_grouped_payload

from .latex_tables_common import (
    _build_standalone_preamble,
    _estimate_page_geometry,
    _needs_cjk_support,
    build_statistics_latex_summary_rows,
    format_statistics_latex_value,
    latex_numeric_values_from_rows,
    statistics_latex_output_unit_for_keys,
    statistics_latex_summary_unit_for_label,
)
from .latex_tables_fitting import latex_escape


def generate_statistics_grouped_latex(
    payload: Mapping[str, Any],
    output_path: str | Path | None = None,
    *,
    caption_text: str = "Grouped statistics",
    use_dcolumn: bool = True,
    digits: int = 20,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    units: Mapping[str, Any] | None = None,
) -> str:
    """Generate a standalone LaTeX document for grouped statistics payloads."""

    from datalab_latex.latex_formatting import calculate_dcolumn_format_for_column, siunitx_column_spec

    validate_statistics_grouped_payload(payload)
    group_size = max(0, int(latex_group_size))
    rows = _grouped_summary_rows(
        payload,
        digits=digits,
        use_dcolumn=use_dcolumn,
        uncertainty_digits=uncertainty_digits,
        latex_group_size=group_size,
        units=units,
    )
    if not rows:
        raise ValueError("grouped statistics payload has no exportable rows.")
    value_cells = _numeric_cells(row[4] for row in rows)
    if value_cells:
        value_spec = (
            calculate_dcolumn_format_for_column(value_cells, "statistics_grouped_summary")
            if use_dcolumn
            else siunitx_column_spec(value_cells)
        )
    else:
        value_spec = "l"
    has_units = any(row[3] for row in rows)
    column_spec = f"l l l l {value_spec}" if has_units else f"l l l {value_spec}"
    text_segments = [
        caption_text,
        str(payload["group_column"]),
        *(str(column) for column in payload["value_columns"]),
        *(segment for row in rows for segment in row),
    ]
    width, _height = _estimate_page_geometry(
        [
            _max_length(row[0] for row in rows),
            _max_length(row[1] for row in rows),
            _max_length(row[2] for row in rows),
            _max_length(row[3] for row in rows) if has_units else 0,
            max(8, _max_length(row[4] for row in rows)),
        ],
        len(rows),
    )
    lines = _build_standalone_preamble(
        width,
        include_dcolumn=use_dcolumn,
        needs_cjk=_needs_cjk_support(*(str(segment) for segment in text_segments)),
        latex_group_size=group_size,
    )
    value_columns = ", ".join(str(column) for column in payload["value_columns"])
    lines.extend(
        [
            f"\\section*{{{latex_escape(caption_text)}}}",
            (
                "\\noindent "
                f"Group column: \\texttt{{{latex_escape(str(payload['group_column']))}}}; "
                f"value columns: \\texttt{{{latex_escape(value_columns)}}}; "
                f"groups: {latex_escape(str(len(payload['group_order'])))}; "
                f"rows: {latex_escape(str(payload['row_count']))}."
            ),
            "",
            "\\begin{threeparttable}",
            f"\\caption{{{latex_escape(caption_text)}}}",
            f"\\begin{{tabular}}{{{column_spec}}}",
            "\\toprule",
            (
                "Group & Column & Metric & Unit & \\multicolumn{1}{c}{Value} \\\\"
                if has_units
                else "Group & Column & Metric & \\multicolumn{1}{c}{Value} \\\\"
            ),
            "\\midrule",
        ]
    )
    for group_label, column_name, metric, unit, value in rows:
        if has_units:
            lines.append(
                f"{latex_escape(group_label)} & {latex_escape(column_name)} & {latex_escape(metric)} & "
                f"{latex_escape(unit)} & {value} \\\\"
            )
        else:
            lines.append(
                f"{latex_escape(group_label)} & {latex_escape(column_name)} & {latex_escape(metric)} & {value} \\\\"
            )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{threeparttable}", "", "\\end{document}"])
    tex = "\n".join(lines) + "\n"
    if output_path is not None:
        Path(output_path).write_text(tex, encoding="utf-8")
    return tex


def _grouped_summary_rows(
    payload: Mapping[str, Any],
    *,
    digits: int,
    use_dcolumn: bool,
    uncertainty_digits: int | None,
    latex_group_size: int,
    units: Mapping[str, Any] | None,
) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []

    def _format_summary_value(value: Any, sigma: Any | None, is_input: bool) -> str:
        return format_statistics_latex_value(
            value,
            sigma,
            digits=digits,
            use_dcolumn=use_dcolumn,
            uncertainty_digits=uncertainty_digits,
            is_input=is_input,
            latex_group_size=latex_group_size,
        )

    for group in _mapping_sequence(payload.get("groups")):
        group_label = str(group["group"])
        for column in _mapping_sequence(group.get("columns")):
            column_name = str(column["value_column"])
            result = column.get("result")
            if isinstance(result, Mapping):
                summary_rows = build_statistics_latex_summary_rows(
                    result,
                    format_value=_format_summary_value,
                    format_text=latex_escape,
                )
                rows.extend(
                    (
                        group_label,
                        column_name,
                        metric,
                        statistics_latex_summary_unit_for_label(units, metric)
                        or statistics_latex_output_unit_for_keys(units, column_name, "result"),
                        value,
                    )
                    for metric, value in summary_rows
                )
            else:
                rows.append((group_label, column_name, "Status", "", _text_cell("No numeric values.")))
            for warning in _text_sequence(column.get("warnings")):
                rows.append((group_label, column_name, "Warning", "", _text_cell(warning)))
    for diagnostic in _mapping_sequence(payload.get("diagnostics")):
        group_label = _optional_text(diagnostic.get("group"))
        column_name = _optional_text(diagnostic.get("column"))
        message = str(diagnostic.get("message") or diagnostic.get("code") or "")
        if message:
            rows.append((group_label, column_name, "Diagnostic", "", _text_cell(message)))
    return rows


def _text_cell(text: str) -> str:
    return f"\\multicolumn{{1}}{{l}}{{{latex_escape(text)}}}"


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _text_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item.strip())


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _max_length(values: Iterable[str]) -> int:
    return max([len(str(value)) for value in values] or [0])


def _numeric_cells(values: Iterable[str]) -> list[str]:
    return latex_numeric_values_from_rows([("", value) for value in values if not value.lstrip().startswith("\\multicolumn")])


__all__ = ["generate_statistics_grouped_latex"]
