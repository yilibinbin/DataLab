from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _combo_data(combo: Any) -> list[object]:
    return [combo.itemData(index) for index in range(combo.count())]


def test_mode_combo_contains_root_solving(window: Any) -> None:
    assert "root_solving" in _combo_data(window.mode_combo)
    index = window.mode_combo.findData("root_solving")
    assert index >= 0

    window._apply_language("zh")
    assert window.mode_combo.itemText(window.mode_combo.findData("root_solving")) == "求根"
    window._apply_language("en")
    assert window.mode_combo.itemText(window.mode_combo.findData("root_solving")) == "Root solving"


def test_root_solving_page_has_required_widgets(window: Any) -> None:
    required = [
        "root_equations_edit",
        "root_formula_preview_button",
        "root_mode_combo",
        "root_unknowns_table",
        "root_add_unknown_button",
        "root_remove_unknown_button",
        "root_detect_unknowns_button",
        "root_constants_editor",
    ]
    for name in required:
        assert hasattr(window, name), name

    assert _combo_data(window.root_mode_combo) == ["auto", "scalar", "scan_multiple", "polynomial", "system"]
    assert [
        window.root_unknowns_table.table_view.horizontalHeaderItem(index).text()
        for index in range(window.root_unknowns_table.table_view.columnCount())
    ] == ["Name", "Initial", "Lower", "Upper"]
    assert window.root_constants_editor.numeric_mode() == "uncertainty"
    assert isinstance(window.root_formula_preview_button, QPushButton)


def test_root_solving_page_has_no_known_values_table(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))

    assert not hasattr(window, "root_known_values_table")
    assert not hasattr(window, "root_add_known_button")
    assert not hasattr(window, "root_remove_known_button")


def test_root_detect_unknowns_populates_table_from_expression_excluding_data_and_constants(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A - C")
    window.root_unknowns_table.set_rows([])
    window.root_constants_editor.set_rows([{"name": "C", "value": "1"}])
    window.root_constants_editor.setChecked(True)
    window.manual_data_edit.setPlainText("A\n4.0(2)")
    window._data_stack.setCurrentIndex(1)

    window.root_detect_unknowns_button.click()

    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_root_solving_job_uses_active_data_source_and_preserves_raw_cells(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.manual_data_edit.setPlainText("A\n4.0(2)\n9.00(3)")
    window._data_stack.setCurrentIndex(1)

    job = window._build_root_solving_job(data_path=None, manual_content=window.manual_data_edit.toPlainText())

    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",), ("9.00(3)",))
    assert job.mode == "scalar"


def test_root_solving_controls_mark_workspace_dirty(window: Any) -> None:
    window._workspace_dirty = False
    window.root_equations_edit.setPlainText("x - 1")
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_unknowns_table.add_row({"name": "x", "initial": "1"})
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_constants_editor.set_rows([{"name": "A", "value": "1.0"}])
    QApplication.processEvents()
    assert window._workspace_dirty is True


def test_root_solving_page_has_no_precision_or_backend_toggle(window: Any) -> None:
    forbidden = [
        "root_precision_spin",
        "root_mpmath_precision_spin",
        "root_backend_combo",
        "root_solver_backend_combo",
        "root_backend_toggle",
    ]

    for name in forbidden:
        assert not hasattr(window, name), name


def test_root_page_visible_only_in_root_mode(window: Any, qtbot: Any) -> None:
    window.show()
    qtbot.waitExposed(window)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.root_box.isVisible()
    assert not window.fit_box.isVisible()
    assert not window.stats_box.isVisible()
    assert not window.error_box.isVisible()
    assert not window.extrap_box.isVisible()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert not window.root_box.isVisible()
    assert window.fit_box.isVisible()


def test_root_formula_preview_uses_f_left_hand_side(window: Any, monkeypatch: pytest.MonkeyPatch, qtbot: Any) -> None:
    captured = []

    def fake_open(parent: Any, expression: str, lhs: str | None = None) -> None:
        captured.append((parent, expression, lhs))

    monkeypatch.setattr("app_desktop.panels.open_formula_preview_dialog", fake_open)
    window.root_equations_edit.setPlainText("x^2 - C\nx + y - 3")

    qtbot.mouseClick(window.root_formula_preview_button, Qt.MouseButton.LeftButton)

    assert captured == [(window, "x^2 - C\nx + y - 3", "F_i")]


def test_custom_and_root_detected_rows_use_same_helper(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.detected_rows_table import DetectedRowsController

    calls = []
    original = DetectedRowsController.set_detected_names

    def spy(self: Any, names: Any, *, keep_orphans: bool = True) -> set[str]:
        calls.append((self, tuple(names), keep_orphans))
        return original(self, names, keep_orphans=keep_orphans)

    monkeypatch.setattr(DetectedRowsController, "set_detected_names", spy)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("A*x + B")
    window.custom_param_refresh_btn.click()
    window.root_unknowns_table.set_detected_names(["x"], keep_orphans=False)

    assert calls == [
        (window.custom_params_table.detected_rows_controller, ("A", "B"), False),
        (window.root_unknowns_table.detected_rows_controller, ("x",), False),
    ]
    assert window.custom_params_table.rows() == [
        {"name": "A", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
    ]
    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_edited_detected_parameter_row_becomes_manual_before_refresh(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.custom_params_table.set_detected_names(["A"], keep_orphans=False)

    item = window.custom_params_table.item(0, 0)
    assert item is not None
    item.setText("manual")
    window.custom_params_table.set_detected_names(["B"], keep_orphans=False)

    assert window.custom_params_table.rows() == [
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "manual", "initial": "", "fixed": "", "min": "", "max": ""},
    ]


def test_edited_detected_root_unknown_row_becomes_manual_before_refresh(window: Any) -> None:
    window.root_unknowns_table.set_detected_names(["x"], keep_orphans=False)

    item = window.root_unknowns_table.table_view.item(0, 0)
    assert item is not None
    item.setText("manual")
    window.root_unknowns_table.set_detected_names(["y"], keep_orphans=False)

    assert window.root_unknowns_table.rows() == [
        {"name": "y", "initial": "", "lower": "", "upper": "", "source": "detected"},
        {"name": "manual", "initial": "", "lower": "", "upper": ""},
    ]


def test_root_solving_run_uses_background_worker(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import RootSolvingJob

    class _Signal:
        def connect(self, callback: object) -> None:
            captured.setdefault("connections", []).append(callback)

        def disconnect(self, *_args: object) -> None:
            return

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

        def request_stop(self) -> None:
            captured["stopped"] = True

    captured: dict[str, Any] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "RootSolvingWorker", _DummyRootSolvingWorker)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x^2 - C")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "2", "lower": "", "upper": ""}])
    window.root_constants_editor.set_rows([{"name": "C", "value": "4.00000000000000000001(2)"}])
    window.root_constants_editor.setChecked(True)
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.manual_data_edit.setPlainText("A\n4.0(2)")
    window._data_stack.setCurrentIndex(1)

    window.run_calculation()

    job = captured["job"]
    assert isinstance(job, RootSolvingJob)
    assert captured["started"] is True
    assert job.equations == ("x^2 - C",)
    assert job.unknown_rows == ({"name": "x", "initial": "2", "lower": "", "upper": ""},)
    assert job.constants_enabled is True
    assert job.constants_rows == ({"name": "C", "value": "4.00000000000000000001(2)"},)
    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",),)
    assert job.mode == "scalar"
