"""Reachability acceptance test for every desktop config control.

This is the HARD gate for the icon-ified menu-bar redesign. It encodes the bug
class the user caught: a control that gets "hidden on the wrong page" or silently
reparented. For every config control we assert two things after performing the
*visible*, user-operable gate that reveals it:

1. ``widget.isVisibleTo(window) is True`` — the control is genuinely reachable.
2. ``widget.parent() is <the same object as before the gate action>`` — the gate
   revealed it *in place*; nothing was reparented (the single-parent invariant).

The reparent guard is the stronger check: ``isVisibleTo`` alone would pass even if
a redesign moved the widget under a different parent, which is exactly what hid
controls last time. This test must pass on the clean baseline BEFORE the menus are
added (proving the baseline is reachable) and keep passing afterward.
"""

from __future__ import annotations

import os
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

# Stack-page index for the free-form text editor inside the input-mode stack
# (table on page 0, text on page 1 — mirrors panels._STACK_PAGE_TEXT).
_DATA_STACK_TEXT_PAGE = 1


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


def _assert_reachable_in_place(window: Any, widget: Any, gate: Callable[[], None]) -> None:
    """Run ``gate`` then assert ``widget`` is visible with an UNCHANGED parent."""
    parent_before = widget.parent()
    gate()
    assert widget.isVisibleTo(window) is True, (
        f"{widget.objectName() or widget!r} not visible after its gate action"
    )
    assert widget.parent() is parent_before, (
        f"{widget.objectName() or widget!r} was reparented by its gate action "
        f"(before={parent_before!r}, after={widget.parent()!r})"
    )


# --- Always-visible controls (no gate) ------------------------------------

_ALWAYS_VISIBLE = (
    "mode_combo",
    "method_combo",
    "mpmath_precision_spin",
    "uncertainty_digits_spin",
    "parallel_mode_combo",
    "parallel_max_workers_spin",
    "parallel_reserve_cores_spin",
    "parallel_nested_policy_combo",
    "generate_latex_checkbox",
    "generate_plots_checkbox",
    "verbose_checkbox",
    "run_button",
)


@pytest.mark.parametrize("attr", _ALWAYS_VISIBLE)
def test_always_visible_control_reachable_in_place(window: Any, attr: str) -> None:
    widget = getattr(window, attr)
    _assert_reachable_in_place(window, widget, gate=lambda: None)


# --- Gated-but-reachable controls -----------------------------------------


def test_manual_data_edit_reachable_via_input_mode_stack(window: Any) -> None:
    """manual_data_edit lives on page 1 of the input-mode QStackedWidget."""
    widget = window.manual_data_edit
    _assert_reachable_in_place(
        window,
        widget,
        gate=lambda: window._data_stack.setCurrentIndex(_DATA_STACK_TEXT_PAGE),
    )


# --- Data-input controls (manual table + data-file path) ------------------


def test_manual_table_reachable_in_default_state(window: Any) -> None:
    """manual_table is the default input view (table page, manual box shown).

    It must be reachable with NO gate action — the workbench opens on manual
    entry. If a redesign moved it behind a page or hid the manual box on start,
    this fails (isVisibleTo False) instead of silently masking the control.
    """
    assert hasattr(window, "manual_table")
    _assert_reachable_in_place(window, window.manual_table, gate=lambda: None)


def test_use_file_checkbox_reachable_in_default_state(window: Any) -> None:
    """The 使用数据文件 toggle is always visible in the input rail."""
    assert hasattr(window, "use_file_checkbox")
    _assert_reachable_in_place(window, window.use_file_checkbox, gate=lambda: None)


def test_data_file_edit_reachable_via_use_file_checkbox(window: Any) -> None:
    """data_file_edit (the data-file path field) is hidden until the user checks
    使用数据文件, which reveals file_box in place."""
    assert hasattr(window, "data_file_edit")
    _assert_reachable_in_place(
        window,
        window.data_file_edit,
        gate=lambda: window.use_file_checkbox.setChecked(True),
    )


# --- Constants input control ----------------------------------------------


