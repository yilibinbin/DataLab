from __future__ import annotations

from data_extrapolation_latex_latest import format_latex_formula


def test_manual_latex_formatter_does_not_break_power_operator() -> None:
    rendered = format_latex_formula("A*x**(-p)+C")
    assert "\\cdot\\cdot" not in rendered
    assert "\\cdot  \\cdot" not in rendered


def test_manual_latex_formatter_handles_parenthesized_exponents() -> None:
    rendered = format_latex_formula("x**(a+b)")
    assert rendered == "x^{a + b}"


def test_manual_latex_formatter_does_not_replace_pi_inside_identifiers() -> None:
    rendered = format_latex_formula("epsilon + spin + pi + Pi")
    assert "epsilon" in rendered
    assert "spin" in rendered
    assert "s\\pin" not in rendered
    assert rendered.count("\\pi") == 2


def test_manual_latex_formatter_uses_standard_abs_bars() -> None:
    rendered = format_latex_formula("abs(x)")
    assert rendered in {"\\left|x\\right|", "\\left|{x}\\right|"}
    assert "\\abs" not in rendered


def test_latex_formatter_uses_sympy_for_nested_fraction_output() -> None:
    rendered = format_latex_formula("sqrt(x)/(a+b)")
    assert "\\frac{\\sqrt{x}}{a + b}" in rendered
