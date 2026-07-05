from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    win = ExtrapolationWindow()
    # Pin the language so assertions are deterministic regardless of the runner's
    # system locale (CI defaults to English, local dev often to Chinese). Tests
    # that need English call _apply_language("en") themselves.
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def _select_combo_data(combo: Any, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0, value
    combo.setCurrentIndex(index)
    QApplication.processEvents()


def _select_mode(window: Any, mode: str) -> None:
    _select_combo_data(window.mode_combo, mode)


def _enter_manual_text(window: Any, text: str) -> None:
    window._data_stack.setCurrentIndex(1)
    window.manual_data_edit.setPlainText(text)
    QApplication.processEvents()


def _click_run_and_wait(qtbot: Any, window: Any, *, timeout: int = 10000) -> None:
    qtbot.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._has_running_worker(), timeout=timeout)
    QApplication.processEvents()


def _result_text(window: Any) -> str:
    return window.result_edit.toPlainText()


def test_mode_switch_refreshes_manual_data_summary_columns(window: Any) -> None:
    window._apply_language("en")

    _select_mode(window, "root_solving")
    assert window.manual_table.columnCount() == 1
    assert window.manual_data_summary.text() == "0 rows · 1 column"
    window.manual_table.setItem(0, 0, QTableWidgetItem("4"))
    window.refresh_workbench_data_summary()
    assert window.manual_data_summary.text() == "1 row · 1 column"
    window.manual_table.item(0, 0).setText("")
    window.refresh_workbench_data_summary()

    _select_mode(window, "statistics")

    assert window.manual_table.columnCount() == 3
    assert window.manual_data_summary.text() == "0 rows · 3 columns"


def test_extrapolation_click_workflow_en(window: Any, qtbot: Any) -> None:
    from mpmath import mp

    window._apply_language("en")
    _select_mode(window, "extrapolation")
    terms = [mp.mpf("1") + mp.mpf("0.5") / mp.power(n, 2) for n in range(1, 9)]
    headers = " ".join(f"S{idx}" for idx in range(1, len(terms) + 1))
    row = " ".join(mp.nstr(value, 30) for value in terms)
    _enter_manual_text(window, f"{headers}\n{row}\n")
    _select_combo_data(window.method_combo, "richardson")
    window.generate_plots_checkbox.setChecked(False)

    _click_run_and_wait(qtbot, window)

    text = _result_text(window)
    log = window.log_edit.toPlainText()
    assert "Extrapolation Results" in text
    assert "Successful rows" in text
    assert window._csv_rows
    assert "Manual input data used." in log
    assert "计算完成" not in log


def test_error_propagation_click_workflow_zh(window: Any, qtbot: Any, tmp_path: Path) -> None:
    window._apply_language("zh")
    _select_mode(window, "error")
    _enter_manual_text(window, "x y\n2.0(1) 3.0(2)\n")
    window.formula_edit.setPlainText("x*y")
    _select_combo_data(window.error_method_combo, "taylor")
    window.generate_plots_checkbox.setChecked(False)
    window.generate_latex_checkbox.setChecked(True)

    _click_run_and_wait(qtbot, window)

    text = _result_text(window)
    assert "误差传递结果" in text
    assert "公式" in text
    assert "不确定度" in text
    assert window._csv_rows
    assert any(str(row.get("latex", "")).strip() for row in window._csv_rows)
    latex_source = window.latex_edit.toPlainText()
    assert "\\begin{document}" in latex_source
    assert "x \\cdot y" in latex_source


def test_fitting_click_workflow_custom_model(window: Any, qtbot: Any) -> None:
    _select_mode(window, "fitting")
    _enter_manual_text(window, "x y\n0 1\n1 3\n2 5\n3 7\n")
    _select_combo_data(window.fit_model_combo, "custom")
    variable_edit, column_edit, *_ = window.variable_rows[0]
    variable_edit.setText("x")
    column_edit.setText("x")
    window.fit_expr_edit.setPlainText("A*x + B")
    window.fit_target_edit.setText("y")
    window.custom_params_table.set_rows(
        [
            {"name": "A", "initial": "1", "min": "", "max": "", "fixed": "", "expr": ""},
            {"name": "B", "initial": "0", "min": "", "max": "", "fixed": "", "expr": ""},
        ]
    )
    window.generate_plots_checkbox.setChecked(False)

    _click_run_and_wait(qtbot, window, timeout=15000)

    text = _result_text(window)
    assert "A" in text
    assert "B" in text
    assert "Fit" in text or "拟合" in text
    assert window._csv_rows


