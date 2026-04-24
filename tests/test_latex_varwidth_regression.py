from __future__ import annotations

import re
from pathlib import Path

from mpmath import mp

from data_extrapolation_latex_latest import generate_latex_table


_VARWIDTH_RE = re.compile(r"\\documentclass\[varwidth=([0-9.]+)in,border=12pt\]\{standalone\}")


def _extract_varwidth_in(tex: str) -> float:
    for line in tex.splitlines():
        if line.startswith("\\documentclass"):
            m = _VARWIDTH_RE.search(line.strip())
            assert m is not None, f"Unexpected documentclass line: {line!r}"
            return float(m.group(1))
    raise AssertionError("Missing \\documentclass line")


def _extract_tabular_line(tex: str) -> str:
    for line in tex.splitlines():
        if "\\begin{tabular" in line:
            return line
    raise AssertionError("Missing tabular environment")


def test_generate_latex_table_auto_uncertainty_digits_does_not_blow_up_varwidth(tmp_path: Path):
    headers = ["A", "B", "C"]
    data_rows = [(mp.mpf("1"), mp.mpf("2"), mp.mpf("3"))]
    with mp.workdps(80):
        value = mp.mpf("1.2345")
        sigma = mp.mpf("6.3156007090725554303242869280435274832700216705024e-9")
    results = [(value, sigma)]

    out = tmp_path / "extrap_varwidth.tex"
    generate_latex_table(
        headers,
        data_rows,
        results,
        out,
        precision=10,
        use_dcolumn=False,
        latex_group_size=3,
        result_uncertainty_digits=None,
    )
    tex = out.read_text(encoding="utf-8")

    assert _extract_varwidth_in(tex) <= 9.0
    tab_line = _extract_tabular_line(tex)
    assert "S[table-format=1.10]" in tab_line
    assert "(" in tab_line
