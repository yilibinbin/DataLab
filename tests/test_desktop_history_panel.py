from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from mpmath import mp

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from datalab_core.history import HistoryEntry, HistoryStore
from app_desktop.workbench_visual_contract import RESULT_RAIL_MIN_WIDTH


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def _workspace() -> dict[str, Any]:
    return {
        "title": "History",
        "current_mode": "statistics",
        "language": "en",
        "ui": {"main_tab": "results"},
        "data": {
            "source_kind": "manual_table",
            "canonical_table": {"headers": ["value"], "rows": [["1"], ["2"]]},
            "decoded_text": "value\n1\n2",
        },
        "constants": {"enabled": False},
        "config": {
            "common": {"precision_digits": 50, "display_digits": 8, "display_scientific": False},
            "statistics": {"mode": "mean", "value_column": "value"},
        },
        "result_snapshot": {"present": False},
    }


def _statistics_semantic(value: str) -> dict[str, Any]:
    from datalab_core.statistics import build_statistics_result_snapshot

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {
            "result": {
                "mode": "mean",
                "mean": value,
                "std": "0",
                "v_min": value,
                "v_max": value,
                "source_row_ids": ["line-1", "line-2"],
            },
            "n": 2,
            "value_col": "value",
        },
        overview_state="complete",
        precision={"compute_digits": 50, "display_digits": 10},
    )
    assert snapshot is not None
    return cast(dict[str, Any], snapshot)


def _bootstrap_semantic() -> dict[str, Any]:
    from datalab_core.statistics import build_statistics_result_snapshot

    payload = {
        "schema": "datalab.statistics.bootstrap.v1",
        "workflow_mode": "bootstrap_confidence_intervals",
        "target_statistic": "mean",
        "confidence_level": "0.95",
        "resample_count": 100,
        "seed": 12345,
        "seeded": True,
        "rng_algorithm": "python_random_v1",
        "rng_schedule": "per_replicate_seed_v1",
        "sample_mode": "sample",
        "trim_fraction": None,
        "method": "percentile",
        "diagnostics": [],
        "columns": [
            {
                "value_column": "value",
                "column_index": 1,
                "row_count": 4,
                "source_row_ids": ["line-1", "line-2", "line-3", "line-4"],
                "original_statistic": "2.5",
                "distribution": {
                    "schema": "datalab.monte_carlo_distribution_summary",
                    "schema_version": 1,
                    "requested_sample_count": 100,
                    "evaluated_sample_count": 100,
                    "accepted_sample_count": 100,
                    "rejected_sample_count": 0,
                    "finite_sample_count": 100,
                    "mean": "2.5",
                    "std": "0.1",
                    "histogram": {"bin_edges": ["2.0", "3.0"], "counts": [100]},
                    "percentiles": {"2.5": "2.1", "50": "2.5", "97.5": "2.9"},
                },
                "diagnostics": [],
            }
        ],
    }
    snapshot = build_statistics_result_snapshot(
        "statistics_bootstrap",
        payload,
        overview_state="complete",
        plot_metadata=[
            {
                "path": "attachments/plots/bootstrap-value.png",
                "column": "value",
                "plot_index": 1,
                "plot_key": "statistics.bootstrap_distribution",
            }
        ],
        precision={"compute_digits": 50, "display_digits": 10},
    )
    assert snapshot is not None
    return cast(dict[str, Any], snapshot)


def _time_series_semantic() -> dict[str, Any]:
    from datalab_core.statistics import build_statistics_result_snapshot
    from datalab_core.statistics_time_series import TIME_SERIES_RESULT_CACHE_KIND, run_statistics_time_series

    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=["line-1", "line-2", "line-3"],
        precision_digits=30,
        inputs={"series_method": "rolling_mean", "window_size": 2, "min_periods": 2},
        value_column="value",
        column_index=1,
    )
    snapshot = build_statistics_result_snapshot(
        TIME_SERIES_RESULT_CACHE_KIND,
        payload,
        overview_state="complete",
        plot_metadata=[
            {
                "path": "attachments/plots/time-series-value.png",
                "column": "value",
                "plot_index": 1,
                "plot_key": "statistics.time_series",
            }
        ],
        precision={"compute_digits": 30, "display_digits": 10},
    )
    assert snapshot is not None
    return cast(dict[str, Any], snapshot)


