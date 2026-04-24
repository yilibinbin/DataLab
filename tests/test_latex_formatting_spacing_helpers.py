from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import (
    add_latex_spacing_to_number,
    add_spacing_to_number,
    format_uncertainty_notation_for_dcolumn,
)


@pytest.mark.parametrize(
    ("text", "group_size"),
    [
        ("1.234567", 3),
        ("1.234567(89)", 3),
        ("1.234567[3]", 3),
        ("1.234567e-10", 3),
        ("-1.234567e10", 3),
        ("1.234567", 0),
    ],
)
def test_add_latex_spacing_matches_siunitx_spacing(text: str, group_size: int) -> None:
    assert add_latex_spacing_to_number(text, group_size=group_size) == add_spacing_to_number(
        text, for_siunitx=True, group_size=group_size
    )


def test_format_uncertainty_notation_for_dcolumn_preserves_text_exponent_sign() -> None:
    with mp.workdps(50):
        pos = format_uncertainty_notation_for_dcolumn(
            mp.mpf("1.2345e3"),
            mp.mpf("1.2e1"),
            uncertainty_digits=2,
            group_size=3,
        )
        neg = format_uncertainty_notation_for_dcolumn(
            mp.mpf("1.2345e-3"),
            mp.mpf("1.2e-5"),
            uncertainty_digits=2,
            group_size=3,
        )
    assert "[\\text{+3}]" in pos
    assert "[\\text{-3}]" in neg

