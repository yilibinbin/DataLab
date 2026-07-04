"""Behaviour tests for the INLINE toolbar options panels (计算 / LaTeX).

Per the 2026-07-04 INLINE amendment (dual-model VERDICT: INLINE), the low-frequency
options move OUT of the left-rail "选项" QGroupBox INTO two toggle panels dropped under
the toolbar. Each panel is a NORMAL ``QWidget`` child (NOT ``Qt.Popup``) toggled visible
by a checkable toolbar button. Because it is an ordinary layout child:

* ``isVisibleTo(window)`` is meaningful (no separate top-level window),
* the control's parent is stable from build time (no reparent-on-open),
* a ``QComboBox`` inside opens its dropdown WITHOUT the macOS Cocoa grab dismissing the
  panel — so the combo test below is meaningful offscreen, unlike a ``Qt.Popup`` host.

These tests are RED until the panels are implemented; they encode WHY each property
matters (see the docstrings), not merely that a value was set.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QToolButton, QWidget


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


# Controls that move into the 计算 (compute) panel and the LaTeX panel. Each stays a
# ``window.<attr>`` so the 30+ tests that read these attributes keep working.
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
    "output_file_edit",
    "latex_input_precision_spin",
    "dcolumn_checkbox",
    "latex_group_size_spin",
    "caption_checkbox",
)


def _button(window: Any, which: str) -> QToolButton:
    attr = f"workbench_{which}_options_button"
    btn = getattr(window, attr, None)
    assert isinstance(btn, QToolButton), f"missing toolbar options button {attr!r}"
    return btn


def _panel(window: Any, which: str) -> QWidget:
    attr = f"{which}_options_panel"
    panel = getattr(window, attr, None)
    assert isinstance(panel, QWidget), f"missing inline options panel {attr!r}"
    return panel


# --- The panel is INLINE, not a floating popup -----------------------------


def test_panels_are_not_qt_popup_windows(window: Any) -> None:
    """The panels must be ordinary layout children, NOT ``Qt.Popup`` top-levels.

    This is the load-bearing INLINE guarantee: a ``Qt.Popup`` host is a separate
    top-level window whose embedded ``QComboBox`` can be dismissed by the macOS Cocoa
    grab (untestable offscreen). A layout child cannot be — so we assert the panel is
    not a window and its window() is the main window.
    """
    for which in ("compute", "latex"):
        panel = _panel(window, which)
        assert panel.isWindow() is False, f"{which} panel must not be a top-level window"
        assert bool(panel.windowFlags() & Qt.WindowType.Popup) is False, (
            f"{which} panel must not carry the Qt.Popup flag"
        )
        assert panel.window() is window, f"{which} panel must belong to the main window"


# --- Hidden until toggled; controls reachable when open --------------------


def test_compute_panel_hidden_until_button_toggled(window: Any) -> None:
    """Panel starts hidden (rail is freed); toggling the button reveals it and every
    moved control becomes reachable with a STABLE parent (no reparent-on-open)."""
    panel = _panel(window, "compute")
    button = _button(window, "compute")
    assert button.isCheckable() is True
    assert panel.isVisible() is False, "compute panel must start collapsed"

    # Snapshot each control's parent BEFORE opening — it must not change on open.
    parents_before = {
        attr: getattr(window, attr).parent() for attr in _COMPUTE_CONTROLS
    }

    button.setChecked(True)
    QApplication.processEvents()
    assert panel.isVisible() is True, "toggling the button must reveal the compute panel"

    for attr in _COMPUTE_CONTROLS:
        control = getattr(window, attr)
        assert control.isVisibleTo(window) is True, (
            f"{attr} must be visible-to-window once the compute panel is open"
        )
        assert control.parent() is parents_before[attr], (
            f"{attr} parent changed on panel open — reparent-on-open is forbidden"
        )


def test_toggling_button_off_collapses_panel(window: Any) -> None:
    """Un-checking the button hides the panel again (space returns to the result area)."""
    panel = _panel(window, "compute")
    button = _button(window, "compute")
    button.setChecked(True)
    QApplication.processEvents()
    assert panel.isVisible() is True
    button.setChecked(False)
    QApplication.processEvents()
    assert panel.isVisible() is False


# --- The combo-in-inline-panel test the whole pivot was for ----------------


def test_combo_in_inline_panel_opens_without_closing_panel(window: Any) -> None:
    """Opening a combo's dropdown inside the panel must NOT close the panel and must NOT
    reparent the combo. Meaningful offscreen precisely because the panel is a normal
    layout child (a ``Qt.Popup`` host would make this a tautology and hide the real
    macOS grab bug). Fails if the panel regresses to a ``Qt.Popup`` container."""
    panel = _panel(window, "compute")
    button = _button(window, "compute")
    button.setChecked(True)
    QApplication.processEvents()

    combo = window.parallel_mode_combo
    assert isinstance(combo, QComboBox)
    parent_before = combo.parent()

    combo.showPopup()
    QApplication.processEvents()

    assert panel.isVisible() is True, (
        "opening a combo dropdown must not collapse the inline panel"
    )
    assert combo.parent() is parent_before, (
        "the combo must not be reparented when its dropdown opens"
    )
    combo.hidePopup()


# --- The 选项 box must LEAVE the left rail ---------------------------------


def test_options_box_no_longer_in_left_config_rail(window: Any) -> None:
    """The whole point: the 选项 panel must not sit in the left config rail anymore, so
    the result area gains the freed space. If ``options_box`` still exists it must not be
    a descendant of the config rail."""
    rail = getattr(window, "workbench_config_content", None) or getattr(
        window, "left_container", None
    )
    assert rail is not None, "could not resolve the left config rail container"
    options_box = getattr(window, "options_box", None)
    if options_box is not None:
        rail_descendants = set(rail.findChildren(QWidget))
        assert options_box not in rail_descendants, (
            "options_box must no longer live in the left config rail"
        )


# --- LaTeX gated controls reachable inside the LaTeX panel -----------------


def test_latex_gated_controls_reachable_in_panel(window: Any) -> None:
    """Opening the LaTeX panel and ticking 生成 LaTeX inside it reveals the gated LaTeX
    controls — they must not be stranded invisible."""
    panel = _panel(window, "latex")
    button = _button(window, "latex")
    button.setChecked(True)
    QApplication.processEvents()
    assert panel.isVisible() is True

    gate = window.generate_latex_checkbox
    assert gate.isVisibleTo(window) is True, "the LaTeX gate must be visible in the panel"
    gate.setChecked(True)
    QApplication.processEvents()

    for attr in ("latex_input_precision_spin", "dcolumn_checkbox", "latex_group_size_spin"):
        control = getattr(window, attr)
        assert control.isVisibleTo(window) is True, (
            f"{attr} must be reachable once 生成 LaTeX is ticked inside the LaTeX panel"
        )
