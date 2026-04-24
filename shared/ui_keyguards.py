"""
UI event filters / key guards shared by desktop views.

Currently includes ArrowKeyGuard to prevent ↑/↓ keys from moving focus when a
QCheckBox has focus (while keeping other widgets' arrow-key behavior intact).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QCheckBox


class ArrowKeyGuard(QObject):
    """Swallow Up/Down arrow key events when a QCheckBox has focus."""

    def eventFilter(self, obj, event):  # noqa: N802 - Qt naming convention
        try:
            if event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
                if isinstance(obj, QCheckBox):
                    key = event.key()
                    if key in (Qt.Key_Up, Qt.Key_Down):
                        return True
        except Exception:
            return False
        return False
