from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_desktop.constants_editor import ConstantsEditor
from app_desktop.schema_widgets import make_editor_header
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import register_schema_text_refresh
from app_desktop.views import helpers as view_helpers
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText


def build_error_mode_view(owner: Any) -> QGroupBox:
    section = view_helpers.make_workbench_section_card_view(
        owner,
        object_name="error_mode_view",
        view_module="app_desktop.views.error",
        card_object_name="error_settings_card",
        role="error",
        title_zh="误差传递设置",
        title_en="Error propagation",
        description_zh="输入公式、常数和不确定度传播方法。",
        description_en="Enter the formula, constants, and uncertainty propagation method.",
    )
    error_box = section.host
    error_layout = section.card_layout

    owner.error_formula_preview_button = view_helpers.make_formula_preview_button(
        owner,
        None,
        title="Preview formula",
    )
    error_header_field = FormFieldSpec(
        key="error.formula",
        widget_kind="textarea",
        label=LocalizedText("公式：", "Formula:"),
        tooltip=LocalizedText(
            "输入误差传递公式。留空不会使用占位示例。",
            "Enter the error propagation formula. Leaving it blank does not use placeholder examples.",
        ),
        required=True,
    )
    error_formula_header = make_editor_header(
        owner,
        error_header_field,
        preview_button=owner.error_formula_preview_button,
    )
    lbl_error_formula = error_formula_header.schema_label
    error_layout.addWidget(error_formula_header)

    owner.formula_edit = QPlainTextEdit()
    owner.formula_edit.setPlaceholderText(
        owner._tr("公式（使用列名或 x1, x2 …）", "Formula (use column names or x1, x2 …)")
    )
    error_layout.addWidget(owner.formula_edit)
    owner.error_formula_preview_button.clicked.connect(
        lambda: view_helpers.open_formula_preview(owner, owner.formula_edit, lhs=None)
    )

    func_btn_row = QHBoxLayout()
    error_layout.setSpacing(4)
    func_btn_row.addStretch()
    func_help_btn = QPushButton("函数支持")
    func_help_btn.setFlat(True)
    func_help_btn.setFocusPolicy(Qt.NoFocus)
    func_help_btn.setToolTip("")
    func_help_btn.clicked.connect(owner._show_error_functions)
    owner._register_text(func_help_btn, "函数支持", "Functions")
    owner.func_help_btn = func_help_btn
    func_btn_row.addWidget(func_help_btn)
    error_layout.addLayout(func_btn_row)

    # owner.error_constants_editor is aliased to input_constants_editor
    owner.error_constants_editor.table_view.setMinimumHeight(160)
    owner.error_constants_editor.text_view.setMinimumHeight(160)

    owner.error_units_box = QGroupBox(owner._tr("单位标注", "Units"))
    owner._register_text(owner.error_units_box, "单位标注", "Units", "setTitle")
    units_layout = QVBoxLayout(owner.error_units_box)
    units_layout.setContentsMargins(8, 8, 8, 8)
    units_layout.setSpacing(6)

    units_header = QHBoxLayout()
    owner.error_units_enabled_checkbox = QCheckBox(owner._tr("启用单位标注", "Enable units"))
    owner._register_text(owner.error_units_enabled_checkbox, "启用单位标注", "Enable units")
    owner.error_units_enabled_checkbox.setProperty("datalab_schema_key", "error.units.enabled")
    owner.error_units_enabled_checkbox.setToolTip(
        owner._tr(
            "启用后，运行误差传递时会保存并可选验证输入、常数和输出单位。",
            "When enabled, error propagation stores and can validate input, constant, and output units.",
        )
    )
    units_header.addWidget(owner.error_units_enabled_checkbox)
    units_header.addWidget(QLabel(owner._tr("模式：", "Mode:")))
    owner.error_units_mode_combo = QComboBox()
    units_mode_items = [
        ("仅显示", "Display only", "display_only"),
        ("验证公式", "Validate expression", "validate_expression"),
    ]
    for zh, _en, data in units_mode_items:
        owner.error_units_mode_combo.addItem(zh, data)
    owner._register_combo(owner.error_units_mode_combo, units_mode_items)
    owner.error_units_mode_combo.setProperty("datalab_schema_key", "error.units.mode")
    owner.error_units_mode_combo.setToolTip(
        owner._tr(
            "仅显示只保存/渲染单位；验证公式会在数值计算前检查量纲兼容性。",
            "Display only stores/renders units; validate expression checks dimensional compatibility before numeric evaluation.",
        )
    )
    units_header.addWidget(owner.error_units_mode_combo)
    units_header.addStretch()
    units_layout.addLayout(units_header)

    owner.error_units_body = QWidget()
    units_body_layout = QVBoxLayout(owner.error_units_body)
    units_body_layout.setContentsMargins(0, 0, 0, 0)
    units_body_layout.setSpacing(6)
    owner.error_units_inputs_editor = ConstantsEditor(min_rows=2, checked=True, checkbox_text="")
    owner.error_units_inputs_editor.set_table_headers(owner._tr("符号", "Symbol"), owner._tr("单位", "Unit"))
    owner.error_units_inputs_editor.setToolTip(
        owner._tr(
            "输入列的单位。符号使用公式中的列名或规范化后的变量名，例如 A 或 distance。",
            "Units for input columns. Symbols use formula column names or canonical variable names, such as A or distance.",
        )
    )
    owner.error_units_inputs_editor.setProperty("datalab_schema_key", "error.units.inputs")
    owner.error_units_constants_editor = ConstantsEditor(min_rows=2, checked=True, checkbox_text="")
    owner.error_units_constants_editor.set_table_headers(owner._tr("符号", "Symbol"), owner._tr("单位", "Unit"))
    owner.error_units_constants_editor.setToolTip(
        owner._tr(
            "常数的单位。符号必须与左侧常数表中的常数名一致。",
            "Units for constants. Symbols must match names in the left constants table.",
        )
    )
    owner.error_units_constants_editor.setProperty("datalab_schema_key", "error.units.constants")
    output_row = QHBoxLayout()
    output_row.addWidget(QLabel(owner._tr("输出 result 单位：", "Output result unit:")))
    owner.error_units_output_edit = QLineEdit()
    owner.error_units_output_edit.setPlaceholderText(owner._tr("例如 m", "e.g. m"))
    owner.error_units_output_edit.setProperty("datalab_schema_key", "error.units.outputs.result")
    owner.error_units_output_edit.setToolTip(
        owner._tr(
            "可选。验证模式下，公式结果单位必须与这里填写的 result 单位完全一致。",
            "Optional. In validate mode, the formula result unit must exactly match this result unit.",
        )
    )
    output_row.addWidget(owner.error_units_output_edit)
    units_body_layout.addWidget(QLabel(owner._tr("输入单位：", "Input units:")))
    units_body_layout.addWidget(owner.error_units_inputs_editor)
    units_body_layout.addWidget(QLabel(owner._tr("常数单位：", "Constant units:")))
    units_body_layout.addWidget(owner.error_units_constants_editor)
    units_body_layout.addLayout(output_row)
    units_layout.addWidget(owner.error_units_body)
    error_layout.addWidget(owner.error_units_box)

    def _update_error_units_controls() -> None:
        enabled = owner.error_units_enabled_checkbox.isChecked()
        owner.error_units_mode_combo.setEnabled(enabled)
        owner.error_units_body.setVisible(enabled)
        owner.error_units_body.setEnabled(enabled)

    owner._update_error_units_controls = _update_error_units_controls
    owner.error_units_enabled_checkbox.toggled.connect(lambda *_args: owner._update_error_units_controls())
    owner._update_error_units_controls()

    method_row = QHBoxLayout()
    lbl_err_method = QLabel("方法：")
    owner._register_text(lbl_err_method, "方法：", "Method:")
    owner.error_method_combo = QComboBox()
    error_method_items = [
        ("Taylor（偏导）", "Taylor (derivative)", "taylor"),
        ("Monte Carlo", "Monte Carlo", "monte_carlo"),
    ]
    for zh, _en, data in error_method_items:
        owner.error_method_combo.addItem(zh, data)
    owner._register_combo(owner.error_method_combo, error_method_items)
    owner.error_method_combo.currentIndexChanged.connect(owner._update_error_propagation_controls)
    method_row.addWidget(lbl_err_method)
    method_row.addWidget(owner.error_method_combo)
    method_row.addStretch()
    error_layout.addLayout(method_row)

    owner.error_taylor_widget = QWidget()
    taylor_layout = QHBoxLayout(owner.error_taylor_widget)
    taylor_layout.setContentsMargins(0, 0, 0, 0)
    taylor_layout.setSpacing(6)
    lbl_err_order = QLabel("阶数：")
    owner._register_text(lbl_err_order, "阶数：", "Order:")
    owner.error_order_spin = QSpinBox()
    owner.error_order_spin.setRange(1, 2)
    owner.error_order_spin.setValue(1)
    owner.error_order_spin.setToolTip(
        owner._tr(
            "1 阶：线性误差估计；2 阶：包含 Hessian（二阶偏导）贡献。",
            "Order 1: linear propagation; order 2: includes Hessian (second-derivative) contributions.",
        )
    )
    taylor_layout.addWidget(lbl_err_order)
    taylor_layout.addWidget(owner.error_order_spin)
    taylor_layout.addStretch()
    error_layout.addWidget(owner.error_taylor_widget)

    owner.error_mc_widget = QWidget()
    mc_layout = QFormLayout(owner.error_mc_widget)
    mc_layout.setContentsMargins(0, 0, 0, 0)
    mc_layout.setSpacing(6)
    lbl_mc_samples = QLabel("MC 样本数：")
    owner._register_text(lbl_mc_samples, "MC 样本数：", "MC samples:")
    owner.error_mc_samples_spin = QSpinBox()
    owner.error_mc_samples_spin.setRange(100, 200000)
    owner.error_mc_samples_spin.setSingleStep(100)
    owner.error_mc_samples_spin.setValue(5000)
    owner.error_mc_samples_spin.setToolTip(
        owner._tr(
            "Monte Carlo 样本数（越大越稳定，但耗时更长），至少 100。",
            "Monte Carlo sample count (larger is more stable but slower), minimum 100.",
        )
    )
    mc_layout.addRow(lbl_mc_samples, owner.error_mc_samples_spin)
    lbl_mc_seed = QLabel("随机种子（可选）：")
    owner._register_text(lbl_mc_seed, "随机种子（可选）：", "Seed (optional):")
    owner.error_mc_seed_edit = QLineEdit()
    owner.error_mc_seed_edit.setPlaceholderText(owner._tr("留空=随机", "blank=random"))
    owner.error_mc_seed_edit.setToolTip(
        owner._tr(
            "留空表示每次随机；填写整数可复现实验结果。",
            "Leave blank for random each run; set an integer for reproducibility.",
        )
    )
    mc_layout.addRow(lbl_mc_seed, owner.error_mc_seed_edit)
    error_layout.addWidget(owner.error_mc_widget)
    owner.error_mc_widget.hide()

    _bind_error_schema_fields(
        owner,
        lbl_error_formula=lbl_error_formula,
        lbl_error_method=lbl_err_method,
        error_method_items=error_method_items,
        lbl_error_order=lbl_err_order,
        lbl_mc_samples=lbl_mc_samples,
        lbl_mc_seed=lbl_mc_seed,
    )

    owner._update_error_propagation_controls()
    owner._update_error_propagation_controls()
    return error_box


