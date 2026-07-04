"""Behaviour tests for the IN-MENU editors on the 计算 / LaTeX icon menus.

Per the 2026-07-04 spec amendment, each value item (spin/combo/line-edit) is a
``QWidgetAction`` hosting a NEW mirror widget two-way synced to the SAME in-rail
control. The real control stays in the config rail (no reparenting — the
reachability sweep is unaffected); the menu shows an editable copy.

These tests assert the mirror <-> real control sync in BOTH directions with no
infinite recursion, and that a gated LaTeX editor reveals its gate on edit.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


def _editor(window: Any, attr: str) -> Any:
    editors = window._option_menu_editors
    assert attr in editors, f"no in-menu editor mirror registered for {attr!r}"
    return editors[attr]


# --- Mirror widgets exist and match the real control's type/range ----------


def test_compute_value_items_are_editor_mirrors(window: Any) -> None:
    """Every compute VALUE control has a mirror editor of the matching type."""
    spins = (
        "mpmath_precision_spin",
        "uncertainty_digits_spin",
        "parallel_max_workers_spin",
        "parallel_reserve_cores_spin",
    )
    for attr in spins:
        mirror = _editor(window, attr)
        assert isinstance(mirror, QSpinBox), f"{attr} mirror should be a QSpinBox"
        real = getattr(window, attr)
        # Range mirrors the real control (source of truth), not a hard-coded guess.
        assert mirror.minimum() == real.minimum()
        assert mirror.maximum() == real.maximum()
    for attr in ("parallel_mode_combo", "parallel_nested_policy_combo"):
        mirror = _editor(window, attr)
        assert isinstance(mirror, QComboBox), f"{attr} mirror should be a QComboBox"
        assert mirror.count() == getattr(window, attr).count()


def test_mirror_is_not_the_real_control(window: Any) -> None:
    """The mirror is a fresh widget — the real control is never reparented."""
    for attr in ("mpmath_precision_spin", "parallel_mode_combo", "output_file_edit"):
        assert _editor(window, attr) is not getattr(window, attr)


# --- Spin mirror two-way sync ----------------------------------------------


def test_precision_mirror_sets_real_spin(window: Any) -> None:
    mirror = _editor(window, "mpmath_precision_spin")
    mirror.setValue(32)
    assert window.mpmath_precision_spin.value() == 32


def test_real_spin_updates_precision_mirror(window: Any) -> None:
    mirror = _editor(window, "mpmath_precision_spin")
    window.mpmath_precision_spin.setValue(64)
    assert mirror.value() == 64


def test_precision_sync_has_no_infinite_recursion(window: Any) -> None:
    """A round-trip must settle, not storm — both sides converge on one value."""
    mirror = _editor(window, "mpmath_precision_spin")
    real = window.mpmath_precision_spin
    mirror.setValue(100)
    assert real.value() == 100
    assert mirror.value() == 100
    real.setValue(250)
    assert mirror.value() == 250
    assert real.value() == 250


def test_precision_mirror_drives_real_downstream_slot(window: Any) -> None:
    """Editing the mirror must RE-RUN the real spin's downstream slots, not set the
    value silently. If the mirror->real path blocked the real's signals (a silent
    set), downstream schema/UI slots would never run. We assert the real control's
    valueChanged actually FIRED (a spy) — not merely that the value equals 7, which
    a silent set would also satisfy."""
    real = window.uncertainty_digits_spin
    fired: list[int] = []
    real.valueChanged.connect(fired.append)
    try:
        mirror = _editor(window, "uncertainty_digits_spin")
        mirror.setValue(7)
        assert real.value() == 7
        # The load-bearing assertion: the real spin's signal actually emitted, so
        # every downstream connection (schema binding, UI refresh) ran. A silent
        # real.setValue() under blockSignals would leave `fired` empty and FAIL here.
        assert fired == [7], (
            "mirror edit did not re-run the real spin's valueChanged "
            f"(downstream slots would be skipped); observed {fired!r}"
        )
    finally:
        real.valueChanged.disconnect(fired.append)


# --- Combo mirror two-way sync ---------------------------------------------


def test_combo_mirror_sets_real_combo(window: Any) -> None:
    mirror = _editor(window, "parallel_mode_combo")
    real = window.parallel_mode_combo
    target = (real.currentIndex() + 1) % real.count()
    mirror.setCurrentIndex(target)
    assert real.currentIndex() == target


def test_real_combo_updates_mirror(window: Any) -> None:
    mirror = _editor(window, "parallel_mode_combo")
    real = window.parallel_mode_combo
    target = (real.currentIndex() + 2) % real.count()
    real.setCurrentIndex(target)
    assert mirror.currentIndex() == target


def test_combo_sync_no_recursion(window: Any) -> None:
    mirror = _editor(window, "parallel_nested_policy_combo")
    real = window.parallel_nested_policy_combo
    mirror.setCurrentIndex(1)
    assert real.currentIndex() == 1
    assert mirror.currentIndex() == 1
    real.setCurrentIndex(0)
    assert mirror.currentIndex() == 0
    assert real.currentIndex() == 0


# --- LineEdit mirror two-way sync ------------------------------------------


def test_output_path_mirror_two_way(window: Any) -> None:
    mirror = _editor(window, "output_file_edit")
    assert isinstance(mirror, QLineEdit)
    real = window.output_file_edit
    mirror.setText("/tmp/out.tex")
    assert real.text() == "/tmp/out.tex"
    real.setText("/tmp/other.tex")
    assert mirror.text() == "/tmp/other.tex"


# --- Gated LaTeX editors reveal the gate on edit ---------------------------


def test_gated_latex_spin_mirror_reveals_gate(window: Any) -> None:
    """latex_input_precision_spin is gated by generate_latex_checkbox. Editing its
    MIRROR must first reveal the gate so the real control is live/visible."""
    assert window.generate_latex_checkbox.isChecked() is False
    real = window.latex_input_precision_spin
    assert real.isVisibleTo(window) is False
    mirror = _editor(window, "latex_input_precision_spin")
    # Choose a value inside the real range but different from current.
    new_value = min(real.value() + 1, real.maximum())
    if new_value == real.value():
        new_value = max(real.value() - 1, real.minimum())
    mirror.setValue(new_value)
    assert window.generate_latex_checkbox.isChecked() is True
    assert real.isVisibleTo(window) is True
    assert real.value() == new_value


def test_gated_latex_group_size_mirror_reveals_gate(window: Any) -> None:
    assert window.generate_latex_checkbox.isChecked() is False
    real = window.latex_group_size_spin
    mirror = _editor(window, "latex_group_size_spin")
    new_value = min(real.value() + 1, real.maximum())
    if new_value == real.value():
        new_value = max(real.value() - 1, real.minimum())
    mirror.setValue(new_value)
    assert window.generate_latex_checkbox.isChecked() is True
    assert real.value() == new_value


def test_gated_output_path_mirror_reveals_gate(window: Any) -> None:
    assert window.generate_latex_checkbox.isChecked() is False
    mirror = _editor(window, "output_file_edit")
    mirror.setText("/tmp/gated.tex")
    assert window.generate_latex_checkbox.isChecked() is True
    assert window.output_file_edit.text() == "/tmp/gated.tex"


# --- QWidgetAction hosting keeps the menu open while editing ----------------


def test_value_items_are_widget_actions(window: Any) -> None:
    """Each value editor is hosted in a QWidgetAction so the menu stays open while
    the user interacts with the embedded spin/combo/line-edit."""
    from PySide6.QtWidgets import QWidgetAction

    for attr in (
        "mpmath_precision_spin",
        "parallel_mode_combo",
        "output_file_edit",
        "latex_group_size_spin",
    ):
        action = window._option_menu_editor_actions[attr]
        assert isinstance(action, QWidgetAction), (
            f"{attr} value item must be a QWidgetAction hosting its mirror editor"
        )
        # The mirror is the (a descendant of the) action's default widget.
        default = action.defaultWidget()
        assert default is not None
        assert _editor(window, attr) in default.findChildren(type(_editor(window, attr))) or \
            _editor(window, attr) is default
