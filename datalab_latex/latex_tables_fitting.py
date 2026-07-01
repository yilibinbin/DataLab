from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mpmath import mp

from shared.latex_escaping import latex_escape as _canonical_latex_escape

from .latex_formatting import calculate_dcolumn_format_for_column, siunitx_column_spec

_NUMERIC_COLUMNS = ("chi2", "reduced_chi2", "aic", "bic", "rmse", "r2")


def build_fitting_comparison_latex_block(
    rows: Sequence[Mapping[str, Any]],
    *,
    use_dcolumn: bool,
    caption_text: str = "Selected model comparison",
) -> list[str]:
    """Build a shared LaTeX table block for selected-fit comparison rows."""

    row_list = [dict(row) for row in rows]
    value_cells = [
        _metric_text(row.get(column))
        for row in row_list
        for column in _NUMERIC_COLUMNS
        if _is_numeric_latex_cell(_metric_text(row.get(column)))
    ]
    if not value_cells:
        value_cells = ["0"]
    if use_dcolumn:
        numeric_spec = calculate_dcolumn_format_for_column(value_cells, "fit_comparison_values")
    else:
        numeric_spec = siunitx_column_spec(value_cells)
    metric_specs = " ".join(numeric_spec for _ in _NUMERIC_COLUMNS)
    col_spec = f"r l l r {metric_specs} l l"

    lines = [
        "",
        "\\begin{table}[h]",
        "\\centering",
        f"\\caption{{{latex_escape(caption_text)}}}",
        f"\\begin{{tabular}}{{{col_spec}}}",
        "\\toprule",
        (
            # The six metric columns are siunitx S (or dcolumn d) columns, which
            # parse cell content as a number; wrap the non-numeric titles in
            # \multicolumn{1}{c}{...} so the header row does not break compilation.
            "Order & Model & Status & Params & "
            "\\multicolumn{1}{c}{$\\chi^2$} & \\multicolumn{1}{c}{Reduced $\\chi^2$} & "
            "\\multicolumn{1}{c}{AIC} & \\multicolumn{1}{c}{BIC} & "
            "\\multicolumn{1}{c}{RMSE} & \\multicolumn{1}{c}{$R^2$} & Warnings & Error \\\\"
        ),
        "\\midrule",
    ]
    for row in row_list:
        lines.append(_comparison_latex_row(row))
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )
    return lines


def latex_escape(text: object) -> str:
    # Delegates to the single canonical implementation (P2-6) so escaping can't
    # diverge between table generators and the web layer.
    return _canonical_latex_escape(text)


def _comparison_latex_row(row: Mapping[str, Any]) -> str:
    cells = [
        latex_escape(row.get("order", "")),
        latex_escape(row.get("model_label", "")),
        latex_escape(row.get("status", "")),
        latex_escape(row.get("free_parameters", "")),
        *[_latex_metric_cell(row.get(column)) for column in _NUMERIC_COLUMNS],
        _latex_text_cell(row.get("warnings", "")),
        _latex_text_cell(row.get("error", "")),
    ]
    return " & ".join(cells) + " \\\\"


def _latex_metric_cell(value: Any) -> str:
    text = _metric_text(value)
    if not text:
        return "\\multicolumn{1}{c}{}"
    if not _is_numeric_latex_cell(text):
        return f"\\multicolumn{{1}}{{c}}{{{latex_escape(text)}}}"
    return text


def _metric_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _latex_text_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return "\\multicolumn{1}{l}{}"
    return f"\\multicolumn{{1}}{{l}}{{{latex_escape(text)}}}"


def _is_numeric_latex_cell(text: str) -> bool:
    if text.startswith("\\multicolumn"):
        return False
    try:
        mp.mpf(text)
    except Exception:
        return False
    return True
