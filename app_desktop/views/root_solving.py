from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from app_desktop.detected_rows_table import DetectedRowsTable
from app_desktop.formula_preview import open_formula_preview_dialog
from app_desktop.schema_widgets import make_editor_header
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import register_schema_text_refresh
from app_desktop.views import helpers as view_helpers
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText


def build_root_solving_mode_view(owner: Any) -> QGroupBox:
    section = view_helpers.make_workbench_section_card_view(
        owner,
        object_name="root_solving_mode_view",
        view_module="app_desktop.views.root_solving",
        card_object_name="root_solving_settings_card",
        role="root_solving",
        title_zh="求根",
        title_en="Root solving",
        description_zh="设置求解模式和根的不确定度传播。",
        description_en="Configure solve mode and root uncertainty propagation.",
    )
    root_box = section.host
    root_layout = section.card_layout

    owner.root_equations_help_button = view_helpers.make_small_help_button()
    owner.root_formula_preview_button = view_helpers.make_formula_preview_button(
        owner,
        None,
        title="Preview equations",
        object_name="root_formula_preview_button",
        tooltip_zh="预览方程",
    )
    owner.root_formula_preview_button.clicked.connect(lambda: open_root_formula_preview(owner))
    root_equation_header_field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        tooltip=LocalizedText(
            "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    root_equation_header = make_editor_header(
        owner,
        root_equation_header_field,
        preview_button=owner.root_formula_preview_button,
        help_button=owner.root_equations_help_button,
    )
    lbl_root_equations = root_equation_header.schema_label
    root_layout.addWidget(root_equation_header)

    owner.root_equations_edit = QPlainTextEdit()
    owner.root_equations_edit.setMinimumHeight(96)
    owner.root_equations_edit.setPlaceholderText(
        "每行一个方程，按 F_i(...)=0 求解；示例：x^2 - A / One equation per line as F_i(...)=0; example: x^2 - A"
    )
    root_layout.addWidget(owner.root_equations_edit)

    root_mode_layout = QFormLayout()
    owner.root_mode_combo = QComboBox()
    root_mode_items = [
        ("标量", "Scalar", "scalar"),
        ("扫描多根", "Scan multiple roots", "scan_multiple"),
        ("多项式", "Polynomial", "polynomial"),
        ("方程组", "System", "system"),
    ]
    for zh, _en, data in root_mode_items:
        owner.root_mode_combo.addItem(zh, data)
    owner._register_combo(owner.root_mode_combo, root_mode_items)
    lbl_root_mode = QLabel("求解模式：")
    owner._register_text(lbl_root_mode, "求解模式：", "Solve mode:")
    root_mode_row = QHBoxLayout()
    root_mode_row.addWidget(owner.root_mode_combo)
    owner.root_mode_help_button = view_helpers.make_small_help_button()
    root_mode_row.addWidget(owner.root_mode_help_button)
    root_mode_row.addStretch()
    root_mode_layout.addRow(lbl_root_mode, root_mode_row)
    root_layout.addLayout(root_mode_layout)

    root_unknown_header = QHBoxLayout()
    lbl_root_unknowns = QLabel("未知量：")
    owner._register_text(lbl_root_unknowns, "未知量：", "Unknowns:")
    root_unknown_header.addWidget(lbl_root_unknowns)
    owner.root_unknowns_help_button = view_helpers.make_small_help_button()
    root_unknown_header.addWidget(owner.root_unknowns_help_button)
    root_unknown_header.addStretch()
    owner.root_detect_unknowns_button = QPushButton("识别未知量")
    owner._register_text(owner.root_detect_unknowns_button, "识别未知量", "Detect")
    owner.root_detect_unknowns_button.setToolTip(owner._tr("从方程中识别未知量", "Detect unknowns from equations"))
    owner.root_detect_unknowns_button.clicked.connect(owner._refresh_root_unknown_rows)
    root_unknown_header.addWidget(owner.root_detect_unknowns_button)
    owner.root_add_unknown_button = QPushButton("+ 行")
    owner._register_text(owner.root_add_unknown_button, "+ 行", "+ Row")
    owner.root_add_unknown_button.setToolTip(owner._tr("手动添加未知量行", "Add an unknown row"))
    owner.root_add_unknown_button.clicked.connect(
        lambda: view_helpers.add_detected_rows_table_row(owner, "root_unknowns_table")
    )
    root_unknown_header.addWidget(owner.root_add_unknown_button)
    owner.root_remove_unknown_button = QPushButton("- 行")
    owner._register_text(owner.root_remove_unknown_button, "- 行", "- Row")
    owner.root_remove_unknown_button.setToolTip(owner._tr("删除选中的未知量行", "Remove selected unknown rows"))
    owner.root_remove_unknown_button.clicked.connect(
        lambda: view_helpers.remove_detected_rows_table_rows(owner, "root_unknowns_table")
    )
    root_unknown_header.addWidget(owner.root_remove_unknown_button)
    root_unknown_header.setContentsMargins(0, 0, 0, 0)
    root_unknown_header_widget = QWidget()
    root_unknown_header_widget.setLayout(root_unknown_header)
    owner.root_unknown_header_widget = root_unknown_header_widget
    root_layout.addWidget(root_unknown_header_widget)

    owner.root_unknowns_table = DetectedRowsTable(
        columns=("name", "initial", "lower", "upper"),
        headers=("名称", "初始值", "下界", "上界"),
        min_rows=2,
    )
    view_helpers.register_table_headers(
        owner,
        owner.root_unknowns_table.set_headers,
        ("名称", "初始值", "下界", "上界"),
        ("Name", "Initial", "Lower", "Upper"),
    )
    owner.root_unknowns_table.table_view.setMinimumHeight(140)
    owner.root_unknowns_table.table_view.setStyleSheet(view_helpers.get_table_style())
    view_helpers.apply_equal_column_stretch(owner.root_unknowns_table.table_view)
    root_layout.addWidget(owner.root_unknowns_table)

    view_helpers.register_constant_headers(owner, owner.root_constants_editor.set_table_headers)
    view_helpers.apply_equal_column_stretch(owner.root_constants_editor.table_view)
    owner.root_constants_editor.table_view.setStyleSheet(view_helpers.get_table_style())
    owner.root_constants_editor.table_view.setMinimumHeight(120)
    root_layout.addWidget(
        view_helpers.make_display_unit_controls(
            owner,
            attr_prefix="root",
            schema_prefix="root_solving",
            input_tooltip_zh="输入数据列的单位。符号使用批处理数据列名，例如 A。",
            input_tooltip_en="Units for input data columns. Symbols use batch data column names, such as A.",
            include_constants=True,
            constants_tooltip_zh="求根常数的单位。符号必须与输入常数名一致。",
            constants_tooltip_en="Units for root-solving constants. Symbols must match input constant names.",
            output_label_zh="根 result 单位：",
            output_label_en="Root result unit:",
            output_tooltip_zh="可选。用于根结果、LaTeX 和根图中的单位显示；不改变求解算法。",
            output_tooltip_en="Optional. Used for root result, LaTeX, and root plot labels; it does not change solving.",
        )
    )
    _bind_root_schema_fields(owner, lbl_root_equations, lbl_root_mode, lbl_root_unknowns, root_mode_items)
    refresh_root_field_help(owner)

    owner.root_uncertainty_group = QGroupBox("根的不确定度传播")
    owner._register_title(owner.root_uncertainty_group, "根的不确定度传播", "Root uncertainty propagation")
    root_uncertainty_layout = QFormLayout(owner.root_uncertainty_group)
    owner.root_uncertainty_method_combo = QComboBox()
    root_uncertainty_method_items = [
        ("Taylor（偏导）", "Taylor (derivative)", "taylor"),
        ("Monte Carlo", "Monte Carlo", "monte_carlo"),
        ("关闭", "Off", "off"),
    ]
    for zh, _en, data in root_uncertainty_method_items:
        owner.root_uncertainty_method_combo.addItem(zh, data)
    owner._register_combo(owner.root_uncertainty_method_combo, root_uncertainty_method_items)
    owner._register_text(
        owner.root_uncertainty_method_combo,
        "选择根的不确定度传播方式；关闭时只求数值根。",
        "Choose how root uncertainties are propagated; Off solves numeric roots only.",
        "setToolTip",
    )
    lbl_root_uncertainty_method = QLabel("方法：")
    owner._register_text(lbl_root_uncertainty_method, "方法：", "Method:")
    root_uncertainty_layout.addRow(lbl_root_uncertainty_method, owner.root_uncertainty_method_combo)

    owner.root_uncertainty_taylor_widget = QWidget()
    root_taylor_layout = QHBoxLayout(owner.root_uncertainty_taylor_widget)
    root_taylor_layout.setContentsMargins(0, 0, 0, 0)
    root_taylor_layout.setSpacing(6)
    owner.root_uncertainty_order_label = QLabel("阶数：")
    owner._register_text(owner.root_uncertainty_order_label, "阶数：", "Order:")
    owner.root_uncertainty_order_spin = QSpinBox()
    owner.root_uncertainty_order_spin.setRange(1, 2)
    owner.root_uncertainty_order_spin.setValue(1)
    owner.root_uncertainty_order_spin.setToolTip(
        owner._tr(
            "1 阶：隐函数线性传播；2 阶：对标量实根使用二阶有限差分传播。",
            "Order 1: linear implicit propagation; order 2: scalar second-order finite-difference propagation.",
        )
    )
    owner._register_text(
        owner.root_uncertainty_order_spin,
        "1 阶：隐函数线性传播；2 阶：对标量实根使用二阶有限差分传播。",
        "Order 1: linear implicit propagation; order 2: scalar second-order finite-difference propagation.",
        "setToolTip",
    )
    root_taylor_layout.addWidget(owner.root_uncertainty_order_label)
    root_taylor_layout.addWidget(owner.root_uncertainty_order_spin)
    root_taylor_layout.addStretch()
    root_uncertainty_layout.addRow("", owner.root_uncertainty_taylor_widget)

    owner.root_monte_carlo_samples_label = QLabel("样本数：")
    owner._register_text(owner.root_monte_carlo_samples_label, "样本数：", "Samples:")
    owner.root_monte_carlo_samples_spin = QSpinBox()
    owner.root_monte_carlo_samples_spin.setRange(100, 50000)
    owner.root_monte_carlo_samples_spin.setValue(2000)
    owner._register_text(
        owner.root_monte_carlo_samples_spin,
        "Monte Carlo 抽样次数；数值越大越稳定但越慢。",
        "Monte Carlo sample count; larger values are more stable but slower.",
        "setToolTip",
    )
    root_uncertainty_layout.addRow(owner.root_monte_carlo_samples_label, owner.root_monte_carlo_samples_spin)

    owner.root_monte_carlo_seed_label = QLabel("随机种子：")
    owner._register_text(owner.root_monte_carlo_seed_label, "随机种子：", "Seed:")
    owner.root_monte_carlo_seed_edit = QLineEdit()
    root_uncertainty_layout.addRow(owner.root_monte_carlo_seed_label, owner.root_monte_carlo_seed_edit)

    owner.root_uncertainty_method_help_label = QLabel()
    owner.root_uncertainty_method_help_label.setWordWrap(True)
    root_uncertainty_layout.addRow(owner.root_uncertainty_method_help_label)
    owner.root_uncertainty_method_combo.currentIndexChanged.connect(
        lambda _index: on_root_uncertainty_method_changed(owner)
    )
    root_layout.addWidget(owner.root_uncertainty_group)
    on_root_uncertainty_method_changed(owner)
    return root_box


