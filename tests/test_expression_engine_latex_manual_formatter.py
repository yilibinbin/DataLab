from __future__ import annotations

from data_extrapolation_latex_latest import format_latex_formula


def test_manual_latex_formatter_does_not_break_power_operator() -> None:
    rendered = format_latex_formula("A*x**(-p)+C")
    assert "\\cdot\\cdot" not in rendered
    assert "\\cdot  \\cdot" not in rendered


def test_manual_latex_formatter_handles_parenthesized_exponents() -> None:
    rendered = format_latex_formula("x**(a+b)")
    assert "^{(a+b)}" in rendered
