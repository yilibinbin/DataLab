from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
)

from app_desktop.formula_preview import open_formula_preview_dialog
from app_desktop.theme import table_style, workbench_section_card_style
from shared.ui_schema import FormFieldSpec


@dataclass(frozen=True)
class WorkbenchSectionCardView:
    host: QGroupBox
    card: QFrame
    card_layout: QVBoxLayout
    title_label: QLabel
    description_label: QLabel


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


def make_workbench_section_card_view(
    owner: Any,
    *,
    object_name: str,
    view_module: str,
    card_object_name: str,
    role: str,
    title_zh: str,
    title_en: str,
    description_zh: str = "",
    description_en: str = "",
    maximum_height: int | None = None,
) -> WorkbenchSectionCardView:
    host = QGroupBox()
    host.setObjectName(object_name)
    host.setProperty("datalab_view_module", view_module)
    host.setProperty("datalab_workbench_section_host", True)
    host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    if maximum_height is not None:
        host.setMaximumHeight(maximum_height)
    host.setStyleSheet(workbench_section_card_style())

    outer_layout = QVBoxLayout(host)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    card = QFrame()
    card.setObjectName(card_object_name)
    card.setProperty("datalab_workbench_section_card", True)
    card.setProperty("datalab_workbench_section_role", role)
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(12, 10, 12, 12)
    card_layout.setSpacing(8)

    title_label = QLabel(_translate_owner(owner, title_zh, title_en))
    title_label.setProperty("datalab_workbench_section_title", True)
    owner._register_text(title_label, title_zh, title_en)
    card_layout.addWidget(title_label)

    description_label = QLabel(_translate_owner(owner, description_zh, description_en))
    description_label.setProperty("datalab_workbench_section_description", True)
    description_label.setWordWrap(True)
    description_label.setVisible(bool(description_zh or description_en))
    owner._register_text(description_label, description_zh, description_en)
    card_layout.addWidget(description_label)

    outer_layout.addWidget(card)
    return WorkbenchSectionCardView(
        host=host,
        card=card,
        card_layout=card_layout,
        title_label=title_label,
        description_label=description_label,
    )


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
    "make_workbench_section_card_view",
    "open_formula_preview",
    "remove_detected_rows_table_rows",
    "remove_parameter_table_rows",
    "register_constant_headers",
    "register_schema_label_refresh",
    "register_table_headers",
    "WorkbenchSectionCardView",
]
