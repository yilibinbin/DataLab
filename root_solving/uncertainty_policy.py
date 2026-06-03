from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import random

from mpmath import mp

from root_solving.expression import RootExpressionSystem
from root_solving.models import RootProblem, RootResult, RootUncertaintyOptions
from root_solving.uncertainty import attach_linear_uncertainty_with_system
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

SampleSolver = Callable[[Mapping[str, mp.mpf]], RootResult]

_COMPLEX_UNCERTAINTY_WARNING = "Linear uncertainty propagation is only supported for real-valued roots."
_SECOND_ORDER_SYSTEM_WARNING = (
    "Second-order root uncertainty is currently supported for scalar real roots only; use Monte Carlo for systems."
)
_SECOND_ORDER_MULTI_INPUT_WARNING = (
    "Second-order root uncertainty fell back to linear propagation: multiple uncertain inputs require mixed curvature terms."
)


def attach_root_uncertainty(
    *,
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
) -> RootResult:
    if not uncertain_inputs:
        return result
    if not result.roots:
        return result

    active_uncertain_inputs = _active_uncertain_inputs(system, uncertain_inputs)
    if not active_uncertain_inputs:
        return result

    options = problem.uncertainty_options
    if options.method == "off":
        return _with_method(result, "off")

    if any(not _is_real_number(root.value) for root in result.roots):
        return replace(
            result,
            details={**result.details, "uncertainty_method": "skipped"},
            warnings=(*result.warnings, _COMPLEX_UNCERTAINTY_WARNING),
        )

    if options.method == "taylor" and options.taylor_order == 1:
        return _with_linear_method(
            attach_linear_uncertainty_with_system(
                system,
                result,
                active_uncertain_inputs,
                precision=problem.precision,
            )
        )

    if options.method == "monte_carlo":
        return _attach_monte_carlo(problem, system, result, active_uncertain_inputs, solve_nominal, options)

    if options.method == "taylor" and options.taylor_order == 2:
        return _attach_scalar_second_order(problem, system, result, active_uncertain_inputs, solve_nominal)

    return result


def _with_method(result: RootResult, method: str) -> RootResult:
    return replace(result, details={**result.details, "uncertainty_method": method})


def _with_linear_method(result: RootResult) -> RootResult:
    details = {**result.details, "taylor_order": 1}
    if any(root.uncertainty is not None for root in result.roots):
        details["uncertainty_method"] = "taylor"
    else:
        details["uncertainty_method"] = "skipped"
    return replace(result, details=details)


def _attach_monte_carlo(
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
    options: RootUncertaintyOptions,
) -> RootResult:
    if result.mode not in {"scalar", "system"}:
        return replace(
            result,
            details={
                **result.details,
                "uncertainty_method": "none",
                "uncertainty_requested_method": "monte_carlo",
            },
            warnings=(*result.warnings, "Monte Carlo root uncertainty is supported for scalar and system roots only."),
        )

    if options.monte_carlo_samples * max(1, len(result.roots)) > 50000:
        return replace(
            result,
            details={
                **result.details,
                "uncertainty_method": "none",
                "uncertainty_requested_method": "monte_carlo",
            },
            warnings=(
                *result.warnings,
                "Monte Carlo root uncertainty skipped: sample budget exceeds the interactive worker limit.",
            ),
        )

    rng = random.Random(_monte_carlo_seed(options.monte_carlo_seed))
    names = tuple(uncertain_inputs)
    values_by_root: list[list[mp.mpf]] = [[] for _ in result.roots]
    failures = 0
    first_failure: str | None = None

    with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        for _ in range(options.monte_carlo_samples):
            nominal_inputs = dict(system.nominal_inputs)
            for name in names:
                uncertain = uncertain_inputs[name]
                nominal_inputs[name] = mp.mpf(uncertain.value) + mp.mpf(uncertain.uncertainty) * mp.mpf(
                    rng.gauss(0.0, 1.0)
                )

            try:
                sample_result = solve_nominal(nominal_inputs)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                if first_failure is None:
                    first_failure = str(exc)
                continue
            if len(sample_result.roots) != len(result.roots):
                failures += 1
                if first_failure is None:
                    first_failure = "sample root count did not match the nominal root count"
                continue

            if any(not _is_real_number(root.value) for root in sample_result.roots):
                failures += 1
                if first_failure is None:
                    first_failure = "sample returned a complex root"
                continue
            for index, root in enumerate(sample_result.roots):
                values_by_root[index].append(mp.mpf(root.value))

    warnings = tuple(result.warnings)
    skipped = any(len(values) < 2 for values in values_by_root)
    if skipped:
        warnings = (*warnings, "Monte Carlo root uncertainty skipped: fewer than two valid samples.")

    roots = tuple(
        replace(root, uncertainty=_sample_std(values) if len(values) >= 2 else None)
        for root, values in zip(result.roots, values_by_root, strict=True)
    )
    details = {
        **result.details,
        "uncertainty_method": "skipped" if skipped else "monte_carlo",
        "uncertainty_requested_method": "monte_carlo" if skipped else "",
        "monte_carlo_samples": options.monte_carlo_samples,
        "monte_carlo_failures": failures,
        "monte_carlo_valid_samples": min((len(values) for values in values_by_root), default=0),
    }
    if first_failure:
        details["monte_carlo_first_failure"] = first_failure
    if not skipped:
        details.pop("uncertainty_requested_method")
    return replace(
        result,
        roots=roots,
        warnings=warnings,
        details=details,
    )


