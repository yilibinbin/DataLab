from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QSplitter

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_OBJECT,
    WORKSPACE_CANVAS_OBJECT,
    visual_contract_issues,
)


def _offscreen_window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_main_area_uses_config_workspace_result_regions(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    splitter = window.findChild(QSplitter, "workbench_main_splitter")

    assert splitter is not None
    assert splitter.count() == 3
    assert isinstance(splitter.widget(0), QScrollArea)
    assert splitter.widget(0).objectName() == CONFIG_RAIL_OBJECT
    assert isinstance(splitter.widget(1), QScrollArea)
    assert splitter.widget(1).objectName() == WORKSPACE_CANVAS_OBJECT
    assert isinstance(splitter.widget(2), QFrame)
    assert splitter.widget(2).objectName() == RESULT_RAIL_OBJECT
    assert visual_contract_issues(window) == []


def test_splitter_cannot_hide_config_or_result_regions(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    splitter = window._main_splitter
    splitter.setSizes([1, 1438, 1])
    QApplication.processEvents()
    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
    sizes = splitter.sizes()

    assert sizes[0] >= 260
    assert sizes[1] >= 520
    assert sizes[2] >= 320


def test_status_strip_owns_workspace_and_job_status(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    assert window.workspace_status_label.parentWidget() is window.workbench_status_strip
    assert window.job_status_label.parentWidget() is window.workbench_status_strip
    assert window.workspace_status_label.text() in {"已保存", "Saved", "未保存", "Unsaved"}
    assert window.job_status_label.text() in {"就绪", "Ready", "运行中", "Running"}


def test_status_strip_tracks_dirty_and_running_state(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)
    window._apply_language("en")

    window._mark_workspace_dirty()
    assert window.workspace_status_label.text() == "Unsaved"

    window._set_button_to_stop_mode()
    assert window.job_status_label.text() == "Running"

    window._set_button_to_run_mode()
    assert window.job_status_label.text() == "Ready"
