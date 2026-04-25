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

from typing import Any, Literal
from dataclasses import dataclass, field

# Import help text from shared formula_help module
from formula_help import (
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
    get_method_parameters,
    EXTRAPOLATION_METHODS,
)


# ============================================================
# UI Widget Type Definitions
# ============================================================

@dataclass
class WidgetSpec:
    """Base specification for a UI widget parameter."""
    name: str
    label_zh: str
    label_en: str
    widget_type: Literal["text", "number", "select", "checkbox", "textarea"]
    default_value: Any = None
    tooltip_zh: str = ""
    tooltip_en: str = ""
    optional: bool = False

    def get_label(self, lang: str = "zh") -> str:
        """Get localized label."""
        return self.label_zh if lang == "zh" else self.label_en

    def get_tooltip(self, lang: str = "zh") -> str:
        """Get localized tooltip."""
        return self.tooltip_zh if lang == "zh" else self.tooltip_en


@dataclass
class TextWidgetSpec(WidgetSpec):
    """Text input widget specification."""
    widget_type: Literal["text"] = "text"
    placeholder_zh: str = ""
    placeholder_en: str = ""

    def get_placeholder(self, lang: str = "zh") -> str:
        return self.placeholder_zh if lang == "zh" else self.placeholder_en


@dataclass
class NumberWidgetSpec(WidgetSpec):
    """Number input widget specification (float or int)."""
    widget_type: Literal["number"] = "number"
    number_type: Literal["int", "float"] = "float"
    min_value: float | None = None
    max_value: float | None = None
    step: float = 0.1
    decimals: int = 2


@dataclass
class SelectWidgetSpec(WidgetSpec):
    """Select/dropdown widget specification."""
    widget_type: Literal["select"] = "select"
    options: list[tuple[str, str, Any]] = field(default_factory=list)  # [(label_zh, label_en, value), ...]

    def get_options(self, lang: str = "zh") -> list[tuple[str, Any]]:
        """Get localized options as [(label, value), ...]"""
        return [(opt[0] if lang == "zh" else opt[1], opt[2]) for opt in self.options]


@dataclass
class TextAreaWidgetSpec(WidgetSpec):
    """Multi-line text area widget specification."""
    widget_type: Literal["textarea"] = "textarea"
    min_height: int = 80
    placeholder_zh: str = ""
    placeholder_en: str = ""
    resizable: bool = True

    def get_placeholder(self, lang: str = "zh") -> str:
        return self.placeholder_zh if lang == "zh" else self.placeholder_en


# ============================================================
# Method Parameter Group Specifications
# ============================================================

@dataclass
class ParameterGroupSpec:
    """Specification for a group of related parameters."""
    group_key: str
    title_zh: str
    title_en: str
    parameters: list[WidgetSpec]
    visible_when: dict[str, Any] = field(default_factory=dict)  # Visibility conditions

    def get_title(self, lang: str = "zh") -> str:
        return self.title_zh if lang == "zh" else self.title_en

    def is_visible(self, current_values: dict[str, Any]) -> bool:
        """Check if this group should be visible given current form values."""
        if not self.visible_when:
            return True
        for key, expected_value in self.visible_when.items():
            if current_values.get(key) != expected_value:
                return False
        return True


# ============================================================
# Extrapolation Method Specifications
# ============================================================

# Power Law Method Parameters
POWER_LAW_PARAMS = ParameterGroupSpec(
    group_key="power_law_params",
    title_zh="幂律参数",
    title_en="Power-law parameters",
    parameters=[
        NumberWidgetSpec(
            name="x1",
            label_zh="x1：",
            label_en="x1:",
            default_value=10.0,
            number_type="float",
            tooltip_zh="第一个自变量值",
            tooltip_en="First x value",
        ),
        NumberWidgetSpec(
            name="x2",
            label_zh="x2：",
            label_en="x2:",
            default_value=20.0,
            number_type="float",
            tooltip_zh="第二个自变量值",
            tooltip_en="Second x value",
        ),
        NumberWidgetSpec(
            name="x3",
            label_zh="x3：",
            label_en="x3:",
            default_value=40.0,
            number_type="float",
            tooltip_zh="第三个自变量值",
            tooltip_en="Third x value",
        ),
        TextWidgetSpec(
            name="p",
            label_zh="自定义 p（可选）：",
            label_en="Custom p (optional):",
            default_value="",
            placeholder_zh="留空则自动求解 p",
            placeholder_en="Leave blank to solve p automatically",
            optional=True,
            tooltip_zh="幂指数，留空则自动求解",
            tooltip_en="Power exponent, auto-solved if blank",
        ),
    ],
    visible_when={"method": "power_law"},
)

# Richardson Method Parameters
RICHARDSON_PARAMS = ParameterGroupSpec(
    group_key="richardson_params",
    title_zh="Richardson 序列加速参数",
    title_en="Richardson acceleration parameters",
    parameters=[
        NumberWidgetSpec(
            name="p",
            label_zh="收敛幂指数 p：",
            label_en="Convergence power p:",
            default_value=2.0,
            number_type="float",
            min_value=0.1,
            max_value=10.0,
            step=0.1,
            decimals=2,
            tooltip_zh="误差展开的幂指数（f(h) ≈ f∞ + c·h^p），常见值 p=2（二阶方法）",
            tooltip_en="Power exponent in error expansion (f(h) ≈ f∞ + c·h^p), common value p=2 (second-order method)",
        ),
    ],
    visible_when={"method": "richardson"},
)

