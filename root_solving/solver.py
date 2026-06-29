from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import importlib
import math
import operator
import re
from typing import Any

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import (
    RootBackend,
    RootMode,
    RootProblem,
    RootResult,
    RootScanConfig,
    RootUncertaintyOptions,
    RootUnknown,
    RootValue,
    immutable_mapping,
)
from root_solving.uncertainty_policy import attach_root_uncertainty
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

_SCIPY_FALLBACK_WARNING = "SciPy validation failed; used mpmath fallback."
_SCIPY_FLOAT_UNSAFE_WARNING = "SciPy bypassed because literals or coefficients are not binary64-exact; used mpmath fallback."
_ROOT_CLASSIFICATION_TAGS = (
    "complex",
    "bracketed_sign_change",
    "suspected_tangent_or_repeated",
    "boundary",
    "unclassified",
)


class _UnsafeFloatRouteError(ValueError):
    pass


@dataclass(frozen=True)
class _Candidate:
    values: tuple[mp.mpf | mp.mpc | complex, ...]
    backend: RootBackend
    warnings: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _ScanRootCandidate:
    value: mp.mpf
    tags: frozenset[str] = field(default_factory=frozenset)
    evidence: Mapping[str, object] = field(default_factory=dict)
    merged_candidates: int = 1


def solve_root_problem(
    problem: RootProblem,
    *,
    uncertain_inputs: Mapping[str, UncertainValue] | None = None,
) -> RootResult:
    system = build_root_expression_system(problem)
    return _solve_root_problem_with_system(problem, system, uncertain_inputs)


def _solve_root_problem_with_system(
    problem: RootProblem,
    system: RootExpressionSystem,
    uncertain_inputs: Mapping[str, UncertainValue] | None = None,
) -> RootResult:
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

    details: dict[str, object] = {
        "requested_mode": problem.mode,
        "resolved_mode": mode,
        "solver_status": "converged",
        "initial_guess_summary": _initial_guess_summary(problem.unknowns),
        **dict(candidate.details),
    }
    if mode == "polynomial" and "root_classification_tags" not in details:
        details.update(_polynomial_classification_details(candidate.values))
    if mode == "system":
        residuals = _per_equation_residuals(system, candidate.values)
        if residuals:
            details["per_equation_residuals"] = residuals
        jacobian_condition = _system_jacobian_condition(system, candidate.values)
    else:
        jacobian_condition = None

    result = RootResult(
        roots=roots,
        backend=candidate.backend,
        mode=mode,
        residual_norm=residual_norm,
        jacobian_condition=jacobian_condition,
        warnings=candidate.warnings,
        details=details,
    )
    if uncertain_inputs:
        return attach_root_uncertainty(
            problem=problem,
            system=system,
            result=result,
            uncertain_inputs=uncertain_inputs,
            solve_nominal=lambda nominal_inputs: _solve_nominal_inputs(problem, system, nominal_inputs),
        )
    return result


def resolve_root_mode(problem: RootProblem, system: RootExpressionSystem) -> RootMode:
    """Resolve the requested root mode for callers that reuse a prepared system."""
    return _resolve_mode(problem, system)


def solve_prepared_root_problem(
    problem: RootProblem,
    system: RootExpressionSystem,
    mode: RootMode,
    *,
    uncertain_inputs: Mapping[str, UncertainValue] | None = None,
    uncertainty_options: Mapping[str, object] | RootUncertaintyOptions | None = None,
) -> RootResult:
    """Solve a root problem with an already-parsed expression system."""
    if uncertainty_options is not None and not isinstance(uncertainty_options, RootUncertaintyOptions):
        from root_solving.normalization import normalize_root_uncertainty_options

        normalized_options = normalize_root_uncertainty_options(uncertainty_options)
    else:
        normalized_options = uncertainty_options or problem.uncertainty_options
    prepared_problem = replace(problem, mode=mode, uncertainty_options=normalized_options)
    return _solve_root_problem_with_system(prepared_problem, system, uncertain_inputs)


