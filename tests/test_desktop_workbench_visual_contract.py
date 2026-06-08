from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_OBJECT,
    STATUS_STRIP_OBJECT,
    SUPPORTED_VISUAL_HEIGHT,
    SUPPORTED_VISUAL_WIDTH,
    TOOLBAR_OBJECT,
    WORKSPACE_CANVAS_OBJECT,
    visual_contract_issues,
    workbench_region_metrics,
)


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(SUPPORTED_VISUAL_WIDTH, SUPPORTED_VISUAL_HEIGHT)
    window.show()
    QApplication.processEvents()
    return window


def test_workbench_exposes_three_column_visual_regions(qtbot: Any) -> None:
    window = _window(qtbot)

    metrics = workbench_region_metrics(window)

    for name in (
        TOOLBAR_OBJECT,
        CONFIG_RAIL_OBJECT,
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