# Levin u-transform Parameters
LEVIN_U_PARAMS = ParameterGroupSpec(
    group_key="levin_u_params",
    title_zh="Levin u 变换参数",
    title_en="Levin u-transform parameters",
    parameters=[
        SelectWidgetSpec(
            name="variant",
            label_zh="变换类型：",
            label_en="Variant:",
            default_value="u",
            options=[
                ("u (最常用)", "u (most common)", "u"),
                ("t (级数)", "t (series)", "t"),
                ("v (积分)", "v (integrals)", "v"),
            ],
            tooltip_zh="变换类型（u最常用，t适用于级数，v用于积分）",
            tooltip_en="Transform type (u most common, t for series, v for integrals)",
        ),
        NumberWidgetSpec(
            name="order",
            label_zh="变换阶数：",
            label_en="Transform order:",
            default_value=2,
            number_type="int",
            min_value=1,
            max_value=10,
            step=1,
            decimals=0,
            tooltip_zh="变换阶数（越高越精确但需要更多项，至少需要 2N+1 项数据）",
            tooltip_en="Transform order (higher = more accurate but needs more terms, requires at least 2N+1 data points)",
        ),
        SelectWidgetSpec(
            name="weight",
            label_zh="权重函数：",
            label_en="Weight function:",
            default_value="default",
            options=[
                ("默认 (1)", "Default (1)", "default"),
                ("1/(n+1)", "1/(n+1)", "reciprocal"),
                ("1/(n+β)", "1/(n+β)", "reciprocal_beta"),
            ],
            tooltip_zh="权重函数类型（默认为1，可选倒数权重）",
            tooltip_en="Weight function type (default is 1, optional reciprocal weights)",
        ),
        NumberWidgetSpec(
            name="beta",
            label_zh="β 参数：",
            label_en="β parameter:",
            default_value=1.0,
            number_type="float",
            min_value=0.01,
            max_value=100.0,
            step=0.1,
            decimals=2,
            tooltip_zh="权重函数 ω(n) = 1/(n+β) 中的 β 参数",
            tooltip_en="β parameter in weight function ω(n) = 1/(n+β)",
            optional=True,  # Only shown when weight = "reciprocal_beta"
        ),
    ],
    visible_when={"method": "levin_u"},
)

# Custom Formula Parameters
CUSTOM_FORMULA_PARAMS = ParameterGroupSpec(
    group_key="custom_formula_params",
    title_zh="自定义公式",
    title_en="Custom formula",
    parameters=[
        TextAreaWidgetSpec(
            name="custom_formula",
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
    visible_when={"method": "custom"},
)

# Shanks and Wynn-epsilon have no additional parameters
SHANKS_PARAMS = ParameterGroupSpec(
    group_key="shanks_params",
    title_zh="Shanks 变换",
    title_en="Shanks transform",
    parameters=[],
    visible_when={"method": "shanks"},
)

WYNN_EPSILON_PARAMS = ParameterGroupSpec(
    group_key="wynn_epsilon_params",
    title_zh="Wynn-epsilon 算法",
    title_en="Wynn-epsilon algorithm",
    parameters=[],
    visible_when={"method": "wynn_epsilon"},
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
    parameter_groups: list[ParameterGroupSpec]
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
        name_zh="Richardson 序列加速(三点外推)",
        name_en="Richardson (3-point)",
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

ERROR_FORMULA_SPEC = TextAreaWidgetSpec(
    name="error_formula",
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
    return {
        # Levin beta parameter only visible when weight = "reciprocal_beta"
        "levin_u.beta": {
            "depends_on": "levin_u.weight",
            "visible_when": "reciprocal_beta",
        },
    }


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
        for param_spec in group.parameters:
            param_name = param_spec.name
            value = params.get(param_name)

            # Check required parameters
            if not param_spec.optional and (value is None or value == ""):
                errors.append(f"Parameter '{param_name}' is required")
                continue

            # Skip validation for empty optional parameters
            if param_spec.optional and (value is None or value == ""):
                continue

            # Validate number parameters
            if isinstance(param_spec, NumberWidgetSpec):
                # ``value`` is ``Any | None`` but the empty / None case
                # was filtered above. Use an explicit guard rather than
                # ``assert`` so the validation survives ``python -O``
                # (PyInstaller bundles can be built with optimisation).
                if value is None:
                    continue
                try:
                    num_value: float | int = (
                        float(value)
                        if param_spec.number_type == "float"
                        else int(value)
                    )
                    if param_spec.min_value is not None and num_value < param_spec.min_value:
                        errors.append(f"Parameter '{param_name}' must be >= {param_spec.min_value}")
                    if param_spec.max_value is not None and num_value > param_spec.max_value:
                        errors.append(f"Parameter '{param_name}' must be <= {param_spec.max_value}")
                except (ValueError, TypeError):
                    errors.append(f"Parameter '{param_name}' must be a valid number")

    return len(errors) == 0, errors


# ============================================================
# Export all public APIs
# ============================================================

__all__ = [
    # Widget specifications
    "WidgetSpec",
    "TextWidgetSpec",
    "NumberWidgetSpec",
    "SelectWidgetSpec",
    "TextAreaWidgetSpec",
    "ParameterGroupSpec",

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
    "ERROR_FORMULA_SPEC",

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
