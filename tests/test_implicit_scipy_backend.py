from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

import mpmath as mp
import pytest

from fitting.model_parser import ModelSpecification
from fitting.problem import ModelProblem

pytest.importorskip("scipy.optimize")


def _implicit_cache_from_spec(model: ModelSpecification) -> object:
    from fitting.implicit_model import ImplicitEvaluationCache

    callables: list[Any] = [model.evaluate_func, *model.gradient_funcs.values()]
    for func in callables:
        closure = getattr(func, "__closure__", None)
        if not closure:
            continue
        for cell in closure:
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, ImplicitEvaluationCache):
                return value
    raise AssertionError("ModelSpecification does not expose an implicit cache in callable closures")


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
    """Exercise the caller seam for a future cached/sample gate that can accept SciPy."""
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

        def observing_fresh_model_factory() -> ModelSpecification:
            seen_fresh_factory["called"] = True
            return fresh_model_factory()

        return bool(original_spotcheck(
            model,
            observations,
            params,
            fitted_curve,
            fresh_model_factory=observing_fresh_model_factory,
        ))

    monkeypatch.setattr("fitting.runner._spotcheck_scipy_solution", wrapped_spotcheck)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]

    FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=16)

    assert seen_fresh_factory["called"] is True


def test_preflight_and_production_use_distinct_implicit_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    import fitting.runner as runner
    from fitting.implicit_model import ImplicitModelDefinition

    original_build = runner.build_implicit_model_specification
    caches_by_stage: dict[str, list[object]] = {"production": [], "preflight": []}

    def recording_build(*args: Any, **kwargs: Any) -> ModelSpecification:
        model = original_build(*args, **kwargs)
        cache = _implicit_cache_from_spec(model)
        stack_functions = {frame.function for frame in inspect.stack()}
        if "_probe_implicit_derivative_parity" in stack_functions:
            caches_by_stage["preflight"].append(cache)
        elif "_fit_mpmath_implicit_route" in stack_functions:
            caches_by_stage["production"].append(cache)
        return model

    monkeypatch.setattr("fitting.runner.build_implicit_model_specification", recording_build)
    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]
    definition = _quadratic_implicit_problem().implicit_definition
    assert isinstance(definition, ImplicitModelDefinition)

    result = runner.FitRunner().fit(_quadratic_implicit_problem(), {"x": xs}, ys, precision=80)

    assert result.details["implicit_strategy"] == "analytic_implicit_output_space"
    assert len(caches_by_stage["production"]) == 1
    assert len(caches_by_stage["preflight"]) >= 2
    all_caches = [*caches_by_stage["production"], *caches_by_stage["preflight"]]
    assert len({id(cache) for cache in all_caches}) == len(all_caches)


