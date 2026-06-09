from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget

from app_desktop.workbench_results import MAX_RESULT_OVERVIEW_ROWS, MAX_RESULT_OVERVIEW_TABLE_HEIGHT


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_result_rail_has_overview_and_data_table(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.workbench_result_overview is not None
    assert isinstance(window.workbench_result_table, QTableWidget)
    assert window.tabs.parentWidget() is window.workbench_result_rail
    assert window.result_tabs.parentWidget() is window.tabs.widget(window.result_tab_index)


def test_result_rail_mirrors_csv_rows(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window.refresh_workbench_result_rail()

    assert window.workbench_result_table.rowCount() == 1
    assert window.workbench_result_table.columnCount() == 2
    assert window.workbench_result_table.item(0, 0).text() == "2.47e-3"
    assert "1" in window.workbench_result_overview.text()


def test_result_rail_clears_stale_columns_when_newer_result_is_narrower(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window._set_csv_data([{"k": "3.14"}], ["k"], "result.csv")

    assert window.workbench_result_table.rowCount() == 1
    assert window.workbench_result_table.columnCount() == 1
    assert window.workbench_result_table.horizontalHeaderItem(0).text() == "k"
    assert window.workbench_result_table.item(0, 0).text() == "3.14"


def test_result_rail_caps_visible_rows_but_reports_total(qtbot: Any) -> None:
    window = _window(qtbot)
    rows = [{"i": str(index)} for index in range(MAX_RESULT_OVERVIEW_ROWS + 3)]

    window._set_csv_data(rows, ["i"], "result.csv")
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == MAX_RESULT_OVERVIEW_ROWS
    assert window.workbench_result_table.maximumHeight() == MAX_RESULT_OVERVIEW_TABLE_HEIGHT
    assert f"Result data: {len(rows)} rows, 1 column" in window.workbench_result_overview.text()
    assert f"showing first {MAX_RESULT_OVERVIEW_ROWS}" in window.workbench_result_overview.text()


def test_result_rail_clears_when_csv_data_resets(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")
    window._reset_csv_data()

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() in {"暂无结果", "No results"}


def test_result_rail_summary_relocalizes_on_language_switch(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")

    window._apply_language("en")
    assert "Result data: 1 row, 1 column" in window.workbench_result_overview.text()
    window._apply_language("zh")
    assert "结果数据：1 行" in window.workbench_result_overview.text()


def _tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfeA\xe2\xa1\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_result_rail_distinguishes_plot_only_result(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = ""
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_distinguishes_text_only_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "x = 1.0"

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_result_rail_distinguishes_plot_and_text_without_tabular_data(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "diagnostic text"
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"


def test_result_rail_distinguishes_failed_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._mark_workbench_result_failed()

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_failed_result_survives_ordinary_csv_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_hard_reset_clears_failed_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_result_rail_shows_running_while_worker_is_in_flight(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data(clear_non_tabular_result=True)
    window._mark_workbench_result_running()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Running"


def test_result_rail_plot_only_success_does_not_stay_running(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._mark_workbench_result_running()
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_plot_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._update_result_plot(_tiny_png_bytes(), final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_text_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("text-only result", final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_result_rail_tabular_result_mentions_available_plot(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": "1", "y": "2"}], ["x", "y"])
    window.result_plot_bytes = b"plot-bytes"
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result data: 1 row, 2 columns; plot also available"


def test_result_rail_empty_tabular_schema_is_still_tabular(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([], ["x", "y"])
    window._apply_language("en")

    assert window.workbench_result_table.columnCount() == 2
    assert window.workbench_result_overview.text() == "Result data: 0 rows, 2 columns"


def test_result_overview_copies_only_preview_rows(qtbot: Any) -> None:
    from app_desktop.workbench_results import _overview_state

    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])

    state = _overview_state(window)

    assert state.total_rows == 500
    assert len(state.preview_rows) == 100


def test_result_overview_summary_reports_displayed_row_count(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])
    window._apply_language("en")

    assert "Result data: 500 rows, 1 column" in window.workbench_result_overview.text()
    assert "showing first 50 rows" in window.workbench_result_overview.text()
    assert window.workbench_result_table.rowCount() == 50


def test_result_rail_intermediate_text_does_not_clear_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("intermediate progress")
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_result_rail_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._mark_workbench_result_complete()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_reset_csv_preserves_empty_success_unless_hard_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"

    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_root_solving_empty_success_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_root_solving_finished({"markdown": "", "csv_rows": [], "csv_headers": []})
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_image_list_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_image_list("fit", [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_fit_batches_tabular_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_substituted_expression", lambda *args, **kwargs: "A*x")
    monkeypatch.setattr(window, "_format_fit_result_text", lambda *args, **kwargs: "fit summary")
    monkeypatch.setattr(window, "_render_fit_plot_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_build_fit_csv_rows",
        lambda *args, **kwargs: [{"section": "parameters", "name": "A", "value": "1"}],
    )
    payload = SimpleNamespace(
        job=SimpleNamespace(
            model_expr="A*x",
            headers=["x", "y"],
            data_rows=[],
            sigma_rows=[],
            render_plots=False,
        ),
        expression="A*x",
        fit_result=SimpleNamespace(params={"A": "1"}),
    )

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="fit", fit_payload=payload, error=None, captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result data: 1 row, 8 columns; text also available"


def test_fit_batches_text_only_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="error", fit_payload=None, error="bad input", captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_reset_csv_rejects_conflicting_hard_reset_and_preserve_running(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": "1"}], ["x"])
    window._mark_workbench_result_running()
    window._apply_language("en")

    with pytest.raises(ValueError, match="preserve_workbench_running"):
        window._reset_csv_data(preserve_workbench_running=True, clear_non_tabular_result=True)

    assert window._csv_rows == [{"x": "1"}]
    assert window._csv_headers == ["x"]
    assert window.workbench_result_overview.text() == "Running"


def test_set_csv_empty_payload_preserves_empty_success(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()

    window._set_csv_data([], [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_csv_intermediate_rows_can_preserve_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._set_csv_data([{"x": "1"}], ["x"], final_result=False)
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_worker_start_failure_does_not_leave_running_overview(qtbot: Any) -> None:
    class BrokenWorker:
        def start(self) -> None:
            raise RuntimeError("boom")

    window = _window(qtbot)
    window._apply_language("en")

    with pytest.raises(RuntimeError):
        window._start_worker_with_workbench_result_state(BrokenWorker())

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_worker_start_refreshes_result_rail_once(qtbot: Any, monkeypatch: Any) -> None:
    class Worker:
        def start(self) -> None:
            pass

    window = _window(qtbot)
    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_result_rail", refresh)
    window._start_worker_with_workbench_result_state(Worker())

    assert calls == 1


def test_calc_success_handler_exception_marks_result_failed(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_show_extrapolation_results",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render boom")),
    )
    window._mark_workbench_result_running()

    window._on_calc_finished(
        SimpleNamespace(
            mode="extrapolation",
            logs=[],
            latex_path=None,
            warnings=[],
            payload={"headers": [], "data_rows": [], "results": []},
        )
    )
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_statistics_empty_batches_use_empty_success_overview(qtbot: Any) -> None:
    window = _window(qtbot)

    window._display_statistics_batches([], "value")
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_empty_result_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(window, "_format_statistics_display", lambda **kwargs: ("", []))

    window._display_statistics_result({}, "value", 0, render_plots=False)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_nonempty_batch_without_csv_reports_text_result(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._apply_language("en")
    captured_text: dict[str, str] = {}
    original_set_result_text = window._set_result_text

    def capture_result_text(text: str, *args: Any, **kwargs: Any) -> None:
        captured_text["text"] = text
        original_set_result_text(text, *args, **kwargs)

    monkeypatch.setattr(window, "_set_result_text", capture_result_text)
    monkeypatch.setattr(window, "_render_statistics_text", lambda *args, **kwargs: "")
    monkeypatch.setattr(window, "_build_stats_csv_rows", lambda *args, **kwargs: [])

    window._display_statistics_batches([{"index": 1, "result": {}, "rows": []}], "value", render_plots=False)
    window._apply_language("en")

    assert captured_text["text"].strip()
    assert "Batch" in captured_text["text"]
    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_run_validation_error_does_not_leave_result_overview_running(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window._apply_language("en")

    window.run_calculation()

    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_does_not_reset_results_before_worker(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    reset_called = False

    def reset_csv_data(*args: object, **kwargs: object) -> None:
        nonlocal reset_called
        reset_called = True

    monkeypatch.setattr(window, "_reset_csv_data", reset_csv_data)

    window.run_calculation()

    assert reset_called is False


def test_worker_cancellation_clears_running_result_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_worker_cancellation_after_old_plot_does_not_restore_stale_plot(qtbot: Any) -> None:
    from pathlib import Path

    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window.current_fit_figures = [Path("old-fit.png")]
    window._image_mode = "fit"
    window._workbench_result_state = "running"

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.current_fit_figures == []
    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_preserves_previous_valid_result_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._last_result_rendered_text = "old text result"
    window.refresh_workbench_result_rail()
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window.run_calculation()

    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"


def test_new_workspace_hard_clears_previous_result_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    monkeypatch.setattr(window, "_confirm_workspace_discard_or_save", lambda: True)
    window._last_result_rendered_text = "old text"
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._mark_workbench_result_failed()
    window.refresh_workbench_result_rail()
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Calculation failed"

    assert window.new_workspace()
    window._apply_language("en")

    assert window._last_result_rendered_text == ""
    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.workbench_result_overview.text() == "No results"
