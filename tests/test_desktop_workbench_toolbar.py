from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QToolButton
from PySide6.QtWidgets import QStyle, QWidget


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
    assert window.new_workspace_button.accessibleName() == "New"
    assert window.new_workspace_button.toolTip() == "Create a blank workspace."
    assert window.new_workspace_button.accessibleDescription() == "Create a blank workspace."
    assert window.workbench_run_button.text() == "Run"
    assert window.workbench_run_button.accessibleName() == "Run"
    assert window.workbench_run_button.toolTip() == "Run the calculation with the current configuration."
    assert (
        window.workbench_run_button.accessibleDescription()
        == "Run the calculation with the current configuration."
    )

    window._apply_language("zh")
    assert window.new_workspace_button.text() == "新建"
    assert window.new_workspace_button.accessibleName() == "新建"
    assert window.new_workspace_button.toolTip() == "新建空白工作区。"
    assert window.new_workspace_button.accessibleDescription() == "新建空白工作区。"
    assert window.workbench_run_button.text() == "运行"
    assert window.workbench_run_button.accessibleName() == "运行"
    assert window.workbench_run_button.toolTip() == "运行当前配置的计算。"
    assert window.workbench_run_button.accessibleDescription() == "运行当前配置的计算。"


def test_toolbar_button_builder_registers_i18n_metadata_and_dispatches(qtbot: Any) -> None:
    from app_desktop.workbench_toolbar import make_toolbar_button

    class Owner(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.registrations: list[tuple[str, str, str]] = []
            self.calls: list[str] = []

        def _tr(self, _zh: str, en: str) -> str:
            return en

        def _register_text(
            self,
            _widget: object,
            zh: str,
            en: str,
            attr: str = "setText",
        ) -> None:
            self.registrations.append((attr, zh, en))

        def handle_click(self) -> None:
            self.calls.append("handle_click")

    owner = Owner()
    qtbot.addWidget(owner)
    button = make_toolbar_button(
        owner,
        "动作",
        "Action",
        "sample_toolbar_button",
        QStyle.StandardPixmap.SP_DialogOkButton,
        "handle_click",
        tooltip_zh="执行动作。",
        tooltip_en="Run the action.",
    )
    qtbot.addWidget(button)

    assert button.objectName() == "sample_toolbar_button"
    assert button.text() == "Action"
    assert button.accessibleName() == "Action"
    assert button.toolTip() == "Run the action."
    assert button.accessibleDescription() == "Run the action."
    assert not button.icon().isNull()
    assert owner.registrations == [
        ("setText", "动作", "Action"),
        ("setAccessibleName", "动作", "Action"),
        ("setToolTip", "执行动作。", "Run the action."),
        ("setAccessibleDescription", "执行动作。", "Run the action."),
    ]

    button.click()

    assert owner.calls == ["handle_click"]
