from __future__ import annotations

from collections import OrderedDict
from mpmath import mp
from typing import Any, Callable

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

from .expression_engine import _normalize_expression, safe_eval


_SymbolicCallable = Callable[..., object]

_SYMBOLIC_PARTIALS_CACHE: "OrderedDict[tuple[str, tuple[str, ...]], list[_SymbolicCallable | None] | None]" = OrderedDict()
_SYMBOLIC_PARTIALS_CACHE_MAX = 64


_SYMBOLIC_HESSIAN_CACHE: "OrderedDict[tuple[str, tuple[str, ...]], list[list[_SymbolicCallable | None]] | None]" = OrderedDict()
_SYMBOLIC_HESSIAN_CACHE_MAX = 32


_SYMPY_GLOBALS: dict[str, object] = {
    "__builtins__": {},
    "Integer": sp.Integer,
    "Rational": sp.Rational,
    "Float": sp.Float,
    "Symbol": sp.Symbol,
    "Add": sp.Add,
    "Mul": sp.Mul,
    "Pow": sp.Pow,
    "Mod": sp.Mod,
}


def _build_sympy_local_dict(variables: list[str]) -> tuple[list[sp.Symbol], dict[str, object]]:
    symbols: list[sp.Symbol] = []
    local_dict: dict[str, object] = {}
    for name in variables:
        sym = sp.Symbol(name)
        symbols.append(sym)
        local_dict[name] = sym

    if "Pi" not in local_dict:
        local_dict["Pi"] = sp.pi
    if "E" not in local_dict:
        local_dict["E"] = sp.E

    def _maybe_add(name: str, obj: object) -> None:
        if name not in local_dict:
            local_dict[name] = obj

    _maybe_add("Sin", sp.sin)
    _maybe_add("Cos", sp.cos)
    _maybe_add("Tan", sp.tan)
    _maybe_add("Asin", sp.asin)
    _maybe_add("Acos", sp.acos)
    _maybe_add("Atan", sp.atan)
    _maybe_add("Sinh", sp.sinh)
    _maybe_add("Cosh", sp.cosh)
    _maybe_add("Tanh", sp.tanh)
    _maybe_add("Asinh", sp.asinh)
    _maybe_add("Acosh", sp.acosh)
    _maybe_add("Atanh", sp.atanh)
    _maybe_add("Exp", sp.exp)
    _maybe_add("Log", sp.log)
    _maybe_add("Ln", sp.log)

    def _log10(x: Any) -> Any:  # sympy.Expr — no stubs, so Any (see pyproject mypy overrides).
        return sp.log(x, 10)

    _maybe_add("Log10", _log10)
    _maybe_add("Sqrt", sp.sqrt)
    _maybe_add("Power", sp.Pow)
    _maybe_add("Abs", sp.Abs)
    _maybe_add("Erf", sp.erf)
    _maybe_add("Gamma", sp.gamma)
    _maybe_add("Zeta", sp.zeta)
    _maybe_add("PolyLog", sp.polylog)
    _maybe_add("BesselJ", sp.besselj)
    _maybe_add("BesselY", sp.bessely)
    _maybe_add("Airy", sp.airyai)

    def _hyp0f1(b: Any, z: Any) -> Any:  # sympy.Expr — no stubs, so Any (see pyproject mypy overrides).
        return sp.hyper([], [b], z)

    def _hyp1f1(a: Any, b: Any, z: Any) -> Any:
        return sp.hyper([a], [b], z)

    def _hyp2f1(a: Any, b: Any, c: Any, z: Any) -> Any:
        return sp.hyper([a, b], [c], z)

    _maybe_add("Hyp0f1", _hyp0f1)
    _maybe_add("Hyp1f1", _hyp1f1)
    _maybe_add("Hyp2f1", _hyp2f1)

    return symbols, local_dict


def _auto_finite_diff_step(x_value: object, derivative_order: int) -> mp.mpf:
    """
    Choose a finite-difference step size based on the current mp.dps.

    Rule of thumb (central differences with O(h^2) truncation):
      - 1st derivative: h ~ eps^(1/3) * max(1, |x|)
      - 2nd derivative: h ~ eps^(1/4) * max(1, |x|)
    """
    try:
        x = mp.mpf(x_value)
    except Exception:
        x = mp.mpf("0")
    try:
        eps = mp.eps
        order = max(1, int(derivative_order or 1))
        base = mp.power(eps, mp.mpf(1) / (order + 2))
    except Exception:
        base = mp.mpf("1e-8")
    try:
        scale = max(mp.mpf("1"), mp.fabs(x))
    except Exception:
        scale = mp.mpf("1")
    h = base * scale
    try:
        if h <= 0 or not mp.isfinite(h):
            return mp.mpf("1e-8")
    except Exception:
        pass
    if h == 0:
        return mp.mpf("1e-8")
    return mp.mpf(h)


