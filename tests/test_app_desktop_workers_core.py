from __future__ import annotations

import pickle
import os
from types import SimpleNamespace
from typing import Any, Callable

import mpmath as mp
import pytest

from data_extrapolation_latex_latest import ExtrapolationOptions, parse_uncertainty_format

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import (
    CalcJob,
    FitBatchTask,
    FitJob,
    _deserialize_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
    _execute_fit_job_payload_subprocess,
    _fit_job_requires_process_boundary,
    _serialize_fit_job,
)
from app_desktop.workers_qt import FitBatchWorker
from fitting.hp_fitter import FitResult
from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
from shared.parallel_config import ParallelConfig
from shared.parallel_backend import KillableProcessTaskRunner, current_parallel_depth


def _small_self_consistent_fit_job(
    *,
    precision: int = 50,
    parallel_config: ParallelConfig | None = None,
) -> FitJob:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("1") + mp.mpf("2") * x for x in x_series]
    data_rows = list(zip(x_series, y_series))
    sigma_rows: list[tuple[mp.mpf | None, ...]] = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u",
        parameters=("a", "b"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="1",
            tolerance="1e-30",
            max_iterations=50,
        ),
    )
    return FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="u",
        parameter_config={
            "a": {"initial": "0.8"},
            "b": {"initial": "1.8"},
        },
        parameter_names=["a", "b"],
        precision=precision,
        weighted=False,
        label="small-self-consistent",
        implicit_definition=definition,
        timeout_seconds=10.0,
        parallel_config=parallel_config or ParallelConfig(),
    )


def _depth_probe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload": payload,
        "env_depth": os.environ.get("DATALAB_PARALLEL_DEPTH"),
        "current_depth": current_parallel_depth(),
    }


def test_execute_fit_job_payload_poly_recovers_linear_params():
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]

    job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
        poly_degree=1,
        precision=80,
        weighted=False,
        label="unit-test",
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result
    assert fit is not None
    assert mp.almosteq(fit.params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-50"))
    assert mp.almosteq(fit.params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-50"))


def test_execute_fit_job_payload_self_consistent_wires_definition_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    x_series = [mp.mpf(v) for v in ["0", "1", "2"]]
    y_series = [mp.mpf(v) for v in ["0.3", "0.4", "0.5"]]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]
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
            tolerance="1e-36",
        ),
    )
    calls: dict[str, object] = {}

    class FakeFitRunner:
        def fit(
            self,
            problem: object,
            variable_data: dict[str, list[mp.mpf]],
            target_series: list[mp.mpf],
            *,
            precision: int,
            weights: list[mp.mpf] | None = None,
            data_sigmas: list[mp.mpf | None] | None = None,
        ) -> FitResult:
            calls["problem"] = problem
            calls["variable_data"] = variable_data
            calls["target_series"] = target_series
            calls["precision"] = precision
            calls["weights"] = weights
            calls["data_sigmas"] = data_sigmas
            return FitResult(
                params={"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.4")},
                param_errors={},
                chi2=mp.mpf("0"),
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[],
                fitted_curve=list(target_series),
                covariance=[],
                details={
                    "implicit_diagnostics": {
                        "points_solved": 7,
                        "root_fallbacks": 2,
                        "max_iterations_used": 5,
                        "max_residual": "1.0e-42",
                    }
                },
            )

    monkeypatch.setattr(workers_core, "FitRunner", FakeFitRunner)

    job = FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="",
        parameter_config={
            "a": {"initial": 0.1},
            "b": {"initial": 0.2},
            "c": {"initial": 0.4},
        },
        parameter_names=["a", "b", "c"],
        precision=30,
        weighted=False,
        label="self-consistent-test",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result

    problem = calls["problem"]
    assert getattr(problem, "implicit_definition") is definition
    assert getattr(problem, "expression") == "u"
    assert getattr(problem, "variables") == ("x",)
    assert getattr(problem, "target_name") == "u"
    assert getattr(problem, "parameter_config") == job.parameter_config
    assert calls["variable_data"] == {"x": x_series}
    assert calls["target_series"] == y_series
    assert calls["precision"] == 30
    assert calls["weights"] is None
    assert calls["data_sigmas"] == [None] * len(y_series)
    assert {name: float(value) for name, value in fit.params.items()} == {
        "a": 0.1,
        "b": 0.2,
        "c": 0.4,
    }
    assert payload.expression == "u"
    details = fit.details
    assert details["implicit_variable"] == "u"
    assert details["equation"] == "a + b*Cos[u] + c*x"
    assert details["output_expression"] == "u"
    assert details["implicit_diagnostics"] == {
        "points_solved": 7,
        "root_fallbacks": 2,
        "max_iterations_used": 5,
        "max_residual": "1.0e-42",
    }


