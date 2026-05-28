"""Rendered formula preview helpers for desktop formula editors."""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from typing import Final, cast

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FUNCTION_NAMES: Final = {
    "sin": r"\sin",
    "cos": r"\cos",
    "tan": r"\tan",
    "log": r"\ln",
    "ln": r"\ln",
    "exp": r"\exp",
    "sqrt": r"\sqrt",
    "abs": r"\left|",
}


def render_formula_pixmap(expression: str, lhs: str | None = None) -> QPixmap | None:
    """Render a display-only expression preview to a ``QPixmap``.

    Returns ``None`` for invalid/empty input or when the optional renderer is
    unavailable. This never calls external LaTeX; matplotlib is imported lazily
    and only uses its built-in mathtext renderer.
    """
    text = (expression or "").strip()
    if not text:
        return None
    if lhs is not None and not _is_identifier(lhs):
        return None

    try:
        mathtext = _expression_to_mathtext(text, lhs=lhs)
        return _render_mathtext(mathtext)
    except Exception:
        return None


def update_formula_preview(label: QLabel, expression: str, lhs: str | None = None) -> None:
    """Update ``label`` with a rendered preview or plain-text fallback."""
    pixmap = render_formula_pixmap(expression, lhs=lhs)
    if pixmap is not None and not pixmap.isNull():
        label.setPixmap(pixmap)
        label.setText("")
        return

    label.clear()
    label.setText(expression or "")


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.fullmatch((value or "").strip()))


def _expression_to_mathtext(expression: str, lhs: str | None = None) -> str:
    _validate_balanced(expression)
    converted = _convert_expression(expression.strip())
    if lhs:
        converted = f"{_escape_identifier(lhs.strip())} = {converted}"
    return f"${converted}$"


def _validate_balanced(expression: str) -> None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in expression:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                raise ValueError("unbalanced expression")
    if stack:
        raise ValueError("unbalanced expression")


def _convert_expression(expression: str) -> str:
    text = expression
    text = re.sub(r"\bPi\b", r"\\pi", text, flags=re.IGNORECASE)
    text = _convert_mathematica_functions(text)
    text = _convert_python_functions(text)
    text = _convert_powers(text)
    text = _replace_multiplication(text)
    return text


def _convert_mathematica_functions(text: str) -> str:
    pattern = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*\[([^\[\]]+)\]")

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        body = _convert_expression(match.group(2))
        func = _FUNCTION_NAMES.get(name.lower())
        if func is None:
            return f"{_escape_identifier(name)}\\left({body}\\right)"
        if name.lower() == "sqrt":
            return rf"\sqrt{{{body}}}"
        if name.lower() == "abs":
            return rf"\left|{body}\right|"
        return rf"{func}\left({body}\right)"

    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(repl, text)
    return text


def _convert_python_functions(text: str) -> str:
    for name, command in _FUNCTION_NAMES.items():
        if name == "abs":
            continue
        if name == "sqrt":
            text = re.sub(
                rf"\b{name}\s*\(([^()]+)\)",
                _replace_sqrt_function,
                text,
                flags=re.IGNORECASE,
            )
            continue
        text = re.sub(
            rf"\b{name}\s*\(([^()]+)\)",
            _function_replacer(command),
            text,
            flags=re.IGNORECASE,
        )
    return text


def _replace_sqrt_function(match: re.Match[str]) -> str:
    return rf"\sqrt{{{_convert_expression(match.group(1))}}}"


def _function_replacer(command: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return rf"{command}\left({_convert_expression(match.group(1))}\right)"

    return replace


def _replace_parenthesized_power(match: re.Match[str]) -> str:
    return f"^{{{_convert_expression(match.group(1))}}}"


def _convert_powers(text: str) -> str:
    text = re.sub(r"\*\*\s*\(([^()]+)\)", _replace_parenthesized_power, text)
    text = re.sub(r"\^\s*\(([^()]+)\)", _replace_parenthesized_power, text)
    exponent_token = r"([+-]?(?:[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d*)?|\.\d+))"
    text = re.sub(r"\*\*\s*" + exponent_token, r"^{\1}", text)
    text = re.sub(r"\^\s*" + exponent_token, r"^{\1}", text)
    return text


def _replace_multiplication(text: str) -> str:
    return text.replace("*", r"\cdot ")


def _escape_identifier(identifier: str) -> str:
    if len(identifier) == 1:
        return identifier
    greek = {
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
    if identifier.lower() in greek:
        return "\\" + identifier.lower()
    return identifier


def _render_mathtext(mathtext: str) -> QPixmap | None:
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(0.01, 0.01), dpi=160)
    figure.patch.set_alpha(0.0)
    FigureCanvasAgg(figure)
    figure.text(0.0, 0.5, mathtext, fontsize=15, va="center", ha="left", color="#222222")
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.06)
    pixmap = QPixmap()
    if not _load_png_pixmap(pixmap, buffer.getvalue()):
        return None
    return pixmap


def _load_png_pixmap(pixmap: QPixmap, data: bytes) -> bool:
    try:
        return pixmap.loadFromData(data, b"PNG")
    except ValueError:
        # Some PySide6 builds type the format as bytes but accept only str at runtime.
        return pixmap.loadFromData(data, cast(bytes, "PNG"))
