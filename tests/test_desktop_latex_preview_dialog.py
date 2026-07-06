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
from pathlib import Path
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


def test_result_buttons_open_dialog_on_right_tab(window: Any, monkeypatch: Any) -> None:
    """The 生成 TeX / 预览 PDF result-panel buttons rebuild tex on demand and open the
    dialog on the matching tab. We stub the rebuild (tested elsewhere) + the async compile
    (tested elsewhere) to isolate the button→dialog wiring."""
    window.latex_edit.setPlainText(_TEX)
    # A rebuildable result exists → the dispatcher returns a path (so the dialog opens).
    monkeypatch.setattr(window, "generate_latex_for_current_result", lambda: "/tmp/x.tex")
    # Do not trigger a real compile when the PDF tab opens.
    monkeypatch.setattr(window, "compile_latex_to_pdf", lambda: None)
    monkeypatch.setattr(window, "_latex_compile_worker", None, raising=False)

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


def test_latex_options_button_lives_in_result_panel_not_toolbar(window: Any) -> None:
    """The LaTeX options entry moved OUT of the toolbar INTO the result panel: a
    result-side 「LaTeX 选项」 button opens the existing latex_options_dialog, and the
    toolbar no longer carries a LaTeX button (user: 工具栏不需要 latex, 单独的 LaTeX 选项入口)."""
    assert not hasattr(window, "workbench_latex_options_button")
    btn = window.result_latex_options_button
    assert btn.objectName() == "result_latex_options_button"

    assert not window.latex_options_dialog.isVisible()
    btn.click()
    QApplication.processEvents()
    assert window.latex_options_dialog.isVisible()
    window.latex_options_dialog.close()


def test_result_buttons_inform_when_no_result(window: Any, monkeypatch: Any) -> None:
    """With nothing to rebuild, clicking 生成 TeX informs the user and opens no dialog."""
    import app_desktop.window as win_mod

    window._last_latex_inputs = {}
    info: list[int] = []
    monkeypatch.setattr(win_mod.QMessageBox, "information", lambda *a, **k: info.append(1))
    window.result_generate_tex_button.click()
    QApplication.processEvents()
    assert info == [1]
    assert getattr(window, "_latex_preview_dialog", None) is None


def test_pdf_status_does_not_lie_compiling_before_any_compile(window: Any) -> None:
    """The PDF tab's status label must NOT read '编译 PDF 中…' before a compile has been
    triggered — that made a NOT-YET-compiled tab look permanently stuck compiling
    (user-reported '一直显示正在编译中'). It should start in a neutral 'no PDF yet' state."""
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")  # open on TeX tab, no compile
    try:
        status = dialog._pdf_status.text()
        assert "编译 PDF 中" not in status and "Compiling" not in status, (
            f"PDF status falsely claims compiling before any compile: {status!r}"
        )
    finally:
        dialog.close()


def test_switching_to_pdf_tab_triggers_compile(window: Any, monkeypatch: Any) -> None:
    """Clicking the PDF tab inside the dialog must trigger a compile (users expect the PDF
    tab to show the PDF). Previously only the 预览 PDF button compiled, so manually
    switching to the PDF tab left the default '编译 PDF 中…' label frozen forever."""
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")  # start on TeX tab
    calls: list[int] = []
    monkeypatch.setattr(dialog, "render_pdf", lambda: calls.append(1))
    try:
        # Switch to the PDF tab as a user would (not via the 预览 PDF button).
        dialog._tabs.setCurrentIndex(dialog._pdf_tab_index)
        QApplication.processEvents()
        assert calls, "switching to the PDF tab must trigger render_pdf (a compile)"
    finally:
        dialog.close()


