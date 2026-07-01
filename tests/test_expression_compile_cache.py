"""P1-1: the expression engine caches the parsed/validated AST and exposes a
compiled evaluator, so a fit loop parses each model exactly once.

These tests pin the behavioural contract (compiled == safe_eval, same errors,
same security boundary) and that the parse is actually cached — not the raw
speedup, which is machine-dependent.
"""

from __future__ import annotations

import pytest
from mpmath import mp

from shared.expression_engine import (
    _parse_validated_expression,
    compile_expression,
    safe_eval,
)


def test_compiled_evaluator_matches_safe_eval():
    mp.dps = 40
    expr = "a*Sin(x) + b*x^2 + Exp(-x)"
    scope = {"x": mp.mpf("1.25"), "a": mp.mpf("2"), "b": mp.mpf("0.5")}

    direct = safe_eval(expr, scope)
    compiled = compile_expression(expr)(scope)

    assert mp.fabs(direct - compiled) < mp.mpf("1e-35")


def test_parse_is_cached_across_repeated_evaluations():
    _parse_validated_expression.cache_clear()
    expr = "a*x + b"
    fn = compile_expression(expr)
    for i in range(50):
        fn({"x": mp.mpf(i), "a": mp.mpf("1"), "b": mp.mpf("2")})
    # compile_expression parsed once; the 50 evaluations reuse the AST.
    info = _parse_validated_expression.cache_info()
    assert info.misses == 1, info
    # A second compile of the same text is a cache hit, not a re-parse.
    compile_expression(expr)
    assert _parse_validated_expression.cache_info().hits >= 1


def test_compile_rejects_lowercase_functions_like_safe_eval():
    # The Mathematica-style capitalization guard must still fire (at compile).
    with pytest.raises(ValueError):
        compile_expression("sin(x)")


def test_compiled_evaluator_still_blocks_attribute_access():
    # Security boundary is unchanged: attribute-access gadgets are rejected at
    # evaluation, exactly as safe_eval rejects them.
    fn = compile_expression("a.__class__")
    with pytest.raises(ValueError):
        fn({"a": mp.mpf("1")})


def test_compile_reports_parse_errors():
    with pytest.raises(ValueError):
        compile_expression("a +* b")


def test_fitting_model_callable_compiles_once_not_per_evaluation(monkeypatch):
    # P1-1's payoff is that the fit model callable parses the expression ONCE
    # (via compile_expression) rather than per residual/gradient evaluation.
    # This fails if _build_safe_eval_callable is reverted to call safe_eval per
    # call, which the parse cache would otherwise mask.
    import fitting.model_parser as model_parser

    calls: list[str] = []
    real_compile = model_parser.compile_expression

    def _spy(expression):
        calls.append(expression)
        return real_compile(expression)

    monkeypatch.setattr(model_parser, "compile_expression", _spy)

    caller = model_parser._build_safe_eval_callable("a*x + b", ["x"], ["a", "b"], {})
    assert calls == ["a*x + b"], "expression must be compiled exactly once at build time"

    # Many evaluations, still only the one compile.
    for i in range(20):
        caller((mp.mpf(i),), (mp.mpf("2"), mp.mpf("1")))
    assert calls == ["a*x + b"], "compile_expression must not be called per evaluation"