def _auto_central_diff_step(x_value: object) -> mp.mpf:
    """Compatibility wrapper: automatic step for 1st-derivative central differences."""
    return _auto_finite_diff_step(x_value, derivative_order=1)


def numerical_second_partial_derivative(
    formula_str: str,
    variables: list[str],
    values: list[object],
    var_index_i: int,
    var_index_j: int,
    *,
    hi: mp.mpf | None = None,
    hj: mp.mpf | None = None,
) -> mp.mpf:
    """
    Compute a 2nd partial derivative numerically using central differences.

    - Diagonal (i==j): (f(x+h) - 2f(x) + f(x-h)) / h^2
    - Mixed (i!=j): (f(++ ) - f(+-) - f(-+) + f(--) ) / (4 hi hj)
    """
    if not variables:
        raise ValueError("Numerical derivative requires variables.")
    if var_index_i < 0 or var_index_i >= len(variables):
        raise ValueError("var_index_i out of range.")
    if var_index_j < 0 or var_index_j >= len(variables):
        raise ValueError("var_index_j out of range.")
    if len(values) != len(variables):
        raise ValueError("Values length must match variables length.")

    i = int(var_index_i)
    j = int(var_index_j)
    if hi is None:
        hi = _auto_finite_diff_step(values[i], derivative_order=2)
    if hj is None:
        hj = _auto_finite_diff_step(values[j], derivative_order=2)

    base_values = [mp.mpf(v) for v in values]
    var_dict = dict(zip(variables, base_values))
    name_i = variables[i]
    name_j = variables[j]

    if i == j:
        f0 = safe_eval(formula_str, var_dict)
        var_dict_p = var_dict.copy()
        var_dict_p[name_i] = base_values[i] + hi
        fp = safe_eval(formula_str, var_dict_p)
        var_dict_m = var_dict.copy()
        var_dict_m[name_i] = base_values[i] - hi
        fm = safe_eval(formula_str, var_dict_m)
        return mp.mpf((fp - mp.mpf("2") * f0 + fm) / (hi * hi))

    var_pp = var_dict.copy()
    var_pp[name_i] = base_values[i] + hi
    var_pp[name_j] = base_values[j] + hj
    f_pp = safe_eval(formula_str, var_pp)

    var_pm = var_dict.copy()
    var_pm[name_i] = base_values[i] + hi
    var_pm[name_j] = base_values[j] - hj
    f_pm = safe_eval(formula_str, var_pm)

    var_mp = var_dict.copy()
    var_mp[name_i] = base_values[i] - hi
    var_mp[name_j] = base_values[j] + hj
    f_mp = safe_eval(formula_str, var_mp)

    var_mm = var_dict.copy()
    var_mm[name_i] = base_values[i] - hi
    var_mm[name_j] = base_values[j] - hj
    f_mm = safe_eval(formula_str, var_mm)

    denom = mp.mpf("4") * hi * hj
    return mp.mpf((f_pp - f_pm - f_mp + f_mm) / denom)


