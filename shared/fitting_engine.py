from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import mpmath as mp

from fitting import (
    FitRunner,
    ModelProblem,
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
)
from fitting.auto_models import (
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)
from fitting.hp_fitter import FitResult
from fitting.diagnostics import attach_fit_diagnostics
from shared.bilingual import _dual_msg
from shared.precision import precision_guard


DIRECT_FIT_MODEL_TYPES = frozenset({"polynomial", "inverse_power", "power_limit", "pade", "custom"})


@dataclass(frozen=True)
class DirectFitInput:
    model_type: str
    x_series: Sequence[mp.mpf]
    y_series: Sequence[mp.mpf]
    sigma_series: Sequence[mp.mpf | None]
    weights: Sequence[mp.mpf] | None
    variable_map: Mapping[str, str]
    variable_data: Mapping[str, Sequence[mp.mpf]]
    target_series: Sequence[mp.mpf]
    target_column: str
    model_expr: str
    parameter_config: Mapping[str, Mapping[str, Any]]
    parameter_names: Sequence[str]
    template_expr: str | None = None
    template_params: Mapping[str, Any] | None = None
    poly_degree: int = 0
    inverse_min: int = 1
    inverse_max: int = 3
    pade_m: int = 1
    pade_n: int = 1
    precision: int = 80
    weighted: bool = False
    label: str = ""
    custom_constants: Mapping[str, str] | None = None
    refine_with_mcmc: bool = False


@dataclass(frozen=True)
class DirectFitOutput:
    fit_result: FitResult
    expression: str
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def execute_direct_fit(fit_input: DirectFitInput, *, verbose: bool = False) -> DirectFitOutput:
    """Run fitting models that do not require a killable subprocess boundary."""

    model_type = fit_input.model_type
    if model_type not in DIRECT_FIT_MODEL_TYPES:
        if model_type == "self_consistent":
            raise ValueError(
                _dual_msg(
                    "self_consistent 拟合仍由子进程路径执行。",
                    "self_consistent fitting still requires the subprocess execution path.",
                )
            )
        raise ValueError(
            _dual_msg(
                f"不支持的拟合模型: {model_type}",
                f"Unsupported fit model: {model_type}",
            )
        )

    logs: list[str] = []
    warnings: list[str] = []
    expression = fit_input.model_expr
    with precision_guard(fit_input.precision):
        if verbose:
            _emit_verbose_start(fit_input)
        if model_type in {"polynomial", "inverse_power"}:
            if model_type == "polynomial":
                definition = build_polynomial_definition(fit_input.poly_degree)
            else:
                definition = build_inverse_series_definition(
                    fit_input.inverse_min,
                    fit_input.inverse_max,
                )
            fit_result = fit_linear_model(
                definition,
                list(fit_input.x_series),
                list(fit_input.y_series),
                precision=fit_input.precision,
                weights=None if fit_input.weights is None else list(fit_input.weights),
                data_sigmas=list(fit_input.sigma_series),
            )
            expression = str(fit_result.details.get("expression", expression))
            logs.append(f"{definition.label} 完成。")
        elif model_type in {"power_limit", "pade", "custom"}:
            output = _execute_custom_like_fit(fit_input)
            fit_result = output.fit_result
            expression = output.expression
            logs.extend(output.logs)
            warnings.extend(output.warnings)
        else:  # pragma: no cover - guarded by DIRECT_FIT_MODEL_TYPES above.
            raise AssertionError(f"Unhandled direct fit model: {model_type}")
        if verbose:
            _emit_verbose_result(fit_result)
        diagnostic_warnings = attach_fit_diagnostics(
            fit_result,
            sigma_series=fit_input.sigma_series,
            weights=fit_input.weights,
            precision=fit_input.precision,
        )
        warnings.extend(diagnostic_warnings)
    return DirectFitOutput(
        fit_result=fit_result,
        expression=expression,
        logs=tuple(logs),
        warnings=tuple(warnings),
    )


def serialize_fit_result(result: FitResult, keep_digits: int) -> dict[str, Any]:
    return {
        "params": {key: _mp_to_string(value, keep_digits) for key, value in result.params.items()},
        "param_errors": {key: _mp_to_string(value, keep_digits) for key, value in result.param_errors.items()},
        "chi2": _mp_to_string(result.chi2, keep_digits),
        "reduced_chi2": _mp_to_string(result.reduced_chi2, keep_digits),
        "aic": _mp_to_string(result.aic, keep_digits),
        "bic": _mp_to_string(result.bic, keep_digits),
        "r2": _mp_to_string(result.r2, keep_digits),
        "rmse": _mp_to_string(result.rmse, keep_digits),
        "residuals": [_mp_to_string(value, keep_digits) for value in result.residuals],
        "fitted_curve": [_mp_to_string(value, keep_digits) for value in result.fitted_curve],
        "covariance": [[_mp_to_string(value, keep_digits) for value in row] for row in result.covariance],
        "param_errors_stat": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_stat.items()
        },
        "param_errors_sys": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_sys.items()
        },
        "param_errors_total": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_total.items()
        },
        "details": serialize_mp_tree(result.details, keep_digits),
    }


