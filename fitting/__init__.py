"""High-precision fitting toolkit for the GUI."""

from typing import NoReturn

from .implicit_model import (
    ImplicitEvaluationCache,
    ImplicitModelDefinition,
    ImplicitSolveDiagnostics,
    ImplicitSolveOptions,
    build_implicit_model_specification,
    quantum_defect_template,
)
from .model_parser import ModelSpecification, build_model_specification, infer_parameter_names
from .constraints import ParameterState, build_parameter_state
from .hp_fitter import FitResult, fit_custom_model
from .auto_models import (
    AUTO_MODELS,
    build_linear_evaluator,
    build_inverse_series_definition,
    build_polynomial_definition,
)
from .report import summarize_fit_result

try:
    from .plot_fitting import render_fitting_overview, sample_mp_function
except ImportError as exc:  # pragma: no cover - optional dependency guard
    def _plotting_missing(*_args: object, **_kwargs: object) -> NoReturn:
        raise ImportError(
            "Matplotlib/numpy is required for plotting helpers but is not available."
        ) from exc

    render_fitting_overview = _plotting_missing
    sample_mp_function = _plotting_missing

__all__ = [
    "ModelSpecification",
    "ImplicitEvaluationCache",
    "ImplicitModelDefinition",
    "ImplicitSolveDiagnostics",
    "ImplicitSolveOptions",
    "build_implicit_model_specification",
    "quantum_defect_template",
    "build_model_specification",
    "infer_parameter_names",
    "ParameterState",
    "build_parameter_state",
    "FitResult",
    "fit_custom_model",
    "AUTO_MODELS",
    "build_linear_evaluator",
    "build_inverse_series_definition",
    "build_polynomial_definition",
    "render_fitting_overview",
    "sample_mp_function",
    "summarize_fit_result",
]
