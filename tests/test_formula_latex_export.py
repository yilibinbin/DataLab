from __future__ import annotations

import subprocess
import sys

import pytest


def test_ast_export_renders_structured_fraction_with_grouped_denominator_and_greek() -> None:
    from shared.formula_latex_export import expression_to_latex

    rendered = expression_to_latex("d0 + d2/(n-delta)^2")

    assert rendered == r"d_{0} + \frac{d_{2}}{(n-\delta)^{2}}"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a*(b+c)", r"a \cdot (b+c)"),
        ("a-(b-c)", r"a - (b-c)"),
        ("a/(b/c)", r"\frac{a}{\frac{b}{c}}"),
        ("(a+b)^c", r"(a+b)^{c}"),
        ("(n-delta)^2", r"(n-\delta)^{2}"),
    ],
)
def test_ast_export_preserves_precedence_and_associativity(source: str, expected: str) -> None:
    from shared.formula_latex_export import expression_to_latex

    assert expression_to_latex(source) == expected


def test_ast_export_converts_mathematica_functions_roots_and_abs() -> None:
    from shared.formula_latex_export import expression_to_latex

    rendered = expression_to_latex("Sin[x] + Sqrt[A] + Abs[y]")

    assert rendered == r"\sin\left(x\right) + \sqrt{A} + \left|y\right|"


def test_ast_export_accepts_trusted_name_latex_overrides_without_flattening_tree() -> None:
    from shared.formula_latex_export import expression_to_latex

    rendered = expression_to_latex(
        "A*x + B/(n-delta)^2",
        name_latex_overrides={
            "A": r"1.23 \times 10^{-5}",
            "B": r"(-2.0)",
        },
    )

    assert rendered == r"1.23 \times 10^{-5} \cdot x + \frac{(-2.0)}{(n-\delta)^{2}}"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x^10", r"x^{10}"),
        ("x^d0", r"x^{d_{0}}"),
    ],
)
def test_ast_export_braces_multi_token_exponents(source: str, expected: str) -> None:
    from shared.formula_latex_export import expression_to_latex

    assert expression_to_latex(source) == expected


def test_ast_export_handles_unary_nested_powers_common_functions_and_constants() -> None:
    from shared.formula_latex_export import expression_to_latex

    assert expression_to_latex("-x + +y") == "-x + +y"
    assert expression_to_latex("a^b^c") == r"a^{b^{c}}"
    assert expression_to_latex("(a^b)^c") == r"(a^{b})^{c}"
    assert (
        expression_to_latex("Exp[-x] + Log[Pi*x] + E")
        == r"\exp\left(-x\right) + \ln\left(\pi \cdot x\right) + e"
    )


def test_formula_latex_export_import_stays_lightweight() -> None:
    script = r"""
import sys

import shared.formula_latex_export

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