def _grouped_semantic() -> dict[str, Any]:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    envelope = run_statistics(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "grouped_statistics",
                "headers": ("Group", "A"),
                "rows": (("control", "1"), ("control", "3"), ("treated", "2"), ("treated", "4")),
                "group_column": "Group",
                "value_columns": ("A",),
                "stats_mode": "mean",
                "source_row_ids": ("1", "2", "3", "4"),
            },
            options=JobOptions(precision_digits=50, uncertainty_digits=1),
            request_id="history-panel-grouped-report-test",
        )
    )
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_grouped",
        envelope.payload,
        overview_state="complete",
    )
    assert snapshot is not None
    return cast(dict[str, Any], snapshot)


def _entry(entry_id: str, label: str, value: str, *, pinned: bool = False) -> HistoryEntry:
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=label,
        created_at=f"2026-06-20T00:00:{entry_id[-1].zfill(2)}Z",
        workspace=_workspace(),
        family="statistics",
        kind="statistics_single",
        result_snapshot=_statistics_semantic(value),
        pinned=pinned,
    )


def _bootstrap_entry(entry_id: str = "hb1", label: str = "Bootstrap result") -> HistoryEntry:
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=label,
        created_at="2026-06-20T00:00:31Z",
        workspace=_workspace(),
        family="statistics",
        kind="statistics_bootstrap",
        result_snapshot=_bootstrap_semantic(),
    )


def _time_series_entry(entry_id: str = "hts1", label: str = "Time-series result") -> HistoryEntry:
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=label,
        created_at="2026-06-20T00:00:41Z",
        workspace=_workspace(),
        family="statistics",
        kind="statistics_time_series",
        result_snapshot=_time_series_semantic(),
    )


def _grouped_entry(entry_id: str = "hgroup1", label: str = "Grouped statistics") -> HistoryEntry:
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=label,
        created_at="2026-06-20T00:00:51Z",
        workspace=_workspace(),
        family="statistics",
        kind="statistics_grouped",
        result_snapshot=_grouped_semantic(),
    )


