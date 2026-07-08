"""Input data + constants merged into sheet-like tabs (输入数据 / 常数).

The 常数 tab appears only in constant-using modes (error / custom-fit / implicit); other modes
show just 输入数据. Both underlying widgets stay alive (removeTab, not delete) so their state and
serialization are untouched.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.window import ExtrapolationWindow


def _window(qtbot: Any) -> ExtrapolationWindow:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def _tab_titles(window: ExtrapolationWindow) -> list[str]:
    tabs = window.input_data_tabs
    return [tabs.tabText(i) for i in range(tabs.count())]


def test_input_and_constants_are_sheet_tabs(qtbot: Any) -> None:
    window = _window(qtbot)
    tabs = window.input_data_tabs
    assert tabs is not None
    # Both hosted widgets live inside the tab widget (input data always; constants when shown).
    assert tabs.indexOf(window.manual_box) != -1


def test_constants_tab_only_in_constant_using_modes(qtbot: Any) -> None:
    window = _window(qtbot)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据"]  # no constants tab

    # Switching back re-adds the constants tab; the editor widget is reused, not rebuilt.
    editor_before = window.input_constants_editor
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]
    assert window.input_constants_editor is editor_before


def test_input_tabs_retranslate(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window._apply_language("zh")
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]
    window._apply_language("en")
    QApplication.processEvents()
    assert _tab_titles(window) == ["Data input", "Constants"]