def _attach_scalar_second_order(
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
) -> RootResult:
    if result.mode != "scalar" or len(result.roots) != 1:
        linear = attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
        return replace(
            linear,
            details={
                **linear.details,
                "uncertainty_method": "taylor",
                "taylor_order": 1,
                "uncertainty_requested_method": "taylor_order_2",
            },
            warnings=(*linear.warnings, _SECOND_ORDER_SYSTEM_WARNING),
        )

    linear = attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
    root = linear.roots[0]
    if root.uncertainty is None:
        return _with_linear_method(linear)
    if len(uncertain_inputs) > 1:
        return replace(
            _with_linear_method(linear),
            details={
                **linear.details,
                "uncertainty_method": "taylor",
                "taylor_order": 1,
                "uncertainty_requested_method": "taylor_order_2",
            },
            warnings=(*linear.warnings, _SECOND_ORDER_MULTI_INPUT_WARNING),
        )

    bias = mp.mpf("0")
    variance = mp.mpf("0")
    with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        for input_name, uncertain in uncertain_inputs.items():
            sigma = mp.mpf(uncertain.uncertainty)
            if sigma == 0:
                continue
            try:
                plus_root = _solve_scalar_with_shift(system, input_name, sigma, solve_nominal)
                minus_root = _solve_scalar_with_shift(system, input_name, -sigma, solve_nominal)
            except Exception:
                return replace(
                    _with_linear_method(linear),
                    details={
                        **linear.details,
                        "uncertainty_method": "taylor",
                        "taylor_order": 1,
                        "uncertainty_requested_method": "taylor_order_2",
                    },
                    warnings=(*linear.warnings, "Second-order root uncertainty fell back to linear propagation."),
                )
            center = mp.mpf(root.value)
            symmetric_delta = (plus_root - minus_root) / 2
            curvature_delta = plus_root - 2 * center + minus_root
            bias += mp.mpf("0.5") * curvature_delta
            variance += symmetric_delta**2 + mp.mpf("0.5") * curvature_delta**2

    return replace(
        linear,
        roots=(replace(root, value=mp.mpf(root.value) + bias, uncertainty=mp.sqrt(variance)),),
        details={
            **linear.details,
            "uncertainty_method": "taylor",
            "taylor_order": 2,
            "uncertainty_bias": mp.nstr(bias, 20),
        },
    )


def _solve_scalar_with_shift(
    system: RootExpressionSystem,
    input_name: str,
    shift: mp.mpf,
    solve_nominal: SampleSolver,
) -> mp.mpf:
    nominal_inputs = dict(system.nominal_inputs)
    nominal_inputs[input_name] = mp.mpf(nominal_inputs[input_name]) + shift
    shifted = solve_nominal(nominal_inputs)
    if len(shifted.roots) != 1 or not _is_real_number(shifted.roots[0].value):
        raise ValueError("Second-order scalar propagation requires one real shifted root.")
    return mp.mpf(shifted.roots[0].value)


def _is_real_number(value: object) -> bool:
    if isinstance(value, complex):
        return value.imag == 0
    if isinstance(value, mp.mpc):
        return bool(mp.im(value) == 0)
    return True


def _sample_std(values: Sequence[mp.mpf]) -> mp.mpf:
    if len(values) < 2:
        raise ValueError("At least two Monte Carlo samples are required.")
    mean = mp.fsum(values) / len(values)
    variance = mp.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mp.sqrt(variance)


def _active_uncertain_inputs(
    system: RootExpressionSystem,
    uncertain_inputs: Mapping[str, UncertainValue],
) -> dict[str, UncertainValue]:
    active_symbols = set().union(*(expression.free_symbols for expression in system.symbolic_expressions))
    return {
        name: value
        for name, value in uncertain_inputs.items()
        if name in system.symbol_map and system.symbol_map[name] in active_symbols
    }


def _monte_carlo_seed(seed: str) -> int | str | None:
    clean = str(seed).strip()
    if not clean:
        return None
    if clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit()):
        return int(clean)
    return clean