def test_execute_fit_job_payload_self_consistent_requires_definition() -> None:
    with pytest.raises(ValueError, match="requires an implicit definition"):
        _execute_fit_job_payload(
            FitJob(
                model_type="self_consistent",
                headers=["x", "u"],
                data_rows=[],
                sigma_rows=[],
                x_series=[],
                y_series=[],
                sigma_series=[],
                weights=None,
                variable_map={"x": "x"},
                variable_data={"x": []},
                target_series=[],
                target_column="u",
                model_expr="",
                parameter_config={"a": {"initial": 0.1}},
                parameter_names=["a"],
                precision=30,
                weighted=False,
                label="missing-definition-test",
            )
        )


def test_execute_fit_job_payload_self_consistent_observed_implicit_linear_fast_path() -> None:
    with mp.workdps(80):
        n_series = [mp.mpf(n) for n in range(12, 22)]
        params = {
            "d0": mp.mpf("-0.012"),
            "d2": mp.mpf("0.0075"),
            "d4": mp.mpf("0.013"),
            "d6": mp.mpf("0.021"),
            "d8": mp.mpf("-0.11"),
        }
        y_series = [
            params["d0"]
            + params["d2"] / n**2
            + params["d4"] / n**4
            + params["d6"] / n**6
            + params["d8"] / n**8
            for n in n_series
        ]
    sigma_series = [mp.mpf("1e-9")] * len(y_series)
    weights = [1 / (sigma * sigma) for sigma in sigma_series]
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/n**2 + d4/n**4 + d6/n**6 + d8/n**8",
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d6", "d8"),
        constants={},
        solve_options=ImplicitSolveOptions(method="root", initial="0", tolerance="1e-40"),
    )
    job = FitJob(
        model_type="self_consistent",
        headers=["n", "delta"],
        data_rows=list(zip(n_series, y_series)),
        sigma_rows=[(None, sigma) for sigma in sigma_series],
        x_series=n_series,
        y_series=y_series,
        sigma_series=sigma_series,
        weights=weights,
        variable_map={"n": "n"},
        variable_data={"n": n_series, "delta": y_series},
        target_series=y_series,
        target_column="delta",
        model_expr="delta",
        parameter_config={name: {"initial": "0"} for name in params},
        parameter_names=list(params),
        precision=80,
        weighted=True,
        label="observed-implicit-linear",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)

    assert payload.fit_result.details["implicit_fast_path"] == "observed_implicit_linear"
    assert payload.fit_result.details["implicit_diagnostics"]["points_solved"] == 0
    for name, expected in params.items():
        assert mp.almosteq(payload.fit_result.params[name], expected, abs_eps=mp.mpf("1e-30"))


def test_self_consistent_fit_job_is_marked_for_process_boundary() -> None:
    job = _small_self_consistent_fit_job()
    assert _fit_job_requires_process_boundary(job) is True

    direct_job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=[],
        sigma_rows=[],
        x_series=[],
        y_series=[],
        sigma_series=[],
        weights=None,
        variable_map={},
        variable_data={},
        target_series=[],
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
    )
    assert _fit_job_requires_process_boundary(direct_job) is False


