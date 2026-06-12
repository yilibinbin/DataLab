from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_formula_preview_translation_fallback_uses_chinese_default() -> None:
    from app_desktop.formula_preview import _translate_for_widget

    assert _translate_for_widget(None, "预览公式", "Preview formula") == "预览公式"


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


def test_formula_preview_dialog_falls_back_to_source_when_mathtext_pixmap_is_null(qtbot, monkeypatch):
    from PySide6.QtGui import QPixmap

    from app_desktop import formula_preview

    monkeypatch.setattr(formula_preview, "render_formula_pixmap", lambda *_args, **_kwargs: QPixmap())

    dialog = formula_preview.FormulaPreviewDialog(expression="sin(x)", lhs="y")
    qtbot.addWidget(dialog)

    assert dialog.formula_surface.text() == "sin(x)"
    assert "公式渲染不可用" in dialog.error_label.text()
    assert not dialog.error_label.isHidden()


def test_formula_preview_dialog_falls_back_to_source_when_mathtext_renderer_raises(qtbot, monkeypatch):
    from app_desktop import formula_preview

    def raise_render_error(*_args, **_kwargs):
        raise RuntimeError("forced formula render failure")

    monkeypatch.setattr(formula_preview, "render_formula_pixmap", raise_render_error)

    dialog = formula_preview.FormulaPreviewDialog(expression="cos(x)", lhs="z")
    qtbot.addWidget(dialog)

    assert dialog.formula_surface.text() == "cos(x)"
    assert dialog.error_label.text() == "forced formula render failure"
    assert not dialog.error_label.isHidden()


def test_formula_preview_dialog_clears_stale_error_when_mathtext_rerender_succeeds(qtbot, monkeypatch):
    from PySide6.QtGui import QPixmap

    from app_desktop import formula_preview

    def render_valid_pixmap(*_args, **_kwargs):
        pixmap = QPixmap(1, 1)
        pixmap.fill(QColor("#111827"))
        return pixmap

    monkeypatch.setattr(formula_preview, "render_formula_pixmap", render_valid_pixmap)

    dialog = formula_preview.FormulaPreviewDialog(expression="exp(x)", lhs="y")
    qtbot.addWidget(dialog)
    dialog.error_label.setText("previous high-fidelity failure")
    dialog.error_label.show()

    dialog._render_formula()

    assert dialog.formula_surface.text() == ""
    assert dialog.error_label.text() == ""
    assert dialog.error_label.isHidden()


def test_open_formula_preview_dialog_executes_and_returns_dialog(qtbot, monkeypatch):
    from app_desktop import formula_preview

    exec_calls: list[formula_preview.FormulaPreviewDialog] = []

    def fake_exec(self):
        exec_calls.append(self)
        return 0

    monkeypatch.setattr(formula_preview.FormulaPreviewDialog, "exec", fake_exec)

    dialog = formula_preview.open_formula_preview_dialog(None, "a*x+b", lhs="y")
    qtbot.addWidget(dialog)

    assert exec_calls == [dialog]
    assert isinstance(dialog, formula_preview.FormulaPreviewDialog)
    assert dialog.expression == "a*x+b"
    assert dialog.lhs == "y"
    assert dialog.expression_text.toPlainText() == "a*x+b"


def test_formula_preview_theme_helpers_cover_dialog_surfaces() -> None:
    from app_desktop import theme

    assert "border-radius" in theme.formula_preview_surface_style(dark=False)
    assert "padding: 12px" in theme.formula_preview_surface_style(dark=True)
    assert "#8a1c13" in theme.formula_preview_error_surface_style(dark=False)
    assert "border" in theme.formula_preview_source_edit_style(dark=False)
    assert "border-radius" in theme.formula_inline_preview_style(dark=True)


def test_formula_preview_module_does_not_embed_targeted_literal_qss() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "formula_preview.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_snippets = {
        "background: #ffffff; color: #111111; border: 1px solid #d0d7de; ",
        "border-radius: 4px; padding: 12px;",
        "background: #fff4f2; color: #8a1c13; border: 1px solid #f2b8b5; ",
        "border-radius: 4px; padding: 8px;",
        "background: #ffffff; color: #111111; border: 1px solid #d0d7de;",
        "background: #f8fafc; color: #111827; border: 1px solid #cbd5e1; ",
        "border-radius: 6px; padding: 12px;",
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert literals.isdisjoint(forbidden_snippets)


def test_formula_preview_dialog_exposes_high_fidelity_latex_controls(qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)

    assert dialog.render_tier_combo.currentData() == "mathtext"
    assert dialog.render_tier_combo.findData("high_fidelity_latex") >= 0
    assert dialog.latex_source_edit.toPlainText().strip()
    assert dialog.high_fidelity_render_button.text()
    assert "显示" in dialog.latex_source_edit.toolTip()
    assert "缓存" in dialog.high_fidelity_render_button.toolTip()


