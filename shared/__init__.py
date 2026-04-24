"""
Shared specifications and utilities package.

This package contains shared specifications used by both desktop GUI and web interface
to ensure perfect alignment and consistency.
"""

from .ui_specs import *
from formula_help import (
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
)

__all__ = [
    # Re-export everything from ui_specs
    "WidgetSpec",
    "TextWidgetSpec",
    "NumberWidgetSpec",
    "SelectWidgetSpec",
    "TextAreaWidgetSpec",
    "ParameterGroupSpec",
    "MethodSpec",
    "EXTRAPOLATION_METHOD_SPECS",
    "METHOD_DISPLAY_ORDER",
    "get_method_options",
    "POWER_LAW_PARAMS",
    "RICHARDSON_PARAMS",
    "LEVIN_U_PARAMS",
    "CUSTOM_FORMULA_PARAMS",
    "SHANKS_PARAMS",
    "WYNN_EPSILON_PARAMS",
    "ERROR_FORMULA_SPEC",
    "FunctionHelpSpec",
    "CUSTOM_FORMULA_FUNCTION_HELP",
    "ERROR_FORMULA_FUNCTION_HELP",
    "MethodHelpButtonSpec",
    "METHOD_HELP_BUTTON",
    "get_parameter_visibility_rules",
    "validate_method_parameters",
    "get_function_help",
    "get_function_tooltip",
    "get_method_description",
    "get_method_name",
]
