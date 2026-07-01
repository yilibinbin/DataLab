from __future__ import annotations

from typing import Any

from datalab_core.history import HistoryEntry
from datalab_core.history_compare import build_history_comparison

from app_desktop.history_compare_panel import (
    COMPARE_CSV_HEADERS,
    build_history_comparison_display,
    history_compare_selection_diagnostic,
    is_displayable_history_comparison,
)


def test_history_compare_display_csv_rows_preserve_core_payload_fields() -> None:
    payload = build_history_comparison(
        _history_snapshot(
            "statistics",
            {
                "schema": "datalab.result_snapshot.statistics",
                "schema_version": 1,
                "family": "statistics",
                "mode": "mean",
                "metric_rows": [{"key": "mean", "label_key": "statistics.metric.mean", "value": "1.25"}],
                "source": {"row_count": 2},
            },
        ),
        _history_snapshot(
            "statistics",
            {
                "schema": "datalab.result_snapshot.statistics",
                "schema_version": 1,
                "family": "statistics",
                "mode": "mean",
                "metric_rows": [{"key": "mean", "label_key": "statistics.metric.mean", "value": "2.75"}],
                "source": {"row_count": 3},
            },
        ),
        left_label="Recent",
        right_label="Current",
        left_id="h2",
        right_id="h1",
    )

    display = build_history_comparison_display(payload, language="en")

    assert is_displayable_history_comparison(payload) is True
    assert display.csv_headers == COMPARE_CSV_HEADERS
    payload_row = payload["rows"][0]
    csv_row = next(row for row in display.csv_rows if row["key"] == payload_row["key"])
    assert csv_row["section"] == "comparison"
    assert csv_row["value"] == payload_row["value"]
    assert csv_row["source"] == payload_row["source"]
    assert csv_row["severity"] == payload_row["severity"]
    assert csv_row["message_key"] == ""
    assert "History comparison" in display.text
    assert "delta.statistics.metric.mean.value" in display.text


def test_history_compare_display_maps_diagnostics_to_message_column() -> None:
    payload = build_history_comparison(
        _history_snapshot(
            "statistics",
            {
                "schema": "datalab.result_snapshot.statistics",
                "schema_version": 1,
                "family": "statistics",
                "metric_rows": [{"key": "mean", "label_key": "statistics.metric.mean", "value": "n/a"}],
            },
        ),
        _history_snapshot(
            "statistics",
            {
                "schema": "datalab.result_snapshot.statistics",
                "schema_version": 1,
                "family": "statistics",
                "metric_rows": [{"key": "mean", "label_key": "statistics.metric.mean", "value": "2"}],
            },
        ),
    )

    display = build_history_comparison_display(payload)

    diagnostic = next(row for row in display.csv_rows if row["section"] == "diagnostic")
    assert diagnostic["message"] == diagnostic["value"]
    assert diagnostic["message_key"] == "statistics.metric.mean.value.non_numeric"


def test_history_compare_display_includes_budget_rows_in_csv() -> None:
    payload = build_history_comparison(
        _history_snapshot(
            "uncertainty",
            {
                "schema": "datalab.result_snapshot.uncertainty",
                "schema_version": 1,
                "family": "uncertainty",
                "diagnostic_rows": [
                    {
                        "key": "contribution_percent.x",
                        "label_key": "uncertainty.diagnostic.contribution_percent",
                        "value": "25",
                    }
                ],
            },
        ),
        _history_snapshot(
            "uncertainty",
            {
                "schema": "datalab.result_snapshot.uncertainty",
                "schema_version": 1,
                "family": "uncertainty",
                "diagnostic_rows": [
                    {
                        "key": "contribution_percent.x",
                        "label_key": "uncertainty.diagnostic.contribution_percent",
                        "value": "40",
                    }
                ],
            },
        ),
        left_label="Recent",
        right_label="Current",
    )

    display = build_history_comparison_display(payload)

    budget_row = next(row for row in display.csv_rows if row["section"] == "budget")
    assert budget_row["key"] == "delta.budget.uncertainty.contribution_percent.contribution_percent.x.percent"
    assert budget_row["value"] == "15.0"
    assert "budget" in display.text.lower()


def test_history_compare_selection_diagnostic_rejects_unsupported_schema() -> None:
    current = _entry("h1", "Current", "statistics", "datalab.result_snapshot.statistics")
    selected = _entry("h2", "Recent", "statistics", "datalab.result_snapshot.future_statistics")

    message = history_compare_selection_diagnostic(current, selected, language="en")

    assert message == "The selected history entry uses an unsupported semantic snapshot schema."


def _entry(entry_id: str, label: str, family: str, result_schema: str) -> HistoryEntry:
    return HistoryEntry(
        entry_id=entry_id,
        label=label,
        created_at="2026-06-21T00:00:00Z",
        semantic_snapshot=_history_snapshot(
            family,
            {
                "schema": result_schema,
                "schema_version": 1,
                "family": family,
                "metric_rows": [],
            },
        ),
    )


def _history_snapshot(family: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "datalab.history.entry.v1",
        "snapshot_version": 1,
        "family": family,
        "kind": family,
        "language": "en",
        "status": "success",
        "input_signature": {
            "current_mode": family,
            "workspace_hash": f"hash-{family}",
            "data_hash": f"data-{family}",
            "constants_hash": f"constants-{family}",
            "formula_model": {},
            "options": {},
        },
        "result": result,
    }
