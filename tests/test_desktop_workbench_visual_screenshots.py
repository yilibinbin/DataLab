from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_MIN_WIDTH,
    RESULT_RAIL_MIN_WIDTH,
    SUPPORTED_VISUAL_HEIGHT,
    SUPPORTED_VISUAL_WIDTH,
    WORKSPACE_CANVAS_MIN_WIDTH,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_workbench_screenshot_manifest_contains_region_metrics(tmp_path) -> None:
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    out = tmp_path / "gui-screens"
    report = capture_desktop_gui_screens(
        out=out,
        width=SUPPORTED_VISUAL_WIDTH,
        height=SUPPORTED_VISUAL_HEIGHT,
    )

    assert report["count"] >= 16
    for item in report["screenshots"]:
        screenshot_path = Path(item["path"])
        assert screenshot_path.is_file(), screenshot_path
        assert screenshot_path.stat().st_size > 0, screenshot_path
        assert screenshot_path.read_bytes().startswith(PNG_SIGNATURE), screenshot_path
        assert item["issue_count"] == 0
        assert item["issues"] == []
        regions = item["regions"]
        assert regions["workbench_config_rail"]["width"] >= CONFIG_RAIL_MIN_WIDTH
        assert regions["workbench_workspace_canvas"]["width"] >= WORKSPACE_CANVAS_MIN_WIDTH
        assert regions["workbench_result_rail"]["width"] >= RESULT_RAIL_MIN_WIDTH

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["screenshots"][0]["regions"]["workbench_toolbar"]["height"] >= 44


def test_screenshot_manifest_includes_common_workbench_panels(tmp_path) -> None:
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    manifest = capture_desktop_gui_screens(out=tmp_path, width=1440, height=900)

    assert manifest["screenshots"]
    assert any(
        item["mode"] == "fitting" and item["root_mode"] == "self_consistent"
        for item in manifest["screenshots"]
    )
    formula_syntaxes = {
        item["formula_syntax"]
        for item in manifest["screenshots"]
        if item["mode"] == "fitting" and item["root_mode"] == "custom"
    }
    assert {"datalab", "python", "mathematica"} <= formula_syntaxes
    assert all(
        item["formula_syntax"] == ""
        for item in manifest["screenshots"]
        if item["mode"] == "statistics"
    )
    for screenshot in manifest["screenshots"]:
        regions = screenshot["regions"]
        spec = MODE_WORKBENCH_SPECS[screenshot["mode"]]

        result_metric = regions["workbench_result_overview_panel"]
        assert result_metric["visible"] is True
        assert result_metric["width"] >= 160
        assert result_metric["height"] >= 48

        result_details_metric = regions["workbench_result_details_panel"]
        assert result_details_metric["visible"] is True
        assert result_details_metric["width"] >= 160
        assert result_details_metric["height"] >= 240

        data_metric = regions["manual_box"]
        assert data_metric["visible"] is True
        assert data_metric["width"] >= 240
        assert data_metric["height"] >= 180

        formula_metric = regions["workbench_formula_panel"]
        assert formula_metric["visible"] is bool(spec.formulas)
        if spec.formulas:
            assert formula_metric["width"] >= 160
            assert formula_metric["height"] >= 48

        variable_metric = regions["workbench_variable_panel"]
        has_variables = bool(spec.parameters or spec.tables or spec.constants)
        assert variable_metric["visible"] is has_variables
        if has_variables:
            assert variable_metric["width"] >= 160
            assert variable_metric["height"] >= 48


