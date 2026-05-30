from __future__ import annotations

import mpmath as mp

from fitting.implicit_derivatives import build_implicit_derivative_evaluator
from fitting.implicit_model import ImplicitModelDefinition


def test_implicit_derivative_matches_closed_form_for_simple_model() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x + c*u",
        output_expression="u*u + q",
        parameters=("a", "b", "c", "q"),
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    variables = {"x": mp.mpf("2")}
    params = {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.3"), "q": mp.mpf("1.5")}
    u = (params["a"] + params["b"] * variables["x"]) / (1 - params["c"])
    expected = 2 * u / (1 - params["c"])

    value = evaluator.partial("a", variables, params, {}, u)

    assert mp.almosteq(value, expected, rel_eps=mp.mpf("1e-30"))


def test_implicit_derivative_parses_datalab_function_syntax() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="Sin[u] + c",
        parameters=("a", "b", "c"),
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    value = evaluator.partial(
        "c",
        {"x": mp.mpf("2")},
        {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.3")},
        {},
        mp.mpf("0.5"),
    )

    assert value == mp.mpf("1")


def test_implicit_derivative_rejects_lowercase_runtime_aliases() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="sin(u) + c",
        parameters=("a", "b", "c"),
    )

    assert build_implicit_derivative_evaluator(definition) is None


def test_implicit_derivative_accepts_constants_in_output_expression() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="u",
        equation="d0 + d2/(n-u)^2",
        output_expression="R/(n-u)^2",
        parameters=("d0", "d2"),
        constants={"R": "100"},
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    value = evaluator.partial(
        "d0",
        {"n": mp.mpf("10")},
        {"d0": mp.mpf("-0.01"), "d2": mp.mpf("0.2")},
        {"R": mp.mpf("100")},
        mp.mpf("-0.01"),
    )

    assert mp.isfinite(value)


def test_implicit_derivative_rejects_near_singular_residual_slope() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + c*u",
        output_expression="u",
        parameters=("a", "c"),
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    try:
        evaluator.partial(
            "a",
            {"x": mp.mpf("0")},
            {"a": mp.mpf("1"), "c": mp.mpf("0.999999999999")},
            {},
            mp.mpf("1"),
            min_abs_residual_u=mp.mpf("1e-6"),
        )
    except ValueError as exc:
        assert "F_u" in str(exc)
    else:  # pragma: no cover - assertion path
        raise AssertionError("near-singular F_u should disable analytic derivative")


def test_implicit_derivative_lambdify_callables_strip_builtins() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="Exp[u] + c",
        parameters=("a", "b", "c"),
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    assert evaluator.residual_u_function.__globals__.get("__builtins__") == {}
    for fn in evaluator.partial_functions.values():
        assert fn.__globals__.get("__builtins__") == {}
