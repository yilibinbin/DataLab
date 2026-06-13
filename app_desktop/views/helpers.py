from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton, QTableWidget

from app_desktop.formula_preview import open_formula_preview_dialog
from app_desktop.theme import table_style
from shared.ui_schema import FormFieldSpec


def apply_equal_column_stretch(table: QTableWidget) -> None:
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setStretchLastSection(False)


def get_table_style() -> str:
    return table_style()


def open_formula_preview(owner: Any, edit_widget: Any, lhs: Any = None) -> None:
    if hasattr(edit_widget, "toPlainText"):
        text = edit_widget.toPlainText().strip()
    else:
        text = edit_widget.text().strip()
    left_hand_side = lhs() if callable(lhs) else lhs
    open_formula_preview_dialog(owner, text, left_hand_side)


def _translate_owner(owner: Any, zh: str, en: str) -> str:
    translate = getattr(owner, "_tr", None)
    if callable(translate):
        return str(translate(zh, en))
    is_en = getattr(owner, "_is_en", None)
    if callable(is_en) and bool(is_en()):
        return en
    return zh


def make_formula_preview_button(
    owner: Any,
    edit_widget: Any = None,
    lhs: Any = None,
    title: str = "Preview formula",
    *,
    object_name: str = "",
    tooltip_zh: str = "预览公式",
) -> QPushButton:
    button_text = _translate_owner(owner, "预览", "Preview")
    tooltip = _translate_owner(owner, tooltip_zh, title)
    button = QPushButton(button_text)
    if object_name:
        button.setObjectName(object_name)
    button.setFocusPolicy(Qt.NoFocus)
    button.setProperty("datalab_preserve_tooltip", True)
    button.setToolTip(tooltip)
    button.setAccessibleName(button_text)
    button.setAccessibleDescription(tooltip)
    owner._register_text(button, "预览", "Preview")
    owner._register_text(button, tooltip_zh, title, "setToolTip")
    owner._register_text(button, "预览", "Preview", "setAccessibleName")
    owner._register_text(button, tooltip_zh, title, "setAccessibleDescription")
    if edit_widget is not None:
        button.clicked.connect(lambda: open_formula_preview(owner, edit_widget, lhs=lhs))
    return button


def make_small_help_button() -> QPushButton:
    button = QPushButton("?")
    button.setFlat(True)
    button.setFocusPolicy(Qt.NoFocus)
    button.setFixedWidth(24)
    return button


class HeaderRegistration:
    def __init__(self, setter: Any) -> None:
        self._setter = setter

    def set_headers(self, headers: Any) -> None:
        self._setter(headers)

    def set_table_headers(self, headers: Any) -> None:
        self._setter(*headers)


def register_table_headers(
    owner: Any,
    setter: Any,
    zh_headers: tuple[str, ...],
    en_headers: tuple[str, ...],
) -> None:
    registration = HeaderRegistration(setter)
    registration.set_headers(zh_headers if not bool(getattr(owner, "_is_en", lambda: False)()) else en_headers)
    owner._register_text(registration, zh_headers, en_headers, "set_headers")


def register_constant_headers(
    owner: Any,
    setter: Any,
    zh_headers: tuple[str, str] = ("名称", "值"),
    en_headers: tuple[str, str] = ("Name", "Value"),
) -> None:
    registration = HeaderRegistration(setter)
    registration.set_table_headers(
        zh_headers if not bool(getattr(owner, "_is_en", lambda: False)()) else en_headers
    )
    owner._register_text(registration, zh_headers, en_headers, "set_table_headers")


def register_schema_label_refresh(owner: Any, label: QLabel, field: FormFieldSpec) -> None:
    owner._register_text(label, field.label.zh, field.label.en, "setText")
    if field.tooltip.zh or field.tooltip.en:
        owner._register_text(label, field.tooltip.zh, field.tooltip.en, "setToolTip")
        owner._register_text(label, field.tooltip.zh, field.tooltip.en, "setAccessibleDescription")


def add_detected_rows_table_row(owner: Any, table_name: str) -> None:
    table = getattr(owner, table_name, None)
    if table is None:
        return
    table.add_row()


def remove_detected_rows_table_rows(owner: Any, table_name: str) -> None:
    table = getattr(owner, table_name, None)
    if table is None:
        return
    selected_rows = {index.row() for index in table.table_view.selectedIndexes()}
    if not selected_rows and table.table_view.rowCount() > 0:
        last_row = table.table_view.rowCount() - 1
        if not table.is_row_empty(last_row):
            return
        selected_rows = {last_row}
    table.delete_rows(selected_rows)


def add_parameter_table_row(table: Any) -> None:
    if table is None:
        return
    table.add_parameter_row()


def remove_parameter_table_rows(table: Any) -> None:
    if table is None:
        return
    selected_rows = {index.row() for index in table.table_view.selectedIndexes()}
    if not selected_rows and table.table_view.rowCount() > 0:
        last_row = table.table_view.rowCount() - 1
        if not table.is_row_empty(last_row):
            return
        selected_rows = {last_row}
    table.delete_rows(selected_rows)


__all__ = [
    "apply_equal_column_stretch",
    "add_detected_rows_table_row",
    "add_parameter_table_row",
    "get_table_style",
    "make_formula_preview_button",
    "make_small_help_button",
    "open_formula_preview",
    "remove_detected_rows_table_rows",
    "remove_parameter_table_rows",
    "register_constant_headers",
    "register_schema_label_refresh",
    "register_table_headers",
]
