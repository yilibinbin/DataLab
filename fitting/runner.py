"""Unified fitting runner boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mpmath import mp

from shared.bilingual import _dual_msg

from .constraints import build_parameter_state
from .hp_fitter import (
    FitResult,
    _compute_covariance,
    _compute_statistics,
    _prepare_points,
    combine_error_components,
    fit_custom_model,
)
from .implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
from . import implicit_model as _implicit_model
from .implicit_model import (
    ImplicitModelDefinition,
    build_implicit_model_specification,
)
from .model_parser import ModelSpecification, build_model_specification, infer_parameter_names
from .problem import ModelProblem, constants_for_compute


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
                result.details["implicit_strategy"] = "observed_linear"
                result.details["optimizer_backend"] = "mpmath_qr"
                return result
            except ValueError:
                pass

        if classification.strategy is ImplicitStrategy.OBSERVED_NONLINEAR:
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
                nonlinear_fallback_reason = str(exc)
            else:
                nonlinear_fallback_reason = ""
        else:
            nonlinear_fallback_reason = ""

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
        result.details["implicit_strategy"] = classification.strategy.value
        if classification.strategy is ImplicitStrategy.OBSERVED_LINEAR:
            result.details["implicit_strategy_fallback"] = "observed_linear_fast_path_unavailable"
        elif classification.strategy is ImplicitStrategy.OBSERVED_NONLINEAR:
            result.details["implicit_strategy_fallback"] = "direct_observed_nonlinear_optimizer_unavailable"
            if nonlinear_fallback_reason:
                result.details["implicit_strategy_fallback_reason"] = nonlinear_fallback_reason
        result.details["optimizer_backend"] = "mpmath_high_precision"
        return result


def _can_try_scipy(problem: ModelProblem, precision: int) -> bool:
    return precision <= 16 and problem.model_type in {"custom", "self_consistent"}


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
    parameter_state,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    *,
    weights: list[mp.mpf] | None,
    data_sigmas: list[mp.mpf | None] | None,
) -> _SciPyCandidate:
    import numpy as np
    from scipy.optimize import least_squares

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

    def _residual_vector(values) -> np.ndarray:
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


def _jacobian_condition_estimate(jacobian) -> float:
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


def _dependent_zero_errors(parameter_state, params: dict[str, mp.mpf]) -> dict[str, mp.mpf]:
    errors: dict[str, mp.mpf] = {}
    for name in params:
        if name not in parameter_state.free_params:
            errors[name] = mp.mpf("0")
    return errors


def _mp_is_finite(value: mp.mpf) -> bool:
    return not mp.isnan(value) and not mp.isinf(value)