def test_fit_job_default_parallel_config_has_no_implicit_backend_gate() -> None:
    job = _small_self_consistent_fit_job()

    assert isinstance(job.parallel_config, ParallelConfig)
    assert not hasattr(job.parallel_config, "enable_new_implicit_backend")


def test_self_consistent_fit_job_payload_is_spawn_picklable() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    assert "enable_new_implicit_backend" not in payload["parallel_config"]
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    assert restored.model_type == "self_consistent"
    assert restored.implicit_definition is not None
    assert restored.implicit_definition.equation == "a + b*x"
    assert restored.implicit_definition.solve_options.method == "root"
    assert restored.timeout_seconds == 10.0
    assert restored.parallel_config.process_start_method == "spawn"
    assert not hasattr(restored.parallel_config, "enable_new_implicit_backend")


def test_stale_fit_job_payload_false_implicit_backend_is_ignored() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["enable_new_implicit_backend"] = False

    restored = _deserialize_fit_job(payload)

    assert not hasattr(restored.parallel_config, "enable_new_implicit_backend")


def test_self_consistent_fit_subprocess_uses_killable_runner_and_forwards_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return workers_core._serialize_fit_result_payload(
                workers_core.FitResultPayload(
                    job=job,
                    fit_result=FitResult(
                        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                        param_errors={},
                        chi2=mp.mpf("0"),
                        reduced_chi2=mp.mpf("0"),
                        aic=mp.mpf("0"),
                        bic=mp.mpf("0"),
                        r2=mp.mpf("1"),
                        rmse=mp.mpf("0"),
                        residuals=[],
                        fitted_curve=[],
                        covariance=[],
                        details={},
                    ),
                    expression="u",
                    logs=[],
                    warnings=[],
                )
            )

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FakeRunner)

    result = _execute_fit_job_payload_subprocess(
        job,
        timeout_seconds=12.5,
        should_cancel=lambda: False,
    )

    assert result.fit_result.params["a"] == mp.mpf("1")
    assert calls["config"] is job.parallel_config
    assert calls["target"] is workers_core._fit_job_subprocess_entry
    assert calls["payload"] == _serialize_fit_job(job)
    assert calls["timeout_seconds"] == 12.5
    assert callable(calls["should_cancel"])


def test_self_consistent_fit_subprocess_ignores_stale_disabled_legacy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["enable_new_implicit_backend"] = False
    job = _deserialize_fit_job(payload)
    calls: dict[str, object] = {}

    class FailingRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return workers_core._serialize_fit_result_payload(
                workers_core.FitResultPayload(
                    job=job,
                    fit_result=FitResult(
                        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                        param_errors={},
                        chi2=mp.mpf("0"),
                        reduced_chi2=mp.mpf("0"),
                        aic=mp.mpf("0"),
                        bic=mp.mpf("0"),
                        r2=mp.mpf("1"),
                        rmse=mp.mpf("0"),
                        residuals=[],
                        fitted_curve=[],
                        covariance=[],
                        details={},
                    ),
                    expression="u",
                    logs=[],
                    warnings=[],
                )
            )

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FailingRunner)

    result = _execute_fit_job_payload_subprocess(
        job,
        timeout_seconds=9.5,
        should_cancel=lambda: False,
    )

    assert result.fit_result.params["a"] == mp.mpf("1")
    assert calls["timeout_seconds"] == 9.5
    assert callable(calls["should_cancel"])
    assert calls["config"] is job.parallel_config
    assert calls["target"] is workers_core._fit_job_subprocess_entry


