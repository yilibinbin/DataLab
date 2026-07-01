"""Desktop theme detection + Auto/Light/Dark mode (P1-5).

The desktop dark theme used to be Windows-only: system detection read the
Windows registry and the refresh was a Windows-gated 5 s timer, so on macOS
(the primary build target) and Linux the OS dark mode was never followed.
Detection now uses Qt's cross-platform ``QStyleHints.colorScheme()`` and the
window offers an explicit Auto/Light/Dark menu that pins the palette.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _make_window():
    QApplication.instance() or QApplication([])
    from app_desktop.window import ExtrapolationWindow

    win = ExtrapolationWindow()
    win._confirm_workspace_discard_or_save = lambda: True
    return win


def test_system_theme_detection_is_cross_platform():
    """_detect_system_light_mode must exist and return a tri-state (True light,
    False dark, None unknown) without requiring Windows."""
    from app_desktop.resources import _detect_system_light_mode

    result = _detect_system_light_mode()
    assert result in (True, False, None)


def test_theme_menu_offers_auto_light_dark(qtbot):
    win = _make_window()
    qtbot.addWidget(win)

    theme_menu = None
    for action in win.menuBar().actions():
        if action.text() in ("主题", "Theme"):
            theme_menu = action.menu()
    assert theme_menu is not None, "Theme menu is missing"
    assert len(theme_menu.actions()) == 3
    # Exactly one entry checked by default (Auto), enforced by the action group.
    checked = [a for a in theme_menu.actions() if a.isChecked()]
    assert len(checked) == 1


def test_set_theme_mode_pins_palette_and_ignores_system_changes(qtbot):
    win = _make_window()
    qtbot.addWidget(win)

    win.set_theme_mode("dark")
    assert win._theme_mode == "dark"
    assert win._windows_light_pref is False

    win.set_theme_mode("light")
    assert win._theme_mode == "light"
    assert win._windows_light_pref is True

    # In a pinned (non-auto) mode, a system-theme signal must not override it.
    win._maybe_refresh_system_theme()
    assert win._windows_light_pref is True

    win.set_theme_mode("auto")
    assert win._theme_mode == "auto"
