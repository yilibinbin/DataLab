from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
import math
from typing import Any, cast

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootBackend, RootMode, RootProblem, RootUnknown, RootValue, RootResult
from root_solving.uncertainty import attach_linear_uncertainty_with_system
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

_SCIPY_FALLBACK_WARNING = "SciPy validation failed; used mpmath fallback."
_COMPLEX_UNCERTAINTY_WARNING = "Linear uncertainty propagation is only supported for real-valued roots."


@dataclass(frozen=True)
class _Candidate:
    values: tuple[mp.mpf | mp.mpc | complex, ...]
    backend: RootBackend
    warnings: tuple[str, ...] = ()


def solve_root_problem(
    problem: RootProblem,
    *,
    uncertain_inputs: dict[str, UncertainValue] | None = None,
) -> RootResult:
    system = build_root_expression_system(problem)
    mode = _resolve_mode(problem, system)

    if problem.precision <= 16:
        if mode == "polynomial":
            candidate = _solve_polynomial_scipy_or_fallback(problem, system)
        else:
            candidate = _solve_with_scipy_or_fallback(problem, system, mode)
    else:
        candidate = _solve_mpmath(problem, system, mode)

    roots = _root_values(system.unknown_names, candidate.values, mode)
    residual_norm = _residual_norm(system, candidate.values, mode)
    if not mp.isfinite(residual_norm):
        raise ValueError("Solver returned a non-finite residual norm.")

    result = RootResult(
        roots=roots,
        backend=candidate.backend,
        mode=mode,
        residual_norm=residual_norm,
        warnings=candidate.warnings,
        details={
            "requested_mode": problem.mode,
            "resolved_mode": mode,
        },
    )
    if uncertain_inputs:
        if _all_roots_real(result.roots):
            return attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
        return replace(result, warnings=(*result.warnings, _COMPLEX_UNCERTAINTY_WARNING))
    return result


def _resolve_mode(problem: RootProblem, system: RootExpressionSystem) -> RootMode:
    requested = problem.mode
    equation_count = len(system.expressions)
    unknown_count = len(system.unknown_names)

    if requested == "auto":
        if equation_count == 1 and unknown_count == 1:
            return "scalar"
        if equation_count == unknown_count and unknown_count > 0:
            return "system"
        raise ValueError("Auto root-solving mode requires a scalar or square system.")
    if requested == "scalar" and (equation_count != 1 or unknown_count != 1):
        raise ValueError("Scalar root-solving mode requires exactly one equation and one unknown.")
    if requested == "polynomial" and (equation_count != 1 or unknown_count != 1):
        raise ValueError("Polynomial root-solving mode requires exactly one equation and one unknown.")
    if requested == "system" and (equation_count != unknown_count or unknown_count == 0):
        raise ValueError("System root-solving mode requires a non-empty square system.")
    return requested


def _solve_with_scipy_or_fallback(
    problem: RootProblem,
    system: RootExpressionSystem,
    mode: RootMode,
) -> _Candidate:
    try:
        candidate = _solve_scipy(problem, system, mode)
        _validate_candidate(system, candidate.values, mode, problem.precision)
    except Exception:  # noqa: BLE001
        fallback = _solve_mpmath(problem, system, mode)
        return _Candidate(fallback.values, fallback.backend, (*fallback.warnings, _SCIPY_FALLBACK_WARNING))
    return candidate


def _solve_polynomial_scipy_or_fallback(problem: RootProblem, system: RootExpressionSystem) -> _Candidate:
    try:
        candidate = _solve_polynomial_scipy(system)
        _validate_candidate(system, candidate.values, "polynomial", problem.precision)
    except Exception:  # noqa: BLE001
        fallback = _solve_mpmath(problem, system, "polynomial")
        return _Candidate(fallback.values, fallback.backend, (*fallback.warnings, _SCIPY_FALLBACK_WARNING))
    return candidate


