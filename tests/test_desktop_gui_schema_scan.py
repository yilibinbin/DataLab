from __future__ import annotations

import base64
from importlib import import_module
import os
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app_desktop.panels import _refresh_visible_table_min_widths
from app_desktop.theme import SUPPORTED_MIN_WINDOW_WIDTH
import tools.capture_desktop_gui_screens as capture_tool
from tools.capture_desktop_gui_screens import LEFT_RAIL_CAPTURE_WIDTHS
from tools.scan_desktop_gui_schema import ScreenScenario
from tools.scan_desktop_gui_schema import LEFT_RAIL_SCROLLBAR_SCAN_WIDTHS
from tools.scan_desktop_gui_schema import SCAN_WIDTHS
from tools.scan_desktop_gui_schema import _combo_index_for_data
from tools.scan_desktop_gui_schema import _force_smallest_left_splitter
from tools.scan_desktop_gui_schema import _state_ownership_issues
from tools.scan_desktop_gui_schema import scan_window


def _issue_message(issue: object) -> str:
    if isinstance(issue, dict):
        return str(issue.get("message", ""))
    return str(issue)


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
    assert report["structured_issues"] == []
    assert report["checks"]["languages"] == ["zh", "en"]
    assert report["checks"]["root_plot_display"] is True
    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True
    assert report["checks"]["workspace_result_restore"] is True


def test_left_rail_scrollbar_scan_covers_requested_capture_widths(window: Any) -> None:
    report = scan_window(window)

    assert SUPPORTED_MIN_WINDOW_WIDTH == 1280
    assert tuple(report["checks"]["scenario_widths"]) == (1280, 1440, 1680)
    assert LEFT_RAIL_SCROLLBAR_SCAN_WIDTHS == (1280, 1440, 1680)
    assert SCAN_WIDTHS == (1280, 1440, 1680)
    assert LEFT_RAIL_CAPTURE_WIDTHS == (1280, 1440, 1680)
    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True


def test_screenshot_capture_records_actual_size_when_qt_adjusts_window(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        capture_tool,
        "_capture_scenarios",
        lambda *, width, height: [
            ScreenScenario(
                key="en:extrapolation",
                language="en",
                mode="extrapolation",
                result_tab="numeric",
                width=width,
                height=height,
            )
        ],
    )

    report = capture_tool.capture_desktop_gui_screens(out=tmp_path, width=1280, height=800)

    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True
    assert report["count"] == 1
    screenshot = report["screenshots"][0]
    assert screenshot["requested_size"] == {"width": 1280, "height": 800}
    assert screenshot["actual_size"]["width"] >= 1280
    assert screenshot["actual_size"]["height"] == 800
    assert screenshot["window_size_adjusted"] is (screenshot["actual_size"] != screenshot["requested_size"])
    assert screenshot["issue_count"] == 0


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

    assert all(isinstance(issue, str) for issue in report["issues"])
    assert any("root equations help tooltip missing" in _issue_message(issue) for issue in report["issues"])
    assert any(issue["kind"] == "missing_tooltip" for issue in report["structured_issues"])


def test_gui_schema_scan_reports_unbound_required_widget_in_options_panel(window: Any) -> None:
    """The global options moved from ``options_box`` into the 计算/LaTeX toolbar DIALOGS.
    The schema-binding scan MUST audit those dialogs — auditing the now-empty
    ``options_box`` would pass vacuously and mask a required-but-unbound widget.

    Simulate a binding regression: strip the schema key off a required dialog widget
    (keeping it required) and assert the scan flags ``compute_options_dialog``."""
    from app_desktop.ui_schema_binder import SCHEMA_KEY_PROPERTY, SCHEMA_REQUIRED_PROPERTY

    spin = window.mpmath_precision_spin
    assert spin.property(SCHEMA_REQUIRED_PROPERTY) is True
    assert spin.property(SCHEMA_KEY_PROPERTY)  # bound today
    spin.setProperty(SCHEMA_KEY_PROPERTY, "")  # make it required-but-unbound

    report = scan_window(window, refresh_language=False)

    assert any(
        issue["kind"] == "schema_binding" and issue["widget"] == "compute_options_dialog"
        for issue in report["structured_issues"]
    ), "scan did not flag the unbound required widget in the compute options dialog"


def test_state_ownership_scan_reports_wrong_model_path_binding(window: Any) -> None:
    scenario = ScreenScenario(key="test", language="zh", mode="fitting")
    window.fit_expr_edit.setProperty("datalab_model_path", "compute.config.fitting.custom.expression")

    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "wrong_model_path_binding"
        and issue["widget"] == "fitting.custom.expression"
        and issue["details"]["expected"] == "compute.formulas.fitting.custom.expression.raw_text"
        and issue["details"]["found"] == "compute.config.fitting.custom.expression"
        for issue in issues
    )


def test_gui_schema_scan_reports_broken_root_plot_display(window: Any, monkeypatch: Any) -> None:
    def ignore_plot_update(_image_data: bytes) -> None:
        window.result_plot_bytes = None
        window.result_plot_label.clear()

    monkeypatch.setattr(window, "_update_result_plot", ignore_plot_update)

    report = scan_window(window)

    assert report["checks"]["root_plot_display"] is False
    assert all(isinstance(issue, str) for issue in report["issues"])
    assert any("root plot display failed" in _issue_message(issue) for issue in report["issues"])
    assert any(issue["kind"] == "root_plot_display" for issue in report["structured_issues"])


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
