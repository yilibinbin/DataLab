from __future__ import annotations

import time
import os
from pathlib import Path

import mpmath as mp
from PySide6.QtCore import QTimer

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import FitJob
from app_desktop.workers_qt import FitWorker
from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions


def _small_self_consistent_fit_job(*, timeout_seconds: float | None = 10.0) -> FitJob:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("1") + mp.mpf("2") * x for x in x_series]
    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]
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
        precision=50,
        weighted=False,
        label="small-self-consistent",
        implicit_definition=definition,
        timeout_seconds=timeout_seconds,
    )


def _slow_fit_job_subprocess_entry(job_payload) -> dict[str, object]:
    marker = os.environ.get("DATALAB_TEST_SLOW_FIT_MARKER")
    if marker:
        Path(marker).write_text("started", encoding="utf-8")
    time.sleep(30)
    return {"error": "slow entry unexpectedly completed"}


def test_fit_worker_stop_cancels_self_consistent_subprocess(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    marker = tmp_path / "slow-child-started.txt"
    monkeypatch.setenv("DATALAB_TEST_SLOW_FIT_MARKER", str(marker))
    monkeypatch.setattr(workers_core, "_fit_job_subprocess_entry", _slow_fit_job_subprocess_entry)
    worker = FitWorker(_small_self_consistent_fit_job(timeout_seconds=30.0))

    worker.start()
    qtbot.waitUntil(marker.exists, timeout=5000)

    with qtbot.waitSignal(worker.cancelled, timeout=5000):
        QTimer.singleShot(0, worker.request_stop)

    assert marker.read_text(encoding="utf-8") == "started"
    assert worker.wait(3000)
