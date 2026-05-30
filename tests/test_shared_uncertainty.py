from __future__ import annotations

from mpmath import mp

from shared.uncertainty import parse_uncertainty_format


def test_parenthesized_uncertainty_scales_with_scientific_suffix() -> None:
    parsed = parse_uncertainty_format("1.23(4)e-2")

    assert parsed.value == mp.mpf("1.23e-2")
    assert parsed.uncertainty == mp.mpf("4e-4")


def test_parenthesized_uncertainty_scales_with_bracket_exponent() -> None:
    parsed = parse_uncertainty_format("1.23(4)[-2]")

    assert parsed.value == mp.mpf("1.23e-2")
    assert parsed.uncertainty == mp.mpf("4e-4")
