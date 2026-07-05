from __future__ import annotations

import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget

from app_desktop.workbench_visual_contract import (
    RESULT_RAIL_MIN_WIDTH,
    RESULT_RAIL_OBJECT,
    STATUS_STRIP_OBJECT,
    SUPPORTED_VISUAL_HEIGHT,
    SUPPORTED_VISUAL_WIDTH,
    TOOLBAR_OBJECT,
    WORKSPACE_CANVAS_MIN_WIDTH,
    WORKSPACE_CANVAS_OBJECT,
    visual_contract_issues,
    workbench_region_metrics,
)


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = cast(Any, ExtrapolationWindow)()
    qtbot.addWidget(window)
    window.resize(SUPPORTED_VISUAL_WIDTH, SUPPORTED_VISUAL_HEIGHT)
    window.show()
    QApplication.processEvents()
    return window


def _visual_contract_root(
    qtbot: Any,
    regions: dict[str, tuple[int, int, int, int]],
) -> QWidget:
    QApplication.instance() or QApplication([])
    root = QWidget()
    root.setObjectName("visual_contract_test_root")
    root.resize(900, 600)
    qtbot.addWidget(root)
    for object_name, geometry in regions.items():
        child = QWidget(root)
        child.setObjectName(object_name)
        child.setGeometry(*geometry)
        child.show()
    root.show()
    QApplication.processEvents()
    return root


def test_workbench_exposes_two_column_visual_regions(qtbot: Any) -> None:
    window = _window(qtbot)

    metrics = workbench_region_metrics(window)

    # Two-pane layout: toolbar + merged workspace pane + result rail + status strip.
    # The config rail merged into the workspace pane and is no longer a visible region.
    for name in (
        TOOLBAR_OBJECT,
        WORKSPACE_CANVAS_OBJECT,
        RESULT_RAIL_OBJECT,
        STATUS_STRIP_OBJECT,
    ):
        assert metrics[name].visible is True, name
    assert visual_contract_issues(window) == []


def test_workbench_keeps_legacy_public_widget_attributes(qtbot: Any) -> None:
    window = _window(qtbot)

    for name in (
        "manual_table",
        "mode_combo",
        "fit_expr_edit",
        "custom_params_table",
        "custom_constants_editor",
        "root_equations_edit",
        "result_tabs",
        "result_edit",
        "latex_edit",
        "run_button",
        "workbench_run_button",
    ):
        assert getattr(window, name, None) is not None, name


def test_visual_contract_reports_minimum_width_violations(qtbot: Any) -> None:
    # Two-pane: only the merged workspace pane + result rail have width contracts now.
    root = _visual_contract_root(
        qtbot,
        {
            TOOLBAR_OBJECT: (0, 0, 900, 40),
            WORKSPACE_CANVAS_OBJECT: (
                0,
                40,
                WORKSPACE_CANVAS_MIN_WIDTH - 1,
                500,
            ),
            RESULT_RAIL_OBJECT: (
                WORKSPACE_CANVAS_MIN_WIDTH,
                40,
                RESULT_RAIL_MIN_WIDTH - 1,
                500,
            ),
            STATUS_STRIP_OBJECT: (0, 540, 900, 40),
        },
    )

    issues = visual_contract_issues(root)

    assert {
        (issue["kind"], issue["widget"])
        for issue in issues
    } >= {
        ("workspace_canvas_width", WORKSPACE_CANVAS_OBJECT),
        ("result_rail_width", RESULT_RAIL_OBJECT),
    }


def test_visual_contract_reports_missing_regions_and_invalid_order(qtbot: Any) -> None:
    # Two-pane order: the merged workspace pane must sit left of the result rail. Here
    # workspace.x (650) > result.x (100) → a region_order issue; toolbar is missing.
    root = _visual_contract_root(
        qtbot,
        {
            WORKSPACE_CANVAS_OBJECT: (650, 40, WORKSPACE_CANVAS_MIN_WIDTH, 500),
            RESULT_RAIL_OBJECT: (100, 40, RESULT_RAIL_MIN_WIDTH, 500),
            STATUS_STRIP_OBJECT: (0, 540, 900, 40),
        },
    )

    issues = visual_contract_issues(root)

    assert {"kind": "missing_workbench_region", "widget": TOOLBAR_OBJECT} in issues
    order_issue = next(issue for issue in issues if issue["kind"] == "region_order")
    assert order_issue["widget"] == "workbench"
    assert order_issue["positions"] == {
        "workspace": 650,
        "result": 100,
    }
