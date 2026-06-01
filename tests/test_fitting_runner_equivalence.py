from __future__ import annotations

import mpmath as mp


def test_runner_matches_existing_custom_fit_for_linear_model():
    from fitting import build_model_specification, build_parameter_state, fit_custom_model
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        target_name="y",
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )
    x = [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]
    y = [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")]

    model = build_model_specification("a*x+b", ["x"], ["a", "b"])
    state = build_parameter_state({"a": {"initial": "1"}, "b": {"initial": "0"}}, ["a", "b"])
    old = fit_custom_model(model, state, {"x": x}, y, precision=50)
    new = FitRunner().fit(problem, {"x": x}, y, precision=50)

    assert mp.almosteq(new.params["a"], old.params["a"])
    assert mp.almosteq(new.params["b"], old.params["b"])
    assert new.details["optimizer_backend"] == "mpmath_high_precision"
