from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
import math
from typing import Any

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootBackend, RootMode, RootProblem, RootScanConfig, RootUnknown, RootValue, RootResult
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

    if mode == "scan_multiple":
        candidate = _solve_scan_multiple(problem, system)
    elif problem.precision <= 16:
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
            propagated = attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
            if not isinstance(propagated, RootResult):
                raise TypeError("uncertainty propagation returned an invalid root result")
            return propagated
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
    if requested == "scan_multiple" and (equation_count != 1 or unknown_count != 1):
        raise ValueError("scan_multiple root-solving mode requires exactly one equation and one unknown.")
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
        second = _scipy_scalar_secant_second_guess(initial)

        def scalar_float(value: float) -> float:
            return float(system.evaluate({unknown.name: mp.mpf(str(value))}))

        result = scipy.optimize.root_scalar(
            scalar_float,
            x0=float(initial),
            x1=float(second),
            method="secant",
        )
        if not result.converged:
            raise ValueError("SciPy scalar root solve did not converge.")
        return _Candidate((_finite_mpf(str(result.root), "SciPy scalar root"),), "scipy")

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


def _solve_scan_multiple(problem: RootProblem, system: RootExpressionSystem) -> _Candidate:
    with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        unknown = _single_unknown(problem)
        if not unknown.lower or not unknown.upper:
            raise ValueError("scan_multiple requires lower and upper bounds.")
        lower = _parse_mpf(unknown.lower, "lower bound")
        upper = _parse_mpf(unknown.upper, "upper bound")
        if lower >= upper:
            raise ValueError("scan_multiple lower bound must be less than upper bound.")

        scan_config = problem.scan_config
        sample_count = _scan_sample_count(scan_config)
        roots: list[mp.mpf] = []
        samples: list[tuple[mp.mpf, mp.mpf]] = []

        for index in range(sample_count + 1):
            x_value = lower + (upper - lower) * index / sample_count
            y_value = _evaluate_scan_point(system, unknown.name, x_value)
            samples.append((x_value, y_value))
            if _scan_candidate_is_valid(system, unknown.name, x_value, problem.precision, scan_config):
                roots.append(x_value)

        for (left_x, left_y), (right_x, right_y) in zip(samples, samples[1:], strict=False):
            if not (mp.isfinite(left_y) and mp.isfinite(right_y)):
                continue
            if left_y * right_y < 0:
                roots.append(_refine_scalar_bracket(system, unknown.name, left_x, right_x, problem.precision))

        for left, center, right in zip(samples, samples[1:], samples[2:], strict=False):
            left_x, left_y = left
            center_x, center_y = center
            right_x, right_y = right
            if not (mp.isfinite(left_y) and mp.isfinite(center_y) and mp.isfinite(right_y)):
                continue
            if abs(center_y) <= abs(left_y) and abs(center_y) <= abs(right_y):
                candidate = _refine_abs_minimum(system, unknown.name, left_x, right_x, problem.precision)
                if _scan_candidate_is_valid(system, unknown.name, candidate, problem.precision, scan_config):
                    roots.append(candidate)

        unique_roots = _deduplicate_roots(
            tuple(roots),
            tolerance=_scan_cluster_tolerance(system, problem.precision, scan_config),
        )
        if not unique_roots:
            raise ValueError("scan_multiple found no roots in the scan range.")
        max_roots = _scan_max_roots(scan_config)
        if len(unique_roots) > max_roots:
            unique_roots = unique_roots[:max_roots]
        candidate = _Candidate(unique_roots, "scipy" if problem.precision <= 16 else "mpmath")
        _validate_candidate(system, candidate.values, "scan_multiple", problem.precision, scan_config)
        return candidate


def _evaluate_scan_point(system: RootExpressionSystem, unknown_name: str, value: mp.mpf) -> mp.mpf:
    try:
        result = system.evaluate({unknown_name: value})
    except Exception:
        return mp.nan
    if not mp.isfinite(result):
        return mp.nan
    return result


def _refine_scalar_bracket(
    system: RootExpressionSystem,
    unknown_name: str,
    lower: mp.mpf,
    upper: mp.mpf,
    precision: int,
) -> mp.mpf:
    if precision <= 16:
        import scipy.optimize

        def scalar_float(value: float) -> float:
            return float(system.evaluate({unknown_name: mp.mpf(str(value))}))

        result = scipy.optimize.root_scalar(scalar_float, bracket=(float(lower), float(upper)), method="brentq")
        if not result.converged:
            raise ValueError("SciPy scan bracket solve did not converge.")
        return _finite_mpf(str(result.root), "SciPy scan root")

    def function(value: mp.mpf) -> mp.mpf:
        return system.evaluate({unknown_name: value})

    return _finite_mpf(mp.findroot(function, (lower, upper)), "mpmath scan root")


def _refine_abs_minimum(
    system: RootExpressionSystem,
    unknown_name: str,
    lower: mp.mpf,
    upper: mp.mpf,
    precision: int,
) -> mp.mpf:
    if precision <= 16:
        import scipy.optimize

        def objective(value: float) -> float:
            try:
                residual = system.evaluate({unknown_name: mp.mpf(str(value))})
            except Exception:
                return float("inf")
            return float(abs(residual))

        result = scipy.optimize.minimize_scalar(objective, bounds=(float(lower), float(upper)), method="bounded")
        if not bool(getattr(result, "success", False)):
            raise ValueError("SciPy scan minimum refinement did not converge.")
        return _finite_mpf(str(result.x), "SciPy scan minimum")

    return _golden_section_abs_minimum(system, unknown_name, lower, upper, precision)


