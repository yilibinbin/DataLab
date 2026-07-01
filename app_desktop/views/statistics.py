from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import register_schema_text_refresh
from app_desktop.views import helpers as view_helpers
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText


def build_statistics_mode_view(owner: Any) -> QGroupBox:
    section = view_helpers.make_workbench_section_card_view(
        owner,
        object_name="statistics_mode_view",
        view_module="app_desktop.views.statistics",
        card_object_name="statistics_settings_card",
        role="statistics",
        title_zh="统计设置",
        title_en="Statistics settings",
        description_zh="选择一个或多个数值列、可选的不确定度列，以及平均方式。",
        description_en="Choose one or more value columns, optional sigma column, and averaging mode.",
    )
    stats_box = section.host
    stats_box.setProperty("datalab_statistics_panel", True)
    card_layout = section.card_layout

    stats_layout = QFormLayout()
    stats_layout.setContentsMargins(0, 0, 0, 0)
    stats_layout.setSpacing(8)
    stats_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    stats_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    owner.stats_workflow_combo = QComboBox()
    workflow_items = [
        ("常规统计", "Standard statistics", "standard"),
        ("协方差/相关矩阵", "Covariance/correlation matrix", "covariance_correlation"),
        ("分组统计", "Grouped statistics", "grouped_statistics"),
        ("Bootstrap 置信区间", "Bootstrap confidence intervals", "bootstrap_confidence_intervals"),
        ("假设检验", "Hypothesis tests", "hypothesis_tests"),
        ("时间序列/滚动统计", "Time-series / rolling", "time_series_rolling"),
    ]
    for zh, _en, data in workflow_items:
        owner.stats_workflow_combo.addItem(zh, data)
    owner._register_combo(owner.stats_workflow_combo, workflow_items)
    lbl_stats_workflow = QLabel("工作流：")
    owner._register_text(lbl_stats_workflow, "工作流：", "Workflow:")
    stats_layout.addRow(lbl_stats_workflow, owner.stats_workflow_combo)

    owner.stats_value_column_edit = QLineEdit("A")
    lbl_stats_value = QLabel("数值列：")
    owner._register_text(lbl_stats_value, "数值列：", "Value columns:")
    stats_layout.addRow(lbl_stats_value, owner.stats_value_column_edit)

    owner.stats_group_column_edit = QLineEdit("")
    lbl_stats_group = QLabel("分组列：")
    owner._register_text(lbl_stats_group, "分组列：", "Group column:")
    owner.stats_group_column_label = lbl_stats_group
    stats_layout.addRow(lbl_stats_group, owner.stats_group_column_edit)

    owner.stats_sigma_column_edit = QLineEdit("")
    lbl_stats_sigma = QLabel("不确定度列（可选）：")
    owner._register_text(lbl_stats_sigma, "不确定度列（可选）：", "Sigma column (optional):")
    owner.stats_sigma_column_label = lbl_stats_sigma
    stats_layout.addRow(lbl_stats_sigma, owner.stats_sigma_column_edit)

    owner.stats_mode_combo = QComboBox()
    stats_items = [
        ("算术平均", "Arithmetic mean", "mean"),
        ("描述统计", "Descriptive statistics", "descriptive"),
        ("加权平均（σ 加权）", "Weighted mean (σ)", "weighted_sigma"),
    ]
    for zh, _en, data in stats_items:
        owner.stats_mode_combo.addItem(zh, data)
    owner._register_combo(owner.stats_mode_combo, stats_items)
    lbl_stats_type = QLabel("统计类型：")
    owner._register_text(lbl_stats_type, "统计类型：", "Statistics type:")
    owner.stats_mode_label = lbl_stats_type
    stats_layout.addRow(lbl_stats_type, owner.stats_mode_combo)

    owner.stats_bootstrap_target_combo = QComboBox()
    bootstrap_target_items = [
        ("均值", "Mean", "mean"),
        ("中位数", "Median", "median"),
        ("修剪均值", "Trimmed mean", "trimmed_mean"),
        ("标准差", "Standard deviation", "std"),
        ("方差", "Variance", "variance"),
    ]
    for zh, _en, data in bootstrap_target_items:
        owner.stats_bootstrap_target_combo.addItem(zh, data)
    owner._register_combo(owner.stats_bootstrap_target_combo, bootstrap_target_items)
    lbl_bootstrap_target = QLabel("Bootstrap 目标：")
    owner._register_text(lbl_bootstrap_target, "Bootstrap 目标：", "Bootstrap target:")
    owner.stats_bootstrap_target_label = lbl_bootstrap_target
    stats_layout.addRow(lbl_bootstrap_target, owner.stats_bootstrap_target_combo)

    owner.stats_bootstrap_confidence_edit = QLineEdit("0.95")
    owner.stats_bootstrap_confidence_edit.setReadOnly(True)
    lbl_bootstrap_confidence = QLabel("置信水平：")
    owner._register_text(lbl_bootstrap_confidence, "置信水平：", "Confidence level:")
    owner.stats_bootstrap_confidence_label = lbl_bootstrap_confidence
    stats_layout.addRow(lbl_bootstrap_confidence, owner.stats_bootstrap_confidence_edit)

    owner.stats_bootstrap_resamples_spin = QSpinBox()
    owner.stats_bootstrap_resamples_spin.setRange(100, 100000)
    owner.stats_bootstrap_resamples_spin.setValue(2000)
    lbl_bootstrap_resamples = QLabel("重采样次数：")
    owner._register_text(lbl_bootstrap_resamples, "重采样次数：", "Resamples:")
    owner.stats_bootstrap_resamples_label = lbl_bootstrap_resamples
    stats_layout.addRow(lbl_bootstrap_resamples, owner.stats_bootstrap_resamples_spin)

    owner.stats_bootstrap_seed_edit = QLineEdit("")
    lbl_bootstrap_seed = QLabel("随机种子：")
    owner._register_text(lbl_bootstrap_seed, "随机种子：", "Seed:")
    owner.stats_bootstrap_seed_label = lbl_bootstrap_seed
    stats_layout.addRow(lbl_bootstrap_seed, owner.stats_bootstrap_seed_edit)

    owner.stats_hypothesis_test_combo = QComboBox()
    hypothesis_test_items = [
        ("单样本 t 检验", "One-sample t-test", "one_sample_t"),
        ("配对 t 检验", "Paired t-test", "paired_t"),
        ("Welch t 检验", "Welch t-test", "welch_t"),
        ("精确符号检验", "Exact sign test", "sign_test"),
        ("卡方拟合优度", "Chi-square goodness-of-fit", "chi_square_gof"),
    ]
    for zh, _en, data in hypothesis_test_items:
        owner.stats_hypothesis_test_combo.addItem(zh, data)
    owner._register_combo(owner.stats_hypothesis_test_combo, hypothesis_test_items)
    lbl_hypothesis_test = QLabel("检验类型：")
    owner._register_text(lbl_hypothesis_test, "检验类型：", "Test kind:")
    owner.stats_hypothesis_test_label = lbl_hypothesis_test
    stats_layout.addRow(lbl_hypothesis_test, owner.stats_hypothesis_test_combo)

    owner.stats_hypothesis_b_column_edit = QLineEdit("B")
    lbl_hypothesis_b_column = QLabel("第二列：")
    owner._register_text(lbl_hypothesis_b_column, "第二列：", "Second column:")
    owner.stats_hypothesis_b_column_label = lbl_hypothesis_b_column
    stats_layout.addRow(lbl_hypothesis_b_column, owner.stats_hypothesis_b_column_edit)

    owner.stats_hypothesis_null_edit = QLineEdit("0")
    lbl_hypothesis_null = QLabel("零假设参数：")
    owner._register_text(lbl_hypothesis_null, "零假设参数：", "Null parameter:")
    owner.stats_hypothesis_null_label = lbl_hypothesis_null
    stats_layout.addRow(lbl_hypothesis_null, owner.stats_hypothesis_null_edit)

    owner.stats_hypothesis_alternative_combo = QComboBox()
    hypothesis_alternative_items = [
        ("双侧", "Two-sided", "two_sided"),
        ("小于", "Less", "less"),
        ("大于", "Greater", "greater"),
    ]
    for zh, _en, data in hypothesis_alternative_items:
        owner.stats_hypothesis_alternative_combo.addItem(zh, data)
    owner._register_combo(owner.stats_hypothesis_alternative_combo, hypothesis_alternative_items)
    lbl_hypothesis_alternative = QLabel("备择假设：")
    owner._register_text(lbl_hypothesis_alternative, "备择假设：", "Alternative:")
    owner.stats_hypothesis_alternative_label = lbl_hypothesis_alternative
    stats_layout.addRow(lbl_hypothesis_alternative, owner.stats_hypothesis_alternative_combo)

    owner.stats_hypothesis_alpha_edit = QLineEdit("0.05")
    lbl_hypothesis_alpha = QLabel("显著性水平 α：")
    owner._register_text(lbl_hypothesis_alpha, "显著性水平 α：", "Significance α:")
    owner.stats_hypothesis_alpha_label = lbl_hypothesis_alpha
    stats_layout.addRow(lbl_hypothesis_alpha, owner.stats_hypothesis_alpha_edit)

    owner.stats_hypothesis_expected_source_combo = QComboBox()
    hypothesis_expected_source_items = [
        ("期望计数", "Expected counts", "counts"),
        ("期望概率", "Expected probabilities", "probabilities"),
    ]
    for zh, _en, data in hypothesis_expected_source_items:
        owner.stats_hypothesis_expected_source_combo.addItem(zh, data)
    owner._register_combo(owner.stats_hypothesis_expected_source_combo, hypothesis_expected_source_items)
    lbl_hypothesis_expected_source = QLabel("期望列类型：")
    owner._register_text(lbl_hypothesis_expected_source, "期望列类型：", "Expected source:")
    owner.stats_hypothesis_expected_source_label = lbl_hypothesis_expected_source
    stats_layout.addRow(lbl_hypothesis_expected_source, owner.stats_hypothesis_expected_source_combo)

    owner.stats_hypothesis_fitted_parameters_spin = QSpinBox()
    owner.stats_hypothesis_fitted_parameters_spin.setRange(0, 100)
    owner.stats_hypothesis_fitted_parameters_spin.setValue(0)
    lbl_hypothesis_fitted_parameters = QLabel("拟合参数数：")
    owner._register_text(lbl_hypothesis_fitted_parameters, "拟合参数数：", "Fitted parameters:")
    owner.stats_hypothesis_fitted_parameters_label = lbl_hypothesis_fitted_parameters
    stats_layout.addRow(lbl_hypothesis_fitted_parameters, owner.stats_hypothesis_fitted_parameters_spin)

    owner.stats_time_series_method_combo = QComboBox()
    time_series_method_items = [
        ("滚动均值", "Rolling mean", "rolling_mean"),
        ("滚动中位数", "Rolling median", "rolling_median"),
        ("滚动标准差", "Rolling standard deviation", "rolling_std"),
        ("指数加权移动平均", "EWMA", "ewma"),
    ]
    for zh, _en, data in time_series_method_items:
        owner.stats_time_series_method_combo.addItem(zh, data)
    owner._register_combo(owner.stats_time_series_method_combo, time_series_method_items)
    lbl_time_series_method = QLabel("序列方法：")
    owner._register_text(lbl_time_series_method, "序列方法：", "Series method:")
    owner.stats_time_series_method_label = lbl_time_series_method
    stats_layout.addRow(lbl_time_series_method, owner.stats_time_series_method_combo)

    owner.stats_time_series_time_column_edit = QLineEdit("")
    lbl_time_series_time_column = QLabel("时间/索引列：")
    owner._register_text(lbl_time_series_time_column, "时间/索引列：", "Time/index column:")
    owner.stats_time_series_time_column_label = lbl_time_series_time_column
    stats_layout.addRow(lbl_time_series_time_column, owner.stats_time_series_time_column_edit)

    owner.stats_time_series_window_size_spin = QSpinBox()
    owner.stats_time_series_window_size_spin.setRange(1, 100000)
    owner.stats_time_series_window_size_spin.setValue(3)
    lbl_time_series_window_size = QLabel("窗口大小：")
    owner._register_text(lbl_time_series_window_size, "窗口大小：", "Window size:")
    owner.stats_time_series_window_size_label = lbl_time_series_window_size
    stats_layout.addRow(lbl_time_series_window_size, owner.stats_time_series_window_size_spin)

    owner.stats_time_series_min_periods_spin = QSpinBox()
    owner.stats_time_series_min_periods_spin.setRange(1, 100000)
    owner.stats_time_series_min_periods_spin.setValue(3)
    lbl_time_series_min_periods = QLabel("最少点数：")
    owner._register_text(lbl_time_series_min_periods, "最少点数：", "Min periods:")
    owner.stats_time_series_min_periods_label = lbl_time_series_min_periods
    stats_layout.addRow(lbl_time_series_min_periods, owner.stats_time_series_min_periods_spin)

    owner.stats_time_series_alignment_combo = QComboBox()
    time_series_alignment_items = [
        ("右对齐", "Right", "right"),
        ("居中", "Center", "center"),
    ]
    for zh, _en, data in time_series_alignment_items:
        owner.stats_time_series_alignment_combo.addItem(zh, data)
    owner._register_combo(owner.stats_time_series_alignment_combo, time_series_alignment_items)
    lbl_time_series_alignment = QLabel("窗口对齐：")
    owner._register_text(lbl_time_series_alignment, "窗口对齐：", "Window alignment:")
    owner.stats_time_series_alignment_label = lbl_time_series_alignment
    stats_layout.addRow(lbl_time_series_alignment, owner.stats_time_series_alignment_combo)

    owner.stats_time_series_denominator_combo = QComboBox()
    time_series_denominator_items = [
        ("样本 (n-1)", "Sample (n-1)", "sample"),
        ("总体 (n)", "Population (n)", "population"),
    ]
    for zh, _en, data in time_series_denominator_items:
        owner.stats_time_series_denominator_combo.addItem(zh, data)
    owner._register_combo(owner.stats_time_series_denominator_combo, time_series_denominator_items)
    lbl_time_series_denominator = QLabel("标准差分母：")
    owner._register_text(lbl_time_series_denominator, "标准差分母：", "Std denominator:")
    owner.stats_time_series_denominator_label = lbl_time_series_denominator
    stats_layout.addRow(lbl_time_series_denominator, owner.stats_time_series_denominator_combo)

    owner.stats_time_series_ewma_parameter_combo = QComboBox()
    time_series_ewma_parameter_items = [
        ("alpha", "alpha", "alpha"),
        ("span", "span", "span"),
    ]
    for zh, _en, data in time_series_ewma_parameter_items:
        owner.stats_time_series_ewma_parameter_combo.addItem(zh, data)
    owner._register_combo(owner.stats_time_series_ewma_parameter_combo, time_series_ewma_parameter_items)
    lbl_time_series_ewma_parameter = QLabel("EWMA 参数：")
    owner._register_text(lbl_time_series_ewma_parameter, "EWMA 参数：", "EWMA parameter:")
    owner.stats_time_series_ewma_parameter_label = lbl_time_series_ewma_parameter
    stats_layout.addRow(lbl_time_series_ewma_parameter, owner.stats_time_series_ewma_parameter_combo)

    owner.stats_time_series_ewma_value_edit = QLineEdit("0.5")
    lbl_time_series_ewma_value = QLabel("EWMA 数值：")
    owner._register_text(lbl_time_series_ewma_value, "EWMA 数值：", "EWMA value:")
    owner.stats_time_series_ewma_value_label = lbl_time_series_ewma_value
    stats_layout.addRow(lbl_time_series_ewma_value, owner.stats_time_series_ewma_value_edit)

    owner.stats_time_series_ewma_adjust_checkbox = QCheckBox("使用 adjust 归一化")
    owner.stats_time_series_ewma_adjust_checkbox.setChecked(False)
    owner._register_text(owner.stats_time_series_ewma_adjust_checkbox, "使用 adjust 归一化", "Use adjusted normalization")
    lbl_time_series_ewma_adjust = QLabel("EWMA adjust：")
    owner._register_text(lbl_time_series_ewma_adjust, "EWMA adjust：", "EWMA adjust:")
    owner.stats_time_series_ewma_adjust_label = lbl_time_series_ewma_adjust
    stats_layout.addRow(lbl_time_series_ewma_adjust, owner.stats_time_series_ewma_adjust_checkbox)

    owner.stats_matrix_missing_policy_combo = QComboBox()
    matrix_missing_policy_items = [
        ("按行删除缺失值", "Listwise deletion", "listwise"),
        ("按对删除缺失值", "Pairwise deletion", "pairwise"),
    ]
    for zh, _en, data in matrix_missing_policy_items:
        owner.stats_matrix_missing_policy_combo.addItem(zh, data)
    owner._register_combo(owner.stats_matrix_missing_policy_combo, matrix_missing_policy_items)
    lbl_matrix_missing_policy = QLabel("缺失值策略：")
    owner._register_text(lbl_matrix_missing_policy, "缺失值策略：", "Missing data:")
    owner.stats_matrix_missing_policy_label = lbl_matrix_missing_policy
    stats_layout.addRow(lbl_matrix_missing_policy, owner.stats_matrix_missing_policy_combo)

    owner.stats_weight_variance_checkbox = QCheckBox("对方差/标准误差使用权重")
    owner.stats_weight_variance_checkbox.setChecked(False)
    owner._register_text(owner.stats_weight_variance_checkbox, "对方差/标准误差使用权重", "Use weights for variance/SE")
    lbl_weight_var = QLabel("方差/标准误差：")
    owner._register_text(lbl_weight_var, "方差/标准误差：", "Variance/SE:")
    owner.stats_weight_variance_label = lbl_weight_var
    stats_layout.addRow(lbl_weight_var, owner.stats_weight_variance_checkbox)

    owner.stats_sample_checkbox = QCheckBox("样本模式 (n-1)")
    owner.stats_sample_checkbox.setChecked(False)
    owner._register_text(owner.stats_sample_checkbox, "样本模式 (n-1)", "Sample mode (n-1)")
    lbl_stats_sample = QLabel("样本/总体：")
    owner._register_text(lbl_stats_sample, "样本/总体：", "Sample/Population:")
    owner.stats_sample_label = lbl_stats_sample
    stats_layout.addRow(lbl_stats_sample, owner.stats_sample_checkbox)

    owner.stats_trim_fraction_edit = QLineEdit("")
    owner.stats_trim_fraction_edit.setPlaceholderText("0.1")
    lbl_trim_fraction = QLabel("修剪比例：")
    owner._register_text(lbl_trim_fraction, "修剪比例：", "Trim fraction:")
    owner.stats_trim_fraction_label = lbl_trim_fraction
    stats_layout.addRow(lbl_trim_fraction, owner.stats_trim_fraction_edit)
    card_layout.addLayout(stats_layout)
    card_layout.addWidget(
        view_helpers.make_display_unit_controls(
            owner,
            attr_prefix="stats",
            schema_prefix="statistics",
            input_tooltip_zh="统计输入列的单位。符号使用数值列名，例如 A 或 B。",
            input_tooltip_en="Units for statistics input columns. Symbols use value column names, such as A or B.",
            output_label_zh="统计 result 单位：",
            output_label_en="Statistics result unit:",
            output_tooltip_zh="可选。用于统计结果、LaTeX 和图中的单位显示；不改变统计计算。",
            output_tooltip_en="Optional. Used for statistics results, LaTeX, and plots; it does not change statistics.",
        )
    )

    _bind_statistics_schema_fields(
        owner,
        lbl_stats_value=lbl_stats_value,
        lbl_stats_group=lbl_stats_group,
        lbl_stats_sigma=lbl_stats_sigma,
        lbl_stats_type=lbl_stats_type,
        lbl_weight_var=lbl_weight_var,
        lbl_stats_sample=lbl_stats_sample,
        lbl_trim_fraction=lbl_trim_fraction,
        lbl_stats_workflow=lbl_stats_workflow,
        lbl_bootstrap_target=lbl_bootstrap_target,
        lbl_bootstrap_confidence=lbl_bootstrap_confidence,
        lbl_bootstrap_resamples=lbl_bootstrap_resamples,
        lbl_bootstrap_seed=lbl_bootstrap_seed,
        lbl_hypothesis_test=lbl_hypothesis_test,
        lbl_hypothesis_b_column=lbl_hypothesis_b_column,
        lbl_hypothesis_null=lbl_hypothesis_null,
        lbl_hypothesis_alternative=lbl_hypothesis_alternative,
        lbl_hypothesis_alpha=lbl_hypothesis_alpha,
        lbl_hypothesis_expected_source=lbl_hypothesis_expected_source,
        lbl_hypothesis_fitted_parameters=lbl_hypothesis_fitted_parameters,
        lbl_time_series_method=lbl_time_series_method,
        lbl_time_series_time_column=lbl_time_series_time_column,
        lbl_time_series_window_size=lbl_time_series_window_size,
        lbl_time_series_min_periods=lbl_time_series_min_periods,
        lbl_time_series_alignment=lbl_time_series_alignment,
        lbl_time_series_denominator=lbl_time_series_denominator,
        lbl_time_series_ewma_parameter=lbl_time_series_ewma_parameter,
        lbl_time_series_ewma_value=lbl_time_series_ewma_value,
        lbl_time_series_ewma_adjust=lbl_time_series_ewma_adjust,
        lbl_matrix_missing_policy=lbl_matrix_missing_policy,
        stats_items=stats_items,
        workflow_items=workflow_items,
        bootstrap_target_items=bootstrap_target_items,
        hypothesis_test_items=hypothesis_test_items,
        hypothesis_alternative_items=hypothesis_alternative_items,
        hypothesis_expected_source_items=hypothesis_expected_source_items,
        time_series_method_items=time_series_method_items,
        time_series_alignment_items=time_series_alignment_items,
        time_series_denominator_items=time_series_denominator_items,
        time_series_ewma_parameter_items=time_series_ewma_parameter_items,
        matrix_missing_policy_items=matrix_missing_policy_items,
    )
    owner.stats_workflow_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner.stats_mode_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner.stats_bootstrap_target_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner.stats_hypothesis_test_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner.stats_time_series_method_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner._on_stats_mode_change()
    return stats_box


