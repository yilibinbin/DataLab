from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootProblem, RootResult, RootValue
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

_COMPLEX_UNCERTAINTY_WARNING = "Linear uncertainty propagation is only supported for real-valued roots."
_JACOBIAN_WARNING = "Linear uncertainty propagation skipped: root Jacobian is singular or non-finite."
_ILL_CONDITIONED_WARNING = "Linear uncertainty propagation skipped: root Jacobian is ill-conditioned."
_INPUT_UNCERTAINTY_WARNING = "Linear uncertainty propagation skipped: input uncertainties must be finite and non-negative."


def attach_linear_uncertainty(
    problem: RootProblem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
) -> RootResult:
    return attach_linear_uncertainty_with_system(
        build_root_expression_system(problem),
        result,
        uncertain_inputs,
        precision=problem.precision,
    )


def attach_linear_uncertainty_with_system(
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    *,
    precision: int,
) -> RootResult:
    if not uncertain_inputs:
        return result
    if any(not _is_real_root(root.value) for root in result.roots):
        return _with_warning(result, _COMPLEX_UNCERTAINTY_WARNING)

    active_inputs = tuple(name for name in system.input_names if name in uncertain_inputs)
    if not active_inputs:
        return result

    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        sigmas = tuple(_input_sigma(uncertain_inputs[name]) for name in active_inputs)
        if any(sigma is None for sigma in sigmas):
            return _with_warning(result, _INPUT_UNCERTAINTY_WARNING)
        input_sigmas = cast(tuple[mp.mpf, ...], sigmas)
        unknown_values = {root.name: cast(mp.mpf, root.value) for root in result.roots}

        try:
            j_z = _unknown_jacobian(system, unknown_values)
            condition = _condition_number(j_z)
        except Exception:  # noqa: BLE001
            return _with_warning(result, _JACOBIAN_WARNING)
        if condition is None or not mp.isfinite(condition):
            return _with_warning(result, _JACOBIAN_WARNING)
        if condition > _ill_conditioning_threshold():
            return _with_condition_and_warning(result, condition, _ILL_CONDITIONED_WARNING)

        try:
            if result.mode == "scalar":
                roots = _attach_scalar_uncertainty(system, result.roots, unknown_values, active_inputs, input_sigmas)
            elif result.mode == "system":
                roots = _attach_system_uncertainty(system, result.roots, unknown_values, active_inputs, input_sigmas, j_z)
            else:
                return result
        except Exception:  # noqa: BLE001
            return _with_condition_and_warning(result, condition, _JACOBIAN_WARNING)

    return replace(result, roots=roots, jacobian_condition=condition)


def _attach_scalar_uncertainty(
    system: RootExpressionSystem,
    roots: Sequence[RootValue],
    unknown_values: Mapping[str, mp.mpf],
    active_inputs: Sequence[str],
    input_sigmas: Sequence[mp.mpf],
) -> tuple[RootValue, ...]:
    root = roots[0]
    unknown_name = root.name
    f_z = system.derivative_unknown(unknown_name, unknown_values, 0)
    if not _is_finite_nonzero(f_z):
        raise ValueError("singular scalar Jacobian")

    contributions: dict[str, mp.mpf] = {}
    variance = mp.mpf("0")
    for input_name, input_sigma in zip(active_inputs, input_sigmas, strict=True):
        f_p = system.derivative_input(input_name, unknown_values, 0)
        sensitivity = -f_p / f_z
        contribution = abs(sensitivity) * input_sigma
        if not mp.isfinite(contribution):
            raise ValueError("non-finite scalar uncertainty contribution")
        contributions[input_name] = contribution
        variance += contribution**2
    return (replace(root, uncertainty=mp.sqrt(variance), contributions=contributions),)


