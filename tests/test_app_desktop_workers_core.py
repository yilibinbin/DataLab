from __future__ import annotations

import os
import pickle
from types import SimpleNamespace
from typing import Any, Callable, cast

import mpmath as mp
import pytest

from data_extrapolation_latex_latest import ExtrapolationOptions

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import (
    CalcJob,
    FitBatchTask,
    FitJob,
    RootSolvingJob,
    _deserialize_root_solving_job,
    _execute_root_solving_job_payload,
    _execute_root_solving_job_payload_subprocess,
    _serialize_root_solving_job,
    _deserialize_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
    _execute_fit_job_payload_subprocess,
    _fit_job_requires_process_boundary,
    _serialize_fit_job,
)
from app_desktop.workers_qt import FitBatchWorker
from app_desktop.workers_qt import RootSolvingWorker
from fitting.hp_fitter import FitResult
from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
from shared.parallel_config import ParallelConfig
from shared.parallel_backend import KillableProcessTaskRunner, current_parallel_depth
from shared.uncertainty import UncertainValue


def _assert_primitive_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_primitive_payload(item)
        return
    if isinstance(value, tuple):
        for item in value:
            _assert_primitive_payload(item)
        return
    assert isinstance(value, (str, int, float, bool, type(None)))


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


def test_root_solving_job_payload_uses_data_rows_and_is_spawn_picklable() -> None:
    job = RootSolvingJob(
        equations=("x**2 - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("4.0(2)",),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        uncertainty_digits=2,
        generate_latex=True,
        output_path="/tmp/root.tex",
        latex_caption="Frozen caption",
        latex_digits=12,
        latex_group_size=4,
        latex_include_dcolumn=True,
        latex_language="zh",
        render_plots=True,
    )

    payload = _serialize_root_solving_job(job)
    restored = pickle.loads(pickle.dumps(payload))

    _assert_primitive_payload(restored)
    assert restored["data_headers"] == ("A",)
    assert restored["data_rows"] == (("4.0(2)",),)
    assert restored["scan_config"] == {}
    assert restored["uncertainty_digits"] == 2
    assert restored["latex_caption"] == "Frozen caption"
    assert restored["latex_digits"] == 12
    assert restored["latex_group_size"] == 4
    assert restored["latex_include_dcolumn"] is True
    assert restored["latex_language"] == "zh"
    assert restored["render_plots"] is True


def test_root_worker_payload_round_trips_frozen_latex_settings() -> None:
    job = RootSolvingJob(
        equations=("x**2 - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("4.0(2)",),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        uncertainty_digits=2,
        generate_latex=True,
        output_path="/tmp/root.tex",
        latex_caption="Root run",
        latex_digits=11,
        latex_group_size=2,
        latex_include_dcolumn=True,
        latex_language="en",
    )

    restored = _deserialize_root_solving_job(_serialize_root_solving_job(job))

    assert restored.latex_caption == "Root run"
    assert restored.latex_digits == 11
    assert restored.latex_group_size == 2
    assert restored.latex_include_dcolumn is True
    assert restored.latex_language == "en"
    assert restored.uncertainty_digits == 2


def test_root_worker_payload_defaults_legacy_render_plots_to_false() -> None:
    payload = {
        "equations": ("x**2 - 2",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 16,
        "display_digits": 10,
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.render_plots is False


def test_root_worker_payload_defaults_latex_language_to_job_language() -> None:
    payload = {
        "equations": ("x**2 - 2",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 16,
        "display_digits": 10,
        "language": "en",
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.latex_language == "en"


def test_root_worker_payload_preserves_uncertainty_options() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=20,
        uncertainty_digits=3,
        uncertainty_options={"method": "monte_carlo", "monte_carlo_samples": 25, "monte_carlo_seed": "7"},
    )

    payload = _serialize_root_solving_job(job)
    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 25,
        "monte_carlo_seed": "7",
    }


def test_root_worker_payload_safely_normalizes_bad_uncertainty_options() -> None:
    payload = {
        "equations": ("x^2 - C",),
        "unknown_rows": ({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": True,
        "constants_rows": ({"name": "C", "value": "4.0(2)"},),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 80,
        "display_digits": 20,
        "uncertainty_options": {
            "method": "monte_carlo",
            "monte_carlo_samples": "bad",
            "monte_carlo_seed": 0,
        },
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "0",
    }


def test_root_worker_payload_safely_normalizes_unknown_uncertainty_method() -> None:
    payload = {
        "equations": ("x^2 - C",),
        "unknown_rows": ({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": True,
        "constants_rows": ({"name": "C", "value": "4.0(2)"},),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 80,
        "display_digits": 20,
        "uncertainty_options": {"method": "future_method"},
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options["method"] == "taylor"
    assert restored.uncertainty_options["taylor_order"] == 1


def test_execute_root_solving_job_payload_forwards_uncertainty_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=20,
        uncertainty_digits=3,
        uncertainty_options={"method": "monte_carlo", "monte_carlo_samples": 25, "monte_carlo_seed": "7"},
    )

    def fake_solve_root_batch(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(rows=(), warnings=(), headers=())

    def fake_render_root_batch_result(
        _batch: object,
        *,
        display_digits: int,
        uncertainty_digits: int,
        language: str,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        captured["display_digits"] = display_digits
        captured["uncertainty_digits"] = uncertainty_digits
        captured["language"] = language
        return "markdown", [], ["name"]

    monkeypatch.setattr(workers_core, "solve_root_batch", fake_solve_root_batch)
    monkeypatch.setattr(workers_core, "render_root_batch_result", fake_render_root_batch_result)

    payload = _execute_root_solving_job_payload(job)

    assert payload["kind"] == "root_solving"
    assert captured["uncertainty_options"] == {
        "method": "monte_carlo",
        "monte_carlo_samples": 25,
        "monte_carlo_seed": "7",
    }
    assert captured["display_digits"] == 20
    assert captured["uncertainty_digits"] == 3
    assert captured["language"] == "en"


def test_root_solving_legacy_known_rows_payload_migrates_to_data_rows() -> None:
    payload = {
        "equations": ("x**2 - A",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "known_rows": ({"name": "A", "value": "4.0(2)"},),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "precision": 16,
        "display_digits": 10,
    }

    job = _deserialize_root_solving_job(payload)

    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",),)
    assert job.scan_config == {}


def test_execute_root_solving_job_payload_returns_markdown_csv_and_log() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0000000000000000000000000001(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=20,
    )

    payload = _execute_root_solving_job_payload(job)

    assert payload["kind"] == "root_solving"
    markdown = payload["markdown"]
    assert isinstance(markdown, str)
    assert "| input_row_index | root_index | name | value | backend |" in markdown
    assert "| uncertainty |" not in markdown
    assert payload["csv_headers"] == [
        "input_row_index",
        "root_index",
        "name",
        "value",
        "uncertainty",
        "display_value",
        "backend",
        "mode",
        "residual_norm",
        "failure",
    ]
    csv_rows = cast(list[dict[str, str]], payload["csv_rows"])
    assert csv_rows[0]["name"] == "x"
    assert csv_rows[0]["uncertainty"]
    assert csv_rows[0]["display_value"]
    log = payload["log"]
    assert isinstance(log, str)
    assert "root solving completed" in log


def test_execute_root_solving_job_payload_skips_root_plot_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_render(*args: object, **kwargs: object) -> object:
        raise AssertionError("root plotting should not run")

    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fail_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=False,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload


def test_execute_root_solving_job_payload_returns_first_root_plot_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    png = b"\x89PNG\r\n\x1a\nroot"
    captured: dict[str, object] = {}

    def fake_render(batch: object, problem: object, *, budget: object = None) -> object:
        captured["batch"] = batch
        captured["problem"] = problem
        captured["budget"] = budget
        return SimpleNamespace(
            images=(SimpleNamespace(image_bytes=png, metadata={"row_index": 0}),),
            warnings=("plot warning",),
        )

    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fake_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert payload["plot_bytes"] == png
    assert "plot_images" not in payload
    assert "plot warning" in payload["warnings"]
    assert captured["budget"] is not None


def test_execute_root_solving_job_payload_returns_real_png_when_root_plots_enabled() -> None:
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    plot_bytes = payload["plot_bytes"]
    assert isinstance(plot_bytes, bytes)
    assert plot_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_execute_root_solving_job_payload_returns_real_png_for_two_dimensional_system_plot() -> None:
    job = RootSolvingJob(
        equations=("x + y - 3", "x - y - 1"),
        unknown_rows=(
            {"name": "x", "initial": "2", "lower": "0", "upper": "4"},
            {"name": "y", "initial": "1", "lower": "0", "upper": "4"},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    plot_bytes = payload["plot_bytes"]
    assert isinstance(plot_bytes, bytes)
    assert plot_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    warnings = cast(list[str], payload["warnings"])
    assert not any("System root plots require exactly two equations" in warning for warning in warnings)


def test_execute_root_solving_job_payload_warns_for_unsupported_system_plot_in_chinese() -> None:
    job = RootSolvingJob(
        equations=("x + y + z - 1", "x - y", "z - 1"),
        unknown_rows=(
            {"name": "x", "initial": "0.5", "lower": "0", "upper": "2"},
            {"name": "y", "initial": "0.5", "lower": "0", "upper": "2"},
            {"name": "z", "initial": "1", "lower": "0", "upper": "2"},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=16,
        display_digits=10,
        language="zh",
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload
    warnings = cast(list[str], payload["warnings"])
    assert any("方程组绘图需要正好两个方程和两个实数未知量" in warning for warning in warnings)


def test_execute_root_solving_job_payload_does_not_plot_failed_root_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_solve_root_batch(**_kwargs: object) -> object:
        return SimpleNamespace(
            rows=(SimpleNamespace(row_index=0, source_values={}, failure="no root", result=None, warnings=()),),
            warnings=(),
            headers=(),
        )

    def fake_render_root_batch_result(
        _batch: object,
        *,
        display_digits: int,
        uncertainty_digits: int,
        language: str,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        return "failed", [], ["name"]

    def fail_render(*args: object, **kwargs: object) -> object:
        raise AssertionError("root plotting should only run for successful root rows")

    monkeypatch.setattr(workers_core, "solve_root_batch", fake_solve_root_batch)
    monkeypatch.setattr(workers_core, "render_root_batch_result", fake_render_root_batch_result)
    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fail_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload


def test_execute_root_solving_job_payload_localizes_root_output_to_chinese() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=8,
        language="zh",
    )

    payload = _execute_root_solving_job_payload(job)

    markdown = cast(str, payload["markdown"])
    assert "| 输入行 | 根序号 | 名称 | 值 | 后端 |" in markdown
    assert "不确定度" not in markdown.split("\n", maxsplit=1)[0]
    assert "求根完成" in cast(str, payload["log"])
    assert payload["csv_headers"] == [
        "input_row_index",
        "root_index",
        "name",
        "value",
        "uncertainty",
        "display_value",
        "backend",
        "mode",
        "residual_norm",
        "failure",
    ]


def test_execute_root_solving_job_payload_preserves_original_data_cell_precision() -> None:
    original = "1.0000000000000000000000000000000000000000000000001"
    job = RootSolvingJob(
        equations=("x - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=((original,),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=80,
    )

    payload = _execute_root_solving_job_payload(job)

    csv_rows = cast(list[dict[str, str]], payload["csv_rows"])
    assert csv_rows[0]["A"] == original
    assert csv_rows[0]["value"].startswith(original)
    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert raw_rows[0]["input_A"] == original
    assert raw_rows[0]["value"].startswith(original)


def test_root_raw_rows_assign_default_input_index_for_no_data_multi_root_latex() -> None:
    job = RootSolvingJob(
        equations=("x^2 - 4",),
        unknown_rows=({"name": "x", "initial": "0", "lower": "-3", "upper": "3"},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scan_multiple",
        scan_config={"sample_count": 100, "max_roots": 5},
        precision=16,
        display_digits=10,
    )

    payload = _execute_root_solving_job_payload(job)

    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert len(raw_rows) == 2
    assert {row["input_row_index"] for row in raw_rows} == {"0"}
    assert [row["root_index"] for row in raw_rows] == ["0", "1"]


def test_root_solving_subprocess_uses_killable_runner_and_forwards_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = RootSolvingJob(
        equations=("x - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=12,
    )
    calls: dict[str, object] = {}
    expected: dict[str, object] = {
        "kind": "root_solving",
        "markdown": "ok",
        "csv_rows": [],
        "csv_headers": ["name", "value", "uncertainty", "backend", "mode", "residual_norm"],
        "log": "ok",
        "warnings": [],
    }

    class FakeRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, object]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, object]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return expected

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FakeRunner)

    result = _execute_root_solving_job_payload_subprocess(
        job,
        timeout_seconds=12.5,
        should_cancel=lambda: False,
    )

    assert result is expected
    assert isinstance(calls["config"], ParallelConfig)
    assert calls["target"] is workers_core._root_solving_job_entry
    assert calls["payload"] == _serialize_root_solving_job(job)
    assert calls["timeout_seconds"] == 12.5
    assert callable(calls["should_cancel"])


def test_root_solving_worker_emits_cancelled_when_subprocess_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    job = RootSolvingJob(
        equations=("x - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=12,
    )
    observed: dict[str, object] = {}

    def fake_subprocess(
        received_job: RootSolvingJob,
        *,
        timeout_seconds: float | None,
        should_cancel: Callable[[], bool] | None,
    ) -> dict[str, object]:
        observed["job"] = received_job
        observed["timeout_seconds"] = timeout_seconds
        observed["should_cancel"] = should_cancel
        if should_cancel and should_cancel():
            raise InterruptedError("root solving cancelled")
        raise AssertionError("expected cancellation")

    monkeypatch.setattr(workers_core, "_execute_root_solving_job_payload_subprocess", fake_subprocess)
    worker = RootSolvingWorker(job)
    worker.request_stop()

    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        worker.start()

    assert worker.wait(3000)
    assert observed["job"] is job
    assert observed["timeout_seconds"] == workers_core.ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS
    assert callable(observed["should_cancel"])


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
    spec = SimpleNamespace(
        implicit_diagnostics=SimpleNamespace(
            points_solved=7,
            root_fallbacks=2,
            max_iterations_used=5,
            max_residual="1.0e-42",
        )
    )
    calls: dict[str, object] = {}

    def fake_build_implicit_model_specification(
        received_definition: ImplicitModelDefinition,
    ) -> object:
        calls["definition"] = received_definition
        return spec

    def fake_fit_custom_model(
        received_spec: object,
        state: object,
        variable_data: dict[str, list[mp.mpf]],
        target_series: list[mp.mpf],
        **kwargs: object,
    ) -> FitResult:
        calls["spec"] = received_spec
        calls["free_params"] = tuple(state.free_params)
        calls["variable_data"] = variable_data
        calls["target_series"] = target_series
        calls["kwargs"] = kwargs
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
            details={},
        )

    monkeypatch.setattr(
        workers_core,
        "build_implicit_model_specification",
        fake_build_implicit_model_specification,
    )
    monkeypatch.setattr(workers_core, "can_fit_observed_implicit_variable", lambda _definition: False)
    monkeypatch.setattr(workers_core, "fit_custom_model", fake_fit_custom_model)

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

    assert calls["definition"] is definition
    assert calls["spec"] is spec
    assert calls["free_params"] == ("a", "b", "c")
    assert calls["variable_data"] == {"x": x_series}
    assert calls["target_series"] == y_series
    assert calls["kwargs"] == {
        "precision": 30,
        "weights": None,
        "data_sigmas": [None] * len(y_series),
    }
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


def test_self_consistent_fit_job_payload_is_spawn_picklable() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    assert restored.model_type == "self_consistent"
    assert restored.implicit_definition is not None
    assert restored.implicit_definition.equation == "a + b*x"
    assert restored.implicit_definition.solve_options.method == "root"
    assert restored.timeout_seconds == 10.0
    assert restored.parallel_config.process_start_method == "spawn"


def test_self_consistent_fit_job_serialization_preserves_uncertain_sigma_rows() -> None:
    job = _small_self_consistent_fit_job()
    job.sigma_rows[0] = (None, UncertainValue("204397210.721", "0.002", uncertainty_digits=1))

    payload = _serialize_fit_job(job)
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    entry = restored.sigma_rows[0][1]
    assert isinstance(entry, UncertainValue)
    assert entry.value == mp.mpf("204397210.721")
    assert entry.uncertainty == mp.mpf("0.002")
    assert entry.uncertainty_digits == 1


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("implicit_definition", "equation"), 123, "equation must be a string"),
        (("implicit_definition", "output_expression"), 123, "output_expression must be a string"),
        (("implicit_definition", "implicit_variable"), 123, "implicit_variable must be a string"),
        (("implicit_definition", "x_variables"), ["x", 1], "x_variables must be a list of strings"),
        (("implicit_definition", "parameters"), ["a", 1], "parameters must be a list of strings"),
        (("implicit_definition", "constants"), [], "constants must be an object"),
        (("implicit_definition", "constants"), {"C": 1}, "constants must map strings to strings"),
        (("implicit_definition", "solve_options"), [], "solve_options must be an object"),
        (("implicit_definition", "solve_options", "method"), 123, "method must be a string"),
        (("implicit_definition", "solve_options", "initial"), 123, "initial must be a string"),
        (("implicit_definition", "solve_options", "tolerance"), 123, "tolerance must be a string"),
    ],
)
def test_deserialize_fit_job_rejects_malformed_implicit_definition_fields(
    path: tuple[str, ...],
    value: object,
    match: str,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    target: dict[str, Any] = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=match):
        _deserialize_fit_job(payload)


def test_deserialize_fit_job_rejects_malformed_implicit_solve_options() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["implicit_definition"]["solve_options"] = "root"

    with pytest.raises(ValueError, match="solve_options must be an object"):
        _deserialize_fit_job(payload)


def test_deserialize_fit_job_rejects_unsupported_process_start_method() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["process_start_method"] = "definitely-not-a-start-method"

    with pytest.raises(ValueError, match="Unsupported process_start_method"):
        _deserialize_fit_job(payload)


@pytest.mark.parametrize("value", [[], ""])
def test_deserialize_fit_job_rejects_malformed_parallel_config(value: object) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"] = value

    with pytest.raises(ValueError, match="parallel_config must be an object"):
        _deserialize_fit_job(payload)


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
