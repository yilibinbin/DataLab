from __future__ import annotations

import base64
from importlib import import_module
import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app_desktop.panels import _refresh_visible_table_min_widths
from tools.scan_desktop_gui_schema import scan_window
from tools.scan_desktop_gui_schema import _combo_index_for_data
from tools.scan_desktop_gui_schema import _force_smallest_left_splitter


@pytest.fixture
def window(qtbot: Any) -> Any:
    QApplication.instance() or QApplication([])
    window_cls = cast(Any, import_module("app_desktop.window").ExtrapolationWindow)
    win = window_cls()
    qtbot.addWidget(win)
    win.resize(1400, 900)
    win.show()
    QApplication.processEvents()
    return win


def test_gui_schema_scan_reports_no_issues(window: Any) -> None:
    report = scan_window(window)

    assert report["issues"] == []
    assert report["checks"]["languages"] == ["zh", "en"]
    assert report["checks"]["root_plot_display"] is True
    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True
    assert report["checks"]["workspace_result_restore"] is True


def test_gui_schema_scan_uses_real_workspace_restore(window: Any) -> None:
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    window.result_edit.setPlainText("before")
    window.result_plot_bytes = png_1x1

    report = scan_window(window)

    assert report["checks"]["workspace_result_restore"] is True


def test_gui_schema_scan_reports_missing_help_as_issue(window: Any) -> None:
    window.root_equations_help_button.setToolTip("")

    report = scan_window(window, refresh_language=False)

    assert any("root equations help tooltip missing" in issue for issue in report["issues"])


def test_gui_schema_scan_reports_broken_root_plot_display(window: Any, monkeypatch: Any) -> None:
    def ignore_plot_update(_image_data: bytes) -> None:
        window.result_plot_bytes = None
        window.result_plot_label.clear()

    monkeypatch.setattr(window, "_update_result_plot", ignore_plot_update)

    report = scan_window(window)

    assert report["checks"]["root_plot_display"] is False
    assert any("root plot display failed" in issue for issue in report["issues"])


def test_root_scan_plot_layout_keeps_left_panel_without_horizontal_scrollbar(window: Any) -> None:
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
    )
    window.mode_combo.setCurrentIndex(_combo_index_for_data(window.mode_combo, "root_solving"))
    window.root_mode_combo.setCurrentIndex(_combo_index_for_data(window.root_mode_combo, "scan_multiple"))
    window.root_equations_edit.setPlainText("x^2-A")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "-2", "upper": "2"}])
    window.generate_plots_checkbox.setChecked(True)
    window._update_result_plot(png_1x1)
    window.tabs.setCurrentIndex(window.result_tab_index)
    window.result_tabs.setCurrentIndex(window.result_tabs.indexOf(window.result_plot_scroll.parentWidget()))
    QApplication.processEvents()

    _force_smallest_left_splitter(window)

    horizontal_bar = window._left_scroll.horizontalScrollBar()
    assert window._main_splitter.sizes()[0] >= window._main_splitter_left_min_width
    assert horizontal_bar.maximum() == 0
    assert not horizontal_bar.isVisible()


def test_visible_table_min_widths_recompute_down_when_content_shrinks(qtbot: Any) -> None:
    QApplication.instance() or QApplication([])
    container = QWidget()
    layout = QVBoxLayout(container)
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(["very long header name", "another very long header name"])
    table.setItem(0, 0, QTableWidgetItem("value"))
    layout.addWidget(table)
    qtbot.addWidget(container)
    container.show()
    QApplication.processEvents()

    _refresh_visible_table_min_widths(container)
    wide_width = table.minimumWidth()
    table.setColumnCount(1)
    table.setHorizontalHeaderLabels(["x"])
    QApplication.processEvents()
    _refresh_visible_table_min_widths(container)

    assert table.minimumWidth() < wide_width
