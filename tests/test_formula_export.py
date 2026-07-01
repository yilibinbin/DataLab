from __future__ import annotations

import subprocess
import sys

import pytest


def test_formula_export_dto_canonicalizes_datalab_formula() -> None:
    from shared.formula_export import export_formula

    result = export_formula("d0 + d2/(n-delta)^2")

    assert result.ok
    assert result.source_text == "d0 + d2/(n-delta)^2"
    assert result.normalized_datalab_text == "d0 + d2/(n-delta)**2"
    assert result.canonical_latex == r"d_{0} + \frac{d_{2}}{(n-\delta)^{2}}"
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("language", "source", "normalized", "latex"),
    [
        ("datalab", "Sin[x] + Sqrt[A]", "Sin(x) + Sqrt(A)", r"\sin\left(x\right) + \sqrt{A}"),
        ("python", "sqrt(A) + exp(-x)", "sqrt(A) + exp(-x)", r"\sqrt{A} + \exp\left(-x\right)"),
        ("mathematica", "Sin[x] + Sqrt[A]", "Sin(x) + Sqrt(A)", r"\sin\left(x\right) + \sqrt{A}"),
    ],
)
def test_formula_export_uses_same_registry_normalization_across_supported_sources(
    language: str,
    source: str,
    normalized: str,
    latex: str,
) -> None:
    from shared.formula_export import export_formula

    result = export_formula(source, language=language)

    assert result.ok
    assert result.normalized_datalab_text == normalized
    assert result.canonical_latex == latex


def test_formula_export_helpers_wrap_delimiters_without_text_escaping() -> None:
    from shared.formula_export import (
        caption_formula,
        display_math,
        inline_math,
        preview_mathtext,
        table_cell_formula,
        tablenote_formula,
    )

    latex = r"\frac{x_1^{2}}{y_{0} + z}"

    assert inline_math(latex) == rf"${latex}$"
    assert display_math(latex) == rf"\[{latex}\]"
    assert preview_mathtext(latex) == rf"${latex}$"
    assert caption_formula(latex) == rf"${latex}$"
    assert tablenote_formula(latex) == rf"${latex}$"
    assert table_cell_formula(latex) == rf"${latex}$"


def test_formula_export_helpers_accept_dto_payloads() -> None:
    from shared.formula_export import display_math, export_formula, inline_math, preview_mathtext

    result = export_formula("d0 + d2/(n-delta)^2")

    assert inline_math(result) == rf"${result.canonical_latex}$"
    assert display_math(result) == rf"\[{result.canonical_latex}\]"
    assert preview_mathtext(result) == inline_math(result)


def test_formula_literal_fallback_escapes_literal_backslash_for_math_mode() -> None:
    from shared.formula_export import formula_literal_fallback, inline_math

    fallback = formula_literal_fallback("x\\")

    assert fallback == r"x\backslash{}"
    assert inline_math(fallback) == r"$x\backslash{}$"
    assert r"$x\$" not in inline_math(fallback)


def test_formula_literal_fallback_escapes_unknown_control_sequences_for_math_mode() -> None:
    from shared.formula_export import formula_literal_fallback, inline_math

    fallback = formula_literal_fallback(r"\foo + x")

    assert fallback == r"\backslash{}foo + x"
    assert inline_math(fallback) == r"$\backslash{}foo + x$"
    assert r"$\foo" not in inline_math(fallback)


def test_formula_literal_fallback_escapes_math_delimiter_specials() -> None:
    from shared.formula_export import formula_literal_fallback

    assert formula_literal_fallback("a & b % c $ d # e") == r"a \& b \% c \$ d \# e"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x_", r"x\_"),
        ("x^", r"x\char`\^{}"),
        ("x}", r"x\}"),
        ("x_{", r"x\_\{"),
        ("a_b_c", r"a\_b\_c"),
        ("x_1^{2} + y_{0}", r"x\_1\char`\^{}\{2\} + y\_\{0\}"),
        ("~x", r"\sim{}x"),
    ],
)
def test_formula_literal_fallback_escapes_math_mode_metacharacters(source: str, expected: str) -> None:
    from shared.formula_export import formula_literal_fallback, inline_math

    fallback = formula_literal_fallback(source)

    assert fallback == expected
    assert inline_math(fallback) == f"${expected}$"


def test_formula_export_unsupported_syntax_returns_diagnostics() -> None:
    from shared.formula_export import export_formula

    result = export_formula("x if y else z")

    assert not result.ok
    assert result.source_text == "x if y else z"
    assert result.normalized_datalab_text == "x if y else z"
    assert result.canonical_latex == ""
    assert result.diagnostics
    assert "unsupported" in result.diagnostics[0].lower()
    assert "ifexp" in result.diagnostics[0].lower()


@pytest.mark.parametrize("source", ["x_", "a_b_c"])
def test_formula_export_rejects_unsafe_underscore_identifiers_for_literal_fallback(source: str) -> None:
    from shared.formula_export import export_formula, formula_literal_fallback, inline_math

    result = export_formula(source)

    assert not result.ok
    assert result.canonical_latex == ""
    assert "identifier" in result.diagnostics[0].lower()
    assert inline_math(formula_literal_fallback(source))


def test_formula_export_import_stays_lightweight() -> None:
    script = r"""
import sys

import shared.formula_export

forbidden_prefixes = (
    "PySide6",
    "matplotlib",
    "data_extrapolation_latex_latest",
    "datalab_latex",
    "fitting",
    "mpmath",
    "sympy",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"
