"""
Internal package containing DataLab's LaTeX/extrapolation implementation.

Public users should continue to import from `data_extrapolation_latex_latest` for
backwards compatibility.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import derivatives, expression_engine, latex_formatting, latex_tables
    from .derivatives import numerical_partial_derivative, numerical_second_partial_derivative
    from .expression_engine import format_latex_formula, list_allowed_functions, safe_eval
    from .latex_formatting import (
        add_latex_spacing_to_number,
        add_spacing_to_number,
        format_result_with_uncertainty_latex,
        format_uncertainty_notation,
    )
    from .latex_tables import (
        ExtrapolationOptions,
        ExtrapolationResult,
        UncertainValue,
        generate_error_propagation_table,
        generate_latex_table,
        process_data_file,
    )


_SUBMODULES = {
    "derivatives",
    "expression_engine",
    "latex_formatting",
    "latex_tables",
}

_EXPORTS = {
    "numerical_partial_derivative": ("datalab_latex.derivatives", "numerical_partial_derivative"),
    "numerical_second_partial_derivative": ("datalab_latex.derivatives", "numerical_second_partial_derivative"),
    "format_latex_formula": ("datalab_latex.expression_engine", "format_latex_formula"),
    "list_allowed_functions": ("datalab_latex.expression_engine", "list_allowed_functions"),
    "safe_eval": ("datalab_latex.expression_engine", "safe_eval"),
    "add_latex_spacing_to_number": ("datalab_latex.latex_formatting", "add_latex_spacing_to_number"),
    "add_spacing_to_number": ("datalab_latex.latex_formatting", "add_spacing_to_number"),
    "format_result_with_uncertainty_latex": (
        "datalab_latex.latex_formatting",
        "format_result_with_uncertainty_latex",
    ),
    "format_uncertainty_notation": ("datalab_latex.latex_formatting", "format_uncertainty_notation"),
    "ExtrapolationOptions": ("datalab_latex.latex_tables", "ExtrapolationOptions"),
    "ExtrapolationResult": ("datalab_latex.latex_tables", "ExtrapolationResult"),
    "UncertainValue": ("datalab_latex.latex_tables", "UncertainValue"),
    "generate_error_propagation_table": ("datalab_latex.latex_tables", "generate_error_propagation_table"),
    "generate_latex_table": ("datalab_latex.latex_tables", "generate_latex_table"),
    "process_data_file": ("datalab_latex.latex_tables", "process_data_file"),
}


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*globals(), *_SUBMODULES, *_EXPORTS])

__all__ = [
    "derivatives",
    "expression_engine",
    "latex_formatting",
    "latex_tables",
    "ExtrapolationOptions",
    "ExtrapolationResult",
    "UncertainValue",
    "process_data_file",
    "generate_latex_table",
    "generate_error_propagation_table",
    "safe_eval",
    "format_latex_formula",
    "list_allowed_functions",
    "numerical_partial_derivative",
    "numerical_second_partial_derivative",
    "add_spacing_to_number",
    "add_latex_spacing_to_number",
    "format_uncertainty_notation",
    "format_result_with_uncertainty_latex",
]
