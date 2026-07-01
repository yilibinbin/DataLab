"""siunitx header-wrapping regressions (PR #70 swarm-review findings A1/A2).

Non-numeric header cells that land in a siunitx ``S`` column must be wrapped in
``\\multicolumn{1}{c}{...}`` — otherwise siunitx tries to parse the title (e.g.
``AIC`` or a column name) as a number and aborts the LaTeX compilation. The data
cells already follow this convention; these tests pin the header rows too.
"""

from __future__ import annotations


def _header_line(lines: list[str], needle: str) -> str:
    for line in lines:
        if needle in line and "\\\\" in line:
            return line
    raise AssertionError(f"header line containing {needle!r} not found")


def test_fitting_comparison_siunitx_header_wraps_metric_titles() -> None:
    from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block

    rows = [
        {
            "model": "Linear",
            "status": "success",
            "params": "a,b",
            "chi_square": "1.2",
            "reduced_chi_square": "0.6",
            "aic": "3.4",
            "bic": "4.5",
            "rmse": "0.1",
            "r_squared": "0.99",
            "warnings": "",
            "error": "",
        }
    ]
    lines = build_fitting_comparison_latex_block(rows, use_dcolumn=False)
    header = _header_line(lines, "AIC")

    # Each metric title sits in a siunitx S column, so it must be multicolumn-wrapped.
    for title in ("$\\chi^2$", "Reduced $\\chi^2$", "AIC", "BIC", "RMSE", "$R^2$"):
        assert f"\\multicolumn{{1}}{{c}}{{{title}}}" in header, (title, header)
    # A bare (unwrapped) metric title in an S column is what breaks siunitx.
    assert " & AIC & " not in header, header


def test_statistics_matrix_siunitx_header_wraps_column_names() -> None:
    from datalab_latex.latex_tables_statistics_matrix import _matrix_table_block

    columns = ("A", "B")
    block = {"values": [["1.0", "0.5"], ["0.5", "1.0"]]}
    lines = _matrix_table_block("covariance", columns, block, use_dcolumn=False)
    header = _header_line(lines, "A")

    for column in columns:
        assert f"\\multicolumn{{1}}{{c}}{{{column}}}" in header, (column, header)
    # A bare column name in an S column is what breaks siunitx.
    assert " & A & " not in header and not header.rstrip().endswith("& B \\\\"), header


def test_fitting_comparison_dcolumn_header_still_readable() -> None:
    # With dcolumn (not siunitx) the metric columns are d{..}; those also parse
    # cell content as math, so wrapping the header is correct there too.
    from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block

    rows = [
        {
            "model": "Linear",
            "status": "success",
            "params": "a",
            "chi_square": "1.2",
            "reduced_chi_square": "0.6",
            "aic": "3.4",
            "bic": "4.5",
            "rmse": "0.1",
            "r_squared": "0.99",
            "warnings": "",
            "error": "",
        }
    ]
    lines = build_fitting_comparison_latex_block(rows, use_dcolumn=True)
    header = _header_line(lines, "AIC")
    assert "\\multicolumn{1}{c}{AIC}" in header, header
