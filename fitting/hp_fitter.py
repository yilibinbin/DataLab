"""High-precision nonlinear least-squares fitting routines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.numerics import noise_floor
from shared.precision import precision_guard

from .constraints import ParameterState
from .model_parser import ModelSpecification


@dataclass
class FitResult:
    """Container for fitting outcomes.

    param_errors_stat: statistical-only uncertainties from χ² covariance.
    param_errors_sys: systematic component from data-uncertainty refits.
    param_errors_total/param_errors: quadrature sum of stat and sys (for compatibility).
    """

    params: dict[str, mp.mpf]
    param_errors: dict[str, mp.mpf]
    chi2: mp.mpf
    reduced_chi2: mp.mpf
    aic: mp.mpf
    bic: mp.mpf
    r2: mp.mpf
    rmse: mp.mpf
    residuals: list[mp.mpf]
    fitted_curve: list[mp.mpf]
    covariance: list[list[mp.mpf]]
    param_errors_stat: dict[str, mp.mpf] = field(default_factory=dict)
    param_errors_sys: dict[str, mp.mpf] = field(default_factory=dict)
    param_errors_total: dict[str, mp.mpf] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class _FitComputation:
    params: dict[str, mp.mpf]
    stat_errors: dict[str, mp.mpf]
    chi2: mp.mpf
    reduced_chi2: mp.mpf
    aic: mp.mpf
    bic: mp.mpf
    r2: mp.mpf
    rmse: mp.mpf
    residuals: list[mp.mpf]
    fitted_curve: list[mp.mpf]
    covariance: list[list[mp.mpf]]
    details: dict[str, object]
    free_solution: tuple[mp.mpf, ...]


def combine_error_components(
    params: dict[str, mp.mpf],
    stat_errors: dict[str, mp.mpf] | None,
    sys_errors: dict[str, mp.mpf] | None,
) -> tuple[dict[str, mp.mpf], dict[str, mp.mpf], dict[str, mp.mpf]]:
    """Return (stat, sys, total) error dictionaries keyed by param names."""

    names = set(params.keys())
    stat_map: dict[str, mp.mpf] = {}
    sys_map: dict[str, mp.mpf] = {}
    total_map: dict[str, mp.mpf] = {}
    zero = mp.mpf("0")
    for name in names:
        stat_val = mp.mpf(stat_errors.get(name, zero)) if stat_errors else zero
        sys_val = mp.mpf(sys_errors.get(name, zero)) if sys_errors else zero
        stat_map[name] = stat_val
        sys_map[name] = sys_val
        if mp.isnan(stat_val) or mp.isnan(sys_val):
            total_map[name] = mp.nan
        else:
            total_map[name] = mp.sqrt(stat_val * stat_val + sys_val * sys_val)
    return stat_map, sys_map, total_map


def _prepare_points(
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
) -> tuple[list[dict[str, mp.mpf]], list[mp.mpf]]:
    var_names = list(variable_data.keys())
    value_columns = [list(variable_data[name]) for name in var_names]
    rows = list(zip(*value_columns))
    observations: list[dict[str, mp.mpf]] = []
    for row in rows:
        obs = {name: mp.mpf(value) for name, value in zip(var_names, row)}
        observations.append(obs)
    targets = [mp.mpf(val) for val in target_data]
    return observations, targets


def _generate_seed_variants(seed: tuple[mp.mpf, ...]) -> list[tuple[mp.mpf, ...]]:
    """Generate deterministic seed variants (compatibility set)."""
    if not seed:
        return [()]
    variants = [tuple(seed)]
    scale = [mp.fabs(value) * mp.mpf("0.25") if value != 0 else mp.mpf("0.5") for value in seed]
    for idx, base in enumerate(seed):
        delta = scale[idx]
        plus = list(seed)
        plus[idx] = base + delta
        variants.append(tuple(plus))
        minus = list(seed)
        minus[idx] = base - delta
        variants.append(tuple(minus))
    return variants


def _generate_seed_variants_fallback(seed: tuple[mp.mpf, ...]) -> list[tuple[mp.mpf, ...]]:
    """Extra deterministic seed variants used only when the compatibility set fails."""
    if not seed:
        return [()]
    variants: list[tuple[mp.mpf, ...]] = []

    # Overall scaling variants.
    for factor in (mp.mpf("0.5"), mp.mpf("2.0")):
        variants.append(tuple(mp.mpf(val) * factor for val in seed))

    # Per-parameter scaling variants (keep others unchanged).
    for idx, base in enumerate(seed):
        for factor in (mp.mpf("0.5"), mp.mpf("2.0")):
            scaled = list(seed)
            scaled[idx] = mp.mpf(base) * factor
            variants.append(tuple(scaled))

    # De-duplicate while preserving order.
    seen: set[tuple[str, ...]] = set()
    deduped: list[tuple[mp.mpf, ...]] = []
    for variant in variants:
        key = tuple(mp.nstr(v, 60) for v in variant)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tuple(mp.mpf(v) for v in variant))

    return deduped or [tuple(seed)]


def _gradient_builder(
    parameter_name: str,
    model: ModelSpecification,
    state: ParameterState,
    observations: Sequence[dict[str, mp.mpf]],
    targets: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
) -> Callable[..., mp.mpf]:
    def _gradient(*free_values: mp.mpf) -> mp.mpf:
        params = state.compose(tuple(free_values))
        total = mp.mpf("0")
        for idx, (obs, target) in enumerate(zip(observations, targets)):
            _set_model_point_index(model, idx)
            y_model = model.evaluate(obs, params)
            derivative = model.partial(parameter_name, obs, params)
            weight = weights[idx] if weights else mp.mpf("1")
            total += weight * (y_model - target) * derivative
        return mp.mpf(2) * total

    return _gradient


def _compute_statistics(
    model: ModelSpecification,
    params: dict[str, mp.mpf],
    observations: Sequence[dict[str, mp.mpf]],
    targets: Sequence[mp.mpf],
    free_param_count: int,
    weights: list[mp.mpf] | None,
) -> tuple[
    list[mp.mpf], list[mp.mpf], mp.mpf, mp.mpf, mp.mpf, mp.mpf, mp.mpf, mp.mpf, int
]:
    fitted: list[mp.mpf] = []
    residuals: list[mp.mpf] = []
    for idx, (obs, target) in enumerate(zip(observations, targets)):
        _set_model_point_index(model, idx)
        value = model.evaluate(obs, params)
        fitted.append(value)
        residuals.append(value - target)
    if weights:
        if any(w <= 0 for w in weights):
            raise ValueError(
                _dual_msg("权重必须为正。", "Weights must be positive.")
            )
        chi2 = sum(weight * (r * r) for weight, r in zip(weights, residuals))
        total_weight = sum(weights)
        if total_weight > 0:
            mean_target = sum(weight * target for weight, target in zip(weights, targets)) / total_weight
        else:
            mean_target = sum(targets) / len(targets)
        sst = sum(weight * (y - mean_target) ** 2 for weight, y in zip(weights, targets))
        rmse = mp.sqrt(chi2 / total_weight)
    else:
        chi2 = sum((r * r) for r in residuals)
        mean_target = sum(targets) / len(targets)
        sst = sum((y - mean_target) ** 2 for y in targets)
        rmse = mp.sqrt(chi2 / len(targets))
    n = len(targets)
    dof = n - free_param_count
    if dof <= 0:
        reduced = mp.nan
        r2 = mp.nan
        noise = mp.nan
        aic = mp.nan
        bic = mp.nan
    else:
        reduced = chi2 / dof
        r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
        eps = noise_floor()
        noise = chi2 / n if chi2 > eps else eps
        aic = 2 * free_param_count + n * mp.log(noise)
        bic = free_param_count * mp.log(n) + n * mp.log(noise)
    return fitted, residuals, chi2, reduced, r2, rmse, aic, bic, dof


def _compute_covariance(
    model: ModelSpecification,
    params: dict[str, mp.mpf],
    observations: Sequence[dict[str, mp.mpf]],
    targets: Sequence[mp.mpf],
    free_params: list[str],
    chi2: mp.mpf,
    dof: int,
    weights: list[mp.mpf] | None,
) -> tuple[list[list[mp.mpf]], dict[str, mp.mpf], str | None]:
    if not free_params:
        return [], {}, None
    n = len(targets)
    k = len(free_params)
    jacobian = [[mp.mpf("0") for _ in range(k)] for _ in range(n)]
    if weights:
        for w in weights:
            if w <= 0:
                raise ValueError(
                    _dual_msg("权重必须为正。", "Weights must be positive.")
                )
    sqrt_weights = [mp.sqrt(w) for w in weights] if weights else None
    for idx, (obs, target) in enumerate(zip(observations, targets)):
        _set_model_point_index(model, idx)
        for jdx, name in enumerate(free_params):
            derivative = model.partial(name, obs, params)
            if sqrt_weights:
                jacobian[idx][jdx] = derivative * sqrt_weights[idx]
            else:
                jacobian[idx][jdx] = derivative
    # build J^T J
    jtj = [[mp.mpf("0") for _ in range(k)] for _ in range(k)]
    for i in range(k):
        for j in range(k):
            s = mp.mpf("0")
            for row in jacobian:
                s += row[i] * row[j]
            jtj[i][j] = s
    # convert to mpmath matrix for inversion
    mat = mp.matrix(jtj)
    cov_warning = None
    try:
        inv = mat ** -1
    except ZeroDivisionError:
        flagged = [[mp.nan for _ in range(k)] for _ in range(k)]
        cov_warning = "协方差矩阵奇异，参数不确定度不可用。 / Covariance matrix is singular; parameter uncertainties unavailable."
        return flagged, {name: mp.nan for name in free_params}, cov_warning
    noise = chi2 / dof if dof > 0 else mp.nan
    covariance = [[inv[i, j] * noise for j in range(k)] for i in range(k)]
    errors = {
        name: mp.sqrt(covariance[idx][idx])
        if not mp.isnan(covariance[idx][idx])
        else mp.nan
        for idx, name in enumerate(free_params)
    }
    if any(mp.isnan(val) or mp.isinf(val) for row in covariance for val in row):
        cov_warning = "协方差矩阵病态或奇异，参数不确定度可能不可靠。 / Covariance matrix is ill-conditioned or singular; parameter uncertainties may be unreliable."
    return covariance, errors, cov_warning


def _set_model_point_index(model: ModelSpecification, row_index: int) -> None:
    setter = getattr(model, "set_implicit_point_index", None)
    if setter is not None:
        setter(row_index)


def _propagate_dependent_errors(
    parameter_state: ParameterState,
    params: dict[str, mp.mpf],
    covariance: list[list[mp.mpf]],
) -> dict[str, mp.mpf]:
    dependent_defs = parameter_state.dependent_defs
    if not dependent_defs:
        return {}
    free_params = parameter_state.free_params
    k = len(free_params)
    if not covariance or k == 0:
        return {name: mp.nan for name in dependent_defs}
    jacobians: dict[str, list[mp.mpf]] = {}
    for idx, name in enumerate(free_params):
        vector = [mp.mpf("0") for _ in range(k)]
        vector[idx] = mp.mpf("1")
        jacobians[name] = vector
    for name in parameter_state.fixed_values:
        jacobians[name] = [mp.mpf("0") for _ in range(k)]
    pending = dict(dependent_defs)
    guard = 0
    while pending and guard < 64:
        progressed = False
        for name, definition in list(pending.items()):
            deps = definition.dependencies
            if any(dep not in jacobians for dep in deps):
                continue
            jac_vec = [mp.mpf("0") for _ in range(k)]
            for dep in deps:
                partial = definition.partials.get(dep)
                if not partial:
                    continue
                derivative = partial(params)
                source = jacobians.get(dep)
                if source is None:
                    continue
                for idx in range(k):
                    jac_vec[idx] += derivative * source[idx]
            jacobians[name] = jac_vec
            pending.pop(name)
            progressed = True
        if not progressed:
            guard += 1
            if guard >= 64:
                break
    errors: dict[str, mp.mpf] = {}
    for name in dependent_defs:
        # Distinct from the ``jac_vec`` built in the loop above; mypy
        # requires separate names for narrowing.
        dep_jac: list[mp.mpf] | None = jacobians.get(name)
        if dep_jac is None:
            errors[name] = mp.nan
            continue
        variance = mp.mpf("0")
        invalid = False
        for i in range(k):
            for j in range(k):
                value = covariance[i][j]
                if mp.isnan(value):
                    invalid = True
                    break
                variance += dep_jac[i] * value * dep_jac[j]
            if invalid:
                break
        if invalid or variance < 0:
            errors[name] = mp.nan
        else:
            errors[name] = mp.sqrt(variance)
    return errors


def _estimate_systematic_uncertainty(
    solver: Callable[[Sequence[mp.mpf], tuple[mp.mpf, ...] | None], _FitComputation],
    base_params: dict[str, mp.mpf],
    targets: Sequence[mp.mpf],
    data_sigmas: Sequence[mp.mpf | None] | None,
    base_seed: tuple[mp.mpf, ...],
) -> tuple[dict[str, mp.mpf], list[str]]:
    """Estimate parameter systematics by refitting targets ±σ."""

    if data_sigmas is None:
        return {}, []
    if len(data_sigmas) != len(targets):
        raise ValueError(
            _dual_msg(
                "数据不确定度列的长度必须与目标数据一致。",
                "Uncertainty column length must match targets.",
            )
        )
    sigma_vec: list[mp.mpf] = []
    for sigma in data_sigmas:
        if sigma is None:
            sigma_vec.append(mp.mpf("0"))
            continue
        sigma_val = mp.fabs(mp.mpf(sigma))
        sigma_vec.append(sigma_val)
    if not sigma_vec or all(sig == 0 for sig in sigma_vec):
        return {}, []

    plus_targets = [mp.mpf(t) + sig for t, sig in zip(targets, sigma_vec)]
    minus_targets = [mp.mpf(t) - sig for t, sig in zip(targets, sigma_vec)]
    notes: list[str] = []
    refits: list[_FitComputation | None] = []
    for direction, perturbed in (("plus", plus_targets), ("minus", minus_targets)):
        try:
            refits.append(solver(perturbed, base_seed))
        except Exception as exc:
            notes.append(f"Systematic {direction} refit failed: {exc}")
            refits.append(None)

    sys_errors: dict[str, mp.mpf] = {}
    names = set(base_params.keys())
    zero = mp.mpf("0")
    for name in names:
        deltas: list[mp.mpf] = []
        base_val = mp.mpf(base_params.get(name, zero))
        for refit in refits:
            if refit is None:
                continue
            candidate = refit.params.get(name, base_val)
            deltas.append(mp.fabs(candidate - base_val))
        if deltas:
            sys_errors[name] = mp.fsum(deltas) / len(deltas)
        elif notes:
            sys_errors[name] = mp.nan
        else:
            sys_errors[name] = zero
    return sys_errors, notes


def _detect_boundary_hits(
    parameter_state: ParameterState,
    free_solution: tuple[mp.mpf, ...],
    solved_params: dict[str, mp.mpf],
    errors: dict[str, mp.mpf],
) -> list[str]:
    hits: list[str] = []
    for idx, name in enumerate(parameter_state.free_params):
        lower, upper = parameter_state.bounds.get(name, (None, None))
        value = solved_params.get(name)
        raw_value = mp.mpf(free_solution[idx]) if idx < len(free_solution) else value
        if value is None:
            continue
        clamped = False
        if lower is not None and value == lower and raw_value <= lower:
            clamped = True
        if upper is not None and value == upper and raw_value >= upper:
            clamped = True
        if clamped:
            hits.append(name)
            errors[name] = mp.nan
    return hits


def fit_custom_model(
    model: ModelSpecification,
    parameter_state: ParameterState,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    precision: int = 80,
    weights: list[mp.mpf] | None = None,
    data_sigmas: list[mp.mpf | None] | None = None,
) -> FitResult:
    if not variable_data:
        raise ValueError(
            _dual_msg(
                "拟合需要至少一个自变量。",
                "At least one independent variable is required.",
            )
        )
    n_points = len(next(iter(variable_data.values())))
    if n_points == 0:
        raise ValueError(
            _dual_msg(
                "未找到任何可用于拟合的数据行。",
                "No data rows available for fitting.",
            )
        )

    for values in variable_data.values():
        if len(values) != n_points:
            raise ValueError(
                _dual_msg(
                    "所有自变量的点数必须一致。",
                    "All independent variables must have the same length.",
                )
            )

    with precision_guard(precision):
        observations, targets = _prepare_points(variable_data, target_data)
        if len(targets) != len(observations):
            raise ValueError(
                _dual_msg(
                    "因变量的数据点数量必须与自变量一致。",
                    "Dependent variable length must match independent variables.",
                )
            )
        applied_weights = None
        if weights:
            if len(weights) != len(targets):
                raise ValueError(
                    _dual_msg(
                        "权重数量必须与数据点数量一致。",
                        "Weight count must match number of data points.",
                    )
                )
            applied_weights = [mp.mpf(w) for w in weights]
            for w in applied_weights:
                if w <= 0 or mp.isnan(w):
                    raise ValueError(
                        _dual_msg(
                            "权重必须为正且有限。",
                            "Weights must be positive and finite.",
                        )
                    )

        def _run_once(current_targets: Sequence[mp.mpf], seed_override: tuple[mp.mpf, ...] | None = None) -> _FitComputation:
            gradient_funcs = tuple(
                _gradient_builder(name, model, parameter_state, observations, current_targets, applied_weights)
                for name in parameter_state.free_params
            )
            seed = tuple(seed_override) if seed_override is not None else parameter_state.initial_vector()
            candidates: list[_FitComputation] = []
            last_exc: Exception | None = None
            variants_tried = 0

            def _solve_seed(
                seed_variant: tuple[mp.mpf, ...],
            ) -> tuple[mp.mpf, ...]:
                # Scale convergence to the requested precision: mpmath's
                # default maxsteps=10 silently caps iterations regardless of
                # mp.dps, so fitting at dps=100 would otherwise stop ~10
                # digits shy of the user's configured precision. Tie the
                # tolerance to mp.dps and give findroot enough budget to
                # actually converge.
                tol = mp.mpf(10) ** (-(mp.dps - 5))
                maxsteps = max(50, mp.dps)
                if len(gradient_funcs) == 1:
                    root = mp.findroot(
                        gradient_funcs[0],
                        seed_variant[0],
                        tol=tol,
                        maxsteps=maxsteps,
                    )
                    return (mp.mpf(root),)

                def system(*values: mp.mpf) -> tuple[mp.mpf, ...]:
                    return tuple(func(*values) for func in gradient_funcs)

                candidate = mp.findroot(
                    system,
                    tuple(seed_variant),
                    tol=tol,
                    maxsteps=maxsteps,
                )
                if isinstance(candidate, mp.matrix):
                    candidate = tuple(candidate)
                if not isinstance(candidate, (tuple, list)):
                    candidate = (candidate,)
                return tuple(mp.mpf(val) for val in candidate)

            def _try_variant(seed_variant: tuple[mp.mpf, ...]) -> None:
                nonlocal last_exc, variants_tried
                variants_tried += 1
                try:
                    solution = _solve_seed(seed_variant)
                    solved_params = parameter_state.compose(solution)
                    free_param_count = len(parameter_state.free_params)
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
                        model, solved_params, observations, current_targets, free_param_count, applied_weights
                    )
                    covariance, stat_errors, cov_warning = _compute_covariance(
                        model,
                        solved_params,
                        observations,
                        current_targets,
                        parameter_state.free_params,
                        chi2,
                        dof if dof > 0 else 1,
                        applied_weights,
                    )
                    dependent_errors = _propagate_dependent_errors(parameter_state, solved_params, covariance)
                    stat_errors.update(dependent_errors)
                    boundary_hits = _detect_boundary_hits(parameter_state, solution, solved_params, stat_errors)
                    for name in model.parameters:
                        if name not in stat_errors:
                            stat_errors[name] = mp.mpf("0")
                    details = {
                        "expression": getattr(model, "expression", ""),
                        "dof": int(dof),
                    }
                    if dof <= 0:
                        details["dof_warning"] = (
                            "自由度不足（n-k<=0），协方差/不确定度可能不可靠。 / "
                            "Insufficient degrees of freedom (n-k<=0); covariance/uncertainties may be unreliable."
                        )
                    if applied_weights:
                        details["weighted"] = True
                    if boundary_hits:
                        details["boundary_warning"] = (
                            f"参数命中边界: {', '.join(boundary_hits)}，误差可能不可靠。 / "
                            f"Parameters hit bounds: {', '.join(boundary_hits)}; errors may be unreliable."
                        )
                    if cov_warning:
                        details["covariance_warning"] = cov_warning
                    candidates.append(
                        _FitComputation(
                            params=solved_params,
                            stat_errors=stat_errors,
                            chi2=chi2,
                            reduced_chi2=reduced,
                            aic=aic,
                            bic=bic,
                            r2=r2,
                            rmse=rmse,
                            residuals=residuals,
                            fitted_curve=fitted_curve,
                            covariance=covariance,
                            details=details,
                            free_solution=solution,
                        )
                    )
                except Exception as exc:  # pragma: no cover - retry path
                    last_exc = exc

            # Pass 1: historical seed variants (compatibility).
            attempted_keys: set[tuple[str, ...]] = set()
            for seed_variant in _generate_seed_variants(seed):
                attempted_keys.add(tuple(mp.nstr(v, 60) for v in seed_variant))
                _try_variant(seed_variant)

            # Pass 2: deterministic fallback variants, only if nothing worked.
            if not candidates:
                for seed_variant in _generate_seed_variants_fallback(seed):
                    key = tuple(mp.nstr(v, 60) for v in seed_variant)
                    if key in attempted_keys:
                        continue
                    attempted_keys.add(key)
                    _try_variant(seed_variant)

            if not candidates:
                if last_exc:
                    raise ValueError(
                        _dual_msg(
                            f"非线性求解失败: {last_exc}",
                            f"Nonlinear solve failed: {last_exc}",
                        )
                    ) from last_exc
                raise ValueError(
                    _dual_msg(
                        "非线性求解失败: 无法求解。",
                        "Nonlinear solve failed: no solution found.",
                    )
                )

            def _score(candidate: _FitComputation) -> mp.mpf:
                return candidate.chi2 if not mp.isnan(candidate.chi2) else mp.inf

            best = min(candidates, key=_score)
            best.details.setdefault("seed_variants_tried", int(variants_tried))
            best.details.setdefault("seed_variants_succeeded", int(len(candidates)))
            return best

        base_fit = _run_once(targets)
        system_sigmas = None if applied_weights else data_sigmas
        sys_errors, sys_notes = _estimate_systematic_uncertainty(
            _run_once, base_fit.params, targets, system_sigmas, base_fit.free_solution
        )
        stat_errors, sys_errors, total_errors = combine_error_components(
            base_fit.params, base_fit.stat_errors, sys_errors
        )
        details = dict(base_fit.details)
        if data_sigmas is not None:
            if applied_weights:
                details.setdefault(
                    "uncertainty_note",
                    {
                        "zh": "已用数据不确定度进行加权，仅统计误差；为避免双计，未单独计算系统误差。",
                        "en": "Data uncertainties were used for weighting (statistical only); to avoid double-counting, no separate systematic error was added.",
                    },
                )
            else:
                details.setdefault(
                    "uncertainty_note",
                    {
                        "zh": "统计误差: χ²/权重协方差；系统误差: 数据列整体按 ±σ 重新拟合；总误差为二次和。",
                        "en": "Statistical errors from χ² covariance; systematic errors from ±σ refits of data; total errors combined in quadrature.",
                    },
                )
        if sys_notes:
            details["systematic_warning"] = "; ".join(sys_notes)

        return FitResult(
            params=base_fit.params,
            param_errors=total_errors,
            chi2=base_fit.chi2,
            reduced_chi2=base_fit.reduced_chi2,
            aic=base_fit.aic,
            bic=base_fit.bic,
            r2=base_fit.r2,
            rmse=base_fit.rmse,
            residuals=base_fit.residuals,
            fitted_curve=base_fit.fitted_curve,
            covariance=base_fit.covariance,
            param_errors_stat=stat_errors,
            param_errors_sys=sys_errors,
            param_errors_total=total_errors,
            details=details,
        )
