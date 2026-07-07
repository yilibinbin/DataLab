"""Regression tests for the dual-model adversarial-review findings on engine-adaptive
digit grouping (F2, F3). F1/F4/F5 are covered in their natural homes
(test_fitting_latex_writer.py, test_latex_engine_capability.py).

The shared theme: when the compile engine's siunitx CANNOT vary the digit-group width
(native_group_width=False → bundled Tectonic), the writer must (a) NOT emit digit-group-size
(which that engine rejects → hard compile failure) and (b) pre-group cells app-side. When it
CAN (native_group_width=True → newer local siunitx), it emits digit-group-size and keeps S
columns.
"""

from __future__ import annotations

import statistics_utils as su
from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block


# --- F3: statistics sub-writers thread native_group_width -------------------


def test_statistics_preamble_omits_digit_group_size_when_engine_incapable():
    text = "\n".join(
        su._statistics_latex_preamble(use_dcolumn=False, group_size=6, native_group_width=False)
    )
    # Bundled-Tectonic path: the key must be absent so the doc compiles.
    assert "digit-group-size" not in text


def test_statistics_preamble_emits_digit_group_size_when_engine_capable():
    text = "\n".join(
        su._statistics_latex_preamble(use_dcolumn=False, group_size=6, native_group_width=True)
    )
    assert "digit-group-size = 6" in text


# --- F2: fitting comparison honours native_group_width ---------------------

_ROW = {
    "order": "1",
    "model_label": "Linear",
    "status": "ok",
    "free_parameters": "2",
    "chi2": "123456789012",
    "reduced_chi2": "1.2",
    "aic": "3",
    "bic": "4",
    "rmse": "5",
    "r2": "0.99",
    "warnings": "",
    "error": "",
}


def test_comparison_block_app_side_groups_metric_when_engine_incapable():
    lines = build_fitting_comparison_latex_block(
        [_ROW], use_dcolumn=False, latex_group_size=6, native_group_width=False
    )
    text = "\n".join(lines)
    # The big metric is pre-grouped in a \text{} cell (app-side), with a plain r metric column.
    assert "\\text{123456\\,789012}" in text
    # No S column for the metrics (siunitx would re-group at width 3).
    assert "S[" not in text


def test_comparison_block_keeps_siunitx_when_engine_capable():
    lines = build_fitting_comparison_latex_block(
        [_ROW], use_dcolumn=False, latex_group_size=6, native_group_width=True
    )
    text = "\n".join(lines)
    # Native path: the raw numeric metric stays (siunitx S column groups it at compile time).
    assert "123456789012" in text
    assert "\\text{123456\\,789012}" not in text


def test_comparison_block_group_size_zero_no_app_side_grouping():
    lines = build_fitting_comparison_latex_block(
        [_ROW], use_dcolumn=False, latex_group_size=0, native_group_width=False
    )
    text = "\n".join(lines)
    assert "\\text{" not in text  # group_size 0 → no grouping wrap
