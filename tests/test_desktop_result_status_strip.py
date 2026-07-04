"""Tests for the minimal always-visible result status strip (Part D).

A NEW minimal strip (status badge + method + elapsed) driven by the same
result/run-state source, always visible even when panels collapse. It must be
built from NEW widgets — not the pre-existing shell footer (workbench_status_strip)
nor the overview card's status badge.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

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
        [{"x": "1", "y": "2"}],
        headers=["x", "y"],
        suggestion="r.csv",
    )


def test_status_strip_exists_and_visible(window: Any) -> None:
    strip = window._result_status_strip
    assert isinstance(strip, QWidget)
    assert strip.isVisibleTo(window) is True


def test_status_strip_has_status_method_elapsed_labels(window: Any) -> None:
    assert isinstance(window._result_status_strip_status, QWidget)
    assert isinstance(window._result_status_strip_method, QWidget)
    assert isinstance(window._result_status_strip_elapsed, QWidget)


def test_status_strip_is_new_not_the_shell_footer_or_overview_badge(window: Any) -> None:
    strip = window._result_status_strip
    # Not the pre-existing shell footer strip.
    assert strip is not getattr(window, "workbench_status_strip", None)
    # Its status label is a brand-new widget, not the overview card's badge.
    assert window._result_status_strip_status is not window.workbench_result_status_badge


def test_status_strip_reflects_result_state(window: Any) -> None:
    from app_desktop.result_status_strip import refresh_result_status_strip

    # Empty baseline -> waiting.
    refresh_result_status_strip(window)
    assert "等待" in window._result_status_strip_status.text()

    # Non-empty tabular result -> ready.
    _drive_non_empty_result(window)
    refresh_result_status_strip(window)
    status_text = window._result_status_strip_status.text()
    assert "就绪" in status_text or "已就绪" in status_text

    # Method label reflects the current method/mode selection.
    assert window._result_status_strip_method.text().strip() != ""


def test_status_strip_updates_via_refresh_result_rail(window: Any) -> None:
    # The strip is driven by the same refresh entry point as the overview card.
    _drive_non_empty_result(window)  # calls refresh_workbench_result_rail internally
    status_text = window._result_status_strip_status.text()
    assert "就绪" in status_text or "已就绪" in status_text