def _solve_nominal_inputs(
    problem: RootProblem,
    system: RootExpressionSystem,
    nominal_inputs: Mapping[str, mp.mpf],
) -> RootResult:
    sampled_system = replace(system, nominal_inputs=immutable_mapping(nominal_inputs))
    sampled_problem = replace(problem, uncertainty_options=RootUncertaintyOptions(method="off"))
    return _solve_root_problem_with_system(sampled_problem, sampled_system, uncertain_inputs=None)


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
        candidate = _solve_polynomial_scipy(problem, system)
        _validate_candidate(system, candidate.values, "polynomial", problem.precision)
    except _UnsafeFloatRouteError:
        fallback = _solve_mpmath(problem, system, "polynomial")
        return _Candidate(fallback.values, fallback.backend, (*fallback.warnings, _SCIPY_FLOAT_UNSAFE_WARNING))
    except Exception:  # noqa: BLE001
        fallback = _solve_mpmath(problem, system, "polynomial")
        return _Candidate(fallback.values, fallback.backend, (*fallback.warnings, _SCIPY_FALLBACK_WARNING))
    return candidate


def _solve_scipy(problem: RootProblem, system: RootExpressionSystem, mode: RootMode) -> _Candidate:
    scipy_optimize = importlib.import_module("scipy.optimize")

    if mode == "scalar":
        unknown = _single_unknown(problem)
        if unknown.lower and unknown.upper:
            lower = _parse_mpf(unknown.lower, "lower bound")
            upper = _parse_mpf(unknown.upper, "upper bound")

            def scalar_float(value: float) -> float:
                return float(system.evaluate({unknown.name: mp.mpf(str(value))}))

            result = scipy_optimize.root_scalar(scalar_float, bracket=(float(lower), float(upper)), method="brentq")
            if not result.converged:
                raise ValueError("SciPy scalar bracket solve did not converge.")
            return _Candidate(
                (_finite_mpf(str(result.root), "SciPy scalar root"),),
                "scipy",
                details=_scipy_scalar_details(result),
            )

        initial = _initial_values(problem)[0]
        second = _scipy_scalar_secant_second_guess(initial)

        def scalar_float(value: float) -> float:
            return float(system.evaluate({unknown.name: mp.mpf(str(value))}))

        result = scipy_optimize.root_scalar(
            scalar_float,
            x0=float(initial),
            x1=float(second),
            method="secant",
        )
        if not result.converged:
            raise ValueError("SciPy scalar root solve did not converge.")
        return _Candidate(
            (_finite_mpf(str(result.root), "SciPy scalar root"),),
            "scipy",
            details=_scipy_scalar_details(result),
        )

    if mode != "system":
        raise ValueError(f"SciPy mode is not supported here: {mode}")

    unknown_names = system.unknown_names
    initials = _initial_values(problem)

    def system_vector(values: Sequence[float]) -> list[float]:
        scope = {name: mp.mpf(str(value)) for name, value in zip(unknown_names, values, strict=True)}
        return [float(value) for value in system.residuals(scope)]

    result = scipy_optimize.root(system_vector, [float(value) for value in initials])
    if not bool(getattr(result, "success", False)):
        raise ValueError("SciPy system root solve did not converge.")
    return _Candidate(
        tuple(_finite_mpf(str(value), "SciPy system root") for value in result.x),
        "scipy",
        details=_scipy_system_details(result),
    )


