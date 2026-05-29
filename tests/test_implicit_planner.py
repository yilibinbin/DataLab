from __future__ import annotations

from mpmath import mp

from fitting.implicit_model import ImplicitModelDefinition
from fitting.implicit_planner import ImplicitPlanKind, plan_implicit_fit


def test_observed_linear_output_delta_returns_observed_linear() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b*n",
        output_expression="delta",
        parameters=("a", "b"),
    )

    plan = plan_implicit_fit(definition, precision=80)

    assert plan.kind is ImplicitPlanKind.OBSERVED_LINEAR
    assert plan.transform is None


def test_affine_output_two_delta_plus_one_returns_exact_affine_output() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b*n",
        output_expression="2*delta + 1",
        parameters=("a", "b"),
    )

    plan = plan_implicit_fit(definition, precision=80)

    assert plan.kind is ImplicitPlanKind.EXACT_AFFINE_OUTPUT
    assert plan.transform is not None
    with mp.workdps(80):
        assert plan.transform.forward_values({}, [mp.mpf("3.25")]) == [mp.mpf("7.5")]


def test_affine_output_outranks_double_precision_candidate_routing() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b*n",
        output_expression="2*delta + 1",
        parameters=("a", "b"),
    )

    plan = plan_implicit_fit(definition, precision=16)

    assert plan.kind is ImplicitPlanKind.EXACT_AFFINE_OUTPUT


def test_nonlinear_output_uses_general_numeric_boundary_at_precision_80() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b/(n - delta)",
        output_expression="R/(n-delta)^2",
        parameters=("a", "b", "R"),
    )

    plan = plan_implicit_fit(definition, precision=80)

    assert plan.kind is ImplicitPlanKind.GENERAL
    assert plan.transform is None


def test_precision_16_derived_output_stays_general_until_scipy_implicit_is_implemented() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b/(n - delta)",
        output_expression="R/(n-delta)^2",
        parameters=("a", "b", "R"),
    )

    plan = plan_implicit_fit(definition, precision=16)

    assert plan.kind is ImplicitPlanKind.GENERAL


def test_precision_17_derived_output_stays_high_precision_plan_boundary() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="a + b/(n - delta)",
        output_expression="R/(n-delta)^2",
        parameters=("a", "b", "R"),
    )

    plan = plan_implicit_fit(definition, precision=17)

    assert plan.kind is ImplicitPlanKind.GENERAL