def deserialize_fit_result(payload: Mapping[str, Any]) -> FitResult:
    return FitResult(
        params={key: mp.mpf(value) for key, value in _required_mapping(payload, "params").items()},
        param_errors={
            key: mp.mpf(value)
            for key, value in _required_mapping(payload, "param_errors").items()
        },
        chi2=mp.mpf(payload["chi2"]),
        reduced_chi2=mp.mpf(payload["reduced_chi2"]),
        aic=mp.mpf(payload["aic"]),
        bic=mp.mpf(payload["bic"]),
        r2=mp.mpf(payload["r2"]),
        rmse=mp.mpf(payload["rmse"]),
        residuals=[mp.mpf(value) for value in _required_sequence(payload, "residuals")],
        fitted_curve=[mp.mpf(value) for value in _required_sequence(payload, "fitted_curve")],
        covariance=[
            [mp.mpf(value) for value in row]
            for row in _required_sequence(payload, "covariance")
        ],
        param_errors_stat={
            key: mp.mpf(value)
            for key, value in _required_mapping(payload, "param_errors_stat").items()
        },
        param_errors_sys={
            key: mp.mpf(value)
            for key, value in _required_mapping(payload, "param_errors_sys").items()
        },
        param_errors_total={
            key: mp.mpf(value)
            for key, value in _required_mapping(payload, "param_errors_total").items()
        },
        details=dict(payload.get("details") or {}),
    )


def serialize_mp_tree(value: Any, keep_digits: int) -> Any:
    if isinstance(value, mp.mpf):
        return _mp_to_string(value, keep_digits)
    if isinstance(value, float):
        return _mp_to_string(value, keep_digits)
    if isinstance(value, (str, int, bool, type(None))):
        return value
    if isinstance(value, Mapping):
        return {str(key): serialize_mp_tree(item, keep_digits) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [serialize_mp_tree(item, keep_digits) for item in value]
    return repr(value)


def _execute_custom_like_fit(fit_input: DirectFitInput) -> DirectFitOutput:
    model_type = fit_input.model_type
    expr = fit_input.template_expr if model_type in {"power_limit", "pade"} else fit_input.model_expr
    params = fit_input.template_params if model_type in {"power_limit", "pade"} else fit_input.parameter_config
    if expr is None:
        expr = ""
    var_names = list(fit_input.variable_map.keys()) or ["x"]
    param_keys = list(params.keys()) if params else []
    parameter_names: list[str] = []
    seen: set[str] = set()
    for name in param_keys + list(fit_input.parameter_names):
        if name in seen:
            continue
        parameter_names.append(name)
        seen.add(name)
    if not parameter_names:
        parameter_names = param_keys
    if model_type == "custom":
        problem = ModelProblem(
            model_type="custom",
            expression=expr,
            variables=tuple(var_names),
            target_name=fit_input.target_column,
            parameter_config={name: (params or {}).get(name, {}) for name in parameter_names},
            constants=dict(fit_input.custom_constants or {}),
            constants_enabled=True,
        )
        fit_result = FitRunner().fit(
            problem,
            {key: list(values) for key, values in fit_input.variable_data.items()},
            list(fit_input.target_series),
            precision=fit_input.precision,
            weights=None if fit_input.weights is None else list(fit_input.weights),
            data_sigmas=list(fit_input.sigma_series),
        )
    else:
        spec = build_model_specification(expr, var_names, parameter_names, None)
        state = build_parameter_state(params or {}, parameter_names)
        fit_result = fit_custom_model(
            spec,
            state,
            {key: list(values) for key, values in fit_input.variable_data.items()},
            list(fit_input.target_series),
            precision=fit_input.precision,
            weights=None if fit_input.weights is None else list(fit_input.weights),
            data_sigmas=list(fit_input.sigma_series),
        )
    return DirectFitOutput(
        fit_result=fit_result,
        expression=expr,
        logs=(f"{model_type} 拟合完成。",),
    )


def _emit_verbose_start(fit_input: DirectFitInput) -> None:
    try:
        print(
            f"[fit] model={fit_input.model_type} label={fit_input.label} "
            f"target={fit_input.target_column} vars={list(fit_input.variable_map.keys()) or ['x']} "
            f"n={len(fit_input.x_series)} precision={fit_input.precision} weighted={fit_input.weighted}"
        )
        if fit_input.model_expr:
            print(f"[fit] expression={fit_input.model_expr}")
        if fit_input.parameter_config:
            print(f"[fit] initial_params={fit_input.parameter_config}")
    except Exception:
        pass


def _emit_verbose_result(fit_result: FitResult) -> None:
    try:
        print(f"[fit] params={fit_result.params}")
        print(
            f"[fit] chi2={fit_result.chi2} reduced_chi2={fit_result.reduced_chi2} "
            f"r2={fit_result.r2} rmse={fit_result.rmse}"
        )
        if fit_result.param_errors_total:
            print(f"[fit] param_errors_total={fit_result.param_errors_total}")
    except Exception:
        pass


def _mp_to_string(value: Any, keep_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, keep_digits)))


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"fit_result.{key} must be an object.")
    return value


def _required_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = payload[key]
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"fit_result.{key} must be a sequence.")
    # Annotate explicitly rather than cast(): older mypy sees the narrowed value
    # as Any (needs the annotation), newer mypy flags a cast as redundant. The
    # typed assignment satisfies both.
    result: Sequence[Any] = value
    return result