def test_input_constants_editor_reachable_via_constants_mode(window: Any) -> None:
    """The constants editor (input_constants_editor) is hidden in extrapolation
    mode and revealed by switching to a mode that consumes constants (误差传递).

    NOTE: the earlier review draft referenced ``use_constants_file_checkbox`` /
    ``constants_file_edit`` — those attrs do NOT exist on the live window (only
    defensive ``hasattr``-guarded references remain). The real, user-operable
    constants control is ``input_constants_editor`` (a ConstantsEditor); that is
    what this asserts reachable.
    """
    assert hasattr(window, "input_constants_editor")
    widget = window.input_constants_editor

    def gate() -> None:
        idx = window.mode_combo.findData("error")
        assert idx >= 0, "error mode not found in mode_combo"
        window.mode_combo.setCurrentIndex(idx)

    _assert_reachable_in_place(window, widget, gate=gate)


_LATEX_GATED = (
    "latex_input_precision_spin",
    "output_file_edit",
    "dcolumn_checkbox",
    "latex_group_size_spin",
    "caption_checkbox",
)


@pytest.mark.parametrize("attr", _LATEX_GATED)
def test_latex_config_control_reachable_via_generate_latex_checkbox(window: Any, attr: str) -> None:
    """The LaTeX config group is revealed by checking generate_latex_checkbox."""
    widget = getattr(window, attr)
    _assert_reachable_in_place(
        window,
        widget,
        gate=lambda: window.generate_latex_checkbox.setChecked(True),
    )


def test_caption_edit_reachable_via_latex_then_caption_checkbox(window: Any) -> None:
    """caption_edit is doubly-gated: hidden until generate_latex_checkbox reveals
    the LaTeX group AND caption_checkbox is ticked (which _toggle_caption_input
    reveals in place). Missing either gate leaves it hidden."""
    assert hasattr(window, "caption_edit")

    def gate() -> None:
        window.generate_latex_checkbox.setChecked(True)
        window.caption_checkbox.setChecked(True)

    _assert_reachable_in_place(window, window.caption_edit, gate=gate)


_RESULT_NUMERIC_GATED = ("display_digits_spin", "scientific_checkbox")


@pytest.mark.parametrize("attr", _RESULT_NUMERIC_GATED)
def test_result_numeric_control_reachable_via_result_tab(window: Any, attr: str) -> None:
    """display_digits_spin / scientific_checkbox live in the result numeric tab.

    They sit inside ``self.tabs`` (hidden while empty), so the gate must both
    populate a result and switch to the numeric subtab.
    """
    widget = getattr(window, attr)

    def gate() -> None:
        _drive_non_empty_result(window)
        numeric_index = window.result_tabs_indices["numeric"]
        window.result_tabs.setCurrentIndex(numeric_index)

    _assert_reachable_in_place(window, widget, gate=gate)


# --- RESULT-ONLY control: latex_engine_combo ------------------------------


def _drive_non_empty_result(window: Any) -> None:
    """Populate a minimal tabular result so ``self.tabs`` becomes visible."""
    window._set_csv_data(
        [{"x": "1", "y": "2"}],
        headers=["x", "y"],
        suggestion="r.csv",
    )


def test_latex_engine_combo_hidden_pre_result(window: Any) -> None:
    """Pre-result, the LaTeX result tab container (self.tabs) is hidden, so the
    engine picker is NOT reachable — even after switching to the latex subtab."""
    latex_index = window.result_tabs_indices["latex"]
    window.result_tabs.setCurrentIndex(latex_index)
    assert window.latex_engine_combo.isVisibleTo(window) is False


def test_latex_engine_combo_reachable_only_in_non_empty_result(window: Any) -> None:
    """latex_engine_combo is a RESULT-OUTPUT control: reachable only once a result
    populates ``self.tabs``. It must NOT be reparented to reveal it."""
    widget = window.latex_engine_combo

    def gate() -> None:
        _drive_non_empty_result(window)
        latex_index = window.result_tabs_indices["latex"]
        window.result_tabs.setCurrentIndex(latex_index)

    _assert_reachable_in_place(window, widget, gate=gate)
