"""History panel collapse-by-default (4·4): the history section starts collapsed to a
header row; clicking the header expands it. This de-emphasises the space-hungry history
list per the 2026-07-05 result-panel cleanup.
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
def panel(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win.workbench_history_panel


def test_history_collapsed_by_default(panel: Any) -> None:
    assert panel.is_history_collapsed() is True
    # The body (entry list + action buttons) is hidden when collapsed.
    assert panel.entry_list.isVisible() is False
    assert panel.restore_button.isVisible() is False


def test_history_toggle_expands_and_collapses(panel: Any) -> None:
    panel.set_history_collapsed(False)
    QApplication.processEvents()
    assert panel.is_history_collapsed() is False
    assert panel.entry_list.isVisible() is True

    panel.set_history_collapsed(True)
    QApplication.processEvents()
    assert panel.is_history_collapsed() is True
    assert panel.entry_list.isVisible() is False


def test_history_header_click_toggles(panel: Any) -> None:
    assert panel.is_history_collapsed() is True
    panel.toggle_history_collapsed()
    QApplication.processEvents()
    assert panel.is_history_collapsed() is False
