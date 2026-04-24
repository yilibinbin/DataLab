from __future__ import annotations

import re

from mpmath import mp

from data_extrapolation_latex_latest import format_result_with_uncertainty_latex


_UNC_PARENS_RE = re.compile(r"\((\d+)\)")


def _unc_digits(text: str) -> int:
    m = _UNC_PARENS_RE.search(text)
    assert m is not None, f"Expected uncertainty parentheses in: {text!r}"
    return len(m.group(1))


def test_auto_uncertainty_digits_uses_two_when_leading_digit_is_one():
    with mp.workdps(80):
        text = format_result_with_uncertainty_latex(mp.mpf("1.2345"), mp.mpf("0.19"), None)
    assert _unc_digits(text) == 2


def test_auto_uncertainty_digits_uses_one_when_leading_digit_is_not_one():
    with mp.workdps(80):
        text = format_result_with_uncertainty_latex(mp.mpf("1.2345"), mp.mpf("0.63"), None)
    assert _unc_digits(text) == 1


def test_auto_uncertainty_digits_keeps_extreme_sigma_compact():
    with mp.workdps(80):
        sigma = mp.mpf("6.3156007090725554303242869280435274832700216705024e-9")
        text = format_result_with_uncertainty_latex(mp.mpf("1.2345"), sigma, None)
    assert _unc_digits(text) <= 2
    assert len(text) < 40

