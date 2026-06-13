from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

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
