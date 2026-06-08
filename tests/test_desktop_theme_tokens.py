from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QTableWidget


def test_supported_left_panel_width_is_not_smaller_than_known_minimum() -> None:
    from app_desktop.theme import MIN_LEFT_PANEL_WIDTH, SUPPORTED_MIN_WINDOW_WIDTH

    assert MIN_LEFT_PANEL_WIDTH >= 420
    assert SUPPORTED_MIN_WINDOW_WIDTH >= 1280


def test_schema_scan_uses_theme_supported_width_constant() -> None:
    from app_desktop.theme import SUPPORTED_MIN_WINDOW_WIDTH
    from tools.scan_desktop_gui_schema import SCAN_WIDTHS

    assert SCAN_WIDTHS[0] == SUPPORTED_MIN_WINDOW_WIDTH


def test_apply_desktop_theme_does_not_reset_user_state(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.show()
    app.processEvents()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window.formula_edit.setPlainText("A + B")
    window.result_edit.setPlainText("existing result")
    original_mode = window.mode_combo.currentData()

    window._apply_desktop_theme()
    app.sendEvent(window, QEvent(QEvent.Type.PaletteChange))
    app.processEvents()

    assert window.mode_combo.currentData() == original_mode
    assert window.formula_edit.toPlainText() == "A + B"
    assert window.result_edit.toPlainText() == "existing result"
    assert all(table.styleSheet() for table in window.findChildren(QTableWidget))
    for widget_name in (
        "workbench_root",
        "workbench_bar",
        "workbench_config_rail",
        "workbench_workspace_canvas",
        "workbench_result_rail",
        "workbench_status_strip",
    ):
        assert getattr(window, widget_name).styleSheet()
