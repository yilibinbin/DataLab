"""Lightweight AST-backed formula-to-LaTeX export helpers."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Final

from shared.expression_registry import normalize_expression as _normalize_datalab_expression


_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOWERCASE_GREEK: Final = frozenset(
    {
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "theta",
        "lambda",
        "mu",
        "pi",
        "sigma",
        "omega",
    }
)
_UPPERCASE_GREEK: Final = frozenset({"gamma", "delta", "theta", "lambda", "pi", "sigma", "omega"})
_FUNCTION_COMMANDS: Final = {
    "sin": r"\sin",
    "cos": r"\cos",
    "tan": r"\tan",
    "sinh": r"\sinh",
    "cosh": r"\cosh",
    "tanh": r"\tanh",
    "asin": r"\arcsin",
    "acos": r"\arccos",
    "atan": r"\arctan",
    "arcsin": r"\arcsin",
    "arccos": r"\arccos",
    "arctan": r"\arctan",
    "log": r"\ln",
    "ln": r"\ln",
    "exp": r"\exp",
}
_MATHEMATICA_FUNCTION_ALIASES: Final = {
    "arcsin": "asin",
    "arccos": "acos",
    "arctan": "atan",
}
_PREC_ADD: Final = 10
_PREC_MUL: Final = 20
_PREC_POW: Final = 30
_PREC_UNARY: Final = 40
_PREC_ATOM: Final = 100


class FormulaLatexExportError(ValueError):
    """Base error for unsupported lightweight formula export syntax."""


class UnsupportedFormulaSyntaxError(FormulaLatexExportError):
    """Raised when Python AST parsing succeeds but the node is unsupported."""


@dataclass(frozen=True)
class _Rendered:
    text: str
    precedence: int
    simple: bool = False


def expression_to_latex(
    source: str,
    *,
    language: str = "datalab",
    name_latex_overrides: Mapping[str, str] | None = None,
) -> str:
    """Render supported DataLab/Python/Mathematica expression syntax as LaTeX.

    The returned string is delimiter-free: callers add ``$...$`` or other display
    delimiters at their boundary. Unsupported syntax raises ``ValueError`` with
    a short diagnostic instead of returning partially converted LaTeX.
    """

    normalized = normalize_expression(source, language=language)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        message = exc.msg or "invalid syntax"
        raise FormulaLatexExportError(f"Unsupported formula syntax: {message}.") from exc
    return _render_node(tree.body, name_latex_overrides or {}).text


def normalize_expression(source: str, *, language: str = "datalab") -> str:
    """Normalize supported DataLab/Mathematica syntax to Python AST syntax."""

    text = (source or "").strip()
    if not text:
        raise FormulaLatexExportError("Formula is empty.")

    language_key = language.lower()
    if language_key not in {"datalab", "python", "mathematica"}:
        raise FormulaLatexExportError(f"Unsupported formula language: {language}.")

    text = text.replace("^", "**")
    if language_key in {"datalab", "mathematica"}:
        text = _normalize_datalab_expression(text)
    return text


def _render_node(node: ast.AST, name_latex_overrides: Mapping[str, str] | None = None) -> _Rendered:
    overrides = name_latex_overrides or {}
    if isinstance(node, ast.BinOp):
        return _render_binop(node, overrides)
    if isinstance(node, ast.UnaryOp):
        return _render_unary(node, overrides)
    if isinstance(node, ast.Call):
        return _render_call(node, overrides)
    if isinstance(node, ast.Name):
        if node.id in overrides:
            return _Rendered(overrides[node.id], _PREC_ATOM, simple=True)
        return _Rendered(_format_identifier(node.id), _PREC_ATOM, simple=True)
    if isinstance(node, ast.Constant):
        return _render_constant(node)
    raise UnsupportedFormulaSyntaxError(f"Unsupported formula syntax node: {node.__class__.__name__}.")


def _render_binop(node: ast.BinOp, name_latex_overrides: Mapping[str, str]) -> _Rendered:
    if isinstance(node.op, ast.Add):
        return _render_add_sub(node.left, node.right, " + ", name_latex_overrides=name_latex_overrides)
    if isinstance(node.op, ast.Sub):
        return _render_add_sub(
            node.left,
            node.right,
            " - ",
            subtract=True,
            name_latex_overrides=name_latex_overrides,
        )
    if isinstance(node.op, ast.Mult):
        left = _render_child(
            node.left,
            _PREC_MUL,
            compact_when_wrapped=True,
            name_latex_overrides=name_latex_overrides,
        )
        right = _render_child(
            node.right,
            _PREC_MUL,
            compact_when_wrapped=True,
            name_latex_overrides=name_latex_overrides,
        )
        return _Rendered(f"{left} \\cdot {right}", _PREC_MUL)
    if isinstance(node.op, ast.Div):
        numerator = _render_node(node.left, name_latex_overrides).text
        denominator = _render_node(node.right, name_latex_overrides).text
        return _Rendered(rf"\frac{{{numerator}}}{{{denominator}}}", _PREC_ATOM)
    if isinstance(node.op, ast.Pow):
        return _render_power(node, name_latex_overrides)
    raise UnsupportedFormulaSyntaxError(f"Unsupported formula operator: {node.op.__class__.__name__}.")


def _render_add_sub(
    left_node: ast.AST,
    right_node: ast.AST,
    operator: str,
    *,
    subtract: bool = False,
    name_latex_overrides: Mapping[str, str],
) -> _Rendered:
    left = _render_child(
        left_node,
        _PREC_ADD,
        compact_when_wrapped=True,
        name_latex_overrides=name_latex_overrides,
    )
    right_rendered = _render_node(right_node, name_latex_overrides)
    right = right_rendered.text
    if right_rendered.precedence < _PREC_ADD or (
        subtract and isinstance(right_node, ast.BinOp) and isinstance(right_node.op, ast.Add | ast.Sub)
    ):
        right = f"({_render_compact(right_node, name_latex_overrides=name_latex_overrides)})"
    return _Rendered(f"{left}{operator}{right}", _PREC_ADD)


def _render_power(node: ast.BinOp, name_latex_overrides: Mapping[str, str]) -> _Rendered:
    base_rendered = _render_node(node.left, name_latex_overrides)
    base = base_rendered.text
    if base_rendered.precedence < _PREC_POW or isinstance(node.left, ast.BinOp | ast.UnaryOp):
        base = f"({_render_compact(node.left, name_latex_overrides=name_latex_overrides)})"

    exponent_rendered = _render_node(node.right, name_latex_overrides)
    if isinstance(node.right, ast.BinOp) and isinstance(node.right.op, ast.Add | ast.Sub):
        exponent_body = f"({_render_compact(node.right, name_latex_overrides=name_latex_overrides)})"
    else:
        exponent_body = exponent_rendered.text
    exponent = f"{{{exponent_body}}}"
    return _Rendered(f"{base}^{exponent}", _PREC_POW)


def _render_unary(node: ast.UnaryOp, name_latex_overrides: Mapping[str, str]) -> _Rendered:
    operand = _render_node(node.operand, name_latex_overrides)
    if isinstance(node.op, ast.UAdd):
        return _Rendered(
            f"+{_wrap_unary_operand(node.operand, operand, name_latex_overrides=name_latex_overrides)}",
            _PREC_UNARY,
        )
    if isinstance(node.op, ast.USub):
        return _Rendered(
            f"-{_wrap_unary_operand(node.operand, operand, name_latex_overrides=name_latex_overrides)}",
            _PREC_UNARY,
        )
    raise UnsupportedFormulaSyntaxError(f"Unsupported formula unary operator: {node.op.__class__.__name__}.")


def _render_call(node: ast.Call, name_latex_overrides: Mapping[str, str]) -> _Rendered:
    if not isinstance(node.func, ast.Name):
        raise UnsupportedFormulaSyntaxError("Unsupported formula function call.")
    if node.keywords:
        raise UnsupportedFormulaSyntaxError("Formula function keyword arguments are not supported.")

    name = node.func.id
    lower = _MATHEMATICA_FUNCTION_ALIASES.get(name.lower(), name.lower())
    args = [_render_node(arg, name_latex_overrides).text for arg in node.args]

    if lower == "sqrt":
        _require_arg_count(name, args, 1)
        return _Rendered(rf"\sqrt{{{args[0]}}}", _PREC_ATOM)
    if lower == "abs":
        _require_arg_count(name, args, 1)
        return _Rendered(rf"\left|{args[0]}\right|", _PREC_ATOM)
    if lower == "power":
        _require_arg_count(name, args, 2)
        synthetic = ast.BinOp(left=node.args[0], op=ast.Pow(), right=node.args[1])
        return _render_power(synthetic, name_latex_overrides)

    rendered_args = ", ".join(args)
    command = _FUNCTION_COMMANDS.get(lower)
    if command is not None:
        return _Rendered(rf"{command}\left({rendered_args}\right)", _PREC_ATOM)
    return _Rendered(rf"{_format_identifier(name)}({rendered_args})", _PREC_ATOM)


def _render_constant(node: ast.Constant) -> _Rendered:
    value = node.value
    if isinstance(value, bool) or value is None:
        raise UnsupportedFormulaSyntaxError("Formula constants must be numeric.")
    if isinstance(value, int | float):
        return _Rendered(str(value), _PREC_ATOM, simple=True)
    raise UnsupportedFormulaSyntaxError(f"Unsupported formula literal: {value!r}.")


def _render_child(
    node: ast.AST,
    parent_precedence: int,
    *,
    compact_when_wrapped: bool,
    name_latex_overrides: Mapping[str, str],
) -> str:
    rendered = _render_node(node, name_latex_overrides)
    if rendered.precedence < parent_precedence:
        body = (
            _render_compact(node, name_latex_overrides=name_latex_overrides)
            if compact_when_wrapped
            else rendered.text
        )
        return f"({body})"
    return rendered.text


def _render_compact(node: ast.AST, *, name_latex_overrides: Mapping[str, str] | None = None) -> str:
    rendered = _render_node(node, name_latex_overrides or {})
    text = rendered.text
    text = text.replace(" + ", "+").replace(" - ", "-")
    text = text.replace(" \\cdot ", r"\cdot ")
    return text


def _wrap_unary_operand(
    node: ast.AST,
    rendered: _Rendered,
    *,
    name_latex_overrides: Mapping[str, str],
) -> str:
    if rendered.precedence < _PREC_UNARY or isinstance(node, ast.BinOp):
        return f"({_render_compact(node, name_latex_overrides=name_latex_overrides)})"
    return rendered.text


def _require_arg_count(name: str, args: list[str], expected: int) -> None:
    if len(args) != expected:
        raise UnsupportedFormulaSyntaxError(f"{name} expects {expected} argument(s).")


def _format_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise UnsupportedFormulaSyntaxError(f"Unsupported formula identifier: {identifier!r}.")
    if identifier == "Pi":
        return r"\pi"
    if identifier == "E":
        return "e"
    if "_" in identifier:
        raise UnsupportedFormulaSyntaxError(f"Unsupported formula identifier: {identifier!r}.")

    match = re.fullmatch(r"([A-Za-z]+)([0-9]+)", identifier)
    if match is not None:
        base = _format_identifier(match.group(1))
        return rf"{base}_{{{match.group(2)}}}"

    lower = identifier.lower()
    if lower in _LOWERCASE_GREEK:
        if identifier[:1].isupper() and identifier[1:].islower() and lower in _UPPERCASE_GREEK:
            return "\\" + identifier[:1].upper() + identifier[1:].lower()
        return "\\" + lower
    return identifier
