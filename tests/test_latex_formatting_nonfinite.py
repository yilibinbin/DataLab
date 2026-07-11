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


def test_app_group_wrap_passes_multicolumn_cells_through(tmp_path) -> None:
    """Codex CX-2: app-side grouping (native_group_width=False, siunitx mode) used to
    blindly wrap every cell in \\text{...}; wrapping a non-finite \\multicolumn
    literal cell produces invalid TeX ('Misplaced \\omit')."""
    from datalab_latex.latex_tables_extrapolation import generate_latex_table

    out = tmp_path / "extrap_nan.tex"
    generate_latex_table(
        headers=["S1", "S2", "S3"],
        data_rows=[(mp.mpf("1"), mp.mpf("2"), mp.mpf("3"))],
        extrapolated_results=[(mp.mpf("nan"), mp.mpf("0"))],
        output_filename=str(out),
        precision=6,
        use_dcolumn=False,
        latex_group_size=3,
        native_group_width=False,  # app_group path
    )
    text = out.read_text(encoding="utf-8")
    assert "\\multicolumn{1}{c}{nan}" in text
    assert "\\text{\\multicolumn" not in text


def test_private_formatter_is_guarded_for_direct_callers() -> None:
    """Gemini G-1: the extrapolation/error-propagation table builders call the
    PRIVATE _format_value_for_latex_file directly, so the guard must live there —
    a public-wrapper-only guard leaves those paths crashing on nan/inf."""
    from datalab_latex.latex_formatting import _format_value_for_latex_file

    for use_dcolumn in (False, True):
        cell = _format_value_for_latex_file(
            value=mp.mpf("nan"),
            sigma=None,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=6,
            is_input=True,
        )
        assert cell.startswith("\\multicolumn{1}{c}{")
        bare = _format_value_for_latex_file(
            value=mp.mpf("2.5"),
            sigma=mp.mpf("inf"),
            use_dcolumn=use_dcolumn,
            latex_input_decimals=6,
            is_input=True,
        )
        assert "inf" not in bare  # non-finite sigma degrades to the bare value