def _golden_section_abs_minimum(
    system: RootExpressionSystem,
    unknown_name: str,
    lower: mp.mpf,
    upper: mp.mpf,
    precision: int,
) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        ratio = (mp.sqrt(5) - 1) / 2
        left = lower
        right = upper
        c_value = right - ratio * (right - left)
        d_value = left + ratio * (right - left)
        for _ in range(max(80, precision * 2)):
            if abs(right - left) <= mp.sqrt(mp.eps) * max(mp.mpf("1"), abs(c_value), abs(d_value)):
                break
            c_score = abs(_evaluate_scan_point(system, unknown_name, c_value))
            d_score = abs(_evaluate_scan_point(system, unknown_name, d_value))
            if c_score < d_score:
                right = d_value
                d_value = c_value
                c_value = right - ratio * (right - left)
            else:
                left = c_value
                c_value = d_value
                d_value = left + ratio * (right - left)
        return _finite_mpf((left + right) / 2, "mpmath scan minimum")


def _scan_candidate_is_valid(
    system: RootExpressionSystem,
    unknown_name: str,
    value: mp.mpf,
    precision: int,
    scan_config: RootScanConfig,
) -> bool:
    residual = abs(_evaluate_scan_point(system, unknown_name, value))
    return bool(mp.isfinite(residual) and residual <= _scan_residual_tolerance(system, precision, scan_config))


def _deduplicate_roots(values: Sequence[mp.mpf], *, tolerance: mp.mpf) -> tuple[mp.mpf, ...]:
    ordered = sorted(values)
    roots: list[mp.mpf] = []
    for value in ordered:
        if not roots or abs(value - roots[-1]) > tolerance:
            roots.append(value)
    return tuple(roots)


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
    scan_config: RootScanConfig | None = None,
) -> None:
    if any(not _is_finite_number(value) for value in values):
        raise ValueError("Solver returned a non-finite root.")
    residual_norm = _residual_norm(system, values, mode)
    tolerance = (
        _scan_residual_tolerance(system, precision, scan_config or RootScanConfig())
        if mode == "scan_multiple"
        else _residual_tolerance(system, precision)
    )
    if residual_norm > tolerance:
        raise ValueError("Solver residual exceeded tolerance.")


def _residual_tolerance(system: RootExpressionSystem, precision: int) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        target_scale = max((abs(value) for value in system.nominal_inputs.values()), default=mp.mpf("1"))
        target_scale = max(mp.mpf("1"), target_scale)
        return mp.mpf(str(max(1e-10, 100 * math.sqrt(float(mp.eps))))) * target_scale


def _scan_residual_tolerance(
    system: RootExpressionSystem,
    precision: int,
    scan_config: RootScanConfig | None = None,
) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if scan_config and scan_config.residual_tolerance:
            return _positive_config_mpf(scan_config.residual_tolerance, "scan residual tolerance")
        target_scale = max((abs(value) for value in system.nominal_inputs.values()), default=mp.mpf("1"))
        target_scale = max(mp.mpf("1"), target_scale)
        if precision <= 16:
            return mp.mpf("1e-10") * target_scale
        digits = max(12, min(precision - 8, precision // 2))
        return mp.power(10, -digits) * target_scale


def _scan_cluster_tolerance(
    system: RootExpressionSystem,
    precision: int,
    scan_config: RootScanConfig,
) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if scan_config.cluster_tolerance:
            return _positive_config_mpf(scan_config.cluster_tolerance, "scan cluster tolerance")
        return max(mp.sqrt(mp.eps), _scan_residual_tolerance(system, precision, scan_config))


def _scan_sample_count(scan_config: RootScanConfig) -> int:
    return max(2, min(100000, int(scan_config.sample_count)))


def _scan_max_roots(scan_config: RootScanConfig) -> int:
    return max(1, min(10000, int(scan_config.max_roots)))


def _positive_config_mpf(value: str, label: str) -> mp.mpf:
    numeric = _finite_mpf(value, label)
    if numeric <= 0:
        raise ValueError(f"{label} must be positive.")
    return numeric


def _residual_norm(system: RootExpressionSystem, values: Sequence[mp.mpf | mp.mpc | complex], mode: RootMode) -> mp.mpf:
    with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if mode == "polynomial":
            coefficients = _polynomial_coefficients(system)
            return max((_polynomial_residual_abs(coefficients, value) for value in values), default=mp.mpf("0"))
        if mode == "scan_multiple":
            name = system.unknown_names[0]
            return max((abs(system.evaluate({name: value})) for value in values), default=mp.mpf("0"))
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
    if mode in {"polynomial", "scan_multiple"}:
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


def _scipy_scalar_secant_second_guess(initial: mp.mpf) -> mp.mpf:
    with precision_guard(16, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        scale = max(mp.mpf("1"), abs(initial))
        step = mp.mpf("1e-6") * scale
        for _ in range(12):
            candidate = initial + step
            if float(candidate) != float(initial):
                return candidate
            step *= 10
        candidate = initial + scale
        if float(candidate) == float(initial):
            raise ValueError("Unable to construct a distinct SciPy secant seed.")
        return candidate


def _polynomial_coefficients(system: RootExpressionSystem) -> tuple[mp.mpf, ...]:
    coefficients = system.polynomial_coefficients()
    if coefficients is None:
        raise ValueError("Equation is not a univariate polynomial in the unknown.")
    return tuple(mp.mpf(coefficient) for coefficient in coefficients)


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