def test_fitting_click_workflow_selected_comparison(window: Any, qtbot: Any, tmp_path: Path) -> None:
    from fitting.comparison_formatting import COMPARISON_TABLE_HEADERS

    _select_mode(window, "fitting")
    _enter_manual_text(window, "x y\n0 1\n1 3\n2 5\n3 7\n")
    _select_combo_data(window.fit_model_combo, "comparison")
    variable_edit, column_edit, *_ = window.variable_rows[0]
    variable_edit.setText("x")
    column_edit.setText("x")
    window.fit_target_edit.setText("y")
    window.fit_comparison_candidates_edit.setPlainText(
        "[\n"
        '  {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},\n'
        '  {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2}\n'
        "]"
    )
    window.generate_plots_checkbox.setChecked(False)
    window.generate_latex_checkbox.setChecked(True)

    _click_run_and_wait(qtbot, window, timeout=15000)

    text = _result_text(window)
    assert "Selected Fit Comparison" in text
    assert "Linear" in text
    assert "Quadratic" in text
    assert window._csv_headers == list(COMPARISON_TABLE_HEADERS)
    assert [row["candidate_id"] for row in window._csv_rows] == ["linear", "quadratic"]
    assert window._csv_suggest_name == "fitting_comparison_results.csv"
    # The tex is written to a per-run temp path and loaded into the editor — read the
    # generated source from the editor (no user output-path field anymore).
    latex_source = window.latex_edit.toPlainText()
    assert "\\begin{table}" in latex_source
    assert "$\\chi^2$" in latex_source
    assert "Linear" in latex_source
    assert "Quadratic" in latex_source
    assert window.latex_edit.toPlainText() == latex_source


def test_root_solving_click_workflow_and_workspace_round_trip(window: Any, qtbot: Any, tmp_path: Path) -> None:
    _select_mode(window, "root_solving")
    _enter_manual_text(window, "A\n4.0\n")
    window.root_equations_edit.setPlainText("x**2 - A")
    _select_combo_data(window.root_mode_combo, "scalar")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.generate_plots_checkbox.setChecked(True)
    window.generate_latex_checkbox.setChecked(True)
    output_path = tmp_path / "root.tex"
    window.output_file_edit.setText(str(output_path))

    _click_run_and_wait(qtbot, window, timeout=15000)

    text = _result_text(window)
    assert "x" in text
    assert "2" in text
    assert window._csv_rows
    assert window.latex_edit.toPlainText().strip()
    assert isinstance(window.result_plot_bytes, bytes)
    assert window.result_plot_bytes.startswith(b"\x89PNG")
    assert window.tabs.currentIndex() == window.result_tab_index
    image_tab = window.result_tabs_indices["image"]
    window.result_tabs.setCurrentIndex(image_tab)

    workspace_path = tmp_path / "root-workflow.datalab"
    assert window._save_workspace_to_path(workspace_path)

    from app_desktop.window import ExtrapolationWindow

    reopened = ExtrapolationWindow()
    qtbot.addWidget(reopened)
    assert reopened._open_workspace_from_path(workspace_path)

    assert reopened.mode_combo.currentData() == "root_solving"
    assert reopened.manual_data_edit.toPlainText() == "A\n4.0\n"
    assert reopened._data_stack.currentIndex() == 1
    assert reopened.root_equations_edit.toPlainText() == "x**2 - A"
    assert reopened.root_unknowns_table.rows()[0]["name"] == "x"
    assert reopened.result_edit.toPlainText() == text
    assert reopened._csv_rows == window._csv_rows
    assert reopened.latex_edit.toPlainText() == window.latex_edit.toPlainText()
    assert reopened.result_plot_bytes == window.result_plot_bytes
    assert reopened.tabs.currentIndex() == window.result_tab_index
    assert reopened.result_tabs.currentIndex() == image_tab


def test_statistics_click_workflow(window: Any, qtbot: Any) -> None:
    _select_mode(window, "statistics")
    _enter_manual_text(window, "A\n1\n2\n3\n")
    window.stats_value_column_edit.setText("A")
    _select_combo_data(window.stats_mode_combo, "mean")
    window.stats_sample_checkbox.setChecked(True)
    window.generate_plots_checkbox.setChecked(False)

    _click_run_and_wait(qtbot, window)

    text = _result_text(window)
    assert "Statistics Results" in text or "统计结果" in text or "统计平均结果" in text
    assert "Mean" in text or "平均值" in text
    assert "Std. dev." in text or "标准差" in text
    assert window._csv_rows
