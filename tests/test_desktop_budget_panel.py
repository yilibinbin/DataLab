from __future__ import annotations

from typing import Any


def test_budget_dashboard_display_exports_rows_and_diagnostics() -> None:
    from app_desktop.budget_panel import BUDGET_CSV_HEADERS, build_budget_dashboard_display

    display = build_budget_dashboard_display(
        _uncertainty_snapshot(),
        source_snapshot_id="run-1",
        language="en",
    )

    assert display.csv_headers == BUDGET_CSV_HEADERS
    assert display.suggestion == "uncertainty_budget.csv"
    rows_by_key = {row["source_key"]: row for row in display.csv_rows}
    assert rows_by_key["contribution.1.A"]["value"] == "0.01"
    assert rows_by_key["contribution_percent.A"]["percent"] == "75%"
    assert rows_by_key["contribution_cumulative_percent.A"]["cumulative_percent"] == "75%"
    assert "Uncertainty budget" in display.text
    assert "No cross-family total is computed" in display.text
    assert not _contains_float(display.csv_rows)


def test_budget_dashboard_pareto_spec_requires_percent_rows() -> None:
    from app_desktop.budget_panel import build_budget_dashboard_display, build_budget_pareto_plot_spec

    display = build_budget_dashboard_display(_uncertainty_snapshot(), source_snapshot_id="run-1")

    spec = build_budget_pareto_plot_spec(display.budget_rows)

    assert spec == {
        "kind": "uncertainty_budget_pareto",
        "labels": ["contribution_percent.A"],
        "percent": ["75%"],
        "cumulative_percent": ["75%"],
    }

    no_percent = build_budget_dashboard_display(
        {
            "schema": "datalab.result_snapshot.statistics",
            "schema_version": 1,
            "family": "statistics",
            "metric_rows": [_row("mean", "statistics.metric.mean", value="1.25")],
            "diagnostic_rows": [],
            "row_flags": [],
        },
        source_snapshot_id="stats-1",
    )
    assert build_budget_pareto_plot_spec(no_percent.budget_rows) is None


def test_budget_latex_block_preserves_numeric_column_policy() -> None:
    from app_desktop.budget_panel import build_budget_dashboard_display
    from datalab_latex.latex_tables_budget import build_budget_latex_block

    display = build_budget_dashboard_display(_uncertainty_snapshot(), source_snapshot_id="run-1")

    lines = build_budget_latex_block(display.csv_rows, use_dcolumn=True, caption_text="Budget_A")
    text = "\n".join(lines)

    assert "\\caption{Budget\\_A}" in text
    assert "\\begin{tabular}{l l l d{" in text
    assert "contribution\\_percent.A" in text
    assert "75%" not in text
    assert text.count(" & 75 & ") == 2
    assert "\\multicolumn{1}{l}{}" in text


def _uncertainty_snapshot() -> dict[str, Any]:
    return {
        "schema": "datalab.result_snapshot.uncertainty",
        "schema_version": 1,
        "family": "uncertainty",
        "metric_rows": [],
        "diagnostic_rows": [
            _row("contribution.1.A", "uncertainty.diagnostic.contribution_variance", value="0.01", row_index=1),
            _row("contribution_total.A", "uncertainty.diagnostic.contribution_total_variance", value="0.03"),
            _row("contribution_percent.A", "uncertainty.diagnostic.contribution_percent", value="75%"),
            _row("contribution_cumulative_percent.A", "uncertainty.diagnostic.contribution_cumulative_percent", value="75%"),
        ],
        "row_flags": [],
    }


def _row(
    key: str,
    label_key: str,
    *,
    value: object = None,
    row_index: object = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "key": key,
        "label_key": label_key,
        "severity": "info",
        "render_group": "metric",
    }
    if value is not None:
        row["value"] = value
    if row_index is not None:
        row["row_index"] = row_index
    return row


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_float(item) for item in value)
    return False
