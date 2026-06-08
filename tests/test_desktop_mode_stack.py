from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.resize(1440, 900)
    win.show()
    QApplication.processEvents()
    return win


def _set_combo_data(combo: Any, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0, value
    combo.setCurrentIndex(index)
    QApplication.processEvents()


def _refresh_mode_stack_width(window: Any) -> int:
    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
    return int(window.mode_stack.sizeHint().width())


def test_hidden_top_level_pages_do_not_control_left_width_until_current(window: Any) -> None:
    assert window.mode_stack.indexOf(window.extrap_box) == 0
    assert window.mode_stack.indexOf(window.error_box) == 1
    assert window.mode_stack.indexOf(window.fit_box) == 2
    assert window.mode_stack.indexOf(window.root_box) == 3
    assert window.mode_stack.indexOf(window.stats_box) == 4

    _set_combo_data(window.mode_combo, "extrapolation")
    baseline_width = _refresh_mode_stack_width(window)

    wide_root_child = QLabel("wide root draft")
    wide_root_child.setMinimumWidth(baseline_width + 240)
    window.root_box.layout().addWidget(wide_root_child)
    hidden_root_width = _refresh_mode_stack_width(window)

    _set_combo_data(window.mode_combo, "root_solving")
    current_root_width = _refresh_mode_stack_width(window)

    assert hidden_root_width == baseline_width
    assert current_root_width >= baseline_width + 200


def test_hidden_extrapolation_submethod_pages_do_not_control_left_width_until_current(window: Any) -> None:
    assert window.extrap_method_stack.indexOf(window.power_box) == 0
    assert window.extrap_method_stack.indexOf(window.levin_box) == 1
    assert window.extrap_method_stack.indexOf(window.richardson_box) == 2
    assert window.extrap_method_stack.indexOf(window.custom_formula_widget) == 3

    _set_combo_data(window.mode_combo, "extrapolation")
    _set_combo_data(window.method_combo, "power_law")
    baseline_width = _refresh_mode_stack_width(window)

    wide_custom_child = QLabel("wide custom draft")
    wide_custom_child.setMinimumWidth(baseline_width + 260)
    window.custom_formula_widget.layout().addWidget(wide_custom_child)
    hidden_custom_width = _refresh_mode_stack_width(window)

    _set_combo_data(window.method_combo, "custom")
    current_custom_width = _refresh_mode_stack_width(window)

    assert hidden_custom_width == baseline_width
    assert current_custom_width >= baseline_width + 220


@pytest.mark.parametrize("width", [1280, 1440, 1680])
def test_supported_widths_modes_and_submethods_have_no_left_horizontal_scrollbar(
    window: Any,
    width: int,
) -> None:
    window.resize(width, 900)
    QApplication.processEvents()

    mode_cases = [
        ("extrapolation", "power_law"),
        ("extrapolation", "richardson"),
        ("extrapolation", "shanks"),
        ("extrapolation", "levin_u"),
        ("extrapolation", "custom"),
        ("error", None),
        ("fitting", None),
        ("root_solving", None),
        ("statistics", None),
    ]

    for mode, method in mode_cases:
        _set_combo_data(window.mode_combo, mode)
        if method is not None:
            _set_combo_data(window.method_combo, method)
        window._refresh_main_splitter_left_min_width()
        window._main_splitter.setSizes([1, max(1, width - 321), 320])
        QApplication.processEvents()

        horizontal_bar = window._left_scroll.horizontalScrollBar()
        assert window._main_splitter.count() == 3
        assert len(window._main_splitter.sizes()) == 3
        assert horizontal_bar.maximum() == 0, (width, mode, method)


def test_drafts_survive_mode_and_submethod_switches(window: Any) -> None:
    _set_combo_data(window.mode_combo, "extrapolation")
    _set_combo_data(window.method_combo, "custom")
    window.custom_formula_edit.setPlainText("A + B + C")
    _set_combo_data(window.method_combo, "power_law")
    window.power_x_edits[0].setText("11")
    window.power_p_edit.setText("1.75")

    _set_combo_data(window.mode_combo, "root_solving")
    window.root_equations_edit.setPlainText("x^2 - A")
    _set_combo_data(window.mode_combo, "error")
    window.formula_edit.setPlainText("A/B")
    _set_combo_data(window.mode_combo, "statistics")
    window.stats_value_column_edit.setText("energy")

    _set_combo_data(window.mode_combo, "extrapolation")
    _set_combo_data(window.method_combo, "custom")
    assert window.custom_formula_edit.toPlainText() == "A + B + C"
    _set_combo_data(window.method_combo, "power_law")
    assert window.power_x_edits[0].text() == "11"
    assert window.power_p_edit.text() == "1.75"

    _set_combo_data(window.mode_combo, "root_solving")
    assert window.root_equations_edit.toPlainText() == "x^2 - A"
    _set_combo_data(window.mode_combo, "error")
    assert window.formula_edit.toPlainText() == "A/B"
    _set_combo_data(window.mode_combo, "statistics")
    assert window.stats_value_column_edit.text() == "energy"


def test_workspace_capture_restore_preserves_hidden_drafts(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    QApplication.instance() or QApplication([])
    source = ExtrapolationWindow()
    target = ExtrapolationWindow()
    qtbot.addWidget(source)
    qtbot.addWidget(target)

    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.method_combo, "custom")
    source.custom_formula_edit.setPlainText("custom hidden formula")
    source.power_x_edits[0].setText("13")
    source.power_p_edit.setText("2.5")
    source.formula_edit.setPlainText("hidden error formula")
    source.stats_value_column_edit.setText("weighted_value")
    source.root_equations_edit.setPlainText("x - ROOT")

    bundle = capture_workspace(source, title="hidden drafts")
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.mode_combo.currentData() == "fitting"
    assert target.method_combo.currentData() == "custom"
    assert target.custom_formula_edit.toPlainText() == "custom hidden formula"
    assert target.power_x_edits[0].text() == "13"
    assert target.power_p_edit.text() == "2.5"
    assert target.formula_edit.toPlainText() == "hidden error formula"
    assert target.stats_value_column_edit.text() == "weighted_value"
    assert target.root_equations_edit.toPlainText() == "x - ROOT"
