"""High-precision fitting toolkit for the GUI."""

from .model_parser import ModelSpecification, build_model_specification, infer_parameter_names
from .constraints import ParameterState, build_parameter_state
from .hp_fitter import FitResult, fit_custom_model
from .auto_models import (
    AUTO_MODELS,
    build_linear_evaluator,
    build_inverse_series_definition,
    build_polynomial_definition,
)
from .model_selector import AutoFitSummary, auto_fit_dataset
from .report import summarize_fit_result, summarize_auto_results

try:
    from .plot_fitting import render_fitting_overview, sample_mp_function
except ImportError as exc:  # pragma: no cover - optional dependency guard
    def _plotting_missing(*_args, **_kwargs):
        raise ImportError(
            "Matplotlib/numpy is required for plotting helpers but is not available."
        ) from exc

    render_fitting_overview = _plotting_missing  # type: ignore
    sample_mp_function = _plotting_missing  # type: ignore

__all__ = [
    "ModelSpecification",
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
    "AutoFitSummary",
    "auto_fit_dataset",
    "render_fitting_overview",
    "sample_mp_function",
    "summarize_fit_result",
    "summarize_auto_results",
]
