"""Pure formula rendering service shared by desktop, web, and LaTeX output."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import io
import re
from typing import Final


class InputLanguage(str, Enum):
    DATALAB = "datalab"
    PYTHON = "python"
    MATHEMATICA = "mathematica"
    LATEX = "latex"


@dataclass(frozen=True)
class RenderRequest:
    source: str
    language: InputLanguage = InputLanguage.DATALAB
    lhs: str | None = None
    dpi: int = 160
    color: str = "#111827"


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    source: str
    language: InputLanguage
    latex: str
    mathtext: str
    png_bytes: bytes
    fallback_text: str
    error_message: str = ""


@dataclass(frozen=True)
class FormulaPreviewMetadata:
    ok: bool
    source: str
    language: InputLanguage
    latex: str
    mathtext: str
    fallback_text: str
    error_message: str = ""


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
_UNSAFE_LATEX_RE: Final = re.compile(
    r"\\(?:input|include|includeonly|openin|openout|read|write|write18|"
    r"immediate|newcommand|renewcommand|def|edef|gdef|xdef|catcode|"
    r"csname|usepackage|documentclass|special|primitive)\b",
    re.IGNORECASE,
)
_LATEX_ENVIRONMENT_RE: Final = re.compile(
    r"\\(?:begin|end)\s*\{\s*([A-Za-z*]+)\s*\}",
    re.IGNORECASE,
)
_SAFE_LATEX_ENVIRONMENTS: Final = frozenset(
    {
        "aligned",
        "array",
        "bmatrix",
        "Bmatrix",
        "cases",
        "gathered",
        "matrix",
        "pmatrix",
        "smallmatrix",
        "split",
        "vmatrix",
        "Vmatrix",
    }
)
_MAX_SOURCE_LENGTH: Final = 8000


def clear_formula_render_cache() -> None:
    _render_formula_cached.cache_clear()


def format_formula_latex(source: str) -> str:
    """Format a compute formula for LaTeX output without rendering an image."""
    text = source or ""
    try:
        return _format_latex_formula_sympy(text)
    except Exception:
        return _format_latex_formula_manual(text)


def sanitize_formula_latex_source(source: str) -> str:
    """Sanitize display-only LaTeX before any high-fidelity preview path."""
    return _sanitize_latex_source(source or "")


def render_formula(request: RenderRequest) -> RenderResult:
    language = InputLanguage(request.language)
    return _render_formula_cached(
        request.source or "",
        language.value,
        request.lhs,
        int(request.dpi),
        request.color,
    )


def render_formula_metadata(request: RenderRequest) -> FormulaPreviewMetadata:
    """Return sanitized formula preview metadata without rendering PNG bytes."""
    return _build_formula_metadata(
        request.source or "",
        InputLanguage(request.language),
        request.lhs,
    )


@lru_cache(maxsize=256)
def _render_formula_cached(
    source: str,
    language_value: str,
    lhs: str | None,
    dpi: int,
    color: str,
) -> RenderResult:
    language = InputLanguage(language_value)
    metadata = _build_formula_metadata(source, language, lhs)
    if not metadata.ok:
        return RenderResult(
            ok=False,
            source=source,
            language=language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=b"",
            fallback_text=metadata.fallback_text,
            error_message=metadata.error_message,
        )

    try:
        png_bytes = _render_mathtext_png(metadata.mathtext, dpi=dpi, color=color)
        return RenderResult(
            ok=True,
            source=source,
            language=language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=png_bytes,
            fallback_text=metadata.fallback_text,
        )
    except Exception as exc:  # noqa: BLE001 - structured render fallback
        return RenderResult(
            ok=False,
            source=source,
            language=language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=b"",
            fallback_text=metadata.fallback_text,
            error_message=str(exc) or exc.__class__.__name__,
        )


def _build_formula_metadata(
    source: str,
    language: InputLanguage,
    lhs: str | None,
) -> FormulaPreviewMetadata:
    fallback_text = source
    text = source.strip()
    if not text:
        return FormulaPreviewMetadata(
            ok=False,
            source=source,
            language=language,
            latex="",
            mathtext="",
            fallback_text=fallback_text,
            error_message="Formula is empty.",
        )
    if len(text) > _MAX_SOURCE_LENGTH:
        return FormulaPreviewMetadata(
            ok=False,
            source=source,
            language=language,
            latex="",
            mathtext="",
            fallback_text=fallback_text,
            error_message="Formula is too long to preview.",
        )
    if lhs is not None and not _is_identifier(lhs):
        return FormulaPreviewMetadata(
            ok=False,
            source=source,
            language=language,
            latex="",
            mathtext="",
            fallback_text=fallback_text,
            error_message="Invalid left-hand side identifier.",
        )

    try:
        latex = _source_to_latex(text, language)
        if lhs:
            latex = f"{_escape_identifier(lhs.strip())} = {latex}"
        return FormulaPreviewMetadata(
            ok=True,
            source=source,
            language=language,
            latex=latex,
            mathtext=f"${latex}$",
            fallback_text=fallback_text,
        )
    except Exception as exc:  # noqa: BLE001 - structured preview fallback
        return FormulaPreviewMetadata(
            ok=False,
            source=source,
            language=language,
            latex="",
            mathtext="",
            fallback_text=fallback_text,
            error_message=str(exc) or exc.__class__.__name__,
        )


def _source_to_latex(source: str, language: InputLanguage) -> str:
    if language is InputLanguage.LATEX:
        return _sanitize_latex_source(source)
    text = source
    _reject_unsafe_latex_fragments(text)
    _reject_unsafe_latex_environments(text)
    _validate_balanced(text)
    if language is InputLanguage.PYTHON:
        return _convert_expression(text, allow_mathematica=False, allow_python=True)
    if language is InputLanguage.MATHEMATICA:
        return _convert_expression(text, allow_mathematica=True, allow_python=False)
    return _convert_expression(text, allow_mathematica=True, allow_python=True)


def _sanitize_latex_source(source: str) -> str:
    text = source.strip()
    # Mathtext does not execute TeX commands, but the same sanitizer also
    # protects the optional external-TeX preview path. Keep raw formula
    # environments on an allowlist and reject document/file/listing structure.
    _reject_unsafe_latex_fragments(text)
    _reject_unsafe_latex_environments(text)
    if "$" in text:
        text = text.strip("$")
    return text


def _reject_unsafe_latex_fragments(text: str) -> None:
    if _UNSAFE_LATEX_RE.search(text):
        raise ValueError("Unsafe LaTeX command is not allowed in formula preview.")


def _reject_unsafe_latex_environments(text: str) -> None:
    for match in _LATEX_ENVIRONMENT_RE.finditer(text):
        name = match.group(1)
        if name not in _SAFE_LATEX_ENVIRONMENTS:
            raise ValueError("Unsafe LaTeX environment is not allowed in formula preview.")


def _validate_balanced(expression: str) -> None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for index, char in enumerate(expression):
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                raise ValueError(f"Unbalanced expression near position {index}.")
    if stack:
        raise ValueError("Unbalanced expression.")


def _convert_expression(
    expression: str,
    *,
    allow_mathematica: bool = True,
    allow_python: bool = True,
) -> str:
    text = expression
    text = re.sub(r"\bPi\b", r"\\pi", text, flags=re.IGNORECASE)
    if allow_mathematica:
        text = _convert_mathematica_functions(text, allow_python=allow_python)
    if allow_python:
        text = _convert_python_functions(text, allow_mathematica=allow_mathematica)
    text = _convert_powers(text)
    text = _replace_multiplication(text)
    return text


def _convert_mathematica_functions(text: str, *, allow_python: bool = True) -> str:
    pattern = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*\[([^\[\]]+)\]")

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        body = _convert_expression(
            match.group(2),
            allow_mathematica=True,
            allow_python=allow_python,
        )
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


def _convert_python_functions(text: str, *, allow_mathematica: bool = True) -> str:
    for name, command in _FUNCTION_NAMES.items():
        if name == "abs":
            continue
        if name == "sqrt":
            text = re.sub(
                rf"\b{name}\s*\(([^()]+)\)",
                _sqrt_replacer(allow_mathematica=allow_mathematica),
                text,
                flags=re.IGNORECASE,
            )
            continue
        text = re.sub(
            rf"\b{name}\s*\(([^()]+)\)",
            _function_replacer(command, allow_mathematica=allow_mathematica),
            text,
            flags=re.IGNORECASE,
        )
    return text


def _sqrt_replacer(*, allow_mathematica: bool) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return rf"\sqrt{{{_convert_expression(match.group(1), allow_mathematica=allow_mathematica)}}}"

    return replace


def _function_replacer(command: str, *, allow_mathematica: bool) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return rf"{command}\left({_convert_expression(match.group(1), allow_mathematica=allow_mathematica)}\right)"

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


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.fullmatch((value or "").strip()))


def _render_mathtext_png(mathtext: str, *, dpi: int, color: str) -> bytes:
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(0.01, 0.01), dpi=dpi)
    figure.patch.set_alpha(0.0)
    FigureCanvasAgg(figure)
    figure.text(0.0, 0.5, mathtext, fontsize=21, va="center", ha="left", color=color)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.06)
    return buffer.getvalue()


def _format_latex_formula_sympy(formula_str: str) -> str:
    """Primary LaTeX formatter for compute formulas.

    Keep this in the shared render service so desktop previews and generated
    LaTeX output do not grow separate formatter ownership again.  Imports stay
    local to avoid making ordinary preview-service import do SymPy setup work.
    """
    import sympy as sp
    from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

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
        "Abs": sp.Abs,
        "pi": sp.pi,
        "Pi": sp.pi,
        "e": sp.E,
        "E": sp.E,
    }
    global_dict = {
        "Symbol": sp.Symbol,
        "Integer": sp.Integer,
        "Float": sp.Float,
        "Rational": sp.Rational,
        "Add": sp.Add,
        "Mul": sp.Mul,
        "Pow": sp.Pow,
        "Function": sp.Function,
    }
    expr = parse_expr(
        formula_str,
        local_dict=local_funcs,
        global_dict=global_dict,
        transformations=standard_transformations + (convert_xor,),
        evaluate=False,
    )
    return str(sp.latex(expr, mul_symbol="dot"))


def _format_latex_formula_manual(formula_str: str) -> str:
    """Fallback manual LaTeX formatter for simple compute formulas."""

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
        }
        i = 0
        out: list[str] = []
        while i < len(expr):
            matched = False
            if expr.startswith("abs(", i):
                start = i + len("abs(") - 1
                end = _find_matching(expr, start)
                if end == -1:
                    out.append(expr[i:])
                    break
                inner = _wrap_calls(expr[start + 1 : end])
                out.append(f"\\left|{inner}\\right|")
                i = end + 1
                continue
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
                    if name == "sqrt":
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
    latex_str = re.sub(r"\bpi\b", r"\\pi", latex_str, flags=re.IGNORECASE)
    latex_str = re.sub(r"\be\b", "e", latex_str)
    latex_str = _wrap_calls(latex_str)
    latex_str = re.sub(r"\^(\w+)", r"^{\1}", latex_str)
    latex_str = re.sub(r"\^\(([^)]+)\)", r"^{(\1)}", latex_str)
    latex_str = re.sub(r"\s+", " ", latex_str)
    return latex_str.strip()
