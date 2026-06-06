from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QObject, Qt

from shared.ui_schema import ChoiceSpec, FormFieldSpec

SCHEMA_KEY_PROPERTY = "datalab_schema_key"
SCHEMA_REQUIRED_PROPERTY = "datalab_schema_required"
SCHEMA_CHOICES_PROPERTY = "datalab_schema_choices"


def bind_field(
    *,
    field: FormFieldSpec,
    label: Any = None,
    widget: Any = None,
    help_button: Any = None,
    lang: str = "zh",
) -> None:
    label_text = field.label.for_lang(lang)
    tooltip = field.tooltip.for_lang(lang)
    placeholder = field.placeholder.for_lang(lang)

    if label is not None:
        _set_property(label, SCHEMA_KEY_PROPERTY, field.key)
        _call_if_supported(label, "setText", label_text)
        if tooltip:
            _call_if_supported(label, "setToolTip", tooltip)

    if widget is not None:
        _set_property(widget, SCHEMA_KEY_PROPERTY, field.key)
        _set_property(widget, SCHEMA_REQUIRED_PROPERTY, field.required)
        if tooltip:
            _call_if_supported(widget, "setToolTip", tooltip)
        if placeholder:
            _call_if_supported(widget, "setPlaceholderText", placeholder)

    if help_button is not None:
        _set_property(help_button, SCHEMA_KEY_PROPERTY, field.key)
        _call_if_supported(help_button, "setText", "?")
        if tooltip:
            _call_if_supported(help_button, "setToolTip", tooltip)
        _call_if_supported(help_button, "setAccessibleName", f"{label_text} help")
        if tooltip:
            _call_if_supported(help_button, "setAccessibleDescription", tooltip)


def bind_choices(combo: Any, choices: Sequence[ChoiceSpec], *, lang: str = "zh") -> None:
    combo.clear()
    for choice in choices:
        combo.addItem(choice.label.for_lang(lang), choice.value)
        tooltip = choice.tooltip.for_lang(lang)
        if tooltip:
            combo.setItemData(combo.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
    _set_property(combo, SCHEMA_CHOICES_PROPERTY, True)


def find_unbound_required_widgets(root: Any) -> list[object]:
    objects = [root]
    find_children = getattr(root, "findChildren", None)
    if callable(find_children):
        objects.extend(find_children(QObject))

    return [
        obj
        for obj in objects
        if _property(obj, SCHEMA_REQUIRED_PROPERTY) is True
        and not _property(obj, SCHEMA_KEY_PROPERTY)
    ]


def _call_if_supported(obj: Any, method_name: str, *args: object) -> None:
    method = getattr(obj, method_name, None)
    if callable(method):
        method(*args)


def _set_property(obj: Any, name: str, value: object) -> None:
    method = getattr(obj, "setProperty", None)
    if callable(method):
        method(name, value)


def _property(obj: Any, name: str) -> object:
    method = getattr(obj, "property", None)
    if not callable(method):
        return None
    return method(name)
