"""Unified fitting runner boundary."""

from __future__ import annotations

from collections.abc import Sequence

from mpmath import mp

from shared.bilingual import _dual_msg

from .constraints import build_parameter_state
from .hp_fitter import FitResult, fit_custom_model
from .implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
from . import implicit_model as _implicit_model
from .implicit_model import (
    ImplicitModelDefinition,
    build_implicit_model_specification,
)
from .model_parser import build_model_specification, infer_parameter_names
from .problem import ModelProblem, constants_for_compute


class FitRunner:
    def fit(
        self,
        problem: ModelProblem,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        *,
        precision: int = 80,
        weights: list[mp.mpf] | None = None,
        data_sigmas: list[mp.mpf | None] | None = None,
    ) -> FitResult:
        if problem.model_type == "custom":
            return self._fit_custom(problem, variable_data, target_data, precision, weights, data_sigmas)
        if problem.model_type == "self_consistent":
            return self._fit_self_consistent(problem, variable_data, target_data, precision, weights, data_sigmas)
        raise ValueError(
            _dual_msg(
                f"不支持的拟合模型: {problem.model_type}",
                f"Unsupported fit model: {problem.model_type}",
            )
        )

    def _fit_custom(
        self,
        problem: ModelProblem,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        precision: int,
        weights: list[mp.mpf] | None,
        data_sigmas: list[mp.mpf | None] | None,
    ) -> FitResult:
        constants = constants_for_compute(problem)
        parameter_names = infer_parameter_names(
            problem.expression,
            problem.variables,
            list(problem.parameter_config.keys()),
            constants=list(constants),
        )
        spec = build_model_specification(problem.expression, list(problem.variables), parameter_names, constants)
        state = build_parameter_state(problem.parameter_config, parameter_names)
        result = fit_custom_model(
            spec,
            state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        result.details["optimizer_backend"] = "mpmath_high_precision"
        return result

    def _fit_self_consistent(
        self,
        problem: ModelProblem,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        precision: int,
        weights: list[mp.mpf] | None,
        data_sigmas: list[mp.mpf | None] | None,
    ) -> FitResult:
        definition = problem.implicit_definition
        if not isinstance(definition, ImplicitModelDefinition):
            raise ValueError(
                _dual_msg(
                    "自洽隐式模型缺少定义。",
                    "Self-consistent fit model requires an implicit definition.",
                )
            )
        state = build_parameter_state(problem.parameter_config or {}, list(definition.parameters))
        classification = ImplicitProblemClassifier().classify(definition)
        observed_linear_fit = getattr(_implicit_model, "fit_observed_implicit_variable_linear_model", None)
        if classification.strategy is ImplicitStrategy.OBSERVED_LINEAR and observed_linear_fit is not None:
            try:
                result = observed_linear_fit(
                    definition,
                    state,
                    variable_data,
                    target_data,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
                result.details["implicit_diagnostics"] = {
                    "points_solved": 0,
                    "root_fallbacks": 0,
                    "max_iterations_used": 0,
                    "max_residual": "0",
                }
                result.details["optimizer_backend"] = "mpmath_high_precision"
                return result
            except ValueError:
                pass

        spec = build_implicit_model_specification(definition)
        result = fit_custom_model(
            spec,
            state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        diagnostics = getattr(spec, "implicit_diagnostics")
        result.details["implicit_diagnostics"] = {
            "points_solved": int(diagnostics.points_solved),
            "root_fallbacks": int(diagnostics.root_fallbacks),
            "max_iterations_used": int(diagnostics.max_iterations_used),
            "max_residual": str(diagnostics.max_residual),
        }
        result.details["optimizer_backend"] = "mpmath_high_precision"
        return result
