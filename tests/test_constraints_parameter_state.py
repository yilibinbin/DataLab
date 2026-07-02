from __future__ import annotations

import pytest
from mpmath import mp

from fitting.constraints import build_parameter_state


def test_build_parameter_state_free_fixed_and_expr_compose():
    state = build_parameter_state(
        {
            "a": {"initial": mp.mpf("3.0")},
            "b": {"fixed": mp.mpf("2.0")},
            "c": {"expr": "a + b"},
        },
        ["a", "b", "c"],
    )

    assert state.free_params == ["a"]
    assert state.fixed_values["b"] == mp.mpf("2.0")
    assert state.dependent_defs["c"].dependencies == ("a", "b")

    composed = state.compose((mp.mpf("3.0"),))
    assert composed["a"] == mp.mpf("3.0")
    assert composed["b"] == mp.mpf("2.0")
    assert composed["c"] == mp.mpf("5.0")


def test_build_parameter_state_unknown_parameter_reference_is_bilingual():
    with pytest.raises(ValueError) as excinfo:
        build_parameter_state({"b": {"expr": "a + z"}}, ["a", "b"])

    msg = str(excinfo.value)
    assert " / " in msg
    assert "Unknown parameter" in msg


@pytest.mark.parametrize(
    "malicious_expr",
    [
        "a.__class__.__subclasses__()",   # attribute + no-arg call gadget
        "a.__class__.__base__",            # attribute chain
        "sqrt.__globals__",                # module-namespace info disclosure
        "a[0]",                            # subscript gadget
        "(lambda: a)()",                   # lambda smuggling
        "__import__",                       # dunder name
    ],
)
def test_build_parameter_state_rejects_sandbox_escape_expressions(malicious_expr):
    """Constraint expressions must go through the whitelisted AST validator like
    every other user-formula path — attribute/subscript/lambda/dunder gadgets
    must be REJECTED, not executed at parse time (audit finding F7)."""
    with pytest.raises(ValueError):
        build_parameter_state({"b": {"expr": malicious_expr}}, ["a", "b"])


def test_build_parameter_state_still_accepts_legitimate_expressions():
    """The security hardening must not break normal constraint expressions."""
    state = build_parameter_state(
        {
            "a": {"initial": mp.mpf("2.0")},
            "b": {"expr": "sqrt(a) + 2*a"},
        },
        ["a", "b"],
    )
    composed = state.compose((mp.mpf("4.0"),))
    assert composed["b"] == mp.mpf("10.0")  # sqrt(4)+2*4 = 2+8


def test_build_parameter_state_cycle_raises_bilingual_on_compose():
    state = build_parameter_state(
        {
            "x": {"initial": mp.mpf("1.0")},
            "a": {"expr": "b + x"},
            "b": {"expr": "a + x"},
        },
        ["x", "a", "b"],
    )

    with pytest.raises(ValueError) as excinfo:
        state.compose((mp.mpf("1.0"),))

    assert " / " in str(excinfo.value)
    assert "Cyclic" in str(excinfo.value)
