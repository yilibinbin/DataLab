from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

pytest.importorskip("pytestqt")


def _make_window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_shell_preserves_legacy_widget_attributes(qtbot: Any) -> None:
    window = _make_window(qtbot)

    for name in (
        "manual_box",
        "extrap_box",
        "error_box",
        "fit_box",
        "root_box",
        "stats_box",
        "options_box",
    ):
        assert getattr(window, name, None) is not None, name
    # run_button was removed in 4·4c (run is on the toolbar); it must NOT survive as a
    # compat attribute — the run/stop state machine drives the toolbar 运行/停止 pair.
    assert not hasattr(window, "run_button")


def test_shell_exposes_workbench_bar_controls(qtbot: Any) -> None:
    window = _make_window(qtbot)

    for name in (
        "workbench_bar",
        "new_workspace_button",
        "open_workspace_button",
        "save_workspace_button",
        "open_examples_button",
        "workbench_run_button",
        "workbench_stop_button",
        "workbench_compute_options_button",
        "docs_button",
        "check_updates_button",
        "workspace_status_label",
        "job_status_label",
    ):
        widget = getattr(window, name, None)
        assert widget is not None, name
        assert widget.objectName(), name


def test_shell_sections_are_visible_in_expected_order(qtbot: Any) -> None:
    window = _make_window(qtbot)

    assert not hasattr(window, "parameters_section")
    assert not hasattr(window, "parameters_section_layout")

    # Two-pane layout: the left config sections merged into the workspace pane. The
    # merged pane stacks (top→bottom): input_section, then the per-mode config
    # (formula/variable/mode_stack), then run_section (the empty output_setup_section is
    # no longer added).
    layout_names = [
        window.left_layout.itemAt(index).widget().objectName()
        for index in range(window.left_layout.count())
        if window.left_layout.itemAt(index).widget() is not None
    ]
    # input is first; mode_stack + per-mode config follow. The mode selector card, the
    # empty output_setup_section, AND the bottom run_section (开始执行 removed in 4·4c —
    # run is on the toolbar) are all gone from the layout.
    assert layout_names[0] == "input_section"
    assert "mode_section" not in layout_names
    assert "output_setup_section" not in layout_names
    assert "run_section" not in layout_names
    assert "workbench_formula_panel" in layout_names
    input_idx = layout_names.index("input_section")
    stack_idx = layout_names.index("mode_stack")
    assert input_idx < stack_idx, "order must be 输入 → 配置"

    assert window.mode_stack.parentWidget() is window.workbench_workspace_content
    assert window.custom_params_table is not None
    assert window.custom_constants_editor is not None


def test_left_configuration_sections_are_visual_cards(qtbot: Any) -> None:
    window = _make_window(qtbot)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()

    # mode_section moved to the toolbar; output_setup_section + run_section removed. Only
    # the input section remains a left-rail config card.
    for section in (window.input_section,):
        assert section.property("datalab_config_card") is True
        assert "border-radius" in section.styleSheet()

    window.refresh_workbench_config_cards()

    assert window.input_section.property("datalab_config_card") is True
    assert "border-radius" in window.input_section.styleSheet()
    # The bottom 开始执行 run_button was removed (4·4c) — run is on the toolbar.
    assert not hasattr(window, "run_button")
    # The mode selector now lives on the workbench toolbar (dedicated coverage in
    # test_desktop_mode_selector_on_toolbar.py), not as a left-rail card.
    from PySide6.QtWidgets import QComboBox

    assert window.mode_combo in window.workbench_bar.findChildren(QComboBox)
    # NOTE: mpmath_precision_spin moved OUT of the left rail into the 计算 toolbar panel
    # (collapsed by default), so it no longer has a laid-out rail-card position — that
    # assertion was removed with the options-panel migration.


def test_toolbar_run_button_reaches_current_run_calculation(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bottom 开始执行 button was removed (4·4c); the toolbar 运行 button runs now.
    window = _make_window(qtbot)
    calls: list[str] = []

    # The toolbar run button resolves run_extrapolation → run_calculation at click time
    # (workbench_toolbar._call_owner); the window exposes run_calculation.
    monkeypatch.setattr(window, "run_calculation", lambda *a, **k: calls.append("run"))

    qtbot.mouseClick(window.workbench_run_button, Qt.MouseButton.LeftButton)

    assert calls == ["run"]


def test_workbench_status_labels_refresh_after_english_language_switch(qtbot: Any) -> None:
    window = _make_window(qtbot)

    window._workspace_dirty = False
    window._on_language_change(2)

    assert window.workspace_status_label.text() == "Saved"
    # Rich status chip: no result yet → Waiting (was the old bare Ready).
    assert window.job_status_label.text() == "Waiting"

    window._workspace_dirty = True
    window._update_workspace_window_title()

    assert window.workspace_status_label.text() == "Unsaved"


def test_workbench_job_status_refreshes_on_run_stop_mode_methods(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _make_window(qtbot)
    window._on_language_change(2)

    monkeypatch.setattr(window, "_has_running_worker", lambda: False)
    window._set_button_to_stop_mode()

    assert window.job_status_label.text() == "Running"
    # Run-state now lives on _datalab_run_state and drives the toolbar 运行/停止 pair
    # (bottom 开始执行 removed in 4·4c): running → 运行 disabled, 停止 enabled.
    assert window._datalab_run_state == "stop"
    assert window.workbench_run_button.isEnabled() is False
    assert window.workbench_stop_button.isEnabled() is True

    monkeypatch.setattr(window, "_has_running_worker", lambda: False)
    window._set_button_to_run_mode()

    # No result → rich chip reads Waiting (was the old bare Ready).
    assert window.job_status_label.text() == "Waiting"
    assert window._datalab_run_state == "run"
    assert window.workbench_run_button.isEnabled() is True
    assert window.workbench_stop_button.isEnabled() is False
