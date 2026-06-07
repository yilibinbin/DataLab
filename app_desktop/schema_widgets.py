from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton

from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    bind_schema_help_button,
)
from shared.ui_schema import FormFieldSpec, LocalizedText


def make_schema_help_button(
    owner: Any,
    *,
    field: FormFieldSpec,
    lang: str,
    object_name: str = "",
) -> QPushButton:
    button = QPushButton()
    if object_name:
        button.setObjectName(object_name)
    bind_schema_help_button(owner, button, field=field, lang=lang)
    return button


def make_schema_command_button(
    owner: Any,
    *,
    field: FormFieldSpec,
    accessible_name: LocalizedText,
    lang: str,
    object_name: str = "",
) -> QPushButton:
    button = make_icon_text_button(field.label.for_lang(lang), object_name=object_name)
    owner._register_text(button, field.label.zh, field.label.en, "setText")
    bind_schema_command_button(
        owner,
        button,
        field=field,
        accessible_name=accessible_name,
        lang=lang,
    )
    return button


def make_icon_text_button(
    text: str,
    *,
    object_name: str = "",
    tooltip: str = "",
    parent: Any = None,
) -> QPushButton:
    button = QPushButton(text, parent)
    if object_name:
        button.setObjectName(object_name)
    if tooltip:
        button.setToolTip(tooltip)
        button.setAccessibleDescription(tooltip)
    if text:
        button.setAccessibleName(text)
    return button
