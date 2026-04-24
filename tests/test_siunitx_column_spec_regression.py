from __future__ import annotations

from data_extrapolation_latex_latest import siunitx_column_spec


def test_siunitx_column_spec_infers_fractional_and_uncertainty_widths():
    assert siunitx_column_spec(["-2.9037243136"]) == "S[table-format=1.10]"
    assert siunitx_column_spec(["-2.90372438(6)"]) == "S[table-format=1.8(1)]"

