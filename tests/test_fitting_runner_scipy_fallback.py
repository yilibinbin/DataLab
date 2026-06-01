from __future__ import annotations

import mpmath as mp
import pytest


def test_precision_16_uses_scipy_when_safety_checks_pass() -> None:
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


def test_precision_16_falls_back_when_scipy_safety_fails(monkeypatch: pytest.MonkeyPatch) -> None:
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
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    first = history[0]
    assert isinstance(first, dict)
    assert first["from"] == "scipy_least_squares"


def test_precision_16_dependent_parameters_fall_back_from_scipy() -> None:
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
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    first = history[0]
    assert isinstance(first, dict)
    assert first["from"] == "scipy_least_squares"
    assert "dependent parameter error propagation" in str(first["reason"])
    assert result.param_errors["b"] > 0


def test_precision_16_unweighted_data_sigmas_keep_mpmath_systematic_refits() -> None:
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
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]},
        [mp.mpf("1.0"), mp.mpf("3.1"), mp.mpf("4.9"), mp.mpf("7.05")],
        precision=16,
        data_sigmas=[mp.mpf("0.1")] * 4,
    )

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    first = history[0]
    assert isinstance(first, dict)
    assert first["from"] == "scipy_least_squares"
    assert first["skipped"] == "unweighted_data_sigmas"
    assert "systematic refits" in str(first["reason"])
    assert result.param_errors_sys["b"] > 0
    note = result.details["uncertainty_note"]
    assert isinstance(note, dict)
    assert "systematic errors from" in str(note["en"]).lower()


def test_precision_16_mismatched_variable_lengths_skip_scipy_validation_shortcut() -> None:
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b*z",
        variables=("x", "z"),
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "1"}},
    )

    with pytest.raises(ValueError, match="All independent variables"):
        FitRunner().fit(
            problem,
            {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")], "z": [mp.mpf("1"), mp.mpf("2")]},
            [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
            precision=16,
        )
