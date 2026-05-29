from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from mpmath import mp

from fitting.constraints import build_parameter_state
from fitting.hp_fitter import FitResult, fit_custom_model
from fitting.implicit_model import (
    ImplicitModelDefinition,
    ImplicitSolveOptions,
    build_implicit_model_specification,
    default_implicit_template,
    quantum_defect_template,
)
from fitting.model_parser import ModelSpecification


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


def test_repeated_evaluate_and_partial_reuse_implicit_solve_cache() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.3",
            tolerance="1e-30",
        ),
    )
    spec = build_implicit_model_specification(definition)
    variables = {"x": mp.mpf("0.2")}
    params = {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.4")}

    for _ in range(3):
        spec.evaluate(variables, params)
        spec.partial("a", variables, params)

    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved <= 12


def test_general_implicit_failure_reports_actual_point_index() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="u + 1",
        output_expression="u + x",
        parameters=("a",),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0",
            tolerance="1e-30",
            max_iterations=5,
        ),
    )
    spec = build_implicit_model_specification(definition)
    getattr(spec, "set_implicit_point_index")(3)

    with pytest.raises(ValueError) as exc_info:
        spec.evaluate({"x": mp.mpf("2")}, {"a": mp.mpf("1")})

    message = str(exc_info.value)
    assert "point_index=3" in message
    assert "point_index=unknown" not in message
    assert "variables={'x': '2.0'}" in message
    assert "parameters={'a': '1.0'}" in message
    assert "method=root" in message
    assert "residual=" in message
    assert "iterations=" in message


def test_sequential_general_implicit_evaluations_keep_configured_seed_before_warm_starts() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="0.1*x + a",
        output_expression="u",
        parameters=("a",),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-30",
            max_iterations=5,
        ),
    )
    spec = build_implicit_model_specification(definition)
    params = {"a": mp.mpf("1")}

    for row_index in range(3):
        getattr(spec, "set_implicit_point_index")(row_index)
        spec.evaluate({"x": mp.mpf(row_index)}, params)

    diagnostics = getattr(spec, "implicit_diagnostics")
    assert diagnostics.points_solved == 3
    assert diagnostics.warm_start_uses == 0


def test_row_dependent_initial_expression_preserves_fresh_root_branch() -> None:
    def build_spec() -> ModelSpecification:
        definition = ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="u**2 - x",
            output_expression="u",
            parameters=("a",),
            constants={},
            solve_options=ImplicitSolveOptions(
                method="root",
                initial="x - 10",
                tolerance="1e-30",
                max_iterations=80,
            ),
        )
        return build_implicit_model_specification(definition)

    params = {"a": mp.mpf("0")}
    sequential = build_spec()
    sequential.evaluate({"x": mp.mpf("0")}, params)
    sequential_second = sequential.evaluate({"x": mp.mpf("100")}, params)

    fresh_second = build_spec().evaluate({"x": mp.mpf("100")}, params)

    assert sequential_second > 0
    assert mp.fabs(sequential_second - fresh_second) < mp.mpf("1e-28")
    diagnostics = getattr(sequential, "implicit_diagnostics")
    assert diagnostics.warm_start_uses == 0


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


def _scaled_rydberg_definition() -> ImplicitModelDefinition:
    return ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="En - K/(n-delta)^2",
        parameters=("d0", "En", "K"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-16",
            max_iterations=20,
        ),
    )


def _fit_scaled_rydberg_dataset(
    xs: list[mp.mpf],
    ys: list[mp.mpf],
) -> FitResult:
    definition = _scaled_rydberg_definition()
    spec = build_implicit_model_specification(definition)
    state = build_parameter_state(
        {
            "d0": {"initial": 0.32},
            "En": {"initial": -0.0121425},
            "K": {"initial": -0.007},
        },
        ["d0", "En", "K"],
    )
    return fit_custom_model(spec, state, {"n": xs}, ys, precision=40)


