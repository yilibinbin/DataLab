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
    for screenshot in manifest["screenshots"]:
        regions = screenshot["regions"]
        spec = MODE_WORKBENCH_SPECS[screenshot["mode"]]

        result_metric = regions["workbench_result_overview_panel"]
        assert result_metric["visible"] is True
        assert result_metric["width"] >= 160
        assert result_metric["height"] >= 48

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


def test_screenshot_report_issue_status_controls_cli_exit() -> None:
    from tools.capture_desktop_gui_screens import report_has_issues

    assert report_has_issues({"screenshots": []}) is True
    assert report_has_issues({"screenshots": [{"issue_count": 0}]}) is False
    assert report_has_issues({"screenshots": [{"issue_count": 0}, {"issue_count": 1}]}) is True


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