def _bind_statistics_schema_fields(
    owner: Any,
    *,
    lbl_stats_value: QLabel,
    lbl_stats_group: QLabel,
    lbl_stats_sigma: QLabel,
    lbl_stats_type: QLabel,
    lbl_weight_var: QLabel,
    lbl_stats_sample: QLabel,
    lbl_trim_fraction: QLabel,
    lbl_stats_workflow: QLabel,
    lbl_bootstrap_target: QLabel,
    lbl_bootstrap_confidence: QLabel,
    lbl_bootstrap_resamples: QLabel,
    lbl_bootstrap_seed: QLabel,
    lbl_hypothesis_test: QLabel,
    lbl_hypothesis_b_column: QLabel,
    lbl_hypothesis_null: QLabel,
    lbl_hypothesis_alternative: QLabel,
    lbl_hypothesis_alpha: QLabel,
    lbl_hypothesis_expected_source: QLabel,
    lbl_hypothesis_fitted_parameters: QLabel,
    lbl_time_series_method: QLabel,
    lbl_time_series_time_column: QLabel,
    lbl_time_series_window_size: QLabel,
    lbl_time_series_min_periods: QLabel,
    lbl_time_series_alignment: QLabel,
    lbl_time_series_denominator: QLabel,
    lbl_time_series_ewma_parameter: QLabel,
    lbl_time_series_ewma_value: QLabel,
    lbl_time_series_ewma_adjust: QLabel,
    lbl_matrix_missing_policy: QLabel,
    stats_items: list[tuple[str, str, str]],
    workflow_items: list[tuple[str, str, str]],
    bootstrap_target_items: list[tuple[str, str, str]],
    hypothesis_test_items: list[tuple[str, str, str]],
    hypothesis_alternative_items: list[tuple[str, str, str]],
    hypothesis_expected_source_items: list[tuple[str, str, str]],
    time_series_method_items: list[tuple[str, str, str]],
    time_series_alignment_items: list[tuple[str, str, str]],
    time_series_denominator_items: list[tuple[str, str, str]],
    time_series_ewma_parameter_items: list[tuple[str, str, str]],
    matrix_missing_policy_items: list[tuple[str, str, str]],
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    workflow_field = FormFieldSpec(
        key="statistics.workflow_mode",
        widget_kind="select",
        label=LocalizedText("工作流：", "Workflow:"),
        tooltip=LocalizedText(
            "常规统计逐列计算；矩阵工作流计算显式选择列之间的协方差和相关系数；分组统计按文本分组列分组后复用统计类型；Bootstrap 对每个数值列独立重采样并报告固定 95% 置信区间；假设检验报告检验统计量、p 值和诊断；时间序列工作流计算滚动统计或 EWMA。",
            "Standard statistics computes columns independently. The matrix workflow computes covariance and correlation across selected columns. Grouped statistics groups rows by a text group column and reuses the statistics type. Bootstrap reports a fixed 95% confidence interval. Hypothesis tests report test statistics, p-values, and diagnostics. Time-series computes rolling statistics or EWMA.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in workflow_items
        ],
    )
    value_field = FormFieldSpec(
        key="statistics.value_columns",
        widget_kind="text",
        label=LocalizedText("数值列：", "Value columns:"),
        placeholder=LocalizedText("例如 A, B, C", "For example A, B, C"),
        tooltip=LocalizedText(
            "数值数据所在列。可用逗号选择多列，例如 A, B；常规统计会逐列计算，矩阵工作流会计算这些列之间的协方差和相关系数。",
            "Columns containing measured values. Use commas for multiple columns, for example A, B. Standard statistics computes each column independently; the matrix workflow computes covariance and correlation across them.",
        ),
        required=True,
    )
    group_field = FormFieldSpec(
        key="statistics.group_column",
        widget_kind="text",
        label=LocalizedText("分组列：", "Group column:"),
        placeholder=LocalizedText("例如 Group", "For example Group"),
        tooltip=LocalizedText(
            "分组统计专用。该列作为文本标签保留，按首次出现顺序分组；空分组标签会被跳过并记录诊断。",
            "Grouped statistics only. This text column is preserved as labels and groups are ordered by first appearance; blank group labels are skipped with diagnostics.",
        ),
        required=False,
    )
    sigma_field = FormFieldSpec(
        key="statistics.sigma_column",
        widget_kind="text",
        label=LocalizedText("不确定度列（可选）：", "Sigma column (optional):"),
        placeholder=LocalizedText("留空则不使用不确定度列", "Leave blank to ignore sigma values"),
        tooltip=LocalizedText(
            "可选的不确定度列。加权平均模式会使用该列作为 σ；时间序列滚动均值可填写与数值列一一对应的 σ 列。",
            "Optional uncertainty column. Weighted mean uses this column as sigma. Time-series rolling mean may use sigma columns aligned with value columns.",
        ),
        required=False,
    )
    mode_field = FormFieldSpec(
        key="statistics.mode",
        widget_kind="select",
        label=LocalizedText("统计类型：", "Statistics type:"),
        tooltip=LocalizedText(
            "选择算术平均、描述统计，或使用 σ 值作为权重的加权平均。",
            "Choose arithmetic mean, descriptive statistics, or weighted mean. Use sigma values as weights for weighted statistics.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in stats_items
        ],
    )
    bootstrap_target_field = FormFieldSpec(
        key="statistics.bootstrap.target_statistic",
        widget_kind="select",
        label=LocalizedText("Bootstrap 目标：", "Bootstrap target:"),
        tooltip=LocalizedText(
            "选择要由 percentile Bootstrap 估计置信区间的统计量。",
            "Statistic whose confidence interval is estimated by percentile bootstrap.",
        ),
        required=False,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in bootstrap_target_items
        ],
    )
    bootstrap_confidence_field = FormFieldSpec(
        key="statistics.bootstrap.confidence_level",
        widget_kind="text",
        label=LocalizedText("置信水平：", "Confidence level:"),
        placeholder=LocalizedText("0.95", "0.95"),
        tooltip=LocalizedText(
            "初版固定为 0.95，因为共享分布摘要目前固定输出 2.5/50/97.5 百分位。",
            "Fixed to 0.95 in the first release because the shared distribution summary currently emits 2.5/50/97.5 percentiles.",
        ),
        required=False,
    )
    bootstrap_resamples_field = FormFieldSpec(
        key="statistics.bootstrap.resample_count",
        widget_kind="number",
        label=LocalizedText("重采样次数：", "Resamples:"),
        tooltip=LocalizedText(
            "Bootstrap 重采样次数。允许范围 100 到 100000。",
            "Bootstrap resample count. Allowed range is 100 to 100000.",
        ),
        required=False,
    )
    bootstrap_seed_field = FormFieldSpec(
        key="statistics.bootstrap.seed",
        widget_kind="text",
        label=LocalizedText("随机种子：", "Seed:"),
        placeholder=LocalizedText("留空则每次随机", "Blank for a non-reproducible run"),
        tooltip=LocalizedText(
            "可选整数种子；填写后串行和并行运行应得到相同结果。",
            "Optional integer seed; when set, serial and parallel runs should produce identical results.",
        ),
        required=False,
    )
    hypothesis_test_field = FormFieldSpec(
        key="statistics.hypothesis.test_kind",
        widget_kind="select",
        label=LocalizedText("检验类型：", "Test kind:"),
        tooltip=LocalizedText(
            "选择显式假设检验；DataLab 不会自动选择检验方法。",
            "Choose an explicit hypothesis test. DataLab does not automatically choose a test.",
        ),
        required=False,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in hypothesis_test_items
        ],
    )
    hypothesis_b_column_field = FormFieldSpec(
        key="statistics.hypothesis.second_column",
        widget_kind="text",
        label=LocalizedText("第二列：", "Second column:"),
        placeholder=LocalizedText("例如 B", "For example B"),
        tooltip=LocalizedText(
            "配对 t、Welch t 和卡方拟合优度需要第二列。卡方中该列表示期望计数或期望概率。",
            "Required for paired t, Welch t, and chi-square GOF. For chi-square, this column is expected counts or probabilities.",
        ),
        required=False,
    )
    hypothesis_null_field = FormFieldSpec(
        key="statistics.hypothesis.null_parameter",
        widget_kind="text",
        label=LocalizedText("零假设参数：", "Null parameter:"),
        placeholder=LocalizedText("mu0 / delta0 / m0，例如 0", "mu0 / delta0 / m0, for example 0"),
        tooltip=LocalizedText(
            "单样本 t 使用 mu0；配对/Welch t 使用 delta0；符号检验使用 m0。",
            "One-sample t uses mu0; paired/Welch t use delta0; sign test uses m0.",
        ),
        required=False,
    )
    hypothesis_alternative_field = FormFieldSpec(
        key="statistics.hypothesis.alternative",
        widget_kind="select",
        label=LocalizedText("备择假设：", "Alternative:"),
        tooltip=LocalizedText(
            "选择双侧、小于或大于。卡方拟合优度固定为上尾检验。",
            "Choose two-sided, less, or greater. Chi-square GOF is fixed to the upper tail.",
        ),
        required=False,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in hypothesis_alternative_items
        ],
    )
    hypothesis_alpha_field = FormFieldSpec(
        key="statistics.hypothesis.alpha",
        widget_kind="text",
        label=LocalizedText("显著性水平 α：", "Significance α:"),
        placeholder=LocalizedText("0.05", "0.05"),
        tooltip=LocalizedText(
            "用于报告是否拒绝零假设；必须在 0 到 1 之间。",
            "Used to report reject/not-reject diagnostics; must be between 0 and 1.",
        ),
        required=False,
    )
    hypothesis_expected_source_field = FormFieldSpec(
        key="statistics.hypothesis.expected_source",
        widget_kind="select",
        label=LocalizedText("期望列类型：", "Expected source:"),
        tooltip=LocalizedText(
            "卡方拟合优度中，第二列可解释为期望计数或期望概率。",
            "For chi-square GOF, the second column can be expected counts or expected probabilities.",
        ),
        required=False,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in hypothesis_expected_source_items
        ],
    )
    hypothesis_fitted_parameters_field = FormFieldSpec(
        key="statistics.hypothesis.fitted_parameter_count",
        widget_kind="number",
        label=LocalizedText("拟合参数数：", "Fitted parameters:"),
        tooltip=LocalizedText(
            "卡方自由度使用 类别数 - 1 - 拟合参数数。",
            "Chi-square degrees of freedom use category count - 1 - fitted parameter count.",
        ),
        required=False,
    )
    time_series_method_field = FormFieldSpec(
        key="statistics.time_series.series_method",
        widget_kind="select",
        label=LocalizedText("序列方法：", "Series method:"),
        tooltip=LocalizedText(
            "选择滚动均值、滚动中位数、滚动标准差或指数加权移动平均。时间序列保持输入顺序，不会自动排序。",
            "Choose rolling mean, rolling median, rolling standard deviation, or EWMA. The series preserves input order and does not sort automatically.",
        ),
        required=False,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in time_series_method_items],
    )
    time_series_time_column_field = FormFieldSpec(
        key="statistics.time_series.time_column",
        widget_kind="text",
        label=LocalizedText("时间/索引列：", "Time/index column:"),
        placeholder=LocalizedText("可留空，默认使用行号", "Optional; blank uses row index"),
        tooltip=LocalizedText(
            "可选标签列。该列可为非数值文本，仅用于显示、绘图标签和单调性诊断，不参与排序。",
            "Optional label column. It may contain non-numeric text and is used only for display, plot labels, and monotonicity diagnostics.",
        ),
        required=False,
    )
    time_series_window_size_field = FormFieldSpec(
        key="statistics.time_series.window_size",
        widget_kind="number",
        label=LocalizedText("窗口大小：", "Window size:"),
        tooltip=LocalizedText("滚动窗口包含的行数；必须至少为 1。", "Row-count rolling window size; must be at least 1."),
        required=False,
    )
    time_series_min_periods_field = FormFieldSpec(
        key="statistics.time_series.min_periods",
        widget_kind="number",
        label=LocalizedText("最少点数：", "Min periods:"),
        tooltip=LocalizedText(
            "窗口内至少需要的有效点数；不足时该输出点为空并产生诊断。",
            "Minimum valid points required in a window; insufficient points produce an empty output point and a diagnostic.",
        ),
        required=False,
    )
    time_series_alignment_field = FormFieldSpec(
        key="statistics.time_series.alignment",
        widget_kind="select",
        label=LocalizedText("窗口对齐：", "Window alignment:"),
        tooltip=LocalizedText("滚动窗口相对当前行右对齐或居中。", "Align the rolling window to the right or center of the current row."),
        required=False,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in time_series_alignment_items],
    )
    time_series_denominator_field = FormFieldSpec(
        key="statistics.time_series.denominator",
        widget_kind="select",
        label=LocalizedText("标准差分母：", "Std denominator:"),
        tooltip=LocalizedText("仅用于滚动标准差：样本模式使用 n-1，总体模式使用 n。", "Rolling standard deviation only: sample uses n-1; population uses n."),
        required=False,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in time_series_denominator_items],
    )
    time_series_ewma_parameter_field = FormFieldSpec(
        key="statistics.time_series.ewma_parameter",
        widget_kind="select",
        label=LocalizedText("EWMA 参数：", "EWMA parameter:"),
        tooltip=LocalizedText(
            "EWMA 需要 alpha 或 span 二选一；span 会换算为 alpha = 2 / (span + 1)。",
            "EWMA requires exactly one of alpha or span. Span is converted by alpha = 2 / (span + 1).",
        ),
        required=False,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in time_series_ewma_parameter_items],
    )
    time_series_ewma_value_field = FormFieldSpec(
        key="statistics.time_series.ewma_value",
        widget_kind="text",
        label=LocalizedText("EWMA 数值：", "EWMA value:"),
        placeholder=LocalizedText("例如 0.5 或 5", "For example 0.5 or 5"),
        tooltip=LocalizedText("当前 EWMA 参数的数值。alpha 必须在 (0, 1]；span 必须 >= 1。", "Value for the selected EWMA parameter. Alpha must be in (0, 1]; span must be >= 1."),
        required=False,
    )
    time_series_ewma_adjust_field = FormFieldSpec(
        key="statistics.time_series.adjust",
        widget_kind="checkbox",
        label=LocalizedText("EWMA adjust：", "EWMA adjust:"),
        tooltip=LocalizedText("启用后使用归一化权重形式的 adjusted EWMA。", "When enabled, use the normalized-weight adjusted EWMA form."),
        required=False,
    )
    matrix_missing_policy_field = FormFieldSpec(
        key="statistics.matrix.missing_policy",
        widget_kind="select",
        label=LocalizedText("缺失值策略：", "Missing data:"),
        tooltip=LocalizedText(
            "矩阵工作流专用。按行删除要求每个选中列都有数值；按对删除为每一列对单独选择共同有效行，并且不会作为预算聚合候选。",
            "Matrix workflow only. Listwise deletion requires every selected column to have a value. Pairwise deletion uses rows valid for each column pair and is not eligible for budget aggregation.",
        ),
        required=False,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in matrix_missing_policy_items
        ],
    )
    weight_variance_field = FormFieldSpec(
        key="statistics.weight_variance",
        widget_kind="checkbox",
        label=LocalizedText("方差/标准误差：", "Variance/SE:"),
        tooltip=LocalizedText(
            "启用后，方差和标准误差也按权重计算。",
            "When enabled, variance and standard error are also computed with weights.",
        ),
        required=False,
    )
    sample_field = FormFieldSpec(
        key="statistics.sample_mode",
        widget_kind="checkbox",
        label=LocalizedText("样本/总体：", "Sample/Population:"),
        tooltip=LocalizedText(
            "启用样本模式时使用 n-1 自由度；关闭时使用总体模式。",
            "Sample mode uses n-1 degrees of freedom; otherwise population mode is used.",
        ),
        required=False,
    )
    trim_fraction_field = FormFieldSpec(
        key="statistics.trim_fraction",
        widget_kind="text",
        label=LocalizedText("修剪比例：", "Trim fraction:"),
        placeholder=LocalizedText("留空或 0 表示关闭", "Blank or 0 disables trimming"),
        tooltip=LocalizedText(
            "仅用于描述统计。每端按 floor(n * 修剪比例) 删除数据后计算均值。",
            "Descriptive statistics only. Each tail removes floor(n * trim fraction) values before averaging.",
        ),
        required=False,
    )

    bind_field(field=workflow_field, label=lbl_stats_workflow, widget=owner.stats_workflow_combo, lang=lang)
    bind_choices(owner.stats_workflow_combo, workflow_field.choices, lang=lang)
    register_schema_text_refresh(owner, workflow_field, widget=owner.stats_workflow_combo)
    bind_field(field=value_field, label=lbl_stats_value, widget=owner.stats_value_column_edit, lang=lang)
    register_schema_text_refresh(owner, value_field, widget=owner.stats_value_column_edit)
    bind_field(field=group_field, label=lbl_stats_group, widget=owner.stats_group_column_edit, lang=lang)
    register_schema_text_refresh(owner, group_field, widget=owner.stats_group_column_edit)
    bind_field(field=sigma_field, label=lbl_stats_sigma, widget=owner.stats_sigma_column_edit, lang=lang)
    register_schema_text_refresh(owner, sigma_field, widget=owner.stats_sigma_column_edit)
    bind_field(field=mode_field, label=lbl_stats_type, widget=owner.stats_mode_combo, lang=lang)
    bind_choices(owner.stats_mode_combo, mode_field.choices, lang=lang)
    register_schema_text_refresh(owner, mode_field, widget=owner.stats_mode_combo)
    bind_field(
        field=bootstrap_target_field,
        label=lbl_bootstrap_target,
        widget=owner.stats_bootstrap_target_combo,
        lang=lang,
    )
    bind_choices(owner.stats_bootstrap_target_combo, bootstrap_target_field.choices, lang=lang)
    register_schema_text_refresh(owner, bootstrap_target_field, widget=owner.stats_bootstrap_target_combo)
    bind_field(
        field=bootstrap_confidence_field,
        label=lbl_bootstrap_confidence,
        widget=owner.stats_bootstrap_confidence_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, bootstrap_confidence_field, widget=owner.stats_bootstrap_confidence_edit)
    bind_field(
        field=bootstrap_resamples_field,
        label=lbl_bootstrap_resamples,
        widget=owner.stats_bootstrap_resamples_spin,
        lang=lang,
    )
    register_schema_text_refresh(owner, bootstrap_resamples_field, widget=owner.stats_bootstrap_resamples_spin)
    bind_field(field=bootstrap_seed_field, label=lbl_bootstrap_seed, widget=owner.stats_bootstrap_seed_edit, lang=lang)
    register_schema_text_refresh(owner, bootstrap_seed_field, widget=owner.stats_bootstrap_seed_edit)
    bind_field(
        field=hypothesis_test_field,
        label=lbl_hypothesis_test,
        widget=owner.stats_hypothesis_test_combo,
        lang=lang,
    )
    bind_choices(owner.stats_hypothesis_test_combo, hypothesis_test_field.choices, lang=lang)
    register_schema_text_refresh(owner, hypothesis_test_field, widget=owner.stats_hypothesis_test_combo)
    bind_field(
        field=hypothesis_b_column_field,
        label=lbl_hypothesis_b_column,
        widget=owner.stats_hypothesis_b_column_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, hypothesis_b_column_field, widget=owner.stats_hypothesis_b_column_edit)
    bind_field(
        field=hypothesis_null_field,
        label=lbl_hypothesis_null,
        widget=owner.stats_hypothesis_null_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, hypothesis_null_field, widget=owner.stats_hypothesis_null_edit)
    bind_field(
        field=hypothesis_alternative_field,
        label=lbl_hypothesis_alternative,
        widget=owner.stats_hypothesis_alternative_combo,
        lang=lang,
    )
    bind_choices(owner.stats_hypothesis_alternative_combo, hypothesis_alternative_field.choices, lang=lang)
    register_schema_text_refresh(owner, hypothesis_alternative_field, widget=owner.stats_hypothesis_alternative_combo)
    bind_field(
        field=hypothesis_alpha_field,
        label=lbl_hypothesis_alpha,
        widget=owner.stats_hypothesis_alpha_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, hypothesis_alpha_field, widget=owner.stats_hypothesis_alpha_edit)
    bind_field(
        field=hypothesis_expected_source_field,
        label=lbl_hypothesis_expected_source,
        widget=owner.stats_hypothesis_expected_source_combo,
        lang=lang,
    )
    bind_choices(owner.stats_hypothesis_expected_source_combo, hypothesis_expected_source_field.choices, lang=lang)
    register_schema_text_refresh(owner, hypothesis_expected_source_field, widget=owner.stats_hypothesis_expected_source_combo)
    bind_field(
        field=hypothesis_fitted_parameters_field,
        label=lbl_hypothesis_fitted_parameters,
        widget=owner.stats_hypothesis_fitted_parameters_spin,
        lang=lang,
    )
    register_schema_text_refresh(
        owner,
        hypothesis_fitted_parameters_field,
        widget=owner.stats_hypothesis_fitted_parameters_spin,
    )
    bind_field(
        field=time_series_method_field,
        label=lbl_time_series_method,
        widget=owner.stats_time_series_method_combo,
        lang=lang,
    )
    bind_choices(owner.stats_time_series_method_combo, time_series_method_field.choices, lang=lang)
    register_schema_text_refresh(owner, time_series_method_field, widget=owner.stats_time_series_method_combo)
    bind_field(
        field=time_series_time_column_field,
        label=lbl_time_series_time_column,
        widget=owner.stats_time_series_time_column_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, time_series_time_column_field, widget=owner.stats_time_series_time_column_edit)
    bind_field(
        field=time_series_window_size_field,
        label=lbl_time_series_window_size,
        widget=owner.stats_time_series_window_size_spin,
        lang=lang,
    )
    register_schema_text_refresh(owner, time_series_window_size_field, widget=owner.stats_time_series_window_size_spin)
    bind_field(
        field=time_series_min_periods_field,
        label=lbl_time_series_min_periods,
        widget=owner.stats_time_series_min_periods_spin,
        lang=lang,
    )
    register_schema_text_refresh(owner, time_series_min_periods_field, widget=owner.stats_time_series_min_periods_spin)
    bind_field(
        field=time_series_alignment_field,
        label=lbl_time_series_alignment,
        widget=owner.stats_time_series_alignment_combo,
        lang=lang,
    )
    bind_choices(owner.stats_time_series_alignment_combo, time_series_alignment_field.choices, lang=lang)
    register_schema_text_refresh(owner, time_series_alignment_field, widget=owner.stats_time_series_alignment_combo)
    bind_field(
        field=time_series_denominator_field,
        label=lbl_time_series_denominator,
        widget=owner.stats_time_series_denominator_combo,
        lang=lang,
    )
    bind_choices(owner.stats_time_series_denominator_combo, time_series_denominator_field.choices, lang=lang)
    register_schema_text_refresh(owner, time_series_denominator_field, widget=owner.stats_time_series_denominator_combo)
    bind_field(
        field=time_series_ewma_parameter_field,
        label=lbl_time_series_ewma_parameter,
        widget=owner.stats_time_series_ewma_parameter_combo,
        lang=lang,
    )
    bind_choices(owner.stats_time_series_ewma_parameter_combo, time_series_ewma_parameter_field.choices, lang=lang)
    register_schema_text_refresh(owner, time_series_ewma_parameter_field, widget=owner.stats_time_series_ewma_parameter_combo)
    bind_field(
        field=time_series_ewma_value_field,
        label=lbl_time_series_ewma_value,
        widget=owner.stats_time_series_ewma_value_edit,
        lang=lang,
    )
    register_schema_text_refresh(owner, time_series_ewma_value_field, widget=owner.stats_time_series_ewma_value_edit)
    bind_field(
        field=time_series_ewma_adjust_field,
        label=lbl_time_series_ewma_adjust,
        widget=owner.stats_time_series_ewma_adjust_checkbox,
        lang=lang,
    )
    register_schema_text_refresh(owner, time_series_ewma_adjust_field, widget=owner.stats_time_series_ewma_adjust_checkbox)
    bind_field(
        field=matrix_missing_policy_field,
        label=lbl_matrix_missing_policy,
        widget=owner.stats_matrix_missing_policy_combo,
        lang=lang,
    )
    bind_choices(owner.stats_matrix_missing_policy_combo, matrix_missing_policy_field.choices, lang=lang)
    register_schema_text_refresh(owner, matrix_missing_policy_field, widget=owner.stats_matrix_missing_policy_combo)
    bind_field(
        field=weight_variance_field,
        label=lbl_weight_var,
        widget=owner.stats_weight_variance_checkbox,
        lang=lang,
    )
    register_schema_text_refresh(owner, weight_variance_field, widget=owner.stats_weight_variance_checkbox)
    bind_field(field=sample_field, label=lbl_stats_sample, widget=owner.stats_sample_checkbox, lang=lang)
    register_schema_text_refresh(owner, sample_field, widget=owner.stats_sample_checkbox)
    bind_field(field=trim_fraction_field, label=lbl_trim_fraction, widget=owner.stats_trim_fraction_edit, lang=lang)
    register_schema_text_refresh(owner, trim_fraction_field, widget=owner.stats_trim_fraction_edit)


__all__ = ["build_statistics_mode_view"]
