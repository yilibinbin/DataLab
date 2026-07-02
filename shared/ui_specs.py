#!/usr/bin/env python3
"""
Shared UI Specifications for Data Extrapolation Application
============================================================

This module serves as the SINGLE SOURCE OF TRUTH for all UI specifications
shared between desktop GUI and web interface.

Desktop is the SOURCE OF TRUTH - all specifications here reflect desktop behavior.
Web MUST implement these specifications exactly to ensure perfect alignment.

Contents:
- Extrapolation method specifications
- Parameter widget specifications
- UI layout hints
- Help text references (from formula_help.py)
- Visibility rules and dependencies

Author: 方昊
Institution: 中国科学院精密测量院外场理论组
"""

from collections.abc import Sequence
from typing import Any
from dataclasses import dataclass

from shared.ui_schema import (
    ChoiceSpec,
    FormFieldSpec,
    FormSectionSpec,
    LocalizedText,
    PlotBudget,
    PlotSpec,
    ResultViewSpec,
    VisibilityRule,
)

# Import help text from shared formula_help module
from formula_help import (
    EXTRAPOLATION_METHODS,  # noqa: F401 - preserve module-level compatibility
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
    get_method_parameters,  # noqa: F401 - preserve module-level compatibility
)


# ============================================================
# Direct Shared Schema Factories
# ============================================================

# Shared specs may describe user-visible labels, help, field keys,
# choices, placeholders, visibility rules, result attachment keys, and
# plot budgets. Desktop-only modules may describe Qt layout containers,
# stretch factors, icons, and platform-specific action placement. Do not
# put duplicate user-visible strings in app_desktop unless a Qt widget
# requires a transient state label that is not part of the shared UI.


def _text(zh: str = "", en: str = "") -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


def _choice(value: Any, zh: str, en: str, tooltip_zh: str = "", tooltip_en: str = "") -> ChoiceSpec:
    return ChoiceSpec(value=value, label=_text(zh, en), tooltip=_text(tooltip_zh, tooltip_en))


def text_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    default_value: Any = "",
    placeholder_zh: str = "",
    placeholder_en: str = "",
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = True,
    visible_when: VisibilityRule | None = None,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="text",
        label=_text(label_zh, label_en),
        placeholder=_text(placeholder_zh, placeholder_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
        visible_when=visible_when,
    )


def number_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    default_value: int | float,
    number_type: str = "float",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float = 0.1,
    decimals: int = 2,
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = True,
    visible_when: VisibilityRule | None = None,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="number",
        label=_text(label_zh, label_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
        visible_when=visible_when,
        metadata={
            "number_type": number_type,
            "min_value": min_value,
            "max_value": max_value,
            "step": step,
            "decimals": decimals,
        },
    )


def select_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    default_value: Any,
    choices: Sequence[ChoiceSpec],
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = True,
    visible_when: VisibilityRule | None = None,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="select",
        label=_text(label_zh, label_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
        choices=choices,
        visible_when=visible_when,
    )


def checkbox_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    default_value: bool = False,
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = False,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="checkbox",
        label=_text(label_zh, label_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
    )


def button_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    tooltip_zh: str = "",
    tooltip_en: str = "",
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="button",
        label=_text(label_zh, label_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=False,
    )


