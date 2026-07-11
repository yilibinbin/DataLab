"""Rendered formula preview helpers for desktop formula editors."""

from __future__ import annotations

import re
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
)
from app_desktop.formula_renderer import render_desktop_preview
from app_desktop.theme import (
    formula_inline_preview_style,
    formula_preview_error_surface_style,
    formula_preview_source_edit_style,
    formula_preview_surface_style,
)

_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INLINE_PREVIEW_MAX_WIDTH: Final = 520
_INLINE_PREVIEW_MAX_HEIGHT: Final = 104
# The label reserves 12px padding + a 1px border on each side (formula_inline_preview_style). The
# rendered pixmap must fit INSIDE that inset, otherwise a tall formula fills the label edge-to-edge
# and paints over the bottom padding/rounded border (the "border not closed" bug). Cap the pixmap a
# little smaller than the label content box so the rounded border always stays visible.
_INLINE_PREVIEW_INSET: Final = 2 * (12 + 1)
_INLINE_PREVIEW_PIXMAP_MAX_HEIGHT: Final = _INLINE_PREVIEW_MAX_HEIGHT - _INLINE_PREVIEW_INSET
_INLINE_PREVIEW_PIXMAP_MAX_WIDTH: Final = _INLINE_PREVIEW_MAX_WIDTH - _INLINE_PREVIEW_INSET


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

        button_row = QHBoxLayout()
        self.copy_button = QPushButton(self._tr("复制", "Copy"))
        self.copy_button.clicked.connect(self._copy_expression)
        button_row.addStretch(1)
        button_row.addWidget(self.copy_button)
        self.close_button = QPushButton(self._tr("关闭", "Close"))
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self._render_formula()

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

    def _copy_expression(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.expression)


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
    return zh


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
    # WA_StyledBackground makes Qt honour the stylesheet's border-radius on a QLabel — without
    # it the rounded background/border isn't clipped to the corners, so they look squared-off.
    label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
    and only uses its built-in mathtext renderer. The ``language`` keyword is a
    legacy compatibility shim and is intentionally ignored; preview input is
    always interpreted as DataLab formula syntax.
    """
    text = (expression or "").strip()
    if not text:
        return None
    if lhs is not None and not _is_identifier(lhs):
        return None

    result = render_desktop_preview(RenderRequest(source=text, language=InputLanguage.DATALAB, lhs=lhs))
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
    """Update ``label`` with a rendered preview, fallback text, or empty-state copy.

    The ``language`` keyword is retained for old callers but is intentionally
    inert; preview input is always interpreted as DataLab formula syntax.
    """
    configure_formula_preview_label(label, constrain_size=constrain_size)
    if hasattr(label, "set_preview_source"):
        label.set_preview_source(expression or "", lhs)
    if not (expression or "").strip():
        label.setPixmap(QPixmap())
        label.setText(empty_text or "")
        return None
    result = render_desktop_preview(
        RenderRequest(
            source=(expression or "").strip(),
            language=InputLanguage.DATALAB,
            lhs=lhs,
        )
    )
    pixmap = QPixmap()
    if result.ok and result.png_bytes and _load_png_pixmap(pixmap, result.png_bytes):
        # Scale to fit INSIDE the label's padded content box (leaving the border visible), not to the
        # label's outer max size — see _INLINE_PREVIEW_PIXMAP_MAX_* above.
        if pixmap.width() > _INLINE_PREVIEW_PIXMAP_MAX_WIDTH:
            pixmap = pixmap.scaledToWidth(
                _INLINE_PREVIEW_PIXMAP_MAX_WIDTH,
                Qt.TransformationMode.SmoothTransformation,
            )
        if pixmap.height() > _INLINE_PREVIEW_PIXMAP_MAX_HEIGHT:
            pixmap = pixmap.scaledToHeight(
                _INLINE_PREVIEW_PIXMAP_MAX_HEIGHT,
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
