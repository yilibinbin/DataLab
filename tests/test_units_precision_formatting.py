from __future__ import annotations

import pytest
from mpmath import mp

from shared.precision import precision_guard
from shared.units import format_quantity_latex, to_siunitx, unit_backend_metadata


def test_format_quantity_latex_preserves_long_decimal_text_without_float() -> None:
    magnitude = "1.234567890123456789012345678901234567890123456789"

    result = format_quantity_latex(magnitude, "m/s", use_siunitx=False)

    assert magnitude in result
    assert r"\num{" in result
    assert r"\text{m/s}" in result


def test_format_quantity_latex_preserves_mpf_created_at_high_precision() -> None:
    magnitude_text = "1.23456789012345678901234567890123456789"
    with precision_guard(90):
        magnitude = mp.mpf(magnitude_text)

    assert mp.dps < 90

    result = format_quantity_latex(magnitude, "m")

    assert magnitude_text in result


def test_format_quantity_latex_preserves_large_high_precision_mpf_default() -> None:
    magnitude_text = "9" * 50
    with precision_guard(80):
        magnitude = mp.mpf(magnitude_text)

    result = format_quantity_latex(magnitude, "")

    assert magnitude_text in result
    assert "1.0e+50" not in result


@pytest.mark.parametrize(
    "magnitude_text",
    [
        "1" + ("0" * 49),
        str(2**150),
    ],
)
def test_format_quantity_latex_preserves_large_integer_mpf_default(magnitude_text: str) -> None:
    with precision_guard(100):
        magnitude = mp.mpf(magnitude_text)

    result = format_quantity_latex(magnitude, "")

    assert magnitude_text in result
    assert "e+" not in result


def test_format_quantity_latex_keeps_standard_precision_mpf_compact() -> None:
    magnitude = mp.mpf("0.1")

    result = format_quantity_latex(magnitude, "")

    assert result == r"\num{0.1}"


def test_format_quantity_latex_allows_explicit_mpf_display_precision() -> None:
    magnitude_text = "1." + ("1234567891" * 8)
    with precision_guard(140):
        magnitude = mp.mpf(magnitude_text)

    result = format_quantity_latex(magnitude, "m", precision_digits=82)

    assert magnitude_text in result


def test_format_quantity_latex_zero_precision_digits_clamps_to_one_digit() -> None:
    with precision_guard(90):
        magnitude = mp.mpf("1.234567890123456789")

    result = format_quantity_latex(magnitude, "", precision_digits=0)

    assert result == r"\num{1.0}"


def test_to_siunitx_keeps_legacy_api_high_precision_safe() -> None:
    magnitude = "0.00000000000000000000000000000000000000000000012345"

    result = to_siunitx(magnitude, "")

    assert result == rf"\num{{{magnitude}}}"


@pytest.mark.parametrize("magnitude", ["nan", "inf", "-inf", "", None, True])
def test_format_quantity_latex_rejects_non_finite_or_empty_magnitude(magnitude: object) -> None:
    with pytest.raises(ValueError):
        format_quantity_latex(magnitude, "m")


def test_format_quantity_latex_escapes_fallback_unit_text() -> None:
    result = format_quantity_latex("1.0", "m_%#{x}&", use_siunitx=False)

    assert result == r"\num{1.0}\,\text{m\_\%\#\{x\}\&}"


def test_unit_backend_metadata_is_deterministic() -> None:
    metadata = unit_backend_metadata()

    assert set(metadata) == {"backend", "available", "version"}
    assert isinstance(metadata["available"], bool)
    if metadata["available"]:
        assert metadata["backend"] == "pint"
        assert isinstance(metadata["version"], str)
    else:
        assert metadata == {"backend": "none", "available": False, "version": ""}
