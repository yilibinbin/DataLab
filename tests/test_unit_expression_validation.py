from __future__ import annotations

import pytest

from shared.unit_expression_validation import (
    UnitExpressionError,
    parse_unit_dimension,
    validate_expression_units,
)


def test_parse_unit_dimension_canonicalizes_products_and_ratios() -> None:
    assert parse_unit_dimension("m/s").to_text() == "m/s"
    assert parse_unit_dimension("m * s^-1").to_text() == "m/s"
    assert parse_unit_dimension("meter^3/(kilogram*second^2)").to_text() == "meter^3/(kilogram*second^2)"
    assert parse_unit_dimension("m/(s*kg)").to_text() == "m/(kg*s)"


def test_parse_unit_dimension_round_trips_emitted_fractional_and_denominator_text() -> None:
    for unit_text in ("m/(s*kg)", "m^0.5", "m^(-2)"):
        emitted = parse_unit_dimension(unit_text).to_text()
        assert parse_unit_dimension(emitted) == parse_unit_dimension(unit_text)


@pytest.mark.parametrize("unit_text", ["m^1.2.3", "m^+", "m^(1/2.3)"])
def test_parse_unit_dimension_rejects_invalid_exponents_as_unit_errors(unit_text: str) -> None:
    with pytest.raises(UnitExpressionError, match="invalid unit exponent"):
        parse_unit_dimension(unit_text)


def test_validate_expression_units_accepts_identical_addition_and_rejects_scaled_units() -> None:
    assert validate_expression_units("x + y", {"x": "m", "y": "m"}, output_unit="m").to_text() == "m"

    with pytest.raises(UnitExpressionError, match="identical units"):
        validate_expression_units("x + y", {"x": "m", "y": "cm"})


def test_validate_expression_units_infers_multiplication_division_and_output_match() -> None:
    result = validate_expression_units("distance / time", {"distance": "m", "time": "s"}, output_unit="m/s")

    assert result.to_text() == "m/s"


def test_validate_expression_units_rejects_mismatched_output_unit() -> None:
    with pytest.raises(UnitExpressionError, match="does not match"):
        validate_expression_units("distance / time", {"distance": "m", "time": "s"}, output_unit="m")


def test_validate_expression_units_handles_abs_sqrt_and_power_literals() -> None:
    assert validate_expression_units("Abs[x]", {"x": "m"}, output_unit="m").to_text() == "m"
    assert validate_expression_units("Sqrt[area]", {"area": "m^2"}, output_unit="m").to_text() == "m"
    assert validate_expression_units("Power[x, 2]", {"x": "m"}, output_unit="m^2").to_text() == "m^2"
    assert validate_expression_units("Power[x, +2]", {"x": "m"}, output_unit="m^2").to_text() == "m^2"
    assert validate_expression_units("x^+2", {"x": "m"}, output_unit="m^2").to_text() == "m^2"
    assert validate_expression_units("x^-1", {"x": "s"}, output_unit="1/s").to_text() == "1/s"


@pytest.mark.parametrize("expression", ["x^n", "x^(1/2)", "Power[x, n]"])
def test_validate_expression_units_rejects_non_literal_power_exponents(expression: str) -> None:
    with pytest.raises(UnitExpressionError, match="literal numeric"):
        validate_expression_units(expression, {"x": "m", "n": "1"})


@pytest.mark.parametrize("expression", ["x^1e1000", "Power[x, 1e1000]"])
def test_validate_expression_units_rejects_nonfinite_literal_power_exponents(expression: str) -> None:
    with pytest.raises(UnitExpressionError, match="finite literal numeric"):
        validate_expression_units(expression, {"x": "m"})


def test_validate_expression_units_requires_unitless_exp_log() -> None:
    validate_expression_units("Exp[z] + Log[z]", {"z": "1"}, output_unit="1")

    with pytest.raises(UnitExpressionError, match="unitless"):
        validate_expression_units("Exp[x]", {"x": "m"})


def test_validate_expression_units_direct_trig_accepts_rad_or_unitless_only() -> None:
    assert validate_expression_units("Sin[theta]", {"theta": "rad"}, output_unit="1").to_text() == "1"
    assert validate_expression_units("Cos[z]", {"z": "1"}, output_unit="1").to_text() == "1"

    with pytest.raises(UnitExpressionError, match="unitless or rad"):
        validate_expression_units("Sin[theta]", {"theta": "degree"})


def test_validate_expression_units_inverse_trig_returns_rad_and_rejects_composite_dimensionless() -> None:
    assert validate_expression_units("Asin[z]", {"z": "1"}, output_unit="rad").to_text() == "rad"

    with pytest.raises(UnitExpressionError, match="unitless"):
        validate_expression_units("Asin[ratio]", {"ratio": "cm/m"})


def test_validate_expression_units_rejects_registry_unsupported_atan2() -> None:
    with pytest.raises(UnitExpressionError, match="unavailable"):
        validate_expression_units("Atan2[y, x]", {"x": "m", "y": "m"})


def test_validate_expression_units_fail_closed_for_unknown_or_unavailable_functions() -> None:
    with pytest.raises(UnitExpressionError, match="unavailable"):
        validate_expression_units("Gamma[x]", {"x": "1"})

    with pytest.raises(UnitExpressionError, match="unknown expression symbol"):
        validate_expression_units("x + y", {"x": "m"})
