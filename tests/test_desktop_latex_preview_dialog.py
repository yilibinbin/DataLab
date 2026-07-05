"""LaTeX preview dialog (TeX/PDF tabs) — Module 1b of the LaTeX/PDF rework.

Per the 2026-07-05 spec, LaTeX/PDF move OUT of the result tabs into a dedicated resizable
dialog with two tabs: TeX source (with 复制/保存) and PDF preview. The dialog uses NEW
display widgets and reuses the underlying logic (tex source string, tectonic compile,
convert_pdf_to_images) — it does NOT reparent the result-tab widgets.

These tests encode WHY: the dialog shows the current tex source, copy puts it on the
clipboard, save writes it to a chosen path, and the two result-panel buttons open the
dialog on the right tab.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QTabWidget


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


_TEX = r"\documentclass{article}\begin{document}Hello $x^2$\end{document}"


def _open_latex_dialog(window: Any, initial_tab: str = "tex") -> Any:
    from app_desktop.latex_preview_dialog import open_latex_preview_dialog

    return open_latex_preview_dialog(window, initial_tab=initial_tab)


def test_latex_preview_dialog_has_tex_and_pdf_tabs(window: Any) -> None:
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window)
    assert isinstance(dialog, QDialog)
    assert dialog.isModal() is False
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    titles = {tabs.tabText(i) for i in range(tabs.count())}
    assert any("TeX" in t for t in titles)
    assert any("PDF" in t for t in titles)
    dialog.close()


def test_tex_tab_shows_current_latex_source(window: Any) -> None:
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")
    # The dialog's TeX view is a NEW widget (not the result-tab latex_edit) showing the
    # same source string.
    assert dialog._tex_view is not window.latex_edit
    assert _TEX in dialog._tex_view.toPlainText()
    dialog.close()


def test_copy_button_puts_tex_on_clipboard(window: Any) -> None:
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")
    QApplication.clipboard().clear()
    dialog._copy_tex()
    assert QApplication.clipboard().text() == dialog._tex_view.toPlainText()
    assert _TEX in QApplication.clipboard().text()
    dialog.close()


def test_save_button_writes_tex_to_chosen_path(window: Any, monkeypatch: Any, tmp_path: Any) -> None:
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")
    target = tmp_path / "saved.tex"

    import app_desktop.latex_preview_dialog as mod

    monkeypatch.setattr(
        mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "LaTeX (*.tex)")
    )
    dialog._save_tex()
    assert target.read_text(encoding="utf-8") == dialog._tex_view.toPlainText()
    assert _TEX in target.read_text(encoding="utf-8")
    dialog.close()


def test_result_buttons_open_dialog_on_right_tab(window: Any) -> None:
    """The 生成 TeX / 预览 PDF result-panel buttons open the dialog on the matching tab."""
    window.latex_edit.setPlainText(_TEX)
    tex_btn = window.result_generate_tex_button
    pdf_btn = window.result_preview_pdf_button

    tex_btn.click()
    QApplication.processEvents()
    dialog = window._latex_preview_dialog
    tabs = dialog.findChild(QTabWidget)
    assert "TeX" in tabs.tabText(tabs.currentIndex())
    dialog.close()

    pdf_btn.click()
    QApplication.processEvents()
    dialog = window._latex_preview_dialog
    tabs = dialog.findChild(QTabWidget)
    assert "PDF" in tabs.tabText(tabs.currentIndex())
    dialog.close()
