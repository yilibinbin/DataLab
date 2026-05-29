from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
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
