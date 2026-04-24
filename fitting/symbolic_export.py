"""Export DataLab expressions to SymPy / Mathematica syntax.

DataLab's safe expression engine uses Mathematica-flavoured syntax
(``Sin[x]``, ``Exp[x]``, ``Pi``) for all fit formulas, error-
propagation expressions, and custom extrapolation models. Users
often want to continue analysis in SymPy (for symbolic integration
/ Taylor series) or Mathematica (the canonical scientific CAS).

``to_sympy(expr)`` emits a Python-valid expression that
``sympy.sympify`` parses; ``to_mathematica(expr)`` emits the
Mathematica canonical form. Both operate via AST transformation
(not regex), so nested function calls, operator precedence, and
constant substitution are preserved exactly.

**Completeness contract**: every function in
``datalab_latex.expression_engine``'s allowlist must have a render
entry in ``SYMPY_FUNCTION_MAP`` and ``MATHEMATICA_FUNCTION_MAP``.
The ``test_allowlist_coverage_*`` regression tests fail if a new
function is added to the engine without a matching export entry —
the goal is to prevent silent "unknown function" errors after
export.
"""

from __future__ import annotations

import ast

from datalab_latex.expression_engine import (
    _ALLOWED_CONSTANTS,
    _ALLOWED_FUNCTIONS,
    _ast_metrics,
    _normalize_expression,
)

__all__ = [
    "MATHEMATICA_FUNCTION_MAP",
    "SYMPY_FUNCTION_MAP",
    "to_mathematica",
    "to_sympy",
]


# Mathematica-style function name → SymPy canonical name. When a
# function is added to the expression engine's allowlist, it must also
# be added here, or the test_allowlist_coverage_sympy test fails.
SYMPY_FUNCTION_MAP: dict[str, str] = {
    "Sin": "sin",
    "Cos": "cos",
    "Tan": "tan",
    "Asin": "asin",
    "Acos": "acos",
    "Atan": "atan",
    "Sinh": "sinh",
    "Cosh": "cosh",
    "Tanh": "tanh",
    "Asinh": "asinh",
    "Acosh": "acosh",
    "Atanh": "atanh",
    "Exp": "exp",
    "Log": "log",
    "Ln": "log",
    "Log10": "log",  # SymPy log with base -- use log(x, 10) if needed
    "Sqrt": "sqrt",
    "Power": "Pow",
    "Abs": "Abs",
    "Erf": "erf",
    "Gamma": "gamma",
    "Zeta": "zeta",
    "Hyp0f1": "hyper",
    "Hyp1f1": "hyper",
    "Hyp2f1": "hyper",
    "PolyLog": "polylog",
    "BesselJ": "besselj",
    "BesselY": "bessely",
    "Airy": "airyai",
}

MATHEMATICA_FUNCTION_MAP: dict[str, str] = {
    # Input IS Mathematica-ish; we verify + canonicalise rather than
    # transform. Entries map 1:1 to themselves so a future
    # lowercased-input bug surfaces here.
    name: name for name in SYMPY_FUNCTION_MAP
}

_SYMPY_CONSTANT_MAP = {
    "Pi": "pi",
    "E": "E",
}

_MATHEMATICA_CONSTANT_MAP = {
    "Pi": "Pi",
    "E": "E",
}


def _normalize_for_parse(expr: str) -> str:
    """Pre-normalise: unicode minus → ASCII, Mathematica brackets → Python."""
    if expr is None:
        raise ValueError("expression must not be None")
    stripped = expr.strip()
    if not stripped:
        raise ValueError("expression must not be empty")
    normalised = stripped.replace("\u2212", "-")
    return _normalize_expression(normalised)


