"""Restricted SymPy parsing helpers shared by DataLab symbolic features."""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

SYMPY_GLOBALS: dict[str, object] = {
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

SYMPY_TRANSFORMATIONS = standard_transformations + (convert_xor,)


def _log10(x: Any) -> Any:
    return sp.log(x, 10)


def _hyp0f1(b: Any, z: Any) -> Any:
    return sp.hyper([], [b], z)


def _hyp1f1(a: Any, b: Any, z: Any) -> Any:
    return sp.hyper([a], [b], z)


def _hyp2f1(a: Any, b: Any, c: Any, z: Any) -> Any:
    return sp.hyper([a, b], [c], z)


SYMPY_CONSTANTS: dict[str, object] = {
    "Pi": sp.pi,
    "E": sp.E,
}

SYMPY_FUNCTIONS: dict[str, object] = {
    "Sin": sp.sin,
    "Cos": sp.cos,
    "Tan": sp.tan,
    "Asin": sp.asin,
    "Acos": sp.acos,
    "Atan": sp.atan,
    "Sinh": sp.sinh,
    "Cosh": sp.cosh,
    "Tanh": sp.tanh,
    "Asinh": sp.asinh,
    "Acosh": sp.acosh,
    "Atanh": sp.atanh,
    "Exp": sp.exp,
    "Log": sp.log,
    "Ln": sp.log,
    "Log10": _log10,
    "Sqrt": sp.sqrt,
    "Power": sp.Pow,
    "Abs": sp.Abs,
    "Erf": sp.erf,
    "Gamma": sp.gamma,
    "Zeta": sp.zeta,
    "PolyLog": sp.polylog,
    "BesselJ": sp.besselj,
    "BesselY": sp.bessely,
    "Airy": sp.airyai,
    "Hyp0f1": _hyp0f1,
    "Hyp1f1": _hyp1f1,
    "Hyp2f1": _hyp2f1,
}


def normalize_symbolic_expression(expression: str) -> str:
    """Normalize DataLab/Mathematica-style syntax into SymPy parse syntax."""

    normalized = expression.replace("^", "**")
    for _ in range(20):
        updated = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[", r"\1(", normalized)
        if updated == normalized:
            break
        normalized = updated
    return normalized.replace("]", ")")


def build_sympy_local_dict(
    variables: Sequence[str],
) -> tuple[list[sp.Symbol], dict[str, object]]:
    symbols: list[sp.Symbol] = []
    local_dict: dict[str, object] = {}
    for name in variables:
        sym = sp.Symbol(name)
        symbols.append(sym)
        local_dict[name] = sym

    for name, value in SYMPY_CONSTANTS.items():
        local_dict.setdefault(name, value)
    for name, value in SYMPY_FUNCTIONS.items():
        local_dict.setdefault(name, value)

    return symbols, local_dict


def parse_symbolic_expression(
    expression: str,
    *,
    variables: Sequence[str],
    evaluate: bool = True,
    normalize: bool = True,
) -> tuple[Any, dict[str, sp.Symbol]]:
    """Parse a symbolic expression using DataLab's restricted SymPy registry."""

    normalized = normalize_symbolic_expression(expression) if normalize else expression
    _validate_symbolic_ast(normalized)
    symbols, local_dict = build_sympy_local_dict(variables)
    expr = parse_expr(
        normalized,
        local_dict=local_dict,
        global_dict=SYMPY_GLOBALS,
        transformations=SYMPY_TRANSFORMATIONS,
        evaluate=evaluate,
    )
    if not isinstance(expr, sp.Expr):
        raise ValueError("Symbolic expression did not produce a SymPy expression.")
    symbol_map = {name: symbol for name, symbol in zip(variables, symbols, strict=True)}
    return expr, symbol_map


def _validate_symbolic_ast(expression: str) -> None:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid symbolic expression syntax: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.Attribute
            | ast.Subscript
            | ast.Tuple
            | ast.List
            | ast.Set
            | ast.Dict
            | ast.Lambda
            | ast.ListComp
            | ast.SetComp
            | ast.DictComp
            | ast.GeneratorExp
            | ast.Await
            | ast.Yield
            | ast.YieldFrom
            | ast.NamedExpr,
        ):
            raise ValueError("Unsupported symbolic expression syntax.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float | complex):
            raise ValueError("Unsupported symbolic expression literal.")
        if isinstance(node, ast.Name) and "__" in node.id:
            raise ValueError("Unsupported symbolic expression name.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Unsupported symbolic expression syntax.")
            if node.func.id not in SYMPY_FUNCTIONS:
                raise ValueError("Unsupported symbolic function call.")
            if node.keywords:
                raise ValueError("Keyword arguments are not supported in symbolic expressions.")
