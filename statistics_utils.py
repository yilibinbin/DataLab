"""Statistics helpers extracted from the GUI layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mpmath import mp

from datalab_latex.latex_tables_common import (
    build_statistics_latex_summary_rows,
    format_statistics_latex_value,
    latex_numeric_values_from_rows,
    statistics_latex_output_unit_for_keys,
    statistics_latex_summary_units_for_rows,
)
from datalab_core.statistics import (
    statistics_snapshot_row_label,
    validate_statistics_bootstrap_snapshot,
)
from datalab_core.statistics_hypothesis import (
    render_statistics_hypothesis_payload_outputs,
    validate_statistics_hypothesis_snapshot,
)
from datalab_core.statistics_time_series import (
    time_series_payload_from_snapshot,
    validate_statistics_time_series_snapshot,
)
from datalab_core.statistics_compute import compute_statistics as compute_statistics
from shared.unit_annotations import unit_annotations_for_labels


def latex_escape(text: str) -> str:
    mapping = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
        "\\": "\\textbackslash{}",
        "σ": "\\ensuremath{\\sigma}",
    }
    return "".join(mapping.get(ch, ch) for ch in str(text))


def _format_table_value(
    value: mp.mpf,
    sigma: mp.mpf | None,
    digits: int,
    use_dcolumn: bool,
    uncertainty_digits: int | None = None,
    *,
    is_input: bool = True,
    group_size: int = 3,
) -> tuple[str, bool]:
    """Return (text, needs_multicolumn)."""
    text = format_statistics_latex_value(
        value,
        sigma,
        digits=digits,
        use_dcolumn=use_dcolumn,
        uncertainty_digits=uncertainty_digits,
        is_input=is_input,
        latex_group_size=group_size,
    )
    return text, False


def _latex_numeric_summary_values(summary_rows: list[tuple[str, str]]) -> list[str]:
    return [str(value) for value in latex_numeric_values_from_rows(summary_rows)]


def _latex_label_with_unit(label: str, unit: str) -> str:
    if unit:
        return latex_escape(f"{label} ({unit})")
    return latex_escape(label)


def _statistics_input_units_for_labels(
    units: Mapping[str, Any] | None,
    labels: Sequence[str],
) -> dict[str, str]:
    return unit_annotations_for_labels(units, "inputs", labels, fallback_prefix="column")


def _statistics_latex_preamble(
    *, use_dcolumn: bool, group_size: int, native_group_width: bool = True
) -> list[str]:
    from datalab_latex.sisetup_block import build_sisetup_block

    lines = [
        "\\documentclass{article}",
        "\\usepackage{ifxetex}",
        "\\usepackage{ifluatex}",
        "\\ifxetex",
        "  \\usepackage{xeCJK}",
        "\\else",
        "  \\ifluatex",
        "    \\usepackage{fontspec}",
        "  \\else",
        "    \\usepackage[utf8]{inputenc}",
        "    \\usepackage[T1]{fontenc}",
        "  \\fi",
        "\\fi",
        "\\usepackage{amsmath}",
        "\\usepackage{array}",
        "\\usepackage{booktabs}",
        "\\usepackage{threeparttable}",
        "\\usepackage{geometry}",
        "\\usepackage{graphicx}",
    ]
    if use_dcolumn:
        lines.append("\\usepackage{dcolumn}")
        lines.append("\\newcolumntype{d}[1]{D{.}{.}{#1}}")
    lines.append("\\usepackage{siunitx}")
    # native_group_width True → the engine honours digit-group-size → emit it (S-column
    # native variable-width grouping). False → don't emit (bundled Tectonic rejects it); the
    # cells are pre-grouped app-side instead. group_size 0 / dcolumn → no override anyway.
    emit_dgs = True if (native_group_width and not use_dcolumn and group_size > 0) else False
    lines.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=use_dcolumn,
            emit_digit_group_size=emit_dgs,
        ).rstrip("\n")
    )
    return lines


def _bootstrap_row_text(row: Mapping[str, Any]) -> str:
    value = row.get("value")
    if value is None or str(value) == "":
        value = row.get("message_key") or row.get("key") or ""
    return str(value)


def _format_bootstrap_metric_value(
    value: object,
    digits: int,
    use_dcolumn: bool,
    uncertainty_digits: int | None,
    group_size: int,
) -> str:
    try:
        parsed = mp.mpf(str(value))
    except Exception:
        return f"\\multicolumn{{1}}{{l}}{{{latex_escape(str(value))}}}"
    if not mp.isfinite(parsed):
        return f"\\multicolumn{{1}}{{l}}{{{latex_escape(str(value))}}}"
    return _format_table_value(
        parsed,
        None,
        digits,
        use_dcolumn,
        uncertainty_digits,
        is_input=False,
        group_size=group_size,
    )[0]


def _snapshot_row_sequence(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def generate_statistics_latex(
    value_col: str,
    data_rows: list[tuple[mp.mpf, ...]],
    sigma_rows: list[tuple[mp.mpf | None, ...]],
    result: dict,
    digits: int,
    tex_path: str,
    use_dcolumn: bool,
    uncertainty_digits: int | None = None,
    caption: str | None = None,
    latex_group_size: int = 3,
    units: Mapping[str, Any] | None = None,
    native_group_width: bool = True,
):
    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec
    from datalab_latex.latex_formatting import group_digits_both_sides

    group_size = max(0, int(latex_group_size))
    # App-side grouping: when the compile engine's siunitx CANNOT vary the digit-group width
    # (native_group_width False → bundled Tectonic siunitx 3.0.49) AND grouping is on in
    # siunitx (non-dcolumn) mode, pre-group each cell here (any width) and print it as a
    # plain \text{} cell in an r column, instead of a raw number in an S column that siunitx
    # would re-group at a fixed 3. When native_group_width is True (capable local TeX) the
    # S column + \sisetup{digit-group-size} does the grouping natively.
    app_group = (not native_group_width) and (not use_dcolumn) and group_size > 0

    def _maybe_group(cell: str) -> str:
        if app_group and "\\multicolumn" not in cell and "\\text" not in cell:
            return "\\text{" + group_digits_both_sides(cell, group_size) + "}"
        return cell

    num_cols = len(data_rows[0]) if data_rows else 0
    formatted_columns: list[list[str]] = [[] for _ in range(num_cols)]
    for row_idx, row in enumerate(data_rows):
        for col_idx in range(num_cols):
            value = row[col_idx] if col_idx < len(row) else mp.mpf("0")
            sigma = None
            if sigma_rows and row_idx < len(sigma_rows) and col_idx < len(sigma_rows[row_idx]):
                sigma = sigma_rows[row_idx][col_idx]
            cell, _ = _format_table_value(
                value,
                sigma,
                digits,
                use_dcolumn,
                uncertainty_digits,
                is_input=True,
                group_size=group_size,
            )
            formatted_columns[col_idx].append(_maybe_group(cell))

    if use_dcolumn:
        num_specs = [
            calculate_dcolumn_format_for_column(formatted_columns[i], f"stats_data_col_{i}")
            for i in range(num_cols)
        ]
    elif app_group:
        # Plain right-aligned column: cell text is already grouped + wrapped in \text{}.
        num_specs = ["r"] * num_cols
    else:
        num_specs = [siunitx_column_spec(formatted_columns[i]) for i in range(num_cols)]
    data_col_spec = "l" + ("" if not num_specs else " " + " ".join(num_specs))
    data_column_labels = [value_col if num_cols == 1 else f"Col {i + 1}" for i in range(num_cols)]
    input_units = _statistics_input_units_for_labels(units, data_column_labels)

    def _format_summary_value(value, sigma, is_input: bool) -> str:
        cell = _format_table_value(
            value,
            sigma,
            digits,
            use_dcolumn,
            uncertainty_digits,
            is_input=is_input,
            group_size=group_size,
        )[0]
        return _maybe_group(cell)

    summary_rows = build_statistics_latex_summary_rows(
        result,
        format_value=_format_summary_value,
        format_text=latex_escape,
    )
    summary_units = statistics_latex_summary_units_for_rows(units, summary_rows)

    lines = _statistics_latex_preamble(
        use_dcolumn=use_dcolumn, group_size=group_size, native_group_width=native_group_width
    )

    title = f"Statistical Summary ({result.get('method_label', '')})"
    table_caption = caption if caption else f"Statistical summary for {value_col}"
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            f"\\section*{{{latex_escape(title)}}}",
            f"Value column: \\texttt{{{latex_escape(value_col)}}}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{latex_escape(table_caption)}}}",
            f"\\begin{{tabular}}{{{data_col_spec}}}",
            "\\toprule",
            "Entry & " + " & ".join(
                f"\\multicolumn{{1}}{{c}}{{{_latex_label_with_unit(label, input_units.get(label, ''))}}}"
                for label in data_column_labels
            ) + " \\\\",
            "\\midrule",
        ]
    )
    for idx in range(len(data_rows)):
        row_cells = [formatted_columns[col_idx][idx] for col_idx in range(num_cols)]
        lines.append(f"Input row {idx + 1} & " + " & ".join(row_cells) + " \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

    # Summary table (single numeric column)
    summary_numeric_values = _latex_numeric_summary_values(summary_rows)
    if use_dcolumn:
        summary_num_spec = calculate_dcolumn_format_for_column(
            summary_numeric_values,
            "stats_summary",
        )
    else:
        summary_num_spec = siunitx_column_spec(summary_numeric_values)
    summary_has_units = bool(summary_units)
    summary_col_spec = f"l l {summary_num_spec}" if summary_has_units else f"l {summary_num_spec}"
    summary_header = (
        "Entry & Unit & \\multicolumn{1}{c}{Value} \\\\"
        if summary_has_units
        else "Entry & \\multicolumn{1}{c}{Value} \\\\"
    )
    lines.extend(
        [
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{latex_escape(table_caption)} (Summary)}}",
            f"\\begin{{tabular}}{{{summary_col_spec}}}",
            "\\toprule",
            summary_header,
            "\\midrule",
        ]
    )
    for key, val in summary_rows:
        if summary_has_units:
            unit = summary_units.get(key, "")
            lines.append(f"{latex_escape(key)} & {latex_escape(unit)} & {val} \\\\")
        else:
            lines.append(f"{latex_escape(key)} & {val} \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", "\\end{document}"])

    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def generate_statistics_latex_batches(
    value_col: str,
    batches: list[dict],
    digits: int,
    tex_path: str,
    use_dcolumn: bool,
    caption: str | None = None,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    units: Mapping[str, Any] | None = None,
    native_group_width: bool = True,
):
    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec
    from datalab_latex.latex_formatting import group_digits_both_sides

    group_size = max(0, int(latex_group_size))
    # See generate_statistics_latex: app-side pre-grouping when the engine can't vary width.
    app_group = (not native_group_width) and (not use_dcolumn) and group_size > 0

    def _maybe_group(cell: str) -> str:
        if app_group and "\\multicolumn" not in cell and "\\text" not in cell:
            return "\\text{" + group_digits_both_sides(cell, group_size) + "}"
        return cell

    def _build_block(
        batch_idx: int,
        rows,
        sigma_rows,
        result,
        caption_text: str,
        block_value_col: str,
        block_units: Mapping[str, Any] | None,
    ):
        num_cols = len(rows[0]) if rows else 0
        formatted_columns: list[list[str]] = [[] for _ in range(num_cols)]
        for row_idx, row in enumerate(rows):
            for col_idx in range(num_cols):
                value = row[col_idx] if col_idx < len(row) else mp.mpf("0")
                sigma = None
                if sigma_rows and row_idx < len(sigma_rows) and col_idx < len(sigma_rows[row_idx]):
                    sigma = sigma_rows[row_idx][col_idx]
                cell, _ = _format_table_value(
                    value,
                    sigma,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )
                formatted_columns[col_idx].append(_maybe_group(cell))

        if use_dcolumn:
            num_specs = [
                calculate_dcolumn_format_for_column(formatted_columns[i], f"stats_batch_{batch_idx}_col_{i}")
                for i in range(num_cols)
            ]
        elif app_group:
            num_specs = ["r"] * num_cols
        else:
            num_specs = [siunitx_column_spec(formatted_columns[i]) for i in range(num_cols)]
        data_col_spec = "l" + ("" if not num_specs else " " + " ".join(num_specs))
        data_column_labels = [block_value_col if num_cols == 1 else f"Col {i + 1}" for i in range(num_cols)]
        input_units = _statistics_input_units_for_labels(block_units, data_column_labels)

        def _format_summary_value(value, sigma, is_input: bool) -> str:
            cell = _format_table_value(
                value,
                sigma,
                digits,
                use_dcolumn,
                uncertainty_digits,
                is_input=is_input,
                group_size=group_size,
            )[0]
            return _maybe_group(cell)

        summary_rows = build_statistics_latex_summary_rows(
            result,
            format_value=_format_summary_value,
            format_text=latex_escape,
        )
        summary_units = statistics_latex_summary_units_for_rows(block_units, summary_rows)

        lines_block = [
            f"\\subsection*{{Statistics: Batch {batch_idx}}}",
            f"Value column: \\texttt{{{latex_escape(block_value_col)}}}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{latex_escape(caption_text)}}}",
            f"\\begin{{tabular}}{{{data_col_spec}}}",
            "\\toprule",
            "Entry & " + " & ".join(
                f"\\multicolumn{{1}}{{c}}{{{_latex_label_with_unit(label, input_units.get(label, ''))}}}"
                for label in data_column_labels
            ) + " \\\\",
            "\\midrule",
        ]
        for idx in range(len(rows)):
            row_cells = [formatted_columns[col_idx][idx] for col_idx in range(num_cols)]
            lines_block.append(f"Input row {idx + 1} & " + " & ".join(row_cells) + " \\\\")
        lines_block.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

        summary_numeric_values = _latex_numeric_summary_values(summary_rows)
        if use_dcolumn:
            summary_num_spec = calculate_dcolumn_format_for_column(
                summary_numeric_values,
                f"stats_batch_{batch_idx}_summary",
            )
        else:
            summary_num_spec = siunitx_column_spec(summary_numeric_values)
        summary_has_units = bool(summary_units)
        summary_col_spec = f"l l {summary_num_spec}" if summary_has_units else f"l {summary_num_spec}"
        summary_header = (
            "Entry & Unit & \\multicolumn{1}{c}{Value} \\\\"
            if summary_has_units
            else "Entry & \\multicolumn{1}{c}{Value} \\\\"
        )
        lines_block.extend(
            [
                "\\begin{table}[!ht]",
                "\\centering",
                f"\\caption{{{latex_escape(caption_text)} (Summary)}}",
                f"\\begin{{tabular}}{{{summary_col_spec}}}",
                "\\toprule",
                summary_header,
                "\\midrule",
            ]
        )
        for key, val in summary_rows:
            if summary_has_units:
                unit = summary_units.get(key, "")
                lines_block.append(f"{latex_escape(key)} & {latex_escape(unit)} & {val} \\\\")
            else:
                lines_block.append(f"{latex_escape(key)} & {val} \\\\")
        lines_block.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
        return lines_block

    lines = _statistics_latex_preamble(
        use_dcolumn=use_dcolumn, group_size=group_size, native_group_width=native_group_width
    )

    title = f"Statistical Summary ({value_col})"
    base_caption = caption if caption else f"Statistical summary for {value_col}"
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            f"\\section*{{{latex_escape(title)}}}",
        ]
    )
    for batch_number, batch in enumerate(batches, 1):
        idx = batch.get("index") or batch_number
        block_value_col = str(batch.get("value_col") or value_col)
        values = batch.get("values")
        sigmas = batch.get("sigmas")
        if values:
            rows = [(value,) for value in values]
            sigma_rows = [(sigma,) for sigma in sigmas] if sigmas else []
        else:
            rows = batch.get("rows", [])
            sigma_rows = batch.get("sigma_rows", [])
        result = batch.get("result", {})
        caption_text = f"{base_caption}: {block_value_col} (Batch {idx})"
        batch_units = batch.get("units") if isinstance(batch.get("units"), Mapping) else units
        lines.extend(_build_block(idx, rows, sigma_rows, result, caption_text, block_value_col, batch_units))
    lines.append("\\end{document}")
    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def generate_statistics_bootstrap_latex(
    snapshot: Mapping[str, Any],
    tex_path: str,
    use_dcolumn: bool,
    digits: int,
    caption: str | None = None,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    native_group_width: bool = True,
):
    """Generate a standalone LaTeX report from a bootstrap statistics snapshot."""

    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec

    validate_statistics_bootstrap_snapshot(snapshot)
    units_config = snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None
    group_size = max(0, int(latex_group_size))
    batches = _snapshot_row_sequence(snapshot.get("batches"))
    if not batches:
        raise ValueError("statistics bootstrap snapshot has no batches.")

    lines = _statistics_latex_preamble(
        use_dcolumn=use_dcolumn, group_size=group_size, native_group_width=native_group_width
    )
    base_caption = latex_escape(caption or "Bootstrap confidence intervals")
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            "\\section*{Bootstrap Confidence Intervals}",
        ]
    )

    for fallback_index, batch in enumerate(batches, 1):
        source = batch.get("source") if isinstance(batch.get("source"), Mapping) else {}
        value_col = str(source.get("value_column") or f"Column {fallback_index}")
        batch_index = source.get("batch_index") or batch.get("index") or fallback_index
        metric_rows = _snapshot_row_sequence(batch.get("metric_rows"))
        diagnostic_rows = _snapshot_row_sequence(batch.get("diagnostic_rows"))

        formatted_metric_rows = []
        raw_metric_values: list[str] = []
        for row in metric_rows:
            unit = statistics_latex_output_unit_for_keys(units_config, row.get("key"), "result")
            raw_value = _bootstrap_row_text(row)
            raw_metric_values.append(raw_value)
            formatted_metric_rows.append(
                (
                    latex_escape(statistics_snapshot_row_label(row)),
                    _format_bootstrap_metric_value(
                        raw_value,
                        digits,
                        use_dcolumn,
                        uncertainty_digits,
                        group_size,
                    ),
                    latex_escape(unit),
                )
            )
        metric_values = _latex_numeric_summary_values([("", value) for value in raw_metric_values])
        if use_dcolumn:
            value_spec = calculate_dcolumn_format_for_column(
                metric_values,
                f"stats_bootstrap_batch_{fallback_index}_summary",
            )
        else:
            value_spec = siunitx_column_spec(metric_values)
        has_units = any(unit for _label, _value, unit in formatted_metric_rows)
        col_spec = f"l l {value_spec}" if has_units else f"l {value_spec}"
        header = (
            "Metric & Unit & \\multicolumn{1}{c}{Value} \\\\"
            if has_units
            else "Metric & \\multicolumn{1}{c}{Value} \\\\"
        )

        lines.extend(
            [
                f"\\subsection*{{Bootstrap: {latex_escape(value_col)}}}",
                f"Value column: \\texttt{{{latex_escape(value_col)}}}",
                "",
                "\\begin{table}[!ht]",
                "\\centering",
                f"\\caption{{{base_caption}: {latex_escape(value_col)} (Batch {latex_escape(str(batch_index))})}}",
                f"\\begin{{tabular}}{{{col_spec}}}",
                "\\toprule",
                header,
                "\\midrule",
            ]
        )
        for label, value, unit in formatted_metric_rows:
            if has_units:
                lines.append(f"{label} & {unit} & {value} \\\\")
            else:
                lines.append(f"{label} & {value} \\\\")
        lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

        if diagnostic_rows:
            lines.extend(
                [
                    "\\begin{table}[!ht]",
                    "\\centering",
                    f"\\caption{{{base_caption}: {latex_escape(value_col)} (Metadata)}}",
                    "\\begin{tabular}{l l}",
                    "\\toprule",
                    "Metric & Value \\\\",
                    "\\midrule",
                ]
            )
            for row in diagnostic_rows:
                label = latex_escape(statistics_snapshot_row_label(row))
                value = latex_escape(_bootstrap_row_text(row))
                lines.append(f"{label} & {value} \\\\")
            lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

    lines.append("\\end{document}")
    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def generate_statistics_time_series_latex(
    snapshot: Mapping[str, Any],
    tex_path: str,
    use_dcolumn: bool,
    digits: int,
    caption: str | None = None,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    native_group_width: bool = True,
):
    """Generate a standalone LaTeX report from a time-series statistics snapshot."""

    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec

    validate_statistics_time_series_snapshot(snapshot)
    units_config = snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None
    payload = time_series_payload_from_snapshot(snapshot)
    group_size = max(0, int(latex_group_size))
    base_caption = caption or "Time-series statistics"
    method = str(payload.get("series_method") or "time_series")
    time_column = str(payload.get("time_column") or "row index")

    def _numeric_cell(value: object) -> str:
        if value in (None, ""):
            return r"\multicolumn{1}{l}{--}"
        return _format_bootstrap_metric_value(
            value,
            digits,
            use_dcolumn,
            uncertainty_digits,
            group_size,
        )

    rows: list[tuple[str, str, str, str, str, str, str, str, str]] = []
    observed_values: list[str] = []
    result_values: list[str] = []
    uncertainty_values: list[str] = []
    has_units = False
    for fallback_index, raw_column in enumerate(payload.get("columns", ()), 1):
        if not isinstance(raw_column, Mapping):
            continue
        value_col = str(raw_column.get("value_column") or f"Column {fallback_index}")
        unit = statistics_latex_output_unit_for_keys(
            units_config,
            value_col,
            "series",
            "smoothed",
            "result",
        )
        if unit:
            has_units = True
        raw_points = raw_column.get("points")
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes, bytearray, memoryview)):
            continue
        for point in raw_points:
            if not isinstance(point, Mapping):
                continue
            observed_value = point.get("observed_value")
            result_value = point.get("value")
            uncertainty_value = point.get("uncertainty")
            observed_cell = _numeric_cell(observed_value)
            result_cell = _numeric_cell(result_value)
            uncertainty_cell = _numeric_cell(uncertainty_value)
            observed_values.append("" if observed_value is None else str(observed_value))
            result_values.append("" if result_value is None else str(result_value))
            uncertainty_values.append("" if uncertainty_value is None else str(uncertainty_value))
            window_rows = point.get("window_source_row_ids")
            if isinstance(window_rows, Sequence) and not isinstance(window_rows, (str, bytes, bytearray, memoryview)):
                window_text = " ".join(str(item) for item in window_rows)
            else:
                window_text = ""
            rows.append(
                (
                    latex_escape(value_col),
                    latex_escape(unit),
                    latex_escape(str(point.get("source_row_id") or "")),
                    latex_escape(str(point.get("time") or "")),
                    observed_cell,
                    result_cell,
                    uncertainty_cell,
                    latex_escape(str(point.get("status") or "")),
                    latex_escape(window_text),
                )
            )
    if not rows:
        raise ValueError("statistics time-series snapshot has no points.")

    def _numeric_spec(values: list[str], key: str) -> str:
        numeric_values = _latex_numeric_summary_values([("", value) for value in values])
        if use_dcolumn:
            return str(calculate_dcolumn_format_for_column(numeric_values, key))
        return str(siunitx_column_spec(numeric_values))

    observed_spec = _numeric_spec(observed_values, "statistics_time_series_observed")
    result_spec = _numeric_spec(result_values, "statistics_time_series_result")
    uncertainty_spec = _numeric_spec(uncertainty_values, "statistics_time_series_uncertainty")
    prefix_spec = "l l l l" if has_units else "l l l"
    header = (
        r"Column & Unit & Row & Time & \multicolumn{1}{c}{Observed} & "
        r"\multicolumn{1}{c}{Result} & \multicolumn{1}{c}{Uncertainty} & "
        r"Status & Window rows \\"
        if has_units
        else (
            r"Column & Row & Time & \multicolumn{1}{c}{Observed} & "
            r"\multicolumn{1}{c}{Result} & \multicolumn{1}{c}{Uncertainty} & "
            r"Status & Window rows \\"
        )
    )
    lines = _statistics_latex_preamble(
        use_dcolumn=use_dcolumn, group_size=group_size, native_group_width=native_group_width
    )
    escaped_caption = latex_escape(base_caption)
    lines.extend(
        [
            r"\geometry{margin=1in}",
            r"\begin{document}",
            r"\section*{Time-Series Statistics}",
            f"Method: \\texttt{{{latex_escape(method)}}}",
            f"Time/index: \\texttt{{{latex_escape(time_column)}}}",
            "",
            r"\begin{table}[!ht]",
            r"\centering",
            f"\\caption{{{escaped_caption}: {latex_escape(method)}}}",
            f"\\begin{{tabular}}{{{prefix_spec} {observed_spec} {result_spec} {uncertainty_spec} l l}}",
            r"\toprule",
            header,
            r"\midrule",
        ]
    )
    for column, unit, row_id, time_label, observed, result, uncertainty, status, window_text in rows:
        if has_units:
            lines.append(
                f"{column} & {unit} & {row_id} & {time_label} & {observed} & {result} & "
                f"{uncertainty} & {status} & {window_text} \\\\"
            )
        else:
            lines.append(
                f"{column} & {row_id} & {time_label} & {observed} & {result} & {uncertainty} & "
                f"{status} & {window_text} \\\\"
            )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", "", r"\end{document}"])
    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def generate_statistics_hypothesis_latex(
    snapshot: Mapping[str, Any],
    tex_path: str,
    use_dcolumn: bool,
    digits: int,
    caption: str | None = None,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    native_group_width: bool = True,
):
    """Generate a standalone LaTeX report from a hypothesis-test snapshot."""

    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec

    validate_statistics_hypothesis_snapshot(snapshot)
    units_config = snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None
    hypothesis_payload = snapshot.get("hypothesis_test")
    if not isinstance(hypothesis_payload, Mapping):
        raise ValueError("statistics hypothesis snapshot has no hypothesis_test payload.")
    _text, csv_rows, _headers = render_statistics_hypothesis_payload_outputs(
        hypothesis_payload,
        units=units_config,
    )
    group_size = max(0, int(latex_group_size))
    base_caption = latex_escape(caption or "Hypothesis test")
    test_kind = str(hypothesis_payload.get("test_kind") or "hypothesis_test")
    metadata_rows = _statistics_hypothesis_latex_metadata_rows(hypothesis_payload)

    formatted_rows: list[tuple[str, str, str, str]] = []
    for row in csv_rows:
        metric = latex_escape(str(row.get("metric") or ""))
        value = _format_bootstrap_metric_value(
            row.get("value", ""),
            digits,
            use_dcolumn,
            uncertainty_digits,
            group_size,
        )
        note = latex_escape(str(row.get("note") or ""))
        unit = latex_escape(str(row.get("value_unit") or ""))
        formatted_rows.append((metric, value, note, unit))

    metric_values = _latex_numeric_summary_values(
        [(metric, value) for metric, value, _note, _unit in formatted_rows]
    )
    if use_dcolumn:
        value_spec = calculate_dcolumn_format_for_column(metric_values, "statistics_hypothesis_summary")
    else:
        value_spec = siunitx_column_spec(metric_values)
    has_units = any(unit for _metric, _value, _note, unit in formatted_rows)
    result_spec = f"l l {value_spec} l" if has_units else f"l {value_spec} l"
    result_header = (
        "Metric & Unit & \\multicolumn{1}{c}{Value} & Note \\\\"
        if has_units
        else "Metric & \\multicolumn{1}{c}{Value} & Note \\\\"
    )

    lines = _statistics_latex_preamble(
        use_dcolumn=use_dcolumn, group_size=group_size, native_group_width=native_group_width
    )
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            "\\section*{Hypothesis Test}",
            f"Test: \\texttt{{{latex_escape(test_kind)}}}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{base_caption}: {latex_escape(test_kind)} (Metadata)}}",
            "\\begin{tabular}{l l}",
            "\\toprule",
            "Field & Value \\\\",
            "\\midrule",
        ]
    )
    for field, value in metadata_rows:
        lines.append(f"{field} & {value} \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{base_caption}: {latex_escape(test_kind)}}}",
            f"\\begin{{tabular}}{{{result_spec}}}",
            "\\toprule",
            result_header,
            "\\midrule",
        ]
    )
    for metric, value, note, unit in formatted_rows:
        if has_units:
            lines.append(f"{metric} & {unit} & {value} & {note} \\\\")
        else:
            lines.append(f"{metric} & {value} & {note} \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", "", "\\end{document}"])
    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def _statistics_hypothesis_latex_metadata_rows(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), Mapping) else {}
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    diagnostics = payload.get("diagnostics")
    null_parameters = inputs.get("null_parameters") if isinstance(inputs.get("null_parameters"), Mapping) else {}
    value_columns = inputs.get("value_columns")

    rows: list[tuple[str, str]] = [
        ("Test", str(payload.get("test_kind") or "")),
        ("Alternative", str(payload.get("alternative") or "")),
        ("Alpha", str(payload.get("alpha") or "")),
        ("Backend", str(payload.get("backend") or "")),
        ("Backend version", str(payload.get("backend_version") or "")),
        ("Precision digits", str(payload.get("precision_used") or "")),
    ]
    if isinstance(value_columns, Sequence) and not isinstance(
        value_columns,
        (str, bytes, bytearray, memoryview),
    ):
        rows.append(("Value columns", ", ".join(str(column) for column in value_columns)))
    if null_parameters:
        rows.append(
            (
                "Null parameters",
                ", ".join(f"{key}={value}" for key, value in sorted(null_parameters.items())),
            )
        )
    for key in (
        "sample_size",
        "sample_size_a",
        "sample_size_b",
        "degrees_of_freedom",
        "expected_source",
        "fitted_parameter_count",
    ):
        if result.get(key) is not None:
            rows.append((key, str(result.get(key))))
    if isinstance(diagnostics, Sequence) and not isinstance(
        diagnostics,
        (str, bytes, bytearray, memoryview),
    ):
        diagnostic_text = "; ".join(
            f"{row.get('severity', '')}:{row.get('code', '')}"
            for row in diagnostics
            if isinstance(row, Mapping)
        )
        rows.append(("Diagnostics", diagnostic_text or "none"))
    else:
        rows.append(("Diagnostics", "none"))
    return [(latex_escape(field), latex_escape(value)) for field, value in rows]
