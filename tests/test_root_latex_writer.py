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
        language="en",
    )

    assert "Root test" in latex
    assert "1.23456789012" in latex
    assert "1.23457" not in latex
    assert "0.000000123456789" in latex or "1.23456789e-7" in latex


def test_root_latex_localizes_headers_for_chinese() -> None:
    latex = build_root_latex_document(
        rows=[{"name": "x", "value": "2", "backend": "scipy", "mode": "scalar"}],
        digits=6,
        language="zh",
    )

    assert "输入行" in latex
    assert "不确定度" in latex