def test_generic_implicit_model_fits_small_scaled_dataset() -> None:
    expected_params = {
        "d0": mp.mpf("0.3220446"),
        "En": mp.mpf("-0.01214252"),
        "K": mp.mpf("-0.00699766"),
    }
    xs = [mp.mpf(i) for i in range(4, 10)]
    ys = [
        expected_params["En"] - expected_params["K"] / (n - expected_params["d0"]) ** 2
        for n in xs
    ]

    result = _fit_scaled_rydberg_dataset(xs, ys)

    assert mp.fabs(result.params["d0"] - expected_params["d0"]) < mp.mpf("1e-7")
    assert mp.fabs(result.params["En"] - expected_params["En"]) < mp.mpf("1e-9")
    assert mp.fabs(result.params["K"] - expected_params["K"]) < mp.mpf("1e-9")
    assert result.rmse < mp.mpf("1e-12")


@pytest.mark.slow
def test_generic_implicit_model_fits_rydberg_like_scaled_dataset_quickly(
    record_property: Callable[[str, object], None],
) -> None:
    xs = [mp.mpf(i) for i in range(4, 39)]
    ys = [
        mp.mpf(v)
        for v in [
            "-0.01162447187",
            "-0.01182402355",
            "-0.01192631926",
            "-0.01198592815",
            "-0.01202377388",
            "-0.01204932984",
            "-0.01206740907",
            "-0.01208067377",
            "-0.0120906960",
            "-0.0120984536",
            "-0.0121045811",
            "-0.0121095054",
            "-0.0121135218",
            "-0.0121168404",
            "-0.0121196138",
            "-0.0121219550",
            "-0.0121239491",
            "-0.0121256614",
            "-0.0121271423",
            "-0.0121284318",
            "-0.0121295613",
            "-0.012130556",
            "-0.012131437",
            "-0.012132220",
            "-0.012132920",
            "-0.012133547",
            "-0.012134113",
            "-0.012134623",
            "-0.012135085",
            "-0.012135505",
            "-0.012135888",
            "-0.01213624",
            "-0.01213656",
            "-0.0121367",
            "-0.01215",
        ]
    ]
    started = time.perf_counter()
    result = _fit_scaled_rydberg_dataset(xs, ys)
    elapsed = time.perf_counter() - started
    record_property("elapsed_seconds", f"{elapsed:.2f}")

    assert mp.fabs(result.params["d0"] - mp.mpf("0.3220446")) < mp.mpf("1e-6")
    assert mp.fabs(result.params["En"] - mp.mpf("-0.01214252")) < mp.mpf("1e-8")
    assert mp.fabs(result.params["K"] - mp.mpf("-0.00699766")) < mp.mpf("1e-8")
    assert result.rmse < mp.mpf("3e-6")


def test_default_implicit_template_is_generic_not_physical_units() -> None:
    template = default_implicit_template()

    assert "R" not in template.parameters
    assert "R" not in template.constants
    assert "c" not in template.constants
    assert template.x_variables == ("x",)
    assert template.implicit_variable == "u"
    assert template.equation == "a + b*Cos[u] + c*x"
    assert template.output_expression == "u"
    assert template.parameters == ("a", "b", "c")


def test_default_implicit_template_builds_model_specification() -> None:
    spec = build_implicit_model_specification(default_implicit_template())

    assert spec.variables == ["x"]
    assert spec.parameters == ["a", "b", "c"]


def test_quantum_defect_template_preserves_legacy_physical_template() -> None:
    with pytest.warns(DeprecationWarning, match="default_implicit_template"):
        template = quantum_defect_template()

    assert template.x_variables == ("n",)
    assert template.implicit_variable == "delta"
    assert template.equation == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
    assert template.output_expression == "En - R*c/(n-delta)^2"
    assert template.parameters == ("d0", "d2", "d4", "En")
    assert template.constants == {"R": "10973731.568160", "c": "299792458"}
    assert template.solve_options.method == "fixed_point"
    assert template.solve_options.initial == "0"
    assert template.solve_options.tolerance == "1e-30"
    assert template.solve_options.max_iterations == 80
