from __future__ import annotations

from pathlib import Path

from mpmath import mp

from data_extrapolation_latex_latest import (
    generate_error_propagation_table,
    generate_latex_table,
    parse_uncertainty_format,
)


def test_generate_latex_table_splits_into_multiple_blocks(tmp_path: Path):
    headers = ["A", "B", "C"]
    data_rows = [
        (mp.mpf("1.0"), mp.mpf("1.1"), mp.mpf("1.2")),
        (mp.mpf("2.0"), mp.mpf("2.1"), mp.mpf("2.2")),
        (mp.mpf("3.0"), mp.mpf("3.1"), mp.mpf("3.2")),
        (mp.mpf("4.0"), mp.mpf("4.1"), mp.mpf("4.2")),
    ]
    results = [(mp.mpf("0.9"), mp.mpf("0.05")) for _ in data_rows]

    out = tmp_path / "extrap_split.tex"
    generate_latex_table(
        headers,
        data_rows,
        results,
        out,
        caption="Split test",
        use_dcolumn=False,
        table_segments=[(0, 2), (2, 4)],
    )
    content = out.read_text(encoding="utf-8")

    assert content.count("\\begin{table}") == 2
    assert "Split test (Part 1)" in content
    assert "Split test (Part 2)" in content


def test_generate_error_table_filters_used_columns_and_splits(tmp_path: Path):
    headers = ["A", "B", "C"]
    parsed_data = [
        [parse_uncertainty_format("1.0(1)"), parse_uncertainty_format("2.0(2)"), parse_uncertainty_format("3.0(3)")],
        [parse_uncertainty_format("1.1(1)"), parse_uncertainty_format("2.1(2)"), parse_uncertainty_format("3.1(3)")],
        [parse_uncertainty_format("1.2(1)"), parse_uncertainty_format("2.2(2)"), parse_uncertainty_format("3.2(3)")],
    ]
    # Keep formula independent of filtered-out columns to make assertions robust.
    formula = "B*2"
    results = [parse_uncertainty_format("4.0(4)")] * len(parsed_data)

    out = tmp_path / "error_filtered.tex"
    generate_error_propagation_table(
        headers,
        parsed_data,
        results,
        constants={},
        formula_str=formula,
        output_filename=out,
        caption="Error split",
        use_dcolumn=False,
        used_columns=["B"],
        table_segments=[(0, 2), (2, 3)],
    )
    content = out.read_text(encoding="utf-8")

    # Filtered header should include B but not A/C.
    assert "\\multicolumn{1}{c}{B}" in content
    assert "\\multicolumn{1}{c}{A}" not in content
    assert "\\multicolumn{1}{c}{C}" not in content

    # Split into two tables.
    assert content.count("\\begin{table}") == 2

