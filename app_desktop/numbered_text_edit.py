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

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


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
        # Keep gutter synchronised with editor scroll / content edits.
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        # 4 + max(3, log10(blockCount)) digits worth of horizontal
        # space, computed against the current font's '9' advance.
        digits = max(3, len(str(max(1, self.blockCount()))))
        space = 8 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        super().resizeEvent(event)
        rect = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(rect.left(), rect.top(), self.line_number_area_width(), rect.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_number_area)
        palette = self.palette()
        # Use ``Base`` (the editor's text-area background) so the gutter
        # blends seamlessly with the editor body — pre-fix we used
        # ``AlternateBase`` which produced a visibly different stripe to
        # the left of the text and the user reported it as "不协调".
        bg = palette.color(QPalette.ColorRole.Base)
        fg = palette.color(QPalette.ColorRole.PlaceholderText)
        if not fg.isValid():
            fg = palette.color(QPalette.ColorRole.WindowText)
            fg.setAlpha(140)
        painter.fillRect(event.rect(), bg)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        painter.setPen(fg)
        right_pad = 4
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - right_pad,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _update_line_number_area_width(self, _block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def _highlight_current_line(self) -> None:
        # Subtle current-line highlight matches Qt's CodeEditor demo —
        # keeps the user oriented when a long .tex scrolls past several
        # screens. Derive the highlight from ``Base`` so it stays
        # gentle relative to the (now-matching) gutter background:
        # a slightly-tinted version of the editor body itself.
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        selection = QTextEdit.ExtraSelection()
        base = self.palette().color(QPalette.ColorRole.Base)
        # Pick the brightness shift that nudges *toward* contrast: a
        # dark theme needs a lighter tint; a light theme a slightly
        # darker one. ``lightness < 128`` is the standard dark check.
        line_color = base.lighter(115) if base.lightness() < 128 else base.darker(105)
        selection.format.setBackground(line_color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
