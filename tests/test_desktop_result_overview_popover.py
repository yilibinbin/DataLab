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

from PySide6.QtCore import Qt
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
