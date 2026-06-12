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
from app_desktop.parameter_table import ParameterTable
from app_desktop.schema_widgets import make_editor_header
from app_desktop.theme import workbench_warning_text_style
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import register_schema_text_refresh
from app_desktop.views import helpers as view_helpers
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText


def build_fitting_mode_view(owner: Any) -> QGroupBox:
    # Fitting module
    owner.fit_box = QGroupBox("拟合模块")
    owner.fit_box.setProperty("datalab_view_module", "app_desktop.views.fitting")
    owner._register_title(owner.fit_box, "拟合模块", "Fitting")
    fit_layout = QVBoxLayout(owner.fit_box)
    model_row = QHBoxLayout()
    lbl_model = QLabel("拟合模型：")
    owner._register_text(lbl_model, "拟合模型：", "Model:")
    model_row.addWidget(lbl_model)
    owner.fit_model_combo = QComboBox()
    owner.fit_model_combo.addItem("自定义模型（非线性）", "custom")
    owner.fit_model_combo.addItem("自洽隐式模型", "self_consistent")
    owner.fit_model_combo.addItem("多项式拟合", "polynomial")
    owner.fit_model_combo.addItem("1/x^p 展开", "inverse_power")
    owner.fit_model_combo.addItem("Padé 拟合", "pade")
    owner.fit_model_combo.addItem("幂律极限拟合", "power_limit")
    fit_items = [
        ("自定义模型（非线性）", "Custom (nonlinear)", "custom"),
        ("自洽隐式模型", "Self-consistent / implicit", "self_consistent"),
        ("多项式拟合", "Polynomial", "polynomial"),
        ("1/x^p 展开", "1/x^p series", "inverse_power"),
        ("Padé 拟合", "Padé", "pade"),
        ("幂律极限拟合", "Power limit", "power_limit"),
    ]
    owner._register_combo(owner.fit_model_combo, fit_items)
    owner.fit_model_combo.currentIndexChanged.connect(owner._on_model_type_changed)
    model_row.addWidget(owner.fit_model_combo)
    fit_layout.addLayout(model_row)

    # MCMC refinement opt-in (Phase 3 #12). Placed in the fit panel
    # so users discover it when selecting a model — not buried in
    # a menu. Disabled with an explanatory tooltip when emcee is
    # missing, so the feature is discoverable but un-breakable.
    owner.fit_mcmc_refine = QCheckBox(owner._tr(
        "MCMC 精炼（拟合后运行）",
        "Refine with MCMC (after fit)",
    ))
    owner._register_text(
        owner.fit_mcmc_refine,
        "MCMC 精炼（拟合后运行）",
        "Refine with MCMC (after fit)",
    )
    owner.fit_mcmc_refine.setChecked(False)
    try:
        from fitting.mcmc_fitter import HAS_EMCEE as _mcmc_has_emcee
    except ImportError:
        # Only ImportError is caught — any other error (SyntaxError,
        # NameError from a bad refactor, etc.) should propagate so
        # the maintainer sees the real bug instead of a mysteriously
        # disabled checkbox.
        owner.fit_mcmc_refine.setEnabled(False)
        owner.fit_mcmc_refine.setToolTip(owner._tr(
            "MCMC 精炼不可用（fitting.mcmc_fitter 未安装）。"
            "pip install emcee numpy corner",
            "MCMC refinement unavailable — fitting.mcmc_fitter "
            "is not importable. pip install emcee numpy corner",
        ))
        owner._register_text(
            owner.fit_mcmc_refine,
            "MCMC 精炼不可用（fitting.mcmc_fitter 未安装）。pip install emcee numpy corner",
            "MCMC refinement unavailable — fitting.mcmc_fitter is not importable. pip install emcee numpy corner",
            "setToolTip",
        )
    else:
        if not _mcmc_has_emcee:
            owner.fit_mcmc_refine.setEnabled(False)
            owner.fit_mcmc_refine.setToolTip(owner._tr(
                "需要安装 emcee 包才能启用 MCMC 精炼。"
                "pip install emcee numpy corner",
                "Install the 'emcee' package to enable MCMC "
                "refinement. pip install emcee numpy corner",
            ))
            owner._register_text(
                owner.fit_mcmc_refine,
                "需要安装 emcee 包才能启用 MCMC 精炼。pip install emcee numpy corner",
                "Install the 'emcee' package to enable MCMC refinement. pip install emcee numpy corner",
                "setToolTip",
            )
        else:
            owner.fit_mcmc_refine.setToolTip(owner._tr(
                "对最佳 AIC 模型的参数后验分布做 MCMC 采样，"
                "给出更可靠的置信区间（可能耗时 10–60 秒）。",
                "Run emcee MCMC on the best-AIC model to produce "
                "robust credible intervals (may take 10–60 s).",
            ))
            owner._register_text(
                owner.fit_mcmc_refine,
                "对最佳 AIC 模型的参数后验分布做 MCMC 采样，给出更可靠的置信区间（可能耗时 10–60 秒）。",
                "Run emcee MCMC on the best-AIC model to produce robust credible intervals (may take 10–60 s).",
                "setToolTip",
            )
    fit_layout.addWidget(owner.fit_mcmc_refine)

    owner.fit_model_hint = QLabel("")
    owner.fit_model_hint.setStyleSheet(workbench_warning_text_style())
    owner.fit_model_hint.setWordWrap(True)
    owner.fit_model_hint.hide()
    fit_layout.addWidget(owner.fit_model_hint)

    owner.inverse_power_widget = QWidget()
    inverse_layout = QHBoxLayout(owner.inverse_power_widget)
    inverse_layout.setContentsMargins(0, 0, 0, 0)
    lbl_inv_min = QLabel("min p：")
    owner._register_text(lbl_inv_min, "min p：", "min p:")
    inverse_layout.addWidget(lbl_inv_min)
    owner.inverse_min_spin = QSpinBox()
    owner.inverse_min_spin.setRange(0, 12)
    owner.inverse_min_spin.setValue(1)
    inverse_layout.addWidget(owner.inverse_min_spin)
    lbl_inv_max = QLabel("max p：")
    owner._register_text(lbl_inv_max, "max p：", "max p:")
    inverse_layout.addWidget(lbl_inv_max)
    owner.inverse_max_spin = QSpinBox()
    owner.inverse_max_spin.setRange(0, 18)
    owner.inverse_max_spin.setValue(3)
    inverse_layout.addWidget(owner.inverse_max_spin)
    inverse_layout.addStretch()
    fit_layout.addWidget(owner.inverse_power_widget)
    owner.inverse_power_widget.hide()

    owner.pade_widget = QWidget()
    pade_layout = QHBoxLayout(owner.pade_widget)
    pade_layout.setContentsMargins(0, 0, 0, 0)
    lbl_pade_m = QLabel("Padé m：")
    owner._register_text(lbl_pade_m, "Padé m：", "Padé m:")
    pade_layout.addWidget(lbl_pade_m)
    owner.pade_m_spin = QSpinBox()
    owner.pade_m_spin.setRange(0, 6)
    owner.pade_m_spin.setValue(1)
    pade_layout.addWidget(owner.pade_m_spin)
    lbl_pade_n = QLabel("n：")
    owner._register_text(lbl_pade_n, "n：", "n:")
    pade_layout.addWidget(lbl_pade_n)
    owner.pade_n_spin = QSpinBox()
    owner.pade_n_spin.setRange(0, 6)
    owner.pade_n_spin.setValue(1)
    pade_layout.addWidget(owner.pade_n_spin)
    pade_layout.addStretch()
    fit_layout.addWidget(owner.pade_widget)
    owner.pade_widget.hide()

    owner.poly_degree_widget = QWidget()
    poly_layout = QHBoxLayout(owner.poly_degree_widget)
    poly_layout.setContentsMargins(0, 0, 0, 0)
    lbl_poly_deg = QLabel("多项式最高阶：")
    owner._register_text(lbl_poly_deg, "多项式最高阶：", "Polynomial degree:")
    poly_layout.addWidget(lbl_poly_deg)
    owner.poly_degree_spin = QSpinBox()
    owner.poly_degree_spin.setRange(1, 18)
    owner.poly_degree_spin.setValue(max(3, owner._baseline_poly_degree))
    poly_layout.addWidget(owner.poly_degree_spin)
    poly_layout.addStretch()
    fit_layout.addWidget(owner.poly_degree_widget)
    owner.poly_degree_widget.hide()

    owner.fit_formula_preview_button = view_helpers.make_formula_preview_button(owner, None, lhs="y", title="Preview formula")
    fit_expr_header_field = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        tooltip=LocalizedText(
            "输入自定义拟合表达式。留空不会使用示例。",
            "Enter the custom fitting expression. Leaving it blank does not use the example.",
        ),
        required=True,
    )
    fit_expr_header = make_editor_header(
        owner,
        fit_expr_header_field,
        preview_button=owner.fit_formula_preview_button,
    )
    lbl_fit_expr = fit_expr_header.schema_label
    fit_layout.addWidget(fit_expr_header)
    owner.fit_expr_edit = QPlainTextEdit("")
    owner.fit_expr_edit.setPlaceholderText("自定义模型表达式，例如 A*x**(-p) + C / Custom model expression")
    fit_layout.addWidget(owner.fit_expr_edit)
    owner.fit_formula_preview_button.clicked.connect(
        lambda: view_helpers.open_formula_preview(owner, owner.fit_expr_edit, lhs="y")
    )
    fit_expr_hint_row = QHBoxLayout()
    fit_expr_hint_row.setContentsMargins(0, 0, 0, 0)
    fit_expr_hint_row.setSpacing(6)
    owner.fit_func_help_btn = QPushButton("函数支持")
    owner.fit_func_help_btn.setFlat(True)
    owner.fit_func_help_btn.setFocusPolicy(Qt.NoFocus)
    owner.fit_func_help_btn.setToolTip("")  # will be set in _update_placeholders_language
    owner.fit_func_help_btn.clicked.connect(owner._show_error_functions)
    owner._register_text(owner.fit_func_help_btn, "函数支持", "Functions")
    fit_expr_hint_row.addWidget(owner.fit_func_help_btn)
    fit_expr_hint_row.addStretch()
    fit_layout.addLayout(fit_expr_hint_row)
    owner.custom_constants_editor = ConstantsEditor(min_rows=3, checked=False, numeric_mode="mpmath")
    owner._register_text(owner.custom_constants_editor.checkbox, "启用常数设置", "Enable constants")
    owner._register_text(
        owner.custom_constants_editor.checkbox,
        "启用后在自定义拟合表达式中代入常数，并从参数识别中排除这些名称。",
        "Enable constants for the custom fit expression and exclude those names from parameter detection.",
        "setToolTip",
    )
    view_helpers.register_constant_headers(owner, owner.custom_constants_editor.set_table_headers)
    view_helpers.apply_equal_column_stretch(owner.custom_constants_editor.table_view)
    owner.custom_constants_editor.table_view.setStyleSheet(view_helpers.get_table_style())
    owner.custom_constants_editor.table_view.setMinimumHeight(120)
    custom_param_header = QHBoxLayout()
    lbl_custom_params = QLabel("参数列表：")
    owner._register_text(lbl_custom_params, "参数列表：", "Parameters:")
    custom_param_header.addWidget(lbl_custom_params)
    custom_param_header.addStretch()
    owner.custom_param_refresh_btn = QPushButton("识别参数")
    owner._register_text(owner.custom_param_refresh_btn, "识别参数", "Detect")
    owner.custom_param_refresh_btn.clicked.connect(owner._refresh_custom_parameter_rows)
    custom_param_header.addWidget(owner.custom_param_refresh_btn)
    owner.custom_param_add_btn = QPushButton("+ 行")
    owner._register_text(owner.custom_param_add_btn, "+ 行", "+ Row")
    owner.custom_param_add_btn.clicked.connect(lambda: view_helpers.add_parameter_table_row(owner.custom_params_table))
    custom_param_header.addWidget(owner.custom_param_add_btn)
    owner.custom_param_remove_btn = QPushButton("- 行")
    owner._register_text(owner.custom_param_remove_btn, "- 行", "- Row")
    owner.custom_param_remove_btn.clicked.connect(lambda: view_helpers.remove_parameter_table_rows(owner.custom_params_table))
    custom_param_header.addWidget(owner.custom_param_remove_btn)
    custom_param_header.setContentsMargins(0, 0, 0, 0)
    custom_param_header_widget = QWidget()
    custom_param_header_widget.setLayout(custom_param_header)
    owner.custom_param_header_widget = custom_param_header_widget
    fit_layout.addWidget(custom_param_header_widget)
    owner.custom_constraints_checkbox = QCheckBox("启用参数约束")
    owner.custom_constraints_checkbox.setChecked(False)
    owner._register_text(owner.custom_constraints_checkbox, "启用参数约束", "Enable parameter constraints")
    owner._register_text(
        owner.custom_constraints_checkbox,
        "启用后参数表显示固定、下界和上界列。",
        "Show fixed, lower-bound, and upper-bound columns in the parameter table.",
        "setToolTip",
    )
    fit_layout.addWidget(owner.custom_constraints_checkbox)
    owner.custom_params_table = ParameterTable()
    view_helpers.register_table_headers(
        owner,
        owner.custom_params_table.set_headers,
        ("名称", "初值", "固定", "下界", "上界"),
        ("Name", "Init", "Fixed", "Min", "Max"),
    )
    owner.custom_params_table.table_view.setMinimumHeight(150)
    owner.custom_params_table.table_view.setStyleSheet(view_helpers.get_table_style())
    view_helpers.apply_equal_column_stretch(owner.custom_params_table.table_view)
    owner.custom_constraints_checkbox.toggled.connect(owner.custom_params_table.set_constraints_enabled)
    fit_layout.addWidget(owner.custom_params_table)
    fit_layout.addWidget(owner.custom_constants_editor)

    owner.implicit_model_widget = QGroupBox("自洽隐式模型")
    owner._register_title(owner.implicit_model_widget, "自洽隐式模型", "Self-consistent / implicit")
    implicit_layout = QVBoxLayout(owner.implicit_model_widget)

    owner.implicit_equation_edit = QPlainTextEdit("")
    owner.implicit_equation_edit.setMinimumHeight(84)
    owner.implicit_equation_edit.setPlaceholderText("示例：a + b*Cos[u] + c*x / Example: a + b*Cos[u] + c*x")
    owner.implicit_equation_preview_button = view_helpers.make_formula_preview_button(
        owner,
        owner.implicit_equation_edit,
        lhs=lambda: owner.implicit_variable_edit.text(),
        title="Preview equation",
        object_name="implicit_equation_preview_button",
        tooltip_zh="预览方程",
    )
    implicit_equation_header_field = FormFieldSpec(
        key="fitting.implicit.equation",
        widget_kind="textarea",
        label=LocalizedText("自洽方程：", "Self-consistent equation:"),
        tooltip=LocalizedText(
            "输入自洽方程。留空不会使用示例。",
            "Enter the self-consistent equation. Leaving it blank does not use the example.",
        ),
        required=True,
    )
    implicit_equation_header = make_editor_header(
        owner,
        implicit_equation_header_field,
        preview_button=owner.implicit_equation_preview_button,
    )
    lbl_implicit_eq = implicit_equation_header.schema_label
    implicit_layout.addWidget(implicit_equation_header)
    implicit_layout.addWidget(owner.implicit_equation_edit)

    owner.implicit_output_edit = QPlainTextEdit("")
    owner.implicit_output_edit.setMinimumHeight(84)
    owner.implicit_output_edit.setPlaceholderText("示例：u / Example: u")
    owner.implicit_output_preview_button = view_helpers.make_formula_preview_button(
        owner,
        owner.implicit_output_edit,
        lhs="y",
        title="Preview output",
        object_name="implicit_output_preview_button",
        tooltip_zh="预览输出",
    )
    implicit_output_header_field = FormFieldSpec(
        key="fitting.implicit.output_expression",
        widget_kind="textarea",
        label=LocalizedText("输出表达式：", "Output expression:"),
        tooltip=LocalizedText(
            "输入由隐式变量和输入变量计算目标列的输出表达式。",
            "Enter the output expression that maps the implicit and input variables to the target column.",
        ),
        required=True,
    )
    implicit_output_header = make_editor_header(
        owner,
        implicit_output_header_field,
        preview_button=owner.implicit_output_preview_button,
    )
    lbl_implicit_output = implicit_output_header.schema_label
    implicit_layout.addWidget(implicit_output_header)
    implicit_layout.addWidget(owner.implicit_output_edit)

    implicit_param_header = QHBoxLayout()
    lbl_implicit_params = QLabel("参数列表：")
    owner._register_text(lbl_implicit_params, "参数列表：", "Parameters:")
    implicit_param_header.addWidget(lbl_implicit_params)
    implicit_param_header.addStretch()
    owner.implicit_param_refresh_btn = QPushButton("识别参数")
    owner._register_text(owner.implicit_param_refresh_btn, "识别参数", "Detect")
    owner.implicit_param_refresh_btn.clicked.connect(owner._refresh_implicit_parameter_rows)
    implicit_param_header.addWidget(owner.implicit_param_refresh_btn)
    owner.implicit_param_add_btn = QPushButton("+ 行")
    owner._register_text(owner.implicit_param_add_btn, "+ 行", "+ Row")
    owner.implicit_param_add_btn.clicked.connect(lambda: view_helpers.add_parameter_table_row(owner.implicit_params_table))
    implicit_param_header.addWidget(owner.implicit_param_add_btn)
    owner.implicit_param_remove_btn = QPushButton("- 行")
    owner._register_text(owner.implicit_param_remove_btn, "- 行", "- Row")
    owner.implicit_param_remove_btn.clicked.connect(lambda: view_helpers.remove_parameter_table_rows(owner.implicit_params_table))
    implicit_param_header.addWidget(owner.implicit_param_remove_btn)
    implicit_param_header.setContentsMargins(0, 0, 0, 0)
    implicit_param_header_widget = QWidget()
    implicit_param_header_widget.setLayout(implicit_param_header)
    owner.implicit_param_header_widget = implicit_param_header_widget
    implicit_layout.addWidget(implicit_param_header_widget)

    owner.implicit_params_table = ParameterTable()
    view_helpers.register_table_headers(
        owner,
        owner.implicit_params_table.set_headers,
        ("名称", "初值", "固定", "下界", "上界"),
        ("Name", "Init", "Fixed", "Min", "Max"),
    )
    owner.implicit_params_table.table_view.setMinimumHeight(150)
    owner.implicit_params_table.table_view.setStyleSheet(view_helpers.get_table_style())
    view_helpers.apply_equal_column_stretch(owner.implicit_params_table.table_view)
    implicit_layout.addWidget(owner.implicit_params_table)

    owner.implicit_constraints_checkbox = QCheckBox("启用参数约束")
    owner.implicit_constraints_checkbox.setChecked(False)
    owner._register_text(owner.implicit_constraints_checkbox, "启用参数约束", "Enable parameter constraints")
    owner._register_text(
        owner.implicit_constraints_checkbox,
        "启用后参数表显示固定、下界和上界列。",
        "Show fixed, lower-bound, and upper-bound columns in the parameter table.",
        "setToolTip",
    )
    owner.implicit_constraints_checkbox.toggled.connect(owner.implicit_params_table.set_constraints_enabled)
    implicit_layout.addWidget(owner.implicit_constraints_checkbox)

    owner.implicit_constants_editor = ConstantsEditor(min_rows=3, checked=True, numeric_mode="mpmath")
    owner._register_text(owner.implicit_constants_editor.checkbox, "启用常数设置", "Enable constants")
    owner._register_text(
        owner.implicit_constants_editor.checkbox,
        "启用后在自洽隐式模型中代入常数，并从参数识别中排除这些名称。",
        "Enable constants for the implicit model and exclude those names from parameter detection.",
        "setToolTip",
    )
    view_helpers.register_constant_headers(owner, owner.implicit_constants_editor.set_table_headers)
    view_helpers.apply_equal_column_stretch(owner.implicit_constants_editor.table_view)
    owner.implicit_constants_editor.table_view.setStyleSheet(view_helpers.get_table_style())
    owner.implicit_constants_editor.table_view.setMinimumHeight(120)
    implicit_layout.addWidget(owner.implicit_constants_editor)

    implicit_basic_layout = QFormLayout()
    owner.implicit_variable_edit = QLineEdit("u")
    lbl_implicit_var = QLabel("隐式变量：")
    owner._register_text(lbl_implicit_var, "隐式变量：", "Implicit variable:")
    implicit_basic_layout.addRow(lbl_implicit_var, owner.implicit_variable_edit)
    implicit_layout.addLayout(implicit_basic_layout)

    implicit_solver_layout = QFormLayout()
    owner.implicit_initial_edit = QLineEdit("0.3")
    lbl_implicit_initial = QLabel("初始值：")
    owner._register_text(lbl_implicit_initial, "初始值：", "Initial:")
    implicit_solver_layout.addRow(lbl_implicit_initial, owner.implicit_initial_edit)
    owner.implicit_tolerance_edit = QLineEdit("1e-30")
    lbl_implicit_tol = QLabel("求解容差：")
    owner._register_text(lbl_implicit_tol, "求解容差：", "Tolerance:")
    implicit_solver_layout.addRow(lbl_implicit_tol, owner.implicit_tolerance_edit)
    owner.implicit_max_iterations_spin = QSpinBox()
    owner.implicit_max_iterations_spin.setRange(1, 10000)
    owner.implicit_max_iterations_spin.setValue(80)
    lbl_implicit_iter = QLabel("最大迭代：")
    owner._register_text(lbl_implicit_iter, "最大迭代：", "Max iterations:")
    implicit_solver_layout.addRow(lbl_implicit_iter, owner.implicit_max_iterations_spin)
    owner.implicit_method_combo = QComboBox()
    implicit_method_items = [
        ("固定点", "Fixed point", "fixed_point"),
        ("求根", "Root", "root"),
    ]
    for zh, en, data in implicit_method_items:
        owner.implicit_method_combo.addItem(zh, data)
    owner._register_combo(owner.implicit_method_combo, implicit_method_items)
    lbl_implicit_method = QLabel("求解方法：")
    owner._register_text(lbl_implicit_method, "求解方法：", "Method:")
    implicit_solver_layout.addRow(lbl_implicit_method, owner.implicit_method_combo)
    owner.implicit_timeout_spin = QSpinBox()
    owner.implicit_timeout_spin.setRange(0, 86400)
    owner.implicit_timeout_spin.setValue(300)
    owner.implicit_timeout_spin.setToolTip(owner._tr("0 表示不自动超时，只能手动停止。", "0 disables automatic timeout; use Stop to cancel."))
    lbl_implicit_timeout = QLabel("最长运行秒数：")
    owner._register_text(lbl_implicit_timeout, "最长运行秒数：", "Max runtime (s):")
    implicit_solver_layout.addRow(lbl_implicit_timeout, owner.implicit_timeout_spin)
    implicit_layout.addLayout(implicit_solver_layout)
    fit_layout.addWidget(owner.implicit_model_widget)
    owner.implicit_model_widget.hide()
    _bind_fitting_schema_fields(
        owner,
        lbl_model=lbl_model,
        fit_items=fit_items,
        lbl_fit_expr=lbl_fit_expr,
        lbl_implicit_eq=lbl_implicit_eq,
        lbl_implicit_output=lbl_implicit_output,
        lbl_implicit_var=lbl_implicit_var,
        lbl_implicit_initial=lbl_implicit_initial,
        lbl_implicit_tol=lbl_implicit_tol,
        lbl_implicit_iter=lbl_implicit_iter,
        lbl_implicit_method=lbl_implicit_method,
        implicit_method_items=implicit_method_items,
        lbl_implicit_timeout=lbl_implicit_timeout,
        lbl_custom_params=lbl_custom_params,
        lbl_implicit_params=lbl_implicit_params,
    )

    var_header = QHBoxLayout()
    lbl_varmap = QLabel("变量映射：")
    owner._register_text(lbl_varmap, "变量映射：", "Variable mapping:")
    var_header.addWidget(lbl_varmap)
    var_header.addStretch()
    owner.add_variable_btn = QPushButton("+")
    owner.add_variable_btn.setFixedWidth(28)
    owner.add_variable_btn.setToolTip(owner._tr("添加变量映射", "Add variable mapping"))
    owner._register_text(owner.add_variable_btn, "添加变量映射", "Add variable mapping", "setToolTip")
    owner.add_variable_btn.clicked.connect(owner._add_variable_row)
    var_header.addWidget(owner.add_variable_btn)
    owner.remove_variable_btn = QPushButton("-")
    owner.remove_variable_btn.setFixedWidth(28)
    owner.remove_variable_btn.setToolTip(owner._tr("删除最后一个变量映射", "Remove last variable mapping"))
    owner._register_text(
        owner.remove_variable_btn,
        "删除最后一个变量映射",
        "Remove last variable mapping",
        "setToolTip",
    )
    owner.remove_variable_btn.clicked.connect(owner._remove_variable_row)
    var_header.addWidget(owner.remove_variable_btn)
    fit_layout.addLayout(var_header)

    owner.variable_rows: list[tuple[QLineEdit, QLineEdit, QWidget]] = []
    owner.variable_name_pool = ["x", "y", "z", "u", "v", "w"]
    owner.variable_rows_layout = QVBoxLayout()
    fit_layout.addLayout(owner.variable_rows_layout)
    owner._reset_variable_rows(default_var="x", default_column="A")

    target_row = QHBoxLayout()
    lbl_target = QLabel("目标列：")
    owner._register_text(lbl_target, "目标列：", "Target column:")
    target_row.addWidget(lbl_target)
    owner.fit_target_edit = QLineEdit("B")
    owner._register_text(
        owner.fit_target_edit,
        "目标列是拟合时要匹配的观测数据列。",
        "Target column is the observed data column matched by the fit.",
        "setToolTip",
    )
    target_row.addWidget(owner.fit_target_edit)
    fit_layout.addLayout(target_row)

    weight_row = QHBoxLayout()
    lbl_weight_mode = QLabel("统计/系统：")
    owner._register_text(lbl_weight_mode, "统计/系统：", "Stat./System:")
    weight_row.addWidget(lbl_weight_mode)
    owner.fit_weighted_checkbox = QCheckBox("统计误差加权")
    owner._register_text(owner.fit_weighted_checkbox, "统计误差加权", "Statistical weighting (sigma)")
    owner._register_text(
        owner.fit_weighted_checkbox,
        "启用后使用目标列中的统计不确定度作为拟合权重。",
        "Use statistical uncertainties in the target column as fit weights when enabled.",
        "setToolTip",
    )
    weight_row.addWidget(owner.fit_weighted_checkbox)
    fit_layout.addLayout(weight_row)

    owner.inverse_min_spin.valueChanged.connect(owner._on_model_settings_changed)
    owner.inverse_max_spin.valueChanged.connect(owner._on_model_settings_changed)
    owner.pade_m_spin.valueChanged.connect(owner._on_model_settings_changed)
    owner.pade_n_spin.valueChanged.connect(owner._on_model_settings_changed)
    owner.poly_degree_spin.valueChanged.connect(owner._on_model_settings_changed)
    return owner.fit_box


