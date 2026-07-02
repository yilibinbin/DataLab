from __future__ import annotations

import ast
from functools import lru_cache
import re
from typing import Any, Callable, cast

from mpmath import mp

# Canonical bilingual message helpers live in shared.bilingual so every
# frontend/worker/scientific module resolves _dual_msg to the same function
# object. Re-exported here for backward compatibility — data_extrapolation_
# latex_latest auto-re-exports this module's public symbols, so existing
# callers of `from data_extrapolation_latex_latest import _dual_msg` keep
# working without change.
from shared.bilingual import _dual_msg, _split_dual  # noqa: F401  (re-export)


MAX_AST_DEPTH = 400
MAX_AST_NODES = 50_000


def _mp(value: object) -> mp.mpf:
    """Convert arbitrary values to mp.mpf with minimal precision loss."""
    if isinstance(value, mp.mpf):
        return value
    if isinstance(value, (int, float)):
        return mp.mpf(value)
    try:
        return mp.mpf(value)
    except Exception:
        return mp.mpf(str(value))


_ALLOWED_CONSTANTS: dict[str, mp.mpf] = {
    "Pi": mp.pi,
    "E": mp.e,
}

_ALLOWED_FUNCTIONS: dict[str, Callable[..., Any]] = {
    # Basic
    "Sin": mp.sin,
    "Cos": mp.cos,
    "Tan": mp.tan,
    "Asin": mp.asin,
    "Acos": mp.acos,
    "Atan": mp.atan,
    "Sinh": mp.sinh,
    "Cosh": mp.cosh,
    "Tanh": mp.tanh,
    "Asinh": mp.asinh,
    "Acosh": mp.acosh,
    "Atanh": mp.atanh,
    # Exponential/log
    "Exp": mp.exp,
    "Log": mp.log,
    "Ln": mp.log,
    "Log10": mp.log10,
    "Sqrt": mp.sqrt,
    "Power": mp.power,
    # Common
    "Abs": mp.fabs,
    "Erf": mp.erf,
    "Gamma": mp.gamma,
    # Special
    "Zeta": mp.zeta,
    "Hyp0f1": mp.hyp0f1,
    "Hyp1f1": mp.hyp1f1,
    "Hyp2f1": mp.hyp2f1,
    "PolyLog": mp.polylog,
    "BesselJ": mp.besselj,
    "BesselY": mp.bessely,
    "Airy": mp.airyai,
}

_BINARY_OPERATORS: dict[
    type[ast.operator], Callable[[Any, Any], Any]
] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: mp.power(a, b),
    ast.Mod: lambda a, b: a % b,
}

_UNARY_OPERATORS: dict[
    type[ast.unaryop], Callable[[Any], Any]
] = {
    ast.UAdd: lambda a: a,
    ast.USub: lambda a: -a,
}


def list_allowed_functions() -> dict[str, list[str]]:
    """Public helper for UIs: report the allowlist used by safe_eval."""
    return {
        "functions": sorted(_ALLOWED_FUNCTIONS.keys(), key=str.lower),
        "constants": sorted(_ALLOWED_CONSTANTS.keys(), key=str.lower),
    }


def _normalize_expression(expr: str) -> str:
    """Convert Mathematica-style syntax to a Python-evaluable expression."""
    # Replace Mathematica-style brackets: f[x] -> f(x)
    normalized = re.sub(r"([A-Za-z][A-Za-z0-9_]*)\s*\[", r"\1(", expr)
    normalized = normalized.replace("]", ")")
    # Caret to Python power
    normalized = normalized.replace("^", "**")
    return normalized


