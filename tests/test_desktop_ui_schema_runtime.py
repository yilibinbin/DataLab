from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    bind_schema_help_button,
    register_schema_text_refresh,
)
from shared.ui_schema import FormFieldSpec, LocalizedText


class DummyWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, str, str]] = []

    def _register_text(self, widget: Any, zh: str, en: str, attr: str = "setText") -> None:
        self.calls.append((widget, zh, en, attr))


def _app() -> QApplication:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])


def test_register_schema_text_refresh_registers_tooltip_and_placeholder() -> None:
    _app()
    win = DummyWindow()
    edit = QLineEdit()
    help_button = QPushButton()
    field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        placeholder=LocalizedText("示例", "Example"),
        tooltip=LocalizedText("提示", "Hint"),
    )

    register_schema_text_refresh(win, field, widget=edit, help_button=help_button)

    assert (edit, "提示", "Hint", "setToolTip") in win.calls
    assert (edit, "示例", "Example", "setPlaceholderText") in win.calls
    assert (help_button, "提示", "Hint", "setToolTip") in win.calls


def test_bind_schema_command_button_sets_accessibility_and_schema_key() -> None:
    _app()
    win = DummyWindow()
    button = QPushButton()
    field = FormFieldSpec(
        key="results.export.csv",
        widget_kind="button",
        label=LocalizedText("导出 CSV", "Export CSV"),
        tooltip=LocalizedText("导出当前结果", "Export current results"),
    )

    bind_schema_command_button(
        win,
        button,
        field=field,
        accessible_name=LocalizedText("导出 CSV", "Export CSV"),
        lang="en",
    )

    assert button.property("datalab_schema_key") == "results.export.csv"
    assert button.accessibleName() == "Export CSV"
    assert button.accessibleDescription() == "Export current results"
    assert (button, "导出当前结果", "Export current results", "setToolTip") in win.calls
    assert (button, "导出当前结果", "Export current results", "setAccessibleDescription") in win.calls
    assert (button, "导出 CSV", "Export CSV", "setAccessibleName") in win.calls


def test_bind_schema_help_button_binds_tooltip_and_refresh_registration() -> None:
    _app()
    win = DummyWindow()
    button = QPushButton()
    field = FormFieldSpec(
        key="error.formula",
        widget_kind="textarea",
        label=LocalizedText("公式：", "Formula:"),
        tooltip=LocalizedText("查看公式帮助", "View formula help"),
    )

    bind_schema_help_button(win, button, field=field, lang="en")

    assert button.property("datalab_schema_key") == "error.formula"
    assert button.text() == "?"
    assert button.toolTip() == "View formula help"
    assert button.accessibleName() == "Formula: help"
    assert button.accessibleDescription() == "View formula help"
    assert (button, "查看公式帮助", "View formula help", "setToolTip") in win.calls
