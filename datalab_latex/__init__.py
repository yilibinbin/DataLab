"""
Internal package containing DataLab's LaTeX/extrapolation implementation.

Public users should continue to import from `data_extrapolation_latex_latest` for
backwards compatibility.
"""

from __future__ import annotations

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
