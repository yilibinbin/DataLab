"""Uncertainty-budget comparison for history compare (extracted from
``history_compare.py`` to shrink that god-file — P2-4).

This is the self-contained budget-comparison family: ``_compare_budget_rows``
and its private helpers. It reuses the low-level formatting helpers that stay in
``history_compare`` (``_parse_number``, ``_diagnostic``, ``_cell``,
``_append_delta_from_values``, ``_safe_key_token``); those are imported here at
module top level, which is cycle-safe because ``history_compare`` imports
``_compare_budget_rows`` *lazily* (inside ``_build_history_comparison``), so there
is no import-time back-edge.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mpmath import mp

from .history_compare import (
    _append_delta_from_values,
    _cell,
    _diagnostic,
    _parse_number,
    _safe_key_token,
)
from .results import AnalysisRow
from .uncertainty_budget import (
    UncertaintyBudgetRow,
    budget_source_key_base,
    extract_uncertainty_budget,
)


def _compare_budget_rows(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    left_id: str | None,
    right_id: str | None,
) -> tuple[list[AnalysisRow], list[AnalysisRow]]:
    left_budget = extract_uncertainty_budget(left, source_snapshot_id=left_id or left_label)
    right_budget = extract_uncertainty_budget(right, source_snapshot_id=right_id or right_label)
    diagnostics = [
        _budget_extraction_diagnostic(row, side="left", label=left_label) for row in left_budget.diagnostics
    ]
    diagnostics.extend(
        _budget_extraction_diagnostic(row, side="right", label=right_label) for row in right_budget.diagnostics
    )
    if not left_budget.rows and not right_budget.rows:
        return [], diagnostics

    rows: list[AnalysisRow] = []
    left_rows = {_budget_match_key(row): row for row in left_budget.rows}
    right_rows = {_budget_match_key(row): row for row in right_budget.rows}
    for match_key in sorted(set(left_rows) | set(right_rows)):
        left_row = left_rows.get(match_key)
        right_row = right_rows.get(match_key)
        if left_row is None or right_row is None:
            rows.append(_missing_budget_row(match_key, left_row, right_row))
            continue
        for field in ("value", "uncertainty", "percent", "cumulative_percent"):
            left_raw = getattr(left_row, field)
            right_raw = getattr(right_row, field)
            if left_raw is None and right_raw is None:
                continue
            if left_raw is None or right_raw is None:
                rows.append(_missing_budget_field(match_key, field, missing_side="left" if left_raw is None else "right"))
                continue
            left_value = _parse_number(left_raw, percent=field in {"percent", "cumulative_percent"})
            right_value = _parse_number(right_raw, percent=field in {"percent", "cumulative_percent"})
            if left_value is None or right_value is None:
                rows.append(
                    _diagnostic(
                        f"budget.{_budget_match_token(match_key)}.{field}.non_numeric",
                        (
                            f"non-numeric budget field {field!r} on "
                            f"{_invalid_budget_sides(left_value, right_value)} for {match_key[1]!r}"
                        ),
                    )
                )
                continue
            _append_delta_from_values(
                left_value,
                right_value,
                key=f"budget.{right_row.category}.{_budget_source_token(right_row)}.{field}",
                label_key="history.compare.budget_delta",
                left_raw=left_raw,
                right_raw=right_raw,
                left_label=left_label,
                right_label=right_label,
                rows=rows,
            )
    return rows, diagnostics


def _missing_budget_field(match_key: tuple[str, str], field: str, *, missing_side: str) -> AnalysisRow:
    return _diagnostic(
        f"budget.{_budget_match_token(match_key)}.{field}.missing",
        f"budget field {field!r} is missing on {missing_side} for {match_key[1]!r}",
    )


def _invalid_budget_sides(left_value: mp.mpf | None, right_value: mp.mpf | None) -> str:
    sides: list[str] = []
    if left_value is None:
        sides.append("left")
    if right_value is None:
        sides.append("right")
    return " and ".join(sides) or "unknown side"


def _budget_extraction_diagnostic(row: AnalysisRow, *, side: str, label: str) -> AnalysisRow:
    return _diagnostic(
        f"history.compare.budget.{side}.{row.key}",
        f"{label}: {_cell(row.value or row.message_key or row.key)}",
        severity=row.severity,
    )


def _missing_budget_row(
    match_key: tuple[str, str],
    left_row: UncertaintyBudgetRow | None,
    right_row: UncertaintyBudgetRow | None,
) -> AnalysisRow:
    side = "left" if left_row is None else "right"
    category, source = match_key
    return _diagnostic(
        f"budget.{_safe_key_token(category)}.{_safe_key_token(source)}.missing",
        f"budget row {source!r} is missing on {side}",
    )


def _budget_match_key(row: UncertaintyBudgetRow) -> tuple[str, str]:
    return row.category, row.source_key or row.label_key


def _budget_match_token(match_key: tuple[str, str]) -> str:
    category, source = match_key
    return f"{_safe_key_token(category)}.{_safe_key_token(source)}"


def _budget_source_token(row: UncertaintyBudgetRow) -> str:
    # The source_key may be an encoded analysis-row token; decode to the readable
    # base so the delta row key is human-readable (contribution_percent.x rather
    # than a re-encoded base64 blob).
    return budget_source_key_base(row.source_key or row.label_key)
