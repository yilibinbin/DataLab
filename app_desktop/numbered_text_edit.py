"""``QPlainTextEdit`` with a left-margin line-number gutter.

The standard Qt code-editor recipe (cf. Qt docs:
https://doc.qt.io/qt-6/qtwidgets-widgets-codeeditor-example.html)
adapted for DataLab's LaTeX viewer. Mirrors the upstream example
verbatim except for the colour palette, which follows DataLab's
existing palette helpers so dark / light mode pick the right
contrast automatically.

Used for the LaTeX output tab so the user can locate compile errors
("error: 1.tex:57: …") by line number without external tooling.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

# Pixel padding around the digit column inside the gutter. The numbers
# are tuned for the default Qt 12-px font; bump them in proportion if a
# bigger global font is ever set on the editor.
_GUTTER_LEFT_PAD = 8
_GUTTER_RIGHT_PAD = 4
# Always reserve room for at least 3-digit line numbers so the gutter
# width doesn't shimmer on documents that grow past 9 / 99 lines.
_GUTTER_MIN_DIGITS = 3


class _LineNumberArea(QWidget):
    """Thin gutter widget that draws line numbers next to the editor.

    Owned by the ``NumberedTextEdit`` and forwards paint + sizing
    decisions back to the parent so the colour / font / metrics stay
    coherent with the editor itself (cf. Qt CodeEditor example).
    """

    def __init__(self, editor: "NumberedTextEdit") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt naming
        self._editor.line_number_area_paint_event(event)


class NumberedTextEdit(QPlainTextEdit):
    """``QPlainTextEdit`` with a synchronised line-number gutter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        # Cached colours + format objects. Rebuilt lazily and on
        # palette / style changes (see ``changeEvent``) so the per-
        # paint and per-cursor-move hot paths don't re-fetch them.
        self._gutter_bg: QColor | None = None
        self._gutter_fg: QColor | None = None
        self._highlight_fmt: QTextCharFormat | None = None
        # Cache the last-emitted gutter width so updates that don't
        # change it can skip ``setViewportMargins`` (which forces a
        # layout pass).
        self._last_gutter_width: int = -1

        # Keep gutter synchronised with editor scroll / content edits.
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(_GUTTER_MIN_DIGITS, len(str(max(1, self.blockCount()))))
        return _GUTTER_LEFT_PAD + self.fontMetrics().horizontalAdvance("9") * digits

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        super().resizeEvent(event)
        rect = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(rect.left(), rect.top(), self.line_number_area_width(), rect.height())
        )

    def changeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        # Drop cached colours / format on palette or style changes so
        # the next paint / highlight rebuilds them against the new
        # palette. Cheaper than recomputing every paint.
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._gutter_bg = None
            self._gutter_fg = None
            self._highlight_fmt = None
        super().changeEvent(event)

    def _ensure_gutter_colours(self) -> tuple[QColor, QColor]:
        if self._gutter_bg is None or self._gutter_fg is None:
            palette = self.palette()
            # ``Base`` is the editor's text-area background — using it
            # makes the gutter blend with the editor body. ``AlternateBase``
            # produced a visibly different stripe and was reported as
            # "不协调".
            self._gutter_bg = palette.color(QPalette.ColorRole.Base)
            fg = palette.color(QPalette.ColorRole.PlaceholderText)
            if not fg.isValid():
                fg = palette.color(QPalette.ColorRole.WindowText)
                fg.setAlpha(140)
            self._gutter_fg = fg
        return self._gutter_bg, self._gutter_fg

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_number_area)
        bg, fg = self._ensure_gutter_colours()
        painter.fillRect(event.rect(), bg)

        # Hoist per-paint constants out of the per-block loop below.
        line_height = self.fontMetrics().height()
        gutter_width_minus_pad = self._line_number_area.width() - _GUTTER_RIGHT_PAD

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        painter.setPen(fg)
        align_right = Qt.AlignmentFlag.AlignRight
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, gutter_width_minus_pad, line_height,
                    align_right, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _update_line_number_area_width(self, _block_count: int) -> None:
        new_width = self.line_number_area_width()
        # Skip the layout pass when the width hasn't actually changed —
        # ``updateRequest`` fires on every cursor blink + keystroke,
        # so a no-op guard saves a layout per event in the common case.
        if new_width != self._last_gutter_width:
            self._last_gutter_width = new_width
            self.setViewportMargins(new_width, 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def _ensure_highlight_format(self) -> QTextCharFormat:
        if self._highlight_fmt is None:
            base = self.palette().color(QPalette.ColorRole.Base)
            # Lightness < 128 = dark theme: nudge toward lighter so the
            # current line stands out against the gutter+body. Light
            # theme: nudge slightly darker.
            tint = base.lighter(115) if base.lightness() < 128 else base.darker(105)
            fmt = QTextCharFormat()
            fmt.setBackground(tint)
            fmt.setProperty(QTextFormat.Property.FullWidthSelection, True)
            self._highlight_fmt = fmt
        return self._highlight_fmt

    def _highlight_current_line(self) -> None:
        # Subtle current-line highlight matches Qt's CodeEditor demo —
        # keeps the user oriented when a long .tex scrolls past several
        # screens. The format object is cached on the editor and only
        # the cursor changes per call (the colour / theme tracking
        # lives in ``changeEvent`` cache invalidation).
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        selection = QTextEdit.ExtraSelection()
        selection.format = self._ensure_highlight_format()
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
