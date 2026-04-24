from __future__ import annotations

from pathlib import Path

from mpmath import mp

from data_extrapolation_latex_latest import generate_error_propagation_table, generate_latex_table, parse_uncertainty_format


def _find_tabular_line(text: str) -> str:
    for line in text.splitlines():
        if "\\begin{tabular" in line:
            return line
    raise AssertionError("tabular not found in generated LaTeX")


def test_generate_latex_table_column_specs_for_siunitx_and_dcolumn(tmp_path: Path):
    headers = ["A", "B", "C"]
    data_rows = [
        (mp.mpf("1.1"), mp.mpf("2.22"), mp.mpf("3.333")),
        (mp.mpf("4.4"), mp.mpf("5.55"), mp.mpf("6.666")),
    ]
    results = [(mp.mpf("7.7777"), mp.mpf("0.12")) for _ in data_rows]

    out_si = tmp_path / "unit_si.tex"
    generate_latex_table(
        headers,
        data_rows,
        results,
        out_si,
        precision=20,
        use_dcolumn=False,
        result_uncertainty_digits=2,
    )
    content = out_si.read_text(encoding="utf-8")
    assert "\\usepackage{siunitx}" in content
    tabular = _find_tabular_line(content)
    assert "S[table-format=1.20]" in tabular
    assert "S[table-format=1.2(2)]" in tabular

    out_dc = tmp_path / "unit_dc.tex"
    generate_latex_table(
        headers,
        data_rows,
        results,
        out_dc,
        precision=20,
        use_dcolumn=True,
        result_uncertainty_digits=2,
    )
    content = out_dc.read_text(encoding="utf-8")
    assert "\\usepackage{dcolumn}" in content
    tabular = _find_tabular_line(content)
    assert "d{" in tabular
    assert "S[table-format=" not in tabular


def test_generate_error_propagation_table_contains_formula_and_filtered_columns(tmp_path: Path):
    headers = ["A", "B", "C"]
    parsed_data = [
        [parse_uncertainty_format("1.0(1)"), parse_uncertainty_format("2.0(2)"), parse_uncertainty_format("3.0(3)")],
        [parse_uncertainty_format("1.1(1)"), parse_uncertainty_format("2.1(2)"), parse_uncertainty_format("3.1(3)")],
    ]
    formula = "B*2"
    results = [parse_uncertainty_format("4.0(4)")] * len(parsed_data)

    out = tmp_path / "unit_error.tex"
    generate_error_propagation_table(
        headers,
        parsed_data,
        results,
        constants={},
        formula_str=formula,
        output_filename=out,
        use_dcolumn=False,
        used_columns=["B"],
    )
    content = out.read_text(encoding="utf-8")
    assert "Formula used:" in content
    assert "B \\cdot 2" in content
    assert "\\multicolumn{1}{c}{B}" in content
    assert "\\multicolumn{1}{c}{A}" not in content
    assert "\\multicolumn{1}{c}{C}" not in content