def textarea_field(
    *,
    key: str,
    label_zh: str,
    label_en: str,
    default_value: Any = "",
    placeholder_zh: str = "",
    placeholder_en: str = "",
    min_height: int = 80,
    resizable: bool = True,
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = True,
    visible_when: VisibilityRule | None = None,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="textarea",
        label=_text(label_zh, label_en),
        placeholder=_text(placeholder_zh, placeholder_en),
        tooltip=_text(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
        visible_when=visible_when,
        metadata={"min_height": min_height, "resizable": resizable},
    )


def form_section(
    *,
    key: str,
    title_zh: str,
    title_en: str,
    fields: Sequence[FormFieldSpec],
    visible_when: VisibilityRule | None = None,
) -> FormSectionSpec:
    return FormSectionSpec(
        key=key,
        title=_text(title_zh, title_en),
        fields=fields,
        visible_when=visible_when,
    )


# ============================================================
# Extrapolation Method Specifications
# ============================================================

# Power Law Method Parameters
POWER_LAW_PARAMS = form_section(
    key="power_law_params",
    title_zh="幂律参数",
    title_en="Power-law parameters",
    fields=[
        number_field(
            key="x1",
            label_zh="x1：",
            label_en="x1:",
            default_value=10.0,
            number_type="float",
            tooltip_zh="第一个自变量值",
            tooltip_en="First x value",
        ),
        number_field(
            key="x2",
            label_zh="x2：",
            label_en="x2:",
            default_value=20.0,
            number_type="float",
            tooltip_zh="第二个自变量值",
            tooltip_en="Second x value",
        ),
        number_field(
            key="x3",
            label_zh="x3：",
            label_en="x3:",
            default_value=40.0,
            number_type="float",
            tooltip_zh="第三个自变量值",
            tooltip_en="Third x value",
        ),
        text_field(
            key="p",
            label_zh="自定义 p（可选）：",
            label_en="Custom p (optional):",
            default_value="",
            placeholder_zh="留空则自动求解 p",
            placeholder_en="Leave blank to solve p automatically",
            required=False,
            tooltip_zh="幂指数，留空则自动求解",
            tooltip_en="Power exponent, auto-solved if blank",
        ),
    ],
    visible_when=VisibilityRule.equals("method", "power_law"),
)

# Richardson Method Parameters — mpmath's mp.richardson(seq) takes no tunable
# knobs, so (like shanks/wynn) this section carries no fields. The former "p"
# control was silently ignored by the backend (audit F4).
RICHARDSON_PARAMS = form_section(
    key="richardson_params",
    title_zh="Richardson 序列加速参数",
    title_en="Richardson acceleration parameters",
    fields=[],
    visible_when=VisibilityRule.equals("method", "richardson"),
)

# Levin u-transform Parameters
LEVIN_U_PARAMS = form_section(
    key="levin_u_params",
    title_zh="Levin u 变换参数",
    title_en="Levin u-transform parameters",
    fields=[
        select_field(
            key="variant",
            label_zh="变换类型：",
            label_en="Variant:",
            default_value="u",
            choices=[
                _choice("u", "u (最常用)", "u (most common)"),
                _choice("t", "t (级数)", "t (series)"),
                _choice("v", "v (积分)", "v (integrals)"),
            ],
            tooltip_zh="变换类型（u最常用，t适用于级数，v用于积分）",
            tooltip_en="Transform type (u most common, t for series, v for integrals)",
        ),
        # order / weight / beta were removed: mpmath's mp.levin(variant) honors
        # only the variant, so those controls were silently ignored (audit F4).
    ],
    visible_when=VisibilityRule.equals("method", "levin_u"),
)

# Custom Formula Parameters
CUSTOM_FORMULA_PARAMS = form_section(
    key="custom_formula_params",
    title_zh="自定义公式",
    title_en="Custom formula",
    fields=[
        textarea_field(
            key="custom_formula",
            label_zh="自定义公式：",
            label_en="Custom formula:",
            default_value="(C - B)^2/(B - A) + C",
            placeholder_zh="示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
            placeholder_en="Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
            min_height=80,
            resizable=True,
            tooltip_zh="使用 A/B/C、列名或 x1/x2/x3 作为变量，支持数学函数",
            tooltip_en="Use A/B/C, column names, or x1/x2/x3 as variables, supports math functions",
        ),
    ],
    visible_when=VisibilityRule.equals("method", "custom"),
)

# Shanks and Wynn-epsilon have no additional parameters
SHANKS_PARAMS = form_section(
    key="shanks_params",
    title_zh="Shanks 变换",
    title_en="Shanks transform",
    fields=[],
    visible_when=VisibilityRule.equals("method", "shanks"),
)

WYNN_EPSILON_PARAMS = form_section(
    key="wynn_epsilon_params",
    title_zh="Wynn-epsilon 算法",
    title_en="Wynn-epsilon algorithm",
    fields=[],
    visible_when=VisibilityRule.equals("method", "wynn_epsilon"),
)


# ============================================================
# Complete Method Specifications
# ============================================================

@dataclass
class MethodSpec:
    """Complete specification for an extrapolation method."""
    key: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    parameter_groups: list[FormSectionSpec]
    help_button: bool = True  # Whether to show "?" help button

    def get_name(self, lang: str = "zh") -> str:
        return self.name_zh if lang == "zh" else self.name_en

    def get_description(self, lang: str = "zh") -> str:
        return self.description_zh if lang == "zh" else self.description_en


# All extrapolation methods with their complete specifications
EXTRAPOLATION_METHOD_SPECS: dict[str, MethodSpec] = {
    "power_law": MethodSpec(
        key="power_law",
        name_zh="幂律外推(三点外推)",
        name_en="Power-law (3-point)",
        description_zh=get_method_description("power_law", "zh"),
        description_en=get_method_description("power_law", "en"),
        parameter_groups=[POWER_LAW_PARAMS],
    ),
    "richardson": MethodSpec(
        key="richardson",
        name_zh="Richardson 序列加速",
        name_en="Richardson",
        description_zh=get_method_description("richardson", "zh"),
        description_en=get_method_description("richardson", "en"),
        parameter_groups=[RICHARDSON_PARAMS],
    ),
    "shanks": MethodSpec(
        key="shanks",
        name_zh="Shanks 变换",
        name_en="Shanks transform",
        description_zh=get_method_description("shanks", "zh"),
        description_en=get_method_description("shanks", "en"),
        parameter_groups=[SHANKS_PARAMS],
    ),
    "levin_u": MethodSpec(
        key="levin_u",
        name_zh="Levin u-transform",
        name_en="Levin u-transform",
        description_zh=get_method_description("levin_u", "zh"),
        description_en=get_method_description("levin_u", "en"),
        parameter_groups=[LEVIN_U_PARAMS],
    ),
    "wynn_epsilon": MethodSpec(
        key="wynn_epsilon",
        name_zh="Wynn-epsilon 算法",
        name_en="Wynn-epsilon algorithm",
        description_zh=get_method_description("wynn_epsilon", "zh"),
        description_en=get_method_description("wynn_epsilon", "en"),
        parameter_groups=[WYNN_EPSILON_PARAMS],
    ),
    "custom": MethodSpec(
        key="custom",
        name_zh="自定义公式(三点外推) (A,B,C)",
        name_en="Custom (A,B,C)",
        description_zh=get_method_description("custom", "zh"),
        description_en=get_method_description("custom", "en"),
        parameter_groups=[CUSTOM_FORMULA_PARAMS],
    ),
}


# ============================================================
# Method Selector Configuration
# ============================================================

# Order of methods in the dropdown (desktop GUI order)
METHOD_DISPLAY_ORDER = [
    "power_law",
    "richardson",
    "shanks",
    "levin_u",
    "custom",
]

def get_method_options(lang: str = "zh") -> list[tuple[str, str]]:
    """
    Get method options for dropdown in display order.
    Returns: [(display_name, method_key), ...]
    """
    return [
        (EXTRAPOLATION_METHOD_SPECS[key].get_name(lang), key)
        for key in METHOD_DISPLAY_ORDER
        if key in EXTRAPOLATION_METHOD_SPECS
    ]


# ============================================================
# Error Propagation Formula Specifications
# ============================================================

ERROR_FORMULA_FIELD = textarea_field(
    key="error.formula",
    label_zh="公式：",
    label_en="Formula:",
    default_value="",
    placeholder_zh="公式（使用列名或 x1, x2 …）",
    placeholder_en="Formula (use column names or x1, x2 …)",
    min_height=80,
    resizable=True,
    tooltip_zh="使用列名或 x1, x2, ... 作为变量，支持数学函数",
    tooltip_en="Use column names or x1, x2, ... as variables, supports math functions",
)

ERROR_FORMULA_SPEC = ERROR_FORMULA_FIELD


# ============================================================
# Desktop Shared Metadata Registries
# ============================================================

INPUT_DATA_FIELD = textarea_field(
    key="input.data",
    label_zh="输入数据：",
    label_en="Input data:",
    placeholder_zh="粘贴空格、逗号或制表符分隔的数据",
    placeholder_en="Paste whitespace-, comma-, or tab-separated data",
    tooltip_zh="输入或粘贴待分析的数据表。",
    tooltip_en="Enter or paste the data table to analyze.",
    required=True,
)
EXTRAPOLATION_METHOD_FIELD = select_field(
    key="extrapolation.method",
    label_zh="外推方法：",
    label_en="Extrapolation method:",
    default_value="power_law",
    choices=[
        _choice(
            method_key,
            EXTRAPOLATION_METHOD_SPECS[method_key].name_zh,
            EXTRAPOLATION_METHOD_SPECS[method_key].name_en,
        )
        for method_key in METHOD_DISPLAY_ORDER
        if method_key in EXTRAPOLATION_METHOD_SPECS
    ],
    tooltip_zh="选择用于当前数据的外推算法。",
    tooltip_en="Choose the extrapolation algorithm for the current data.",
)
FITTING_MODEL_FIELD = select_field(
    key="fitting.model",
    label_zh="拟合模型：",
    label_en="Fit model:",
    default_value="polynomial",
    choices=[
        _choice("polynomial", "多项式", "Polynomial"),
        _choice("inverse_power", "反幂级数", "Inverse-power series"),
        _choice("custom", "自定义模型", "Custom model"),
    ],
    tooltip_zh="选择曲线拟合模型。",
    tooltip_en="Choose the curve fitting model.",
)
ROOT_FORMULA_FIELD = textarea_field(
    key="root_solving.equation",
    label_zh="方程：",
    label_en="Equation:",
    placeholder_zh="例如 x^2 - A",
    placeholder_en="e.g. x^2 - A",
    tooltip_zh="输入要求根的方程或方程组。",
    tooltip_en="Enter the equation or system to solve.",
)
STATISTICS_VALUE_FIELD = select_field(
    key="statistics.value_column",
    label_zh="数值列：",
    label_en="Value column:",
    default_value="",
    choices=[],
    tooltip_zh="选择用于统计分析的数值列。",
    tooltip_en="Choose the value column for statistical analysis.",
)
GENERATE_PDF_FIELD = checkbox_field(
    key="options.generate_pdf",
    label_zh="生成 PDF",
    label_en="Generate PDF",
    default_value=False,
    tooltip_zh="运行后尝试生成 LaTeX PDF。",
    tooltip_en="Try to generate a LaTeX PDF after running.",
)

RESULT_DISPLAY_SCIENTIFIC_FIELD = checkbox_field(
    key="results.display.scientific",
    label_zh="使用科学计数法显示结果",
    label_en="Display results in scientific notation",
    tooltip_zh="切换数值结果是否使用科学计数法显示。",
    tooltip_en="Toggle scientific notation for numeric result display.",
)
RESULT_DISPLAY_DIGITS_FIELD = number_field(
    key="results.display.decimal_places",
    label_zh="小数位数：",
    label_en="Decimal places:",
    default_value=10,
    number_type="int",
    min_value=0,
    max_value=50,
    step=1,
    decimals=0,
    tooltip_zh="控制数值结果显示的小数位数。",
    tooltip_en="Controls decimal places shown in numeric results.",
    required=False,
)
RESULT_EXPORT_CSV_FIELD = button_field(
    key="results.export.csv",
    label_zh="导出 CSV",
    label_en="Export CSV",
    tooltip_zh="导出当前结果表格为 CSV 文件。",
    tooltip_en="Export the current result table as a CSV file.",
)
RESULT_IMAGE_ZOOM_FIELD = number_field(
    key="results.image.zoom_percent",
    label_zh="图片缩放",
    label_en="Image zoom",
    default_value=100,
    number_type="int",
    min_value=25,
    max_value=400,
    step=5,
    decimals=0,
    tooltip_zh="结果图片缩放百分比。",
    tooltip_en="Result image zoom percentage.",
    required=False,
)
RESULT_IMAGE_LOG_X_FIELD = checkbox_field(
    key="results.image.log_x",
    label_zh="x 轴",
    label_en="log x",
    tooltip_zh="使用 x 轴对数坐标。",
    tooltip_en="Use logarithmic x axis.",
)
RESULT_IMAGE_LOG_Y_FIELD = checkbox_field(
    key="results.image.log_y",
    label_zh="y 轴",
    label_en="log y",
    tooltip_zh="使用 y 轴对数坐标。",
    tooltip_en="Use logarithmic y axis.",
)
RESULT_IMAGE_ZOOM_IN_FIELD = button_field(
    key="results.image.zoom_in",
    label_zh="放大图片",
    label_en="Zoom image in",
    tooltip_zh="放大结果图片。",
    tooltip_en="Zoom result image in.",
)
RESULT_IMAGE_ZOOM_OUT_FIELD = button_field(
    key="results.image.zoom_out",
    label_zh="缩小图片",
    label_en="Zoom image out",
    tooltip_zh="缩小结果图片。",
    tooltip_en="Zoom result image out.",
)
RESULT_IMAGE_ZOOM_RESET_FIELD = button_field(
    key="results.image.zoom_reset",
    label_zh="重置图片缩放",
    label_en="Reset image zoom",
    tooltip_zh="重置结果图片缩放。",
    tooltip_en="Reset result image zoom.",
)
RESULT_IMAGE_EXPORT_FIELD = button_field(
    key="results.image.export",
    label_zh="导出图片",
    label_en="Export image",
    tooltip_zh="导出当前结果图片。",
    tooltip_en="Export the current result image.",
)
RESULT_IMAGE_PAGE_FIELD = number_field(
    key="results.image.page",
    label_zh="图片页",
    label_en="Image page",
    default_value=1,
    number_type="int",
    min_value=1,
    max_value=None,
    step=1,
    decimals=0,
    tooltip_zh="选择要查看的结果图片页。",
    tooltip_en="Image page to view.",
    required=False,
)
RESULT_IMAGE_PREVIOUS_FIELD = button_field(
    key="results.image.previous",
    label_zh="上一张图片",
    label_en="Previous image",
    tooltip_zh="查看上一张结果图片。",
    tooltip_en="View the previous result image.",
)
RESULT_IMAGE_NEXT_FIELD = button_field(
    key="results.image.next",
    label_zh="下一张图片",
    label_en="Next image",
    tooltip_zh="查看下一张结果图片。",
    tooltip_en="View the next result image.",
)
RESULT_LATEX_OPEN_FIELD = button_field(
    key="results.latex.open",
    label_zh="打开 LaTeX 文件",
    label_en="Open LaTeX file",
    tooltip_zh="打开已有 LaTeX 文件到编辑器。",
    tooltip_en="Open an existing LaTeX file in the editor.",
)
RESULT_LATEX_SAVE_FIELD = button_field(
    key="results.latex.save",
    label_zh="保存 LaTeX 文件",
    label_en="Save LaTeX file",
    tooltip_zh="保存当前 LaTeX 编辑器内容。",
    tooltip_en="Save the current LaTeX editor content.",
)
RESULT_LATEX_RELOAD_FIELD = button_field(
    key="results.latex.reload",
    label_zh="重新载入 LaTeX 文件",
    label_en="Reload LaTeX file",
    tooltip_zh="从磁盘重新载入当前 LaTeX 文件。",
    tooltip_en="Reload the current LaTeX file from disk.",
)
RESULT_LATEX_COMPILE_FIELD = button_field(
    key="latex.compile",
    label_zh="编译 PDF",
    label_en="Compile PDF",
    tooltip_zh="将当前 LaTeX 内容编译为 PDF。",
    tooltip_en="Compile the current LaTeX content into a PDF.",
)
RESULT_LATEX_VIEW_PDF_FIELD = button_field(
    key="latex.view_pdf",
    label_zh="查看 PDF",
    label_en="View PDF",
    tooltip_zh="打开已编译的 PDF 文件。",
    tooltip_en="Open the compiled PDF file.",
)
RESULT_LATEX_ENGINE_FIELD = select_field(
    key="latex.engine",
    label_zh="LaTeX 引擎：",
    label_en="LaTeX engine:",
    default_value="tectonic",
    choices=(
        _choice("pdflatex", "pdflatex", "pdflatex"),
        _choice("xelatex", "xelatex", "xelatex"),
        _choice("tectonic", "tectonic", "tectonic"),
    ),
    tooltip_zh="选择用于编译 PDF 的 LaTeX 引擎。",
    tooltip_en="Choose the LaTeX engine used to compile PDF output.",
    required=False,
)
RESULT_LATEX_ENGINE_PATH_FIELD = button_field(
    key="latex.engine_path",
    label_zh="选择引擎路径",
    label_en="Select engine path",
    tooltip_zh="手动选择 LaTeX 引擎可执行文件路径。",
    tooltip_en="Manually select the LaTeX engine executable path.",
)
RESULT_PDF_ZOOM_FIELD = number_field(
    key="pdf.zoom_percent",
    label_zh="缩放%：",
    label_en="Zoom %:",
    default_value=100,
    number_type="float",
    min_value=35,
    max_value=400,
    step=5,
    decimals=0,
    tooltip_zh="PDF 预览缩放百分比。",
    tooltip_en="PDF preview zoom percentage.",
    required=False,
)
RESULT_PDF_ZOOM_IN_FIELD = button_field(
    key="pdf.zoom_in",
    label_zh="放大 PDF",
    label_en="Zoom PDF in",
    tooltip_zh="放大 PDF 预览。",
    tooltip_en="Zoom PDF preview in.",
)
RESULT_PDF_ZOOM_OUT_FIELD = button_field(
    key="pdf.zoom_out",
    label_zh="缩小 PDF",
    label_en="Zoom PDF out",
    tooltip_zh="缩小 PDF 预览。",
    tooltip_en="Zoom PDF preview out.",
)
RESULT_PDF_ZOOM_RESET_FIELD = button_field(
    key="pdf.zoom_reset",
    label_zh="重置 PDF 缩放",
    label_en="Reset PDF zoom",
    tooltip_zh="重置 PDF 预览缩放。",
    tooltip_en="Reset PDF preview zoom.",
)

DESKTOP_FORM_SECTIONS: dict[str, FormSectionSpec] = {
    "input": form_section(
        key="input",
        title_zh="输入",
        title_en="Input",
        fields=[INPUT_DATA_FIELD],
    ),
    "extrapolation": form_section(
        key="extrapolation",
        title_zh="外推",
        title_en="Extrapolation",
        fields=[
            EXTRAPOLATION_METHOD_FIELD,
            *POWER_LAW_PARAMS.fields,
            *RICHARDSON_PARAMS.fields,
            *LEVIN_U_PARAMS.fields,
            *CUSTOM_FORMULA_PARAMS.fields,
        ],
    ),
    "error": form_section(
        key="error",
        title_zh="误差传播",
        title_en="Error propagation",
        fields=[ERROR_FORMULA_FIELD],
    ),
    "fitting": form_section(
        key="fitting",
        title_zh="曲线拟合",
        title_en="Curve fitting",
        fields=[FITTING_MODEL_FIELD],
    ),
    "root_solving": form_section(
        key="root_solving",
        title_zh="方程求根",
        title_en="Root solving",
        fields=[ROOT_FORMULA_FIELD],
    ),
    "statistics": form_section(
        key="statistics",
        title_zh="统计分析",
        title_en="Statistics",
        fields=[STATISTICS_VALUE_FIELD],
    ),
    "options": form_section(
        key="options",
        title_zh="选项",
        title_en="Options",
        fields=[GENERATE_PDF_FIELD],
    ),
}

DESKTOP_RESULT_VIEWS: dict[str, ResultViewSpec] = {
    "result.numeric": ResultViewSpec(
        key="result.numeric",
        title=_text("数值结果", "Numeric results"),
        attachment_key="numeric",
        raw_columns=("value", "uncertainty"),
        controls=(RESULT_DISPLAY_SCIENTIFIC_FIELD, RESULT_DISPLAY_DIGITS_FIELD, RESULT_EXPORT_CSV_FIELD),
    ),
    "result.image": ResultViewSpec(
        key="result.image",
        title=_text("图像结果", "Image results"),
        attachment_key="image",
        controls=(
            RESULT_IMAGE_ZOOM_FIELD,
            RESULT_IMAGE_LOG_X_FIELD,
            RESULT_IMAGE_LOG_Y_FIELD,
            RESULT_IMAGE_ZOOM_IN_FIELD,
            RESULT_IMAGE_ZOOM_OUT_FIELD,
            RESULT_IMAGE_ZOOM_RESET_FIELD,
            RESULT_IMAGE_EXPORT_FIELD,
            RESULT_IMAGE_PAGE_FIELD,
            RESULT_IMAGE_PREVIOUS_FIELD,
            RESULT_IMAGE_NEXT_FIELD,
        ),
    ),
    "result.log": ResultViewSpec(
        key="result.log",
        title=_text("运行日志", "Run log"),
        attachment_key="log",
    ),
    "result.latex": ResultViewSpec(
        key="result.latex",
        title=_text("LaTeX 源码", "LaTeX source"),
        attachment_key="latex",
        controls=(
            RESULT_LATEX_OPEN_FIELD,
            RESULT_LATEX_SAVE_FIELD,
            RESULT_LATEX_RELOAD_FIELD,
            RESULT_LATEX_COMPILE_FIELD,
            RESULT_LATEX_VIEW_PDF_FIELD,
            RESULT_LATEX_ENGINE_FIELD,
            RESULT_LATEX_ENGINE_PATH_FIELD,
        ),
    ),
    "result.pdf": ResultViewSpec(
        key="result.pdf",
        title=_text("PDF 预览", "PDF preview"),
        attachment_key="pdf",
        controls=(
            RESULT_PDF_ZOOM_FIELD,
            RESULT_PDF_ZOOM_IN_FIELD,
            RESULT_PDF_ZOOM_OUT_FIELD,
            RESULT_PDF_ZOOM_RESET_FIELD,
        ),
    ),
}

DESKTOP_PLOT_SPECS: dict[str, PlotSpec] = {
    "input": PlotSpec(
        key="input",
        title=_text("输入预览", "Input preview"),
        plot_kind="table_preview",
        attachment_key="input",
    ),
    "extrapolation": PlotSpec(
        key="extrapolation",
        title=_text("外推图", "Extrapolation plot"),
        plot_kind="line",
        attachment_key="extrapolation_plot",
    ),
    "error": PlotSpec(
        key="error",
        title=_text("误差贡献", "Error contributions"),
        plot_kind="bar",
        attachment_key="error_plot",
    ),
    "fitting": PlotSpec(
        key="fitting",
        title=_text("拟合图", "Fit plot"),
        plot_kind="line",
        attachment_key="fit_plot",
    ),
    "root_solving": PlotSpec(
        key="root_solving",
        title=_text("求根图", "Root plot"),
        plot_kind="contour_or_line",
        attachment_key="root_plot",
    ),
    "statistics": PlotSpec(
        key="statistics",
        title=_text("统计图", "Statistics plot"),
        plot_kind="histogram",
        attachment_key="statistics_plot",
    ),
    "options": PlotSpec(
        key="options",
        title=_text("导出预览", "Export preview"),
        plot_kind="export_preview",
        attachment_key="options",
    ),
    "result.numeric": PlotSpec(
        key="result.numeric",
        title=_text("数值结果图", "Numeric result plot"),
        plot_kind="table",
        attachment_key="numeric",
    ),
    "result.image": PlotSpec(
        key="result.image",
        title=_text("图像结果", "Image result"),
        plot_kind="image",
        attachment_key="image",
    ),
    "result.log": PlotSpec(
        key="result.log",
        title=_text("日志", "Log"),
        plot_kind="text",
        attachment_key="log",
    ),
    "result.latex": PlotSpec(
        key="result.latex",
        title=_text("LaTeX 预览", "LaTeX preview"),
        plot_kind="latex",
        attachment_key="latex",
    ),
    "result.pdf": PlotSpec(
        key="result.pdf",
        title=_text("PDF 预览", "PDF preview"),
        plot_kind="pdf",
        attachment_key="pdf",
    ),
}


# ============================================================
# Function Support Help Specifications
# ============================================================

@dataclass
class FunctionHelpSpec:
    """Specification for function support help button and content."""
    button_label_zh: str = "函数支持"
    button_label_en: str = "Functions"
    dialog_title_zh: str = "可用函数"
    dialog_title_en: str = "Available Functions"

    def get_button_label(self, lang: str = "zh") -> str:
        return self.button_label_zh if lang == "zh" else self.button_label_en

    def get_dialog_title(self, lang: str = "zh") -> str:
        return self.dialog_title_zh if lang == "zh" else self.dialog_title_en

    def get_content(self, lang: str = "zh") -> str:
        """Get function help content from formula_help module."""
        return get_function_help(lang)

    def get_tooltip(self, lang: str = "zh") -> str:
        """Get tooltip text from formula_help module."""
        return get_function_tooltip(lang)


# Function help used in custom formula (extrapolation mode)
CUSTOM_FORMULA_FUNCTION_HELP = FunctionHelpSpec()

# Function help used in error propagation formula
ERROR_FORMULA_FUNCTION_HELP = FunctionHelpSpec()


# ============================================================
# Method Help Button Specification
# ============================================================

@dataclass
class MethodHelpButtonSpec:
    """Specification for method help button ("?" button)."""
    button_label: str = "?"
    button_tooltip_zh: str = "点击查看当前外推方法的详细说明、适用场景和参数解释"
    button_tooltip_en: str = "Click to view detailed description, applicable scenarios, and parameter explanations for the current method"
    dialog_title_zh: str = "外推方法说明"
    dialog_title_en: str = "Extrapolation Method Help"

    def get_tooltip(self, lang: str = "zh") -> str:
        return self.button_tooltip_zh if lang == "zh" else self.button_tooltip_en

    def get_dialog_title(self, lang: str = "zh") -> str:
        return self.dialog_title_zh if lang == "zh" else self.dialog_title_en

    def get_content(self, method_key: str, lang: str = "zh") -> str:
        """Get method help content from formula_help module."""
        return get_method_description(method_key, lang)


METHOD_HELP_BUTTON = MethodHelpButtonSpec()


# ============================================================
# Dynamic Visibility Rules
# ============================================================

def get_parameter_visibility_rules() -> dict[str, dict[str, Any]]:
    """
    Get parameter visibility rules for dynamic UI updates.

    Returns:
        dict: {
            "parameter_name": {
                "depends_on": "other_parameter_name",
                "visible_when": value_or_condition,
            },
            ...
        }
    """
    # No dynamic visibility rules remain: the levin_u.beta rule depended on the
    # levin_u.weight control, both removed as dead knobs (audit F4). Kept as a
    # function so both frontends keep a stable rules source to consume.
    return {}


# ============================================================
# Validation Rules
# ============================================================

def validate_method_parameters(method_key: str, params: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate parameters for a given method.

    Args:
        method_key: Method identifier
        params: Parameter values to validate

    Returns:
        (is_valid, error_messages)
    """
    errors: list[str] = []

    if method_key not in EXTRAPOLATION_METHOD_SPECS:
        return False, [f"Unknown method: {method_key}"]

    method_spec = EXTRAPOLATION_METHOD_SPECS[method_key]

    for group in method_spec.parameter_groups:
        for param_spec in group.fields:
            param_name = param_spec.key
            value = params.get(param_name)

            # Check required parameters
            if param_spec.required and (value is None or value == ""):
                errors.append(f"Parameter '{param_name}' is required")
                continue

            # Skip validation for empty optional parameters
            if not param_spec.required and (value is None or value == ""):
                continue

            # Validate number parameters
            if param_spec.widget_kind == "number":
                # ``value`` is ``Any | None`` but the empty / None case
                # was filtered above. Use an explicit guard rather than
                # ``assert`` so the validation survives ``python -O``
                # (PyInstaller bundles can be built with optimisation).
                if value is None:
                    continue
                number_type = str(param_spec.metadata.get("number_type", "float"))
                min_value = param_spec.metadata.get("min_value")
                max_value = param_spec.metadata.get("max_value")
                try:
                    num_value: float | int = (
                        float(value)
                        if number_type == "float"
                        else int(value)
                    )
                    if min_value is not None and num_value < min_value:
                        errors.append(f"Parameter '{param_name}' must be >= {min_value}")
                    if max_value is not None and num_value > max_value:
                        errors.append(f"Parameter '{param_name}' must be <= {max_value}")
                except (ValueError, TypeError):
                    errors.append(f"Parameter '{param_name}' must be a valid number")

    return len(errors) == 0, errors


# ============================================================
# Export all public APIs
# ============================================================

__all__ = [
    # Unified schema primitives
    "ChoiceSpec",
    "FormFieldSpec",
    "FormSectionSpec",
    "LocalizedText",
    "PlotBudget",
    "PlotSpec",
    "ResultViewSpec",
    "VisibilityRule",
    "checkbox_field",
    "form_section",
    "number_field",
    "select_field",
    "text_field",
    "textarea_field",

    # Method specifications
    "MethodSpec",
    "EXTRAPOLATION_METHOD_SPECS",
    "METHOD_DISPLAY_ORDER",
    "get_method_options",

    # Parameter groups
    "POWER_LAW_PARAMS",
    "RICHARDSON_PARAMS",
    "LEVIN_U_PARAMS",
    "CUSTOM_FORMULA_PARAMS",
    "SHANKS_PARAMS",
    "WYNN_EPSILON_PARAMS",

    # Error propagation
    "ERROR_FORMULA_FIELD",
    "ERROR_FORMULA_SPEC",

    # Desktop registries
    "DESKTOP_FORM_SECTIONS",
    "DESKTOP_RESULT_VIEWS",
    "DESKTOP_PLOT_SPECS",

    # Function help
    "FunctionHelpSpec",
    "CUSTOM_FORMULA_FUNCTION_HELP",
    "ERROR_FORMULA_FUNCTION_HELP",

    # Method help
    "MethodHelpButtonSpec",
    "METHOD_HELP_BUTTON",

    # Utilities
    "get_parameter_visibility_rules",
    "validate_method_parameters",

    # Re-export from formula_help for convenience
    "get_function_help",
    "get_function_tooltip",
    "get_method_description",
    "get_method_name",
]
