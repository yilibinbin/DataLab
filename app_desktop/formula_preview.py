"""Rendered formula preview helpers for desktop formula editors."""

from __future__ import annotations

import re
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datalab_latex.formula_render_service import (
    InputLanguage,
    RenderRequest,
    RenderResult,
    format_formula_latex,
    render_formula,
)
from app_desktop.formula_tex_render_worker import (
    FormulaTexRenderWorker,
    TexRenderRequest,
    TexRenderResult,
)
from app_desktop.theme import (
    formula_inline_preview_style,
    formula_preview_error_surface_style,
    formula_preview_source_edit_style,
    formula_preview_surface_style,
)

_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INLINE_PREVIEW_MAX_WIDTH: Final = 520
_INLINE_PREVIEW_MAX_HEIGHT: Final = 104


class FormulaPreviewLabel(QLabel):
    """Compact formula preview that opens the unified preview dialog on click."""

    def __init__(self) -> None:
        super().__init__()
        configure_formula_preview_label(self, constrain_size=True)
        self._preview_expression = ""
        self._preview_lhs: str | None = None

    def set_preview_source(self, expression: str, lhs: str | None) -> None:
        self._preview_expression = expression
        self._preview_lhs = lhs

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() != Qt.MouseButton.LeftButton or not self._preview_expression.strip():
            super().mousePressEvent(event)
            return
        dialog = FormulaPreviewDialog(
            self,
            expression=self._preview_expression,
            lhs=self._preview_lhs,
        )
        dialog.exec()


