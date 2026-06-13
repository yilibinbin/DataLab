from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QStackedWidget


class CurrentPageStack(QStackedWidget):
    """QStackedWidget whose layout hints come only from the current page."""

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        if page is None:
            return super().sizeHint()
        return page.sizeHint()

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        if page is None:
            return super().minimumSizeHint()
        return page.minimumSizeHint()
