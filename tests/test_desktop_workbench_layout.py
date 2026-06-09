from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QScrollArea, QSplitter

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_MIN_WIDTH,
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_MIN_WIDTH,
    RESULT_RAIL_OBJECT,
    WORKSPACE_CANVAS_MIN_WIDTH,
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

    assert sizes[0] >= CONFIG_RAIL_MIN_WIDTH
    assert sizes[1] >= WORKSPACE_CANVAS_MIN_WIDTH
    assert sizes[2] >= RESULT_RAIL_MIN_WIDTH


def test_splitter_refresh_requires_three_pane_workbench(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    assert window._main_splitter.count() == 3
    window._refresh_main_splitter_left_min_width()

    assert window._main_splitter.count() == 3
    assert window._main_splitter_left_min_width >= window.workbench_config_rail.minimumWidth()


def test_splitter_clamp_preserves_side_rail_proportions_for_subminimum_center() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 320]
    clamped = _clamp_workbench_splitter_sizes([600, 120, 700], minimums, total=1620)

    assert sum(clamped) == 1620
    assert clamped[0] >= minimums[0]
    assert clamped[1] >= minimums[1]
    assert clamped[2] >= minimums[2]
    assert clamped[0] > minimums[0]
    assert clamped[2] > minimums[2]
    assert clamped == [516, 520, 584]


def test_splitter_clamp_returns_minimums_when_total_cannot_satisfy_contract() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 320]

    assert _clamp_workbench_splitter_sizes([200, 200, 200], minimums, total=600) == minimums


def test_splitter_clamp_preserves_sum_with_small_remainder() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 320]
    clamped = _clamp_workbench_splitter_sizes([321, 519, 323], minimums, total=1163)

    assert sum(clamped) == 1163
    assert all(size >= minimum for size, minimum in zip(clamped, minimums, strict=True))


def test_splitter_refresh_uses_three_pane_clamp(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)
    splitter = window._main_splitter
    splitter.setSizes([520, 584, 320])
    QApplication.processEvents()
    before = splitter.sizes()
    wide_probe = QLabel("wide probe")
    wide_probe.setMinimumWidth(before[0] + 20)
    window.workbench_config_content.layout().addWidget(wide_probe)
    QApplication.processEvents()

    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
    sizes = splitter.sizes()

    assert sizes != before
    assert sizes[1] >= window.workbench_workspace_canvas.minimumWidth()
    assert sizes[0] >= window.workbench_config_rail.minimumWidth()
    assert sizes[2] >= window.workbench_result_rail.minimumWidth()
    assert sum(sizes) == sum(before)


def test_splitter_refresh_preserves_defensive_extra_panes(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)
    splitter = window._main_splitter
    extra = QFrame()
    splitter.addWidget(extra)
    splitter.setSizes([520, 584, 320, 111])
    QApplication.processEvents()
    before = splitter.sizes()
    wide_probe = QLabel("wide probe")
    wide_probe.setMinimumWidth(before[0] + 20)
    window.workbench_config_content.layout().addWidget(wide_probe)
    QApplication.processEvents()

    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
    sizes = splitter.sizes()

    assert len(sizes) == 4
    assert sizes[0] >= window.workbench_config_rail.minimumWidth()
    assert sizes[1] >= window.workbench_workspace_canvas.minimumWidth()
    assert sizes[2] >= window.workbench_result_rail.minimumWidth()
    assert sizes[3] > 0


def test_splitter_refresh_fallback_total_excludes_extra_panes(qtbot: Any) -> None:
    class FakeSplitter:
        def __init__(self) -> None:
            self.recorded_sizes: list[int] = []

        def count(self) -> int:
            return 4

        def sizes(self) -> list[int]:
            return [0, 0, 0, 200]

        def handleWidth(self) -> int:  # noqa: N802
            return 8

        def width(self) -> int:
            return 1600

        def setSizes(self, sizes: list[int]) -> None:  # noqa: N802
            self.recorded_sizes = list(sizes)

    window = _offscreen_window(qtbot)
    fake_splitter = FakeSplitter()
    window._main_splitter = fake_splitter

    window._refresh_main_splitter_left_min_width()

    assert len(fake_splitter.recorded_sizes) == 4
    assert fake_splitter.recorded_sizes[3] == 200
    assert sum(fake_splitter.recorded_sizes) <= fake_splitter.width()


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