def _solve_scipy(problem: RootProblem, system: RootExpressionSystem, mode: RootMode) -> _Candidate:
    import scipy.optimize  # type: ignore[import-untyped]

    if mode == "scalar":
        unknown = _single_unknown(problem)
        if unknown.lower and unknown.upper:
            lower = _parse_mpf(unknown.lower, "lower bound")
            upper = _parse_mpf(unknown.upper, "upper bound")

            def scalar_float(value: float) -> float:
                return float(system.evaluate({unknown.name: mp.mpf(str(value))}))

            result = scipy.optimize.root_scalar(scalar_float, bracket=(float(lower), float(upper)), method="brentq")
            if not result.converged:
                raise ValueError("SciPy scalar bracket solve did not converge.")
            return _Candidate((_finite_mpf(str(result.root), "SciPy scalar root"),), "scipy")

        initial = _initial_values(problem)[0]

        def scalar_vector(values: Sequence[float]) -> list[float]:
            return [float(system.evaluate({unknown.name: mp.mpf(str(values[0]))}))]

        result = scipy.optimize.root(scalar_vector, [float(initial)])
        if not bool(getattr(result, "success", False)):
            raise ValueError("SciPy scalar root solve did not converge.")
        return _Candidate((_finite_mpf(str(result.x[0]), "SciPy scalar root"),), "scipy")

    if mode != "system":
        raise ValueError(f"SciPy mode is not supported here: {mode}")

    unknown_names = system.unknown_names
    initials = _initial_values(problem)

    def system_vector(values: Sequence[float]) -> list[float]:
        scope = {name: mp.mpf(str(value)) for name, value in zip(unknown_names, values, strict=True)}
        return [float(value) for value in system.residuals(scope)]

    result = scipy.optimize.root(system_vector, [float(value) for value in initials])
    if not bool(getattr(result, "success", False)):
        raise ValueError("SciPy system root solve did not converge.")
    return _Candidate(tuple(_finite_mpf(str(value), "SciPy system root") for value in result.x), "scipy")


def _solve_polynomial_scipy(system: RootExpressionSystem) -> _Candidate:
    import numpy as np

    coefficients = _polynomial_coefficients(system)
    roots = np.roots([float(coefficient) for coefficient in coefficients])
    values = tuple(_mp_or_complex_from_number(root) for root in roots)
    return _Candidate(values, "scipy")


def _solve_mpmath(problem: RootProblem, system: RootExpressionSystem, mode: RootMode) -> _Candidate:
    with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if mode == "polynomial":
            coefficients = _polynomial_coefficients(system)
            values = tuple(_mp_or_complex_from_mpmath(root) for root in mp.polyroots(coefficients, maxsteps=200))
            return _Candidate(values, "mpmath")

        initials = _initial_values(problem)
        if mode == "scalar":
            unknown = _single_unknown(problem)
            guesses = _scalar_findroot_guesses(unknown, initials[0])

            def function(value: mp.mpf) -> mp.mpf:
                return system.evaluate({unknown.name: value})

            root = mp.findroot(function, guesses if len(guesses) > 1 else guesses[0])
            return _Candidate((_finite_mpf(root, "mpmath scalar root"),), "mpmath")

        unknown_names = system.unknown_names
        functions = tuple(_system_function(system, unknown_names, index) for index in range(len(system.expressions)))
        roots = mp.findroot(functions, initials)
        root_values = tuple(roots)
        return _Candidate(tuple(_finite_mpf(value, "mpmath system root") for value in root_values), "mpmath")


def _system_function(
    system: RootExpressionSystem,
    unknown_names: Sequence[str],
    equation_index: int,
) -> Callable[..., mp.mpf]:
    def function(*values: mp.mpf) -> mp.mpf:
        scope = {name: value for name, value in zip(unknown_names, values, strict=True)}
        return system.evaluate(scope, equation_index)

    return function


def _validate_candidate(
    system: RootExpressionSystem,
    values: Sequence[mp.mpf | complex],
    mode: RootMode,
    precision: int,
) -> None:
    if any(not _is_finite_number(value) for value in values):
        raise ValueError("Solver returned a non-finite root.")
    residual_norm = _residual_norm(system, values, mode)
    tolerance = _residual_tolerance(system, precision)
    if residual_norm > tolerance:
        raise ValueError("Solver residual exceeded tolerance.")


def _residual_tolerance(system: RootExpressionSystem, precision: int) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        target_scale = max((abs(value) for value in system.nominal_inputs.values()), default=mp.mpf("1"))
        target_scale = max(mp.mpf("1"), target_scale)
        return mp.mpf(str(max(1e-10, 100 * math.sqrt(float(mp.eps))))) * target_scale


