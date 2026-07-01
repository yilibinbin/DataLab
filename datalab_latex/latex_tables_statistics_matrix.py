from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .latex_tables_common import (
    _build_standalone_preamble,
    _estimate_page_geometry,
    statistics_latex_output_unit_for_keys,
)
from .latex_tables_fitting import latex_escape


def generate_statistics_matrix_latex(
    payload: Mapping[str, Any],
    output_path: str | Path | None = None,
    *,
    caption_text: str = "Statistics covariance/correlation matrix",
    use_dcolumn: bool = True,
    latex_group_size: int = 3,
    units: Mapping[str, Any] | None = None,
) -> str:
    """Generate a standalone LaTeX document for statistics matrix payloads."""

    # Payload is already validated in datalab_core before it reaches the renderer
    # (statistics_matrix.py:77); re-validating here forced a datalab_latex ->
    # datalab_core layering inversion (P2-5). The renderer trusts its typed input.
    columns = tuple(str(column) for column in payload["columns"])
    matrices = payload["matrices"]
    row_count = sum(len(columns) for _ in ("covariance", "correlation"))
    width, _height = _estimate_page_geometry([max(8, len(column) + 2) for column in columns], row_count)
    lines = _build_standalone_preamble(
        width,
        include_dcolumn=use_dcolumn,
        needs_cjk=any(_contains_cjk_text(column) for column in columns + (caption_text,)),
        latex_group_size=latex_group_size,
    )
    lines.extend(
        [
            f"\\section*{{{latex_escape(caption_text)}}}",
            (
                "\\noindent "
                f"Missing data: \\texttt{{{latex_escape(str(payload['missing_policy']))}}}; "
                f"denominator: \\texttt{{{latex_escape(str(payload['denominator']))}}}; "
                f"rows: {latex_escape(str(payload['row_count']))}/{latex_escape(str(payload['input_row_count']))}."
            ),
            "",
        ]
    )
    for kind in ("covariance", "correlation"):
        block = matrices[kind]
        unit = statistics_latex_output_unit_for_keys(units, "covariance", "result") if kind == "covariance" else ""
        lines.extend(_matrix_table_block(kind, columns, block, use_dcolumn=use_dcolumn, unit=unit))
        lines.append("")
    lines.append("\\end{document}")
    tex = "\n".join(lines) + "\n"
    if output_path is not None:
        Path(output_path).write_text(tex, encoding="utf-8")
    return tex


def _matrix_table_block(
    kind: str,
    columns: tuple[str, ...],
    block: Mapping[str, Any],
    *,
    use_dcolumn: bool,
    unit: str = "",
) -> list[str]:
    numeric_spec = "d{12}" if use_dcolumn else "S[table-format=1.16]"
    column_spec = " ".join(["l", *(numeric_spec for _ in columns)])
    lines = [
        f"\\subsection*{{{latex_escape(kind.capitalize())}}}",
        f"\\noindent Unit: \\texttt{{{latex_escape(unit)}}}" if unit else "",
        "\\begin{threeparttable}",
        f"\\begin{{tabular}}{{{column_spec}}}",
        "\\toprule",
        " & ".join([""] + [latex_escape(column) for column in columns]) + r" \\",
        "\\midrule",
    ]
    lines = [line for line in lines if line]
    values = block["values"]
    for row_column, row in zip(columns, values):
        cells = [_numeric_cell(cell) for cell in row]
        lines.append(" & ".join([latex_escape(row_column)] + cells) + r" \\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{threeparttable}"])
    return lines


def _numeric_cell(value: object) -> str:
    if value is None or value == "":
        return r"\multicolumn{1}{c}{--}"
    return str(value)


def _contains_cjk_text(value: object) -> bool:
    text = str(value)
    return any(
        "\u3040" <= char <= "\u30ff"
        or "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in text
    )


__all__ = ["generate_statistics_matrix_latex"]
