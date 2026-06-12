"""High-precision fitting toolkit for the GUI."""

from collections.abc import Mapping
from typing import Any, Callable, cast

from .implicit_model import (
    ImplicitEvaluationCache,
    ImplicitModelDefinition,
    ImplicitSolveDiagnostics,
    ImplicitSolveOptions,
    build_implicit_model_specification,
    can_fit_observed_implicit_variable,
    fit_observed_implicit_variable_linear_model,
    quantum_defect_template,
)
from .model_parser import ModelSpecification, build_model_specification, infer_parameter_names
from .constraints import ParameterState, build_parameter_state as _build_parameter_state
from .hp_fitter import FitResult, fit_custom_model
from .implicit_classifier import ImplicitClassification, ImplicitProblemClassifier, ImplicitStrategy
from .problem import ModelProblem, ParameterDraft, constants_for_compute, parameters_for_compute
from .runner import FitRunner
from .auto_models import (
    AUTO_MODELS,
    build_linear_evaluator,
    build_inverse_series_definition,
    build_polynomial_definition,
)
from .report import summarize_fit_result


def build_parameter_state(parameter_config: Any, parameter_names: Any | None = None) -> ParameterState:
    """Public compatibility wrapper for parameter state construction."""

    if isinstance(parameter_config, (list, tuple)) and isinstance(parameter_names, dict):
        return _build_parameter_state(
            cast("Mapping[str, Mapping[str, object]]", parameter_names),
            list(parameter_config),
        )
    return _build_parameter_state(
        cast("Mapping[str, Mapping[str, object]]", parameter_config),
        cast("list[str]", parameter_names),
    )


def _plotting_helper(name: str) -> Callable[..., Any]:
    try:
        from . import plot_fitting
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        raise ImportError(
            "Matplotlib/numpy is required for plotting helpers but is not available."
        ) from exc
    return cast("Callable[..., Any]", getattr(plot_fitting, name))


def render_fitting_overview(*args: object, **kwargs: object) -> bytes:
    """Render the fitting overview, importing matplotlib only on demand."""

    return cast("bytes", _plotting_helper("render_fitting_overview")(*args, **kwargs))


def sample_mp_function(*args: object, **kwargs: object) -> Any:
    """Sample a high-precision function, importing plotting helpers on demand."""

    return _plotting_helper("sample_mp_function")(*args, **kwargs)

__all__ = [
    "ModelSpecification",
    "ImplicitEvaluationCache",
    "ImplicitModelDefinition",
    "ImplicitSolveDiagnostics",
    "ImplicitSolveOptions",
    "ImplicitClassification",
    "ImplicitProblemClassifier",
    "ImplicitStrategy",
    "ModelProblem",
    "ParameterDraft",
    "build_implicit_model_specification",
    "can_fit_observed_implicit_variable",
    "fit_observed_implicit_variable_linear_model",
    "quantum_defect_template",
    "build_model_specification",
    "infer_parameter_names",
    "ParameterState",
    "build_parameter_state",
    "FitResult",
    "FitRunner",
    "fit_custom_model",
    "constants_for_compute",
    "parameters_for_compute",
    "AUTO_MODELS",
    "build_linear_evaluator",
    "build_inverse_series_definition",
    "build_polynomial_definition",
    "render_fitting_overview",
    "sample_mp_function",
    "summarize_fit_result",
]
