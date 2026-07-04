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
