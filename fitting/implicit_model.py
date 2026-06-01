"""Implicit self-consistent fitting model support."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from collections.abc import MutableMapping
from typing import Any, Callable, Sequence, cast

from mpmath import mp

from datalab_latex.expression_engine import safe_eval
from shared.numerics import noise_floor
from fitting.model_parser import ModelSpecification, MpfCallable
from fitting.constraints import ParameterState
from fitting.hp_fitter import FitResult, combine_error_components
from shared.bilingual import _dual_msg
from shared.uncertainty import parse_numeric_value


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MpfKey = tuple[int, int, int, int]
_BranchSignature = tuple[_MpfKey, ...] | None
_CacheKey = tuple[int, int, _BranchSignature, tuple[_MpfKey, ...], tuple[_MpfKey, ...]]
_MAX_IMPLICIT_CACHE_ENTRIES = 10_000
_IMPLICIT_CACHE_EVICT_BATCH = 1_000


@dataclass(frozen=True)
class ImplicitSolveOptions:
    method: str = "fixed_point"
    initial: str = "0"
    tolerance: str = "1e-30"
    max_iterations: int = 80


@dataclass(frozen=True)
class ImplicitModelDefinition:
    x_variables: tuple[str, ...]
    implicit_variable: str
    equation: str
    output_expression: str
    parameters: tuple[str, ...]
    constants: dict[str, str] = field(default_factory=dict)
    solve_options: ImplicitSolveOptions = field(default_factory=ImplicitSolveOptions)


@dataclass
class ImplicitSolveDiagnostics:
    points_solved: int = 0
    root_fallbacks: int = 0
    max_iterations_used: int = 0
    max_residual: mp.mpf = field(default_factory=lambda: mp.mpf("0"))
    warm_start_uses: int = 0


class ImplicitEvaluationCache:
    def __init__(self, target_implicit_candidates: Sequence[tuple[mp.mpf, ...]] | None = None) -> None:
        self.diagnostics = ImplicitSolveDiagnostics()
        self._values: dict[_CacheKey, mp.mpf] = {}
        self._warm_starts: dict[tuple[int, int, tuple[_MpfKey, ...]], mp.mpf] = {}
        self.current_point_index: int | None = None
        self.target_implicit_candidates = target_implicit_candidates

    def get(
        self,
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> mp.mpf | None:
        return self._values.get(self._key(var_tuple, param_tuple))

    def set(
        self,
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
        value: mp.mpf,
    ) -> None:
        self._trim_if_needed(self._values)
        self._trim_if_needed(self._warm_starts)
        self._values[self._key(var_tuple, param_tuple)] = value
        self._warm_starts[self._warm_key(param_tuple)] = value

    def get_warm_start(self, param_tuple: tuple[mp.mpf, ...]) -> mp.mpf | None:
        return self._warm_starts.get(self._warm_key(param_tuple))

    def _key(
        self,
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> _CacheKey:
        return (
            int(mp.dps),
            int(mp.prec),
            self._branch_signature(),
            tuple(cast(_MpfKey, value._mpf_) for value in var_tuple),
            tuple(cast(_MpfKey, value._mpf_) for value in param_tuple),
        )

    def _warm_key(self, param_tuple: tuple[mp.mpf, ...]) -> tuple[int, int, tuple[_MpfKey, ...]]:
        return (
            int(mp.dps),
            int(mp.prec),
            tuple(cast(_MpfKey, value._mpf_) for value in param_tuple),
        )

    def _branch_signature(self) -> _BranchSignature:
        if self.target_implicit_candidates is None or self.current_point_index is None:
            return None
        if self.current_point_index < 0 or self.current_point_index >= len(self.target_implicit_candidates):
            return None
        return tuple(cast(_MpfKey, mp.mpf(value)._mpf_) for value in self.target_implicit_candidates[self.current_point_index])

    @staticmethod
    def _trim_if_needed(cache: MutableMapping[Any, mp.mpf]) -> None:
        if len(cache) < _MAX_IMPLICIT_CACHE_ENTRIES:
            return
        evict_count = max(
            _IMPLICIT_CACHE_EVICT_BATCH,
            len(cache) - _MAX_IMPLICIT_CACHE_ENTRIES + 1,
        )
        for key in list(cache)[:evict_count]:
            del cache[key]


def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    target_implicit_candidates: Sequence[tuple[mp.mpf, ...]] | None = None,
) -> ModelSpecification:
    """Build a `ModelSpecification` for a one-variable implicit equation."""

    _validate_definition(definition)
    del target_data
    cache = ImplicitEvaluationCache(target_implicit_candidates=target_implicit_candidates)
    x_names = list(definition.x_variables)
    param_names = list(definition.parameters)

    def _evaluate(
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> mp.mpf:
        try:
            solved = _solve_implicit_value(definition, cache, var_tuple, param_tuple)
        except ValueError as exc:
            raise ValueError(_implicit_solve_failure_context(definition, cache, var_tuple, param_tuple, exc)) from exc
        scope = _scope_for(definition, var_tuple, param_tuple, solved)
        return mp.mpf(safe_eval(definition.output_expression, scope))

    def _set_point_index(row_index: int | None) -> None:
        cache.current_point_index = row_index

    gradient_funcs: dict[str, MpfCallable] = {}
    for parameter_index, parameter_name in enumerate(param_names):
        gradient_funcs[parameter_name] = _build_numeric_partial(
            definition,
            cache,
            parameter_index=parameter_index,
        )

    spec = ModelSpecification(
        expression=definition.output_expression.strip(),
        variables=x_names,
        parameters=param_names,
        constants=dict(definition.constants),
        evaluate_func=_evaluate,
        gradient_funcs=gradient_funcs,
    )
    setattr(spec, "implicit_definition", definition)
    setattr(spec, "implicit_diagnostics", cache.diagnostics)
    setattr(spec, "set_implicit_point_index", _set_point_index)
    return spec


def can_fit_observed_implicit_variable(
    definition: ImplicitModelDefinition,
) -> bool:
    """Return true when the target column is the implicit variable itself.

    For data such as quantum-defect tables where the observed y column is
    already ``delta`` and the model is ``delta = rhs(n, delta, params)``, the
    statistically useful residual is ``rhs(n, delta_obs, params) - delta_obs``.
    That form does not require solving an inner implicit equation for every
    point and parameter perturbation.
    """

    return (
        definition.output_expression.strip() == definition.implicit_variable
        and definition.implicit_variable not in definition.x_variables
    )


def fit_observed_implicit_variable_linear_model(
    definition: ImplicitModelDefinition,
    parameter_state: ParameterState,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    precision: int = 80,
    weights: list[mp.mpf] | None = None,
    data_sigmas: list[mp.mpf | None] | None = None,
) -> FitResult:
    """Fit an implicit-variable target through a direct linear least-squares path.

    This covers the common self-consistent residual
    ``u_obs ~= equation(x, u_obs, params)`` when the equation is linear in the
    free parameters. It intentionally refuses bounded/dependent free-parameter
    configurations because direct QR cannot honor nonlinear constraints; those
    cases should use the generic implicit solver path.
    """

    if not can_fit_observed_implicit_variable(definition):
        raise ValueError(
            _dual_msg(
                "该隐式模型不能使用观测隐变量快路径。",
                "This implicit model cannot use the observed-implicit-variable fast path.",
            )
        )
    _validate_definition(definition)
    if parameter_state.dependent_defs:
        raise ValueError(
            _dual_msg(
                "带参数表达式约束的隐式模型暂不支持线性快路径。",
                "Implicit models with dependent parameter constraints do not support the linear fast path.",
            )
        )
    bounded = [
        name
        for name in parameter_state.free_params
        if parameter_state.bounds.get(name, (None, None)) != (None, None)
    ]
    if bounded:
        raise ValueError(
            _dual_msg(
                "带边界约束的隐式模型暂不支持线性快路径。",
                "Implicit models with bounded parameters do not support the linear fast path.",
            )
        )

    with mp.workdps(precision):
        targets = [mp.mpf(value) for value in target_data]
        if not targets:
            raise ValueError(
                _dual_msg(
                    "未找到任何可用于拟合的数据行。",
                    "No data rows available for fitting.",
                )
            )
        for name in definition.x_variables:
            if name not in variable_data:
                raise ValueError(
                    _dual_msg(
                        f"缺少自变量数据: {name}",
                        f"Missing independent variable data: {name}",
                    )
                )
            if len(variable_data[name]) != len(targets):
                raise ValueError(
                    _dual_msg(
                        "所有自变量的点数必须一致。",
                        "All independent variables must have the same length.",
                    )
                )
        weight_vec = _normalise_weights(weights, len(targets))

        offsets: list[mp.mpf] = []
        basis_rows: list[list[mp.mpf]] = []
        zero_vector = tuple(mp.mpf("0") for _ in parameter_state.free_params)
        offset_params = parameter_state.compose(zero_vector)
        for row_index, target in enumerate(targets):
            scope_base = _observed_scope_for(definition, variable_data, targets, row_index)
            offset = _eval_equation_with_params(definition, scope_base, offset_params)
            offsets.append(offset)
            row: list[mp.mpf] = []
            for free_index, _name in enumerate(parameter_state.free_params):
                unit = list(zero_vector)
                unit[free_index] = mp.mpf("1")
                unit_params = parameter_state.compose(tuple(unit))
                row.append(_eval_equation_with_params(definition, scope_base, unit_params) - offset)
            basis_rows.append(row)

        _assert_linear_in_free_params(definition, parameter_state, variable_data, targets, offsets, basis_rows)
        return _solve_observed_linear_least_squares(
            definition=definition,
            parameter_state=parameter_state,
            targets=targets,
            offsets=offsets,
            basis_rows=basis_rows,
            weights=weight_vec,
            data_sigmas=data_sigmas,
        )


def default_implicit_template() -> ImplicitModelDefinition:
    """Return the generic default self-consistent model template."""

    return ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0.3",
            tolerance="1e-16",
            max_iterations=80,
        ),
    )


def quantum_defect_template() -> ImplicitModelDefinition:
    """Return the legacy physical quantum-defect template.

    Deprecated for GUI defaults; use `default_implicit_template()` for the
    generic self-consistent example.
    """

    warnings.warn(
        "quantum_defect_template() is deprecated; use default_implicit_template() "
        "for the generic implicit model default.",
        DeprecationWarning,
        stacklevel=2,
    )
    return ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        output_expression="En - R*c/(n-delta)^2",
        parameters=("d0", "d2", "d4", "En"),
        constants={"R": "10973731.568160", "c": "299792458"},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-30",
            max_iterations=80,
        ),
    )


def _build_numeric_partial(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    *,
    parameter_index: int,
) -> MpfCallable:
    options = definition.solve_options
    tol = mp.mpf(options.tolerance)

    def _call(
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> mp.mpf:
        _validate_tuple_lengths(definition, var_tuple, param_tuple, derivative=True)
        base = mp.mpf(param_tuple[parameter_index])
        scale = max(mp.mpf("1"), mp.fabs(base))
        precision_step = mp.power(mp.eps, mp.mpf(1) / 3) * scale
        solve_noise_step = mp.sqrt(tol) * scale
        step = max(precision_step, solve_noise_step)
        plus_params = list(param_tuple)
        minus_params = list(param_tuple)
        plus_params[parameter_index] = base + step
        minus_params[parameter_index] = base - step
        plus_value = _evaluate_output(definition, cache, var_tuple, tuple(plus_params))
        minus_value = _evaluate_output(definition, cache, var_tuple, tuple(minus_params))
        return mp.mpf((plus_value - minus_value) / (2 * step))

    return _call


def _evaluate_output(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
) -> mp.mpf:
    solved = _solve_implicit_value(definition, cache, var_tuple, param_tuple)
    return mp.mpf(safe_eval(definition.output_expression, _scope_for(definition, var_tuple, param_tuple, solved)))


def _solve_implicit_value(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
) -> mp.mpf:
    _validate_tuple_lengths(definition, var_tuple, param_tuple, derivative=False)
    cached = cache.get(var_tuple, param_tuple)
    if cached is not None:
        return cached

    options = definition.solve_options
    tol = mp.mpf(options.tolerance)
    seed_scope = _scope_for(definition, var_tuple, param_tuple, None)
    configured_seed = mp.mpf(safe_eval(options.initial, seed_scope))
    warm_seed = cache.get_warm_start(param_tuple)
    prefer_warm_start = warm_seed is not None and not _initial_depends_on_variables(definition)

    def rhs(value: mp.mpf) -> mp.mpf:
        scope = _scope_for(definition, var_tuple, param_tuple, mp.mpf(value))
        return mp.mpf(safe_eval(definition.equation, scope))

    active_target_candidates = _active_target_candidates(cache)
    seeds: list[tuple[mp.mpf, bool, mp.mpf | None]] = [(configured_seed, False, None)]
    target_seeds = _target_implicit_seeds(cache, rhs, options.method)
    if target_seeds:
        seeds = [(seed, False, seed) for seed in target_seeds] + seeds
    if warm_seed is not None:
        if prefer_warm_start:
            seeds = [(warm_seed, True, None), (configured_seed, False, None)]
            if target_seeds:
                seeds = [(seed, False, seed) for seed in target_seeds] + seeds
        else:
            seeds.append((warm_seed, True, None))
    seeds = _deduplicate_seed_order(seeds)

    last_error: ValueError | None = None
    for seed, used_warm_start, branch_anchor in seeds:
        try:
            solved, iterations_used, used_fallback, residual = _solve_from_seed(
                rhs,
                seed,
                options,
                tol,
            )
            if not _solution_matches_target_branch(solved, active_target_candidates, branch_anchor):
                raise ValueError(
                    _dual_msg(
                        "隐式方程收敛到目标输出分支之外的根。",
                        "Implicit solve converged outside the target output branch.",
                    )
                )
            if used_warm_start:
                cache.diagnostics.warm_start_uses += 1
            break
        except ValueError as exc:
            last_error = exc
    else:
        assert last_error is not None
        raise last_error

    diagnostics = cache.diagnostics
    diagnostics.points_solved += 1
    if used_fallback:
        diagnostics.root_fallbacks += 1
    diagnostics.max_iterations_used = max(diagnostics.max_iterations_used, iterations_used)
    diagnostics.max_residual = max(diagnostics.max_residual, residual)
    cache.set(var_tuple, param_tuple, solved)
    return solved


def _target_implicit_seeds(
    cache: ImplicitEvaluationCache,
    rhs: Callable[[mp.mpf], mp.mpf],
    method: str,
) -> list[mp.mpf]:
    candidates = _active_target_candidates(cache)
    ranked: list[tuple[mp.mpf, mp.mpf]] = []
    for candidate in candidates:
        try:
            rhs_value = rhs(candidate)
            residual = mp.fabs(rhs_value) if method == "root" else mp.fabs(candidate - rhs_value)
        except Exception:
            continue
        if mp.isfinite(residual):
            ranked.append((residual, candidate))
    ranked.sort(key=lambda item: item[0])
    return [candidate for _residual, candidate in ranked]


def _active_target_candidates(cache: ImplicitEvaluationCache) -> list[mp.mpf]:
    if cache.target_implicit_candidates is None or cache.current_point_index is None:
        return []
    if cache.current_point_index < 0 or cache.current_point_index >= len(cache.target_implicit_candidates):
        return []
    return [mp.mpf(candidate) for candidate in cache.target_implicit_candidates[cache.current_point_index]]


def _solution_matches_target_branch(
    solved: mp.mpf,
    candidates: Sequence[mp.mpf],
    branch_anchor: mp.mpf | None,
) -> bool:
    if not candidates:
        return True
    if not mp.isfinite(solved):
        return False
    if branch_anchor is not None:
        return _solution_matches_branch_anchor(solved, branch_anchor, candidates)
    return any(_solution_matches_branch_anchor(solved, candidate, candidates) for candidate in candidates)


def _solution_matches_branch_anchor(solved: mp.mpf, anchor: mp.mpf, candidates: Sequence[mp.mpf]) -> bool:
    unique = sorted({mp.mpf(candidate) for candidate in candidates})
    if not unique:
        return True
    if anchor not in unique:
        anchor = min(unique, key=lambda candidate: mp.fabs(candidate - anchor))
    anchor_distance = mp.fabs(solved - anchor)
    other_distances = [mp.fabs(solved - candidate) for candidate in unique if candidate != anchor]
    if not other_distances:
        return True
    nearest_other = min(other_distances)
    if anchor_distance < nearest_other:
        return True
    return bool(anchor_distance <= _branch_anchor_tolerance(solved, anchor, unique))


def _branch_anchor_tolerance(solved: mp.mpf, anchor: mp.mpf, candidates: Sequence[mp.mpf]) -> mp.mpf:
    scale = max(mp.mpf("1"), mp.fabs(solved), mp.fabs(anchor), *(mp.fabs(candidate) for candidate in candidates))
    return mp.eps * scale * 64


def _deduplicate_seed_order(
    seeds: Sequence[tuple[mp.mpf, bool, mp.mpf | None]],
) -> list[tuple[mp.mpf, bool, mp.mpf | None]]:
    unique: list[tuple[mp.mpf, bool, mp.mpf | None]] = []
    for seed, used_warm_start, branch_anchor in seeds:
        if any(existing == seed and existing_anchor == branch_anchor for existing, _existing_warm, existing_anchor in unique):
            continue
        unique.append((seed, used_warm_start, branch_anchor))
    return unique


def _solve_from_seed(
    rhs: Callable[[mp.mpf], mp.mpf],
    seed: mp.mpf,
    options: ImplicitSolveOptions,
    tol: mp.mpf,
) -> tuple[mp.mpf, int, bool, mp.mpf]:
    iterations_used = 0
    used_fallback = False
    if options.method == "fixed_point":
        current = seed
        for iteration in range(1, int(options.max_iterations) + 1):
            next_value = rhs(current)
            iterations_used = iteration
            if mp.fabs(next_value - current) <= tol:
                solved = next_value
                break
            current = next_value
        else:
            used_fallback = True
            solved = _find_root(rhs, current, options)
            iterations_used = int(options.max_iterations)
    elif options.method == "root":
        iterations_used = 1
        solved = _find_root(rhs, seed, options)
    else:
        raise ValueError(
            _dual_msg(
                f"不支持的隐式求解方法: {options.method}",
                f"Unsupported implicit solve method: {options.method}",
            )
        )

    residual = mp.fabs(solved - rhs(solved))
    if residual > tol and options.method == "fixed_point" and not used_fallback:
        used_fallback = True
        solved = _find_root(rhs, solved, options)
        residual = mp.fabs(solved - rhs(solved))
    return solved, iterations_used, used_fallback, residual


def _initial_depends_on_variables(definition: ImplicitModelDefinition) -> bool:
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", definition.solve_options.initial))
    return any(name in identifiers for name in definition.x_variables)


def _find_root(
    rhs: Callable[[mp.mpf], mp.mpf],
    seed: mp.mpf,
    options: ImplicitSolveOptions,
) -> mp.mpf:
    try:
        return mp.mpf(
            mp.findroot(
                lambda value: value - rhs(mp.mpf(value)),
                seed,
                tol=mp.mpf(options.tolerance),
                maxsteps=int(options.max_iterations),
            )
        )
    except Exception as exc:
        raise ValueError(
            _dual_msg(
                f"隐式方程求解失败: {exc}",
                f"Implicit equation solve failed: {exc}",
            )
        ) from exc


def _implicit_solve_failure_context(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
    exc: ValueError,
) -> str:
    variable_values = {
        name: mp.nstr(value, 30)
        for name, value in zip(definition.x_variables, var_tuple)
    }
    parameter_values = {
        name: mp.nstr(value, 30)
        for name, value in zip(definition.parameters, param_tuple)
    }
    diagnostics = cache.diagnostics
    return str(
        _dual_msg(
        "隐式方程逐点求解失败: "
        f"point_index={cache.current_point_index}, variables={variable_values}, parameters={parameter_values}, "
        f"method={definition.solve_options.method}, residual={mp.nstr(diagnostics.max_residual, 30)}, "
        f"iterations={diagnostics.max_iterations_used}, error={exc}",
        "Per-point implicit solve failed: "
        f"point_index={cache.current_point_index}, variables={variable_values}, parameters={parameter_values}, "
        f"method={definition.solve_options.method}, residual={mp.nstr(diagnostics.max_residual, 30)}, "
        f"iterations={diagnostics.max_iterations_used}, error={exc}",
        )
    )


def _scope_for(
    definition: ImplicitModelDefinition,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
    implicit_value: mp.mpf | None,
) -> dict[str, object]:
    scope: dict[str, object] = {}
    scope.update(_constant_values(definition.constants))
    scope.update(zip(definition.x_variables, var_tuple))
    scope.update(zip(definition.parameters, param_tuple))
    if implicit_value is not None:
        scope[definition.implicit_variable] = implicit_value
    return scope


def _constant_values(constants: dict[str, str]) -> dict[str, mp.mpf]:
    return {name: parse_numeric_value(value) for name, value in constants.items()}


def _observed_scope_for(
    definition: ImplicitModelDefinition,
    variable_data: dict[str, Sequence[mp.mpf]],
    targets: Sequence[mp.mpf],
    row_index: int,
) -> dict[str, object]:
    scope: dict[str, object] = {}
    scope.update(_constant_values(definition.constants))
    for name in definition.x_variables:
        scope[name] = mp.mpf(variable_data[name][row_index])
    scope[definition.implicit_variable] = mp.mpf(targets[row_index])
    return scope


def _eval_equation_with_params(
    definition: ImplicitModelDefinition,
    scope_base: dict[str, object],
    params: dict[str, mp.mpf],
) -> mp.mpf:
    scope = dict(scope_base)
    scope.update(params)
    return mp.mpf(safe_eval(definition.equation, scope))


def _normalise_weights(
    weights: list[mp.mpf] | None,
    row_count: int,
) -> list[mp.mpf] | None:
    if not weights:
        return None
    if len(weights) != row_count:
        raise ValueError(
            _dual_msg(
                "权重数量必须与数据点数量一致。",
                "Weight count must match number of data points.",
            )
        )
    weight_vec = [mp.mpf(weight) for weight in weights]
    if any(weight <= 0 or mp.isnan(weight) for weight in weight_vec):
        raise ValueError(
            _dual_msg(
                "权重必须为正且有限。",
                "Weights must be positive and finite.",
            )
        )
    return weight_vec


def _assert_linear_in_free_params(
    definition: ImplicitModelDefinition,
    parameter_state: ParameterState,
    variable_data: dict[str, Sequence[mp.mpf]],
    targets: Sequence[mp.mpf],
    offsets: Sequence[mp.mpf],
    basis_rows: Sequence[Sequence[mp.mpf]],
) -> None:
    if not parameter_state.free_params:
        return
    trial_values = tuple(
        mp.mpf(idx + 2) / mp.mpf("3")
        for idx, _name in enumerate(parameter_state.free_params)
    )
    trial_params = parameter_state.compose(trial_values)
    tolerance = mp.sqrt(mp.eps) * mp.mpf("100")
    for row_index, target in enumerate(targets):
        scope_base = _observed_scope_for(definition, variable_data, targets, row_index)
        actual = _eval_equation_with_params(definition, scope_base, trial_params)
        linear = offsets[row_index] + mp.fsum(
            coeff * value for coeff, value in zip(basis_rows[row_index], trial_values)
        )
        scale = max(mp.mpf("1"), mp.fabs(actual), mp.fabs(linear), mp.fabs(target))
        if mp.fabs(actual - linear) > tolerance * scale:
            raise ValueError(
                _dual_msg(
                    "隐式方程对自由参数不是线性的，不能使用线性快路径。",
                    "Implicit equation is not linear in free parameters; cannot use the linear fast path.",
                )
            )


def _solve_observed_linear_least_squares(
    *,
    definition: ImplicitModelDefinition,
    parameter_state: ParameterState,
    targets: list[mp.mpf],
    offsets: list[mp.mpf],
    basis_rows: list[list[mp.mpf]],
    weights: list[mp.mpf] | None,
    data_sigmas: list[mp.mpf | None] | None,
) -> FitResult:
    row_count = len(targets)
    free_params = list(parameter_state.free_params)
    col_count = len(free_params)
    if row_count < col_count:
        raise ValueError(
            _dual_msg(
                "数据点数量不足以拟合该模型。",
                "Not enough data points for this model.",
            )
        )
    design = mp.matrix(row_count, col_count)
    rhs = mp.matrix(row_count, 1)
    for i in range(row_count):
        weight_scale = mp.sqrt(weights[i]) if weights else mp.mpf("1")
        for j in range(col_count):
            design[i, j] = mp.mpf(basis_rows[i][j]) * weight_scale
        rhs[i] = (mp.mpf(targets[i]) - mp.mpf(offsets[i])) * weight_scale
    try:
        q_matrix, r_matrix = mp.qr(design)
        qt_rhs = q_matrix.T * rhs
        r_top = r_matrix[:col_count, :col_count]
        rhs_top = qt_rhs[:col_count, :]
        coeff_matrix = mp.lu_solve(r_top, rhs_top)
    except ZeroDivisionError as exc:
        raise ValueError(
            _dual_msg(
                "设计矩阵奇异，无法拟合。",
                "Design matrix is singular, cannot fit.",
            )
        ) from exc
    free_solution = tuple(mp.mpf(coeff_matrix[i, 0]) for i in range(col_count))
    params = parameter_state.compose(free_solution)
    fitted_curve = [
        offsets[i] + mp.fsum(basis_rows[i][j] * free_solution[j] for j in range(col_count))
        for i in range(row_count)
    ]
    residuals = [fitted_curve[i] - targets[i] for i in range(row_count)]
    if weights:
        chi2 = mp.fsum(weight * (residual * residual) for weight, residual in zip(weights, residuals))
        total_weight = mp.fsum(weights)
        mean_target = (
            mp.fsum(weight * target for weight, target in zip(weights, targets)) / total_weight
            if total_weight > 0 else mp.fsum(targets) / row_count
        )
        sst = mp.fsum(weight * (target - mean_target) ** 2 for weight, target in zip(weights, targets))
        rmse = mp.sqrt(chi2 / total_weight)
    else:
        chi2 = mp.fsum(residual * residual for residual in residuals)
        mean_target = mp.fsum(targets) / row_count
        sst = mp.fsum((target - mean_target) ** 2 for target in targets)
        rmse = mp.sqrt(chi2 / row_count)
    dof = row_count - col_count
    if dof <= 0:
        reduced = mp.nan
        r2 = mp.nan
        aic = mp.nan
        bic = mp.nan
    else:
        reduced = chi2 / dof
        r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
        eps = noise_floor()
        noise = chi2 / row_count if chi2 > eps else eps
        aic = 2 * col_count + row_count * mp.log(noise)
        bic = col_count * mp.log(row_count) + row_count * mp.log(noise)

    covariance, stat_errors, cov_warning = _linear_covariance(
        design=design,
        free_params=free_params,
        chi2=chi2,
        dof=dof if dof > 0 else 1,
    )
    for name in definition.parameters:
        stat_errors.setdefault(name, mp.mpf("0"))
    sys_errors: dict[str, mp.mpf] = {}
    stat_errors, sys_errors, total_errors = combine_error_components(params, stat_errors, sys_errors)
    details: dict[str, object] = {
        "expression": definition.equation,
        "dof": int(dof),
        "implicit_fast_path": "observed_implicit_linear",
    }
    if weights:
        details["weighted"] = True
    if data_sigmas is not None:
        if weights:
            details["uncertainty_note"] = {
                "zh": "已用数据不确定度进行加权，仅统计误差；为避免双计，未单独计算系统误差。",
                "en": "Data uncertainties were used for weighting (statistical only); to avoid double-counting, no separate systematic error was added.",
            }
        else:
            details["uncertainty_note"] = {
                "zh": "已保存数据不确定度；该线性快路径当前未执行 ±σ 系统重拟合。",
                "en": "Data uncertainties were retained; this linear fast path does not currently run +/- sigma systematic refits.",
            }
    if cov_warning:
        details["covariance_warning"] = cov_warning
    return FitResult(
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


def _linear_covariance(
    *,
    design: mp.matrix,
    free_params: list[str],
    chi2: mp.mpf,
    dof: int,
) -> tuple[list[list[mp.mpf]], dict[str, mp.mpf], str | None]:
    col_count = len(free_params)
    try:
        inv = (design.T * design) ** -1
    except ZeroDivisionError:
        return (
            [[mp.nan for _ in range(col_count)] for _ in range(col_count)],
            {name: mp.nan for name in free_params},
            "协方差矩阵奇异，参数不确定度不可用。 / Covariance matrix is singular; parameter uncertainties unavailable.",
        )
    sigma2 = chi2 / dof if dof > 0 else mp.nan
    covariance = [[inv[i, j] * sigma2 for j in range(col_count)] for i in range(col_count)]
    errors = {
        name: (
            mp.sqrt(covariance[idx][idx])
            if not mp.isnan(covariance[idx][idx]) and covariance[idx][idx] >= 0
            else mp.nan
        )
        for idx, name in enumerate(free_params)
    }
    warning = None
    if any(mp.isnan(value) or mp.isinf(value) for row in covariance for value in row):
        warning = "协方差矩阵病态或奇异，参数不确定度可能不可靠。 / Covariance matrix is ill-conditioned or singular; parameter uncertainties may be unreliable."
    return covariance, errors, warning


def _validate_definition(definition: ImplicitModelDefinition) -> None:
    _validate_names(
        list(definition.x_variables)
        + [definition.implicit_variable]
        + list(definition.parameters)
        + list(definition.constants)
    )
    if not definition.equation.strip():
        raise ValueError(_dual_msg("未提供隐式方程。", "Implicit equation not provided."))
    if not definition.output_expression.strip():
        raise ValueError(_dual_msg("未提供输出表达式。", "Output expression not provided."))
    if not definition.parameters:
        raise ValueError(_dual_msg("至少需要一个参数以执行拟合。", "Need at least one parameter to fit."))
    if definition.solve_options.max_iterations <= 0:
        raise ValueError(_dual_msg("最大迭代次数必须为正数。", "Max iterations must be positive."))
    if mp.mpf(definition.solve_options.tolerance) <= 0:
        raise ValueError(_dual_msg("求解容差必须为正数。", "Solve tolerance must be positive."))
    if definition.solve_options.method not in {"fixed_point", "root"}:
        raise ValueError(
            _dual_msg(
                f"不支持的隐式求解方法: {definition.solve_options.method}",
                f"Unsupported implicit solve method: {definition.solve_options.method}",
            )
        )
    _reject_initial_implicit_reference(definition)
    _prevalidate_expressions(definition)


def _validate_names(names: Sequence[str]) -> None:
    invalid = [name for name in names if not _IDENTIFIER_RE.match(name)]
    if invalid:
        joined = ", ".join(invalid)
        raise ValueError(_dual_msg(f"无效名称: {joined}", f"Invalid names: {joined}"))
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(
            _dual_msg(
                f"变量名/参数名/常量名存在重复: {joined}",
                f"Duplicate variable/parameter/constant names: {joined}",
            )
        )


def _reject_initial_implicit_reference(definition: ImplicitModelDefinition) -> None:
    pattern = rf"\b{re.escape(definition.implicit_variable)}\b"
    if re.search(pattern, definition.solve_options.initial):
        raise ValueError(
            _dual_msg(
                "初始值表达式不能引用隐式变量。",
                "The initial expression cannot reference the implicit variable.",
            )
        )


def _prevalidate_expressions(definition: ImplicitModelDefinition) -> None:
    dummy_vars = tuple(mp.mpf(idx + 2) for idx, _ in enumerate(definition.x_variables))
    dummy_params = tuple(mp.mpf("1") for _ in definition.parameters)
    base_scope = _scope_for(definition, dummy_vars, dummy_params, None)
    implicit_scope = dict(base_scope)
    implicit_scope[definition.implicit_variable] = mp.mpf("0.5")
    validations = (
        ("initial", definition.solve_options.initial, base_scope),
        ("equation", definition.equation, implicit_scope),
        ("output", definition.output_expression, implicit_scope),
    )
    for label, expression, scope in validations:
        try:
            mp.mpf(safe_eval(expression, scope))
        except Exception as exc:
            raise ValueError(
                _dual_msg(
                    f"{label} 表达式无效: {exc}",
                    f"Invalid {label} expression: {exc}",
                )
            ) from exc


def _validate_tuple_lengths(
    definition: ImplicitModelDefinition,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
    *,
    derivative: bool,
) -> None:
    if len(var_tuple) == len(definition.x_variables) and len(param_tuple) == len(definition.parameters):
        return
    if derivative:
        message = _dual_msg(
            "隐式模型偏导参数数量不匹配。",
            "Implicit model derivative received mismatched argument counts.",
        )
    else:
        message = _dual_msg(
            "隐式模型求值参数数量不匹配。",
            "Implicit model evaluation received mismatched argument counts.",
        )
    raise ValueError(message)
