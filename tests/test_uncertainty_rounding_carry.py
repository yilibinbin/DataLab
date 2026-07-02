"""Uncertainty rounding carry-over (audit finding F5).

When a magnitude>=1 uncertainty rounds UP to the next power of ten at the
requested significant digits, the carry handling must keep the magnitude
(e.g. 9.6 @ 1 sig fig -> "10", not "1"), not shrink it 10x.
"""

from __future__ import annotations

from mpmath import mp

from datalab_latex.latex_formatting import _uncertainty_decimal_places


def test_carry_to_next_power_of_ten_keeps_magnitude_one_sig_fig():
    # 9.6 to 1 significant digit rounds to 10, not 1.
    decimal_places, unc_str = _uncertainty_decimal_places(mp.mpf("9.6"), 1)
    assert (decimal_places, unc_str) == (0, "10")


def test_carry_to_next_power_of_ten_keeps_magnitude_two_sig_figs():
    # 99.6 to 2 significant digits rounds to 100, not 10.
    decimal_places, unc_str = _uncertainty_decimal_places(mp.mpf("99.6"), 2)
    assert (decimal_places, unc_str) == (0, "100")


def test_non_carry_cases_unchanged():
    # Regression guard: values that do NOT carry stay exactly as before.
    assert _uncertainty_decimal_places(mp.mpf("9.6"), 2) == (1, "96")
    assert _uncertainty_decimal_places(mp.mpf("1.23"), 1) == (0, "1")
    assert _uncertainty_decimal_places(mp.mpf("0.045"), 1) == (2, "4")


def test_carry_with_fractional_uncertainty_keeps_magnitude():
    # 0.96 to 1 sig fig carries to 1.0: unc_int "10" at decimal_places 1
    # (real value = 10 * 10**-1 = 1.0), NOT "1" at dp 1 (= 0.1, 10x too small).
    decimal_places, unc_str = _uncertainty_decimal_places(mp.mpf("0.96"), 1)
    assert unc_str == "10"
    assert decimal_places == 1
    assert int(unc_str) * mp.power(10, -decimal_places) == mp.mpf("1")
