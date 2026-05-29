from __future__ import annotations

import mpmath as mp


def test_precision_16_uses_scipy_when_safety_checks_pass():
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )
    result = FitRunner().fit(
        problem,
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]},
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        precision=16,
    )

    assert result.details["optimizer_backend"] == "scipy_least_squares"
    assert result.details["scipy_safety_passed"] is True


def test_precision_16_falls_back_when_scipy_safety_fails(monkeypatch):
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )

    monkeypatch.setattr("fitting.runner._jacobian_condition_estimate", lambda *_args, **_kwargs: float("inf"))
    result = FitRunner().fit(
        problem,
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]},
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        precision=16,
    )

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["fallback_history"][0]["from"] == "scipy_least_squares"


def test_precision_16_dependent_parameters_fall_back_from_scipy():
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={
            "a": {"initial": "1"},
            "b": {"expr": "a+a"},
        },
    )
    result = FitRunner().fit(
        problem,
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]},
        [mp.mpf("2.1"), mp.mpf("3.0"), mp.mpf("4.2"), mp.mpf("5.0")],
        precision=16,
    )

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    assert result.details["fallback_history"][0]["from"] == "scipy_least_squares"
    assert "dependent parameter error propagation" in result.details["fallback_history"][0]["reason"]
    assert result.param_errors["b"] > 0
