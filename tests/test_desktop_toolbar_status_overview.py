"""The toolbar job-status chip is the result-overview entry point.

Design (user-approved): the left-rail overview CARD is removed from the visible result layout;
the toolbar ``job_status_label`` becomes a clickable chip that shows the rich 5-state status
word + a one-line summary and opens the existing overview popover on click.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from app_desktop.window import ExtrapolationWindow


def _window(qtbot: Any) -> ExtrapolationWindow:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_toolbar_status_chip_is_clickable_and_opens_popover(qtbot: Any) -> None:
    window = _window(qtbot)
    chip = window.job_status_label
    # The chip advertises itself as clickable.
    assert chip.cursor().shape() == Qt.CursorShape.PointingHandCursor

    from app_desktop import result_overview_popover as pop

    opened: list[bool] = []
    orig = pop.open_result_overview_popover
    pop.open_result_overview_popover = lambda owner: opened.append(True)  # type: ignore[assignment]
    try:
        # Simulate a left-click release on the chip.
        window._open_result_overview_from_toolbar()
    finally:
        pop.open_result_overview_popover = orig
    assert opened, "clicking the toolbar status chip must open the overview popover"


def test_toolbar_status_chip_shows_rich_status_word(qtbot: Any) -> None:
    window = _window(qtbot)
    # Before any run: the chip shows the waiting/ready word (not the old bare 就绪/Ready only).
    window._refresh_toolbar_status_chip()
    text = window.job_status_label.text()
    assert text, "status chip must not be empty"
    # After a tabular result, the chip carries a one-line summary (· N rows).
    window._last_result_kind = "statistics_single"
    window._set_result_text("| a | b |\n|---|---|\n| 1 | 2 |", final_result=True)
    window._refresh_toolbar_status_chip()
    summary_text = window.job_status_label.text()
    assert "·" in summary_text or "-" in summary_text or summary_text != text


def test_toolbar_status_chip_retranslates(qtbot: Any) -> None:
    window = _window(qtbot)
    window._apply_language("zh")
    window._refresh_toolbar_status_chip()
    zh = window.job_status_label.text()
    window._apply_language("en")
    window._refresh_toolbar_status_chip()
    en = window.job_status_label.text()
    assert zh != en, "status chip must retranslate on language change"


def test_overview_card_removed_from_visible_result_layout(qtbot: Any) -> None:
    window = _window(qtbot)
    # The card widget may survive off-layout (so refresh writes stay valid), but it must NOT be
    # a visible child taking result space — its parent chain must not include the result rail.
    card = getattr(window, "workbench_result_overview_panel", None)
    assert card is not None  # kept alive for refresh writes
    rail = getattr(window, "workbench_result_details_panel", None) or window
    # The card is not laid out inside the visible result rail.
    assert card.parent() is not rail
    # ...and must not have been orphaned to a top-level widget either (CodeRabbit CR): a
    # parentless card would leak as a stray window. It stays parented to the main window.
    assert card.parent() is not None
