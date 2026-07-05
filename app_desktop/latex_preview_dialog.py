"""LaTeX preview dialog — a resizable window with TeX-source and PDF-preview tabs.

Per the 2026-07-05 spec, LaTeX/PDF move out of the result tabs into this dedicated dialog.
It uses NEW display widgets and REUSES the underlying logic — it never reparents the
result-tab ``latex_edit`` / ``pdf_scroll`` (those are the result-panel's own widgets):

* **TeX tab** — a fresh ``NumberedTextEdit`` + ``LatexHighlighter`` showing the current tex
  source (from ``window.latex_edit``). 复制 copies it to the clipboard; 保存 writes it to a
  ``QFileDialog``-chosen path (the ONLY user-path write).
* **PDF tab** — compiles the current tex via the window's tectonic-only
  ``compile_latex_to_pdf`` (Module 2) to a temp PDF, then rasterizes it with the pure
  ``shared.pdf_preview_raster.convert_pdf_to_images`` helper into the dialog's OWN scroll
  (the dialog owns its zoom/dpi — no coupling to the main window's pdf state).

The dialog is non-modal and parented to the main window; it is created lazily and reused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

__all__ = ["LatexPreviewDialog", "open_latex_preview_dialog"]

# Default rasterization DPI for the dialog's PDF preview (the dialog owns this, not self).
_PREVIEW_DPI = 150


class LatexPreviewDialog(QDialog):
    """Resizable, non-modal TeX/PDF preview window (see module docstring)."""

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner
        self.setObjectName("latex_preview_dialog")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(720, 640)

        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("latex_preview_tabs")
        layout.addWidget(self._tabs)

        self._build_tex_tab()
        self._build_pdf_tab()

    # -- TeX tab ------------------------------------------------------------
    def _build_tex_tab(self) -> None:
        from app_desktop.latex_highlighter import LatexHighlighter
        from app_desktop.numbered_text_edit import NumberedTextEdit

        tab = QWidget()
        v = QVBoxLayout(tab)
        self._tex_view = NumberedTextEdit()
        self._tex_view.setObjectName("latex_preview_tex_view")
        self._tex_highlighter = LatexHighlighter(self._tex_view.document())
        v.addWidget(self._tex_view, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._copy_button = QPushButton(self._tr("复制", "Copy"))
        self._copy_button.setObjectName("latex_preview_copy_button")
        self._copy_button.clicked.connect(lambda _c=False: self._copy_tex())
        self._save_button = QPushButton(self._tr("保存", "Save"))
        self._save_button.setObjectName("latex_preview_save_button")
        self._save_button.clicked.connect(lambda _c=False: self._save_tex())
        buttons.addWidget(self._copy_button)
        buttons.addWidget(self._save_button)
        v.addLayout(buttons)

        self._tex_tab_index = self._tabs.addTab(tab, "TeX")

    def _copy_tex(self) -> None:
        QApplication.clipboard().setText(self._tex_view.toPlainText())

    def _save_tex(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("保存 LaTeX 文件", "Save LaTeX File"),
            "",
            "LaTeX (*.tex);;All Files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(self._tex_view.toPlainText(), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self._tr("保存失败", "Save Failed"), str(exc)
            )

    # -- PDF tab ------------------------------------------------------------
    def _build_pdf_tab(self) -> None:
        tab = QWidget()
        v = QVBoxLayout(tab)
        self._pdf_scroll = QScrollArea()
        self._pdf_scroll.setObjectName("latex_preview_pdf_scroll")
        self._pdf_scroll.setWidgetResizable(True)
        self._pdf_container = QWidget()
        self._pdf_container_layout = QVBoxLayout(self._pdf_container)
        self._pdf_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._pdf_scroll.setWidget(self._pdf_container)
        self._pdf_status = QLabel(self._tr("编译 PDF 中…", "Compiling PDF…"))
        self._pdf_status.setObjectName("latex_preview_pdf_status")
        v.addWidget(self._pdf_status)
        v.addWidget(self._pdf_scroll, 1)
        self._pdf_tab_index = self._tabs.addTab(tab, "PDF")

    def render_pdf(self) -> None:
        """Compile the current tex via tectonic (ASYNC) and rasterize the result into this
        dialog's scroll when the compile finishes.

        ``compile_latex_to_pdf`` runs a background QThread; ``last_pdf_path`` is only valid
        in the compile-completion callback, NOT synchronously after the call returns. So we
        register a one-shot ``_pdf_ready_callback`` on the owner and let it fire
        :meth:`_on_pdf_ready` when the PDF exists. If a PDF was already compiled and no
        recompile is triggered, render it directly.
        """
        compile_fn = getattr(self._owner, "compile_latex_to_pdf", None)
        if callable(compile_fn):
            self._pdf_status.setText(self._tr("编译 PDF 中…", "Compiling PDF…"))
            # Fire our renderer when the async compile completes.
            self._owner._pdf_ready_callback = self._on_pdf_ready
            compile_fn()
            # If compile did NOT start a worker (e.g. nothing to compile), fall back to any
            # already-compiled PDF so the dialog is not left stuck on "compiling".
            if getattr(self._owner, "_latex_compile_worker", None) is None:
                self._owner._pdf_ready_callback = None
                existing = getattr(self._owner, "last_pdf_path", None)
                if existing and Path(existing).exists():
                    self._on_pdf_ready(Path(existing))
                else:
                    self._pdf_status.setText(
                        self._tr("尚无已编译的 PDF。", "No compiled PDF yet.")
                    )
            return
        existing = getattr(self._owner, "last_pdf_path", None)
        if existing and Path(existing).exists():
            self._on_pdf_ready(Path(existing))

    def _on_pdf_ready(self, pdf_path: Any) -> None:
        """Rasterize a freshly-compiled PDF into the dialog's own scroll (dialog-owned dpi)."""
        from shared.pdf_preview_raster import convert_pdf_to_images

        path = Path(pdf_path)
        if not path.exists():
            self._pdf_status.setText(
                self._tr("尚无已编译的 PDF。", "No compiled PDF yet.")
            )
            return
        try:
            images = convert_pdf_to_images(path, dpi=_PREVIEW_DPI)
        except Exception as exc:  # noqa: BLE001
            self._pdf_status.setText(
                self._tr(f"PDF 预览失败: {exc}", f"PDF preview failed: {exc}")
            )
            return
        self._lay_out_pdf_images(images)

    def _lay_out_pdf_images(self, images: list) -> None:
        # Clear previous pages.
        for i in reversed(range(self._pdf_container_layout.count())):
            item = self._pdf_container_layout.takeAt(i)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not images:
            self._pdf_status.setText(self._tr("暂无 PDF 预览", "No PDF preview"))
            return
        for pil_image in images:
            rgba = pil_image.convert("RGBA")
            qimage = QImage(
                rgba.tobytes("raw", "RGBA"),
                rgba.width,
                rgba.height,
                QImage.Format.Format_RGBA8888,
            )
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(qimage))
            self._pdf_container_layout.addWidget(label)
        self._pdf_status.setText(
            self._tr(f"共 {len(images)} 页", f"{len(images)} page(s)")
        )

    # -- open on a tab ------------------------------------------------------
    def show_tab(self, initial_tab: str) -> None:
        """Refresh content and select the requested tab, then show/raise."""
        # TeX view mirrors the current source string (reuse, not reparent).
        source = ""
        editor = getattr(self._owner, "latex_edit", None)
        if editor is not None:
            source = editor.toPlainText()
        self._tex_view.setPlainText(source)
        if initial_tab == "pdf":
            self._tabs.setCurrentIndex(self._pdf_tab_index)
            self.render_pdf()
        else:
            self._tabs.setCurrentIndex(self._tex_tab_index)
        self.show()
        self.raise_()
        self.activateWindow()

    def _tr(self, zh: str, en: str) -> str:
        tr = getattr(self._owner, "_tr", None)
        return tr(zh, en) if callable(tr) else zh


def open_latex_preview_dialog(owner: Any, initial_tab: str = "tex") -> LatexPreviewDialog:
    """Create-or-reuse the LaTeX preview dialog on ``owner`` and open it on ``initial_tab``."""
    dialog = getattr(owner, "_latex_preview_dialog", None)
    if dialog is None or not isinstance(dialog, LatexPreviewDialog):
        dialog = LatexPreviewDialog(owner)
        owner._latex_preview_dialog = dialog
    dialog.show_tab(initial_tab)
    return dialog
