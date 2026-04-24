#!/usr/bin/env python3
"""
Regression tests: fitting custom model expression must reuse the same
parser/registry as:
- extrapolation custom formula
- error propagation formula
"""

from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import (
    ExtrapolationOptions,
    _precision_guard,
    apply_formula_to_data,
    parse_uncertainty_format,
    process_data_string,
)
from fitting import build_model_specification


def _extract_extrapolated_value(entry) -> mp.mpf:
    if hasattr(entry, "value"):
        return mp.mpf(entry.value)
    if isinstance(entry, (tuple, list)) and entry:
        return mp.mpf(entry[0])
    return mp.mpf(entry)


def test_fit_custom_model_expression_same_as_extrapolation_and_error_propagation():
    expr = "P*Gamma[1/2] + Erf[x1] + Zeta[2] + BesselJ[0, x1]"
    data_text = "X B P\n0.25 1.0 2.0\n"

    with _precision_guard(80):
        opts = ExtrapolationOptions(method="custom", custom_formula=expr, mp_precision=80)
        headers, rows, extrapolated = process_data_string(data_text, verbose=False, options=opts)
        assert headers == ["X", "B", "P"]
        assert rows
        assert extrapolated
        value_extrap = _extract_extrapolated_value(extrapolated[0])

        parsed_data = [
            [
                parse_uncertainty_format("0.25", lang="zh"),
                parse_uncertainty_format("1.0", lang="zh"),
                parse_uncertainty_format("2.0", lang="zh"),
            ]
        ]
        error_results = apply_formula_to_data(headers, parsed_data, {}, expr, verbose=False)
        assert error_results
        value_error = mp.mpf(error_results[0].value)

        model = build_model_specification(expr, ["x1"], ["P"])
        value_fit = model.evaluate({"x1": mp.mpf("0.25")}, {"P": mp.mpf("2.0")})

        assert mp.almosteq(value_extrap, value_error, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(value_extrap, value_fit, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))


@pytest.mark.parametrize(
    ("expr", "must_contain"),
    [
        ("__import__('os')", "不支持的函数调用"),
        ("a.__class__", "不支持的属性访问"),
        ("os.system('echo hi')", "不支持的函数调用"),
    ],
)
def test_fit_custom_model_rejects_unsafe_expressions(expr: str, must_contain: str):
    model = build_model_specification(expr, ["x1"], ["P"])
    with pytest.raises(ValueError) as excinfo:
        model.evaluate({"x1": mp.mpf("0.1")}, {"P": mp.mpf("1.0")})
    assert must_contain in str(excinfo.value)

