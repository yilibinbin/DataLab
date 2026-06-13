from __future__ import annotations

from typing import Any

from app_desktop.schema_widgets import (
    make_icon_text_button,
    make_schema_command_button,
    make_schema_help_button,
)
from shared.ui_schema import FormFieldSpec, LocalizedText


class DummyOwner:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, str, str]] = []

    def _register_text(self, widget: Any, zh: str, en: str, attr: str = "setText") -> None:
        self.calls.append((widget, zh, en, attr))


def test_schema_help_button_has_tooltip_accessibility(qtbot: Any) -> None:
    owner = DummyOwner()
    field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程", "Equations"),
        tooltip=LocalizedText("查看方程说明", "View equation help"),
    )

    button = make_schema_help_button(
        owner,
        field=field,
        lang="en",
        object_name="rootEquationsHelpButton",
    )
    qtbot.addWidget(button)

    assert button.objectName() == "rootEquationsHelpButton"
    assert button.property("datalab_schema_key") == "root.equations"
    assert button.text() == "?"
    assert button.toolTip() == "View equation help"
    assert button.accessibleName() == "Equations help"
    assert button.accessibleDescription() == "View equation help"
    assert (button, "查看方程说明", "View equation help", "setToolTip") in owner.calls


def test_schema_command_button_uses_field_label_and_registers_refresh(qtbot: Any) -> None:
    owner = DummyOwner()
    field = FormFieldSpec(
        key="results.export.csv",
        widget_kind="button",
        label=LocalizedText("导出 CSV", "Export CSV"),
        tooltip=LocalizedText("导出当前结果", "Export current results"),
    )

    button = make_schema_command_button(
        owner,
        field=field,
        accessible_name=LocalizedText("导出 CSV", "Export CSV"),
        lang="en",
        object_name="exportCsvButton",
    )
    qtbot.addWidget(button)

    assert button.objectName() == "exportCsvButton"
    assert button.text() == "Export CSV"
    assert button.property("datalab_schema_key") == "results.export.csv"
    assert button.toolTip() == "Export current results"
    assert button.accessibleName() == "Export CSV"
    assert button.accessibleDescription() == "Export current results"
    assert (button, "导出 CSV", "Export CSV", "setText") in owner.calls
    assert (button, "导出当前结果", "Export current results", "setToolTip") in owner.calls
    assert (button, "导出 CSV", "Export CSV", "setAccessibleName") in owner.calls


def test_icon_text_button_sets_stable_metadata(qtbot: Any) -> None:
    button = make_icon_text_button(
        "Run",
        object_name="runButton",
        tooltip="Run the calculation",
    )
    qtbot.addWidget(button)

    assert button.objectName() == "runButton"
    assert button.text() == "Run"
    assert button.toolTip() == "Run the calculation"
    assert button.accessibleName() == "Run"
    assert button.accessibleDescription() == "Run the calculation"
