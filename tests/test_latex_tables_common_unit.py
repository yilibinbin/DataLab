from __future__ import annotations

import pytest

from datalab_latex import latex_tables_common as common


def test_normalize_input_lines_strips_leading_blanks_and_trailing_space():
    assert common._normalize_input_lines(["", "  ", "a  ", "b\t"]) == ["a", "b"]
    assert common._normalize_input_lines(["a", "", "b  "]) == ["a", "", "b"]


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("−1.0", "-1.0"),
        ("＋2.0", "+2.0"),
        (" \u2014\uFF0B3 ", "-+3"),
    ],
)
def test_normalize_numeric_token_normalizes_unicode_signs(token: str, expected: str):
    assert common._normalize_numeric_token(token) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, 0),
        ("", 0),
        ("  ", 1),
        (r"\num{1.23}", 4),
        (r"\frac{1}{2}", 2),
        (r"1.2\,3", 4),
    ],
)
def test_string_length_hint_strips_latex_commands(text, expected: int):
    assert common._string_length_hint(text) == expected


def test_estimate_page_geometry_clamps_and_is_monotonic():
    width1, height1 = common._estimate_page_geometry([1, 1], 1)
    assert 8.0 <= width1 <= 18.0
    assert 9.0 <= height1 <= 13.5

    width2, height2 = common._estimate_page_geometry([200, 200], 1)
    assert 8.0 <= width2 <= 18.0
    assert width2 >= width1

    width3, height3 = common._estimate_page_geometry([1, 1], 200)
    assert 9.0 <= height3 <= 13.5
    assert height3 >= height1


def test_cjk_detection_helpers():
    assert common._contains_cjk_characters("中文")
    assert not common._contains_cjk_characters("abc")
    assert not common._contains_cjk_characters(None)
    assert common._needs_cjk_support("abc", "中文")
    assert not common._needs_cjk_support("abc", "")


def test_build_standalone_preamble_variants():
    preamble = common._build_standalone_preamble(8.0, include_dcolumn=False, needs_cjk=False, latex_group_size=0)
    text = "\n".join(preamble)
    assert "\\documentclass[varwidth=8.00in" in text
    assert "group-digits = false," in text
    assert "\\usepackage{dcolumn}" not in text

    preamble_cjk = common._build_standalone_preamble(8.0, include_dcolumn=False, needs_cjk=True, latex_group_size=3)
    text_cjk = "\n".join(preamble_cjk)
    assert "\\usepackage{fontspec}" in text_cjk
    assert "\\usepackage{xeCJK}" in text_cjk

    preamble_dcolumn = common._build_standalone_preamble(8.0, include_dcolumn=True, needs_cjk=False, latex_group_size=3)
    text_dcolumn = "\n".join(preamble_dcolumn)
    assert "\\usepackage{dcolumn}" in text_dcolumn
    assert "\\newcolumntype{d}[1]{D{.}{.}{#1}}" in text_dcolumn


def test_normalize_table_segments_behaviour():
    assert common._normalize_table_segments(0, None) == []
    assert common._normalize_table_segments(10, None) == [(0, 10)]
    assert common._normalize_table_segments(10, [(0, 5), (5, 10)]) == [(0, 5), (5, 10)]

    # invalid: gap
    assert common._normalize_table_segments(10, [(0, 4), (6, 10)]) == [(0, 10)]
    # invalid: empty segment
    assert common._normalize_table_segments(10, [(0, 0)]) == [(0, 10)]
    # invalid: not covering full range
    assert common._normalize_table_segments(10, [(0, 5)]) == [(0, 10)]


@pytest.mark.parametrize(
    ("header", "index", "expected"),
    [
        ("x 1", 0, "x_1"),
        ("1abc", 0, "c_1abc"),
        ("!!!", 0, "col_1"),
    ],
)
def test_normalize_header_to_symbol(header: str, index: int, expected: str):
    assert common._normalize_header_to_symbol(header, index) == expected


def test_apply_aliases_prefers_longer_aliases_and_respects_boundaries():
    assert common._apply_aliases("x1 + x10", {"x1": "A", "x10": "B"}) == "A + B"
    assert common._apply_aliases("x1x", {"x1": "A"}) == "x1x"
