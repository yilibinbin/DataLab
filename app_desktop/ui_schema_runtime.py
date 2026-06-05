from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from app_desktop.ui_schema_binder import bind_field
from shared.ui_schema import FormFieldSpec, LocalizedText


def register_schema_text_refresh(
    owner: Any,
    field: FormFieldSpec,
    *,
    widget: QWidget | None = None,
    help_button: QWidget | None = None,
) -> None:
    if widget is not None:
        if field.tooltip.zh or field.tooltip.en:
            owner._register_text(widget, field.tooltip.zh, field.tooltip.en, "setToolTip")
        if field.placeholder.zh or field.placeholder.en:
            owner._register_text(widget, field.placeholder.zh, field.placeholder.en, "setPlaceholderText")
    if help_button is not None and (field.tooltip.zh or field.tooltip.en):
        owner._register_text(help_button, field.tooltip.zh, field.tooltip.en, "setToolTip")


def bind_schema_command_button(
    owner: Any,
    button: QWidget,
    *,
    field: FormFieldSpec,
    accessible_name: LocalizedText,
    lang: str,
) -> None:
    bind_field(field=field, widget=button, lang=lang)
    register_schema_text_refresh(owner, field, widget=button)
    button.setAccessibleName(accessible_name.for_lang(lang))
    if field.tooltip.zh or field.tooltip.en:
        button.setAccessibleDescription(field.tooltip.for_lang(lang))
        owner._register_text(button, field.tooltip.zh, field.tooltip.en, "setAccessibleDescription")
    owner._register_text(button, accessible_name.zh, accessible_name.en, "setAccessibleName")
