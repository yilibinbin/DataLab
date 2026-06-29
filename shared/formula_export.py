"""Canonical formula export DTO and lightweight LaTeX context helpers."""

from __future__ import annotations

from dataclasses import dataclass

from shared.formula_latex_export import FormulaLatexExportError, expression_to_latex, normalize_expression


@dataclass(frozen=True)
class FormulaExport:
    """Delimiter-free canonical formula export payload."""

    source_text: str
    normalized_datalab_text: str
    canonical_latex: str
    ok: bool
    diagnostics: tuple[str, ...] = ()


def export_formula(source: str, *, language: str = "datalab") -> FormulaExport:
    """Export supported DataLab/Python/Mathematica formula syntax to canonical LaTeX."""

    source_text = source or ""
    normalized_text = ""
    try:
        normalized_text = normalize_expression(source_text, language=language)
        canonical_latex = expression_to_latex(source_text, language=language)
    except FormulaLatexExportError as exc:
        return FormulaExport(
            source_text=source_text,
            normalized_datalab_text=normalized_text or source_text.strip(),
            canonical_latex="",
            ok=False,
            diagnostics=(str(exc) or exc.__class__.__name__,),
        )
    return FormulaExport(
        source_text=source_text,
        normalized_datalab_text=normalized_text,
        canonical_latex=canonical_latex,
        ok=True,
    )


def inline_math(payload: FormulaExport | str) -> str:
    """Return an inline math fragment without escaping formula commands."""

    return f"${_canonical_latex(payload)}$"


def display_math(payload: FormulaExport | str) -> str:
    """Return a display math fragment without escaping formula commands."""

    return rf"\[{_canonical_latex(payload)}\]"


def preview_mathtext(payload: FormulaExport | str) -> str:
    """Return the current preview mathtext wrapper."""

    return inline_math(payload)


def formula_literal_fallback(source: object) -> str:
    """Return readable literal formula text that is safe to wrap in math mode."""

    text = "" if source is None else str(source)
    mapping = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "^": r"\char`\^{}",
        "{": r"\{",
        "}": r"\}",
        "~": r"\sim{}",
        "\\": r"\backslash{}",
    }
    return "".join(mapping.get(ch, ch) for ch in text)


def inline_formula_or_literal_fallback(source: object, *, language: str = "datalab") -> str:
    """Return supported formulas canonically, otherwise a compile-safe literal inline fragment."""

    text = "" if source is None else str(source).strip()
    formula = export_formula(text, language=language)
    if formula.ok:
        return inline_math(formula)
    return inline_math(formula_literal_fallback(text))


def inline_formula_summary_or_none(source: object | None, *, language: str = "datalab") -> str | None:
    """Return an inline formula summary, or None for empty/legacy placeholder values."""

    text = "" if source is None else str(source).strip()
    if not text or text == "None":
        return None
    return inline_formula_or_literal_fallback(text, language=language)


def caption_formula(payload: FormulaExport | str) -> str:
    """Typed caption embedding boundary; currently renders as inline math."""

    return inline_math(payload)


def tablenote_formula(payload: FormulaExport | str) -> str:
    """Typed table-note embedding boundary; currently renders as inline math."""

    return inline_math(payload)


def table_cell_formula(payload: FormulaExport | str) -> str:
    """Typed table-cell embedding boundary; currently renders as inline math."""

    return inline_math(payload)


def _canonical_latex(payload: FormulaExport | str) -> str:
    if isinstance(payload, FormulaExport):
        if not payload.ok:
            diagnostic = "; ".join(payload.diagnostics) or "Formula export failed."
            raise ValueError(diagnostic)
        return payload.canonical_latex
    return payload