def _bind_error_schema_fields(
    owner: Any,
    *,
    lbl_error_formula: QLabel,
    lbl_error_method: QLabel,
    error_method_items: list[tuple[str, str, str]],
    lbl_error_order: QLabel,
    lbl_mc_samples: QLabel,
    lbl_mc_seed: QLabel,
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    formula_field = FormFieldSpec(
        key="error.formula",
        widget_kind="textarea",
        label=LocalizedText("公式：", "Formula:"),
        placeholder=LocalizedText(
            "公式（使用列名或 x1, x2 …）",
            "Formula (use column names or x1, x2 …)",
        ),
        tooltip=LocalizedText(
            "输入要传播不确定度的公式，可使用数据列名或 x1、x2 等变量。",
            "Enter the formula whose uncertainty should be propagated; use column names or variables such as x1 and x2.",
        ),
        required=True,
    )
    function_help_field = FormFieldSpec(
        key="error.functions",
        widget_kind="button",
        label=LocalizedText("函数支持", "Functions"),
        tooltip=LocalizedText(
            "查看公式中支持的函数和表达式语法。",
            "View supported functions and expression syntax for formulas.",
        ),
        required=False,
    )
    method_field = FormFieldSpec(
        key="error.method",
        widget_kind="select",
        label=LocalizedText("方法：", "Method:"),
        tooltip=LocalizedText(
            "Taylor 使用偏导传播不确定度；Monte Carlo 通过随机采样估计不确定度。",
            "Taylor propagates uncertainty with derivatives; Monte Carlo estimates uncertainty by random sampling.",
        ),
        required=True,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in error_method_items],
    )
    order_field = FormFieldSpec(
        key="error.taylor.order",
        widget_kind="number",
        label=LocalizedText("阶数：", "Order:"),
        tooltip=LocalizedText(
            "1 阶：线性误差估计；2 阶：包含 Hessian（二阶偏导）贡献。",
            "Order 1: linear propagation; order 2: includes Hessian (second-derivative) contributions.",
        ),
        required=False,
    )
    mc_samples_field = FormFieldSpec(
        key="error.monte_carlo.samples",
        widget_kind="number",
        label=LocalizedText("MC 样本数：", "MC samples:"),
        tooltip=LocalizedText(
            "Monte Carlo 样本数（越大越稳定，但耗时更长），至少 100。",
            "Monte Carlo sample count (larger is more stable but slower), minimum 100.",
        ),
        required=False,
    )
    mc_seed_field = FormFieldSpec(
        key="error.monte_carlo.seed",
        widget_kind="text",
        label=LocalizedText("随机种子（可选）：", "Seed (optional):"),
        placeholder=LocalizedText("留空=随机", "blank=random"),
        tooltip=LocalizedText(
            "留空表示每次随机；填写整数可复现实验结果。",
            "Leave blank for random each run; set an integer for reproducibility.",
        ),
        required=False,
    )

    bind_field(
        field=formula_field,
        label=lbl_error_formula,
        widget=owner.formula_edit,
        help_button=owner.error_formula_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        formula_field,
        widget=owner.formula_edit,
        help_button=owner.error_formula_preview_button,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_error_formula, formula_field)
    bind_field(field=function_help_field, widget=owner.func_help_btn, lang=lang)
    register_schema_text_refresh(owner, function_help_field, widget=owner.func_help_btn)
    bind_field(field=method_field, label=lbl_error_method, widget=owner.error_method_combo, lang=lang)
    bind_choices(owner.error_method_combo, method_field.choices, lang=lang)
    register_schema_text_refresh(owner, method_field, widget=owner.error_method_combo)
    bind_field(field=order_field, label=lbl_error_order, widget=owner.error_order_spin, lang=lang)
    register_schema_text_refresh(owner, order_field, widget=owner.error_order_spin)
    bind_field(field=mc_samples_field, label=lbl_mc_samples, widget=owner.error_mc_samples_spin, lang=lang)
    register_schema_text_refresh(owner, mc_samples_field, widget=owner.error_mc_samples_spin)
    bind_field(field=mc_seed_field, label=lbl_mc_seed, widget=owner.error_mc_seed_edit, lang=lang)
    register_schema_text_refresh(owner, mc_seed_field, widget=owner.error_mc_seed_edit)


__all__ = ["build_error_mode_view"]