def _ast_metrics(root: ast.AST) -> tuple[int, int]:
    max_depth = 0
    node_count = 0
    stack: list[tuple[ast.AST, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if depth > max_depth:
            max_depth = depth
        for child in ast.iter_child_nodes(node):
            stack.append((child, depth + 1))
    return max_depth, node_count


def _detect_lowercase_allowed_function_calls(expression: str) -> set[str]:
    """Return lowercase function names that match the allowlist but are not capitalized."""
    allowed_lower = {name.lower() for name in _ALLOWED_FUNCTIONS}
    matches = re.findall(r"\b([a-z][a-zA-Z0-9_]*)\s*[\[(]", expression or "")
    return {name for name in matches if name.lower() in allowed_lower}


def _resolve_name(name: str, variables: dict[str, object]) -> object | None:
    """Resolve a bare name to a variable/constant/function, or None if unknown.

    Returns ``object | None`` (not ``Any``) so callers must check the
    ``None`` sentinel; the single widening point is the ``cast(...)``
    in ``_resolve_callable`` after its ``callable()`` guard.
    """
    if name in variables:
        return variables[name]
    if name in _ALLOWED_CONSTANTS:
        # mp.mpf is Any (no stubs); cast restores the narrower contract.
        return cast(object, _ALLOWED_CONSTANTS[name])
    if name in _ALLOWED_FUNCTIONS:
        return cast(object, _ALLOWED_FUNCTIONS[name])
    return None


@lru_cache(maxsize=512)
def _parse_validated_expression(expression: str) -> tuple[ast.AST, str]:
    """Normalize, parse, and safety-check an expression, returning its AST body
    and the normalized source. Cached on the raw expression string: the parse
    and validation are pure functions of the text, so a fit loop that evaluates
    the same model thousands of times parses it exactly once (P1-1).

    Raising calls are not cached by lru_cache, so an invalid expression still
    re-validates (and re-raises) on every call — only successful parses persist.
    """
    bad_calls = _detect_lowercase_allowed_function_calls(expression)
    if bad_calls:
        bad_names = ", ".join(sorted(bad_calls))
        raise ValueError(
            _dual_msg(
                f"函数名需首字母大写（Mathematica 风格），检测到: {bad_names}",
                f"Function names must be capitalized (Mathematica style), found: {bad_names}",
            )
        )

    expr = _normalize_expression(expression)
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, RecursionError, MemoryError) as exc:
        # RecursionError is raised by CPython's ast.parse when the expression
        # tree exceeds the interpreter recursion limit (e.g. pathological
        # 10k+ term sums); MemoryError can occur on extremely large inputs.
        # Surface both as a clean bilingual ValueError rather than leaking
        # an untrusted RecursionError up the stack.
        raise ValueError(
            _dual_msg(
                f"无法解析表达式 '{expression}': {exc}",
                f"Failed to parse expression '{expression}': {exc}",
            )
        ) from exc

    depth, nodes = _ast_metrics(tree)
    if depth > MAX_AST_DEPTH or nodes > MAX_AST_NODES:
        raise ValueError(
            _dual_msg(
                "表达式过于复杂（嵌套过深或节点过多）。请简化表达式。",
                "Expression is too complex (nesting too deep or too many nodes). Please simplify it.",
            )
        )

    return tree.body, expr


def safe_eval(expression: str, var_dict: dict[str, object]) -> Any:
    """
    Safely evaluate a mathematical expression with given variables.

    Notes:
    - Uses an AST allowlist (no attribute access, no kwargs, no comprehensions).
    - Enforces a maximum AST depth/node count to prevent recursion/CPU abuse.
    - The parse + validation is cached per expression string (see
      ``_parse_validated_expression``); only variable binding varies per call.
    """
    body, expr = _parse_validated_expression(expression)
    variables = {name: _mp(value) for name, value in (var_dict or {}).items()}
    return _evaluate_ast(body, variables, expr)


def compile_expression(expression: str) -> Callable[[dict[str, object]], Any]:
    """Parse/validate ``expression`` once and return a fast evaluator.

    The returned callable takes a variable dict and evaluates the pre-parsed AST
    without re-parsing — the hot-path API for tight loops (fitting residuals /
    gradients, Monte-Carlo sampling). Equivalent to ``safe_eval(expression, d)``
    but with the parse hoisted out of the loop. Validation errors surface here,
    at compile time, exactly as ``safe_eval`` would raise them.
    """
    body, expr = _parse_validated_expression(expression)

    def _evaluate(var_dict: dict[str, object]) -> Any:
        variables = {name: _mp(value) for name, value in (var_dict or {}).items()}
        return _evaluate_ast(body, variables, expr)

    return _evaluate


def _evaluate_ast(node: ast.AST, variables: dict[str, object], source: str) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate_ast(node.body, variables, source)
    if isinstance(node, ast.Attribute):
        raise ValueError(_dual_msg("不支持的属性访问。", "Attribute access is not supported."))
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError(_dual_msg("不支持的常量类型。", "Unsupported constant type."))
        if isinstance(node.value, (int, float)):
            return _mp_numeric_literal(node, source)
        raise ValueError(_dual_msg("不支持的常量类型。", "Unsupported constant type."))
    if isinstance(node, ast.Name):
        resolved = _resolve_name(node.id, variables)
        if resolved is not None:
            return resolved
        raise ValueError(_dual_msg(f"未知变量或函数: {node.id}", f"Unknown variable or function: {node.id}"))
    if isinstance(node, ast.BinOp):
        left = _evaluate_ast(node.left, variables, source)
        right = _evaluate_ast(node.right, variables, source)
        bin_op_type = type(node.op)
        if bin_op_type in _BINARY_OPERATORS:
            try:
                return _BINARY_OPERATORS[bin_op_type](left, right)
            except ZeroDivisionError as exc:
                # '/' and '%' raise ZeroDivisionError on a zero divisor; the
                # module's contract is ValueError-only, so re-raise as one.
                raise ValueError(
                    _dual_msg("表达式求值时除以零。", "Division by zero during evaluation.")
                ) from exc
        raise ValueError(_dual_msg(f"不支持的二元操作: {bin_op_type}", f"Unsupported binary operator: {bin_op_type}"))
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_ast(node.operand, variables, source)
        un_op_type = type(node.op)
        if un_op_type in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[un_op_type](operand)
        raise ValueError(_dual_msg(f"不支持的单目操作: {un_op_type}", f"Unsupported unary operator: {un_op_type}"))
    if isinstance(node, ast.Call):
        func = _resolve_callable(node.func, variables)
        if node.keywords:
            raise ValueError(_dual_msg("不支持带关键字参数的函数。", "Keyword arguments are not supported."))
        args = [_evaluate_ast(arg, variables, source) for arg in node.args]
        return func(*args)
    raise ValueError(_dual_msg(f"不支持的语法节点: {type(node)}", f"Unsupported syntax node: {type(node)}"))


def _mp_numeric_literal(node: ast.Constant, source: str) -> mp.mpf:
    """Convert numeric literals from source text, not Python's rounded AST value."""
    if isinstance(node.value, int):
        return _mp(node.value)
    text = ast.get_source_segment(source, node)
    if text:
        return mp.mpf(text.replace("_", ""))
    raise ValueError(
        _dual_msg(
            "无法恢复数值字面量的原始文本，已拒绝避免精度损失。",
            "Numeric literal source text is unavailable; refusing to avoid precision loss.",
        )
    )


def _resolve_callable(
    func_node: ast.AST, variables: dict[str, object]
) -> Callable[..., Any]:
    if isinstance(func_node, ast.Name):
        func_value = _resolve_name(func_node.id, variables)
        if func_value is not None and callable(func_value):
            # ``func_value`` is ``Any`` because the lookup tables hold
            # untyped mpmath callables — the ``callable()`` check has
            # narrowed the runtime type but mypy doesn't know that.
            # Hence the explicit cast to satisfy the return contract.
            return cast(Callable[..., Any], func_value)
    raise ValueError(_dual_msg(f"不支持的函数调用: {ast.dump(func_node)}", f"Unsupported function call: {ast.dump(func_node)}"))


def format_latex_formula(formula_str: str) -> str:
    """
    Compatibility placeholder for callers that need a display string.

    LaTeX-specific rendering belongs in ``datalab_latex.formula_render_service``.
    The shared expression engine stays independent of LaTeX and UI packages.
    """
    return formula_str