def test_formula_preview_dialog_localizes_from_parent_window(window, qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog

    window._apply_language("zh")
    zh_dialog = FormulaPreviewDialog(window, expression="a*x+b", lhs="y")
    qtbot.addWidget(zh_dialog)

    assert zh_dialog.windowTitle() == "公式预览"
    assert zh_dialog.render_tier_combo.itemText(zh_dialog.render_tier_combo.findData("mathtext")) == "数学预览"
    assert (
        zh_dialog.render_tier_combo.itemText(zh_dialog.render_tier_combo.findData("high_fidelity_latex"))
        == "高保真 LaTeX"
    )
    assert zh_dialog.high_fidelity_render_button.text() == "渲染"
    assert zh_dialog.copy_button.text() == "复制"
    assert zh_dialog.close_button.text() == "关闭"
    assert "计算输入" in zh_dialog.render_tier_combo.toolTip()
    assert "不会安装或下载" in zh_dialog.high_fidelity_render_button.toolTip()

    window._apply_language("en")
    en_dialog = FormulaPreviewDialog(window, expression="a*x+b", lhs="y")
    qtbot.addWidget(en_dialog)

    assert en_dialog.windowTitle() == "Formula Preview"
    assert en_dialog.render_tier_combo.itemText(en_dialog.render_tier_combo.findData("mathtext")) == "Math preview"
    assert (
        en_dialog.render_tier_combo.itemText(en_dialog.render_tier_combo.findData("high_fidelity_latex"))
        == "High-fidelity LaTeX"
    )
    assert en_dialog.high_fidelity_render_button.text() == "Render"
    assert en_dialog.copy_button.text() == "Copy"
    assert en_dialog.close_button.text() == "Close"


def test_formula_preview_dialog_high_fidelity_render_uses_worker(qtbot, monkeypatch):
    from app_desktop import formula_preview
    from app_desktop.formula_tex_render_worker import TexRenderResult

    captured = []

    class FakeWorker(QObject):
        finished_ok = Signal(object)
        failed = Signal(str)
        cancelled = Signal()
        finished = Signal()

        def __init__(self, request):
            super().__init__()
            captured.append(request)

        def start(self):
            self.finished_ok.emit(
                TexRenderResult(
                    ok=True,
                    latex=r"\frac{1}{2}",
                    png_bytes=(
                        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
                        b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\n"
                        b"IDATx\x9cc``\x00\x00\x00\x02\x00\x01"
                        b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
                    ),
                    engine="tectonic",
                    engine_path="/fake/tectonic",
                    from_cache=False,
                )
            )

        def request_stop(self):
            pass

    monkeypatch.setattr(formula_preview, "FormulaTexRenderWorker", FakeWorker)
    dialog = formula_preview.FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    dialog.latex_source_edit.setPlainText(r"\frac{1}{2}")
    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("high_fidelity_latex"))

    qtbot.mouseClick(dialog.high_fidelity_render_button, Qt.MouseButton.LeftButton)

    assert captured
    assert captured[0].latex == r"\frac{1}{2}"
    assert captured[0].engine == "tectonic"
    assert dialog.high_fidelity_status_label.text()


def test_formula_preview_dialog_ignores_superseded_worker_result(qtbot, monkeypatch):
    from app_desktop import formula_preview
    from app_desktop.formula_tex_render_worker import TexRenderResult

    workers = []

    class FakeWorker(QObject):
        finished_ok = Signal(object)
        failed = Signal(str)
        cancelled = Signal()

        def __init__(self, request):
            super().__init__()
            self.request = request
            self.stopped = False
            workers.append(self)

        def start(self):
            pass

        def request_stop(self):
            self.stopped = True

    monkeypatch.setattr(formula_preview, "FormulaTexRenderWorker", FakeWorker)
    dialog = formula_preview.FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("high_fidelity_latex"))

    dialog.latex_source_edit.setPlainText("first")
    qtbot.mouseClick(dialog.high_fidelity_render_button, Qt.MouseButton.LeftButton)
    dialog.latex_source_edit.setPlainText("second")
    dialog._start_high_fidelity_render()
    stale_status = dialog.high_fidelity_status_label.text()

    workers[0].finished_ok.emit(
        TexRenderResult(ok=True, latex="first", png_bytes=b"not-png", engine="tectonic")
    )

    assert workers[0].stopped is True
    assert dialog.high_fidelity_status_label.text() == stale_status
    assert not dialog.high_fidelity_render_button.isEnabled()

    workers[1].failed.emit("second failed")

    assert dialog.high_fidelity_render_button.isEnabled()


