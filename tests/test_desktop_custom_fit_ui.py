from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _select_model(win, model_type: str) -> None:
    mode_index = win.mode_combo.findData("fitting")
    assert mode_index >= 0
    win.mode_combo.setCurrentIndex(mode_index)
    index = win.fit_model_combo.findData(model_type)
    assert index >= 0
    win.fit_model_combo.setCurrentIndex(index)


def _table_names(parameter_table) -> list[str]:
    return [row["name"] for row in parameter_table.rows()]


def test_custom_fit_detects_parameters_and_constants(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("A*x + B + K")
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    window.custom_param_refresh_btn.click()

    assert _table_names(window.custom_params_table) == ["A", "B"]


def test_disabled_custom_constants_are_detected_as_parameters(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("A*x + K")
    window.custom_constants_editor.setChecked(False)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    window.custom_param_refresh_btn.click()

    assert _table_names(window.custom_params_table) == ["A", "K"]
