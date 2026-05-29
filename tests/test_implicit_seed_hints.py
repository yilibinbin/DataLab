from __future__ import annotations

import mpmath as mp

from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
from fitting.implicit_seed_hints import ImplicitSeedHint, detect_seed_hint


def test_inverse_square_seed_hint_returns_valid_branches_and_reconstructs_target() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="CR*M/(M+1)/(n-delta)^2",
        parameters=("d0",),
        constants={"CR": "3.2898419602500e9", "M": "7294.29954171"},
    )

    hint = detect_seed_hint(definition, precision=80)

    assert hint is not None
    with mp.workdps(80):
        coeff = mp.mpf("3.2898419602500e9") * mp.mpf("7294.29954171") / (mp.mpf("7294.29954171") + 1)
        target = mp.mpf("100")
        guesses = hint.candidates({"n": mp.mpf("10")}, target)
        assert len(guesses) == 2
        expected = (
            mp.mpf("10") - mp.sqrt(coeff / target),
            mp.mpf("10") + mp.sqrt(coeff / target),
        )
        for guess, expected_guess in zip(guesses, expected, strict=True):
            assert mp.almosteq(guess, expected_guess, rel_eps=mp.mpf("1e-15"))
        for guess in guesses:
            assert mp.almosteq(coeff / (mp.mpf("10") - guess) ** 2, target, rel_eps=mp.mpf("1e-15"))


def test_inverse_square_seed_hint_supports_constant_offset_output() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="En - R/(n-delta)^2",
        parameters=("d0",),
        constants={"En": "0.5", "R": "100"},
    )

    hint = detect_seed_hint(definition, precision=80)

    assert hint is not None
    with mp.workdps(80):
        guesses = hint.candidates({"n": mp.mpf("10")}, mp.mpf("0.25"))
        assert len(guesses) == 2
        for guess in guesses:
            reconstructed = mp.mpf("0.5") - mp.mpf("100") / (mp.mpf("10") - guess) ** 2
            assert mp.almosteq(reconstructed, mp.mpf("0.25"), rel_eps=mp.mpf("1e-30"))


def test_inverse_square_seed_hint_rejects_ambiguous_or_invalid_targets() -> None:
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="R/(n-delta)^2",
        parameters=("d0",),
        constants={"R": "100"},
    )

    hint = detect_seed_hint(definition, precision=80)

    assert hint is not None
    assert hint.candidates({"n": mp.mpf("10")}, mp.mpf("0")) == ()
    assert hint.candidates({"n": mp.mpf("10")}, mp.mpf("-1")) == ()


def test_seed_hint_rejects_parameter_dependent_or_unknown_output() -> None:
    parameter_dependent = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="d0/(n-delta)^2",
        parameters=("d0",),
    )
    unknown_symbol = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="R/(n-delta)^2",
        parameters=("d0",),
    )

    assert detect_seed_hint(parameter_dependent) is None
    assert detect_seed_hint(unknown_symbol) is None


def test_seed_hint_is_attached_to_high_precision_fit_path() -> None:
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("4"), mp.mpf("5"), mp.mpf("6"), mp.mpf("7")]
    deltas = [mp.mpf("-0.01"), mp.mpf("-0.011"), mp.mpf("-0.012"), mp.mpf("-0.0125")]
    ys = [mp.mpf("100") / (x - u) ** 2 for x, u in zip(xs, deltas, strict=True)]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="R/(n-delta)^2",
        variables=("n",),
        parameter_config={"d0": {"initial": "-0.012"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0",
            output_expression="R/(n-delta)^2",
            parameters=("d0",),
            constants={"R": "100"},
            solve_options=ImplicitSolveOptions(method="fixed_point", initial="0", tolerance="1e-30", max_iterations=20),
        ),
    )

    result = FitRunner().fit(problem, {"n": xs}, ys, precision=80)

    assert result.details.get("implicit_seed_hint") == "validated inverse-square output seed"
    assert result.details["implicit_strategy"] == "analytic_implicit_output_space"
    assert all(mp.isfinite(value) for value in result.fitted_curve)


def test_hint_candidates_do_not_override_configured_root_branch() -> None:
    from fitting.implicit_model import build_implicit_model_specification

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="u**2 - 4",
        output_expression="u",
        parameters=("a",),
        solve_options=ImplicitSolveOptions(method="root", initial="-3", tolerance="1e-30", max_iterations=40),
    )
    hint = ImplicitSeedHint(
        reason="test competing positive branch",
        candidates=lambda variables, target: (mp.mpf("3"),),
    )
    spec = build_implicit_model_specification(
        definition,
        target_data=[mp.mpf("2")],
        seed_hint=hint,
    )
    getattr(spec, "set_implicit_point_index")(0)

    result = spec.evaluate({"x": mp.mpf("0")}, {"a": mp.mpf("0")})

    assert result < 0


def test_seed_hints_are_used_for_numeric_partial_solves() -> None:
    from fitting.implicit_model import build_implicit_model_specification

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="u**2 - 4",
        output_expression="u + a",
        parameters=("a",),
        solve_options=ImplicitSolveOptions(method="root", initial="0", tolerance="1e-30", max_iterations=40),
    )
    hint = ImplicitSeedHint(
        reason="test derivative branch",
        candidates=lambda variables, target: (mp.mpf("-3"),),
    )
    spec = build_implicit_model_specification(
        definition,
        target_data=[mp.mpf("-2")],
        seed_hint=hint,
    )
    getattr(spec, "set_implicit_point_index")(0)

    assert spec.evaluate({"x": mp.mpf("0")}, {"a": mp.mpf("0")}) < 0
    partial = spec.partial("a", {"x": mp.mpf("0")}, {"a": mp.mpf("0")})

    assert mp.almosteq(partial, mp.mpf("1"), rel_eps=mp.mpf("1e-10"))
