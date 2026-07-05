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
        "run_button",
    ):
        assert getattr(window, name, None) is not None, name


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
        "workbench_latex_options_button",
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
    # (formula/variable/mode_stack), then output_setup_section + run_section.
    layout_names = [
        window.left_layout.itemAt(index).widget().objectName()
        for index in range(window.left_layout.count())
        if window.left_layout.itemAt(index).widget() is not None
    ]
    # input is first; output_setup + run are the last two (footer); mode_stack sits
    # between them. The mode selector card is gone (moved to the toolbar).
    assert layout_names[0] == "input_section"
    assert layout_names[-2:] == ["output_setup_section", "run_section"]
    assert "mode_section" not in layout_names
    assert "workbench_formula_panel" in layout_names
    input_idx = layout_names.index("input_section")
    stack_idx = layout_names.index("mode_stack")
    run_idx = layout_names.index("run_section")
    assert input_idx < stack_idx < run_idx, "order must be 输入 → 配置 → 运行"

    assert window.mode_stack.parentWidget() is window.workbench_workspace_content
    assert window.custom_params_table is not None
    assert window.custom_constants_editor is not None


def test_left_configuration_sections_are_visual_cards(qtbot: Any) -> None:
    window = _make_window(qtbot)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()

    # mode_section moved to the toolbar; the remaining left-rail sections stay cards.
    for section in (
        window.input_section,
        window.output_setup_section,
        window.run_section,
    ):
        assert section.property("datalab_config_card") is True
        assert "border-radius" in section.styleSheet()

    window.refresh_workbench_config_cards()

    assert window.input_section.property("datalab_config_card") is True
    assert "border-radius" in window.input_section.styleSheet()
    assert window.run_button.property("datalab_primary_run_button") is True
    assert window.run_button.property("datalab_run_state") == "run"
    assert 'QPushButton[datalab_primary_run_button="true"]' in window.run_section.styleSheet()
    # The mode selector now lives on the workbench toolbar (dedicated coverage in
    # test_desktop_mode_selector_on_toolbar.py), not as a left-rail card.
    from PySide6.QtWidgets import QComboBox

    assert window.mode_combo in window.workbench_bar.findChildren(QComboBox)
    # NOTE: mpmath_precision_spin moved OUT of the left rail into the 计算 toolbar panel
    # (collapsed by default), so it no longer has a laid-out rail-card position — that
    # assertion was removed with the options-panel migration.


def test_legacy_run_button_click_reaches_current_run_calculation(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _make_window(qtbot)
    calls: list[str] = []

    monkeypatch.setattr(window, "run_calculation", lambda: calls.append("run"))

    qtbot.mouseClick(window.run_button, Qt.MouseButton.LeftButton)

    assert calls == ["run"]


def test_workbench_status_labels_refresh_after_english_language_switch(qtbot: Any) -> None:
    window = _make_window(qtbot)

    window._workspace_dirty = False
    window._on_language_change(2)

    assert window.workspace_status_label.text() == "Saved"
    assert window.job_status_label.text() == "Ready"

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
    assert window.run_button.property("datalab_run_state") == "stop"
    assert window.run_button.styleSheet() == ""

    monkeypatch.setattr(window, "_has_running_worker", lambda: False)
    window._set_button_to_run_mode()

    assert window.job_status_label.text() == "Ready"
    assert window.run_button.property("datalab_run_state") == "run"
