from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tools.scan_desktop_gui_schema import (
    FITTING_SUBMODES,
    MODES,
    RESULT_TABS,
    ROOT_SOLVING_SUBMODES,
    SCAN_WIDTHS,
)

EXPECTED_SCENARIO_COUNT = len(SCAN_WIDTHS) * 2 * len(RESULT_TABS) * (
    (len(MODES) - 2) + len(FITTING_SUBMODES) + len(ROOT_SOLVING_SUBMODES)
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
        huge_label.setMinimumWidth(5000)
        window.workbench_config_layout.addWidget(huge_label)

        issues = _horizontal_scrollbar_issues(
            window,
            [ScreenScenario(key="zh:fitting", language="zh", mode="fitting")],
        )

        config_issues = [issue for issue in issues if issue["kind"] == "workbench_config_horizontal_scrollbar"]
        assert config_issues
        assert config_issues[0]["details"]["target_width"] == 1400
        assert config_issues[0]["details"]["content_width"] > config_issues[0]["details"]["target_width"]
    finally:
        window.deleteLater()


def test_config_horizontal_scrollbar_gate_reports_missing_scroll_widget(
    qapp: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.scan_desktop_gui_schema as scanner

    monkeypatch.setattr(scanner, "_apply_screen_scenario", lambda *_args: None)
    monkeypatch.setattr(scanner, "_force_smallest_left_splitter", lambda *_args: None)

    window = SimpleNamespace(findChild=lambda *_args: None)
    issues = scanner._horizontal_scrollbar_issues(
        window,
        [scanner.ScreenScenario(key="zh:statistics", language="zh", mode="statistics")],
    )

    assert issues == [
        {
            "kind": "missing_scroll_widget",
            "scenario": "zh:statistics",
            "language": "zh",
            "widget": "workbench_config_rail",
            "message": "neither workbench_config_rail nor _left_scroll found on window",
            "details": {
                "attempted_widgets": ["workbench_config_rail", "_left_scroll"],
            },
        }
    ]


def test_visual_contract_scan_attributes_issue_to_scenario(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.scan_desktop_gui_schema as scanner
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario

    scenario = ScreenScenario(
        key="current:1440:fitting:numeric",
        language="current",
        mode="fitting",
        result_tab="numeric",
        width=1440,
    )

    monkeypatch.setattr(scanner, "_screen_scenarios", lambda *, refresh_language: [scenario])
    monkeypatch.setattr(scanner, "_legacy_language_issues", lambda window, lang: [])
    monkeypatch.setattr(scanner, "_horizontal_scrollbar_issues", lambda window, scenarios: [])
    monkeypatch.setattr(scanner, "_root_plot_display_ok", lambda window: True)
    monkeypatch.setattr(scanner, "_workspace_result_round_trip_ok", lambda window: True)
    monkeypatch.setattr(
        scanner,
        "visual_contract_issues",
        lambda window: [{"kind": "visual_probe", "widget": "workbench_workspace_canvas"}],
    )

    window = ExtrapolationWindow()
    try:
        report = scanner.scan_window(window, refresh_language=False, strict=True)
    finally:
        window.deleteLater()

    assert report["issues"] == [
        {
            "kind": "visual_probe",
            "scenario": scenario.key,
            "language": "current",
            "widget": "workbench_workspace_canvas",
            "message": "visual workbench contract issue: visual_probe",
            "details": {
                "contract_issue": {
                    "kind": "visual_probe",
                    "widget": "workbench_workspace_canvas",
                }
            },
        }
    ]


def test_visual_contract_scan_uses_stable_fallback_shape(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.scan_desktop_gui_schema as scanner
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario

    scenario = ScreenScenario(
        key="zh:1440:root:numeric",
        language="zh",
        mode="root_solving",
        result_tab="numeric",
        width=1440,
    )
    monkeypatch.setattr(scanner, "visual_contract_issues", lambda window: [{"width": 1}])

    window = ExtrapolationWindow()
    try:
        issues = scanner._workbench_visual_contract_issues(window, [scenario])
    finally:
        window.deleteLater()

    assert issues == [
        {
            "kind": "visual_contract",
            "scenario": scenario.key,
            "language": "zh",
            "widget": "workbench",
            "message": "visual workbench contract issue: visual_contract",
            "details": {"contract_issue": {"width": 1}},
        }
    ]


def test_gui_scan_reports_duplicate_state_roles(qtbot: Any) -> None:
    from PySide6.QtWidgets import QLabel

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    clone = QLabel("duplicate", window)
    clone.setObjectName("duplicated_manual_owner")
    clone.setProperty("datalab_state_role", "manual_data_owner")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)
    issue = next(issue for issue in issues if issue["kind"] == "duplicate_state_role")
    assert issue["message"]
    # Role-ownership issues use the role identifier in the shared "widget" field.
    assert issue["widget"] == "manual_data_owner"
    assert issue["details"]["count"] == 2
    assert "duplicated_manual_owner" in issue["details"]["widgets"]


def test_gui_scan_reports_missing_state_role_owner(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_box.setProperty("datalab_state_role", "")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "missing_state_role_owner" for issue in issues)


def test_gui_scan_reports_wrong_state_role_owner(qtbot: Any) -> None:
    from PySide6.QtWidgets import QLabel

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_box.setProperty("datalab_state_role", "")
    wrong = QLabel("wrong", window)
    wrong.setObjectName("wrong_manual_owner")
    wrong.setProperty("datalab_state_role", "manual_data_owner")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "wrong_state_role_owner" for issue in issues)


def test_gui_scan_reports_cross_mode_widget_sharing_from_scanner_spec(
    qtbot: Any, monkeypatch: Any
) -> None:
    from app_desktop import workbench_formula_panel as formula_panel
    from app_desktop.window import ExtrapolationWindow
    from tools import scan_desktop_gui_schema as scan
    from tools.scan_desktop_gui_schema import ScreenScenario
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, ModeWorkbenchSpec, FormulaMount

    specs = dict(MODE_WORKBENCH_SPECS)
    specs["dummy_test_mode"] = ModeWorkbenchSpec(
        mode_key="dummy_test_mode",
        mode_stack_index=99,
        formulas=(FormulaMount("fit_expr_edit", "dummy_btn", "dummy"),),
    )
    monkeypatch.setattr(scan, "MODE_WORKBENCH_SPECS", specs)
    assert "dummy_test_mode" not in formula_panel.MODE_WORKBENCH_SPECS

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = scan._state_ownership_issues(window, scenario)

    issue = next((i for i in issues if i["kind"] == "cross_mode_widget_sharing"), None)
    assert issue is not None
    assert issue["widget"] == "fit_expr_edit"
    assert "multiple modes" in issue["message"]


def test_gui_scan_reports_missing_manual_data_editor(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_table.setProperty("datalab_state_role", "")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "missing_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_duplicate_manual_data_editor(qtbot: Any) -> None:
    from PySide6.QtWidgets import QTableWidget

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    duplicate = QTableWidget(window)
    duplicate.setObjectName("duplicate_manual_table_editor")
    duplicate.setProperty("datalab_state_role", "manual_table_editor")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "duplicate_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_wrong_manual_data_editor(qtbot: Any) -> None:
    from PySide6.QtWidgets import QTableWidget

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_table.setProperty("datalab_state_role", "")
    wrong = QTableWidget(window)
    wrong.setObjectName("wrong_manual_table_editor")
    wrong.setProperty("datalab_state_role", "manual_table_editor")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "wrong_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_untagged_manual_data_table_clone(qtbot: Any) -> None:
    from PySide6.QtWidgets import QTableWidget

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    clone = QTableWidget(window.manual_box)
    clone.setObjectName("untagged_manual_table_clone")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "unexpected_manual_data_table" for issue in issues)


def test_gui_scan_reports_mirrored_manual_data_clone_outside_manual_box(qtbot: Any) -> None:
    from PySide6.QtWidgets import QPlainTextEdit, QTableWidget

    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    table_clone = QTableWidget(window.workbench_workspace_content)
    table_clone.setObjectName("workbench_data_preview_table")
    text_clone = QPlainTextEdit(window.workbench_workspace_content)
    text_clone.setObjectName("workbench_editor_stack")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    mirrored_widgets = {
        issue["widget"]
        for issue in issues
        if issue["kind"] == "mirrored_editable_state_widget"
    }
    assert {"workbench_data_preview_table", "workbench_editor_stack"} <= mirrored_widgets


def test_gui_scan_reports_duplicate_state_role_definitions(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools import scan_desktop_gui_schema as scan
    from tools.scan_desktop_gui_schema import ScreenScenario

    specs = dict(MODE_WORKBENCH_SPECS)
    fitting = specs["fitting"]
    root = specs["root_solving"]
    conflicting_mount = replace(root.tables[0], state_role=fitting.parameters[0].state_role)
    specs["root_solving"] = replace(root, tables=(conflicting_mount,))
    monkeypatch.setattr(scan, "MODE_WORKBENCH_SPECS", specs)

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    scenario = ScreenScenario(key="test", language="en", mode="fitting")

    issues = scan._state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "duplicate_state_role_definition" for issue in issues)


def test_gui_scan_reports_spec_collision_with_baseline_state_role(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools import scan_desktop_gui_schema as scan
    from tools.scan_desktop_gui_schema import ScreenScenario

    specs = dict(MODE_WORKBENCH_SPECS)
    root = specs["root_solving"]
    conflicting_mount = replace(root.tables[0], state_role="manual_data_owner")
    specs["root_solving"] = replace(root, tables=(conflicting_mount,))
    monkeypatch.setattr(scan, "MODE_WORKBENCH_SPECS", specs)

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    scenario = ScreenScenario(key="test", language="en", mode="root_solving")

    issues = scan._state_ownership_issues(window, scenario)
    issue = next(issue for issue in issues if issue["kind"] == "duplicate_state_role_definition")

    assert issue["details"]["first_widget"] == "manual_box"
    assert issue["details"]["second_widget"] == root.tables[0].widget_attr


def test_gui_scan_reports_wrong_owner_without_unexpected_owner_when_object_name_missing(
    qtbot: Any,
) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    mount = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    widget = getattr(window, mount.widget_attr)
    widget.setObjectName("")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "wrong_state_role_owner" and issue["widget"] == mount.state_role
        for issue in issues
    )
    assert not any(issue["kind"] == "unexpected_editable_state_owner" for issue in issues)


def test_gui_scan_reports_named_parameter_table_clone_without_state_role(qtbot: Any) -> None:
    from app_desktop.parameter_table import ParameterTable
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    mount = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    clone = ParameterTable(window)
    clone.setObjectName(mount.widget_attr)

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "unexpected_editable_state_owner" and issue["widget"] == mount.widget_attr
        for issue in issues
    )


def test_gui_scan_reports_missing_model_path_binding(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_model_bindings import MODEL_PATH_PROPERTY
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    mount = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    getattr(window, mount.widget_attr).setProperty(MODEL_PATH_PROPERTY, "")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "missing_model_path_binding" and issue["widget"] == mount.widget_attr
        for issue in issues
    )


def test_gui_scan_reports_duplicate_model_path_binding(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_model_bindings import MODEL_PATH_PROPERTY
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    first = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    second = MODE_WORKBENCH_SPECS["root_solving"].tables[0]
    first_path = getattr(window, first.widget_attr).property(MODEL_PATH_PROPERTY)
    getattr(window, second.widget_attr).setProperty(MODEL_PATH_PROPERTY, first_path)

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "duplicate_model_path_binding"
        and first.widget_attr in issue["details"]["widgets"]
        and second.widget_attr in issue["details"]["widgets"]
        for issue in issues
    )


def test_gui_scan_rejects_empty_scenario_list(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.window import ExtrapolationWindow
    from tools import scan_desktop_gui_schema as scan

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(scan, "_screen_scenarios", lambda *, refresh_language: [])

    with pytest.raises(ValueError, match="duplicate-state scan requires"):
        scan.scan_window(window)
