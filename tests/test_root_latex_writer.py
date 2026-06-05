from __future__ import annotations

from app_desktop.root_latex_writer import build_root_latex_document


def test_root_latex_uses_raw_rows_and_latex_digits_independent_from_display_digits() -> None:
    raw_rows = [
        {
            "input_row_index": "0",
            "root_index": "0",
            "name": "x",
            "value": "1.234567890123456789",
            "uncertainty": "0.000000123456789",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    latex = build_root_latex_document(
        rows=raw_rows,
        caption="Root test",
        digits=12,
        uncertainty_digits=3,
        language="en",
    )

    assert "Root test" in latex
    assert "1.234567890(123)" in latex
    assert "1.23457" not in latex
    assert "Uncertainty" not in latex
    assert "(123)" in latex


def test_root_latex_uncertainty_digits_follow_option() -> None:
    raw_rows = [
        {
            "input_row_index": "0",
            "root_index": "0",
            "name": "x",
            "value": "1.23456789",
            "uncertainty": "0.001234567",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    one_digit = build_root_latex_document(rows=raw_rows, digits=12, uncertainty_digits=1, language="en")
    three_digits = build_root_latex_document(rows=raw_rows, digits=12, uncertainty_digits=3, language="en")

    assert one_digit != three_digits
    assert "(1)" in one_digit
    assert "(123)" in three_digits


def test_root_latex_localizes_headers_for_chinese() -> None:
    latex = build_root_latex_document(
        rows=[{"name": "x", "value": "2", "backend": "scipy", "mode": "scalar"}],
        digits=6,
        language="zh",
    )

    assert "输入行" in latex
    assert "不确定度" not in latex


def test_root_latex_uses_numeric_column_spec_controls() -> None:
    rows = [
        {
            "input_row_index": "0",
            "root_index": "0",
            "name": "x",
            "value": "123456789.0",
            "uncertainty": "120000",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    siunitx_latex = build_root_latex_document(rows=rows, include_dcolumn=False, language="en")
    dcolumn_latex = build_root_latex_document(rows=rows, include_dcolumn=True, language="en")

    assert r"\begin{tabular}{lllS" in siunitx_latex
    assert r"\begin{tabular}{llld" in dcolumn_latex


def test_root_latex_dcolumn_preamble_declares_column_type() -> None:
    rows = [{"input_row_index": "0", "root_index": "0", "name": "x", "value": "2", "backend": "mpmath"}]

    latex = build_root_latex_document(rows=rows, include_dcolumn=True, language="en")

    assert r"\usepackage{dcolumn}" in latex
    assert r"\newcolumntype{d}[1]{D{.}{.}{#1}}" in latex


def test_root_latex_dcolumn_respects_group_size_option() -> None:
    rows = [
        {
            "input_row_index": "0",
            "root_index": "0",
            "name": "x",
            "value": "1234567.890123",
            "uncertainty": "0.00000123",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    group_two = build_root_latex_document(rows=rows, include_dcolumn=True, group_size=2, language="en")
    group_three = build_root_latex_document(rows=rows, include_dcolumn=True, group_size=3, language="en")

    assert "1.23\\,45\\,67\\,89" in group_two
    assert "1.234\\,567\\,890" in group_three
    assert group_two != group_three
