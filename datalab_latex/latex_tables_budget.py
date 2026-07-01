from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mpmath import mp

from .latex_formatting import calculate_dcolumn_format_for_column, siunitx_column_spec, siunitx_safe_cell
from .latex_tables_fitting import latex_escape

_NUMERIC_COLUMNS = ("value", "uncertainty", "percent", "cumulative_percent")


def build_budget_latex_block(
    rows: Sequence[Mapping[str, Any]],
    *,
    use_dcolumn: bool,
    caption_text: str = "Uncertainty budget",
) -> list[str]:
    """Build a shared LaTeX budget table block from budget CSV rows."""

    row_list = [dict(row) for row in rows]
    numeric_cells = [
        _metric_text(row.get(column))
        for row in row_list
        for column in _NUMERIC_COLUMNS
        if _is_numeric_latex_cell(_metric_text(row.get(column)))
    ]
    if not numeric_cells:
        numeric_cells = ["0"]
    numeric_spec = (
        calculate_dcolumn_format_for_column(numeric_cells, "budget_values")
        if use_dcolumn
        else siunitx_column_spec(numeric_cells)
    )
    metric_specs = " ".join(numeric_spec for _ in _NUMERIC_COLUMNS)
    col_spec = f"l l l {metric_specs} l"

    lines = [
        "",
        "\\begin{table}[h]",
        "\\centering",
        f"\\caption{{{latex_escape(caption_text)}}}",
        f"\\begin{{tabular}}{{{col_spec}}}",
        "\\toprule",
        "Family & Category & Source & Value & Uncertainty & Percent & Cumulative percent & Severity \\\\",
        "\\midrule",
    ]
    for row in row_list:
        lines.append(_budget_latex_row(row, use_dcolumn=use_dcolumn))
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    return lines


def _budget_latex_row(row: Mapping[str, Any], *, use_dcolumn: bool) -> str:
    cells = [
        latex_escape(row.get("family", "")),
        latex_escape(row.get("category", "")),
        latex_escape(row.get("source_key", "") or row.get("label_key", "")),
        *[_latex_metric_cell(row.get(column), use_dcolumn=use_dcolumn) for column in _NUMERIC_COLUMNS],
        latex_escape(row.get("severity", "")),
    ]
    return " & ".join(cells) + " \\\\"


def _latex_metric_cell(value: Any, *, use_dcolumn: bool) -> str:
    text = _metric_text(value)
    if not text:
        return "\\multicolumn{1}{l}{}"
    numeric_text = _numeric_latex_text(text)
    if numeric_text is None:
        return f"\\multicolumn{{1}}{{l}}{{{latex_escape(text)}}}"
    if use_dcolumn:
        return numeric_text
    return str(siunitx_safe_cell(numeric_text))


def _metric_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_numeric_latex_cell(text: str) -> bool:
    return _numeric_latex_text(text) is not None


def _numeric_latex_text(text: str) -> str | None:
    if text.startswith("\\multicolumn"):
        return None
    numeric_text = text[:-1].strip() if text.endswith("%") else text
    try:
        numeric = mp.mpf(numeric_text)
    except Exception:
        return None
    return numeric_text if mp.isfinite(numeric) else None


__all__ = ["build_budget_latex_block"]
