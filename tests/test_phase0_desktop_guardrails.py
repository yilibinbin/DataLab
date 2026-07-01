from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from mpmath import mp
from PySide6.QtWidgets import QApplication

from shared.parallel_config import NestedParallelPolicy, ParallelMode


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _set_combo_data(combo: Any, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


class _RunningWorker:
    def __init__(self) -> None:
        self.stop_requests = 0
        self.running = True

    def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
        return self.running

    def request_stop(self) -> None:
        self.stop_requests += 1
        self.running = False

    def wait(self, _timeout: int | None = None) -> bool:
        return True

    def terminate(self) -> None:
        self.running = False

    def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
        return None


class _RunningLatexWorker:
    def __init__(self) -> None:
        self.cancel_requests = 0
        self.running = True

    def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
        return self.running

    def request_cancel(self) -> None:
        self.cancel_requests += 1
        self.running = False

    def wait(self, _timeout: int | None = None) -> bool:
        return True

    def terminate(self) -> None:
        self.running = False

    def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
        return None


def test_run_while_busy_requests_cooperative_stop_and_skips_input_collection(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calc_worker = _RunningWorker()
    fit_worker = _RunningWorker()
    root_worker = _RunningWorker()
    latex_worker = _RunningLatexWorker()
    window._calc_worker = calc_worker
    window._fit_worker = fit_worker
    window._root_worker = root_worker
    window._latex_compile_worker = latex_worker

    def fail_if_inputs_are_collected() -> tuple[None, str]:
        raise AssertionError("run_calculation collected inputs while worker was running")

    monkeypatch.setattr(window, "_active_data_source", fail_if_inputs_are_collected)

    window.run_calculation()

    assert calc_worker.stop_requests == 1
    assert fit_worker.stop_requests == 1
    assert root_worker.stop_requests == 1
    assert latex_worker.cancel_requests == 1


def test_run_when_idle_collects_inputs_and_starts_worker(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import CalcJob

    captured: dict[str, Any] = {}

    class _DummyCalcWorker:
        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job
            self.finished_ok = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()
            self.cancelled = _Signal()
            self.log_ready = _Signal()

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def wait(self, _timeout: int | None = None) -> bool:
            return True

        def terminate(self) -> None:
            return None

        def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
            return None

    class _Signal:
        def connect(self, _slot: Any) -> None:
            pass

    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)
    _set_combo_data(window.mode_combo, "statistics")
    window.manual_data_edit.setPlainText("A\n1\n2\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_value_column_edit.setText("A")

    window.run_calculation()

    assert captured["started"] is True
    assert isinstance(captured["job"], CalcJob)
    assert captured["job"].mode == "statistics"
    headers, rows, sigma_rows = captured["job"].dataset
    assert headers == ["A"]
    assert [str(row[0]) for row in rows] == ["1.0", "2.0"]
    assert sigma_rows == [(None,), (None,)]
    assert captured["job"].core_request is not None
    assert captured["job"].core_request.inputs["values"] == ["1.0", "2.0"]
    assert captured["job"].core_request.inputs["sigmas"] == [None, None]
    assert captured["job"].core_request.inputs["stats_mode"] == "mean"
    assert captured["job"].core_request.inputs["source_row_ids"] == ["1", "2"]


def test_statistics_interactive_display_keeps_current_legacy_statistics_projection(
    window: Any,
) -> None:
    window._apply_language("en")
    stats_result = {
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (σ=0 anchor)",
        "dropped": 1,
        "effective_n": mp.mpf("1"),
        "zero_sigma_anchor": True,
        "warnings": ["Detected σ=0; treated as infinite weight."],
    }

    text, csv_rows = window._format_statistics_display(stats_result, "A", 2)

    metrics = {str(row["metric"]): row for row in csv_rows}
    assert "Weighted effective n_eff = 1.0" in text
    assert "Min = 1.25" in text
    assert "Max = 2.5" in text
    assert metrics["rows"]["value"] == 2
    assert str(metrics["min"]["value"]).startswith("1.25")
    assert str(metrics["max"]["value"]).startswith("2.5")
    assert str(metrics["effective_n"]["value"]).startswith("1.0")
    assert metrics["dropped"]["value"] == 1
    assert metrics["zero_sigma_anchor"]["value"] == "True"


def test_statistics_direct_mode_attaches_source_row_ids(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Statistics now compute through the core session service, not a module-level
    # compute_statistics(). Run the real path and spy on the display seam to
    # confirm the parsed values/sigmas and that source_row_ids are attached to
    # the result carried into the UI.
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n1\n2\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_value_column_edit.setText("A")
    captured: dict[str, object] = {}

    def fake_display_statistics_result(
        result: dict[str, object],
        value_col: str,
        row_count: int,
        *,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None],
        render_plots: bool = False,
        units: object = None,
    ) -> None:
        captured["result"] = result
        captured["values"] = [str(value) for value in values]
        captured["sigmas"] = list(sigmas)

    monkeypatch.setattr(window, "_display_statistics_result", fake_display_statistics_result)

    window._run_statistics_mode(False, "")

    assert captured["values"] == ["1.0", "2.0"]
    assert captured["sigmas"] == [None, None]
    result = captured["result"]
    assert isinstance(result, dict)
    assert result["source_row_ids"] == ("1", "2")


def test_statistics_display_result_routes_current_csv_plot_and_snapshot(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window._apply_language("en")
    stats_result = {
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (σ=0 anchor)",
        "dropped": 1,
        "effective_n": mp.mpf("1"),
        "zero_sigma_anchor": True,
        "warnings": ["Detected σ=0; treated as infinite weight."],
    }
    values = [mp.mpf("1.25"), mp.mpf("2.5")]
    sigmas = [mp.mpf("0"), mp.mpf("0.1")]
    captured: dict[str, object] = {}

    def fake_render_statistics_plots(
        plot_values: list[mp.mpf],
        plot_sigmas: list[mp.mpf | None] | None,
        plot_result: dict[str, object],
        batch_idx: int | None = None,
        value_unit: str | None = None,
    ) -> list[bytes]:
        captured["plot_values"] = list(plot_values)
        captured["plot_sigmas"] = list(plot_sigmas or [])
        captured["plot_result"] = plot_result
        captured["plot_batch_idx"] = batch_idx
        captured["plot_value_unit"] = value_unit
        return [b"\x89PNG\r\n\x1a\nstats-1", b"\x89PNG\r\n\x1a\nstats-2"]

    def fake_save_batch_figure(plot_bytes: bytes, _label: str, idx: int, *, prefix: str) -> Path:
        captured.setdefault("saved_plots", []).append((plot_bytes, idx, prefix))
        return Path(f"/tmp/datalab-p0-1-{prefix}.png")

    def fake_set_image_list(mode: str, paths: list[Path]) -> None:
        captured["image_list"] = (mode, paths)

    def fake_remember_last_result(kind: str, payload: dict[str, object]) -> None:
        captured["last_result"] = (kind, payload)

    monkeypatch.setattr(window, "_render_statistics_plots", fake_render_statistics_plots)
    monkeypatch.setattr(window, "_save_batch_figure", fake_save_batch_figure)
    monkeypatch.setattr(window, "_set_image_list", fake_set_image_list)
    monkeypatch.setattr(window, "_remember_last_result", fake_remember_last_result)

    window._display_statistics_result(
        stats_result,
        "A",
        2,
        values=values,
        sigmas=sigmas,
        render_plots=True,
    )

    assert window._csv_headers == ["batch", "metric", "value", "uncertainty"]
    metrics = {str(row["metric"]): row for row in window._csv_rows}
    assert metrics["min"]["value"].startswith("1.25")
    assert metrics["max"]["value"].startswith("2.5")
    assert metrics["zero_sigma_anchor"]["value"] == "True"
    assert captured["plot_values"] == values
    assert captured["plot_sigmas"] == sigmas
    assert captured["plot_result"] is stats_result
    assert captured["plot_batch_idx"] is None
    assert captured["saved_plots"] == [
        (b"\x89PNG\r\n\x1a\nstats-1", 1, "stats1"),
        (b"\x89PNG\r\n\x1a\nstats-2", 1, "stats2"),
    ]
    assert captured["image_list"] == (
        "stats",
        [Path("/tmp/datalab-p0-1-stats1.png"), Path("/tmp/datalab-p0-1-stats2.png")],
    )
    assert captured["last_result"] == (
        "statistics_single",
        {"result": stats_result, "value_col": "A", "n": 2},
    )

    window._display_statistics_result(
        stats_result,
        "A",
        2,
        values=values,
        sigmas=sigmas,
        render_plots=False,
    )

    assert captured["last_result"] == (
        "statistics_single",
        {"result": stats_result, "value_col": "A", "n": 2},
    )


def test_statistics_render_plot_returns_png_for_current_statistics_result(
    window: Any,
) -> None:
    pytest.importorskip("matplotlib")
    window._apply_language("en")

    png = window._render_statistics_plot(
        [mp.mpf("1.25"), mp.mpf("2.5")],
        [mp.mpf("0.1"), None],
        {
            "mean": mp.mpf("1.875"),
            "std_mean": mp.mpf("0.625"),
            "std": mp.mpf("0.883883476"),
            "v_min": mp.mpf("1.25"),
            "v_max": mp.mpf("2.5"),
            "method_label": "Arithmetic mean (sample)",
        },
        batch_idx=1,
    )

    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_render_plot_routes_shared_spec_with_direct_labels(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\ndesktop"

    monkeypatch.setattr(plotting, "render_statistics_plot_from_spec", fake_render)
    window._apply_language("en")

    png = window._render_statistics_plot(
        [mp.mpf("1.25"), mp.mpf("2.5")],
        [mp.mpf("0.1"), None],
        {"mean": mp.mpf("1.875"), "std_mean": mp.mpf("0.625")},
        batch_idx=2,
    )

    assert png == b"\x89PNG\r\n\x1a\ndesktop"
    spec = captured["spec"]
    assert spec.values == (mp.mpf("1.25"), mp.mpf("2.5"))
    assert spec.labels.title == "Statistics"
    assert spec.labels.mean_band == "Mean ± SE"
    assert spec.batch_suffix == " #2"


def test_statistics_core_projection_failure_does_not_block_legacy_worker(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import CalcJob

    captured: dict[str, Any] = {}

    class _Signal:
        def connect(self, _slot: Any) -> None:
            pass

    class _DummyCalcWorker:
        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job
            self.finished_ok = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()
            self.cancelled = _Signal()
            self.log_ready = _Signal()

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def wait(self, _timeout: int | None = None) -> bool:
            return True

        def terminate(self) -> None:
            return None

        def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
            return None

    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)
    _set_combo_data(window.mode_combo, "statistics")
    window.manual_data_edit.setPlainText("A\n1\n2\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_value_column_edit.setText("missing")

    window.run_calculation()

    assert captured["started"] is True
    assert isinstance(captured["job"], CalcJob)
    assert captured["job"].stats_value_col == "missing"
    assert captured["job"].core_request is None


def test_run_when_idle_starts_root_solving_worker(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import RootSolvingJob

    captured: dict[str, Any] = {}

    class _Signal:
        def connect(self, _slot: Any) -> None:
            pass

    class _DummyRootSolvingWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: RootSolvingJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def wait(self, _timeout: int | None = None) -> bool:
            return True

        def terminate(self) -> None:
            return None

        def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
            return None

    monkeypatch.setattr(window_extrapolation_mixin, "RootSolvingWorker", _DummyRootSolvingWorker)
    _set_combo_data(window.mode_combo, "root_solving")
    _set_combo_data(window.root_mode_combo, "scalar")
    window.root_equations_edit.setPlainText("x^2 - C")
    window.root_unknowns_table.set_rows(
        [{"name": "x", "initial": "2.0", "lower": "", "upper": ""}]
    )
    window.root_constants_editor.setChecked(True)
    window.root_constants_editor.set_rows([{"name": "C", "value": "4.00000000000000000001(2)"}])
    window.manual_data_edit.setPlainText("A\n4.0(2)\n")
    window._data_stack.setCurrentIndex(1)

    window.run_calculation()

    assert captured["started"] is True
    assert isinstance(captured["job"], RootSolvingJob)
    assert captured["job"].equations == ("x^2 - C",)
    assert captured["job"].unknown_rows == (
        {"name": "x", "initial": "2.0", "lower": "", "upper": ""},
    )


def test_root_job_construction_keeps_compute_payload_strings_and_parallel_config(
    window: Any,
) -> None:
    _set_combo_data(window.mode_combo, "root_solving")
    _set_combo_data(window.root_mode_combo, "scalar")
    _set_combo_data(window.parallel_mode_combo, ParallelMode.PROCESS.value)
    _set_combo_data(window.parallel_nested_policy_combo, NestedParallelPolicy.ALLOW.value)
    window.parallel_max_workers_spin.setValue(3)
    window.parallel_reserve_cores_spin.setValue(2)
    window.mpmath_precision_spin.setValue(64)
    window.display_digits_spin.setValue(18)
    window.uncertainty_digits_spin.setValue(2)
    window.root_equations_edit.setPlainText("x^2 - A")
    window.root_unknowns_table.set_rows(
        [{"name": "x", "initial": "1.00000000000000000001", "lower": "", "upper": ""}]
    )
    window.root_constants_editor.setChecked(True)
    window.root_constants_editor.set_rows(
        [{"name": "A", "value": "2.00000000000000000003(4)"}]
    )

    job = window._build_root_solving_job(
        manual_content="A\n2.00000000000000000003(4)\n",
    )

    from datalab_core.jobs import JobMode

    assert job.equations == ("x^2 - A",)
    assert job.unknown_rows == (
        {"name": "x", "initial": "1.00000000000000000001", "lower": "", "upper": ""},
    )
    assert job.data_headers == ("A",)
    assert job.data_rows == (("2.00000000000000000003(4)",),)
    assert job.constants_enabled is True
    assert job.constants_rows == ({"name": "A", "value": "2.00000000000000000003(4)"},)
    assert job.precision == 64
    assert job.display_digits == 18
    assert job.uncertainty_digits == 2
    assert job.parallel_config.mode == ParallelMode.PROCESS
    assert job.parallel_config.max_workers == 3
    assert job.parallel_config.reserve_cores == 2
    assert job.parallel_config.nested_policy == NestedParallelPolicy.ALLOW
    assert job.core_request is not None
    assert job.core_request.mode is JobMode.ROOT_SOLVING
    assert job.core_request.inputs["equations"] == ["x^2 - A"]
    assert job.core_request.inputs["unknown_rows"] == [
        {"name": "x", "initial": "1.00000000000000000001", "lower": "", "upper": "", "source": "manual"}
    ]
    assert job.core_request.inputs["data_headers"] == ["A"]
    assert job.core_request.inputs["data_rows"] == [["2.00000000000000000003(4)"]]
    assert job.core_request.inputs["constants_enabled"] is True
    assert job.core_request.inputs["constants_rows"] == [{"name": "A", "value": "2.00000000000000000003(4)"}]
    assert job.core_request.options.precision_digits == 64
    assert job.core_request.options.uncertainty_digits == 2
    assert job.core_request.options.parallel["mode"] == "process"
    assert job.core_request.options.parallel["max_workers"] == 3
    assert job.core_request.options.parallel["reserve_cores"] == 2
    assert job.core_request.options.parallel["nested_policy"] == "allow"


def _root_workspace() -> dict[str, Any]:
    return {
        "current_mode": "root_solving",
        "ui": {"main_tab": "results", "splitter": [300, 700]},
        "data": {
            "source_kind": "manual_table",
            "decoded_text": "A\n2.0\n",
            "canonical_table": {"headers": ["A"], "rows": [["2.0"]]},
        },
        "constants": {"enabled": False},
        "config": {
            "common": {"mpmath_precision": 64, "display_digits": 10},
            "root_solving": {"equations": ["x^2 - A"], "mode": "scalar"},
        },
        "result_snapshot": {
            "present": True,
            "markdown": "old result",
            "result_of_hash": "sha256:old",
        },
    }


def test_workspace_hash_is_stable_for_ui_only_changes() -> None:
    from shared.workspace_schema import compute_workspace_hash

    base_workspace = _root_workspace()
    ui_changed = {
        **base_workspace,
        "ui": {"main_tab": "logs", "splitter": [400, 600]},
    }

    assert compute_workspace_hash(base_workspace) == compute_workspace_hash(ui_changed)


def test_workspace_hash_is_stable_for_result_snapshot_changes() -> None:
    from shared.workspace_schema import compute_workspace_hash

    base_workspace = _root_workspace()
    result_changed = {
        **base_workspace,
        "result_snapshot": {
            "present": True,
            "markdown": "new result",
            "result_of_hash": "sha256:new",
        },
    }

    assert compute_workspace_hash(base_workspace) == compute_workspace_hash(result_changed)


def test_workspace_hash_changes_for_compute_data_config_and_constants() -> None:
    from shared.workspace_schema import compute_workspace_hash

    base_workspace = _root_workspace()
    data_changed = {
        **base_workspace,
        "data": {
            "source_kind": "manual_table",
            "decoded_text": "A\n3.0\n",
            "canonical_table": {"headers": ["A"], "rows": [["3.0"]]},
        },
    }
    equation_changed = {
        **base_workspace,
        "config": {
            "common": {"mpmath_precision": 64, "display_digits": 10},
            "root_solving": {"equations": ["x^3 - A"], "mode": "scalar"},
        },
    }
    constants_changed = {
        **base_workspace,
        "constants": {
            "enabled": True,
            "canonical_table": {"headers": ["name", "value"], "rows": [["C", "1.0"]]},
        },
    }

    # Data and constants changes are field-presence guards; the nested
    # root-solving equation change catches accidental narrowing to common config.
    assert compute_workspace_hash(base_workspace) != compute_workspace_hash(data_changed)
    assert compute_workspace_hash(base_workspace) != compute_workspace_hash(equation_changed)
    assert compute_workspace_hash(base_workspace) != compute_workspace_hash(constants_changed)
