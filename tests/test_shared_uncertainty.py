from __future__ import annotations

from mpmath import mp
import pytest

from shared.uncertainty import parse_numeric_value, parse_uncertainty_format


def test_parenthesized_uncertainty_scales_with_scientific_suffix() -> None:
    parsed = parse_uncertainty_format("1.23(4)e-2")

    assert parsed.value == mp.mpf("1.23e-2")
    assert parsed.uncertainty == mp.mpf("4e-4")


def test_parenthesized_uncertainty_scales_with_bracket_exponent() -> None:
    parsed = parse_uncertainty_format("1.23(4)[-2]")

    assert parsed.value == mp.mpf("1.23e-2")
    assert parsed.uncertainty == mp.mpf("4e-4")


def test_parse_numeric_value_accepts_uncertainty_magnitude_notation() -> None:
    assert parse_numeric_value("3.2898419602500(36)[9]") == mp.mpf("3.2898419602500e9")
    assert parse_numeric_value("3.2898419602500(36)[+9]") == mp.mpf("3.2898419602500e9")
    assert parse_numeric_value("7295.29954171(17)") == mp.mpf("7295.29954171")


def test_parenthesized_uncertainty_rejects_signed_sigma() -> None:
    with pytest.raises(ValueError, match="uncertainty|不确定度"):
        parse_uncertainty_format("1.23(-4)")


def test_parse_numeric_value_uses_explicit_precision() -> None:
    previous = mp.dps
    try:
        mp.dps = 15
        parsed = parse_numeric_value("0.123456789012345678901234567890", precision=80)
    finally:
        mp.dps = previous

    with mp.workdps(80):
        assert parsed == mp.mpf("0.123456789012345678901234567890")
