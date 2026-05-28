from __future__ import annotations

import pytest
from mpmath import mp

from fitting.implicit_model import (
    ImplicitModelDefinition,
    ImplicitSolveOptions,
    build_implicit_model_specification,
    quantum_defect_template,
)


def test_fixed_point_model_solves_real_self_dependent_equation() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0.5",
            tolerance="1e-28",
            max_iterations=100,
        ),
    )
    spec = build_implicit_model_specification(definition)

    y = spec.evaluate(
        {"x": mp.mpf("0.25")},
        {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.3")},
    )
    residual = y - (
        mp.mpf("0.1")
        + mp.mpf("0.2") * mp.cos(y)
        + mp.mpf("0.3") * mp.mpf("0.25")
    )

    assert mp.fabs(residual) < mp.mpf("1e-24")
    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved == 1
    assert diagnostics.max_residual < mp.mpf("1e-24")


def test_numeric_partial_matches_analytic_implicit_derivative() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.4",
            tolerance="1e-40",
            max_iterations=80,
        ),
    )
    spec = build_implicit_model_specification(definition)
    variables = {"x": mp.mpf("0.2")}
    params = {"a": mp.mpf("0.1"), "b": mp.mpf("0.25"), "c": mp.mpf("0.4")}
    u = spec.evaluate(variables, params)

    expected_da = 1 / (1 + params["b"] * mp.sin(u))
    assert mp.fabs(spec.partial("a", variables, params) - expected_da) < mp.mpf(
        "1e-8"
    )


def test_root_method_records_solve_attempt_diagnostics() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.4",
            tolerance="1e-40",
            max_iterations=80,
        ),
    )
    spec = build_implicit_model_specification(definition)
    variables = {"x": mp.mpf("0.2")}
    params = {"a": mp.mpf("0.1"), "b": mp.mpf("0.25"), "c": mp.mpf("0.4")}

    spec.evaluate(variables, params)

    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved == 1
    assert diagnostics.root_fallbacks == 0
    assert diagnostics.max_iterations_used > 0


def test_high_precision_cache_key_preserves_values_beyond_80_digits() -> None:
    with mp.workdps(140):
        definition = ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + x*0",
            output_expression="u",
            parameters=("a",),
            constants={},
            solve_options=ImplicitSolveOptions(
                method="fixed_point",
                initial="0",
                tolerance="1e-120",
                max_iterations=20,
            ),
        )
        spec = build_implicit_model_specification(definition)
        variables = {"x": mp.mpf("1")}
        first_param = mp.mpf("1." + ("0" * 80) + "1")
        second_param = mp.mpf("1." + ("0" * 80) + "2")

        first = spec.evaluate(variables, {"a": first_param})
        second = spec.evaluate(variables, {"a": second_param})

        assert first == first_param
        assert second == second_param
        assert first != second
        diagnostics = getattr(spec, "implicit_diagnostics")
        assert diagnostics.points_solved == 2


def test_low_precision_cache_entry_is_not_reused_at_high_precision() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a/3 + x*0",
        output_expression="u",
        parameters=("a",),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-100",
            max_iterations=20,
        ),
    )
    spec = build_implicit_model_specification(definition)

    with mp.workdps(30):
        spec.evaluate({"x": mp.mpf("1")}, {"a": mp.mpf("1")})

    with mp.workdps(120):
        high_precision_value = spec.evaluate({"x": mp.mpf("1")}, {"a": mp.mpf("1")})
        expected = mp.mpf("1") / 3

        assert mp.fabs(high_precision_value - expected) < mp.mpf("1e-100")

    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved == 2


def test_same_dps_different_workprec_contexts_do_not_share_cache() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a/3 + x*0",
        output_expression="u",
        parameters=("a",),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-100",
            max_iterations=20,
        ),
    )
    spec = build_implicit_model_specification(definition)
    variables = {"x": mp.mpf("1")}
    params = {"a": mp.mpf("1")}

    with mp.workprec(334):
        assert int(mp.dps) == 100
        assert int(mp.prec) == 334
        spec.evaluate(variables, params)

    with mp.workprec(337):
        assert int(mp.dps) == 100
        assert int(mp.prec) == 337
        spec.evaluate(variables, params)

    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved == 2


def test_numeric_partial_uses_high_precision_step() -> None:
    with mp.workdps(120):
        definition = ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a*a*a + x*0",
            output_expression="u",
            parameters=("a",),
            constants={},
            solve_options=ImplicitSolveOptions(
                method="fixed_point",
                initial="0",
                tolerance="1e-90",
                max_iterations=20,
            ),
        )
        spec = build_implicit_model_specification(definition)
        variables = {"x": mp.mpf("1")}
        params = {"a": mp.mpf("1.25")}
        expected = 3 * params["a"] * params["a"]

        assert mp.fabs(spec.partial("a", variables, params) - expected) < mp.mpf(
            "1e-60"
        )


def test_initial_expression_cannot_reference_implicit_variable() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u]",
        output_expression="u",
        parameters=("a", "b"),
        constants={},
        solve_options=ImplicitSolveOptions(initial="u + 1"),
    )

    with pytest.raises(ValueError, match="initial"):
        build_implicit_model_specification(definition)


def test_duplicate_names_are_rejected_across_all_name_groups() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + c*x",
        output_expression="u",
        parameters=("a",),
        constants={"a": "1"},
    )

    with pytest.raises(ValueError, match="Duplicate"):
        build_implicit_model_specification(definition)


def test_equation_output_and_initial_are_prevalidated() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + missing*x",
        output_expression="u",
        parameters=("a",),
        constants={},
        solve_options=ImplicitSolveOptions(initial="0.1"),
    )

    with pytest.raises(ValueError, match="equation"):
        build_implicit_model_specification(definition)


def test_quantum_defect_template_uses_constants_not_fit_parameters() -> None:
    template = quantum_defect_template()

    assert "R" not in template.parameters
    assert "c" not in template.parameters
    assert "R" in template.constants
    assert "c" in template.constants
    assert template.implicit_variable == "delta"


def test_quantum_defect_template_builds_model_specification() -> None:
    spec = build_implicit_model_specification(quantum_defect_template())

    assert spec.variables == ["n"]
    assert spec.parameters == ["d0", "d2", "d4", "En"]
