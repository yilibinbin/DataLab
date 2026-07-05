"""Options dialogs (计算 / LaTeX) — Module 3 of the LaTeX/PDF rework.

Per the 2026-07-05 spec, the inline toolbar option panels become resizable QDialog windows.
Each dialog holds the SAME real option controls (reparented once at build), so the run
pipeline keeps reading ``self.<widget>`` and there are no hidden state-holders/mirrors.

These tests encode WHY the design is correct:
* the toolbar buttons OPEN dialogs (not toggle inline panels);
* the real option controls live in the dialogs and become reachable when opened;
* editing a control in the dialog IS the run-read state (same object);
* the LaTeX dialog has NO output-path field (path is chosen at save-time in the TeX window).
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QToolButton


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


# Real controls that must live in each dialog (and stay window.<attr>).
_COMPUTE_CONTROLS = (
    "mpmath_precision_spin",
    "uncertainty_digits_spin",
    "parallel_mode_combo",
    "parallel_max_workers_spin",
    "parallel_reserve_cores_spin",
    "parallel_nested_policy_combo",
    "verbose_checkbox",
    "generate_plots_checkbox",
)
_LATEX_CONTROLS = (
    "generate_latex_checkbox",
    "dcolumn_checkbox",
    "latex_group_size_spin",
    "caption_checkbox",
    "latex_input_precision_spin",
)


def _dialog(window: Any, which: str) -> QDialog:
    attr = f"{which}_options_dialog"
    dialog = getattr(window, attr, None)
    assert isinstance(dialog, QDialog), f"missing options dialog {attr!r}"
    return dialog


def _button(window: Any, which: str) -> QToolButton:
    attr = f"workbench_{which}_options_button"
    btn = getattr(window, attr, None)
    assert isinstance(btn, QToolButton), f"missing toolbar options button {attr!r}"
    return btn


# --- The dialogs exist and are real QDialog windows ------------------------


def test_options_dialogs_are_qdialogs_not_inline_panels(window: Any) -> None:
    for which in ("compute", "latex"):
        dialog = _dialog(window, which)
        assert isinstance(dialog, QDialog)
        assert dialog.window() is dialog, f"{which} options dialog must be its own window"
        assert dialog.isModal() is False, "options dialogs must be non-modal"
    # The old inline-panel row must be gone.
    assert getattr(window, "options_panels_row", None) is None


def test_toolbar_buttons_open_the_dialogs(window: Any) -> None:
    for which in ("compute", "latex"):
        dialog = _dialog(window, which)
        button = _button(window, which)
        assert dialog.isVisible() is False, f"{which} dialog starts closed"
        button.click()
        QApplication.processEvents()
        assert dialog.isVisible() is True, f"clicking the button must open the {which} dialog"
        dialog.close()


# --- The real controls live in the dialogs and are reachable when open -----


def test_compute_controls_live_in_dialog_and_reachable_when_open(window: Any) -> None:
    dialog = _dialog(window, "compute")
    for attr in _COMPUTE_CONTROLS:
        control = getattr(window, attr)
        assert control in dialog.findChildren(type(control)), (
            f"{attr} must live inside the compute options dialog"
        )
        # Closed dialog → not visible-to-window; opened → visible.
        assert control.isVisibleTo(window) is False
    _button(window, "compute").click()
    QApplication.processEvents()
    for attr in _COMPUTE_CONTROLS:
        assert getattr(window, attr).isVisibleTo(window) is True, (
            f"{attr} must be reachable when the compute dialog is open"
        )
    dialog.close()


def test_editing_dialog_control_is_the_run_read_state(window: Any) -> None:
    """The control in the dialog IS the object the run pipeline reads — not a mirror.
    Editing it changes the value the run sees. A spy on the real signal proves it fired."""
    real = window.uncertainty_digits_spin
    fired: list[int] = []
    real.valueChanged.connect(fired.append)
    try:
        _button(window, "compute").click()
        QApplication.processEvents()
        real.setValue(7)
        assert real.value() == 7
        assert fired == [7]
    finally:
        real.valueChanged.disconnect(fired.append)


# --- LaTeX dialog has NO output-path field ---------------------------------


def test_latex_dialog_has_no_output_path_field(window: Any) -> None:
    """The output path moved to the TeX window's Save button; the LaTeX options dialog
    must NOT contain output_file_edit."""
    dialog = _dialog(window, "latex")
    output_edit = getattr(window, "output_file_edit", None)
    if output_edit is not None:
        assert output_edit not in dialog.findChildren(QLineEdit), (
            "output_file_edit must not live in the LaTeX options dialog"
        )
    for attr in _LATEX_CONTROLS:
        control = getattr(window, attr)
        assert control in dialog.findChildren(type(control)), (
            f"{attr} must live inside the LaTeX options dialog"
        )