def _build_symbolic_hessian(
    formula_str: str, variables: list[str]
) -> list[list[_SymbolicCallable | None]] | None:
    """Build a Hessian (2nd partial derivatives) callable table for a formula."""
    if not formula_str or not variables:
        return None

    normalized = _normalize_expression(formula_str)

    symbols, local_dict = _build_sympy_local_dict(variables)

    try:
        expr = parse_expr(
            normalized,
            local_dict=local_dict,
            global_dict=_SYMPY_GLOBALS,
            evaluate=True,
        )
    except Exception:
        return None

    modules_dict = {
        "hyper": mp.hyper,
        "sign": mp.sign,
    }
    if hasattr(mp, "polygamma"):
        modules_dict["polygamma"] = mp.polygamma
    if hasattr(mp, "digamma"):
        modules_dict["digamma"] = mp.digamma
    modules = [modules_dict, "mpmath"]

    size = len(symbols)
    hessian: list[list[_SymbolicCallable | None]] = [[None for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for j in range(size):
            try:
                derivative = sp.diff(expr, symbols[i], symbols[j])
            except Exception:
                hessian[i][j] = None
                continue
            try:
                if derivative.has(sp.Derivative):
                    hessian[i][j] = None
                    continue
            except Exception:
                pass
            try:
                hessian[i][j] = sp.lambdify(symbols, derivative, modules=modules)
            except Exception:
                hessian[i][j] = None
    return hessian


def _get_symbolic_hessian(
    formula_str: str, variables: list[str]
) -> list[list[_SymbolicCallable | None]] | None:
    key = (formula_str or "", tuple(variables or []))
    if key in _SYMBOLIC_HESSIAN_CACHE:
        _SYMBOLIC_HESSIAN_CACHE.move_to_end(key)
        return _SYMBOLIC_HESSIAN_CACHE[key]
    if len(_SYMBOLIC_HESSIAN_CACHE) >= _SYMBOLIC_HESSIAN_CACHE_MAX:
        _SYMBOLIC_HESSIAN_CACHE.popitem(last=False)
    hessian = _build_symbolic_hessian(formula_str, variables)
    _SYMBOLIC_HESSIAN_CACHE[key] = hessian
    return hessian


def _build_symbolic_partials(
    formula_str: str, variables: list[str]
) -> list[_SymbolicCallable | None] | None:
    """
    Try to build symbolic partial derivative callables for error propagation.

    Returns a list aligned with `variables`, where each entry is a callable
    produced by sympy.lambdify (or None if that partial cannot be represented).
    Returns None if parsing fails entirely.
    """
    if not formula_str or not variables:
        return None

    normalized = _normalize_expression(formula_str)

    # Build a restricted Sympy environment that mirrors safe_eval's registry
    symbols, local_dict = _build_sympy_local_dict(variables)

    try:
        expr = parse_expr(
            normalized,
            local_dict=local_dict,
            global_dict=_SYMPY_GLOBALS,
            evaluate=True,
        )
    except Exception:
        return None

    modules = [
        {
            # Ensure mpmath has these even if sympy's default mapping misses them.
            "hyper": mp.hyper,
            "sign": mp.sign,
        },
        "mpmath",
    ]

    partials: list[_SymbolicCallable | None] = []
    for sym in symbols:
        try:
            derivative = sp.diff(expr, sym)
        except Exception:
            partials.append(None)
            continue
        # If sympy couldn't resolve, it may leave Derivative(...) nodes.
        try:
            if derivative.has(sp.Derivative):
                partials.append(None)
                continue
        except Exception:
            pass
        try:
            func = sp.lambdify(symbols, derivative, modules=modules)
        except Exception:
            partials.append(None)
            continue
        partials.append(func)

    return partials


def _get_symbolic_partials(
    formula_str: str, variables: list[str]
) -> list[_SymbolicCallable | None] | None:
    key = (formula_str or "", tuple(variables or []))
    if key in _SYMBOLIC_PARTIALS_CACHE:
        _SYMBOLIC_PARTIALS_CACHE.move_to_end(key)
        return _SYMBOLIC_PARTIALS_CACHE[key]
    if len(_SYMBOLIC_PARTIALS_CACHE) >= _SYMBOLIC_PARTIALS_CACHE_MAX:
        _SYMBOLIC_PARTIALS_CACHE.popitem(last=False)
    partials = _build_symbolic_partials(formula_str, variables)
    _SYMBOLIC_PARTIALS_CACHE[key] = partials
    return partials


def numerical_partial_derivative(
    formula_str: str,
    variables: list[str],
    values: list[object],
    var_index: int,
    h: mp.mpf | None = None,
) -> mp.mpf:
    """
    Compute a first-order partial derivative numerically using central differences.

    Args:
        formula_str: Formula expression string.
        variables: Variable names used in the formula.
        values: Values corresponding to variables.
        var_index: Index of variable to differentiate with respect to.
        h: Step size. If None, choose an automatic step based on mp.dps.

    Returns:
        Numerical partial derivative as mp.mpf.
    """
    if not variables:
        raise ValueError("Numerical derivative requires variables.")
    if var_index < 0 or var_index >= len(variables):
        raise ValueError("var_index out of range.")
    if len(values) != len(variables):
        raise ValueError("Values length must match variables length.")

    base_values = [mp.mpf(v) for v in values]
    if h is None:
        h = _auto_central_diff_step(base_values[var_index])
    else:
        h = mp.mpf(h)

    # Create variable dictionary
    var_dict = dict(zip(variables, base_values))

    # Evaluate at x + h
    var_dict_plus = var_dict.copy()
    var_dict_plus[variables[var_index]] = base_values[var_index] + h
    f_plus = safe_eval(formula_str, var_dict_plus)

    # Evaluate at x - h
    var_dict_minus = var_dict.copy()
    var_dict_minus[variables[var_index]] = base_values[var_index] - h
    f_minus = safe_eval(formula_str, var_dict_minus)

    # Compute partial derivative using central difference
    return mp.mpf((f_plus - f_minus) / (mp.mpf("2") * h))
