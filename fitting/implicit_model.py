"""Implicit self-consistent fitting model support."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Sequence, cast

from mpmath import mp

from datalab_latex.expression_engine import safe_eval
from fitting.model_parser import ModelSpecification, MpfCallable
from shared.bilingual import _dual_msg


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CacheKey = tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]


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


class ImplicitEvaluationCache:
    def __init__(self) -> None:
        self.diagnostics = ImplicitSolveDiagnostics()
        self._values: dict[_CacheKey, mp.mpf] = {}

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
        self._values[self._key(var_tuple, param_tuple)] = value

    @staticmethod
    def _key(
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> _CacheKey:
        return (
            tuple((str(idx), cast(str, mp.nstr(value, n=80))) for idx, value in enumerate(var_tuple)),
            tuple((str(idx), cast(str, mp.nstr(value, n=80))) for idx, value in enumerate(param_tuple)),
        )


def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
) -> ModelSpecification:
    """Build a `ModelSpecification` for a one-variable implicit equation."""

    _validate_definition(definition)
    cache = ImplicitEvaluationCache()
    x_names = list(definition.x_variables)
    param_names = list(definition.parameters)

    def _evaluate(
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> mp.mpf:
        solved = _solve_implicit_value(definition, cache, var_tuple, param_tuple)
        scope = _scope_for(definition, var_tuple, param_tuple, solved)
        return mp.mpf(safe_eval(definition.output_expression, scope))

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
        evaluate_func=_evaluate,
        gradient_funcs=gradient_funcs,
    )
    setattr(spec, "implicit_definition", definition)
    setattr(spec, "implicit_diagnostics", cache.diagnostics)
    return spec


def quantum_defect_template() -> ImplicitModelDefinition:
    """Return the default quantum-defect self-consistent model template."""

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
        scale = mp.fabs(base) + 1
        step = max(mp.sqrt(tol) * scale, mp.mpf("1e-8") * scale)
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
    seed = mp.mpf(safe_eval(options.initial, seed_scope))

    def rhs(value: mp.mpf) -> mp.mpf:
        scope = _scope_for(definition, var_tuple, param_tuple, mp.mpf(value))
        return mp.mpf(safe_eval(definition.equation, scope))

    solved: mp.mpf
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

    diagnostics = cache.diagnostics
    diagnostics.points_solved += 1
    if used_fallback:
        diagnostics.root_fallbacks += 1
    diagnostics.max_iterations_used = max(diagnostics.max_iterations_used, iterations_used)
    diagnostics.max_residual = max(diagnostics.max_residual, residual)
    cache.set(var_tuple, param_tuple, solved)
    return solved


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
    return {name: mp.mpf(value) for name, value in constants.items()}


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
