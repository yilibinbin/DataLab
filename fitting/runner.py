"""Unified fitting runner boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from mpmath import mp

from shared.bilingual import _dual_msg

from .constraints import ParameterState, build_parameter_state
from .hp_fitter import (
    FitResult,
    _compute_covariance,
    _compute_statistics,
    _prepare_points,
    combine_error_components,
    fit_custom_model,
)
from .implicit_model import (
    ImplicitModelDefinition,
    build_implicit_model_specification,
    fit_observed_implicit_variable_linear_model,
)
from .implicit_planner import ImplicitPlanKind, plan_implicit_fit
from .implicit_transforms import OutputTransform
from .model_parser import ModelSpecification, build_model_specification, infer_parameter_names
from .problem import ModelProblem, constants_for_compute
from .statistics import compute_fit_statistics


@dataclass(frozen=True)
class _SciPyCandidate:
    result: FitResult
    scipy_success: bool
    scipy_message: str
    condition: float
    spotcheck_ok: bool


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
        fallback_history: list[dict[str, object]] = []
        if _can_try_scipy(problem, precision):
            if state.dependent_defs:
                fallback_history.append(
                    {
                        "from": "scipy_least_squares",
                        "to": "mpmath_high_precision",
                        "reason": "dependent parameter error propagation is not implemented for SciPy",
                    }
                )
            else:
                try:
                    candidate = _fit_with_scipy_least_squares(
                        spec,
                        state,
                        variable_data,
                        target_data,
                        weights=weights,
                        data_sigmas=data_sigmas,
                    )
                    start_norm = _weighted_residual_norm(
                        spec,
                        state.compose(state.initial_vector()),
                        variable_data,
                        target_data,
                        weights,
                    )
                    accepted, reason = _accept_scipy_result(
                        candidate.result,
                        start_norm,
                        candidate.condition,
                        candidate.spotcheck_ok,
                    )
                    if accepted:
                        candidate.result.details["optimizer_backend"] = "scipy_least_squares"
                        candidate.result.details["scipy_safety_passed"] = True
                        return candidate.result
                    fallback_history.append(
                        {
                            "from": "scipy_least_squares",
                            "to": "mpmath_high_precision",
                            "reason": reason,
                            "condition": candidate.condition,
                        }
                    )
                except Exception as exc:
                    fallback_history.append(
                        {
                            "from": "scipy_least_squares",
                            "to": "mpmath_high_precision",
                            "reason": f"scipy unavailable or failed: {exc}",
                        }
                    )

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
        if fallback_history:
            result.details["fallback_history"] = fallback_history
            result.details["scipy_safety_passed"] = False
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
        plan = plan_implicit_fit(definition, precision=precision)
        fallback_history: list[dict[str, str]] = []
        if plan.kind is ImplicitPlanKind.OBSERVED_LINEAR:
            try:
                result = fit_observed_implicit_variable_linear_model(
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
                result.details["implicit_strategy"] = "observed_linear"
                result.details["optimizer_backend"] = "mpmath_qr"
                return result
            except ValueError as exc:
                fallback_history.append({"from": "observed_linear", "to": "general", "reason": str(exc)})

        if plan.kind is ImplicitPlanKind.EXACT_AFFINE_OUTPUT and plan.transform is not None:
            if weights is None and data_sigmas is not None and any(sigma is not None for sigma in data_sigmas):
                fallback_history.append(
                    {
                        "from": "exact_affine_output",
                        "to": "general",
                        "skipped": "unweighted_data_sigmas",
                    }
                )
            else:
                try:
                    with mp.workdps(precision):
                        transformed_targets = plan.transform.transformed_targets(variable_data, target_data)
                        transformed_weights = plan.transform.transformed_weights(variable_data, weights)
                        transformed_sigmas = plan.transform.transformed_sigmas(variable_data, data_sigmas)
                    observed_definition = ImplicitModelDefinition(
                        x_variables=definition.x_variables,
                        implicit_variable=definition.implicit_variable,
                        equation=definition.equation,
                        output_expression=definition.implicit_variable,
                        parameters=definition.parameters,
                        constants=definition.constants,
                        solve_options=definition.solve_options,
                    )
                    observed_plan = plan_implicit_fit(observed_definition, precision=precision)
                    if observed_plan.kind is not ImplicitPlanKind.OBSERVED_LINEAR:
                        raise ValueError("Exact affine output fast path requires an observed-linear implicit equation.")
                    result = fit_observed_implicit_variable_linear_model(
                        observed_definition,
                        state,
                        variable_data,
                        transformed_targets,
                        precision=precision,
                        weights=transformed_weights,
                        data_sigmas=transformed_sigmas,
                    )
                    result.details["implicit_diagnostics"] = {
                        "points_solved": 0,
                        "root_fallbacks": 0,
                        "max_iterations_used": 0,
                        "max_residual": "0",
                    }
                    result.details["implicit_strategy"] = "exact_affine_output_observed_linear"
                    result.details["optimizer_backend"] = "mpmath_qr"
                    result.details["output_transform"] = plan.transform.reason
                    with mp.workdps(precision):
                        return _remap_affine_result_to_output_space(
                            result,
                            plan.transform,
                            variable_data,
                            target_data,
                            weights,
                            free_param_count=len(state.free_params),
                        )
                except ValueError as exc:
                    fallback_history.append({"from": "exact_affine_output", "to": "general", "reason": str(exc)})

        if plan.kind is ImplicitPlanKind.OBSERVED_NONLINEAR:
            try:
                observed_variable_data = dict(variable_data)
                observed_variable_data[definition.implicit_variable] = target_data
                spec = build_model_specification(
                    definition.equation,
                    [*definition.x_variables, definition.implicit_variable],
                    definition.parameters,
                    definition.constants,
                )
                result = fit_custom_model(
                    spec,
                    state,
                    observed_variable_data,
                    target_data,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
                result.details["implicit_strategy"] = "observed_nonlinear"
                result.details["optimizer_backend"] = "mpmath_high_precision"
                result.details["implicit_diagnostics"] = {
                    "points_solved": 0,
                    "root_fallbacks": 0,
                    "max_iterations_used": 0,
                    "max_residual": "0",
                    "direct_observed_residual": True,
                }
                return result
            except ValueError as exc:
                fallback_history.append({"from": "observed_nonlinear", "to": "general", "reason": str(exc)})

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
        result.details["implicit_strategy"] = "general_implicit_numeric_finite_difference"
        if plan.kind in {
            ImplicitPlanKind.SCIPY_IMPLICIT,
            ImplicitPlanKind.ANALYTIC_IMPLICIT_JACOBIAN,
        }:
            result.details["implicit_planned_strategy"] = plan.kind.value
        if fallback_history:
            result.details["fallback_history"] = fallback_history
        result.details["optimizer_backend"] = "mpmath_high_precision"
        return result


def _can_try_scipy(problem: ModelProblem, precision: int) -> bool:
    return precision <= 16 and problem.model_type == "custom"


def _accept_scipy_result(
    candidate: FitResult,
    start_norm: float,
    condition: float,
    spotcheck_ok: bool,
) -> tuple[bool, str]:
    if not candidate.details.get("scipy_success"):
        return False, "scipy did not report convergence"
    if not all(_mp_is_finite(value) for value in candidate.fitted_curve + candidate.residuals):
        return False, "non-finite residuals or fitted values"
    if not _mp_is_finite(candidate.chi2) or float(candidate.chi2) > start_norm:
        return False, "weighted residual norm is not improved"
    if not condition < float("inf") or condition > 1e12:
        return False, "jacobian condition estimate exceeds 1e12"
    if not spotcheck_ok:
        return False, "mpmath spot-check disagrees with SciPy model values"
    return True, "accepted"


def _fit_with_scipy_least_squares(
    model: ModelSpecification,
    parameter_state: ParameterState,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    *,
    weights: list[mp.mpf] | None,
    data_sigmas: list[mp.mpf | None] | None,
) -> _SciPyCandidate:
    import numpy as np
    from scipy.optimize import least_squares  # type: ignore[import-untyped]

    observations, targets = _prepare_points(variable_data, target_data)
    if len(targets) != len(observations):
        raise ValueError(
            _dual_msg(
                "因变量的数据点数量必须与自变量一致。",
                "Dependent variable length must match independent variables.",
            )
        )
    scipy_weights = _normalise_scipy_weights(weights, len(targets))
    sqrt_weights = np.sqrt(np.asarray(scipy_weights, dtype=float)) if scipy_weights is not None else None
    lower: list[float] = []
    upper: list[float] = []
    for name in parameter_state.free_params:
        lo, hi = parameter_state.bounds.get(name, (None, None))
        lower.append(float(lo) if lo is not None else -np.inf)
        upper.append(float(hi) if hi is not None else np.inf)
    x0 = np.asarray([float(value) for value in parameter_state.initial_vector()], dtype=float)

    def _residual_vector(values: Sequence[float]) -> Any:
        params = parameter_state.compose(tuple(mp.mpf(str(float(value))) for value in values))
        residuals = []
        for idx, (obs, target) in enumerate(zip(observations, targets)):
            residual = float(model.evaluate(obs, params) - target)
            if sqrt_weights is not None:
                residual *= float(sqrt_weights[idx])
            residuals.append(residual)
        return np.asarray(residuals, dtype=float)

    scipy_result = least_squares(
        _residual_vector,
        x0,
        bounds=(np.asarray(lower), np.asarray(upper)),
    )
    solution = tuple(mp.mpf(str(float(value))) for value in scipy_result.x)
    params = parameter_state.compose(solution)
    (
        fitted_curve,
        residuals,
        chi2,
        reduced,
        r2,
        rmse,
        aic,
        bic,
        dof,
    ) = _compute_statistics(
        model,
        params,
        observations,
        targets,
        len(parameter_state.free_params),
        [mp.mpf(str(weight)) for weight in scipy_weights] if scipy_weights is not None else None,
    )
    covariance, stat_errors, cov_warning = _compute_covariance(
        model,
        params,
        observations,
        targets,
        parameter_state.free_params,
        chi2,
        dof if dof > 0 else 1,
        [mp.mpf(str(weight)) for weight in scipy_weights] if scipy_weights is not None else None,
    )
    stat_errors.update(_dependent_zero_errors(parameter_state, params))
    for name in model.parameters:
        stat_errors.setdefault(name, mp.mpf("0"))
    stat_errors, sys_errors, total_errors = combine_error_components(params, stat_errors, {})
    details: dict[str, object] = {
        "expression": getattr(model, "expression", ""),
        "dof": int(dof),
        "scipy_success": bool(scipy_result.success),
        "scipy_message": str(scipy_result.message),
        "scipy_cost": float(scipy_result.cost),
    }
    if scipy_weights is not None:
        details["weighted"] = True
    if data_sigmas is not None and scipy_weights is not None:
        details["uncertainty_note"] = {
            "zh": "已用数据不确定度进行加权，仅统计误差；为避免双计，未单独计算系统误差。",
            "en": "Data uncertainties were used for weighting (statistical only); to avoid double-counting, no separate systematic error was added.",
        }
    if cov_warning:
        details["covariance_warning"] = cov_warning
    fit_result = FitResult(
        params=params,
        param_errors=total_errors,
        chi2=chi2,
        reduced_chi2=reduced,
        aic=aic,
        bic=bic,
        r2=r2,
        rmse=rmse,
        residuals=residuals,
        fitted_curve=fitted_curve,
        covariance=covariance,
        param_errors_stat=stat_errors,
        param_errors_sys=sys_errors,
        param_errors_total=total_errors,
        details=details,
    )
    condition = _jacobian_condition_estimate(scipy_result.jac)
    spotcheck_ok = _spotcheck_scipy_solution(model, observations, params, fitted_curve)
    fit_result.details["scipy_jacobian_condition"] = condition
    fit_result.details["scipy_spotcheck_ok"] = spotcheck_ok
    return _SciPyCandidate(
        result=fit_result,
        scipy_success=bool(scipy_result.success),
        scipy_message=str(scipy_result.message),
        condition=condition,
        spotcheck_ok=spotcheck_ok,
    )


def _normalise_scipy_weights(weights: list[mp.mpf] | None, row_count: int) -> list[float] | None:
    if not weights:
        return None
    if len(weights) != row_count:
        raise ValueError(
            _dual_msg(
                "权重数量必须与数据点数量一致。",
                "Weight count must match number of data points.",
            )
        )
    normalized = [float(mp.mpf(weight)) for weight in weights]
    if any(weight <= 0 or not mp.isfinite(weight) for weight in normalized):
        raise ValueError(
            _dual_msg(
                "权重必须为正且有限。",
                "Weights must be positive and finite.",
            )
        )
    return normalized


def _weighted_residual_norm(
    model: ModelSpecification,
    params: dict[str, mp.mpf],
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
) -> float:
    observations, targets = _prepare_points(variable_data, target_data)
    total = mp.mpf("0")
    for idx, (obs, target) in enumerate(zip(observations, targets)):
        residual = model.evaluate(obs, params) - target
        weight = mp.mpf(weights[idx]) if weights else mp.mpf("1")
        total += weight * residual * residual
    return float(total)


def _remap_affine_result_to_output_space(
    result: FitResult,
    transform: OutputTransform,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
    *,
    free_param_count: int,
) -> FitResult:
    fitted = transform.forward_values(variable_data, result.fitted_curve)
    residuals = [mp.mpf(fit) - mp.mpf(target) for fit, target in zip(fitted, target_data)]
    stats = compute_fit_statistics(
        target_data,
        residuals,
        weights,
        free_param_count=free_param_count,
    )
    details = dict(result.details)
    details["output_space_remapped"] = True
    return replace(
        result,
        chi2=stats.chi2,
        reduced_chi2=stats.reduced_chi2,
        aic=stats.aic,
        bic=stats.bic,
        r2=stats.r2,
        rmse=stats.rmse,
        residuals=residuals,
        fitted_curve=fitted,
        details=details,
    )


def _jacobian_condition_estimate(jacobian: Any) -> float:
    import numpy as np

    try:
        condition = float(np.linalg.cond(jacobian))
    except Exception:
        return float("inf")
    return condition if np.isfinite(condition) else float("inf")


def _spotcheck_scipy_solution(
    model: ModelSpecification,
    observations: Sequence[dict[str, mp.mpf]],
    params: dict[str, mp.mpf],
    fitted_curve: Sequence[mp.mpf],
) -> bool:
    if not observations:
        return False
    indices = sorted({0, len(observations) // 2, len(observations) - 1})
    for index in indices:
        expected = mp.mpf(fitted_curve[index])
        actual = model.evaluate(observations[index], params)
        scale = max(mp.mpf("1"), mp.fabs(expected), mp.fabs(actual))
        if mp.fabs(actual - expected) > max(mp.mpf("1e-10"), mp.mpf("1e-8") * scale):
            return False
    return True


def _dependent_zero_errors(parameter_state: ParameterState, params: dict[str, mp.mpf]) -> dict[str, mp.mpf]:
    errors: dict[str, mp.mpf] = {}
    for name in params:
        if name not in parameter_state.free_params:
            errors[name] = mp.mpf("0")
    return errors


def _mp_is_finite(value: mp.mpf) -> bool:
    return not mp.isnan(value) and not mp.isinf(value)
