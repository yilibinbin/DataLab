from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QToolButton


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_toolbar_uses_icon_actions_and_preserves_public_attributes(qtbot: Any) -> None:
    window = _window(qtbot)

    toolbar = window.findChild(QFrame, "workbench_toolbar")
    assert toolbar is not None
    assert toolbar.height() >= 44

    for name in (
        "new_workspace_button",
        "open_workspace_button",
        "save_workspace_button",
        "open_examples_button",
        "workbench_run_button",
        "workbench_stop_button",
        "docs_button",
        "check_updates_button",
    ):
        button = getattr(window, name, None)
        assert isinstance(button, QToolButton), name
        assert not button.icon().isNull(), name
        assert button.toolTip(), name
        assert button.accessibleDescription(), name


def test_toolbar_language_switch_keeps_actions(qtbot: Any) -> None:
    window = _window(qtbot)

    window._apply_language("en")
    assert window.new_workspace_button.text() == "New"
    assert window.workbench_run_button.text() == "Run"

    window._apply_language("zh")
    assert window.new_workspace_button.text() == "新建"
    assert window.workbench_run_button.text() == "运行"