def test_scipy_candidate_spotcheck_rematerialize_and_comparator_use_distinct_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitting.runner as runner
    from fitting.constraints import build_parameter_state
    from fitting.implicit_model import ImplicitModelDefinition

    caches_by_stage: dict[str, list[object]] = {
        "start_norm": [],
        "candidate": [],
        "spotcheck": [],
        "rematerialize": [],
        "comparator": [],
    }

    original_weighted_norm = runner._weighted_residual_norm
    original_scipy_fit = runner._fit_with_scipy_least_squares
    original_materialize = runner._materialize_scipy_result_with_fresh_model
    original_mpmath_route = runner._fit_mpmath_implicit_route
    original_build = runner.build_implicit_model_specification

    def record(stage: str, model: ModelSpecification) -> None:
        caches_by_stage[stage].append(_implicit_cache_from_spec(model))

    def recording_weighted_norm(model: ModelSpecification, *args: Any, **kwargs: Any) -> float:
        record("start_norm", model)
        return float(original_weighted_norm(model, *args, **kwargs))

    def recording_scipy_fit(
        model: ModelSpecification,
        *args: Any,
        fresh_model_factory: Callable[[], ModelSpecification] | None = None,
        **kwargs: Any,
    ) -> Any:
        record("candidate", model)

        def recording_fresh_factory() -> ModelSpecification:
            assert fresh_model_factory is not None
            fresh = fresh_model_factory()
            record("spotcheck", fresh)
            return fresh

        return original_scipy_fit(
            model,
            *args,
            fresh_model_factory=recording_fresh_factory,
            **kwargs,
        )

    def recording_materialize(
        candidate: Any,
        fresh_model_factory: Callable[[], ModelSpecification],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        def recording_fresh_factory() -> ModelSpecification:
            fresh = fresh_model_factory()
            record("rematerialize", fresh)
            return fresh

        return original_materialize(candidate, recording_fresh_factory, *args, **kwargs)

    in_comparator = {"active": False}

    def recording_build(*args: Any, **kwargs: Any) -> ModelSpecification:
        model = original_build(*args, **kwargs)
        if in_comparator["active"]:
            record("comparator", model)
        return model

    def recording_mpmath_route(*args: Any, **kwargs: Any) -> Any:
        in_comparator["active"] = True
        try:
            return original_mpmath_route(*args, **kwargs)
        finally:
            in_comparator["active"] = False

    monkeypatch.setattr("fitting.runner._weighted_residual_norm", recording_weighted_norm)
    monkeypatch.setattr("fitting.runner._fit_with_scipy_least_squares", recording_scipy_fit)
    monkeypatch.setattr("fitting.runner._materialize_scipy_result_with_fresh_model", recording_materialize)
    monkeypatch.setattr("fitting.runner._fit_mpmath_implicit_route", recording_mpmath_route)
    monkeypatch.setattr("fitting.runner.build_implicit_model_specification", recording_build)

    xs = [mp.mpf(i) for i in range(1, 8)]
    ys = [(mp.mpf("0.2") + mp.mpf("0.5") * x) ** 2 for x in xs]
    state = build_parameter_state({"a": {"initial": "0.15"}, "b": {"initial": "0.45"}}, ["a", "b"])
    definition = _quadratic_implicit_problem().implicit_definition
    assert isinstance(definition, ImplicitModelDefinition)

    benchmark = runner._implicit_scipy_benchmark_gate(
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
    assert benchmark.fallback_result is not None
    assert all(caches_by_stage[stage] for stage in caches_by_stage)
    flattened = [cache for caches in caches_by_stage.values() for cache in caches]
    assert len({id(cache) for cache in flattened}) == len(flattened)


def test_scipy_implicit_rematerialization_uses_seed_hints_and_fresh_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise accepted-result metadata wiring for a future cached/sample gate."""
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

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    history = result.details.get("fallback_history", [])
    assert isinstance(history, list)
    reason = " ".join(str(item.get("reason", "")) for item in history if isinstance(item, dict))
    assert "scipy_total=" in reason
    assert "start_norm=" in reason
    assert "candidate_fit=" in reason
    assert "rematerialize=" in reason
    assert "comparator=" in reason


def test_scipy_benchmark_gate_rejects_after_full_comparator_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import FitResult
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.runner import _ImplicitScipyBenchmark, _SciPyCandidate, _implicit_scipy_benchmark_gate

    def fit_result(strategy: str) -> FitResult:
        return FitResult(
            params={"a": mp.mpf("0.2"), "b": mp.mpf("0.5")},
            param_errors={"a": mp.mpf("0"), "b": mp.mpf("0")},
            chi2=mp.mpf("0"),
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[],
            fitted_curve=[],
            covariance=[],
            details={"implicit_strategy": strategy},
        )

    candidate_result = fit_result("scipy_candidate")
    comparator_result = fit_result("analytic_implicit_output_space")
    monkeypatch.setattr("fitting.runner._weighted_residual_norm", lambda *_args, **_kwargs: mp.mpf("1"))
    monkeypatch.setattr(
        "fitting.runner._fit_with_scipy_least_squares",
        lambda *_args, **_kwargs: _SciPyCandidate(
            candidate_result,
            True,
            "ok",
            1.0,
            True,
            (mp.mpf("0.2"), mp.mpf("0.5")),
        ),
    )
    monkeypatch.setattr("fitting.runner._accept_scipy_result", lambda *_args, **_kwargs: (True, "accepted"))
    monkeypatch.setattr(
        "fitting.runner._materialize_scipy_result_with_fresh_model",
        lambda *_args, **_kwargs: (candidate_result, None),
    )
    monkeypatch.setattr(
        "fitting.runner._fit_mpmath_implicit_route",
        lambda *_args, **_kwargs: (comparator_result, []),
    )
    times = iter([0.0, 0.01, 0.01, 0.11, 0.11, 0.13, 0.13, 1.13])
    monkeypatch.setattr("fitting.runner.time.perf_counter", lambda: next(times))

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

    assert isinstance(benchmark, _ImplicitScipyBenchmark)
    assert benchmark.accepted is False
    assert benchmark.fallback_result is comparator_result
    assert "scipy_total=0.13s" in benchmark.reason
    assert "paid_total=1.13s" in benchmark.reason
    assert "selected_comparator=analytic_implicit_output_space" in benchmark.reason


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
