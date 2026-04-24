"""Parameter constraint helper utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Mapping

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, convert_xor
from mpmath import mp

from shared.bilingual import _dual_msg

_logger = logging.getLogger(__name__)

_MIN_SYMPY_VERSION = (1, 13, 0)


def _parse_version_tuple(version_text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw in str(version_text or "").split("."):
        num = ""
        for ch in raw:
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            break
        parts.append(int(num))
    return tuple(parts)


_sympy_version = _parse_version_tuple(getattr(sp, "__version__", ""))
if _sympy_version and _sympy_version < _MIN_SYMPY_VERSION:
    required = ".".join(map(str, _MIN_SYMPY_VERSION))
    current = getattr(sp, "__version__", "unknown")
    raise ImportError(
        f"sympy>={required} is required for fitting constraints, but sympy=={current} is installed."
    )

_SAFE_TRANSFORMS = standard_transformations + (convert_xor,)
_SAFE_MATH_FUNCS: dict[str, object] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "exp": sp.exp,
    "log": sp.log,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "pi": sp.pi,
    "E": sp.E,
}


@dataclass
class DependentDefinition:
    evaluate: Callable[[dict[str, mp.mpf]], mp.mpf]
    dependencies: tuple[str, ...]
    partials: dict[str, Callable[[dict[str, mp.mpf]], mp.mpf]]


@dataclass
class ParameterState:
    free_params: list[str]
    bounds: dict[str, tuple[mp.mpf | None, mp.mpf | None]]
    initial_guess: dict[str, mp.mpf]
    fixed_values: dict[str, mp.mpf]
    dependent_defs: dict[str, DependentDefinition]

    def initial_vector(self) -> tuple[mp.mpf, ...]:
        return tuple(self.initial_guess[name] for name in self.free_params)

    def compose(self, free_vector: tuple[mp.mpf, ...]) -> dict[str, mp.mpf]:
        params: dict[str, mp.mpf] = {}
        for name, value in zip(self.free_params, free_vector):
            lower, upper = self.bounds.get(name, (None, None))
            mp_value = mp.mpf(value)
            if lower is not None and mp_value < lower:
                mp_value = lower
            if upper is not None and mp_value > upper:
                mp_value = upper
            params[name] = mp_value
        params.update(self.fixed_values)
        pending = dict(self.dependent_defs)
        while pending:
            solved = []
            for name, definition in pending.items():
                try:
                    params[name] = mp.mpf(definition.evaluate(params))
                    solved.append(name)
                except KeyError:
                    continue
            for name in solved:
                pending.pop(name, None)
            if not solved:
                unresolved = ", ".join(sorted(pending))
                raise ValueError(
                    f"参数表达式存在循环或缺失依赖，无法求解: {unresolved}。 / Cyclic or unresolved parameter expressions: {unresolved}."
                )
        return params


def _to_mpf(value, default: mp.mpf = mp.mpf("0")) -> mp.mpf:
    if value is None:
        return default
    return mp.mpf(value)


def build_parameter_state(config: Mapping[str, Mapping[str, object]], parameter_names: list[str]) -> ParameterState:
    free_params: list[str] = []
    bounds: dict[str, tuple[mp.mpf | None, mp.mpf | None]] = {}
    initial_guess: dict[str, mp.mpf] = {}
    fixed_values: dict[str, mp.mpf] = {}
    dependent_defs: dict[str, DependentDefinition] = {}

    available_symbols = {name: sp.symbols(name) for name in parameter_names}
    order_index = {name: idx for idx, name in enumerate(parameter_names)}

    for name in parameter_names:
        conf = config.get(name, {}) if config else {}
        if conf.get("expr"):
            expr_text = str(conf["expr"])
            try:
                parsed = _parse_expr_safe(expr_text, available_symbols)
                definition = _build_dependent_definition(
                    name, parsed, available_symbols, order_index
                )
            except Exception as exc:
                raise ValueError(f"无法解析参数 {name} 的表达式: {exc} / Failed to parse expression for {name}: {exc}") from exc

            dependent_defs[name] = definition
            continue
        if conf.get("fixed") is not None:
            fixed_values[name] = _to_mpf(
                conf.get("fixed", conf.get("initial", conf.get("value", 0))), mp.mpf("0")
            )
            continue
        free_params.append(name)
        initial_guess[name] = _to_mpf(conf.get("initial", conf.get("value", 1.0)), mp.mpf("1"))
        min_value = conf.get("min")
        max_value = conf.get("max")
        bounds[name] = (
            _to_mpf(min_value) if min_value is not None else None,
            _to_mpf(max_value) if max_value is not None else None,
        )

    if not free_params:
        raise ValueError(
            _dual_msg(
                "至少需要一个自由参数以执行拟合。",
                "Need at least one free parameter to fit.",
            )
        )

    return ParameterState(
        free_params=free_params,
        bounds=bounds,
        initial_guess=initial_guess,
        fixed_values=fixed_values,
        dependent_defs=dependent_defs,
    )


def _build_dependent_definition(
    target_name: str,
    expr,
    available_symbols: dict[str, sp.Symbol],
    order_index: dict[str, int],
) -> DependentDefinition:
    dependencies, evaluator = _lambdify_expression(expr, available_symbols, order_index, exclude=target_name)
    partials: dict[str, Callable[[dict[str, mp.mpf]], mp.mpf]] = {}
    for dep in dependencies:
        derivative = sp.diff(expr, available_symbols[dep])
        _, partial_callable = _lambdify_expression(derivative, available_symbols, order_index)
        partials[dep] = partial_callable
    return DependentDefinition(
        evaluate=evaluator,
        dependencies=dependencies,
        partials=partials,
    )


def _lambdify_expression(
    expr,
    available_symbols: dict[str, sp.Symbol],
    order_index: dict[str, int],
    exclude: str | None = None,
) -> tuple[tuple[str, ...], Callable[[dict[str, mp.mpf]], mp.mpf]]:
    dependencies: list[str] = []
    for symbol in expr.free_symbols:
        symbol_name = str(symbol)
        if exclude and symbol_name == exclude:
            continue
        if symbol_name not in available_symbols:
            raise ValueError(
                _dual_msg(
                    f"参数表达式引用了未知参数 {symbol_name}。",
                    f"Unknown parameter referenced: {symbol_name}.",
                )
            )
        dependencies.append(symbol_name)
    dependencies = sorted(set(dependencies), key=lambda item: order_index.get(item, 0))
    lambda_symbols = [available_symbols[dep] for dep in dependencies]
    expr_lambda = sp.lambdify(lambda_symbols, expr, "mpmath")

    # Defense-in-depth: sp.lambdify seeds the callable's __globals__ with the
    # full builtins module (including __import__, open, eval, exec). The
    # SymPy parser upstream (_parse_expr_safe) is already whitelist-restricted,
    # but stripping __builtins__ here ensures a bypass of the parser can't
    # reach dangerous primitives via the callable's globals. mpmath-backed
    # lambdify callables do not need Python's builtins — all operators are
    # pulled from the mpmath namespace already present in __globals__.
    try:
        expr_lambda.__globals__["__builtins__"] = {}
    except Exception:
        # Some exotic callables may not expose __globals__ as a writable dict;
        # in that case the parser-level whitelist remains the primary defense.
        # Log at DEBUG so this is discoverable if it ever trips in the wild
        # without changing behavior for callers.
        _logger.debug(
            "Could not strip __builtins__ from lambdify callable; "
            "parser-level whitelist remains primary defense.",
            exc_info=True,
        )

    def _evaluate(params, deps=tuple(dependencies), expr_lambda=expr_lambda):
        missing = [dep for dep in deps if dep not in params]
        if missing:
            raise KeyError(missing[0])
        if deps:
            values = [params[dep] for dep in deps]
            return mp.mpf(expr_lambda(*values))
        return mp.mpf(expr_lambda())

    return tuple(dependencies), _evaluate


def _parse_expr_safe(expr_text: str, available_symbols: dict[str, sp.Symbol]):
    """Safely parse user expressions using a restricted Sympy environment."""
    local_dict: dict[str, object] = {**available_symbols, **_SAFE_MATH_FUNCS}
    try:
        return parse_expr(
            expr_text,
            local_dict=local_dict,
            global_dict={"__builtins__": {}, "Symbol": sp.Symbol},
            transformations=_SAFE_TRANSFORMS,
            evaluate=True,
        )
    except Exception as exc:  # pragma: no cover - delegated to sympy internals
        raise ValueError(f"无法解析表达式: {exc}") from exc
