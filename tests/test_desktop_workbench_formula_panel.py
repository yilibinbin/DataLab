from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_formula_workspace_panel_mounts_existing_editors(qtbot: Any) -> None:
    window = _window(qtbot)
    panel = window.findChild(QWidget, "workbench_formula_panel")

    assert panel is not None
    assert window.workbench_formula_preview_label.parentWidget() is panel
    assert window.fit_expr_edit.parentWidget() is window.fit_box
    assert window.fit_formula_preview_button.parentWidget() is not None


def test_formula_workspace_has_single_persistent_preview_label(qtbot: Any) -> None:
    from app_desktop.formula_preview import FormulaPreviewLabel

    window = _window(qtbot)

    assert window.findChildren(FormulaPreviewLabel) == [window.workbench_formula_preview_label]


def test_formula_workspace_preview_uses_current_editor_text(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_expr_edit.setPlainText("A*x+B")
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_preview_tracks_last_edited_implicit_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    assert window._workbench_active_formula_attr == "implicit_output_edit"
    window.refresh_workbench_formula_panel()

    assert current_formula_mount(window).editor_attr == "implicit_output_edit"


def test_formula_workspace_ignores_hidden_programmatic_text_changes(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("A*x+B")
    QApplication.processEvents()

    assert window._workbench_active_formula_attr == "fit_expr_edit"

    window.implicit_output_edit.setPlainText("u + x")
    QApplication.processEvents()

    assert window._workbench_active_formula_attr == "fit_expr_edit"
    assert current_formula_mount(window).editor_attr == "fit_expr_edit"


def test_formula_workspace_preview_prefers_focused_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_equation_edit.setPlainText("u - x")
    window.implicit_equation_edit.setFocus()
    QApplication.processEvents()

    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_focus_filter_updates_active_formula(qtbot: Any) -> None:
    from PySide6.QtCore import QEvent

    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    handled = window._workbench_formula_focus_filter.eventFilter(
        window.implicit_equation_edit,
        QEvent(QEvent.Type.FocusIn),
    )

    assert handled is False
    assert window._workbench_active_formula_attr == "implicit_equation_edit"
    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_installs_editor_local_focus_filter(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window._workbench_formula_focus_filter is not None
    assert not hasattr(window, "_workbench_formula_focus_disconnect")
    assert len(window._workbench_formula_text_changed_callbacks) == 6


def test_formula_workspace_title_identifies_active_formula(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    assert window.workbench_formula_panel_title.text() == "Output expression:"


def test_formula_workspace_mode_switch_uses_bound_schema_title_without_manual_refresh(qtbot: Any) -> None:
    window = _window(qtbot)
    window._apply_language("en")
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert window.workbench_formula_panel_title.text() == "Model expression:"


def test_formula_workspace_title_does_not_expose_raw_schema_key_when_label_missing(qtbot: Any) -> None:
    from app_desktop.ui_schema_binder import SCHEMA_LABEL_EN_PROPERTY, SCHEMA_LABEL_ZH_PROPERTY

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_ZH_PROPERTY, "")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_EN_PROPERTY, "")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    title = window.workbench_formula_panel_title.text()
    assert "fitting.implicit.output_expression" not in title
    assert title == "Output Expression:"


def test_formula_panel_hidden_when_mode_has_no_formulas(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()


def test_formula_panel_tracks_extrapolation_method_visibility(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    window.method_combo.setCurrentIndex(window.method_combo.findData("power_law"))
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()

    window.method_combo.setCurrentIndex(window.method_combo.findData("custom"))
    QApplication.processEvents()

    assert window.workbench_formula_panel.isVisible()
    assert window.workbench_formula_panel_title.text() == "自定义公式："


def test_formula_panel_hidden_when_fitting_submode_has_no_visible_formula(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    assert window.workbench_formula_panel.isVisible()

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("polynomial"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()


def test_formula_workspace_refreshes_on_fitting_submode_visibility_change(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_formula_panel", refresh)

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()

    assert calls >= 1