def test_history_panel_constructs_and_displays_current_and_recent(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    recent = _entry("h2", "Older result", "2.50", pinned=True)
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window.refresh_workbench_result_rail()

    panel = window.workbench_history_panel
    assert panel.title_label.text() in {"历史", "History"}
    assert panel.entry_list.count() == 2
    assert "Current result" in panel.entry_list.item(0).text()
    assert "Older result" in panel.entry_list.item(1).text()
    assert panel.export_button.isEnabled() is True
    assert "not connected" not in panel.export_button.toolTip()
    assert panel.message_label.text() in {
        "选择一条历史记录后可导出报告包。",
        "Select a history entry to export a report bundle.",
    }

    window._apply_language("en")
    assert panel.title_label.text() == "History"
    assert "Current" in panel.entry_list.item(0).text()
    assert "pinned" in panel.entry_list.item(1).text()


def test_history_panel_minimum_width_fits_result_rail(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    recent = _entry("h2", "Older result", "2.50", pinned=True)
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window.refresh_workbench_result_rail()

    panel = window.workbench_history_panel

    assert panel.minimumSizeHint().width() <= RESULT_RAIL_MIN_WIDTH


def test_history_panel_compare_selected_recent_against_current(qtbot: Any) -> None:
    from app_desktop.workspace_controller import capture_workspace

    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._last_result_kind = current.kind
    window._last_result_semantic_snapshot = current.semantic_snapshot["result"]
    window._last_result_semantic_snapshot_kind = current.kind
    window._workspace_dirty = False
    window._update_workspace_window_title()
    original_title = window.windowTitle()
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)
    assert panel.compare_button.isEnabled() is True
    assert panel.compare_selected() is True

    assert window._workspace_dirty is False
    assert window.windowTitle() == original_title
    assert window._workbench_result_state == "complete"
    assert window._csv_headers[:6] == ["section", "source", "key", "label_key", "row_index", "method"]
    delta_row = next(row for row in window._csv_rows if row["key"] == "delta.statistics.metric.mean.value")
    assert delta_row["section"] == "comparison"
    assert delta_row["value"] == "1.5"
    assert "Older result=1.25; Current result=2.75" == delta_row["source"]
    assert "History comparison" in window.result_edit.toPlainText()
    assert "shown in results" in panel.message_label.text()
    assert window._last_result_kind == "history_comparison"
    assert window._last_result_semantic_snapshot is None
    assert window._last_result_semantic_snapshot_kind is None

    bundle = capture_workspace(window, title="compare", include_history=False)
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    assert snapshot["kind"] == "history_comparison"
    assert "semantic" not in snapshot
    assert "History comparison" in snapshot["markdown"]


def test_history_panel_budget_selected_shows_dashboard_without_dirtying_workspace(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window._update_workspace_window_title()
    original_title = window.windowTitle()
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)
    assert panel.budget_button.isEnabled() is True
    assert panel.show_budget_selected() is True

    assert window._workspace_dirty is False
    assert window.windowTitle() == original_title
    assert window._workbench_result_state == "complete"
    assert window._csv_headers[:4] == ["family", "result_id", "source_snapshot_id", "source_row_id"]
    assert any(row["label_key"] == "statistics.metric.mean" for row in window._csv_rows)
    assert "Uncertainty budget" in window.result_edit.toPlainText()
    assert "shown in results" in panel.message_label.text()
    assert window._last_result_kind == "uncertainty_budget"


def test_history_panel_compare_does_not_stale_saved_snapshot(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window._workspace_snapshot_only = True
    window._workspace_snapshot_stale = False
    window._update_workspace_window_title()
    original_title = window.windowTitle()
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)

    assert panel.compare_selected() is True
    assert window._workspace_dirty is False
    assert window._workspace_snapshot_only is True
    assert window._workspace_snapshot_stale is False
    assert window.windowTitle() == original_title
    assert "saved result snapshot" not in window.result_edit.toPlainText()
    assert "History comparison" in window.result_edit.toPlainText()


def test_history_panel_compare_rolls_back_result_state_on_display_error(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._last_result_kind = current.kind
    window._last_result_payloads = {"statistics_single": {"mean": "2.75"}}
    window._last_result_semantic_snapshot = current.semantic_snapshot["result"]
    window._last_result_semantic_snapshot_kind = current.kind
    window._last_result_text = "previous markdown"
    window._last_result_text_format = "markdown"
    window._last_result_rendered_text = "previous rendered"
    window._csv_rows = [{"metric": "mean", "value": "2.75"}]
    window._csv_headers = ["metric", "value"]
    window._csv_suggest_name = "statistics_results.csv"
    window._workbench_result_state = "complete"
    window._workspace_dirty = False
    window._update_workspace_window_title()
    original_title = window.windowTitle()
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    def fail_display(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("display failed")

    monkeypatch.setattr(window, "_set_result_text", fail_display)
    panel.entry_list.setCurrentRow(1)

    with pytest.raises(RuntimeError, match="display failed"):
        panel.compare_selected()

    assert window._workspace_dirty is False
    assert window.windowTitle() == original_title
    assert window._last_result_kind == current.kind
    assert window._last_result_payloads == {"statistics_single": {"mean": "2.75"}}
    assert window._last_result_semantic_snapshot == current.semantic_snapshot["result"]
    assert window._last_result_semantic_snapshot_kind == current.kind
    assert window._last_result_text == "previous markdown"
    assert window._last_result_text_format == "markdown"
    assert window._last_result_rendered_text == "previous rendered"
    assert window._csv_rows == [{"metric": "mean", "value": "2.75"}]
    assert window._csv_headers == ["metric", "value"]
    assert window._csv_suggest_name == "statistics_results.csv"
    assert window._workbench_result_state == "complete"


def test_history_panel_compare_rolls_back_visible_result_on_csv_error(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._last_result_kind = current.kind
    window._last_result_payloads = {"statistics_single": {"mean": "2.75"}}
    window._last_result_semantic_snapshot = current.semantic_snapshot["result"]
    window._last_result_semantic_snapshot_kind = current.kind
    window._last_result_text = "previous markdown"
    window._last_result_text_format = "markdown"
    window._last_result_rendered_text = "Previous rendered result"
    window._csv_rows = [{"metric": "mean", "value": "2.75"}]
    window._csv_headers = ["metric", "value"]
    window._csv_suggest_name = "statistics_results.csv"
    window._workbench_result_state = "complete"
    window._workspace_dirty = False
    window.result_edit.setPlainText("Previous rendered result")
    window.export_csv_btn.setEnabled(True)
    window._update_workspace_window_title()
    original_title = window.windowTitle()
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    def fail_csv(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("csv failed")

    monkeypatch.setattr(window, "_set_csv_data", fail_csv)
    panel.entry_list.setCurrentRow(1)

    with pytest.raises(RuntimeError, match="csv failed"):
        panel.compare_selected()

    assert window._workspace_dirty is False
    assert window.windowTitle() == original_title
    assert window._last_result_kind == current.kind
    assert window._last_result_payloads == {"statistics_single": {"mean": "2.75"}}
    assert window._last_result_semantic_snapshot == current.semantic_snapshot["result"]
    assert window._last_result_semantic_snapshot_kind == current.kind
    assert window._last_result_text == "previous markdown"
    assert window._last_result_rendered_text == "Previous rendered result"
    assert window._csv_rows == [{"metric": "mean", "value": "2.75"}]
    assert window._csv_headers == ["metric", "value"]
    assert window._csv_suggest_name == "statistics_results.csv"
    assert window._workbench_result_state == "complete"
    assert window.result_edit.toPlainText() == "Previous rendered result"
    assert window.export_csv_btn.isEnabled() is True


def test_history_panel_compare_rejects_current_selection_without_dirtying(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(0)

    assert panel.compare_button.isEnabled() is False
    assert "recent history entry" in panel.compare_button.toolTip()
    assert panel.compare_selected() is False
    assert window._workspace_dirty is False
    assert "recent history entry" in panel.message_label.text()


def test_history_panel_compare_rejects_missing_current(qtbot: Any) -> None:
    window = _window(qtbot)
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    window._workspace_history_store = HistoryStore(entries=(recent,))
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(0)

    assert panel.compare_button.isEnabled() is False
    assert "No current history result" in panel.compare_button.toolTip()
    assert panel.compare_selected() is False
    assert window._workspace_dirty is False
    assert "No current history result" in panel.message_label.text()


def test_history_panel_compare_rejects_unsupported_schema(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "2.75")
    recent = _entry("h2", "Older result", "1.25")
    window._apply_language("en")
    unsupported_semantic = dict(recent.semantic_snapshot)
    unsupported_result = dict(unsupported_semantic["result"])
    unsupported_result["schema"] = "datalab.result_snapshot.future_statistics"
    unsupported_semantic["result"] = unsupported_result
    recent = HistoryEntry(
        entry_id=recent.entry_id,
        label=recent.label,
        created_at=recent.created_at,
        pinned=recent.pinned,
        semantic_snapshot=unsupported_semantic,
    )
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)

    assert panel.compare_button.isEnabled() is False
    assert "unsupported semantic snapshot schema" in panel.compare_button.toolTip()
    assert panel.compare_selected() is False
    assert window._workspace_dirty is False
    assert "unsupported semantic snapshot schema" in panel.message_label.text()


def test_history_panel_rename_pin_delete_mark_workspace_dirty(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    recent = _entry("h2", "Older result", "2.50")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)
    assert panel.rename_selected("Renamed result") is True
    assert window._workspace_dirty is True
    assert window._workspace_history_store.entries[0].label == "Renamed result"

    window._workspace_dirty = False
    assert panel.toggle_pin_selected() is True
    assert window._workspace_dirty is True
    assert window._workspace_history_store.entries[0].pinned is True

    window._workspace_dirty = False
    assert panel.delete_selected() is True
    assert window._workspace_dirty is True
    assert window._workspace_history_store.entries == ()
    assert panel.entry_list.count() == 1


def test_history_panel_restores_selected_entry_via_semantic_snapshot(qtbot: Any) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    recent = _entry("h2", "Older result", "2.50")
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._last_result_semantic_snapshot = current.semantic_snapshot["result"]
    window._last_result_semantic_snapshot_kind = current.kind
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)
    assert panel.restore_selected() is True

    assert window._workspace_dirty is True
    assert window._workspace_history_store.current.entry_id == "h2"
    assert window._last_result_semantic_snapshot == recent.semantic_snapshot["result"]
    assert window._last_result_semantic_snapshot_kind == "statistics_single"
    assert any("2.5" in str(row) for row in window._csv_rows)
    assert "2.5" in window.result_edit.toPlainText()
    assert window._workspace_snapshot_only is True


def test_history_panel_restore_unsupported_snapshot_reports_error_without_raising(
    qtbot: Any,
) -> None:
    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    recent = _entry("h2", "Older result", "2.50")
    window._apply_language("en")
    # An entry whose family is outside the supported renderer set (e.g. a legacy,
    # foreign, or future-version .datalab file). Load-time validation only requires
    # non-empty strings, so such an entry loads and is selectable, but
    # restore_history_entry_result raises HistoryValidationError because
    # _semantic_snapshot_matches_kind rejects the unknown family.
    unsupported_semantic = dict(recent.semantic_snapshot)
    unsupported_semantic["family"] = "extrapolation"
    unsupported_semantic["kind"] = "extrapolation_richardson"
    recent = HistoryEntry(
        entry_id=recent.entry_id,
        label=recent.label,
        created_at=recent.created_at,
        pinned=recent.pinned,
        semantic_snapshot=unsupported_semantic,
    )
    window._workspace_history_store = HistoryStore(current=current, entries=(recent,))
    window._workspace_dirty = False
    window.refresh_workbench_result_rail()
    panel = window.workbench_history_panel

    panel.entry_list.setCurrentRow(1)

    # Must not raise into the Qt event loop; it surfaces a message and returns False.
    assert panel.restore_selected() is False
    assert window._workspace_dirty is False
    assert window._workspace_history_store.current.entry_id == "h1"
    assert "restore" in panel.message_label.text().lower()


def test_history_panel_refreshes_after_workspace_restore(qtbot: Any) -> None:
    from app_desktop.workspace_controller import restore_workspace

    window = _window(qtbot)
    current = _entry("h1", "Restored current", "1.25")
    workspace = _workspace()
    workspace["history"] = HistoryStore(current=current).to_json()

    restore_workspace(window, {"workspace": workspace}, {})

    panel = window.workbench_history_panel
    assert window._workspace_history_enabled is True
    assert panel.entry_list.count() == 1
    assert "Restored current" in panel.entry_list.item(0).text()


def test_history_panel_exports_selected_entry_to_report_bundle(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    target = tmp_path / "history-report.datalab-report.zip"
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()
    window._apply_language("en")

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    assert panel.export_button.isEnabled() is True
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    assert loaded.manifest["schema"] == "datalab.report_bundle.v1"
    assert loaded.manifest["metadata"]["language"] == "en"
    assert loaded.manifest["selected_snapshots"] == [
        {"id": "h1", "family": "statistics", "kind": "statistics_single"}
    ]
    assert loaded.snapshots["h1"]["result"]["family"] == "statistics"
    assert loaded.tables["table-h1"].startswith("batch,metric,value,uncertainty")
    assert loaded.latex_report.startswith("\\documentclass")
    assert "Report bundle exported" in panel.message_label.text()


def test_history_panel_report_bundle_includes_cached_statistics_plots(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    window = _window(qtbot)
    current = _entry("h1", "Current result", "1.25")
    current = HistoryEntry(
        entry_id=current.entry_id,
        label=current.label,
        created_at=current.created_at,
        semantic_snapshot=current.semantic_snapshot,
        rendered_cache={
            "plots": [
                {"path": "attachments/plots/plot-001.png", "column": "B", "plot_index": 1},
                {"path": "attachments/plots/plot-002.png", "column": "A", "plot_index": 1},
            ]
        },
    )
    target = tmp_path / "history-report-with-plots.datalab-report.zip"
    first_plot = b"\x89PNG\r\n\x1a\nfirst"
    second_plot = b"\x89PNG\r\n\x1a\nsecond"
    window._workspace_attachments = {
        "attachments/plots/plot-001.png": first_plot,
        "attachments/plots/plot-002.png": second_plot,
    }
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    assert loaded.manifest["export_options"]["include_plots"] is True
    assert set(loaded.plots.values()) == {first_plot, second_plot}


def test_history_panel_report_bundle_round_trips_bootstrap_table_and_plot(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    window = _window(qtbot)
    current = _bootstrap_entry()
    plot_bytes = b"\x89PNG\r\n\x1a\nbootstrap"
    current = HistoryEntry(
        entry_id=current.entry_id,
        label=current.label,
        created_at=current.created_at,
        semantic_snapshot=current.semantic_snapshot,
        rendered_cache={
            "plots": [
                {
                    "path": "attachments/plots/bootstrap-value.png",
                    "column": "value",
                    "plot_index": 1,
                    "plot_key": "statistics.bootstrap_distribution",
                }
            ]
        },
    )
    target = tmp_path / "bootstrap-history-report.datalab-report.zip"
    window._workspace_attachments = {"attachments/plots/bootstrap-value.png": plot_bytes}
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    assert loaded.manifest["selected_snapshots"] == [
        {"id": "hb1", "family": "statistics", "kind": "statistics_bootstrap"}
    ]
    assert loaded.snapshots["hb1"]["result"]["mode"] == "bootstrap_confidence_intervals"
    assert "bootstrap_ci_lower" in loaded.tables["table-hb1"]
    assert "bootstrap_seed" in loaded.tables["table-hb1"]
    assert loaded.manifest["export_options"]["include_plots"] is True
    assert loaded.plots == {"plot-hb1-value-1": plot_bytes}


def test_history_panel_report_bundle_round_trips_time_series_table_and_plot(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    window = _window(qtbot)
    current = _time_series_entry()
    plot_bytes = b"\x89PNG\r\n\x1a\ntime-series"
    current = HistoryEntry(
        entry_id=current.entry_id,
        label=current.label,
        created_at=current.created_at,
        semantic_snapshot=current.semantic_snapshot,
        rendered_cache={
            "plots": [
                {
                    "path": "attachments/plots/time-series-value.png",
                    "column": "value",
                    "plot_index": 1,
                    "plot_key": "statistics.time_series",
                }
            ]
        },
    )
    target = tmp_path / "time-series-history-report.datalab-report.zip"
    window._workspace_attachments = {"attachments/plots/time-series-value.png": plot_bytes}
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    assert loaded.manifest["selected_snapshots"] == [
        {"id": "hts1", "family": "statistics", "kind": "statistics_time_series"}
    ]
    assert loaded.snapshots["hts1"]["result"]["mode"] == "time_series_rolling"
    assert "window_source_rows" in loaded.tables["table-hts1"]
    assert "1.5" in loaded.tables["table-hts1"]
    assert loaded.manifest["export_options"]["include_plots"] is True
    assert loaded.plots == {"plot-hts1-value-1": plot_bytes}


def test_history_panel_report_bundle_round_trips_grouped_table(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    window = _window(qtbot)
    current = _grouped_entry()
    target = tmp_path / "grouped-history-report.datalab-report.zip"
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    assert loaded.manifest["selected_snapshots"] == [
        {"id": "hgroup1", "family": "statistics", "kind": "statistics_grouped"}
    ]
    assert loaded.snapshots["hgroup1"]["result"]["mode"] == "grouped_statistics"
    assert "group,column,batch,metric,value,uncertainty" in loaded.tables["table-hgroup1"]
    assert "control,A,1,mean" in loaded.tables["table-hgroup1"]
    assert "treated,A,2,mean" in loaded.tables["table-hgroup1"]


def test_history_panel_report_bundle_export_bounds_prefixed_attachment_ids(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.history_panel as history_panel
    from datalab_core.report_bundle import read_report_bundle

    long_id = "h" + ("x" * 160) + "9"
    window = _window(qtbot)
    current = _entry(long_id, "Very long result label", "1.25")
    target = tmp_path / "long-history-report.datalab-report.zip"
    window._workspace_history_store = HistoryStore(current=current)
    window.refresh_workbench_result_rail()

    panel = window.workbench_history_panel
    panel.entry_list.setCurrentRow(0)
    monkeypatch.setattr(history_panel.QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    assert panel.export_selected() is True

    loaded = read_report_bundle(target)
    attachment_groups = loaded.manifest["attachments"]
    latex_group = attachment_groups["latex"]
    ids = [entry["id"] for entry in attachment_groups["semantic_snapshots"]]
    ids.extend(entry["id"] for entry in attachment_groups["tables"])
    ids.append(latex_group["report"]["id"])
    ids.extend(entry["id"] for entry in latex_group["sections"])
    assert all(len(attachment_id) <= 128 for attachment_id in ids)
    assert list(loaded.tables) and all(name.startswith("table-") for name in loaded.tables)
    assert list(loaded.latex_sections) and all(name.startswith("section-") for name in loaded.latex_sections)
