"""QSyntaxHighlighter for LaTeX code in the desktop app."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QApplication


def _is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    return app.palette().window().color().lightness() < 128


def _make_fmt(color_dark: str, color_light: str, italic: bool = False, bold: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    color = color_dark if _is_dark() else color_light
    fmt.setForeground(QColor(color))
    if italic:
        fmt.setFontItalic(True)
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    return fmt


class LatexHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for LaTeX source code."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rebuild_rules()

    def _rebuild_rules(self):
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = [
            # Comments (highest priority — applied last so it overrides)
            (re.compile(r"%.*$", re.MULTILINE), _make_fmt("#8b949e", "#6e7781", italic=True)),
            # Environments: \begin{...} and \end{...}
            (re.compile(r"\\(?:begin|end)\{[^}]*\}"), _make_fmt("#d2a8ff", "#8250df", bold=True)),
            # Commands: \commandname
            (re.compile(r"\\[a-zA-Z@]+\*?"), _make_fmt("#6cb6ff", "#0550ae")),
            # Braces
            (re.compile(r"[{}]"), _make_fmt("#ffa657", "#bc4c00")),
            # Brackets
            (re.compile(r"[\[\]]"), _make_fmt("#79c0ff", "#0969da")),
            # Alignment &
            (re.compile(r"&"), _make_fmt("#ff7b72", "#cf222e")),
            # Inline math $...$
            (re.compile(r"\$[^$]*\$"), _make_fmt("#7ee787", "#116329")),
        ]

    def refresh_theme(self):
        """Call when system theme changes to update colors."""
        self._rebuild_rules()
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
