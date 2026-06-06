from __future__ import annotations

from mpmath import mp

from data_extrapolation_latex_latest import (
    UncertainValue,
    apply_formula_to_data,
    format_uncertainty_display_latex,
)


def test_format_uncertainty_display_latex_respects_mp_precision_for_almosteq():
    # sigma=1e-50 is treated as ~0 at low dps, but must be treated as non-zero at dps>=80.
    with mp.workdps(15):
        value = mp.mpf("1")
        sigma = mp.mpf("1e-50")

        text_low, is_latex_low = format_uncertainty_display_latex(
            value,
            sigma,
            mp_precision=None,
            latex_digits=16,
            uncertainty_digits=3,
        )
        assert is_latex_low is False
        assert "(" not in text_low

        text_high, is_latex_high = format_uncertainty_display_latex(
            value,
            sigma,
            mp_precision=80,
            latex_digits=16,
            uncertainty_digits=3,
        )
        assert is_latex_high is True
        assert "(" in text_high


def test_error_propagation_preserves_high_precision_literal_cancellation():
    formula = (
        "-0.125002080319379889989055335841397 + \\\n"
        "0.125002079389684968484888259436634 + A"
    )

    with mp.workdps(50):
        result = apply_formula_to_data(
            ["A"],
            [[UncertainValue("0", "0")]],
            {},
            formula,
        )[0]
        expected = (
            mp.mpf("-0.125002080319379889989055335841397")
            + mp.mpf("0.125002079389684968484888259436634")
        )

    assert result.uncertainty == 0
    assert mp.almosteq(result.value, expected, rel_eps=mp.mpf("1e-45"), abs_eps=mp.mpf("1e-45"))
