"""History moved to a toolbar 历史 button that opens the panel in a popup."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app_desktop.window import ExtrapolationWindow


def _window(qtbot: Any) -> ExtrapolationWindow:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_history_button_in_toolbar_and_panel_off_result_layout(qtbot: Any) -> None:
    window = _window(qtbot)
    assert hasattr(window, "history_button"), "toolbar must have a 历史 button"
    panel = window.workbench_history_panel
    assert panel is not None  # kept alive
    # Not laid out in the visible result rail — parented to the window, hidden until popup.
    rail = getattr(window, "workbench_result_details_panel", None)
    assert panel.parent() is not rail


def test_history_button_toggles_popup_hosting_real_panel(qtbot: Any) -> None:
    window = _window(qtbot)
    window._toggle_history_popup()
    popup = window._history_popup
    assert popup.isVisible() is True
    # The REAL panel (not a copy) is hosted so its restore/compare/etc. buttons work.
    assert window.workbench_history_panel.parent() is popup
    window._toggle_history_popup()
    assert popup.isVisible() is False
