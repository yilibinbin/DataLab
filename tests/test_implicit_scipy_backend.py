from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

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


def test_precision_16_general_implicit_accepts_scipy_candidate_when_gates_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.runner import FitRunner, _ImplicitScipyBenchmark

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    def fake_gate(
        definition: Any,
        parameter_state: Any,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        *,
        seed_hint: Any,
        weights: list[mp.mpf] | None,
        data_sigmas: list[mp.mpf | None] | None,
        precision: int,
    ) -> _ImplicitScipyBenchmark:
        from fitting.hp_fitter import fit_custom_model
        from fitting.implicit_model import build_implicit_model_specification

        spec = build_implicit_model_specification(
            definition,
            target_data=target_data,
            seed_hint=seed_hint,
            use_analytic_derivatives=False,
        )
        result = fit_custom_model(
            spec,
            parameter_state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        return _ImplicitScipyBenchmark(
            True,
            "benchmark accepted: scipy_total=0.1s start_norm=0.01s candidate_fit=0.05s rematerialize=0.04s",
            materialized_result=result,
            diagnostics=getattr(spec, "implicit_diagnostics", None),
        )

    monkeypatch.setattr("fitting.runner._implicit_scipy_benchmark_gate", fake_gate)

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    assert result.details["implicit_strategy"] == "scipy_general_implicit"
    assert result.details["scipy_safety_passed"] is True
    assert mp.fabs(result.params["a"] - mp.mpf("0.2")) < mp.mpf("1e-8")
    assert mp.fabs(result.params["b"] - mp.mpf("0.5")) < mp.mpf("1e-8")


def test_precision_16_general_implicit_falls_back_when_benchmark_gate_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.runner import FitRunner, _ImplicitScipyBenchmark

    monkeypatch.setattr(
        "fitting.runner._implicit_scipy_benchmark_gate",
        lambda *_args, **_kwargs: _ImplicitScipyBenchmark(False, "forced benchmark rejection"),
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

    def raise_gate_error(*_args: object, **_kwargs: object) -> object:
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
    from fitting.runner import FitRunner, _ImplicitScipyBenchmark

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

    def fake_gate(
        definition: Any,
        parameter_state: Any,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        *,
        seed_hint: Any,
        weights: list[mp.mpf] | None,
        data_sigmas: list[mp.mpf | None] | None,
        precision: int,
    ) -> _ImplicitScipyBenchmark:
        from fitting.hp_fitter import fit_custom_model
        from fitting.implicit_model import build_implicit_model_specification

        spec = build_implicit_model_specification(
            definition,
            target_data=target_data,
            seed_hint=seed_hint,
            use_analytic_derivatives=False,
        )
        result = fit_custom_model(
            spec,
            parameter_state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        return _ImplicitScipyBenchmark(
            True,
            "benchmark accepted: scipy_total=0.1s start_norm=0.01s candidate_fit=0.05s rematerialize=0.04s",
            materialized_result=result,
            diagnostics=getattr(spec, "implicit_diagnostics", None),
        )

    monkeypatch.setattr("fitting.runner._implicit_scipy_benchmark_gate", fake_gate)

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    diagnostics = result.details.get("implicit_diagnostics")
    assert isinstance(diagnostics, dict)
    assert int(diagnostics["points_solved"]) > 0
    assert max(abs(fitted - expected) for fitted, expected in zip(result.fitted_curve, ys, strict=True)) < mp.mpf("1e-8")


def test_real_scipy_implicit_benchmark_gate_reports_total_cost() -> None:
    from fitting.runner import FitRunner

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    if result.details["optimizer_backend"] == "scipy_implicit_least_squares":
        reason = str(result.details["scipy_implicit_benchmark"])
    else:
        history = result.details.get("fallback_history", [])
        assert isinstance(history, list)
        reason = " ".join(str(item.get("reason", "")) for item in history if isinstance(item, dict))
    assert "scipy_total=" in reason
    assert "start_norm=" in reason
    assert "candidate_fit=" in reason
    assert "rematerialize=" in reason
    assert "comparator=" in reason


def test_scipy_benchmark_gate_reports_full_route_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitting.constraints import build_parameter_state
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.runner import _implicit_scipy_benchmark_gate

    stages: list[str] = []

    def fake_candidate(*_args: object, **_kwargs: object) -> object:
        stages.append("candidate_fit")
        raise RuntimeError("stop after candidate stage")

    monkeypatch.setattr("fitting.runner._fit_with_scipy_least_squares", fake_candidate)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]
    state = build_parameter_state({"a": {"initial": "0.15"}, "b": {"initial": "0.45"}}, ["a", "b"])
    definition = _quadratic_implicit_problem().implicit_definition
    assert isinstance(definition, ImplicitModelDefinition)

    benchmark = _implicit_scipy_benchmark_gate(
        definition,
        state,
        {"x": xs},
        ys,
        seed_hint=None,
        weights=None,
        data_sigmas=None,
        precision=16,
    )

    assert benchmark.accepted is False
    assert stages == ["candidate_fit"]
    assert "candidate route failed" in benchmark.reason


def test_rejected_scipy_benchmark_reuses_comparator_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.runner import FitRunner

    calls = {"fit": 0}

    def fake_gate(
        definition: Any,
        parameter_state: Any,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        *,
        seed_hint: Any,
        weights: list[mp.mpf] | None,
        data_sigmas: list[mp.mpf | None] | None,
        precision: int,
    ) -> Any:
        from fitting.hp_fitter import fit_custom_model
        from fitting.implicit_model import build_implicit_model_specification
        from fitting.runner import _ImplicitScipyBenchmark

        spec = build_implicit_model_specification(definition, target_data=target_data, seed_hint=seed_hint)
        result = fit_custom_model(
            spec,
            parameter_state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        calls["fit"] += 1
        return _ImplicitScipyBenchmark(
            False,
            "benchmark rejected SciPy implicit candidate: selected_comparator=numeric_finite_difference",
            fallback_result=result,
            fallback_diagnostics=getattr(spec, "implicit_diagnostics", None),
        )

    monkeypatch.setattr("fitting.runner._implicit_scipy_benchmark_gate", fake_gate)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert calls["fit"] == 1
    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    assert "fallback_history" in result.details


def test_scipy_benchmark_gate_compares_numeric_when_analytic_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting.constraints import build_parameter_state
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner, _ImplicitScipyBenchmark

    seen_gate = {"called": False}

    def fake_gate(*_args: object, **_kwargs: object) -> _ImplicitScipyBenchmark:
        seen_gate["called"] = True
        return _ImplicitScipyBenchmark(False, "benchmark rejected SciPy implicit candidate: comparator=numeric_finite_difference")

    monkeypatch.setattr("fitting.runner._implicit_scipy_benchmark_gate", fake_gate)
    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.exp(mp.mpf("0.2") + mp.mpf("0.5") * x) for x in xs]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="Exp[u]",
        variables=("x",),
        parameter_config={"a": {"initial": "0.15"}, "b": {"initial": "0.45"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="Exp[u]",
            parameters=("a", "b"),
        ),
    )
    build_parameter_state(problem.parameter_config or {}, ["a", "b"])

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert seen_gate["called"] is True
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    assert any("comparator=numeric_finite_difference" in str(item.get("reason", "")) for item in history if isinstance(item, dict))


def test_real_scipy_benchmark_gate_compares_numeric_when_analytic_unavailable() -> None:
    from fitting.constraints import build_parameter_state
    from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
    from fitting.runner import _implicit_scipy_benchmark_gate

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [mp.mpf("0.2") + mp.mpf("0.5") * x for x in xs]
    state = build_parameter_state({"a": {"initial": "0.15"}, "b": {"initial": "0.45"}}, ["a", "b"])
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="Abs[u]",
        parameters=("a", "b"),
        solve_options=ImplicitSolveOptions(method="fixed_point", initial="0", tolerance="1e-16", max_iterations=20),
    )

    benchmark = _implicit_scipy_benchmark_gate(
        definition,
        state,
        {"x": xs},
        ys,
        seed_hint=None,
        weights=None,
        data_sigmas=None,
        precision=16,
    )

    assert "comparator=general_implicit_numeric_finite_difference" in benchmark.reason
    assert "analytic derivative evaluator could not be built" not in benchmark.reason
    if benchmark.fallback_result is not None:
        assert benchmark.fallback_result.details["implicit_strategy"] == "general_implicit_numeric_finite_difference"


def test_implicit_scipy_skips_unweighted_data_sigmas() -> None:
    from fitting.runner import FitRunner

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    result = FitRunner().fit(
        _quadratic_implicit_problem(),
        {"x": xs},
        ys,
        precision=16,
        data_sigmas=[mp.mpf("0.01")] * len(xs),
    )

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["scipy_safety_passed"] is False
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    assert any(
        isinstance(item, dict)
        and item.get("from") == "scipy_implicit_least_squares"
        and "unweighted data_sigmas" in str(item.get("reason", ""))
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
