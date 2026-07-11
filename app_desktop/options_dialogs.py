"""Toolbar options as resizable QDialog windows (计算 / LaTeX).

Replaces the inline toggle panels (``workbench_options_panel``) with real, resizable,
non-modal dialog windows — per the 2026-07-05 spec (user chose "真独立窗口"). Each dialog
holds the SAME real option controls (reparented ONCE at build time into the dialog), so:

* the run pipeline keeps reading ``self.mpmath_precision_spin`` / ``self.latex_group_size_spin``
  etc. — unchanged; the controls just live in the dialog now;
* there are NO hidden state-holders and NO mirror widgets (a hidden real would fail the
  reachability sweep, which enumerates every schema-keyed input);
* the reachability sweep reaches each control by OPENING the dialog (a QDialog child is
  ``isVisibleTo(window)`` only while the dialog is shown), then the control's parent is the
  stable dialog content — no reparent-on-open.

A QDialog is either open or closed; unlike the abandoned QStackedWidget page, it never
"hides a control on the wrong page". Non-modal so the user can keep interacting with the
main window while the options dialog is open.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QVBoxLayout, QWidget

__all__ = [
    "OptionsDialog",
    "build_options_dialog",
    "bind_options_button",
    "add_separator",
]


def add_separator(layout: QVBoxLayout) -> None:
    """Add a thin horizontal separator between option groups in a dialog's layout."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(line)


class OptionsDialog(QDialog):
    """A resizable, non-modal dialog hosting a single content widget.

    The content widget (built by ``panels.py`` from the real option controls) is added to
    the dialog's layout once. The dialog is created hidden; :func:`bind_options_button`
    wires a toolbar button to open it.
    """

    def __init__(self, parent: QWidget, object_name: str, content: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        # Non-modal: keep the main window usable while options are open.
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(content)
        self._content = content

    def open_dialog(self) -> None:
        """Show the dialog and bring it to the front (idempotent)."""
        self.show()
        self.raise_()
        self.activateWindow()


def build_options_dialog(
    owner: QWidget, object_name: str, title_zh: str, title_en: str, content: QWidget
) -> OptionsDialog:
    """Build an :class:`OptionsDialog` parented to ``owner``, hidden until opened."""
    dialog = OptionsDialog(owner, object_name, content)
    dialog.setWindowTitle(title_zh)
    register = getattr(owner, "_register_text", None)
    if callable(register):
        register(dialog, title_zh, title_en, "setWindowTitle")
    return dialog


def bind_options_button(button: Any, dialog: OptionsDialog) -> None:
    """Make ``button`` open ``dialog`` on click (not a toggle — a dialog opens/closes on
    its own). The button is NOT checkable: clicking always brings the dialog to front."""
    button.setCheckable(False)
    button.clicked.connect(lambda _checked=False: dialog.open_dialog())
