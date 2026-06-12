from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_desktop.current_page_stack import CurrentPageStack
from app_desktop.schema_widgets import make_editor_header
from app_desktop.theme import workbench_muted_text_style
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    register_schema_text_refresh,
)
from app_desktop.views import helpers as view_helpers
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText
from shared.ui_specs import EXTRAPOLATION_METHOD_SPECS, get_method_options


def build_extrapolation_mode_view(owner: Any) -> QGroupBox:
    extrap_box = QGroupBox("外推设置")
    extrap_box.setProperty("datalab_view_module", "app_desktop.views.extrapolation")
    owner._register_title(extrap_box, "外推设置", "Extrapolation")
    extrap_layout = QVBoxLayout(extrap_box)

    method_layout = QHBoxLayout()
    method_label = QLabel("外推方法：")
    owner._register_text(method_label, "外推方法：", "Method:")
    owner.method_combo = QComboBox()
    method_options_zh = get_method_options("zh")
    method_options_en = get_method_options("en")
    combo_items: list[tuple[str, str, str]] = []
    for (name_zh, key), (name_en, _) in zip(method_options_zh, method_options_en):
        owner.method_combo.addItem(name_zh, key)
        combo_items.append((name_zh, name_en, key))
    owner._register_combo(owner.method_combo, combo_items)
    owner.method_combo.currentIndexChanged.connect(owner._update_method_state)
    method_layout.addWidget(method_label)
    method_layout.addWidget(owner.method_combo)

    method_help_btn = QPushButton("?")
    method_help_btn.setFlat(True)
    method_help_btn.setFocusPolicy(Qt.NoFocus)
    method_help_btn.setMaximumWidth(30)
    method_help_btn.clicked.connect(owner._show_method_help)
    method_help_btn.setToolTip(
        owner._tr(
            "点击查看当前外推方法的详细说明、适用场景和参数解释",
            "Click to view detailed description, applicable scenarios, and parameter explanations for the current method",
        )
    )
    owner._register_text(method_help_btn, "?", "?")
    owner.method_help_btn = method_help_btn
    method_layout.addWidget(method_help_btn)
    method_layout.addStretch()
    extrap_layout.addLayout(method_layout)

    owner.extrap_method_stack = CurrentPageStack()
    owner.extrap_method_stack.setObjectName("extrap_method_stack")

    owner.custom_formula_widget = QWidget()
    custom_layout = QVBoxLayout(owner.custom_formula_widget)
    owner.custom_formula_preview_button = view_helpers.make_formula_preview_button(
        owner,
        None,
        title="Preview formula",
    )
    custom_header_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="textarea",
        label=LocalizedText("自定义公式：", "Custom formula:"),
        tooltip=LocalizedText(
            "输入自定义三点外推公式。可使用 A/B/C、列名或 x1/x2/x3，并支持数学函数。",
            "Enter a custom three-point extrapolation formula. Use A/B/C, column names, or x1/x2/x3; math functions are supported.",
        ),
        required=True,
    )
    custom_title_header = make_editor_header(
        owner,
        custom_header_field,
        preview_button=owner.custom_formula_preview_button,
    )
    lbl_custom = custom_title_header.schema_label
    custom_layout.addWidget(custom_title_header)
    owner.custom_formula_edit = QPlainTextEdit("(C - B)^2/(B - A) + C")
    owner.custom_formula_edit.setPlaceholderText(
        owner._tr(
            "示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
            "Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
        )
    )
    owner.custom_formula_edit.setMinimumHeight(80)
    owner.custom_formula_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    custom_layout.addWidget(owner.custom_formula_edit, stretch=1)
    owner.custom_formula_preview_button.clicked.connect(
        lambda: view_helpers.open_formula_preview(owner, owner.custom_formula_edit, lhs=None)
    )

    custom_hint_row = QHBoxLayout()
    custom_hint_row.setContentsMargins(0, 0, 0, 0)
    custom_hint_row.setSpacing(6)
    func_btn = QPushButton("函数支持")
    func_btn.setFlat(True)
    func_btn.setFocusPolicy(Qt.NoFocus)
    func_btn.clicked.connect(owner._show_error_functions)
    owner._register_text(func_btn, "函数支持", "Functions")
    owner.custom_formula_function_button = func_btn
    custom_hint_row.addWidget(func_btn)
    hint_lbl = QLabel(
        owner._tr(
            "支持 Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]，可用 A/B/C、列名或 x1/x2。",
            "Supports Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]; use A/B/C, headers, or x1/x2.",
        )
    )
    hint_lbl.setWordWrap(True)
    hint_lbl.setStyleSheet(workbench_muted_text_style())
    custom_hint_row.addWidget(hint_lbl)
    custom_hint_row.addStretch()
    custom_layout.addLayout(custom_hint_row)

    owner.power_box = QGroupBox("幂律参数")
    owner._register_title(owner.power_box, "幂律参数", "Power-law parameters")
    power_layout = QFormLayout(owner.power_box)
    owner.power_x_edits = []
    power_x_labels: list[QLabel] = []
    for idx, default in enumerate((10, 20, 40), start=1):
        edit = QLineEdit(str(default))
        owner.power_x_edits.append(edit)
        lbl_x = QLabel(f"x{idx}：")
        owner._register_text(lbl_x, f"x{idx}：", f"x{idx}:")
        power_x_labels.append(lbl_x)
        power_layout.addRow(lbl_x, edit)
    owner.power_p_edit = QLineEdit()
    owner.power_p_edit.setPlaceholderText(owner._tr("留空则自动求解 p", "Leave blank to solve p automatically"))
    lbl_p = QLabel("自定义 p（可选）：")
    owner._register_text(lbl_p, "自定义 p（可选）：", "Custom p (optional):")
    power_layout.addRow(lbl_p, owner.power_p_edit)
    owner.power_seed_guesses_edit = QLineEdit()
    owner.power_seed_guesses_edit.setPlaceholderText(
        owner._tr("如 0.5, 1, 2, -1", "e.g. 0.5, 1, 2, -1")
    )
    lbl_seed = QLabel("p 种子列表（可选）：")
    owner._register_text(lbl_seed, "p 种子列表（可选）：", "p seed list (optional):")
    power_layout.addRow(lbl_seed, owner.power_seed_guesses_edit)

    owner.levin_box = QGroupBox("Levin u 变换参数")
    owner._register_title(owner.levin_box, "Levin u 变换参数", "Levin u-transform parameters")
    levin_layout = QFormLayout(owner.levin_box)

    lbl_variant = QLabel("变换类型：")
    owner._register_text(lbl_variant, "变换类型：", "Variant:")
    owner.levin_variant_combo = QComboBox()
    owner.levin_variant_combo.addItem("u (最常用)", "u")
    owner.levin_variant_combo.addItem("t (级数)", "t")
    owner.levin_variant_combo.addItem("v (积分)", "v")
    owner._register_combo(
        owner.levin_variant_combo,
        [
            ("u (最常用)", "u (most common)", "u"),
            ("t (级数)", "t (series)", "t"),
            ("v (积分)", "v (integrals)", "v"),
        ],
    )
    levin_layout.addRow(lbl_variant, owner.levin_variant_combo)

    lbl_order = QLabel("变换阶数：")
    owner._register_text(lbl_order, "变换阶数：", "Transform order:")
    owner.levin_order_spin = QSpinBox()
    owner.levin_order_spin.setRange(1, 10)
    owner.levin_order_spin.setValue(2)
    owner.levin_order_spin.setToolTip(
        owner._tr(
            "变换阶数（越高越精确但需要更多项，至少需要 2N+1 项数据）",
            "Transform order (higher = more accurate but needs more terms, requires at least 2N+1 data points)",
        )
    )
    levin_layout.addRow(lbl_order, owner.levin_order_spin)

    lbl_weight = QLabel("权重函数：")
    owner._register_text(lbl_weight, "权重函数：", "Weight function:")
    owner.levin_weight_combo = QComboBox()
    owner.levin_weight_combo.addItem("默认 (1)", "default")
    owner.levin_weight_combo.addItem("1/(n+1)", "reciprocal")
    owner.levin_weight_combo.addItem("1/(n+β)", "reciprocal_beta")
    owner._register_combo(
        owner.levin_weight_combo,
        [
            ("默认 (1)", "Default (1)", "default"),
            ("1/(n+1)", "1/(n+1)", "reciprocal"),
            ("1/(n+β)", "1/(n+β)", "reciprocal_beta"),
        ],
    )
    owner.levin_weight_combo.currentIndexChanged.connect(owner._update_levin_weight_state)
    levin_layout.addRow(lbl_weight, owner.levin_weight_combo)

    lbl_beta = QLabel("β 参数：")
    owner._register_text(lbl_beta, "β 参数：", "β parameter:")
    owner.levin_beta_spin = QDoubleSpinBox()
    owner.levin_beta_spin.setRange(0.01, 100.0)
    owner.levin_beta_spin.setValue(1.0)
    owner.levin_beta_spin.setSingleStep(0.1)
    owner.levin_beta_spin.setDecimals(2)
    owner.levin_beta_spin.setToolTip(
        owner._tr(
            "权重函数 ω(n) = 1/(n+β) 中的 β 参数",
            "β parameter in weight function ω(n) = 1/(n+β)",
        )
    )
    levin_layout.addRow(lbl_beta, owner.levin_beta_spin)
    lbl_beta.setVisible(False)
    owner.levin_beta_spin.setVisible(False)
    owner.levin_beta_label = lbl_beta

    owner.richardson_box = QGroupBox("Richardson 序列加速参数")
    owner._register_title(owner.richardson_box, "Richardson 序列加速参数", "Richardson acceleration parameters")
    richardson_layout = QFormLayout(owner.richardson_box)

    lbl_richardson_p = QLabel("收敛幂指数 p：")
    owner._register_text(lbl_richardson_p, "收敛幂指数 p：", "Convergence power p:")
    owner.richardson_p_spin = QDoubleSpinBox()
    owner.richardson_p_spin.setRange(0.1, 10.0)
    owner.richardson_p_spin.setValue(2.0)
    owner.richardson_p_spin.setSingleStep(0.1)
    owner.richardson_p_spin.setDecimals(2)
    owner.richardson_p_spin.setToolTip(
        owner._tr(
            "误差展开的幂指数（f(h) ≈ f∞ + c·h^p），常见值 p=2（二阶方法）",
            "Power exponent in error expansion (f(h) ≈ f∞ + c·h^p), common value p=2 (second-order method)",
        )
    )
    richardson_layout.addRow(lbl_richardson_p, owner.richardson_p_spin)

    owner.extrap_method_stack.addWidget(owner.power_box)
    owner.extrap_method_stack.addWidget(owner.levin_box)
    owner.extrap_method_stack.addWidget(owner.richardson_box)
    owner.extrap_method_stack.addWidget(owner.custom_formula_widget)
    extrap_layout.addWidget(owner.extrap_method_stack)

    uncert_layout = QHBoxLayout()
    lbl_uncert = QLabel("不确定度参考列：")
    owner._register_text(lbl_uncert, "不确定度参考列：", "Uncertainty ref column:")
    uncert_layout.addWidget(lbl_uncert)
    owner.uncertainty_combo = QComboBox()
    owner._refresh_uncertainty_selector(["A", "B", "C"])
    uncert_layout.addWidget(owner.uncertainty_combo)
    refresh_uncert_btn = QPushButton("刷新")
    refresh_uncert_btn.setToolTip(
        owner._tr(
            "重新扫描数据以列出可选的不确定度参考列。",
            "Rescan data to list available uncertainty columns.",
        )
    )
    owner._register_text(refresh_uncert_btn, "刷新", "Refresh")
    refresh_uncert_btn.clicked.connect(owner._refresh_uncertainty_from_source)
    owner.uncertainty_refresh_btn = refresh_uncert_btn
    uncert_layout.addWidget(refresh_uncert_btn)
    extrap_layout.addLayout(uncert_layout)

    _bind_extrapolation_schema_fields(
        owner,
        method_label=method_label,
        lbl_custom=lbl_custom,
        power_x_labels=power_x_labels,
        lbl_p=lbl_p,
        lbl_seed=lbl_seed,
        lbl_variant=lbl_variant,
        lbl_order=lbl_order,
        lbl_weight=lbl_weight,
        lbl_beta=lbl_beta,
        lbl_richardson_p=lbl_richardson_p,
        lbl_uncert=lbl_uncert,
        combo_items=combo_items,
    )
    return extrap_box