class FormulaPreviewDialog(QDialog):
    """Read-only formula preview dialog with a light rendering surface."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        expression: str,
        lhs: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.expression = expression or ""
        self.lhs = lhs
        self.setWindowTitle(self._tr("公式预览", "Formula Preview"))
        self.resize(560, 320)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.formula_surface = QLabel()
        self.formula_surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.formula_surface.setMinimumHeight(96)
        self.formula_surface.setStyleSheet(formula_preview_surface_style())
        layout.addWidget(self.formula_surface)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(formula_preview_error_surface_style())
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.expression_text = QPlainTextEdit()
        self.expression_text.setReadOnly(True)
        self.expression_text.setPlainText(self.expression)
        self.expression_text.setMinimumHeight(84)
        self.expression_text.setStyleSheet(formula_preview_source_edit_style())
        layout.addWidget(self.expression_text)

        self.render_tier_combo = QComboBox()
        self.render_tier_combo.setObjectName("formula_preview_render_tier_combo")
        self.render_tier_combo.addItem(self._tr("数学预览", "Math preview"), "mathtext")
        self.render_tier_combo.addItem(self._tr("高保真 LaTeX", "High-fidelity LaTeX"), "high_fidelity_latex")
        self.render_tier_combo.setToolTip(
            self._tr(
                "仅控制预览渲染方式；不会改变计算输入。",
                "Controls preview rendering only; it does not change computation input.",
            )
        )
        layout.addWidget(self.render_tier_combo)

        self.latex_source_edit = QPlainTextEdit()
        self.latex_source_edit.setObjectName("formula_preview_latex_source_edit")
        self.latex_source_edit.setPlainText(self._default_latex_source())
        self.latex_source_edit.setMinimumHeight(84)
        self.latex_source_edit.setToolTip(
            self._tr(
                "仅用于高保真预览显示的 LaTeX 源；不会用于计算。",
                "Display-only LaTeX source for high-fidelity preview; this is never used for computation.",
            )
        )
        self.latex_source_edit.setStyleSheet(formula_preview_source_edit_style())
        layout.addWidget(self.latex_source_edit)

        self.high_fidelity_status_label = QLabel("")
        self.high_fidelity_status_label.setObjectName("formula_preview_high_fidelity_status")
        self.high_fidelity_status_label.setWordWrap(True)
        layout.addWidget(self.high_fidelity_status_label)

        button_row = QHBoxLayout()
        self.high_fidelity_render_button = QPushButton(self._tr("渲染", "Render"))
        self.high_fidelity_render_button.setObjectName("formula_preview_high_fidelity_render_button")
        self.high_fidelity_render_button.setToolTip(
            self._tr(
                "使用已安装的 TeX 引擎渲染仅显示用 LaTeX 源。所需宏包必须已缓存；此预览不会安装或下载 TeX 宏包。",
                "Render the display-only LaTeX source with an installed TeX engine. "
                "Packages must already be cached; this preview does not install or download TeX packages.",
            )
        )
        self.high_fidelity_render_button.clicked.connect(self._start_high_fidelity_render)
        button_row.addWidget(self.high_fidelity_render_button)
        button_row.addStretch()
        self.copy_button = QPushButton(self._tr("复制", "Copy"))
        self.copy_button.clicked.connect(self._copy_expression)
        button_row.addWidget(self.copy_button)
        self.close_button = QPushButton(self._tr("关闭", "Close"))
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self._formula_tex_worker = None
        self._formula_tex_job_id = 0
        self.render_tier_combo.currentIndexChanged.connect(lambda _index: self._sync_high_fidelity_controls())
        self._sync_high_fidelity_controls()
        self._render_formula()
        self._formula_tex_retained_workers = set()

    def _tr(self, zh: str, en: str) -> str:
        return _translate_for_widget(self.parentWidget(), zh, en)

    def _render_formula(self) -> None:
        self.error_label.clear()
        self.error_label.hide()
        try:
            pixmap = render_formula_pixmap(self.expression, lhs=self.lhs)
        except Exception as exc:  # noqa: BLE001
            pixmap = None
            self.error_label.setText(str(exc))
            self.error_label.show()
        if pixmap is not None and not pixmap.isNull():
            self.formula_surface.setPixmap(pixmap)
            self.formula_surface.setText("")
            return
        self.formula_surface.setPixmap(QPixmap())
        self.formula_surface.setText(self.expression)
        if self.expression.strip() and not self.error_label.text():
            self.error_label.setText(
                self._tr("公式渲染不可用；显示源文本。", "Formula rendering unavailable; showing source text.")
            )
            self.error_label.show()

    def _default_latex_source(self) -> str:
        if not self.expression.strip():
            return ""
        try:
            latex = format_formula_latex(self.expression)
            return f"{self.lhs} = {latex}" if self.lhs else latex
        except Exception:  # noqa: BLE001
            return self.expression

    def _sync_high_fidelity_controls(self) -> None:
        high_fidelity = self.render_tier_combo.currentData() == "high_fidelity_latex"
        if not high_fidelity:
            if self._formula_tex_worker is not None:
                self._formula_tex_job_id += 1
                self._cancel_formula_tex_worker()
            self._render_formula()
        self.latex_source_edit.setEnabled(high_fidelity)
        self.high_fidelity_render_button.setEnabled(high_fidelity)

    def _start_high_fidelity_render(self) -> None:
        self._cancel_formula_tex_worker()
        self._formula_tex_job_id += 1
        job_id = self._formula_tex_job_id
        request = TexRenderRequest(
            latex=self.latex_source_edit.toPlainText(),
            engine="tectonic",
            dpi=180,
        )
        worker = FormulaTexRenderWorker(request)
        self._formula_tex_worker = worker
        worker.finished_ok.connect(lambda result, _job_id=job_id: self._on_high_fidelity_finished(_job_id, result))
        worker.failed.connect(lambda message, _job_id=job_id: self._on_high_fidelity_failed(_job_id, message))
        worker.cancelled.connect(lambda _job_id=job_id: self._on_high_fidelity_cancelled(_job_id))
        finished = getattr(worker, "finished", None)
        if finished is not None:
            finished.connect(lambda _worker=worker: self._release_formula_tex_worker(_worker))
            finished.connect(worker.deleteLater)
        self.high_fidelity_render_button.setEnabled(False)
        self.high_fidelity_status_label.setText(self._tr("正在渲染高保真预览...", "Rendering high-fidelity preview..."))
        worker.start()

    def _on_high_fidelity_finished(self, job_id: int, result: TexRenderResult) -> None:
        if job_id != self._formula_tex_job_id:
            return
        pixmap = QPixmap()
        if result.ok and result.png_bytes and _load_png_pixmap(pixmap, result.png_bytes):
            self.formula_surface.setPixmap(pixmap)
            self.formula_surface.setText("")
            self.error_label.hide()
            cache_text = self._tr("（缓存）", " (cache)") if result.from_cache else ""
            self.high_fidelity_status_label.setText(
                self._tr(f"高保真预览已生成{cache_text}。", f"High-fidelity preview ready{cache_text}.")
            )
        else:
            self._show_high_fidelity_failed(result.error_message or self._tr("高保真渲染不可用。", "High-fidelity rendering unavailable."))
        self._finish_high_fidelity_worker(job_id)

    def _on_high_fidelity_failed(self, job_id: int, message: str) -> None:
        if job_id != self._formula_tex_job_id:
            return
        self._show_high_fidelity_failed(message)
        self._finish_high_fidelity_worker(job_id)

    def _show_high_fidelity_failed(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        self.high_fidelity_status_label.setText(
            self._tr(
                "高保真预览不可用；请确认 TeX 宏包已安装或缓存。",
                "High-fidelity preview unavailable; ensure TeX packages are installed or cached.",
            )
        )

    def _on_high_fidelity_cancelled(self, job_id: int) -> None:
        if job_id != self._formula_tex_job_id:
            return
        self.high_fidelity_status_label.setText(self._tr("高保真预览已取消。", "High-fidelity preview cancelled."))
        self._finish_high_fidelity_worker(job_id)

    def _finish_high_fidelity_worker(self, job_id: int) -> None:
        if job_id != self._formula_tex_job_id:
            return
        worker = self._formula_tex_worker
        self._disconnect_formula_tex_worker()
        self.high_fidelity_render_button.setEnabled(self.render_tier_combo.currentData() == "high_fidelity_latex")
        if worker is not None:
            self._retain_formula_tex_worker(worker)
        self._formula_tex_worker = None

    def _cancel_formula_tex_worker(self) -> None:
        worker = self._formula_tex_worker
        if worker is not None and hasattr(worker, "request_stop"):
            worker.request_stop()
        # Cancellation is cooperative and TeX subprocess cleanup happens in
        # the worker. Do not wait here: the dialog must stay responsive. The
        # custom result signals are disconnected so a superseded/closing
        # worker cannot mutate UI. Keep QThread.finished -> deleteLater, when
        # present, so the thread object can finish its own Qt lifecycle.
        self._disconnect_formula_tex_worker()
        if worker is not None:
            self._retain_formula_tex_worker(worker)
        self._formula_tex_worker = None

    def _retain_formula_tex_worker(self, worker: object) -> None:
        if not hasattr(worker, "finished"):
            return
        self._formula_tex_retained_workers.add(worker)

    def _release_formula_tex_worker(self, worker: object) -> None:
        self._formula_tex_retained_workers.discard(worker)

    def _disconnect_formula_tex_worker(self) -> None:
        worker = self._formula_tex_worker
        if worker is None:
            return
        for signal in (worker.finished_ok, worker.failed, worker.cancelled):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass

    def _copy_expression(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.expression)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._formula_tex_job_id += 1
        self._cancel_formula_tex_worker()
        super().closeEvent(event)


def open_formula_preview_dialog(
    parent: QWidget | None,
    expression: str,
    lhs: str | None = None,
) -> FormulaPreviewDialog:
    dialog = FormulaPreviewDialog(parent, expression=expression, lhs=lhs)
    dialog.exec()
    return dialog


def _translate_for_widget(widget: QWidget | None, zh: str, en: str) -> str:
    seen: set[int] = set()
    current = widget
    while current is not None:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        translator = getattr(current, "_tr", None)
        if callable(translator):
            try:
                return str(translator(zh, en))
            except Exception:  # noqa: BLE001
                pass
        parent = current.parentWidget()
        if parent is None:
            top_level = current.window()
            if top_level is not current:
                current = top_level
                continue
        current = parent
    return en


def configure_formula_preview_label(label: QLabel, *, constrain_size: bool = False) -> None:
    """Apply the inline workbench preview chrome when explicitly requested.

    Legacy call sites pass ordinary ``QLabel`` instances that may already be
    styled by their parent UI. Keep those labels untouched unless the caller
    opts in to workbench sizing/styling through ``constrain_size``.
    """
    if not constrain_size:
        return
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setMinimumHeight(92)
    label.setMaximumHeight(_INLINE_PREVIEW_MAX_HEIGHT)
    label.setMaximumWidth(_INLINE_PREVIEW_MAX_WIDTH + 24)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    label.setCursor(Qt.CursorShape.PointingHandCursor)
    label.setToolTip("Click to enlarge formula")
    label.setStyleSheet(formula_inline_preview_style())


def render_formula_pixmap(
    expression: str,
    lhs: str | None = None,
    *,
    language: InputLanguage | str = InputLanguage.DATALAB,
) -> QPixmap | None:
    """Render a display-only expression preview to a ``QPixmap``.

    Returns ``None`` for invalid/empty input or when the optional renderer is
    unavailable. This never calls external LaTeX; matplotlib is imported lazily
    and only uses its built-in mathtext renderer.
    """
    text = (expression or "").strip()
    if not text:
        return None
    if lhs is not None and not _is_identifier(lhs):
        return None

    result = render_formula(RenderRequest(source=text, language=InputLanguage(language), lhs=lhs))
    if not result.ok or not result.png_bytes:
        return None
    pixmap = QPixmap()
    if not _load_png_pixmap(pixmap, result.png_bytes):
        return None
    return pixmap


def update_formula_preview(label: QLabel, expression: str, lhs: str | None = None) -> RenderResult | None:
    """Update ``label`` with a rendered preview or plain-text fallback.

    Legacy callers keep empty formulas blank; workbench callers pass localized
    ``empty_text`` through ``update_formula_preview_with_empty_text``. Returns
    the structured render result for callers that want preview diagnostics.
    """
    return update_formula_preview_with_empty_text(label, expression, lhs=lhs)


def update_formula_preview_with_empty_text(
    label: QLabel,
    expression: str,
    lhs: str | None = None,
    *,
    empty_text: str | None = None,
    language: InputLanguage | str = InputLanguage.DATALAB,
    constrain_size: bool = False,
) -> RenderResult | None:
    """Update ``label`` with a rendered preview, fallback text, or empty-state copy."""
    configure_formula_preview_label(label, constrain_size=constrain_size)
    if hasattr(label, "set_preview_source"):
        label.set_preview_source(expression or "", lhs)
    if not (expression or "").strip():
        label.setPixmap(QPixmap())
        label.setText(empty_text or "")
        return None
    result = render_formula(
        RenderRequest(
            source=(expression or "").strip(),
            language=InputLanguage(language),
            lhs=lhs,
        )
    )
    pixmap = QPixmap()
    if result.ok and result.png_bytes and _load_png_pixmap(pixmap, result.png_bytes):
        if pixmap.width() > _INLINE_PREVIEW_MAX_WIDTH:
            pixmap = pixmap.scaledToWidth(
                _INLINE_PREVIEW_MAX_WIDTH,
                Qt.TransformationMode.SmoothTransformation,
            )
        if pixmap.height() > _INLINE_PREVIEW_MAX_HEIGHT:
            pixmap = pixmap.scaledToHeight(
                _INLINE_PREVIEW_MAX_HEIGHT,
                Qt.TransformationMode.SmoothTransformation,
            )
        label.setPixmap(pixmap)
        label.setText("")
        return result

    label.clear()
    label.setText(expression or "")
    return result


def _is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.fullmatch((value or "").strip()))


def _load_png_pixmap(pixmap: QPixmap, data: bytes) -> bool:
    try:
        return pixmap.loadFromData(data, b"PNG")
    except ValueError:
        # Some PySide6 builds type the format as bytes but accept only str at runtime.
        return pixmap.loadFromData(data, cast(bytes, "PNG"))
