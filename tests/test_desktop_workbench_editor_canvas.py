from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStackedWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_mode_editors_reuse_existing_mode_stack_in_center_canvas(qtbot: Any) -> None:
    window = _window(qtbot)

    stack = window.mode_stack
    assert isinstance(stack, QStackedWidget)
    assert stack.parentWidget() is window.workbench_workspace_content
    assert stack.count() >= 5
    for widget in (window.extrap_box, window.error_box, window.fit_box, window.root_box, window.stats_box):
        assert stack.indexOf(widget) >= 0


def test_mode_switch_updates_center_editor_without_losing_drafts(qtbot: Any) -> None:
    window = _window(qtbot)
    stack = window.mode_stack

    window.fit_expr_edit.setPlainText("A*x+B")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.root_box

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.fit_box
    assert window.fit_expr_edit.toPlainText() == "A*x+B"


def test_no_second_editor_stack_is_created(qtbot: Any) -> None:
    window = _window(qtbot)
    assert window.findChild(QStackedWidget, "workbench_editor_stack") is None
