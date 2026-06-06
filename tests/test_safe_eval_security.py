from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import safe_eval


def test_safe_eval_rejects_attribute_access():
    with pytest.raises(ValueError) as excinfo:
        safe_eval("a.__class__", {"a": mp.mpf("1")})
    text = str(excinfo.value)
    assert ("属性访问" in text) or ("Attribute access" in text)


def test_safe_eval_rejects_keyword_arguments():
    with pytest.raises(ValueError) as excinfo:
        safe_eval("Sin[1, x=2]", {})
    text = str(excinfo.value)
    assert ("关键字" in text) or ("Keyword arguments" in text)


def test_safe_eval_rejects_import():
    with pytest.raises(ValueError) as excinfo:
        safe_eval("__import__('os')", {})
    text = str(excinfo.value)
    assert ("不支持的函数调用" in text) or ("Unsupported function call" in text)


def test_safe_eval_preserves_high_precision_numeric_literals():
    expr = (
        "-0.125002080319379889989055335841397 + "
        "0.125002079389684968484888259436634"
    )

    with mp.workdps(50):
        actual = mp.mpf(safe_eval(expr, {}))
        expected = (
            mp.mpf("-0.125002080319379889989055335841397")
            + mp.mpf("0.125002079389684968484888259436634")
        )

    assert mp.almosteq(actual, expected, rel_eps=mp.mpf("1e-45"), abs_eps=mp.mpf("1e-45"))


def test_safe_eval_limits_ast_depth():
    expr = "+".join(["1"] * 1000)
    with pytest.raises(ValueError) as excinfo:
        safe_eval(expr, {})
    text = str(excinfo.value)
    assert ("过于复杂" in text) or ("too complex" in text)
