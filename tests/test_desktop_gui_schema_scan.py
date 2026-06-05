from __future__ import annotations

import base64
from importlib import import_module
import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tools.scan_desktop_gui_schema import scan_window


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
