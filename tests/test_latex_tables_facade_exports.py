from __future__ import annotations

import datalab_latex.latex_tables as latex_tables

import data_extrapolation_latex_latest as shim


def test_latex_tables_facade_exports_are_restricted():
    assert not hasattr(latex_tables, "_normalize_input_lines")
    assert hasattr(latex_tables, "generate_latex_table")
    assert hasattr(latex_tables, "generate_error_propagation_table")
    assert hasattr(latex_tables, "__all__")
    assert all(not name.startswith("_") for name in latex_tables.__all__)


def test_latex_latest_shim_keeps_private_helpers():
    assert hasattr(shim, "_dual_msg")
    assert hasattr(shim, "_precision_guard")
    assert hasattr(shim, "_expand_scientific_brackets_to_fixed")