def test_render_pdf_registers_completion_callback_not_sync_read(window: Any, monkeypatch: Any) -> None:
    """render_pdf must NOT read last_pdf_path synchronously after the async compile — it
    must register a one-shot _pdf_ready_callback that the compile-completion path fires.
    (Regression for the Module-1b race: compile is a QThread; last_pdf_path is only valid
    in _on_latex_compile_completed, not right after compile_latex_to_pdf() returns.)"""
    window.latex_edit.setPlainText(_TEX)
    dialog = _open_latex_dialog(window, initial_tab="tex")

    compiled: list[int] = []

    class _PendingWorker:
        def isRunning(self) -> bool:  # noqa: N802 - Qt naming
            return False

        def request_cancel(self) -> None:
            pass

        def request_kill(self) -> None:
            pass

    # Simulate an async compile: it starts a "worker" and does NOT set last_pdf_path yet.
    def fake_compile() -> None:
        compiled.append(1)
        window._latex_compile_worker = _PendingWorker()

    monkeypatch.setattr(window, "compile_latex_to_pdf", fake_compile)
    window.last_pdf_path = None

    try:
        dialog.render_pdf()
        # It triggered compile and registered our renderer as the completion callback —
        # it must NOT have tried to render synchronously (no last_pdf_path yet).
        assert compiled == [1]
        assert window._pdf_ready_callback == dialog._on_pdf_ready
    finally:
        window._latex_compile_worker = None
        window._pdf_ready_callback = None
        dialog.close()


def test_render_pdf_never_shows_a_stale_pdf(window: Any, monkeypatch: Any) -> None:
    """After 生成 TeX regenerates fresh tex, an earlier last_pdf_path is STALE. render_pdf
    must NOT fall back to rendering it — that showed the old tex's PDF (user-reported bug).
    When no fresh compile starts, it reports status instead of rendering the stale page."""
    dialog = _open_latex_dialog(window, initial_tab="tex")
    # A PDF from a PREVIOUS compile is on record.
    window.last_pdf_path = Path("/tmp/datalab_STALE.pdf")
    rendered: list[Any] = []
    monkeypatch.setattr(dialog, "_on_pdf_ready", lambda p: rendered.append(p))
    # Compile early-returns without starting a worker (engine missing / user declined).
    monkeypatch.setattr(window, "compile_latex_to_pdf", lambda: None)
    window._latex_compile_worker = None

    dialog.render_pdf()
    QApplication.processEvents()

    assert rendered == [], "must not render the stale last_pdf_path"
    assert dialog._pdf_status.text() != dialog._tr("编译 PDF 中…", "Compiling PDF…"), (
        "status must not be stuck on 'compiling'"
    )
    dialog.close()


def test_render_pdf_clears_a_dead_worker_handle(window: Any, monkeypatch: Any) -> None:
    """A prior compile that left a dead _latex_compile_worker handle must NOT block a fresh
    compile forever (compile_latex_to_pdf early-returns on a live worker). render_pdf clears
    a non-running handle first (regression for the permanently-stuck '正在编译中')."""
    dialog = _open_latex_dialog(window, initial_tab="tex")

    class _DeadWorker:
        def isRunning(self) -> bool:  # noqa: N802 - Qt naming
            return False

    window._latex_compile_worker = _DeadWorker()
    cleared_before_call: list[bool] = []
    monkeypatch.setattr(
        window,
        "compile_latex_to_pdf",
        lambda: cleared_before_call.append(window._latex_compile_worker is None),
    )

    dialog.render_pdf()
    QApplication.processEvents()

    assert cleared_before_call == [True], "dead worker handle must be cleared before compile"
    window._pdf_ready_callback = None
    dialog.close()


def test_on_pdf_ready_rasterizes_into_dialog_scroll(window: Any, monkeypatch: Any, tmp_path: Any) -> None:
    """When the compile completes, _on_pdf_ready rasterizes the PDF into the dialog's OWN
    scroll via the pure convert_pdf_to_images helper."""
    from PySide6.QtWidgets import QLabel

    import shared.pdf_preview_raster as raster

    # Open on the TeX tab so we do NOT trigger a real compile; then drive _on_pdf_ready
    # directly (that is the compile-completion path under test).
    dialog = _open_latex_dialog(window, initial_tab="tex")
    pdf_path = tmp_path / "out.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class _FakeImg:
        width, height = 4, 4

        def convert(self, _mode: str) -> "_FakeImg":
            return self

        def tobytes(self, *_a: Any, **_k: Any) -> bytes:
            return b"\x00" * (4 * 4 * 4)

    monkeypatch.setattr(raster, "convert_pdf_to_images", lambda *a, **k: [_FakeImg(), _FakeImg()])
    dialog._on_pdf_ready(pdf_path)
    # Two pages laid into the dialog's own container as QLabels.
    labels = dialog._pdf_container.findChildren(QLabel)
    assert len(labels) >= 2
    dialog.close()