def _bind_extrapolation_schema_fields(
    owner: Any,
    *,
    method_label: QLabel,
    lbl_custom: QLabel,
    power_x_labels: list[QLabel],
    lbl_p: QLabel,
    lbl_seed: QLabel,
    lbl_variant: QLabel,
    lbl_order: QLabel,
    lbl_weight: QLabel,
    lbl_beta: QLabel,
    lbl_richardson_p: QLabel,
    lbl_uncert: QLabel,
    combo_items: list[tuple[str, str, str]],
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    method_field = FormFieldSpec(
        key="extrapolation.method",
        widget_kind="select",
        label=LocalizedText("外推方法：", "Method:"),
        tooltip=LocalizedText(
            "选择外推算法。不同方法会显示对应的参数设置。",
            "Choose the extrapolation algorithm. Different methods show their relevant parameter settings.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in combo_items
        ],
    )
    method_help_field = FormFieldSpec(
        key="extrapolation.method",
        widget_kind="button",
        label=LocalizedText("外推方法帮助", "Extrapolation method help"),
        tooltip=LocalizedText(
            "点击查看当前外推方法的详细说明、适用场景和参数解释。",
            "Click to view detailed description, applicable scenarios, and parameter explanations for the current method.",
        ),
        required=False,
    )
    custom_formula_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="textarea",
        label=LocalizedText("自定义公式：", "Custom formula:"),
        placeholder=LocalizedText(
            "示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
            "Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
        ),
        tooltip=LocalizedText(
            "输入自定义三点外推公式。可使用 A/B/C、列名或 x1/x2/x3，并支持数学函数。",
            "Enter a custom three-point extrapolation formula. Use A/B/C, column names, or x1/x2/x3; math functions are supported.",
        ),
        required=True,
    )
    custom_formula_preview_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="button",
        label=LocalizedText("预览公式", "Preview formula"),
        tooltip=LocalizedText(
            "打开渲染后的自定义外推公式预览。",
            "Open a rendered preview of the custom extrapolation formula.",
        ),
        required=False,
    )
    custom_functions_field = FormFieldSpec(
        key="extrapolation.custom.functions",
        widget_kind="button",
        label=LocalizedText("函数支持", "Functions"),
        tooltip=LocalizedText(
            "查看自定义外推公式支持的函数和表达式语法。",
            "View supported functions and expression syntax for custom extrapolation formulas.",
        ),
        required=False,
    )
    power_x_fields = [
        FormFieldSpec(
            key=f"extrapolation.power_law.x{idx}",
            widget_kind="text",
            label=LocalizedText(f"x{idx}：", f"x{idx}:"),
            tooltip=LocalizedText(
                f"幂律三点外推的第 {idx} 个自变量值。",
                f"Input x value {idx} for three-point power-law extrapolation.",
            ),
            required=True,
        )
        for idx in range(1, 4)
    ]
    power_p_field = FormFieldSpec(
        key="extrapolation.power_law.p",
        widget_kind="text",
        label=LocalizedText("自定义 p（可选）：", "Custom p (optional):"),
        placeholder=LocalizedText("留空则自动求解 p", "Leave blank to solve p automatically"),
        tooltip=LocalizedText(
            "可选幂指数。留空时由程序根据数据自动求解。",
            "Optional power exponent. Leave blank for automatic solving from the data.",
        ),
        required=False,
    )
    power_seed_field = FormFieldSpec(
        key="extrapolation.power_law.seed_guesses",
        widget_kind="text",
        label=LocalizedText("p 种子列表（可选）：", "p seed list (optional):"),
        placeholder=LocalizedText("如 0.5, 1, 2, -1", "e.g. 0.5, 1, 2, -1"),
        tooltip=LocalizedText(
            "用于自动求解 p 的候选初值，多个值用逗号分隔。",
            "Candidate initial guesses for solving p automatically, separated by commas.",
        ),
        required=False,
    )
    levin_variant_field = FormFieldSpec(
        key="extrapolation.levin.variant",
        widget_kind="select",
        label=LocalizedText("变换类型：", "Variant:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[0].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[0].tooltip_en,
        ),
        required=True,
        choices=[
            ChoiceSpec(value="u", label=LocalizedText("u (最常用)", "u (most common)")),
            ChoiceSpec(value="t", label=LocalizedText("t (级数)", "t (series)")),
            ChoiceSpec(value="v", label=LocalizedText("v (积分)", "v (integrals)")),
        ],
    )
    levin_order_field = FormFieldSpec(
        key="extrapolation.levin.order",
        widget_kind="number",
        label=LocalizedText("变换阶数：", "Transform order:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[1].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[1].tooltip_en,
        ),
        required=True,
    )
    levin_weight_field = FormFieldSpec(
        key="extrapolation.levin.weight",
        widget_kind="select",
        label=LocalizedText("权重函数：", "Weight function:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[2].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[2].tooltip_en,
        ),
        required=True,
        choices=[
            ChoiceSpec(value="default", label=LocalizedText("默认 (1)", "Default (1)")),
            ChoiceSpec(value="reciprocal", label=LocalizedText("1/(n+1)", "1/(n+1)")),
            ChoiceSpec(value="reciprocal_beta", label=LocalizedText("1/(n+β)", "1/(n+β)")),
        ],
    )
    levin_beta_field = FormFieldSpec(
        key="extrapolation.levin.beta",
        widget_kind="number",
        label=LocalizedText("β 参数：", "β parameter:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[3].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[3].tooltip_en,
        ),
        required=False,
    )
    richardson_p_field = FormFieldSpec(
        key="extrapolation.richardson.p",
        widget_kind="number",
        label=LocalizedText("收敛幂指数 p：", "Convergence power p:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["richardson"].parameter_groups[0].parameters[0].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["richardson"].parameter_groups[0].parameters[0].tooltip_en,
        ),
        required=True,
    )
    uncertainty_field = FormFieldSpec(
        key="extrapolation.uncertainty.reference_column",
        widget_kind="select",
        label=LocalizedText("不确定度参考列：", "Uncertainty ref column:"),
        tooltip=LocalizedText(
            "重新扫描数据以列出可选的不确定度参考列。",
            "Rescan data to list available uncertainty columns.",
        ),
        required=False,
    )
    uncertainty_refresh_field = FormFieldSpec(
        key="extrapolation.uncertainty.reference_column",
        widget_kind="button",
        label=LocalizedText("刷新不确定度列", "Refresh uncertainty columns"),
        tooltip=LocalizedText(
            "重新扫描数据以列出可选的不确定度参考列。",
            "Rescan data to list available uncertainty columns.",
        ),
        required=False,
    )

    bind_field(field=method_field, label=method_label, widget=owner.method_combo, lang=lang)
    bind_choices(owner.method_combo, method_field.choices, lang=lang)
    register_schema_text_refresh(owner, method_field, widget=owner.method_combo)
    bind_field(field=method_help_field, help_button=owner.method_help_btn, lang=lang)
    register_schema_text_refresh(owner, method_help_field, help_button=owner.method_help_btn)
    bind_field(
        field=custom_formula_field,
        label=lbl_custom,
        widget=owner.custom_formula_edit,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        custom_formula_field,
        widget=owner.custom_formula_edit,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_custom, custom_formula_field)
    bind_schema_command_button(
        owner,
        owner.custom_formula_preview_button,
        field=custom_formula_preview_field,
        accessible_name=LocalizedText("预览公式", "Preview formula"),
        lang=lang,
    )
    bind_field(field=custom_functions_field, widget=owner.custom_formula_function_button, lang=lang)
    register_schema_text_refresh(owner, custom_functions_field, widget=owner.custom_formula_function_button)
    for field, label, edit in zip(power_x_fields, power_x_labels, owner.power_x_edits, strict=True):
        bind_field(field=field, label=label, widget=edit, lang=lang)
        register_schema_text_refresh(owner, field, widget=edit)
    bind_field(field=power_p_field, label=lbl_p, widget=owner.power_p_edit, lang=lang)
    register_schema_text_refresh(owner, power_p_field, widget=owner.power_p_edit)
    bind_field(field=power_seed_field, label=lbl_seed, widget=owner.power_seed_guesses_edit, lang=lang)
    register_schema_text_refresh(owner, power_seed_field, widget=owner.power_seed_guesses_edit)
    bind_field(field=levin_variant_field, label=lbl_variant, widget=owner.levin_variant_combo, lang=lang)
    bind_choices(owner.levin_variant_combo, levin_variant_field.choices, lang=lang)
    register_schema_text_refresh(owner, levin_variant_field, widget=owner.levin_variant_combo)
    bind_field(field=levin_order_field, label=lbl_order, widget=owner.levin_order_spin, lang=lang)
    register_schema_text_refresh(owner, levin_order_field, widget=owner.levin_order_spin)
    bind_field(field=levin_weight_field, label=lbl_weight, widget=owner.levin_weight_combo, lang=lang)
    bind_choices(owner.levin_weight_combo, levin_weight_field.choices, lang=lang)
    register_schema_text_refresh(owner, levin_weight_field, widget=owner.levin_weight_combo)
    bind_field(field=levin_beta_field, label=lbl_beta, widget=owner.levin_beta_spin, lang=lang)
    register_schema_text_refresh(owner, levin_beta_field, widget=owner.levin_beta_spin)
    bind_field(field=richardson_p_field, label=lbl_richardson_p, widget=owner.richardson_p_spin, lang=lang)
    register_schema_text_refresh(owner, richardson_p_field, widget=owner.richardson_p_spin)
    bind_field(
        field=uncertainty_field,
        label=lbl_uncert,
        widget=owner.uncertainty_combo,
        lang=lang,
    )
    register_schema_text_refresh(owner, uncertainty_field, widget=owner.uncertainty_combo)
    bind_schema_command_button(
        owner,
        owner.uncertainty_refresh_btn,
        field=uncertainty_refresh_field,
        accessible_name=LocalizedText("刷新不确定度列", "Refresh uncertainty columns"),
        lang=lang,
    )


__all__ = ["build_extrapolation_mode_view"]