def _solve_polynomial_scipy(problem: RootProblem, system: RootExpressionSystem) -> _Candidate:
    import numpy as np

    if not _problem_literals_are_float_safe(problem):
        raise _UnsafeFloatRouteError("Polynomial literals exceed the safe float route.")
    coefficients = _polynomial_coefficients(system)
    if not _coefficients_are_float_safe(coefficients):
        raise _UnsafeFloatRouteError("Polynomial coefficients exceed the safe float route.")
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
        samples: list[tuple[mp.mpf, mp.mpf]] = []

        for index in range(sample_count + 1):
            x_value = lower + (upper - lower) * index / sample_count
            y_value = _evaluate_scan_point(system, unknown.name, x_value)
            samples.append((x_value, y_value))

        cluster_tolerance = _scan_cluster_tolerance(problem.precision, scan_config)
        residual_tolerance = _scan_residual_tolerance(system, problem.precision, scan_config)
        configured_scan_step = (upper - lower) / sample_count
        root_candidates: list[_ScanRootCandidate] = []

        for index, (x_value, y_value) in enumerate(samples):
            if _scan_sample_is_exact_root(y_value):
                exact_sample_tags: set[str] = set()
                finite_difference = _scan_exact_sample_finite_difference(samples, index)
                if finite_difference is not None:
                    x_left, y_left, x_right, y_right = finite_difference
                    if _scan_suspected_tangent_or_repeated(
                        residual=abs(y_value),
                        x_left=x_left,
                        y_left=y_left,
                        x_right=x_right,
                        y_right=y_right,
                        configured_scan_step=configured_scan_step,
                        cluster_tolerance=cluster_tolerance,
                        residual_tolerance=residual_tolerance,
                    ):
                        exact_sample_tags.add("suspected_tangent_or_repeated")
                root_candidates.append(
                    _ScanRootCandidate(
                        x_value,
                        frozenset(exact_sample_tags),
                        {"kind": "exact_sample", "sample": x_value},
                    )
                )

        for (left_x, left_y), (right_x, right_y) in zip(samples, samples[1:], strict=False):
            if not (mp.isfinite(left_y) and mp.isfinite(right_y)):
                continue
            if left_y * right_y < 0:
                root_candidates.append(
                    _ScanRootCandidate(
                        _refine_scalar_bracket(system, unknown.name, left_x, right_x, problem.precision),
                        frozenset({"bracketed_sign_change"}),
                        {
                            "kind": "bracketed_sign_change",
                            "left": left_x,
                            "right": right_x,
                            "left_value": left_y,
                            "right_value": right_y,
                        },
                    )
                )

        for left, center, right in zip(samples, samples[1:], samples[2:], strict=False):
            left_x, left_y = left
            _center_x, center_y = center
            right_x, right_y = right
            if not (mp.isfinite(left_y) and mp.isfinite(center_y) and mp.isfinite(right_y)):
                continue
            if abs(center_y) < abs(left_y) and abs(center_y) < abs(right_y):
                evidence_left = left_x
                evidence_right = right_x
                candidate = _refine_abs_minimum(system, unknown.name, left_x, right_x, problem.precision)
                if _scan_candidate_is_valid(system, unknown.name, candidate, problem.precision, scan_config):
                    minimum_tags: set[str] = set()
                    residual = abs(_evaluate_scan_point(system, unknown.name, candidate))
                    tangent_points = _scan_candidate_finite_difference(
                        system,
                        unknown.name,
                        candidate,
                        lower=lower,
                        upper=upper,
                        configured_scan_step=configured_scan_step,
                    )
                    if tangent_points is not None:
                        left_x, left_y, right_x, right_y = tangent_points
                    if _scan_suspected_tangent_or_repeated(
                        residual=residual,
                        x_left=left_x,
                        y_left=left_y,
                        x_right=right_x,
                        y_right=right_y,
                        configured_scan_step=configured_scan_step,
                        cluster_tolerance=cluster_tolerance,
                        residual_tolerance=residual_tolerance,
                    ):
                        minimum_tags.add("suspected_tangent_or_repeated")
                    root_candidates.append(
                        _ScanRootCandidate(
                            candidate,
                            frozenset(minimum_tags),
                            {"kind": "local_minimum", "left": evidence_left, "right": evidence_right},
                        )
                    )

        unique_candidates = _deduplicate_scan_root_candidates(
            tuple(root_candidates),
            tolerance=cluster_tolerance,
        )
        unique_candidates = tuple(
            _scan_candidate_with_boundary_tag(
                candidate,
                lower=lower,
                upper=upper,
                tolerance=cluster_tolerance,
            )
            for candidate in unique_candidates
        )
        if not unique_candidates:
            raise ValueError("scan_multiple found no roots in the scan range.")
        max_roots = _scan_max_roots(scan_config)
        if len(unique_candidates) > max_roots:
            unique_candidates = unique_candidates[:max_roots]
        unique_roots = tuple(candidate.value for candidate in unique_candidates)
        details = _scan_classification_details(unique_candidates, precision=problem.precision)
        details["scan_summary"] = {
            "lower": _diagnostic_number_text(lower, problem.precision),
            "upper": _diagnostic_number_text(upper, problem.precision),
            "sample_count": sample_count,
            "max_roots": max_roots,
            "accepted_roots_count": len(unique_roots),
        }
        candidate = _Candidate(
            unique_roots,
            "scipy" if problem.precision <= 16 else "mpmath",
            details=details,
        )
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
        scipy_optimize = importlib.import_module("scipy.optimize")

        def scalar_float(value: float) -> float:
            return float(system.evaluate({unknown_name: mp.mpf(str(value))}))

        result = scipy_optimize.root_scalar(scalar_float, bracket=(float(lower), float(upper)), method="brentq")
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
        scipy_optimize = importlib.import_module("scipy.optimize")

        def objective(value: float) -> float:
            try:
                residual = system.evaluate({unknown_name: mp.mpf(str(value))})
            except Exception:
                return float("inf")
            return float(abs(residual))

        result = scipy_optimize.minimize_scalar(objective, bounds=(float(lower), float(upper)), method="bounded")
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


