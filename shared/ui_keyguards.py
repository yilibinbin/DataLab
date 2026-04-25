"""
UI event filters / key guards shared by desktop views.

Currently includes ArrowKeyGuard to prevent ↑/↓ keys from moving focus when a
QCheckBox has focus (while keeping other widgets' arrow-key behavior intact).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QCheckBox


class ArrowKeyGuard(QObject):
    """Swallow Up/Down arrow key events when a QCheckBox has focus."""

    def eventFilter(  # noqa: N802 - Qt naming convention
        self, obj: QObject, event: QEvent
    ) -> bool:
        try:
            if event.type() in (
                QEvent.Type.KeyPress,
                QEvent.Type.KeyRelease,
            ):
                if isinstance(obj, QCheckBox) and isinstance(event, QKeyEvent):
                    key = event.key()
                    if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                        return True
        except Exception:
            return False
        return False
