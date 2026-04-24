from __future__ import annotations

import pytest

from data_extrapolation_latex_latest import _expand_scientific_brackets_to_fixed


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("1.23(45)[2]", "123(45)"),
        ("1.23(45)[-2]", "0.0123(45)"),
        (r"\num{1.0[\text{-3}]}", "0.0010"),
        ("12.3(4)", "12.3(4)"),
        ("9.99[+1]", "99.9"),
        ("-1.2[2]", "-120"),
    ],
)
def test_expand_scientific_brackets_to_fixed_edges(input_text: str, expected: str):
    assert _expand_scientific_brackets_to_fixed(input_text) == expected
