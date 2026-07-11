"""Bounded message dialogs.

A plain ``QMessageBox`` grows its height with the message text, so a very long body (e.g. a
full LaTeX compile log) can push the OK button past the bottom of the screen, leaving it
unreachable (user-reported). ``show_bounded_critical`` keeps the dialog compact: a short
summary line stays in the main area, and the long detail goes into the built-in, SCROLLABLE
"Show Details" pane — so the buttons never move off-screen no matter how long the detail is.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

# Bodies longer than this (chars or lines) go into the collapsible/scrollable detail pane.
_MAX_INLINE_CHARS = 400
_MAX_INLINE_LINES = 8


def _is_long(text: str) -> bool:
    return len(text) > _MAX_INLINE_CHARS or text.count("\n") + 1 > _MAX_INLINE_LINES


def show_bounded_critical(
    parent: QWidget | None, title: str, text: str, *, summary: str | None = None
) -> None:
    """Show a critical dialog whose OK button never leaves the screen.

    Short ``text`` renders inline as usual. Long ``text`` is moved to the scrollable
    "Show Details" pane, with ``summary`` (or a default) shown inline so the user still gets a
    one-line explanation without an unbounded dialog.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    if _is_long(text):
        box.setText(summary or title)
        box.setDetailedText(text)
    else:
        box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()
