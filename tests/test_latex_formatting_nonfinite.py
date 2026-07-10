"""Non-finite guards at the format_value_for_latex_file boundary (round-2 R2-1/R2-4).

int(mp.floor(nan)) deep in the fixed-place formatter raises
'cannot convert inf or nan to int', which used to discard an otherwise-successful
fit/table at every caller (web fitting LaTeX params/metrics branches, the desktop
fit LaTeX writer). The public wrapper now degrades gracefully instead:
- a non-finite sigma formats the bare value (as if sigma were None);
- a non-finite value becomes a parse-safe \\multicolumn literal cell.
"""

from __future__ import annotations

from mpmath import mp

from datalab_latex.latex_formatting import format_value_for_latex_file

_KW = dict(latex_input_decimals=6, is_input=True, latex_group_size=3)


def test_nan_value_becomes_parse_safe_literal_cell() -> None:
    for use_dcolumn in (False, True):
        cell = format_value_for_latex_file(mp.mpf("nan"), None, use_dcolumn=use_dcolumn, **_KW)
        assert cell.startswith("\\multicolumn{1}{c}{")
        assert "nan" in cell


def test_inf_value_becomes_parse_safe_literal_cell() -> None:
    cell = format_value_for_latex_file(mp.mpf("+inf"), None, use_dcolumn=False, **_KW)
    assert cell.startswith("\\multicolumn{1}{c}{")


def test_nan_sigma_formats_bare_value() -> None:
    for use_dcolumn in (False, True):
        with_nan_sigma = format_value_for_latex_file(
            mp.mpf("2.5"), mp.mpf("nan"), use_dcolumn=use_dcolumn, **_KW
        )
        with_none_sigma = format_value_for_latex_file(
            mp.mpf("2.5"), None, use_dcolumn=use_dcolumn, **_KW
        )
        assert with_nan_sigma == with_none_sigma