def _scan_sample_is_exact_root(residual: mp.mpf) -> bool:
    if not mp.isfinite(residual):
        return False
    return bool(residual == 0)


def _deduplicate_roots(values: Sequence[mp.mpf], *, tolerance: mp.mpf) -> tuple[mp.mpf, ...]:
    ordered = sorted(values)
    roots: list[mp.mpf] = []
    for value in ordered:
        if not roots or abs(value - roots[-1]) > tolerance:
            roots.append(value)
    return tuple(roots)


def _deduplicate_scan_root_candidates(
    values: Sequence[_ScanRootCandidate],
    *,
    tolerance: mp.mpf,
) -> tuple[_ScanRootCandidate, ...]:
    ordered = sorted(values, key=lambda candidate: candidate.value)
    roots: list[_ScanRootCandidate] = []
    for candidate in ordered:
        if not roots or abs(candidate.value - roots[-1].value) > tolerance:
            roots.append(candidate)
            continue
        merged_tags = roots[-1].tags | candidate.tags
        roots[-1] = _ScanRootCandidate(
            roots[-1].value,
            frozenset(merged_tags),
            _preferred_scan_evidence(roots[-1].evidence, candidate.evidence),
            roots[-1].merged_candidates + candidate.merged_candidates,
        )
    return tuple(roots)


def _scan_candidate_with_boundary_tag(
    candidate: _ScanRootCandidate,
    *,
    lower: mp.mpf,
    upper: mp.mpf,
    tolerance: mp.mpf,
) -> _ScanRootCandidate:
    tags = set(candidate.tags)
    if abs(candidate.value - lower) <= tolerance or abs(candidate.value - upper) <= tolerance:
        tags.add("boundary")
    return _ScanRootCandidate(candidate.value, frozenset(tags), candidate.evidence, candidate.merged_candidates)


def _scan_classification_details(candidates: Sequence[_ScanRootCandidate], *, precision: int) -> dict[str, object]:
    details: dict[str, object] = {
        "root_classification_tags": {
            str(index): list(_ordered_root_classification_tags(candidate.tags))
            for index, candidate in enumerate(candidates)
        }
    }
    evidence = {
        str(index): payload
        for index, candidate in enumerate(candidates)
        if (payload := _scan_root_evidence_payload(candidate, precision=precision))
    }
    if evidence:
        details["scan_root_evidence"] = evidence
    return details


def _preferred_scan_evidence(
    current: Mapping[str, object],
    candidate: Mapping[str, object],
) -> Mapping[str, object]:
    current_priority = _scan_evidence_priority(current)
    candidate_priority = _scan_evidence_priority(candidate)
    if candidate_priority > current_priority:
        return candidate
    return current


def _scan_evidence_priority(evidence: Mapping[str, object]) -> int:
    kind = evidence.get("kind")
    if kind == "bracketed_sign_change":
        return 3
    if kind == "local_minimum":
        return 2
    if kind == "exact_sample":
        return 1
    return 0


