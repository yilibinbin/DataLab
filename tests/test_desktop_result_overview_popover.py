"""Tests for the result-overview popover (Part C).

The popover is a NEW top-level popup (``QWidget`` with ``Qt.WindowType.Popup``)
that reads the SAME result-state source as the existing overview card and shows
the full overview (method / value / uncertainty / elapsed / #points). It must not
reparent or move any existing overview widget — the single-parent invariant.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


def _drive_non_empty_result(window: Any) -> None:
    window._set_csv_data(
        [{"x": "1", "y": "2"}, {"x": "3", "y": "4"}],
        headers=["x", "y"],
        suggestion="r.csv",
    )


def test_points_shows_zero_for_empty_tabular_result(window: Any) -> None:
    """An empty tabular result (0 rows, N headers) must show 0 points — NOT the column
    count. The falsy-``rows`` fallback used the column count, so a 0-row/3-col table
    displayed '3' points (CodeRabbit finding)."""
    from app_desktop.result_overview_popover import open_result_overview_popover

    window._set_csv_data([], headers=["x", "y", "z"], suggestion="r.csv")
    popover = open_result_overview_popover(window)
    assert popover._datalab_value_labels["points"].text() == "0", (
        "empty tabular result must show 0 points, not the column count"
    )


def test_overview_card_is_clickable_and_opens_popover(window: Any) -> None:
    from app_desktop.result_overview_popover import open_result_overview_popover

    popover = open_result_overview_popover(window)
    assert isinstance(popover, QWidget)
    # Top-level popup: parented to window but its own top-level window.
    assert bool(popover.windowFlags() & Qt.WindowType.Popup)
    assert popover.isVisible() is True


def test_popover_does_not_reparent_existing_overview_widgets(window: Any) -> None:
    from app_desktop.result_overview_popover import open_result_overview_popover

    tracked = (
        "workbench_result_overview_panel",
        "workbench_result_status_badge",
        "workbench_result_overview",
        "workbench_result_overview_meta",
    )
    parents_before = {name: getattr(window, name).parent() for name in tracked}
    open_result_overview_popover(window)
    for name in tracked:
        assert getattr(window, name).parent() is parents_before[name], (
            f"{name} was reparented by opening the popover"
        )


def test_popover_shows_full_overview_fields_from_same_source(window: Any) -> None:
    from app_desktop.result_overview_popover import open_result_overview_popover

    _drive_non_empty_result(window)
    popover = open_result_overview_popover(window)
    text = _all_text(popover)
    # Field labels present (method / value|uncertainty / elapsed / #points).
    assert "方法" in text or "Method" in text
    assert "用时" in text or "Elapsed" in text
    assert "点数" in text or "Points" in text
    # Reads the same tabular result: 2 rows populated above.
    assert "2" in text


def test_popover_widgets_are_new_not_the_existing_overview(window: Any) -> None:
    from app_desktop.result_overview_popover import open_result_overview_popover

    popover = open_result_overview_popover(window)
    # None of the popover's descendants may be the existing overview widgets.
    existing = {
        id(window.workbench_result_overview),
        id(window.workbench_result_status_badge),
        id(window.workbench_result_overview_meta),
        id(window.workbench_result_overview_panel),
    }
    descendants = {id(child) for child in popover.findChildren(QWidget)}
    assert existing.isdisjoint(descendants)


def _all_text(widget: QWidget) -> str:
    from PySide6.QtWidgets import QLabel

    parts = []
    for label in widget.findChildren(QLabel):
        parts.append(label.text())
    return " ".join(parts)


def _release_event(button: Qt.MouseButton) -> Any:
    """A MouseButtonRelease QMouseEvent for the given button at the card origin.

    Uses the non-deprecated constructor that takes an explicit ``QPointingDevice``
    (the position-only overloads are deprecated in Qt 6).
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent, QPointingDevice

    pos = QPointF(1.0, 1.0)
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
        QPointingDevice.primaryPointingDevice(),
    )


def test_only_left_click_release_opens_popover(window: Any, monkeypatch: Any) -> None:
    """The card's click filter must open the popover on a LEFT release only.

    A right/middle release passing through the same filter must be ignored —
    otherwise a right-click (context intent) would spuriously pop the overview.
    We spy on ``open_result_overview_popover`` (the filter's callee) rather than
    checking value/visibility, so the test fails if the button guard is dropped
    and the filter fires on every button.
    """
    import app_desktop.result_overview_popover as mod

    mod.install_overview_popover_trigger(window)
    card = window.workbench_result_overview_panel
    filt = window._result_overview_popover_filter

    calls: list[int] = []
    monkeypatch.setattr(
        mod, "open_result_overview_popover", lambda owner: calls.append(1)
    )

    # Right release: filter sees it but must NOT open the popover.
    filt.eventFilter(card, _release_event(Qt.MouseButton.RightButton))
    assert calls == [], "right-click release must not open the overview popover"

    # Middle release: also ignored.
    filt.eventFilter(card, _release_event(Qt.MouseButton.MiddleButton))
    assert calls == [], "middle-click release must not open the overview popover"

    # Left release: opens exactly once.
    filt.eventFilter(card, _release_event(Qt.MouseButton.LeftButton))
    assert calls == [1], "left-click release must open the overview popover once"

    # A non-mouse event through the same filter is a no-op too.
    filt.eventFilter(card, QEvent(QEvent.Type.Enter))
    assert calls == [1]
