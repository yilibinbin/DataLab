from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app_desktop.constants_editor import ConstantsEditor
from app_desktop.formula_preview import open_formula_preview_dialog
from app_desktop.theme import (
    CARD_MARGIN_H,
    CARD_MARGIN_V,
    INNER_BOX_MARGIN,
    SPACE_MD,
    SPACE_SM,
    table_style,
    workbench_section_card_style,
)
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


def _unit_editor(
    owner: Any,
    *,
    schema_key: str,
    tooltip_zh: str,
    tooltip_en: str,
) -> ConstantsEditor:
    editor = ConstantsEditor(min_rows=2, checked=True, checkbox_text="")
    register_constant_headers(
        owner,
        editor.set_table_headers,
        zh_headers=("符号", "单位"),
        en_headers=("Symbol", "Unit"),
    )
    editor.setToolTip(_translate_owner(owner, tooltip_zh, tooltip_en))
    editor.setProperty("datalab_schema_key", schema_key)
    owner._register_text(editor, tooltip_zh, tooltip_en, "setToolTip")
    apply_equal_column_stretch(editor.table_view)
    editor.table_view.setStyleSheet(get_table_style())
    fit_table_height_to_contents(editor.table_view, min_rows=2, max_rows=5)
    return editor


def make_display_unit_controls(
    owner: Any,
    *,
    attr_prefix: str,
    schema_prefix: str,
    title_zh: str = "单位标注",
    title_en: str = "Units",
    input_label_zh: str = "输入单位：",
    input_label_en: str = "Input units:",
    input_tooltip_zh: str = "输入列的单位。符号使用数据列名或规范化后的变量名。",
    input_tooltip_en: str = "Units for input columns. Symbols use data column names or canonical variable names.",
    include_constants: bool = False,
    constants_label_zh: str = "常数单位：",
    constants_label_en: str = "Constant units:",
    constants_tooltip_zh: str = "常数的单位。符号必须与常数表中的常数名一致。",
    constants_tooltip_en: str = "Units for constants. Symbols must match names in the constants table.",
    include_parameters: bool = False,
    parameters_label_zh: str = "参数单位：",
    parameters_label_en: str = "Parameter units:",
    parameters_tooltip_zh: str = "拟合参数的单位。符号必须与参数列表中的参数名一致。",
    parameters_tooltip_en: str = "Units for fitting parameters. Symbols must match names in the parameter table.",
    output_label_zh: str = "输出 result 单位：",
    output_label_en: str = "Output result unit:",
    output_tooltip_zh: str = "可选。只用于结果、LaTeX 和图片中的单位显示，不改变数值计算。",
    output_tooltip_en: str = "Optional. Used only for result, LaTeX, and plot labels; it does not change numeric computation.",
) -> QGroupBox:
    """Create shared display-only unit annotation controls.

    Error propagation still owns its validate-expression UI. Other families use
    this display-only control so unit labels stay metadata instead of changing
    calculation semantics.
    """

    box = QGroupBox(_translate_owner(owner, title_zh, title_en))
    owner._register_text(box, title_zh, title_en, "setTitle")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(INNER_BOX_MARGIN, INNER_BOX_MARGIN, INNER_BOX_MARGIN, INNER_BOX_MARGIN)
    layout.setSpacing(SPACE_SM)

    checkbox = QCheckBox(_translate_owner(owner, "启用单位标注", "Enable units"))
    checkbox.setProperty("datalab_schema_key", f"{schema_prefix}.units.enabled")
    checkbox.setToolTip(
        _translate_owner(
            owner,
            "启用后，仅保存并渲染单位标注；不会改变数值计算或执行量纲校验。",
            "When enabled, unit annotations are stored and rendered only; numeric computation and dimensional validation are unchanged.",
        )
    )
    owner._register_text(checkbox, "启用单位标注", "Enable units")
    owner._register_text(
        checkbox,
        "启用后，仅保存并渲染单位标注；不会改变数值计算或执行量纲校验。",
        "When enabled, unit annotations are stored and rendered only; numeric computation and dimensional validation are unchanged.",
        "setToolTip",
    )

    header = QHBoxLayout()
    header.addWidget(checkbox)
    header.addStretch()
    layout.addLayout(header)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(6)

    input_label = QLabel(_translate_owner(owner, input_label_zh, input_label_en))
    owner._register_text(input_label, input_label_zh, input_label_en)
    inputs_editor = _unit_editor(
        owner,
        schema_key=f"{schema_prefix}.units.inputs",
        tooltip_zh=input_tooltip_zh,
        tooltip_en=input_tooltip_en,
    )
    body_layout.addWidget(input_label)
    body_layout.addWidget(inputs_editor)

    constants_editor = None
    if include_constants:
        constants_label = QLabel(_translate_owner(owner, constants_label_zh, constants_label_en))
        owner._register_text(constants_label, constants_label_zh, constants_label_en)
        constants_editor = _unit_editor(
            owner,
            schema_key=f"{schema_prefix}.units.constants",
            tooltip_zh=constants_tooltip_zh,
            tooltip_en=constants_tooltip_en,
        )
        body_layout.addWidget(constants_label)
        body_layout.addWidget(constants_editor)

    parameters_editor = None
    if include_parameters:
        parameters_label = QLabel(_translate_owner(owner, parameters_label_zh, parameters_label_en))
        owner._register_text(parameters_label, parameters_label_zh, parameters_label_en)
        parameters_editor = _unit_editor(
            owner,
            schema_key=f"{schema_prefix}.units.parameters",
            tooltip_zh=parameters_tooltip_zh,
            tooltip_en=parameters_tooltip_en,
        )
        body_layout.addWidget(parameters_label)
        body_layout.addWidget(parameters_editor)

    output_row = QHBoxLayout()
    output_label = QLabel(_translate_owner(owner, output_label_zh, output_label_en))
    owner._register_text(output_label, output_label_zh, output_label_en)
    output_row.addWidget(output_label)
    output_edit = QLineEdit()
    output_edit.setPlaceholderText(_translate_owner(owner, "例如 m", "e.g. m"))
    output_edit.setProperty("datalab_schema_key", f"{schema_prefix}.units.outputs.result")
    output_edit.setToolTip(_translate_owner(owner, output_tooltip_zh, output_tooltip_en))
    owner._register_text(output_edit, "例如 m", "e.g. m", "setPlaceholderText")
    owner._register_text(output_edit, output_tooltip_zh, output_tooltip_en, "setToolTip")
    output_row.addWidget(output_edit)
    body_layout.addLayout(output_row)

    layout.addWidget(body)

    setattr(owner, f"{attr_prefix}_units_box", box)
    setattr(owner, f"{attr_prefix}_units_enabled_checkbox", checkbox)
    setattr(owner, f"{attr_prefix}_units_body", body)
    # Name the editors after their owner attribute (mirrors input_constants_editor) so
    # the GUI schema scanner recognizes them as expected state owners rather than
    # flagging them as unexpected ConstantsEditor instances mounted with no objectName.
    inputs_editor.setObjectName(f"{attr_prefix}_units_inputs_editor")
    setattr(owner, f"{attr_prefix}_units_inputs_editor", inputs_editor)
    if constants_editor is not None:
        constants_editor.setObjectName(f"{attr_prefix}_units_constants_editor")
        setattr(owner, f"{attr_prefix}_units_constants_editor", constants_editor)
    if parameters_editor is not None:
        parameters_editor.setObjectName(f"{attr_prefix}_units_parameters_editor")
        setattr(owner, f"{attr_prefix}_units_parameters_editor", parameters_editor)
    setattr(owner, f"{attr_prefix}_units_output_edit", output_edit)

    def update_controls() -> None:
        enabled = checkbox.isChecked()
        body.setVisible(enabled)
        body.setEnabled(enabled)

    setattr(owner, f"_update_{attr_prefix}_units_controls", update_controls)
    checkbox.toggled.connect(lambda *_args: update_controls())
    update_controls()
    return box


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
    card_layout.setContentsMargins(CARD_MARGIN_H, CARD_MARGIN_V, CARD_MARGIN_H, CARD_MARGIN_H)
    card_layout.setSpacing(SPACE_MD)

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


def _populated_row_count(table: QTableWidget) -> int:
    count = 0
    for row in range(table.rowCount()):
        if any(
            table.item(row, col) is not None and table.item(row, col).text().strip()
            for col in range(table.columnCount())
        ):
            count = row + 1
    return count


def fit_table_height_to_contents(table: QTableWidget, min_rows: int = 1, max_rows: int = 8) -> None:
    if table is None:
        return
    row_height = table.rowHeight(0) if table.rowCount() > 0 else 24
    if row_height <= 0:
        row_height = 24
    header = table.horizontalHeader()
    header_height = 0
    if not header.isHidden():
        header_height = header.height() or 25
        if header_height <= 0:
            header_height = 25
    visible_rows = max(min_rows, min(_populated_row_count(table) + 1, max_rows))
    frame_width = table.frameWidth() * 2
    total_height = header_height + (visible_rows * row_height) + frame_width + 4
    table.setMinimumHeight(total_height)
    table.setMaximumHeight(total_height)


__all__ = [
    "apply_equal_column_stretch",
    "add_detected_rows_table_row",
    "add_parameter_table_row",
    "fit_table_height_to_contents",
    "get_table_style",
    "make_formula_preview_button",
    "make_display_unit_controls",
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