def _scan_root_evidence_payload(candidate: _ScanRootCandidate, *, precision: int) -> dict[str, object]:
    raw_kind = candidate.evidence.get("kind")
    if raw_kind not in {"exact_sample", "bracketed_sign_change", "local_minimum"}:
        return {}
    payload: dict[str, object] = {"kind": str(raw_kind)}
    for field_name in ("left", "right", "left_value", "right_value", "sample"):
        if field_name not in candidate.evidence:
            continue
        try:
            payload[field_name] = _diagnostic_number_text(candidate.evidence[field_name], precision)
        except (TypeError, ValueError, ArithmeticError):
            continue
    if candidate.merged_candidates > 1:
        payload["merged_candidates"] = candidate.merged_candidates
    return payload


def _polynomial_classification_details(values: Sequence[mp.mpf | mp.mpc | complex]) -> dict[str, object]:
    return {
        "root_classification_tags": {
            str(index): ["complex"] if _is_non_real_complex(value) else ["unclassified"]
            for index, value in enumerate(values)
        }
    }


def _scipy_scalar_details(result: Any) -> dict[str, object]:
    details: dict[str, object] = {}
    iterations = _diagnostic_int(getattr(result, "iterations", None))
    if iterations is not None:
        details["scipy_iterations"] = iterations
    function_calls = _diagnostic_int(getattr(result, "function_calls", None))
    if function_calls is not None:
        details["scipy_function_evaluations"] = function_calls
    return details


def _scipy_system_details(result: Any) -> dict[str, object]:
    details: dict[str, object] = {}
    function_evaluations = _diagnostic_int(getattr(result, "nfev", None))
    if function_evaluations is not None:
        details["scipy_function_evaluations"] = function_evaluations
    return details


def _diagnostic_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("+"):
            text = text[1:]
        if not text.isdecimal():
            return None
        return int(text)
    try:
        integer = operator.index(value)
    except TypeError:
        return None
    return integer if integer >= 0 else None


def _initial_guess_summary(unknowns: Sequence[RootUnknown]) -> str:
    return "; ".join(
        f"{unknown.name} initial={unknown.initial} lower={unknown.lower} upper={unknown.upper}"
        for unknown in unknowns
    )


def _per_equation_residuals(
    system: RootExpressionSystem,
    values: Sequence[mp.mpf | mp.mpc | complex],
) -> dict[str, str]:
    with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        scope = {name: value for name, value in zip(system.unknown_names, values, strict=True)}
        return {
            str(index): _diagnostic_number_text(residual, system.precision)
            for index, residual in enumerate(system.residuals(scope))
        }


def _system_jacobian_condition(
    system: RootExpressionSystem,
    values: Sequence[mp.mpf | mp.mpc | complex],
) -> mp.mpf | None:
    try:
        with precision_guard(system.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
            scope = {name: value for name, value in zip(system.unknown_names, values, strict=True)}
            jacobian = mp.matrix(
                [
                    [system.derivative_unknown(name, scope, equation_index) for name in system.unknown_names]
                    for equation_index in range(len(system.expressions))
                ]
            )
            condition = mp.mpf(mp.cond(jacobian))
    except Exception:
        return None
    if not mp.isfinite(condition) or condition < 0:
        return None
    return condition


def _diagnostic_number_text(value: Any, precision: int) -> str:
    digits = max(1, int(precision))
    numeric = mp.mpc(value)
    if numeric.imag:
        return str(mp.nstr(numeric, n=digits))
    return str(mp.nstr(numeric.real, n=digits))


def _ordered_root_classification_tags(tags: frozenset[str] | set[str]) -> tuple[str, ...]:
    filtered = {tag for tag in tags if tag in _ROOT_CLASSIFICATION_TAGS and tag != "unclassified"}
    if not filtered:
        return ("unclassified",)
    return tuple(tag for tag in _ROOT_CLASSIFICATION_TAGS if tag in filtered)


def _scan_exact_sample_finite_difference(
    samples: Sequence[tuple[mp.mpf, mp.mpf]],
    index: int,
) -> tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf] | None:
    if index <= 0 or index >= len(samples) - 1:
        return None
    x_left, y_left = samples[index - 1]
    x_right, y_right = samples[index + 1]
    return x_left, y_left, x_right, y_right


