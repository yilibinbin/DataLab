from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_result_rail_has_overview_and_data_table(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.workbench_result_overview is not None
    assert isinstance(window.workbench_result_table, QTableWidget)
    assert window.tabs.parentWidget() is window.workbench_result_rail
    assert window.result_tabs.parentWidget() is window.tabs.widget(window.result_tab_index)


def test_result_rail_mirrors_csv_rows(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window.refresh_workbench_result_rail()

    assert window.workbench_result_table.rowCount() == 1
    assert window.workbench_result_table.columnCount() == 2
    assert window.workbench_result_table.item(0, 0).text() == "2.47e-3"
    assert "1" in window.workbench_result_overview.text()


def test_result_rail_clears_when_csv_data_resets(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")
    window._reset_csv_data()

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() in {"暂无结果", "No results"}


def test_result_rail_summary_relocalizes_on_language_switch(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")

    window._apply_language("en")
    assert "Result data: 1 rows" in window.workbench_result_overview.text()
    window._apply_language("zh")
    assert "结果数据：1 行" in window.workbench_result_overview.text()
