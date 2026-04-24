from __future__ import annotations

import ast
import re

from mpmath import mp

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr


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


def _dual_msg(zh: str, en: str) -> str:
    """Join zh/en messages so the GUI can localize with _localize_text."""
    return f"{zh} / {en}"


def _split_dual(text: str) -> tuple[str, str]:
    """Return (zh, en) parts if dual, otherwise the same text for both."""
    if " / " in text:
        left, right = text.split(" / ", 1)
        return left.strip(), right.strip()
    return text, text


_ALLOWED_CONSTANTS: dict[str, mp.mpf] = {
    "Pi": mp.pi,
    "E": mp.e,
}

_ALLOWED_FUNCTIONS = {
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

_BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: mp.power(a, b),
    ast.Mod: lambda a, b: a % b,
}

_UNARY_OPERATORS = {
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
    """Resolve a bare name to a variable/constant/function, or None if unknown."""
    if name in variables:
        return variables[name]
    if name in _ALLOWED_CONSTANTS:
        return _ALLOWED_CONSTANTS[name]
    if name in _ALLOWED_FUNCTIONS:
        return _ALLOWED_FUNCTIONS[name]
    return None


def safe_eval(expression: str, var_dict: dict[str, object]):
    """
    Safely evaluate a mathematical expression with given variables.

    Notes:
    - Uses an AST allowlist (no attribute access, no kwargs, no comprehensions).
    - Enforces a maximum AST depth/node count to prevent recursion/CPU abuse.
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
    except SyntaxError as exc:
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

    variables = {name: _mp(value) for name, value in (var_dict or {}).items()}
    return _evaluate_ast(tree.body, variables)


def _evaluate_ast(node, variables):
    if isinstance(node, ast.Expression):
        return _evaluate_ast(node.body, variables)
    if isinstance(node, ast.Attribute):
        raise ValueError(_dual_msg("不支持的属性访问。", "Attribute access is not supported."))
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return _mp(node.value)
        raise ValueError(_dual_msg("不支持的常量类型。", "Unsupported constant type."))
    if isinstance(node, ast.Name):
        resolved = _resolve_name(node.id, variables)
        if resolved is not None:
            return resolved
        raise ValueError(_dual_msg(f"未知变量或函数: {node.id}", f"Unknown variable or function: {node.id}"))
    if isinstance(node, ast.BinOp):
        left = _evaluate_ast(node.left, variables)
        right = _evaluate_ast(node.right, variables)
        operator_type = type(node.op)
        if operator_type in _BINARY_OPERATORS:
            return _BINARY_OPERATORS[operator_type](left, right)
        raise ValueError(_dual_msg(f"不支持的二元操作: {operator_type}", f"Unsupported binary operator: {operator_type}"))
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_ast(node.operand, variables)
        operator_type = type(node.op)
        if operator_type in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[operator_type](operand)
        raise ValueError(_dual_msg(f"不支持的单目操作: {operator_type}", f"Unsupported unary operator: {operator_type}"))
    if isinstance(node, ast.Call):
        func = _resolve_callable(node.func, variables)
        if node.keywords:
            raise ValueError(_dual_msg("不支持带关键字参数的函数。", "Keyword arguments are not supported."))
        args = [_evaluate_ast(arg, variables) for arg in node.args]
        return func(*args)
    raise ValueError(_dual_msg(f"不支持的语法节点: {type(node)}", f"Unsupported syntax node: {type(node)}"))


def _resolve_callable(func_node, variables):
    if isinstance(func_node, ast.Name):
        func_value = _resolve_name(func_node.id, variables)
        if func_value is not None and callable(func_value):
            return func_value
    raise ValueError(_dual_msg(f"不支持的函数调用: {ast.dump(func_node)}", f"Unsupported function call: {ast.dump(func_node)}"))


def _format_latex_formula_manual(formula_str: str) -> str:
    """Fallback manual LaTeX formatter for very simple formulas."""

    def _find_matching(expr: str, start: int) -> int:
        depth = 0
        for idx in range(start, len(expr)):
            if expr[idx] == "(":
                depth += 1
            elif expr[idx] == ")":
                depth -= 1
                if depth == 0:
                    return idx
        return -1

    def _wrap_calls(expr: str) -> str:
        functions = {
            "sinh": "\\sinh",
            "cosh": "\\cosh",
            "tanh": "\\tanh",
            "asin": "\\arcsin",
            "acos": "\\arccos",
            "atan": "\\arctan",
            "sin": "\\sin",
            "cos": "\\cos",
            "tan": "\\tan",
            "exp": "\\exp",
            "log": "\\log",
            "ln": "\\ln",
            "sqrt": "\\sqrt",
            "abs": "\\abs",
        }
        i = 0
        out: list[str] = []
        while i < len(expr):
            matched = False
            for name, latex_name in functions.items():
                prefix = f"{name}("
                if expr.startswith(prefix, i):
                    start = i + len(prefix) - 1
                    end = _find_matching(expr, start)
                    if end == -1:
                        out.append(expr[i:])
                        i = len(expr)
                        matched = True
                        break
                    inner = _wrap_calls(expr[start + 1 : end])
                    if name == "abs":
                        out.append(f"\\left|{inner}\\right|")
                    elif name == "sqrt":
                        out.append(f"{latex_name}{{{inner}}}")
                    else:
                        out.append(f"{latex_name}\\left({inner}\\right)")
                    i = end + 1
                    matched = True
                    break
            if not matched:
                out.append(expr[i])
                i += 1
        return "".join(out)

    latex_str = formula_str.replace("**", "^")
    latex_str = latex_str.replace("*", " \\cdot ")
    latex_str = latex_str.replace("pi", "\\pi")
    latex_str = re.sub(r"\be\b", "e", latex_str)
    latex_str = _wrap_calls(latex_str)
    latex_str = re.sub(r"\^(\w+)", r"^{\1}", latex_str)
    latex_str = re.sub(r"\^\(([^)]+)\)", r"^{(\1)}", latex_str)
    latex_str = re.sub(r"\s+", " ", latex_str)
    return latex_str.strip()


def format_latex_formula(formula_str: str) -> str:
    """
    Format a formula string for LaTeX display.

    Primary path uses Sympy's parser + latex to handle nesting robustly.
    Falls back to a lightweight manual formatter if parsing fails.
    """
    local_funcs = {
        "sin": sp.sin,
        "cos": sp.cos,
        "tan": sp.tan,
        "asin": sp.asin,
        "acos": sp.acos,
        "atan": sp.atan,
        "sinh": sp.sinh,
        "cosh": sp.cosh,
        "tanh": sp.tanh,
        "exp": sp.exp,
        "log": sp.log,
        "ln": sp.log,
        "sqrt": sp.sqrt,
        "abs": sp.Abs,
        "pi": sp.pi,
        "e": sp.E,
    }
    try:
        expr = parse_expr(
            formula_str,
            local_dict=local_funcs,
            global_dict={},
            evaluate=False,
        )
        return sp.latex(expr)
    except Exception:
        return _format_latex_formula_manual(formula_str)
