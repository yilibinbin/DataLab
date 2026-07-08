"""Toolbar-launched history popup.

The history panel is a full interactive widget (entry list + restore/compare/budget/rename/pin/
delete/export buttons) — too large for the thin toolbar. Instead a toolbar 历史 button opens it
in a top-level ``Qt.Popup`` window, mirroring how the status chip opens the result-overview
popover. Unlike that popover (which builds its own read-only labels), the history panel is
interactive, so the REAL ``workbench_history_panel`` widget is reparented into the popup when
shown and back out when hidden — its buttons keep working and no state is duplicated.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


def _build_popup(owner: Any) -> QWidget | None:
    popup = getattr(owner, "_history_popup", None)
    if popup is None:
        popup = QWidget(owner, Qt.WindowType.Popup)
        popup.setObjectName("history_popup")
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        owner._history_popup = popup
    return popup


def toggle_history_popup(owner: Any) -> None:
    """Open (or close) the history popup, hosting the real history panel, anchored to the
    toolbar 历史 button."""
    panel = getattr(owner, "workbench_history_panel", None)
    if panel is None:
        return
    popup = _build_popup(owner)
    if popup is None:
        return
    if popup.isVisible():
        popup.hide()
        return

    # Host the real panel inside the popup for this showing (reparents it in).
    layout = popup.layout()
    if panel.parent() is not popup:
        layout.addWidget(panel)
    panel.show()

    # Refresh so the list reflects the latest history before showing.
    refresh = getattr(panel, "refresh", None)
    if callable(refresh):
        refresh()

    anchor = getattr(owner, "history_button", None)
    if anchor is not None:
        try:
            global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
            popup.move(global_pos)
        except (RuntimeError, AttributeError):
            pass
    popup.adjustSize()
    popup.show()
    popup.raise_()