def _scan_candidate_finite_difference(
    system: RootExpressionSystem,
    unknown_name: str,
    value: mp.mpf,
    *,
    lower: mp.mpf,
    upper: mp.mpf,
    configured_scan_step: mp.mpf,
) -> tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf] | None:
    half_step = configured_scan_step / 2
    if half_step <= 0:
        return None
    x_left = max(lower, value - half_step)
    x_right = min(upper, value + half_step)
    if x_left == x_right:
        return None
    y_left = _evaluate_scan_point(system, unknown_name, x_left)
    y_right = _evaluate_scan_point(system, unknown_name, x_right)
    if not (mp.isfinite(y_left) and mp.isfinite(y_right)):
        return None
    return x_left, y_left, x_right, y_right


def _scan_suspected_tangent_or_repeated(
    *,
    residual: mp.mpf,
    x_left: mp.mpf,
    y_left: mp.mpf,
    x_right: mp.mpf,
    y_right: mp.mpf,
    configured_scan_step: mp.mpf,
    cluster_tolerance: mp.mpf,
    residual_tolerance: mp.mpf,
) -> bool:
    values = (residual, x_left, y_left, x_right, y_right, configured_scan_step, cluster_tolerance, residual_tolerance)
    if not all(mp.isfinite(value) for value in values):
        return False
    if residual > residual_tolerance:
        return False
    if y_left * y_right < 0:
        return False
    delta_x = x_right - x_left
    if delta_x == 0:
        return False
    slope = (y_right - y_left) / delta_x
    x_scale = max(abs(delta_x), configured_scan_step, cluster_tolerance)
    return bool(abs(slope) * x_scale <= residual_tolerance)


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
    precision: int,
    scan_config: RootScanConfig,
) -> mp.mpf:
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        if scan_config.cluster_tolerance:
            return _positive_config_mpf(scan_config.cluster_tolerance, "scan cluster tolerance")
        if precision <= 16:
            return mp.mpf("1e-12")
        digits = max(12, min(precision - 8, precision // 2))
        return mp.power(10, -digits)


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


def _is_non_real_complex(value: mp.mpf | mp.mpc | complex) -> bool:
    if isinstance(value, mp.mpc):
        return bool(mp.im(value) != 0)
    if isinstance(value, complex):
        return value.imag != 0
    return False


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


def _coefficients_are_float_safe(coefficients: Sequence[mp.mpf]) -> bool:
    for coefficient in coefficients:
        if not mp.isfinite(coefficient):
            return False
        try:
            round_trip = mp.mpf(float(coefficient))
        except (OverflowError, ValueError):
            return False
        if round_trip != coefficient:
            return False
    return True


_NUMERIC_LITERAL_RE = re.compile(r"(?<![A-Za-z_])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _problem_literals_are_float_safe(problem: RootProblem) -> bool:
    literals: list[str] = []
    for expression in problem.equations:
        literals.extend(match.group(0) for match in _NUMERIC_LITERAL_RE.finditer(expression))
    literals.extend(known.value for known in problem.known_values)
    literals.extend(str(value) for value in problem.row_values.values())
    literals.extend(str(value) for value in problem.constants.values())
    return all(_literal_is_binary64_exact(literal) for literal in literals if str(literal).strip())


def _literal_is_binary64_exact(literal: str) -> bool:
    text = str(literal).strip()
    if "(" in text or "[" in text:
        from shared.uncertainty import parse_numeric_value

        numeric = parse_numeric_value(text, precision=max(80, len(text) + 10))
        float_text = text.split("(", 1)[0]
    else:
        with precision_guard(max(80, len(text) + 10), clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
            numeric = mp.mpf(text)
        float_text = text
    try:
        as_float = float(float_text)
    except (OverflowError, ValueError):
        return False
    with precision_guard(max(80, len(text) + 10), clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        return bool(mp.mpf(as_float) == numeric)


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