def test_formula_preview_dialog_job_id_guard_blocks_direct_stale_result(qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog
    from app_desktop.formula_tex_render_worker import TexRenderResult

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    dialog._formula_tex_job_id = 2
    previous_status = dialog.high_fidelity_status_label.text()

    dialog._on_high_fidelity_finished(
        1,
        TexRenderResult(ok=True, latex="stale", png_bytes=b"not-png", engine="tectonic"),
    )

    assert dialog.high_fidelity_status_label.text() == previous_status


def test_formula_preview_dialog_switching_to_mathtext_cancels_worker(qtbot, monkeypatch):
    from app_desktop import formula_preview

    workers = []

    class FakeWorker(QObject):
        finished_ok = Signal(object)
        failed = Signal(str)
        cancelled = Signal()
        finished = Signal()

        def __init__(self, request):
            super().__init__()
            self.stopped = False
            workers.append(self)

        def start(self):
            pass

        def request_stop(self):
            self.stopped = True

    monkeypatch.setattr(formula_preview, "FormulaTexRenderWorker", FakeWorker)
    dialog = formula_preview.FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("high_fidelity_latex"))
    qtbot.mouseClick(dialog.high_fidelity_render_button, Qt.MouseButton.LeftButton)

    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("mathtext"))

    assert workers[0].stopped is True
    assert dialog._formula_tex_worker is None
    assert workers[0] in dialog._formula_tex_retained_workers

    workers[0].finished.emit()

    assert workers[0] not in dialog._formula_tex_retained_workers


def test_formula_preview_dialog_switching_to_mathtext_refreshes_without_worker(qtbot, monkeypatch):
    from app_desktop.formula_preview import FormulaPreviewDialog

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    calls = []
    monkeypatch.setattr(dialog, "_render_formula", lambda: calls.append("render"))

    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("high_fidelity_latex"))
    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("mathtext"))

    assert calls == ["render"]


def test_formula_preview_dialog_close_disconnects_worker_result(qtbot, monkeypatch):
    from app_desktop import formula_preview
    from app_desktop.formula_tex_render_worker import TexRenderResult

    workers = []

    class FakeWorker(QObject):
        finished_ok = Signal(object)
        failed = Signal(str)
        cancelled = Signal()

        def __init__(self, request):
            super().__init__()
            workers.append(self)

        def start(self):
            pass

        def request_stop(self):
            pass

    monkeypatch.setattr(formula_preview, "FormulaTexRenderWorker", FakeWorker)
    dialog = formula_preview.FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)
    dialog.render_tier_combo.setCurrentIndex(dialog.render_tier_combo.findData("high_fidelity_latex"))
    qtbot.mouseClick(dialog.high_fidelity_render_button, Qt.MouseButton.LeftButton)

    dialog.close()
    workers[0].finished_ok.emit(
        TexRenderResult(ok=True, latex="late", png_bytes=b"not-png", engine="tectonic")
    )

    assert dialog._formula_tex_worker is None


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


def test_inline_formula_preview_never_starts_tex_worker(qtbot, monkeypatch):
    from datalab_latex.formula_render_service import InputLanguage

    import app_desktop.formula_preview as formula_preview

    label = formula_preview.FormulaPreviewLabel()
    qtbot.addWidget(label)
    monkeypatch.setattr(
        formula_preview,
        "FormulaTexRenderWorker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("inline preview must not start TeX worker")),
        raising=False,
    )

    formula_preview.update_formula_preview_with_empty_text(
        label,
        r"\frac{1}{2}",
        language=InputLanguage.LATEX,
        constrain_size=True,
    )


def test_formula_preview_label_click_uses_unified_dialog(qtbot, monkeypatch):
    from app_desktop import formula_preview

    captured = []

    class FakeDialog:
        def __init__(self, parent, *, expression, lhs):
            captured.append((parent, expression, lhs))

        def exec(self):
            pass

    def fail_legacy_dialog(*_args, **_kwargs):
        raise AssertionError("FormulaPreviewLabel must not use the legacy QDialog path")

    monkeypatch.setattr(formula_preview, "FormulaPreviewDialog", FakeDialog)
    monkeypatch.setattr(formula_preview, "QDialog", fail_legacy_dialog)
    label = formula_preview.FormulaPreviewLabel()
    qtbot.addWidget(label)
    label.set_preview_source("a*x+b", "y")

    class FakeMouseEvent:
        def button(self):
            return Qt.MouseButton.LeftButton

    label.mousePressEvent(FakeMouseEvent())

    assert captured == [(label, "a*x+b", "y")]


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
        for button in window.workbench_formula_panel.findChildren(QPushButton)
        if button.objectName().startswith("implicit_") and "preview" in button.objectName()
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

    monkeypatch.setattr("app_desktop.views.helpers.open_formula_preview_dialog", fake_open)

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
    window._main_splitter.setSizes([1, 879, 320])
    QApplication.processEvents()
    assert window._main_splitter.sizes()[0] >= left_scroll.minimumWidth()
    assert left_scroll.horizontalScrollBar().maximum() == 0
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
