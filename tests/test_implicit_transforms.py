from __future__ import annotations

import mpmath as mp

from fitting.implicit_model import ImplicitModelDefinition
from fitting.implicit_transforms import detect_output_transform


def test_affine_output_transform_maps_target_sigma_and_weights_exactly() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="2*u + 1",
        parameters=("a", "b"),
    )

    transform = detect_output_transform(definition)

    assert transform is not None
    assert transform.transformed_targets({"x": [mp.mpf("3")]}, [mp.mpf("9")]) == [mp.mpf("4")]
    assert transform.transformed_sigmas({"x": [mp.mpf("3")]}, [mp.mpf("0.4")]) == [mp.mpf("0.2")]
    assert transform.transformed_weights({"x": [mp.mpf("3")]}, [mp.mpf("25")]) == [mp.mpf("100")]


def test_affine_output_transform_preserves_unweighted_fit_state() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="2*u + 1",
        parameters=("a", "b"),
    )

    transform = detect_output_transform(definition)

    assert transform is not None
    assert transform.transformed_weights({"x": [mp.mpf("3")]}, None) is None


def test_affine_output_transform_detects_generic_constant_affine_expression() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="C*u + B",
        parameters=("a", "b"),
        constants={"C": "3", "B": "-2"},
    )

    transform = detect_output_transform(definition)

    assert transform is not None
    assert transform.transformed_targets({"x": [mp.mpf("0")]}, [mp.mpf("7")]) == [mp.mpf("3")]
    assert transform.forward_values({"x": [mp.mpf("0")]}, [mp.mpf("3")]) == [mp.mpf("7")]


def test_affine_output_transform_honors_requested_precision_for_constants() -> None:
    long_value = "1.123456789123456789123456789123456789123456789"
    long_intercept = "-0.987654321987654321987654321987654321987654321"
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="C*u + B",
        parameters=("a", "b"),
        constants={"C": long_value, "B": long_intercept},
    )

    transform = detect_output_transform(definition, precision=80)

    assert transform is not None
    with mp.workdps(80):
        u_value = mp.mpf("2.3456789123456789123456789")
        target = mp.mpf(long_value) * u_value + mp.mpf(long_intercept)
        assert transform.forward_values({"x": [mp.mpf("0")]}, [u_value]) == [target]
        assert mp.almosteq(
            transform.transformed_targets({"x": [mp.mpf("0")]}, [target])[0],
            u_value,
            rel_eps=mp.mpf("1e-70"),
            abs_eps=mp.mpf("1e-70"),
        )


def test_affine_output_transform_rejects_x_dependent_slope_for_v1() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="C*x*u + B",
        parameters=("a", "b"),
        constants={"C": "3", "B": "5"},
    )

    assert detect_output_transform(definition) is None


def test_nonlinear_inverse_square_output_is_not_affine_transformed() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2",
        output_expression="R/(n-delta)^2",
        parameters=("d0", "d2"),
        constants={"R": "100"},
    )

    assert detect_output_transform(definition) is None


def test_affine_output_transform_rejects_free_parameter_slope() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="a*u + 1",
        parameters=("a", "b"),
    )

    assert detect_output_transform(definition) is None


def test_affine_output_transform_rejects_runtime_formula_alias_mismatches() -> None:
    def _definition(output_expression: str) -> ImplicitModelDefinition:
        return ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression=output_expression,
            parameters=("a", "b"),
        )

    assert detect_output_transform(_definition("e*u + 1")) is None
    assert detect_output_transform(_definition("pi*u + 1")) is None
    assert detect_output_transform(_definition("sin(1)*u + 1")) is None


def test_seed_hint_detector_rejects_runtime_formula_alias_mismatches() -> None:
    from fitting.implicit_seed_hints import detect_seed_hint

    lowercase_constant = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="r/(n-delta)^2",
        parameters=("d0",),
    )
    lowercase_function = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="sin[R]/(n-delta)^2",
        parameters=("d0",),
        constants={"R": "1"},
    )

    assert detect_seed_hint(lowercase_constant) is None
    assert detect_seed_hint(lowercase_function) is None


def test_affine_output_transform_rejects_nonfinite_complex_or_near_zero_scale() -> None:
    def _definition(output_expression: str, constants: dict[str, str] | None = None) -> ImplicitModelDefinition:
        return ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression=output_expression,
            parameters=("a", "b"),
            constants=constants or {},
        )

    assert detect_output_transform(_definition("0*u + 1")) is None
    assert detect_output_transform(_definition("C*u + 1", {"C": "nan"})) is None
    assert detect_output_transform(_definition("C*u + 1", {"C": "inf"})) is None
    assert detect_output_transform(_definition("Sqrt[-1]*u + 1")) is None
