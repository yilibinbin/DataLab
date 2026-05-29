from __future__ import annotations

from collections.abc import Callable, Sequence

import mpmath as mp
import pytest

from fitting.model_parser import ModelSpecification
from fitting.problem import ModelProblem

pytest.importorskip("scipy.optimize")


def _quadratic_implicit_problem() -> ModelProblem:
    from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
    from fitting.problem import ModelProblem

    return ModelProblem(
        model_type="self_consistent",
        expression="u*u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.15"}, "b": {"initial": "0.45"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u",
            parameters=("a", "b"),
            solve_options=ImplicitSolveOptions(method="fixed_point", initial="0", tolerance="1e-16", max_iterations=20),
        ),
    )


def test_precision_16_general_implicit_accepts_scipy_candidate_when_gates_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitting.runner import FitRunner

    monkeypatch.setattr(
        "fitting.runner._implicit_scipy_benchmark_gate",
        lambda *_args, **_kwargs: (True, "forced benchmark pass"),
    )
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    assert result.details["implicit_strategy"] == "scipy_general_implicit"
    assert result.details["scipy_safety_passed"] is True
    assert mp.fabs(result.params["a"] - mp.mpf("0.2")) < mp.mpf("1e-8")
    assert mp.fabs(result.params["b"] - mp.mpf("0.5")) < mp.mpf("1e-8")


def test_precision_16_general_implicit_falls_back_when_benchmark_gate_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.runner import FitRunner

    monkeypatch.setattr(
        "fitting.runner._implicit_scipy_benchmark_gate",
        lambda *_args, **_kwargs: (False, "forced benchmark rejection"),
    )
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    last = history[-1]
    assert isinstance(last, dict)
    assert last["from"] == "scipy_implicit_least_squares"
    assert "forced benchmark rejection" in str(last["reason"])


def test_precision_16_general_implicit_falls_back_when_benchmark_gate_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.runner import FitRunner

    def raise_gate_error(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise RuntimeError("forced benchmark gate error")

    monkeypatch.setattr("fitting.runner._implicit_scipy_benchmark_gate", raise_gate_error)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    last = history[-1]
    assert isinstance(last, dict)
    assert last["from"] == "scipy_implicit_least_squares"
    assert "forced benchmark gate error" in str(last["reason"])


def test_scipy_implicit_spotcheck_uses_fresh_implicit_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitting.runner import FitRunner
    import fitting.runner as runner

    monkeypatch.setattr(
        "fitting.runner._implicit_scipy_benchmark_gate",
        lambda *_args, **_kwargs: (True, "forced benchmark pass"),
    )
    original_spotcheck = runner._spotcheck_scipy_solution
    seen_fresh_factory = {"called": False}

    def wrapped_spotcheck(
        model: ModelSpecification,
        observations: Sequence[dict[str, mp.mpf]],
        params: dict[str, mp.mpf],
        fitted_curve: Sequence[mp.mpf],
        *,
        fresh_model_factory: Callable[[], ModelSpecification] | None = None,
    ) -> bool:
        assert fresh_model_factory is not None
        fresh_model_factory()
        seen_fresh_factory["called"] = True
        return original_spotcheck(
            model,
            observations,
            params,
            fitted_curve,
            fresh_model_factory=fresh_model_factory,
        )

    monkeypatch.setattr("fitting.runner._spotcheck_scipy_solution", wrapped_spotcheck)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert seen_fresh_factory["called"] is True


def test_scipy_implicit_rematerialization_uses_seed_hints_and_fresh_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    monkeypatch.setattr(
        "fitting.runner._implicit_scipy_benchmark_gate",
        lambda *_args, **_kwargs: (True, "forced benchmark pass"),
    )
    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    true_values = [mp.mpf("0.2") + mp.mpf("0.5") * x for x in xs]
    ys = [value * value for value in true_values]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u*u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.15"}, "b": {"initial": "0.45"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u",
            parameters=("a", "b"),
            solve_options=ImplicitSolveOptions(method="root", initial="-10", tolerance="1e-16", max_iterations=50),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    diagnostics = result.details.get("implicit_diagnostics")
    assert isinstance(diagnostics, dict)
    assert int(diagnostics["points_solved"]) > 0
    assert max(abs(fitted - expected) for fitted, expected in zip(result.fitted_curve, ys, strict=True)) < mp.mpf("1e-8")


def test_real_scipy_implicit_benchmark_gate_rejects_without_clear_speed_win() -> None:
    from fitting.runner import FitRunner

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    assert any(
        isinstance(item, dict)
        and item.get("from") == "scipy_implicit_least_squares"
        and "benchmark" in str(item.get("reason", ""))
        for item in history
    )


def test_implicit_dependent_parameters_skip_scipy_candidate() -> None:
    from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [(mp.mpf("0.2") + mp.mpf("0.4") * x) ** 2 for x in xs]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u*u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.2"}, "b": {"expr": "a+a"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u",
            parameters=("a", "b"),
            solve_options=ImplicitSolveOptions(method="fixed_point", initial="0", tolerance="1e-16", max_iterations=20),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    assert any(
        isinstance(item, dict)
        and item.get("from") == "scipy_implicit_least_squares"
        and "dependent parameter" in str(item.get("reason", ""))
        for item in history
    )
    assert result.param_errors["b"] > 0