def test_legacy_implicit_backend_surfaces_are_removed() -> None:
    assert not hasattr(ParallelConfig, "enable_new_implicit_backend")
    assert not hasattr(workers_core, "_execute_fit_job_payload_subprocess_legacy")
    assert not hasattr(workers_core, "_fit_job_subprocess_queue_entry")
    assert not hasattr(workers_core, "_terminate_fit_subprocess")
    assert not hasattr(workers_core, "_deserialize_fit_subprocess_queue_payload")
    assert not hasattr(workers_core, "_fit_self_consistent_with_legacy_hooks")
    assert not hasattr(workers_core, "_self_consistent_hooks_replaced")
    assert not hasattr(workers_core, "_ORIGINAL_BUILD_IMPLICIT_MODEL_SPECIFICATION")
    assert not hasattr(workers_core, "_ORIGINAL_CAN_FIT_OBSERVED_IMPLICIT_VARIABLE")
    assert not hasattr(workers_core, "_ORIGINAL_FIT_OBSERVED_IMPLICIT_VARIABLE_LINEAR_MODEL")
    assert not hasattr(workers_core, "_ORIGINAL_FIT_CUSTOM_MODEL")


def test_self_consistent_fit_subprocess_target_uses_job_precision_under_low_ambient_dps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job(precision=90)
    precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
    job.y_series[0] = precise
    job.target_series[0] = precise
    observed: dict[str, object] = {}

    def fake_execute(received_job: FitJob) -> workers_core.FitResultPayload:
        observed["mp_dps"] = mp.mp.dps
        observed["target_value"] = received_job.target_series[0]
        return workers_core.FitResultPayload(
            job=received_job,
            fit_result=FitResult(
                params={"a": precise},
                param_errors={},
                chi2=precise,
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[precise],
                fitted_curve=[precise],
                covariance=[],
                details={},
            ),
            expression="u",
            logs=[],
            warnings=[],
        )

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload", fake_execute)
    payload = _serialize_fit_job(job)

    with mp.workdps(15):
        result_payload = workers_core._fit_job_subprocess_entry(payload)
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    assert observed["mp_dps"] == 90
    with mp.workdps(100):
        assert mp.almosteq(observed["target_value"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_subprocess_maps_backend_interruption_to_cancelled_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()

    class InterruptingRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            self.config = config

        def run_killable(self, *args: object, **kwargs: object) -> object:
            raise InterruptedError("backend interrupted")

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", InterruptingRunner)

    with pytest.raises(InterruptedError, match="Self-consistent fit cancelled"):
        _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)


def test_fit_killable_runner_child_depth_marker_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    runner = KillableProcessTaskRunner(config=ParallelConfig())

    payload = runner.run_killable(
        _depth_probe_payload,
        {"kind": "fit"},
        timeout_seconds=2.0,
    )

    assert payload["payload"] == {"kind": "fit"}
    assert payload["env_depth"] == "1" or payload["current_depth"] >= 1


def test_self_consistent_fit_job_serialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        job.x_series[0] = precise
        row = list(job.data_rows[0])
        row[0] = precise
        job.data_rows[0] = tuple(row)
        job.variable_data["x"][0] = precise

        payload = _serialize_fit_job(job)

    with mp.workdps(15):
        restored = _deserialize_fit_job(payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.x_series[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.data_rows[0][0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.variable_data["x"][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_job_serialization_unwraps_uncertainty_sigmas() -> None:
    job = _small_self_consistent_fit_job(precision=50)
    uncertain = parse_uncertainty_format("1.23(4)", lang="en")
    job.sigma_rows[0] = (None, uncertain)
    job.sigma_series[0] = uncertain  # type: ignore[list-item]

    payload = _serialize_fit_job(job)

    assert mp.almosteq(mp.mpf(payload["sigma_rows"][0][1]), mp.mpf("0.04"), abs_eps=mp.mpf("1e-18"))
    assert mp.almosteq(mp.mpf(payload["sigma_series"][0]), mp.mpf("0.04"), abs_eps=mp.mpf("1e-18"))

    restored = _deserialize_fit_job(payload)

    assert restored.sigma_rows[0][1] == mp.mpf("0.04")
    assert restored.sigma_series[0] == mp.mpf("0.04")


def test_self_consistent_fit_result_deserialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("2.34567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        fit = FitResult(
            params={"a": precise},
            param_errors={"a": mp.mpf("1e-40")},
            chi2=precise,
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[precise],
            fitted_curve=[precise],
            covariance=[[precise]],
            details={"metric": precise},
        )
        result_payload = workers_core._serialize_fit_result_payload(
            workers_core.FitResultPayload(
                job=job,
                fit_result=fit,
                expression="u",
                logs=[],
                warnings=[],
            )
        )

    with mp.workdps(15):
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.chi2, precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.residuals[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.fitted_curve[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.covariance[0][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_subprocess_executes_real_fit_roundtrip() -> None:
    job = _small_self_consistent_fit_job()

    payload = _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)
    fit = payload.fit_result

    assert mp.almosteq(fit.params["a"], mp.mpf("1"), abs_eps=mp.mpf("1e-20"))
    assert mp.almosteq(fit.params["b"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))
    assert payload.job.model_type == "self_consistent"
    assert payload.expression == "u"


def test_fit_batch_worker_routes_self_consistent_fit_through_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        calls["job"] = received_job
        calls["timeout_seconds"] = timeout_seconds
        calls["should_cancel"] = should_cancel
        return SimpleNamespace(fit_result=None, logs=[], warnings=[])

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([], capture_output=False)
    payload = worker._run_fit_task(job)

    assert payload.fit_result is None
    assert calls["job"] is job
    assert calls["timeout_seconds"] == 10.0
    assert callable(calls["should_cancel"])


def test_fit_batch_worker_emits_cancelled_when_self_consistent_subprocess_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    job = _small_self_consistent_fit_job()

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        raise InterruptedError("cancelled")

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([FitBatchTask(index=0, fit_job=job)], capture_output=False)
    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        worker.start()

    assert worker.wait(3000)


def test_execute_calc_job_extrapolation_returns_payload() -> None:
    with mp.workdps(80):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, 9)]  # 8 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + " ".join(mp.nstr(v, 50) for v in terms) + "\n"

        opts = ExtrapolationOptions(method="richardson", mp_precision=80)
        job = CalcJob(
            mode="extrapolation",
            data_path=None,
            manual_content=data_text,
            manual_constants="",
            constants_file_path=None,
            options=opts,
            caption=None,
            generate_latex=False,
            output_path="",
            use_dcolumn=False,
            verbose=False,
            render_plots=False,
            lang="en",
            latex_digits=16,
            latex_group_size=3,
            uncertainty_digits=2,
        )

        result = _execute_calc_job(job)
        assert result.mode == "extrapolation"
        assert result.latex_path is None
        payload = result.payload
        assert payload["headers"] == headers
        assert len(payload["data_rows"]) == 1
        assert len(payload["results"]) == 1
        assert payload["precision_used"] == 80
        assert payload["render_plots"] is False
        assert "plots" not in payload

        res0 = payload["results"][0]
        assert mp.fabs(res0.value - limit) < mp.mpf("1e-2")


def test_run_calculation_excludes_disabled_error_constants_from_calc_job(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.window import ExtrapolationWindow

    class _Signal:
        def connect(self, _callback: object) -> None:
            return

    class _DummyCalcWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

    captured: dict[str, object] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("error"))
    win._data_stack.setCurrentIndex(1)
    win.manual_data_edit.setPlainText("A B\n1 2\n")
    win.formula_edit.setPlainText("A + B")
    win.error_constants_editor.set_rows([{"name": "K", "value": "1.23(4)"}])
    win.error_constants_editor.setChecked(False)

    win.run_calculation()

    job = captured["job"]
    assert isinstance(job, CalcJob)
    assert captured["started"] is True
    assert win.error_constants_editor.constants_dict(validate=False) == {"K": "1.23(4)"}
    assert job.constants_enabled is False
    assert job.manual_constants == ""
