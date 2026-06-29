"""Desktop helpers for uncertainty-budget dashboard display/export."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from datalab_core.history import HistoryEntry
from datalab_core.uncertainty_budget import (
    BudgetExtractionResult,
    UncertaintyBudgetRow,
    extract_uncertainty_budget,
)

BUDGET_CSV_HEADERS = [
    "family",
    "result_id",
    "source_snapshot_id",
    "source_row_id",
    "source_key",
    "category",
    "label_key",
    "value",
    "uncertainty",
    "percent",
    "cumulative_percent",
    "method",
    "severity",
    "notes",
]


@dataclass(frozen=True)
class BudgetDashboardDisplay:
    text: str
    csv_rows: list[dict[str, str]]
    csv_headers: list[str]
    budget_rows: tuple[UncertaintyBudgetRow, ...]
    diagnostics: tuple[dict[str, str], ...]
    suggestion: str = "uncertainty_budget.csv"


def build_budget_dashboard_display(
    snapshot: Mapping[str, Any],
    *,
    source_snapshot_id: str = "snapshot",
    language: str = "en",
) -> BudgetDashboardDisplay:
    """Build a read-only desktop display from an existing semantic result snapshot."""

    extraction = extract_uncertainty_budget(snapshot, source_snapshot_id=source_snapshot_id)
    csv_rows = budget_rows_to_csv_rows(extraction.rows)
    diagnostics = _diagnostic_rows(extraction)
    return BudgetDashboardDisplay(
        text=_markdown_text(
            extraction.rows,
            diagnostics,
            source_snapshot_id=source_snapshot_id,
            language=language,
        ),
        csv_rows=csv_rows,
        csv_headers=list(BUDGET_CSV_HEADERS),
        budget_rows=extraction.rows,
        diagnostics=tuple(diagnostics),
    )


def build_budget_dashboard_for_history_entry(
    entry: HistoryEntry,
    *,
    language: str = "en",
) -> BudgetDashboardDisplay:
    result = entry.semantic_snapshot.get("result")
    if not isinstance(result, Mapping):
        return BudgetDashboardDisplay(
            text=_localized(
                language,
                zh="所选历史记录没有可用的语义结果快照。",
                en="The selected history entry has no semantic result snapshot.",
            ),
            csv_rows=[],
            csv_headers=list(BUDGET_CSV_HEADERS),
            budget_rows=(),
            diagnostics=(
                {
                    "key": "budget.history_entry.missing_result_snapshot",
                    "severity": "error",
                    "message": "semantic result snapshot missing",
                },
            ),
        )
    return build_budget_dashboard_display(result, source_snapshot_id=entry.entry_id, language=language)


def budget_rows_to_csv_rows(rows: Sequence[UncertaintyBudgetRow]) -> list[dict[str, str]]:
    return [
        {
            "family": row.family,
            "result_id": row.result_id,
            "source_snapshot_id": row.source_snapshot_id,
            "source_row_id": _cell(row.source_row_id),
            "source_key": _cell(row.source_key),
            "category": row.category,
            "label_key": row.label_key,
            "value": _cell(row.value),
            "uncertainty": _cell(row.uncertainty),
            "percent": _cell(row.percent),
            "cumulative_percent": _cell(row.cumulative_percent),
            "method": _cell(row.method),
            "severity": row.severity,
            "notes": "; ".join(row.notes),
        }
        for row in rows
    ]


def build_budget_pareto_plot_spec(rows: Sequence[UncertaintyBudgetRow]) -> dict[str, object] | None:
    """Return a small plot data spec only when contribution percent rows exist."""

    percent_rows = [row for row in rows if row.category == "uncertainty.contribution_percent" and row.percent]
    if not percent_rows:
        return None
    cumulative_by_suffix = {
        _contribution_suffix(row.source_key, "contribution_cumulative_percent."): row.cumulative_percent
        for row in rows
        if row.category == "uncertainty.contribution_cumulative_percent" and row.cumulative_percent
    }
    labels: list[str] = []
    percent: list[str] = []
    cumulative: list[str] = []
    for row in percent_rows:
        labels.append(row.source_key or row.label_key)
        percent.append(str(row.percent))
        suffix = _contribution_suffix(row.source_key, "contribution_percent.")
        cumulative.append(str(cumulative_by_suffix.get(suffix) or row.cumulative_percent or row.percent))
    return {
        "kind": "uncertainty_budget_pareto",
        "labels": labels,
        "percent": percent,
        "cumulative_percent": cumulative,
    }


def _markdown_text(
    rows: Sequence[UncertaintyBudgetRow],
    diagnostics: Sequence[Mapping[str, str]],
    *,
    source_snapshot_id: str,
    language: str,
) -> str:
    title = _localized(language, zh="不确定度预算", en="Uncertainty budget")
    empty = _localized(language, zh="没有可显示的预算行。", en="No budget rows are available.")
    total_note = _localized(
        language,
        zh="未计算跨模块总预算；只有在快照提供兼容分母和协方差/相关性元数据时才会聚合。",
        en="No cross-family total is computed; aggregation requires compatible denominators and covariance/correlation metadata.",
    )
    lines = [f"# {title}", "", f"- Snapshot: `{source_snapshot_id}`", f"- {total_note}", ""]
    if rows:
        lines.extend(["| Family | Category | Source | Value | Uncertainty | % | Cumulative % | Severity |", "|---|---|---|---:|---:|---:|---:|---|"])
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(row.family),
                        _markdown_cell(row.category),
                        _markdown_cell(row.source_key or row.label_key),
                        _markdown_cell(row.value),
                        _markdown_cell(row.uncertainty),
                        _markdown_cell(row.percent),
                        _markdown_cell(row.cumulative_percent),
                        _markdown_cell(row.severity),
                    ]
                )
                + " |"
            )
    else:
        lines.append(empty)
    if diagnostics:
        diag_title = _localized(language, zh="诊断", en="Diagnostics")
        lines.extend(["", f"## {diag_title}"])
        for diagnostic in diagnostics:
            lines.append(f"- `{_cell(diagnostic.get('key'))}`: {_cell(diagnostic.get('message'))}")
    return "\n".join(lines)


def _diagnostic_rows(extraction: BudgetExtractionResult) -> list[dict[str, str]]:
    return [
        {
            "key": row.key,
            "severity": row.severity,
            "message": _cell(row.value or row.message_key or row.key),
        }
        for row in extraction.diagnostics
    ]


def _contribution_suffix(source_key: str | None, prefix: str) -> str:
    text = source_key or ""
    return text[len(prefix) :] if text.startswith(prefix) else text


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def _markdown_cell(value: object) -> str:
    text = _cell(value)
    return text.replace("|", "\\|") if text else ""


def _localized(language: str, *, zh: str, en: str) -> str:
    return zh if str(language).lower().startswith("zh") else en


__all__ = [
    "BUDGET_CSV_HEADERS",
    "BudgetDashboardDisplay",
    "budget_rows_to_csv_rows",
    "build_budget_dashboard_display",
    "build_budget_dashboard_for_history_entry",
    "build_budget_pareto_plot_spec",
]
