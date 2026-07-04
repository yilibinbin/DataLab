"""Inline toolbar options panels (计算 / LaTeX) for the desktop workbench.

Per the 2026-07-04 INLINE amendment (dual-model VERDICT: INLINE), low-frequency options
live in a toggle panel dropped under the toolbar — NOT a floating ``Qt.Popup`` window. A
``QComboBox`` inside a ``Qt.Popup`` can be dismissed by the macOS Cocoa grab when its own
dropdown opens (a bug that is invisible offscreen, so it always passes CI and only fails in
production on Mac). A normal ``QWidget`` child toggled ``setVisible`` avoids the grab
entirely, keeps ``isVisibleTo(window)`` meaningful, and keeps each control's parent stable
from build time — so the reachability sweep only needs a trivial "open the panel" gate.

This module is a reusable host: it builds the checkable toolbar button + the empty panel
and wires the toggle. It creates NO option controls — ``panels.py`` fills each panel with
the REAL controls (reparented, never recreated, so their schema keys survive).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

__all__ = ["build_options_panel", "bind_options_toggle", "add_form_row", "add_separator"]


def build_options_panel(key: str) -> QWidget:
    """Build an empty inline (non-popup) options panel.

    The panel is a plain ``QWidget`` (no ``Qt.Popup`` flag), hidden initially, whose
    ``QVBoxLayout`` the caller fills with real controls. Because it is an ordinary layout
    child it never becomes a separate top-level window and never triggers the nested-popup
    Cocoa grab. Pair with :func:`bind_options_toggle` to drive its visibility from a
    checkable toolbar button.
    """
    panel = QWidget()
    panel.setObjectName(f"{key}_options_panel")
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(6)
    panel.setVisible(False)
    return panel


def bind_options_toggle(button: Any, panel: QWidget) -> None:
    """Make ``button`` (checkable) show/hide ``panel``.

    A plain one-way visibility toggle: the button drives the panel and nothing drives the
    button back, so no recursion guard is needed. Seeds the panel from the button's current
    checked state so the two never start out of sync.
    """
    button.setCheckable(True)
    panel.setVisible(button.isChecked())
    button.toggled.connect(panel.setVisible)


def add_form_row(
    panel_layout: QVBoxLayout, label: QWidget | None, field: QWidget
) -> None:
    """Add a ``label: field`` row to a panel layout (label may be ``None``)."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    if label is not None:
        row.addWidget(label)
    row.addWidget(field, 1)
    panel_layout.addLayout(row)


def add_separator(panel_layout: QVBoxLayout) -> None:
    """Add a thin horizontal separator between option groups."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    panel_layout.addWidget(line)
