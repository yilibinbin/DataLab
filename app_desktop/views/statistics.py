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
        description_zh="选择数值列、可选的不确定度列，以及平均方式。",
        description_en="Choose the value column, optional sigma column, and averaging mode.",
    )
    stats_box = section.host
    stats_box.setProperty("datalab_statistics_panel", True)
    card_layout = section.card_layout

    stats_layout = QFormLayout()
    stats_layout.setContentsMargins(0, 0, 0, 0)
    stats_layout.setSpacing(8)
    stats_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    stats_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    owner.stats_value_column_edit = QLineEdit("A")
    lbl_stats_value = QLabel("数值列：")
    owner._register_text(lbl_stats_value, "数值列：", "Value column:")
    stats_layout.addRow(lbl_stats_value, owner.stats_value_column_edit)

    owner.stats_sigma_column_edit = QLineEdit("")
    lbl_stats_sigma = QLabel("不确定度列（可选）：")
    owner._register_text(lbl_stats_sigma, "不确定度列（可选）：", "Sigma column (optional):")
    stats_layout.addRow(lbl_stats_sigma, owner.stats_sigma_column_edit)

    owner.stats_mode_combo = QComboBox()
    stats_items = [
        ("算术平均", "Arithmetic mean", "mean"),
        ("加权平均（σ 加权）", "Weighted mean (σ)", "weighted_sigma"),
    ]
    for zh, _en, data in stats_items:
        owner.stats_mode_combo.addItem(zh, data)
    owner._register_combo(owner.stats_mode_combo, stats_items)
    lbl_stats_type = QLabel("统计类型：")
    owner._register_text(lbl_stats_type, "统计类型：", "Statistics type:")
    stats_layout.addRow(lbl_stats_type, owner.stats_mode_combo)

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
    stats_layout.addRow(lbl_stats_sample, owner.stats_sample_checkbox)
    card_layout.addLayout(stats_layout)

    _bind_statistics_schema_fields(
        owner,
        lbl_stats_value=lbl_stats_value,
        lbl_stats_sigma=lbl_stats_sigma,
        lbl_stats_type=lbl_stats_type,
        lbl_weight_var=lbl_weight_var,
        lbl_stats_sample=lbl_stats_sample,
        stats_items=stats_items,
    )
    owner.stats_mode_combo.currentIndexChanged.connect(owner._on_stats_mode_change)
    owner._on_stats_mode_change()
    return stats_box


def _bind_statistics_schema_fields(
    owner: Any,
    *,
    lbl_stats_value: QLabel,
    lbl_stats_sigma: QLabel,
    lbl_stats_type: QLabel,
    lbl_weight_var: QLabel,
    lbl_stats_sample: QLabel,
    stats_items: list[tuple[str, str, str]],
) -> None:
    lang = "en" if bool(getattr(owner, "_is_en", lambda: False)()) else "zh"
    value_field = FormFieldSpec(
        key="statistics.value_column",
        widget_kind="text",
        label=LocalizedText("数值列：", "Value column:"),
        tooltip=LocalizedText(
            "数值数据所在列，例如 A 或列名。",
            "Column containing measured values, for example A or a header name.",
        ),
        required=True,
    )
    sigma_field = FormFieldSpec(
        key="statistics.sigma_column",
        widget_kind="text",
        label=LocalizedText("不确定度列（可选）：", "Sigma column (optional):"),
        placeholder=LocalizedText("留空则不使用不确定度列", "Leave blank to ignore sigma values"),
        tooltip=LocalizedText(
            "可选的不确定度列。加权平均模式会使用该列作为 σ。",
            "Optional uncertainty column. Weighted mean mode uses this column as sigma.",
        ),
        required=False,
    )
    mode_field = FormFieldSpec(
        key="statistics.mode",
        widget_kind="select",
        label=LocalizedText("统计类型：", "Statistics type:"),
        tooltip=LocalizedText(
            "选择算术平均或使用 σ 值作为权重的加权平均。",
            "Choose arithmetic mean or weighted mean. Use sigma values as weights for weighted statistics.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in stats_items
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

    bind_field(field=value_field, label=lbl_stats_value, widget=owner.stats_value_column_edit, lang=lang)
    register_schema_text_refresh(owner, value_field, widget=owner.stats_value_column_edit)
    bind_field(field=sigma_field, label=lbl_stats_sigma, widget=owner.stats_sigma_column_edit, lang=lang)
    register_schema_text_refresh(owner, sigma_field, widget=owner.stats_sigma_column_edit)
    bind_field(field=mode_field, label=lbl_stats_type, widget=owner.stats_mode_combo, lang=lang)
    bind_choices(owner.stats_mode_combo, mode_field.choices, lang=lang)
    register_schema_text_refresh(owner, mode_field, widget=owner.stats_mode_combo)
    bind_field(
        field=weight_variance_field,
        label=lbl_weight_var,
        widget=owner.stats_weight_variance_checkbox,
        lang=lang,
    )
    register_schema_text_refresh(owner, weight_variance_field, widget=owner.stats_weight_variance_checkbox)
    bind_field(field=sample_field, label=lbl_stats_sample, widget=owner.stats_sample_checkbox, lang=lang)
    register_schema_text_refresh(owner, sample_field, widget=owner.stats_sample_checkbox)


__all__ = ["build_statistics_mode_view"]
