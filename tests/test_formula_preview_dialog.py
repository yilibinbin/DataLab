from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_formula_preview_dialog_has_high_contrast_surface(qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle()
    assert "a*x+b" in dialog.expression_text.toPlainText()
    assert "#ffffff" in dialog.formula_surface.styleSheet().lower() or "background" in dialog.formula_surface.styleSheet().lower()


def test_implicit_panel_uses_preview_buttons_not_inline_labels(window):
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))

    assert hasattr(window, "implicit_equation_preview_button")
    assert hasattr(window, "implicit_output_preview_button")
    assert not hasattr(window, "implicit_equation_preview") or not window.implicit_equation_preview.isVisible()


def test_implicit_preview_buttons_open_dialog_with_current_formula(window, monkeypatch, qtbot):
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_variable_edit.setText("delta")
    window.implicit_equation_edit.setPlainText("d0 + d2/(n-delta)^2")
    window.implicit_output_edit.setPlainText("En + R/(n-delta)^2")
    captured = []

    def fake_open(parent, expression, lhs=None):
        captured.append((parent, expression, lhs))

    monkeypatch.setattr("app_desktop.panels.open_formula_preview_dialog", fake_open)

    qtbot.mouseClick(window.implicit_equation_preview_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.implicit_output_preview_button, Qt.MouseButton.LeftButton)

    assert captured == [
        (window, "d0 + d2/(n-delta)^2", "delta"),
        (window, "En + R/(n-delta)^2", "y"),
    ]
