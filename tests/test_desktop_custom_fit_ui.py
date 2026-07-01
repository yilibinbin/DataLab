from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from mpmath import mp

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _select_model(win, model_type: str) -> None:
    mode_index = win.mode_combo.findData("fitting")
    assert mode_index >= 0
    win.mode_combo.setCurrentIndex(mode_index)
    index = win.fit_model_combo.findData(model_type)
    assert index >= 0
    win.fit_model_combo.setCurrentIndex(index)


def _table_names(parameter_table) -> list[str]:
    return [row["name"] for row in parameter_table.rows()]


def test_custom_fit_detects_parameters_and_constants(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("A*x + B + K")
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    window.custom_param_refresh_btn.click()

    assert _table_names(window.custom_params_table) == ["A", "B"]


def test_content_driven_custom_constants_are_excluded_from_parameters(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("A*x + K")
    window.custom_constants_editor.setChecked(False)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    window.custom_param_refresh_btn.click()

    assert _table_names(window.custom_params_table) == ["A"]


def test_custom_fit_detects_sectioned_input_constants(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("A*x + K")
    window.manual_data_edit.setPlainText("[data]\nx y\n1 3\n\n[constants]\nK = 1\n")
    window._data_stack.setCurrentIndex(1)
    window.custom_constants_editor.set_rows([])

    window.custom_param_refresh_btn.click()

    assert _table_names(window.custom_params_table) == ["A"]
    assert window._collect_custom_constants() == {"K": "1"}


def test_desktop_comparison_mode_shows_explicit_candidates_editor(window) -> None:
    _select_model(window, "comparison")

    assert not window.fit_comparison_candidates_edit.isHidden()
    tooltip = window.fit_comparison_candidates_edit.toolTip().lower()
    assert "json" in tooltip
    assert "候选" in tooltip or "candidate" in tooltip
    assert not window.custom_params_table.isVisible()
    assert not window.implicit_model_widget.isVisible()
    assert not window.fit_expr_edit.isVisible()
    assert not window.add_variable_btn.isHidden()
    assert not window.remove_variable_btn.isHidden()


def test_fitting_visible_units_are_passed_to_core_request(window) -> None:
    _select_model(window, "custom")
    window.fit_expr_edit.setPlainText("a*x + b")
    window.fit_target_edit.setText("B")
    window.custom_params_table.set_rows(
        [
            {"name": "a", "initial": "1", "fixed": "", "lower": "", "upper": ""},
            {"name": "b", "initial": "0", "fixed": "", "lower": "", "upper": ""},
        ]
    )
    window.fit_units_enabled_checkbox.setChecked(True)
    window.fit_units_inputs_editor.set_rows([{"name": "A", "value": "s"}])
    window.fit_units_parameters_editor.set_rows([{"name": "a", "value": "m/s"}])
    window.fit_units_output_edit.setText("m")

    job = window._prepare_fit_job(
        (
            ["A", "B"],
            [(mp.mpf("1"), mp.mpf("2")), (mp.mpf("2"), mp.mpf("3"))],
            [(None, None), (None, None)],
        ),
        generate_latex=False,
        output_path="",
        verbose=False,
    )

    assert job.core_request is not None
    assert job.core_request.inputs["units"]["inputs"] == {"A": {"unit": "s"}}
    assert job.core_request.inputs["units"]["parameters"] == {"a": {"unit": "m/s"}}
    assert job.core_request.inputs["units"]["outputs"] == {"result": {"unit": "m"}}
