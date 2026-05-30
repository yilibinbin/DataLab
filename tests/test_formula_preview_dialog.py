from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _contrast_ratio(foreground: QColor, background: QColor) -> float:
    def channel(value: int) -> float:
        normalized = value / 255
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    def luminance(color: QColor) -> float:
        return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())

    first = luminance(foreground)
    second = luminance(background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _style_color(style: str, property_name: str) -> QColor:
    for declaration in style.split(";"):
        name, separator, value = declaration.partition(":")
        if separator and name.strip().lower() == property_name:
            color = QColor(value.strip())
            assert color.isValid(), value.strip()
            return color
    raise AssertionError(f"{property_name} not found in stylesheet: {style}")


def _has_dark_rendered_pixels(image, *, threshold: int = 96) -> bool:
    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 0 and max(pixel.red(), pixel.green(), pixel.blue()) <= threshold:
                return True
    return False


def test_formula_preview_dialog_has_high_contrast_surface(qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle()
    assert "a*x+b" in dialog.expression_text.toPlainText()
    assert "#ffffff" in dialog.formula_surface.styleSheet().lower() or "background" in dialog.formula_surface.styleSheet().lower()


def test_formula_preview_dialog_uses_palette_independent_high_contrast(qtbot):
    pytest.importorskip("matplotlib")

    from app_desktop.formula_preview import FormulaPreviewDialog

    app = QApplication.instance() or QApplication([])
    original = app.palette()
    dark = QPalette(original)
    dark.setColor(QPalette.ColorRole.Window, QColor("#111111"))
    dark.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
    dark.setColor(QPalette.ColorRole.Base, QColor("#111111"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#111111"))
    app.setPalette(dark)
    try:
        dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
        qtbot.addWidget(dialog)
    finally:
        app.setPalette(original)

    surface_style = dialog.formula_surface.styleSheet().lower()
    expression_style = dialog.expression_text.styleSheet().lower()
    error_style = dialog.error_label.styleSheet().lower()
    assert _contrast_ratio(
        _style_color(surface_style, "color"),
        _style_color(surface_style, "background"),
    ) >= 7
    assert _contrast_ratio(
        _style_color(expression_style, "color"),
        _style_color(expression_style, "background"),
    ) >= 7
    assert _contrast_ratio(
        _style_color(error_style, "color"),
        _style_color(error_style, "background"),
    ) >= 7
    pixmap = dialog.formula_surface.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert _has_dark_rendered_pixels(pixmap.toImage())


def test_implicit_panel_uses_preview_buttons_not_inline_labels(window):
    from app_desktop.formula_preview import FormulaPreviewLabel

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))

    assert hasattr(window, "implicit_equation_preview_button")
    assert hasattr(window, "implicit_output_preview_button")
    assert not hasattr(window, "implicit_equation_preview") or not window.implicit_equation_preview.isVisible()
    assert not hasattr(window, "implicit_output_preview") or not window.implicit_output_preview.isVisible()
    assert window.implicit_model_widget.findChildren(FormulaPreviewLabel) == []
    preview_buttons = {
        button.objectName()
        for button in window.implicit_model_widget.findChildren(QPushButton)
        if "preview" in button.objectName()
    }
    assert preview_buttons == {"implicit_equation_preview_button", "implicit_output_preview_button"}


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


def test_implicit_preview_tooltips_keep_button_meaning_in_chinese(window):
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))

    window._apply_language("zh")

    assert window.implicit_equation_preview_button.toolTip() == "预览方程"
    assert window.implicit_output_preview_button.toolTip() == "预览输出"

    window._apply_language("en")

    assert window.implicit_equation_preview_button.toolTip() == "Preview equation"
    assert window.implicit_output_preview_button.toolTip() == "Preview output"


def test_long_implicit_formula_does_not_expand_left_splitter(window, qtbot):
    from app_desktop.formula_preview import FormulaPreviewLabel

    window.resize(1200, 800)
    window.show()
    qtbot.waitExposed(window)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()

    left_scroll = window._main_splitter.widget(0)
    assert isinstance(left_scroll, QScrollArea)
    assert left_scroll.widgetResizable()
    before_minimum_width = left_scroll.minimumWidth()
    long_formula = "d0 + " + " + ".join(f"d{i}/(n-delta)^{i}" for i in range(2, 40))
    window.implicit_equation_edit.setPlainText(long_formula)
    window.implicit_output_edit.setPlainText(long_formula)
    QApplication.processEvents()

    assert window.implicit_model_widget.findChildren(FormulaPreviewLabel) == []
    assert left_scroll.minimumWidth() == before_minimum_width
    assert left_scroll.minimumWidth() <= 360
    window._main_splitter.setSizes([320, 880])
    QApplication.processEvents()
    assert window._main_splitter.sizes()[0] <= 360
    assert window._main_splitter.sizes()[1] >= 800
    assert window.implicit_equation_preview_button.isVisible()
    assert window.implicit_output_preview_button.isVisible()


def test_implicit_preview_controls_hidden_for_non_self_consistent_models(window, qtbot):
    window.show()
    qtbot.waitExposed(window)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_mcmc_refine.setChecked(True)

    for mode in ("custom", "polynomial", "inverse_power", "pade", "power_limit"):
        index = window.fit_model_combo.findData(mode)
        if index < 0:
            continue
        window.fit_model_combo.setCurrentIndex(index)
        QApplication.processEvents()
        assert not window.implicit_model_widget.isVisible()
        assert not window.implicit_equation_preview_button.isVisible()
        assert not window.implicit_output_preview_button.isVisible()
        leaked_implicit_previews = [
            button
            for button in window.fit_box.findChildren(QPushButton)
            if button.isVisible()
            and button.objectName() in {"implicit_equation_preview_button", "implicit_output_preview_button"}
        ]
        assert leaked_implicit_previews == []
