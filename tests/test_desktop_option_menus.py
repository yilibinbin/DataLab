"""Behaviour tests for the two icon option menus (计算 / LaTeX).

The menus are ADDITIONAL entry points to config controls that already live in the
rail. They must:
  * exist in the menu bar, placed after 文件;
  * carry an IN-MENU editor (a mirror widget in a QWidgetAction) for each
    config-time VALUE control (spin/combo/line-edit), two-way synced to the SAME
    in-rail control — never a second copy of the real control;
  * NOT include latex_engine_combo (a result-only control);
  * for checkboxes, expose a checkable QAction kept in two-way sync with the SAME
    in-rail checkbox (no recursion, no duplicate widget);
  * for gated value editors, reveal the control's gate on edit (parent unchanged).

The mirror <-> real value-editor sync is covered in depth by
test_desktop_option_menu_editors.py; here we assert the menu STRUCTURE (which
controls are present, ordering, icons, bilingual titles) plus the checkbox mirrors.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


def _menu_titles(window: Any) -> list[str]:
    return [
        action.menu().title()
        for action in window.menuBar().actions()
        if action.menu() is not None
    ]


def test_compute_and_latex_menus_exist_after_file(window: Any) -> None:
    titles = _menu_titles(window)
    assert "计算" in titles
    assert "LaTeX" in titles
    # Placed AFTER 文件 (index 0), before the pre-existing 示例/语言/主题/帮助.
    assert titles.index("文件") == 0
    assert titles.index("计算") == 1
    assert titles.index("LaTeX") == 2


def test_all_existing_menus_have_icons(window: Any) -> None:
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is None:
            continue
        assert not menu.icon().isNull(), f"menu {menu.title()!r} has no icon"


def test_compute_menu_has_precision_and_parallel_editors(window: Any) -> None:
    editors = window._option_menu_editors
    actions = window._option_menu_editor_actions
    for key in (
        "mpmath_precision_spin",
        "uncertainty_digits_spin",
        "parallel_mode_combo",
        "parallel_max_workers_spin",
        "parallel_reserve_cores_spin",
        "parallel_nested_policy_combo",
    ):
        assert key in editors, f"计算 menu missing in-menu editor for {key}"
        assert key in actions, f"计算 menu missing QWidgetAction for {key}"
        # The mirror is a fresh widget, not the reparented real control.
        assert editors[key] is not getattr(window, key)


def test_compute_menu_has_separator_between_groups(window: Any) -> None:
    menu = window._compute_menu
    separators = [a for a in menu.actions() if a.isSeparator()]
    assert len(separators) >= 1


def test_latex_menu_has_expected_actions_and_omits_engine(window: Any) -> None:
    # LaTeX controls are exposed either as value editors (non-checkboxes) or as
    # checkable mirror actions (checkboxes). Both count as "in the LaTeX menu".
    all_keys = set(window._option_menu_editors) | set(window._option_menu_check_actions)
    for key in (
        "generate_latex_checkbox",
        "output_file_edit",
        "dcolumn_checkbox",
        "latex_group_size_spin",
        "caption_checkbox",
    ):
        assert key in all_keys, f"LaTeX menu missing action for {key}"
    # Value controls are in-menu editors; checkboxes are checkable mirror actions.
    assert "output_file_edit" in window._option_menu_editors
    assert "latex_group_size_spin" in window._option_menu_editors
    for cb in ("generate_latex_checkbox", "dcolumn_checkbox", "caption_checkbox"):
        assert cb in window._option_menu_check_actions
    # latex_engine_combo is a result-only control — must NOT be in any option menu.
    assert "latex_engine_combo" not in all_keys
    assert "latex_engine_combo" not in window._option_menu_editor_actions
    latex_titles = [a.text() for a in window._latex_menu.actions()]
    assert not any("引擎" in t or "engine" in t.lower() for t in latex_titles)


def test_checkable_action_toggles_checkbox_both_ways_without_recursion(window: Any) -> None:
    action = window._option_menu_check_actions["dcolumn_checkbox"]
    checkbox = window.dcolumn_checkbox
    # Same-widget invariant: the action drives the real checkbox, not a copy.
    assert checkbox.isChecked() is False
    assert action.isChecked() is False

    # action -> checkbox
    action.setChecked(True)
    assert checkbox.isChecked() is True
    # checkbox -> action
    checkbox.setChecked(False)
    assert action.isChecked() is False
    # round-trip again to prove no signal storm left them out of sync
    action.setChecked(True)
    assert checkbox.isChecked() is True
    action.setChecked(False)
    assert checkbox.isChecked() is False


def test_generate_latex_check_action_syncs_and_reveals_group(window: Any) -> None:
    action = window._option_menu_check_actions["generate_latex_checkbox"]
    checkbox = window.generate_latex_checkbox
    assert checkbox.isChecked() is False
    action.setChecked(True)
    assert checkbox.isChecked() is True
    # Checking it reveals the gated LaTeX config group in place.
    assert window.output_file_edit.isVisibleTo(window) is True


def test_editing_precision_mirror_changes_real_spin_in_place(window: Any) -> None:
    """Editing the in-menu mirror changes the REAL spin without reparenting it."""
    widget = window.mpmath_precision_spin
    parent_before = widget.parent()
    mirror = window._option_menu_editors["mpmath_precision_spin"]
    mirror.setValue(32)
    assert widget.value() == 32
    # The real control is not moved by the in-menu edit (single-parent invariant).
    assert widget.parent() is parent_before


def test_editing_latex_mirror_reveals_gate_in_place(window: Any) -> None:
    # generate_latex_checkbox starts unchecked, so output_file_edit is hidden.
    assert window.output_file_edit.isVisibleTo(window) is False
    widget = window.output_file_edit
    parent_before = widget.parent()
    mirror = window._option_menu_editors["output_file_edit"]
    mirror.setText("/tmp/from_menu.tex")
    # Editing the gated mirror checks the gate checkbox first, then applies.
    assert window.generate_latex_checkbox.isChecked() is True
    assert widget.isVisibleTo(window) is True
    assert widget.text() == "/tmp/from_menu.tex"
    assert widget.parent() is parent_before


def test_latex_menu_includes_input_precision_spin(window: Any) -> None:
    """latex_input_precision_spin (输入列位数) is a config-time, schema-bound LaTeX
    control and must be reachable from the LaTeX menu as a gated in-menu editor."""
    assert "latex_input_precision_spin" in window._option_menu_editors
    assert window._option_menu_gates.get("latex_input_precision_spin") == "latex"


def test_gated_checkbox_action_reveals_gate_when_triggered(window: Any) -> None:
    """A gated checkable menu action (dcolumn/caption, gate='latex') must not
    operate a control the user cannot see: triggering it from the default state
    (generate_latex unchecked) must reveal the LaTeX group so the real checkbox
    becomes visible, not just silently flip a hidden checkbox."""
    assert window.generate_latex_checkbox.isChecked() is False
    action = window._option_menu_check_actions["dcolumn_checkbox"]
    checkbox = window.dcolumn_checkbox
    assert checkbox.isVisibleTo(window) is False

    action.setChecked(True)

    assert window.generate_latex_checkbox.isChecked() is True
    assert checkbox.isChecked() is True
    assert checkbox.isVisibleTo(window) is True


def test_menu_titles_are_bilingual(window: Any) -> None:
    window._apply_language("en")
    titles = _menu_titles(window)
    assert "Compute" in titles
    assert "LaTeX" in titles
    window._apply_language("zh")
    assert "计算" in _menu_titles(window)
