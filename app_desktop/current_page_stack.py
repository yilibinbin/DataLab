from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QStackedWidget, QWidget


class CurrentPageStack(QStackedWidget):
    """QStackedWidget whose height tracks the CURRENT page only.

    A plain QStackedWidget sizes to its tallest page, so a short mode config would sit in a hollow
    gap; capping it at Maximum policy instead clipped a mode whose config grows after layout
    (fitting→comparison). This subclass pins its own fixed height to the active page's sizeHint,
    re-syncing on page change and when the active page's layout invalidates — so it is always
    exactly as tall as the current page needs (no gap, no clip).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.currentChanged.connect(lambda _index: self._sync_height_to_current())

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()

    def _sync_height_to_current(self) -> None:
        page = self.currentWidget()
        if page is None:
            return
        # Fix the stack to the current page's preferred height so the layout neither inflates a
        # short page (gap) nor caps a taller/grown page (clip).
        self.setFixedHeight(max(page.sizeHint().height(), page.minimumSizeHint().height()))

    def event(self, evt) -> bool:  # type: ignore[no-untyped-def]
        # LayoutRequest fires when the current page's contents change size (e.g. a mode reveals
        # extra fields). Re-sync so a dynamically growing page is not clipped.
        result = super().event(evt)
        from PySide6.QtCore import QEvent

        if evt.type() == QEvent.Type.LayoutRequest:
            self._sync_height_to_current()
        return result