def open_root_formula_preview(owner: Any) -> None:
    lines = [
        line.strip()
        for line in owner.root_equations_edit.toPlainText().splitlines()
        if line.strip()
    ]
    if not lines:
        expression = ""
        lhs = "F"
    elif len(lines) == 1:
        expression = lines[0]
        lhs = "F"
    else:
        expression = "\n".join(lines)
        lhs = "F_i"
    open_formula_preview_dialog(owner, expression, lhs)


def _bind_root_schema_fields(
    owner: Any,
    lbl_root_equations: QLabel,
    lbl_root_mode: QLabel,
    lbl_root_unknowns: QLabel,
    root_mode_items: list[tuple[str, str, object]],
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    root_equations_field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        placeholder=LocalizedText(
            "每行一个方程，按 F_i(...)=0 求解；示例：x^2 - A",
            "One equation per line as F_i(...)=0; example: x^2 - A",
        ),
        tooltip=LocalizedText(
            "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    root_mode_field = FormFieldSpec(
        key="root.mode",
        widget_kind="select",
        label=LocalizedText("求解模式：", "Solve mode:"),
        tooltip=LocalizedText(
            "标量：单未知量单根；扫描多根：从区间/采样查找多个根；多项式：一元多项式根；方程组：多个未知量联立求解。",
            "Scalar: one unknown and one root; Scan multiple: search multiple roots by interval/sampling; Polynomial: univariate polynomial roots; System: solve coupled equations.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in root_mode_items
        ],
    )
    root_unknowns_field = FormFieldSpec(
        key="root.unknowns",
        widget_kind="table",
        label=LocalizedText("未知量：", "Unknowns:"),
        tooltip=LocalizedText(
            "不同模式需要的列不同：标量通常填名称和初始值；扫描多根还可填下界/上界；多项式可只填名称；方程组每个未知量一行。",
            "Columns depend on mode: scalar usually needs name and initial; scan can use lower/upper; polynomial can use only name; system uses one row per unknown.",
        ),
        required=True,
    )
    bind_field(
        field=root_equations_field,
        label=lbl_root_equations,
        widget=owner.root_equations_edit,
        help_button=owner.root_equations_help_button,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        root_equations_field,
        widget=owner.root_equations_edit,
        help_button=owner.root_equations_help_button,
    )
    view_helpers.register_schema_label_refresh(owner, lbl_root_equations, root_equations_field)
    bind_field(
        field=root_mode_field,
        label=lbl_root_mode,
        widget=owner.root_mode_combo,
        help_button=owner.root_mode_help_button,
        lang=lang,
    )
    bind_choices(owner.root_mode_combo, root_mode_field.choices, lang=lang)
    bind_field(
        field=root_unknowns_field,
        label=lbl_root_unknowns,
        widget=owner.root_unknowns_table,
        help_button=owner.root_unknowns_help_button,
        lang=lang,
    )


def refresh_root_field_help(owner: Any) -> None:
    is_en = bool(getattr(owner, "_is_en", lambda: False)())
    unknown_headers = (
        ("Name", "Initial", "Lower", "Upper")
        if is_en
        else ("名称", "初始值", "下界", "上界")
    )
    constants_headers = ("Name", "Value") if is_en else ("名称", "值")
    unknowns_table = getattr(owner, "root_unknowns_table", None)
    if unknowns_table is not None:
        unknowns_table.set_headers(unknown_headers)
        unknowns_table.setToolTip(
            owner._tr(
                "未知量表：名称为要求解的变量；初始值用于数值迭代；下界/上界可选，仅部分求解器使用。不同模式可只填写需要的列。",
                "Unknowns table: Name is the variable to solve; Initial seeds numeric iteration; Lower/Upper are optional and used only by supported solvers. Fill only the columns needed by the selected mode.",
            )
        )
    constants_editor = getattr(owner, "root_constants_editor", None)
    if constants_editor is not None:
        constants_editor.set_table_headers(*constants_headers)
        constants_tooltip = owner._tr(
            "常数设置：填写方程中的固定量，支持 1.23(4) 和 1.23(4)[-5] 这类不确定度写法；非空常数会自动代入。",
            "Constants: fixed quantities used by equations; accepts uncertainty notation such as 1.23(4) and 1.23(4)[-5]; non-empty constants are substituted automatically.",
        )
        constants_editor.setToolTip(constants_tooltip)
        if hasattr(constants_editor, "help_button"):
            constants_editor.help_button.setToolTip(constants_tooltip)
        if hasattr(constants_editor, "checkbox"):
            constants_editor.checkbox.setToolTip(constants_tooltip)
    tooltip_pairs = (
        (
            "root_equations_help_button",
            "方程按 F(...)=0 求解；可写多行方程组。示例：x^2 - A。",
            "Equations are solved as F(...)=0; use multiple lines for a system. Example: x^2 - A.",
        ),
        (
            "root_mode_help_button",
            "标量：单未知量单根；扫描多根：从区间/采样查找多个根；多项式：一元多项式根；方程组：多个未知量联立求解。",
            "Scalar: one unknown and one root; Scan multiple: search multiple roots by interval/sampling; Polynomial: univariate polynomial roots; System: solve coupled equations.",
        ),
        (
            "root_unknowns_help_button",
            "不同模式需要的列不同：标量通常填名称和初始值；扫描多根还可填下界/上界；多项式可只填名称；方程组每个未知量一行。",
            "Columns depend on mode: scalar usually needs name and initial; scan can use lower/upper; polynomial can use only name; system uses one row per unknown.",
        ),
    )
    for attr, zh, en in tooltip_pairs:
        widget = getattr(owner, attr, None)
        if widget is not None:
            widget.setToolTip(owner._tr(zh, en))
    if hasattr(owner, "root_equations_edit"):
        owner.root_equations_edit.setToolTip(
            owner._tr(
                "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
                "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
            )
        )
    if hasattr(owner, "root_mode_combo"):
        owner.root_mode_combo.setToolTip(getattr(owner, "root_mode_help_button", owner.root_mode_combo).toolTip())
    button_tooltips = {
        "root_detect_unknowns_button": (
            "按当前方程、数据列和常数重新识别未知量；已删除的已识别行会被移除。",
            "Detect unknowns from the current equations, data columns, and constants; removed detected symbols are removed from the table.",
        ),
        "root_add_unknown_button": (
            "手动添加未知量行，用于补充或覆盖自动识别。",
            "Add an unknown row manually to supplement or override detection.",
        ),
        "root_remove_unknown_button": (
            "删除选中的未知量行。",
            "Remove selected unknown rows.",
        ),
    }
    for attr, (zh, en) in button_tooltips.items():
        widget = getattr(owner, attr, None)
        if widget is not None:
            widget.setToolTip(owner._tr(zh, en))


def on_root_uncertainty_method_changed(owner: Any) -> None:
    method = str(owner.root_uncertainty_method_combo.currentData() or "taylor")
    show_monte_carlo = method == "monte_carlo"
    show_taylor = method == "taylor"
    taylor_widget = getattr(owner, "root_uncertainty_taylor_widget", None)
    if taylor_widget is not None:
        taylor_widget.setVisible(show_taylor)
    for widget_name in (
        "root_monte_carlo_samples_label",
        "root_monte_carlo_samples_spin",
        "root_monte_carlo_seed_label",
        "root_monte_carlo_seed_edit",
    ):
        widget = getattr(owner, widget_name, None)
        if widget is not None:
            widget.setVisible(show_monte_carlo)

    help_text = {
        "off": owner._tr("不传播输入不确定度。", "Input uncertainty is not propagated."),
        "taylor": owner._tr("使用 Taylor 传播；阶数由阶数控件设置。", "Uses Taylor propagation; order is set by the order control."),
        "monte_carlo": owner._tr("对输入不确定度抽样后重新求根。", "Resolves roots from sampled uncertain inputs."),
    }.get(method, "")
    owner.root_uncertainty_method_help_label.setText(help_text)


__all__ = [
    "build_root_solving_mode_view",
    "on_root_uncertainty_method_changed",
    "refresh_root_field_help",
]
