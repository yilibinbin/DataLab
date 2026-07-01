"""Additive fitting diagnostics shared by desktop, Web, and LaTeX adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mpmath import mp

from shared.precision import precision_guard

from .hp_fitter import FitResult

_DIAGNOSTICS_KEY = "diagnostics"


def chi_square_p_value(chi2: object, dof: object, *, precision: int = 80) -> mp.mpf:
    """Return upper-tail chi-square survival probability Q(dof/2, chi2/2)."""

    with precision_guard(precision):
        try:
            chi2_val = mp.mpf(chi2)
            dof_val = int(str(dof))
        except Exception:
            return mp.nan
        if dof_val <= 0 or not mp.isfinite(chi2_val) or chi2_val < 0:
            return mp.nan
        shape = mp.mpf(dof_val) / 2
        cutoff = chi2_val / 2
        return mp.gammainc(shape, cutoff, mp.inf, regularized=True)


def attach_fit_diagnostics(
    fit_result: FitResult,
    *,
    sigma_series: Sequence[object | None] | None = None,
    weights: Sequence[object] | None = None,
    precision: int = 80,
) -> tuple[str, ...]:
    """Compute P2.1A diagnostics and store them under ``fit_result.details``."""

    diagnostics, warnings = compute_fit_diagnostics(
        fit_result,
        sigma_series=sigma_series,
        weights=weights,
        precision=precision,
    )
    fit_result.details[_DIAGNOSTICS_KEY] = diagnostics
    deduped_warnings = tuple(dict.fromkeys(warnings))
    if deduped_warnings:
        fit_result.details["diagnostic_warnings"] = list(deduped_warnings)
    else:
        fit_result.details.pop("diagnostic_warnings", None)
    return deduped_warnings


def compute_fit_diagnostics(
    fit_result: FitResult,
    *,
    sigma_series: Sequence[object | None] | None = None,
    weights: Sequence[object] | None = None,
    precision: int = 80,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    warnings: list[str] = []
    dof = _fit_dof(fit_result)
    p_value = chi_square_p_value(fit_result.chi2, dof, precision=precision)
    diagnostics: dict[str, Any] = {
        "chi_square_p_value": p_value,
        "dof": int(dof) if dof is not None else None,
    }

    correlation, correlation_warnings = parameter_correlation_matrix(fit_result)
    diagnostics["parameter_correlation"] = correlation
    warnings.extend(correlation_warnings)

    residuals, residual_warnings = standardized_residuals(
        fit_result,
        sigma_series=sigma_series,
        weights=weights,
    )
    diagnostics["residuals"] = residuals
    warnings.extend(residual_warnings)
    return diagnostics, tuple(warnings)


def parameter_correlation_matrix(fit_result: FitResult) -> tuple[dict[str, Any], tuple[str, ...]]:
    warnings: list[str] = []
    covariance = fit_result.covariance or []
    names = _covariance_parameter_names(fit_result, len(covariance))
    errors = fit_result.param_errors_stat or fit_result.param_errors or {}
    matrix: list[list[mp.mpf]] = []

    for i, cov_row in enumerate(covariance):
        out_row: list[mp.mpf] = []
        for j, cov_value in enumerate(cov_row):
            name_i = names[i] if i < len(names) else f"p{i + 1}"
            name_j = names[j] if j < len(names) else f"p{j + 1}"
            cell = _correlation_cell(
                cov_value,
                errors.get(name_i),
                errors.get(name_j),
                diagonal=i == j,
            )
            if mp.isnan(cell):
                warnings.append(
                    f"Parameter correlation {name_i},{name_j} unavailable because covariance or parameter error is non-finite or zero."
                )
            out_row.append(cell)
        matrix.append(out_row)

    return {
        "parameters": names,
        "matrix": matrix,
    }, tuple(dict.fromkeys(warnings))


def standardized_residuals(
    fit_result: FitResult,
    *,
    sigma_series: Sequence[object | None] | None = None,
    weights: Sequence[object] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    warnings: list[str] = []
    residuals = list(fit_result.residuals or [])
    sigma_values = _finite_positive_optional_series(sigma_series)
    weight_values = _finite_positive_series(weights)

    method = "normalized"
    label = "Normalized residual"
    values: list[mp.mpf] = []
    if sigma_values and len(sigma_values) == len(residuals):
        method = "sigma"
        label = "Sigma-standardized residual"
        for idx, (residual, sigma) in enumerate(zip(residuals, sigma_values), start=1):
            if sigma is None:
                values.append(mp.nan)
                warnings.append(f"Standardized residual {idx} unavailable because sigma is missing, non-finite, or zero.")
            else:
                values.append(mp.mpf(residual) / sigma)
    elif weight_values and len(weight_values) == len(residuals):
        method = "weight"
        label = "Weight-standardized residual"
        values = [mp.mpf(residual) * mp.sqrt(weight) for residual, weight in zip(residuals, weight_values)]
    else:
        rmse = mp.mpf(fit_result.rmse)
        if residuals and mp.isfinite(rmse) and rmse != 0:
            values = [mp.mpf(residual) / rmse for residual in residuals]
        else:
            values = [mp.nan for _ in residuals]
            if residuals:
                warnings.append("Normalized residuals unavailable because RMSE is non-finite or zero.")

    finite_abs = [mp.fabs(value) for value in values if mp.isfinite(value)]
    max_abs = max(finite_abs) if finite_abs else mp.nan
    return {
        "method": method,
        "label": label,
        "values": values,
        "max_abs": max_abs,
    }, tuple(dict.fromkeys(warnings))


def fit_diagnostics(fit_result: FitResult) -> Mapping[str, Any]:
    diagnostics = fit_result.details.get(_DIAGNOSTICS_KEY)
    return diagnostics if isinstance(diagnostics, Mapping) else {}


def fit_diagnostic_warnings(fit_result: FitResult) -> tuple[str, ...]:
    return tuple(_diagnostic_warning_texts(fit_result.details))


def _fit_dof(fit_result: FitResult) -> int | None:
    raw = fit_result.details.get("dof")
    try:
        if raw is not None:
            return int(str(raw))
    except Exception:
        pass
    residual_count = len(fit_result.residuals or [])
    parameter_count = len(_covariance_parameter_names(fit_result, len(fit_result.covariance or [])))
    return residual_count - parameter_count


def _covariance_parameter_names(fit_result: FitResult, covariance_size: int) -> list[str]:
    raw = fit_result.details.get("covariance_parameters")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray, memoryview)):
        names = [str(name) for name in raw]
        if len(names) >= covariance_size:
            return names[:covariance_size]
    return list(fit_result.params.keys())[:covariance_size]


def _correlation_cell(value: object, error_i: object, error_j: object, *, diagonal: bool) -> mp.mpf:
    try:
        cov = mp.mpf(value)
        err_i = mp.mpf(error_i)
        err_j = mp.mpf(error_j)
    except Exception:
        return mp.nan
    if not mp.isfinite(cov) or not mp.isfinite(err_i) or not mp.isfinite(err_j):
        return mp.nan
    if err_i == 0 or err_j == 0:
        return mp.nan
    if diagonal:
        return mp.mpf("1")
    corr = cov / (err_i * err_j)
    if not mp.isfinite(corr):
        return mp.nan
    return min(mp.mpf("1"), max(mp.mpf("-1"), corr))


def _finite_positive_optional_series(values: Sequence[object | None] | None) -> list[mp.mpf | None] | None:
    if values is None:
        return None
    normalized: list[mp.mpf | None] = []
    any_present = False
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        try:
            numeric = mp.mpf(value)
        except Exception:
            normalized.append(None)
            continue
        if mp.isfinite(numeric) and numeric > 0:
            any_present = True
            normalized.append(numeric)
        else:
            normalized.append(None)
    return normalized if any_present else None


def _finite_positive_series(values: Sequence[object] | None) -> list[mp.mpf] | None:
    if not values:
        return None
    normalized: list[mp.mpf] = []
    for value in values:
        try:
            numeric = mp.mpf(value)
        except Exception:
            return None
        if not mp.isfinite(numeric) or numeric <= 0:
            return None
        normalized.append(numeric)
    return normalized


def _diagnostic_warning_texts(details: Mapping[str, object]) -> tuple[str, ...]:
    raw = details.get("diagnostic_warnings")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray, memoryview)):
        return tuple(str(item) for item in raw if str(item))
    return ()
