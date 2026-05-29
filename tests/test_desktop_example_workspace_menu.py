from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_example_workspace_menu_action_exists(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    actions = [action.text() for action in win.menuBar().actions()]
    menu_text = " ".join(actions).lower()
    assert "example" in menu_text or "示例" in menu_text