def _attach_system_uncertainty(
    system: RootExpressionSystem,
    roots: Sequence[RootValue],
    unknown_values: Mapping[str, mp.mpf],
    active_inputs: Sequence[str],
    input_sigmas: Sequence[mp.mpf],
    j_z: mp.matrix,
) -> tuple[RootValue, ...]:
    j_p = _input_jacobian(system, unknown_values, active_inputs)
    sensitivities = _solve_sensitivity_matrix(j_z, j_p)
    covariance = _covariance_from_sensitivities(sensitivities, input_sigmas)
    attached: list[RootValue] = []
    for row, root in enumerate(roots):
        diagonal = covariance[row, row]
        if not mp.isfinite(diagonal) or diagonal < 0:
            raise ValueError("non-finite system covariance")
        contributions = {
            input_name: abs(sensitivities[row, column]) * input_sigmas[column]
            for column, input_name in enumerate(active_inputs)
        }
        if any(not mp.isfinite(value) for value in contributions.values()):
            raise ValueError("non-finite system uncertainty contribution")
        attached.append(replace(root, uncertainty=mp.sqrt(diagonal), contributions=contributions))
    return tuple(attached)


def _unknown_jacobian(system: RootExpressionSystem, unknown_values: Mapping[str, mp.mpf]) -> mp.matrix:
    rows = len(system.expressions)
    columns = len(system.unknown_names)
    matrix = mp.matrix(rows, columns)
    for row in range(rows):
        for column, name in enumerate(system.unknown_names):
            matrix[row, column] = system.derivative_unknown(name, unknown_values, row)
    _ensure_finite_matrix(matrix)
    return matrix


def _input_jacobian(
    system: RootExpressionSystem,
    unknown_values: Mapping[str, mp.mpf],
    active_inputs: Sequence[str],
) -> mp.matrix:
    matrix = mp.matrix(len(system.expressions), len(active_inputs))
    for row in range(len(system.expressions)):
        for column, name in enumerate(active_inputs):
            matrix[row, column] = system.derivative_input(name, unknown_values, row)
    _ensure_finite_matrix(matrix)
    return matrix


def _solve_sensitivity_matrix(j_z: mp.matrix, j_p: mp.matrix) -> mp.matrix:
    sensitivities = mp.matrix(j_z.rows, j_p.cols)
    for column in range(j_p.cols):
        rhs = mp.matrix([-j_p[row, column] for row in range(j_p.rows)])
        solution = mp.lu_solve(j_z, rhs)
        for row in range(j_z.rows):
            sensitivities[row, column] = solution[row]
    _ensure_finite_matrix(sensitivities)
    return sensitivities


def _covariance_from_sensitivities(sensitivities: mp.matrix, input_sigmas: Sequence[mp.mpf]) -> mp.matrix:
    covariance = mp.matrix(sensitivities.rows, sensitivities.rows)
    for row in range(sensitivities.rows):
        for other_row in range(sensitivities.rows):
            total = mp.mpf("0")
            for column, sigma in enumerate(input_sigmas):
                total += sensitivities[row, column] * sensitivities[other_row, column] * sigma**2
            covariance[row, other_row] = total
    _ensure_finite_matrix(covariance)
    return covariance


def _condition_number(matrix: mp.matrix) -> mp.mpf | None:
    try:
        value = mp.mpf(mp.cond(matrix))
    except Exception:
        return None
    return value if mp.isfinite(value) else None


def _ill_conditioning_threshold() -> mp.mpf:
    return 1 / mp.sqrt(mp.eps)


def _input_sigma(value: UncertainValue) -> mp.mpf | None:
    sigma = mp.mpf(value.uncertainty)
    if not mp.isfinite(sigma) or sigma < 0:
        return None
    return sigma


def _ensure_finite_matrix(matrix: mp.matrix) -> None:
    for row in range(matrix.rows):
        for column in range(matrix.cols):
            if not mp.isfinite(matrix[row, column]):
                raise ValueError("matrix contains a non-finite value")


def _is_finite_nonzero(value: mp.mpf) -> bool:
    return bool(mp.isfinite(value) and value != 0)


def _is_real_root(value: object) -> bool:
    if isinstance(value, complex):
        return value.imag == 0
    if isinstance(value, mp.mpc):
        return bool(mp.im(value) == 0)
    return True


def _with_warning(result: RootResult, warning: str) -> RootResult:
    return replace(result, warnings=(*result.warnings, warning))


def _with_condition_and_warning(result: RootResult, condition: mp.mpf, warning: str) -> RootResult:
    return replace(result, jacobian_condition=condition, warnings=(*result.warnings, warning))
