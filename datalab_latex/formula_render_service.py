"""Pure formula rendering service shared by desktop, web, and LaTeX output."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import re
from typing import Final

from shared.formula_mathtext_png import render_mathtext_png as _render_mathtext_png


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

# Non-ASCII runs (CJK etc.) that must not sit bare inside a mathtext $...$ span:
# matplotlib's math font has no CJK glyphs and would substitute tofu boxes.
_MATHTEXT_NON_ASCII_RUN_RE: Final = re.compile(r"[^\x00-\x7f]+")
# Existing ``\text{...}`` spans (e.g. from a LaTeX-language source) — their
# contents are already text-mode, so they must be left untouched.
_MATHTEXT_TEXT_SPAN_RE: Final = re.compile(r"\\text\{[^{}]*\}")
# Full-width punctuation and math operators → ASCII so they render in the math
# font (and as real operators) instead of a tofu box inside a \text{} run.
# Braces are escaped (\{ \}) not bare ({ }): bare braces are invisible TeX
# grouping delimiters, so a full-width ｛x｝ must stay a *visible* literal brace.
_FULL_WIDTH_PUNCT_MAP: Final = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "｛": r"\{",
        "｝": r"\}",
        "，": ",",
        "：": ":",
        "；": ";",
        "．": ".",
        "　": " ",
        "＋": "+",
        "－": "-",
        "＊": "*",
        "／": "/",
        "＝": "=",
        "＜": "<",
        "＞": ">",
        "｜": "|",
        "％": r"\%",
    }
)


def _protect_non_ascii_for_mathtext(latex: str) -> str:
    """Make a LaTeX string safe for matplotlib mathtext ($...$) rendering.

    Normalizes full-width punctuation to ASCII, then wraps each remaining
    non-ASCII run (e.g. a Chinese identifier) in ``\\text{...}`` so it renders
    with the regular CJK-capable font rather than the CJK-less math font. Runs
    already inside a ``\\text{...}`` span are left as-is — double-wrapping into
    ``\\text{\\text{...}}`` is unparseable by matplotlib and would crash the
    preview. Real math (``\\cdot``, ``x^{2}``, ``\\chi``) stays in math mode.
    Only the mathtext field needs this; the plain ``latex`` field stays raw
    because real LaTeX handles CJK via the document's CJK package.
    """

    latex = latex.translate(_FULL_WIDTH_PUNCT_MAP)

    def _wrap_outside(segment: str) -> str:
        return _MATHTEXT_NON_ASCII_RUN_RE.sub(lambda m: rf"\text{{{m.group(0)}}}", segment)

    parts: list[str] = []
    cursor = 0
    for span in _MATHTEXT_TEXT_SPAN_RE.finditer(latex):
        parts.append(_wrap_outside(latex[cursor:span.start()]))
        parts.append(span.group(0))  # already a \text{...} span — leave untouched
        cursor = span.end()
    parts.append(_wrap_outside(latex[cursor:]))
    return "".join(parts)


def clear_formula_render_cache() -> None:
    _render_formula_cached.cache_clear()


def format_formula_latex(source: str) -> str:
    """Format a compute formula for LaTeX output without rendering an image."""
    text = source or ""
    try:
        return _format_latex_formula_sympy(text)
    except Exception:
        return _format_latex_formula_manual(text)


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
            mathtext=f"${_protect_non_ascii_for_mathtext(latex)}$",
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
    text = re.sub(r"(?<!\\)\bPi\b", r"\\pi", text, flags=re.IGNORECASE)
    if allow_mathematica:
        text = _convert_mathematica_functions(text, allow_python=allow_python)
    if allow_python:
        text = _convert_python_functions(text, allow_mathematica=allow_mathematica)
    text = _convert_powers(text)
    text = _replace_multiplication(text)
    text = _replace_greek_identifiers(text)
    return text


def _find_matching_delimiter(expr: str, start: int, *, open_char: str, close_char: str) -> int:
    depth = 0
    for idx in range(start, len(expr)):
        if expr[idx] == open_char:
            depth += 1
        elif expr[idx] == close_char:
            depth -= 1
            if depth == 0:
                return idx
    return -1


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
    i = 0
    out: list[str] = []
    while i < len(text):
        char = text[i]
        if not (char.isalpha() or char == "_"):
            out.append(char)
            i += 1
            continue

        start = i
        i += 1
        while i < len(text) and (text[i].isalnum() or text[i] == "_"):
            i += 1
        name = text[start:i]
        lower_name = name.lower()
        j = i
        while j < len(text) and text[j].isspace():
            j += 1

        if lower_name in _FUNCTION_NAMES and j < len(text) and text[j] == "(":
            end = _find_matching_delimiter(text, j, open_char="(", close_char=")")
            if end != -1:
                body = _convert_expression(
                    text[j + 1 : end],
                    allow_mathematica=allow_mathematica,
                    allow_python=True,
                )
                command = _FUNCTION_NAMES[lower_name]
                if lower_name == "sqrt":
                    out.append(rf"{command}{{{body}}}")
                elif lower_name == "abs":
                    out.append(rf"\left|{body}\right|")
                else:
                    out.append(rf"{command}\left({body}\right)")
                i = end + 1
                continue

        out.append(text[start:i])
    return "".join(out)


def _convert_powers(text: str) -> str:
    i = 0
    out: list[str] = []
    while i < len(text):
        if text.startswith("**", i):
            exponent, end = _consume_power_exponent(text, i + 2)
        elif text[i] == "^":
            exponent, end = _consume_power_exponent(text, i + 1)
        else:
            out.append(text[i])
            i += 1
            continue
        if exponent is None:
            out.append("**" if text.startswith("**", i) else "^")
            i += 2 if text.startswith("**", i) else 1
            continue
        out.append(f"^{{{exponent}}}")
        i = end
    return "".join(out)


def _consume_power_exponent(text: str, start: int) -> tuple[str | None, int]:
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return None, start

    sign = ""
    if text[i] in "+-":
        sign = text[i]
        i += 1
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return None, start

    if text[i] == "(":
        end = _find_matching_delimiter(text, i, open_char="(", close_char=")")
        if end == -1:
            return None, start
        body = _convert_expression(text[i + 1 : end])
        return f"{sign}{body}", end + 1

    if text[i] == "\\":
        end = _consume_latex_command_expression(text, i)
        if end == i:
            return None, start
        return f"{sign}{text[i:end]}", end

    token_match = re.match(r"(?:\d+(?:\.\d*)?|\.\d+|[A-Za-z_][A-Za-z0-9_]*)", text[i:])
    if token_match is None:
        return None, start
    end = i + token_match.end()
    if end < len(text) and text[end] == "(":
        call_end = _find_matching_delimiter(text, end, open_char="(", close_char=")")
        if call_end != -1:
            end = call_end + 1
    exponent = _convert_expression(text[i:end])
    return f"{sign}{exponent}", end


def _consume_latex_command_expression(text: str, start: int) -> int:
    match = re.match(r"\\[A-Za-z]+", text[start:])
    if match is None:
        return start
    end = start + match.end()
    if text.startswith(r"\left(", end):
        paren_start = end + len(r"\left")
        paren_end = _find_matching_delimiter(text, paren_start, open_char="(", close_char=")")
        if paren_end != -1:
            end = paren_end + 1
            if text.startswith(r"\right)", end):
                end += len(r"\right)")
            return end
    if end < len(text) and text[end] == "{":
        brace_end = _find_matching_delimiter(text, end, open_char="{", close_char="}")
        if brace_end != -1:
            return brace_end + 1
    return end


def _replace_multiplication(text: str) -> str:
    return text.replace("*", r"\cdot ")


def _replace_greek_identifiers(text: str) -> str:
    return re.sub(
        r"(?<!\\)\b[A-Za-z_][A-Za-z0-9_]*\b",
        lambda match: _escape_identifier(match.group(0)),
        text,
    )


def _escape_identifier(identifier: str) -> str:
    if len(identifier) == 1:
        return identifier
    lowercase_greek = {
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
    uppercase_greek = {"gamma", "delta", "theta", "lambda", "pi", "sigma", "omega"}
    lower = identifier.lower()
    if lower in lowercase_greek:
        if identifier[:1].isupper() and identifier[1:].islower() and lower in uppercase_greek:
            return "\\" + identifier[:1].upper() + identifier[1:].lower()
        return "\\" + lower
    return identifier


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.fullmatch((value or "").strip()))


def _reject_unsafe_formula_ast(formula_str: str) -> None:
    """Reject sandbox-escape gadgets before the formula reaches ``parse_expr``.

    ``parse_expr`` will happily evaluate attribute access (``sqrt(1).__class__``)
    and subscripting, which are the first rungs of a SymPy sandbox escape.  Mirror
    the security-critical checks in ``shared.symbolic_math._validate_symbolic_ast``
    here, but without its capitalized-function whitelist so lowercase names
    (``sin``/``cos``/…) that this formatter accepts keep working.  ``^`` is a valid
    formula operator but not valid Python, so translate it to ``**`` for the AST
    check only — the real parse still applies ``convert_xor`` to the raw string.
    """
    try:
        tree = ast.parse(formula_str.replace("^", "**"), mode="eval")
    except SyntaxError:
        # Let parse_expr surface the syntax error with its own message.
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute | ast.Subscript | ast.Lambda | ast.NamedExpr):
            raise ValueError("Unsupported formula syntax.")
        if isinstance(node, ast.Name) and "__" in node.id:
            raise ValueError("Unsupported formula name.")


def _format_latex_formula_sympy(formula_str: str) -> str:
    """Primary LaTeX formatter for compute formulas.

    Keep this in the shared render service so desktop previews and generated
    LaTeX output do not grow separate formatter ownership again.  Imports stay
    local to avoid making ordinary preview-service import do SymPy setup work.
    """
    _reject_unsafe_formula_ast(formula_str)

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
    latex_str = re.sub(r"(?<!\\)\bpi\b", r"\\pi", latex_str, flags=re.IGNORECASE)
    latex_str = re.sub(r"\be\b", "e", latex_str)
    latex_str = _wrap_calls(latex_str)
    latex_str = re.sub(r"\^(\w+)", r"^{\1}", latex_str)
    latex_str = re.sub(r"\^\(([^)]+)\)", r"^{(\1)}", latex_str)
    latex_str = re.sub(r"\s+", " ", latex_str)
    return latex_str.strip()