def _residual_norm(system: RootExpressionSystem, values: Sequence[mp.mpf | mp.mpc | complex], mode: RootMode) -> mp.mpf:
    with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if mode == "polynomial":
            coefficients = _polynomial_coefficients(system)
            return max((_polynomial_residual_abs(coefficients, value) for value in values), default=mp.mpf("0"))
        scope = {name: value for name, value in zip(system.unknown_names, values, strict=True)}
        residuals = system.residuals(scope)
        return max((abs(residual) for residual in residuals), default=mp.mpf("0"))


def _polynomial_residual_abs(coefficients: Sequence[mp.mpf], value: mp.mpf | mp.mpc | complex) -> mp.mpf:
    total: mp.mpf | mp.mpc | complex = mp.mpf("0")
    for coefficient in coefficients:
        total = total * value + coefficient
    return mp.mpf(str(abs(total)))


def _root_values(
    unknown_names: Sequence[str],
    values: Sequence[mp.mpf | mp.mpc | complex],
    mode: RootMode,
) -> tuple[RootValue, ...]:
    if mode == "polynomial":
        name = unknown_names[0]
        return tuple(RootValue(name, value) for value in values)
    return tuple(RootValue(name, value) for name, value in zip(unknown_names, values, strict=True))


def _all_roots_real(roots: Sequence[RootValue]) -> bool:
    for root in roots:
        value = root.value
        if isinstance(value, mp.mpc):
            if mp.im(value) != 0:
                return False
        elif isinstance(value, complex) and value.imag != 0:
            return False
    return True


def _initial_values(problem: RootProblem) -> tuple[mp.mpf, ...]:
    return tuple(_initial_value(unknown) for unknown in problem.unknowns)


def _single_unknown(problem: RootProblem) -> RootUnknown:
    return problem.unknowns[0]


def _initial_value(unknown: RootUnknown) -> mp.mpf:
    if unknown.initial:
        return _parse_mpf(unknown.initial, f"initial value for {unknown.name}")
    if unknown.lower and unknown.upper:
        return (_parse_mpf(unknown.lower, "lower bound") + _parse_mpf(unknown.upper, "upper bound")) / 2
    return mp.mpf("1")


def _scalar_findroot_guesses(unknown: RootUnknown, initial: mp.mpf) -> tuple[mp.mpf, ...]:
    if unknown.lower and unknown.upper:
        return (_parse_mpf(unknown.lower, "lower bound"), _parse_mpf(unknown.upper, "upper bound"))
    return (initial,)


def _polynomial_coefficients(system: RootExpressionSystem) -> tuple[mp.mpf, ...]:
    coefficients = system.polynomial_coefficients()
    if coefficients is None:
        raise ValueError("Equation is not a univariate polynomial in the unknown.")
    return cast(tuple[mp.mpf, ...], coefficients)


def _parse_mpf(value: str, label: str) -> mp.mpf:
    return _finite_mpf(value, label)


def _finite_mpf(value: object, label: str) -> mp.mpf:
    numeric = mp.mpf(value)
    if not mp.isfinite(numeric):
        raise ValueError(f"{label} must be finite.")
    return numeric


def _mp_or_complex_from_number(value: Any) -> mp.mpf | complex:
    try:
        if abs(complex(value).imag) <= 1e-14:
            return _finite_mpf(str(complex(value).real), "root")
        numeric = complex(value)
    except TypeError:
        return _finite_mpf(value, "root")
    if not (math.isfinite(numeric.real) and math.isfinite(numeric.imag)):
        raise ValueError("root must be finite.")
    return numeric


def _mp_or_complex_from_mpmath(value: Any) -> mp.mpf | mp.mpc:
    real = _finite_mpf(mp.re(value), "root real")
    imaginary = _finite_mpf(mp.im(value), "root imaginary")
    if imaginary == 0:
        return real
    return mp.mpc(real, imaginary)


def _is_finite_number(value: mp.mpf | mp.mpc | complex) -> bool:
    if isinstance(value, mp.mpc):
        return bool(mp.isfinite(mp.re(value)) and mp.isfinite(mp.im(value)))
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    return bool(mp.isfinite(value))
