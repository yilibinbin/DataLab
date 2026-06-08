from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tools.scan_desktop_gui_schema import MODES, RESULT_TABS, ROOT_SOLVING_SUBMODES, SCAN_WIDTHS

EXPECTED_SCENARIO_COUNT = len(SCAN_WIDTHS) * 2 * len(RESULT_TABS) * (
    (len(MODES) - 1) + len(ROOT_SOLVING_SUBMODES)
)
EXPECTED_CURRENT_HELP_GAP_COUNT = 0


def _issue_summary(issues: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[str(issue.get("kind", ""))] = counts.get(str(issue.get("kind", "")), 0) + 1
    return ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items()))


def test_redesign_scan_covers_all_modes_and_languages(qapp: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import scan_window

    window = ExtrapolationWindow()
    try:
        report = scan_window(window, refresh_language=True, strict=True)
        assert report["checks"]["scenario_count"] >= 30
        if report["issues"]:
            assert report["checks"]["scenario_count"] == EXPECTED_SCENARIO_COUNT
            assert report["checks"]["missing_help_affordance_count"] == EXPECTED_CURRENT_HELP_GAP_COUNT
            assert len(report["issues"]) == EXPECTED_CURRENT_HELP_GAP_COUNT
            assert {issue["kind"] for issue in report["issues"]} == {"missing_help_affordance"}
            assert any(issue["details"].get("class_name") == "QTableWidget" for issue in report["issues"])
            pytest.xfail(f"Current GUI strict scan reports structured issues: {_issue_summary(report['issues'])}")
        assert report["issues"] == []
    finally:
        window.deleteLater()


def test_redesign_scan_returns_structured_strict_report(qapp: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import scan_window

    window = ExtrapolationWindow()
    try:
        report = scan_window(window, refresh_language=True, strict=True)
        assert report["checks"]["scenario_count"] == EXPECTED_SCENARIO_COUNT
        assert report["checks"]["strict"] is True
        assert isinstance(report["issues"], list)
        assert report["issues"] == report["structured_issues"]
        assert all(isinstance(issue, dict) for issue in report["issues"])
        assert all(
            {"kind", "scenario", "language", "widget", "details"}.issubset(issue)
            for issue in report["issues"]
        )
        assert report["checks"]["missing_help_affordance_count"] == EXPECTED_CURRENT_HELP_GAP_COUNT
        assert report["issues"] == []
    finally:
        window.deleteLater()


def test_config_horizontal_scrollbar_gate_detects_overflow(qapp: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import (
        ScreenScenario,
        _horizontal_scrollbar_issues,
    )

    window = ExtrapolationWindow()
    try:
        window.resize(1440, 900)
        window.show()
        huge_label = QLabel("X" * 500)
        window.workbench_config_layout.addWidget(huge_label)

        issues = _horizontal_scrollbar_issues(
            window,
            [ScreenScenario(key="zh:fitting", language="zh", mode="fitting")],
        )

        assert any(issue["kind"] == "workbench_config_horizontal_scrollbar" for issue in issues)
    finally:
        window.deleteLater()