def _ensure_allowed_names(tree: ast.AST) -> None:
    """Walk the AST and verify every Name refers to the allowlist or
    a free variable. Raises ValueError if a ``Frobnicate[x]`` slips
    through (the engine would catch this at safe_eval; we catch it
    at export so the error surface matches)."""
    allowed = set(_ALLOWED_FUNCTIONS) | set(_ALLOWED_CONSTANTS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id not in allowed:
                # A user-defined variable can never appear as a call
                # target — only a whitelisted function can. Reject
                # so export doesn't ship an unknown call to SymPy.
                raise ValueError(
                    f"Unknown function in expression: {func.id!r}. "
                    "Add it to datalab_latex/expression_engine allowlist "
                    "and to SYMPY_FUNCTION_MAP before exporting."
                )


def _transform_for_sympy(node: ast.AST) -> ast.AST:
    """Rename function calls and constants in-place for SymPy output."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id in SYMPY_FUNCTION_MAP:
                func.id = SYMPY_FUNCTION_MAP[func.id]
        elif isinstance(child, ast.Name):
            if child.id in _SYMPY_CONSTANT_MAP:
                child.id = _SYMPY_CONSTANT_MAP[child.id]
    return node


def _transform_for_mathematica(node: ast.AST) -> ast.AST:
    """Mathematica output leaves known names as-is (input IS Mathematica).
    Just verify they're known."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id not in MATHEMATICA_FUNCTION_MAP:
                # Not a known call — already caught by _ensure_allowed_names,
                # but defensive.
                raise ValueError(
                    f"Unknown function in expression: {func.id!r}"
                )
    return node


def _render(node: ast.AST, style: str) -> str:
    """Unified un-parser for both SymPy and Mathematica output.

    Formatting convention (stable across both):
    - additive operators (+ / -) get spaces around them
    - multiplicative (* / / / ^/** / Mod) are tight
    - unary +/- tight
    - calls render as ``f(x)`` for SymPy, ``f[x]`` for Mathematica

    ``style`` is ``"sympy"`` or ``"mathematica"`` — determines power
    operator spelling and call brackets.
    """
    if isinstance(node, ast.Expression):
        return _render(node.body, style)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, float) and node.value.is_integer():
            return str(int(node.value))
        return str(node.value)
    if isinstance(node, ast.Name):
        constant_map = (
            _SYMPY_CONSTANT_MAP if style == "sympy"
            else _MATHEMATICA_CONSTANT_MAP
        )
        return constant_map.get(node.id, node.id)
    if isinstance(node, ast.BinOp):
        left = _render(node.left, style)
        right = _render(node.right, style)
        op_type = type(node.op)
        if op_type is ast.Add:
            return f"{left} + {right}"
        if op_type is ast.Sub:
            return f"{left} - {right}"
        if op_type is ast.Mult:
            return f"{left}*{right}"
        if op_type is ast.Div:
            return f"{left}/{right}"
        if op_type is ast.Pow:
            pow_op = "**" if style == "sympy" else "^"
            return f"{left}{pow_op}{right}"
        if op_type is ast.Mod:
            return f"{left} % {right}" if style == "sympy" else f"Mod[{left},{right}]"
        raise ValueError(f"Unsupported operator: {op_type.__name__}")
    if isinstance(node, ast.UnaryOp):
        operand = _render(node.operand, style)
        op_type = type(node.op)
        if op_type is ast.UAdd:
            return f"+{operand}"
        if op_type is ast.USub:
            return f"-{operand}"
        raise ValueError(f"Unsupported unary op: {op_type.__name__}")
    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name):
            raise ValueError("Call target must be a simple name")
        args = ", ".join(_render(a, style) for a in node.args)
        if style == "sympy":
            return f"{func.id}({args})"
        return f"{func.id}[{args}]"
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def _parse_expr(expr: str) -> ast.Module:
    """Parse a DataLab expression into an AST with the same safety
    caps the engine uses. Raises ValueError on syntax errors or
    excessive AST size."""
    normalised = _normalize_for_parse(expr)
    try:
        tree = ast.parse(normalised, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Malformed expression: {exc}") from exc
    # Reuse the engine's depth/node caps so export surface can't be
    # abused for CPU-heavy AST walks.
    max_depth, node_count = _ast_metrics(tree)
    if max_depth > 50 or node_count > 500:
        raise ValueError(
            f"Expression AST too deep ({max_depth}) or large "
            f"({node_count} nodes) — simplify before export"
        )
    _ensure_allowed_names(tree)
    return tree


def to_sympy(expr: str) -> str:
    """Emit a SymPy-parseable string from a DataLab expression."""
    tree = _parse_expr(expr)
    transformed = _transform_for_sympy(tree)
    return _render(transformed.body, style="sympy")


def to_mathematica(expr: str) -> str:
    """Emit a Mathematica-canonical string from a DataLab expression."""
    tree = _parse_expr(expr)
    transformed = _transform_for_mathematica(tree)
    return _render(transformed.body, style="mathematica")
