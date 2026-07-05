"""Stage ① of the 2-pane layout refactor: the compute-mode selector lives on the
in-window toolbar, not in a left-rail ``mode_section``.

Per the 2026-07-05 spec: ``mode_combo`` moves onto the workbench toolbar (left, after
the DataLab identity label). It must stay the SAME widget (30+ ``self.mode_combo``
references), keep driving ``_on_mode_change`` → ``mode_stack.setCurrentIndex`` for all 5
modes, and be a descendant of the toolbar (``workbench_bar``), NOT the macOS menu bar.

These tests encode WHY the move is correct: they assert the downstream per-mode config
switch (mode_stack index), not merely the combo's own value.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


# The 5 modes and the mode_stack index each must select (mirrors _on_mode_change).
_MODE_TO_STACK_INDEX = {
    "extrapolation": 0,
    "error": 1,
    "fitting": 2,
    "root_solving": 3,
    "statistics": 4,
}


def test_mode_combo_is_on_the_toolbar(window: Any) -> None:
    """``mode_combo`` must be a descendant of the in-window toolbar, not the menu bar."""
    combo = window.mode_combo
    assert isinstance(combo, QComboBox)
    toolbar = window.workbench_bar
    assert combo in toolbar.findChildren(QComboBox), (
        "mode_combo must live on the in-window toolbar (workbench_bar)"
    )


def test_mode_combo_is_left_of_the_workspace_buttons(window: Any) -> None:
    """The mode selector sits on the LEFT of the toolbar (after the identity label,
    before 新建), matching the spec's 'toolbar left dropdown' decision."""
    combo = window.mode_combo
    new_btn = window.new_workspace_button
    # Both are in the same toolbar layout; the mode combo's x is left of 新建.
    combo_x = combo.mapTo(window, combo.rect().topLeft()).x()
    new_x = new_btn.mapTo(window, new_btn.rect().topLeft()).x()
    assert combo_x < new_x, "mode selector must be left of the 新建 button on the toolbar"


def test_each_mode_still_switches_the_per_mode_config(window: Any) -> None:
    """Changing the toolbar mode combo must still drive ``_on_mode_change`` →
    ``mode_stack.setCurrentIndex`` for every mode — the real downstream effect, not
    merely the combo's own currentData. Fails if the move severs the signal wiring."""
    combo = window.mode_combo
    stack = window.mode_stack
    for mode, expected_index in _MODE_TO_STACK_INDEX.items():
        # Find the combo item whose data == mode and select it (drives the signal).
        idx = next(i for i in range(combo.count()) if combo.itemData(i) == mode)
        combo.setCurrentIndex(idx)
        QApplication.processEvents()
        assert stack.currentIndex() == expected_index, (
            f"selecting mode {mode!r} on the toolbar must switch mode_stack to "
            f"index {expected_index}, got {stack.currentIndex()}"
        )


def test_mode_section_not_a_visible_left_rail_card(window: Any) -> None:
    """The old ``mode_section`` QGroupBox card must no longer occupy the left config
    rail (the mode selector is on the toolbar now). If the attribute is kept for
    compatibility it must not be a visible descendant of the config rail."""
    mode_section = getattr(window, "mode_section", None)
    if mode_section is not None:
        rail = window.workbench_config_content
        from PySide6.QtWidgets import QWidget

        assert mode_section not in rail.findChildren(QWidget), (
            "mode_section must no longer be a card in the left config rail"
        )