def _bind_fitting_schema_fields(
    owner,
    *,
    lbl_model: QLabel,
    fit_items: list[tuple[str, str, str]],
    lbl_fit_expr: QLabel,
    lbl_implicit_eq: QLabel,
    lbl_implicit_output: QLabel,
    lbl_implicit_var: QLabel,
    lbl_implicit_initial: QLabel,
    lbl_implicit_tol: QLabel,
    lbl_implicit_iter: QLabel,
    lbl_implicit_method: QLabel,
    implicit_method_items: list[tuple[str, str, str]],
    lbl_implicit_timeout: QLabel,
    lbl_custom_params: QLabel,
    lbl_implicit_params: QLabel,
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    fit_model_field = FormFieldSpec(
        key="fitting.model",
        widget_kind="select",
        label=LocalizedText("拟合模型：", "Model:"),
        tooltip=LocalizedText(
            "选择拟合模型。自定义模型允许编辑表达式；其他模型会显示只读预览。",
            "Choose the fitting model. Custom models allow expression editing; other models show read-only previews.",
        ),
        required=True,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in fit_items],
    )
    custom_expression_field = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        placeholder=LocalizedText("示例：A*x**(-p) + C", "Example: A*x**(-p) + C"),
        tooltip=LocalizedText(
            "输入自定义拟合表达式。留空不会使用示例；示例只显示在背景提示中。",
            "Enter the custom fitting expression. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    custom_constants_field = FormFieldSpec(
        key="fitting.custom.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "可选常数表。启用后，常数名会从参数识别和拟合参数中排除。",
            "Optional constants table. When enabled, constant names are excluded from parameter detection and fit parameters.",
        ),
        required=False,
    )
    custom_params_field = FormFieldSpec(
        key="fitting.custom.parameters",
        widget_kind="table",
        label=LocalizedText("参数列表：", "Parameters:"),
        tooltip=LocalizedText(
            "自定义模型参数及初值、固定值和约束。",
            "Custom model parameters with initial values, fixed values, and constraints.",
        ),
        required=False,
    )
    implicit_equation_field = FormFieldSpec(
        key="fitting.implicit.equation",
        widget_kind="textarea",
        label=LocalizedText("自洽方程：", "Self-consistent equation:"),
        placeholder=LocalizedText("示例：a + b*Cos[u] + c*x", "Example: a + b*Cos[u] + c*x"),
        tooltip=LocalizedText(
            "输入自洽方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter the self-consistent equation. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    implicit_output_field = FormFieldSpec(
        key="fitting.implicit.output_expression",
        widget_kind="textarea",
        label=LocalizedText("输出表达式：", "Output expression:"),
        placeholder=LocalizedText("示例：u", "Example: u"),
        tooltip=LocalizedText(
            "输入由隐式变量和输入变量计算目标列的输出表达式。",
            "Enter the output expression that maps the implicit and input variables to the target column.",
        ),
        required=True,
    )
    implicit_variable_field = FormFieldSpec(
        key="fitting.implicit.variable",
        widget_kind="text",
        label=LocalizedText("隐式变量：", "Implicit variable:"),
        tooltip=LocalizedText("自洽方程中要求解的变量名。", "Variable solved by the self-consistent equation."),
        required=True,
    )
    implicit_initial_field = FormFieldSpec(
        key="fitting.implicit.initial",
        widget_kind="text",
        label=LocalizedText("初始值：", "Initial:"),
        tooltip=LocalizedText("隐式变量求解初值。", "Initial value for solving the implicit variable."),
        required=True,
    )
    implicit_tolerance_field = FormFieldSpec(
        key="fitting.implicit.tolerance",
        widget_kind="text",
        label=LocalizedText("求解容差：", "Tolerance:"),
        tooltip=LocalizedText("隐式变量求解容差。", "Tolerance for solving the implicit variable."),
        required=True,
    )
    implicit_iterations_field = FormFieldSpec(
        key="fitting.implicit.max_iterations",
        widget_kind="number",
        label=LocalizedText("最大迭代：", "Max iterations:"),
        tooltip=LocalizedText("每次隐式变量求解允许的最大迭代次数。", "Maximum iterations allowed for each implicit solve."),
        required=True,
    )
    implicit_method_field = FormFieldSpec(
        key="fitting.implicit.method",
        widget_kind="select",
        label=LocalizedText("求解方法：", "Method:"),
        tooltip=LocalizedText(
            "固定点用于 u=g(...) 形式；求根用于 F(...)=0 形式。",
            "Fixed point is for u=g(...) forms; Root is for F(...)=0 forms.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in implicit_method_items
        ],
    )
    implicit_timeout_field = FormFieldSpec(
        key="fitting.implicit.timeout_seconds",
        widget_kind="number",
        label=LocalizedText("最长运行秒数：", "Max runtime (s):"),
        tooltip=LocalizedText(
            "0 表示不自动超时，只能手动停止。",
            "0 disables automatic timeout; use Stop to cancel.",
        ),
        required=True,
    )
    implicit_constants_field = FormFieldSpec(
        key="fitting.implicit.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "可选常数表。启用后，常数名会从隐式参数识别和拟合参数中排除。",
            "Optional constants table. When enabled, constant names are excluded from implicit parameter detection and fit parameters.",
        ),
        required=False,
    )
    implicit_params_field = FormFieldSpec(
        key="fitting.implicit.parameters",
        widget_kind="table",
        label=LocalizedText("参数列表：", "Parameters:"),
        tooltip=LocalizedText(
            "自洽隐式模型参数及初值、固定值和约束。",
            "Self-consistent implicit model parameters with initial values, fixed values, and constraints.",
        ),
        required=False,
    )

    bind_field(field=fit_model_field, label=lbl_model, widget=owner.fit_model_combo, lang=lang)
    bind_choices(owner.fit_model_combo, fit_model_field.choices, lang=lang)
    bind_field(
        field=custom_expression_field,
        label=lbl_fit_expr,
        widget=owner.fit_expr_edit,
        help_button=owner.fit_formula_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        custom_expression_field,
        widget=owner.fit_expr_edit,
        help_button=owner.fit_formula_preview_button,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_fit_expr, custom_expression_field)
    bind_field(field=custom_constants_field, widget=owner.custom_constants_editor, lang=lang)
    bind_field(field=custom_params_field, label=lbl_custom_params, widget=owner.custom_params_table, lang=lang)
    bind_field(
        field=implicit_equation_field,
        label=lbl_implicit_eq,
        widget=owner.implicit_equation_edit,
        help_button=owner.implicit_equation_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        implicit_equation_field,
        widget=owner.implicit_equation_edit,
        help_button=owner.implicit_equation_preview_button,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_implicit_eq, implicit_equation_field)
    bind_field(
        field=implicit_output_field,
        label=lbl_implicit_output,
        widget=owner.implicit_output_edit,
        help_button=owner.implicit_output_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        implicit_output_field,
        widget=owner.implicit_output_edit,
        help_button=owner.implicit_output_preview_button,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_implicit_output, implicit_output_field)
    bind_field(field=implicit_variable_field, label=lbl_implicit_var, widget=owner.implicit_variable_edit, lang=lang)
    bind_field(field=implicit_initial_field, label=lbl_implicit_initial, widget=owner.implicit_initial_edit, lang=lang)
    bind_field(field=implicit_tolerance_field, label=lbl_implicit_tol, widget=owner.implicit_tolerance_edit, lang=lang)
    bind_field(field=implicit_iterations_field, label=lbl_implicit_iter, widget=owner.implicit_max_iterations_spin, lang=lang)
    bind_field(field=implicit_method_field, label=lbl_implicit_method, widget=owner.implicit_method_combo, lang=lang)
    bind_choices(owner.implicit_method_combo, implicit_method_field.choices, lang=lang)
    bind_field(field=implicit_timeout_field, label=lbl_implicit_timeout, widget=owner.implicit_timeout_spin, lang=lang)
    bind_field(field=implicit_constants_field, widget=owner.implicit_constants_editor, lang=lang)
    bind_field(field=implicit_params_field, label=lbl_implicit_params, widget=owner.implicit_params_table, lang=lang)



__all__ = ["build_fitting_mode_view"]