def test_screen_scenario_refreshes_formula_preview_without_waiting_for_debounce(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario, _apply_screen_scenario

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()

    _apply_screen_scenario(
        window,
        ScreenScenario(
            key="zh:root_solving:scalar:python",
            language="zh",
            mode="root_solving",
            root_mode="scalar",
            formula_syntax="python",
            result_tab="numeric",
            width=1440,
            height=900,
        ),
    )

    assert window.workbench_formula_language_combo.currentData() == "python"
    pixmap = window.workbench_formula_preview_label.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.height() >= 64


def test_screen_scenario_resets_formula_syntax_when_unspecified(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from app_desktop.window import ExtrapolationWindow
    from tools.capture_desktop_gui_screens import _current_formula_syntax
    from tools.scan_desktop_gui_schema import ScreenScenario, _apply_screen_scenario

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()

    _apply_screen_scenario(
        window,
        ScreenScenario(
            key="en:fitting:custom:python",
            language="en",
            mode="fitting",
            root_mode="custom",
            formula_syntax="python",
            result_tab="numeric",
            width=1440,
            height=900,
        ),
    )
    assert window.workbench_formula_language_combo.currentData() == "python"

    default_custom = ScreenScenario(
        key="en:fitting:custom",
        language="en",
        mode="fitting",
        root_mode="custom",
        result_tab="numeric",
        width=1440,
        height=900,
    )
    _apply_screen_scenario(window, default_custom)

    assert window.workbench_formula_language_combo.currentData() == "datalab"
    assert _current_formula_syntax(window, default_custom) == "datalab"

    _apply_screen_scenario(
        window,
        ScreenScenario(
            key="en:fitting:self_consistent",
            language="en",
            mode="fitting",
            root_mode="self_consistent",
            result_tab="numeric",
            width=1440,
            height=900,
        ),
    )

    assert window.workbench_formula_language_combo.currentData() == "datalab"


def test_screenshot_scenarios_do_not_leak_fake_result_state(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from app_desktop.window import ExtrapolationWindow
    from tools.capture_desktop_gui_screens import _prepare_screenshot_scenario
    from tools.scan_desktop_gui_schema import PNG_1X1, ScreenScenario, _apply_screen_scenario

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()

    _apply_screen_scenario(
        window,
        ScreenScenario(
            key="zh:root_solving:scan_multiple",
            language="zh",
            mode="root_solving",
            root_mode="scan_multiple",
            result_tab="image",
            width=1440,
            height=900,
        ),
    )
    assert window.result_plot_bytes == PNG_1X1

    _prepare_screenshot_scenario(
        window,
        ScreenScenario(
            key="en:fitting:self_consistent",
            language="en",
            mode="fitting",
            root_mode="self_consistent",
            result_tab="numeric",
            width=1440,
            height=900,
        ),
    )

    assert window.result_plot_bytes is None
    assert window.workbench_result_status_badge.text() == "Waiting"
    assert window.workbench_result_overview.text() == "No results"
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["numeric"]


def test_screenshot_report_issue_status_controls_cli_exit() -> None:
    from tools.capture_desktop_gui_screens import report_has_issues

    assert report_has_issues({"screenshots": []}) is True
    assert report_has_issues({"screenshots": [{"issue_count": 0}]}) is False
    assert report_has_issues({"screenshots": [{"issue_count": 0}, {"issue_count": 1}]}) is True


def test_screenshot_capture_rejects_persistent_size_mismatch(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtCore import QSize

    import tools.capture_desktop_gui_screens as capture_tool
    from tools.scan_desktop_gui_schema import ScreenScenario

    class WrongSizeImage:
        def size(self) -> QSize:
            return QSize(1439, 900)

        def width(self) -> int:
            return 1439

        def height(self) -> int:
            return 900

    class FakeWindow:
        def resize(self, *_args: object) -> None:
            pass

        def show(self) -> None:
            pass

        def grab(self) -> WrongSizeImage:
            return WrongSizeImage()

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr(capture_tool, "_create_window", FakeWindow)
    monkeypatch.setattr(
        capture_tool,
        "_capture_scenarios",
        lambda **_: [
            ScreenScenario(
                key="en:statistics",
                language="en",
                mode="statistics",
                width=1440,
                height=900,
            )
        ],
    )
    monkeypatch.setattr(capture_tool, "_prepare_screenshot_scenario", lambda *_args: None)

    with pytest.raises(RuntimeError, match="screenshot size mismatch for en:statistics"):
        capture_tool.capture_desktop_gui_screens(out=tmp_path, width=1440, height=900)


def test_screenshot_cli_returns_failure_when_manifest_has_issues(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.capture_desktop_gui_screens as capture_tool

    monkeypatch.setattr(
        capture_tool,
        "capture_desktop_gui_screens",
        lambda **_: {"screenshots": [{"issue_count": 1, "issues": [{"kind": "probe"}]}]},
    )

    assert capture_tool.main(["--out", str(tmp_path / "screens")]) == 1
