from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

TOOLBAR_OBJECT = "workbench_toolbar"
CONFIG_RAIL_OBJECT = "workbench_config_rail"
WORKSPACE_CANVAS_OBJECT = "workbench_workspace_canvas"
RESULT_RAIL_OBJECT = "workbench_result_rail"
STATUS_STRIP_OBJECT = "workbench_status_strip"

SUPPORTED_VISUAL_WIDTH = 1440
SUPPORTED_VISUAL_HEIGHT = 900
CONFIG_RAIL_MIN_WIDTH = 320
CONFIG_RAIL_DEFAULT_WIDTH = 320
RESULT_RAIL_MIN_WIDTH = 320
RESULT_RAIL_DEFAULT_WIDTH = 380
WORKSPACE_CANVAS_MIN_WIDTH = 520


@dataclass(frozen=True)
class WorkbenchRegionMetric:
    object_name: str
    x: int
    y: int
    width: int
    height: int
    visible: bool


def widget_metric(root: QWidget, object_name: str) -> WorkbenchRegionMetric:
    widget = root.findChild(QWidget, object_name)
    if widget is None:
        return WorkbenchRegionMetric(object_name, 0, 0, 0, 0, False)
    geometry = widget.geometry()
    top_left = widget.mapTo(root, QPoint(0, 0))
    return WorkbenchRegionMetric(
        object_name=object_name,
        x=int(top_left.x()),
        y=int(top_left.y()),
        width=int(geometry.width()),
        height=int(geometry.height()),
        visible=bool(widget.isVisible()),
    )


def workbench_region_metrics(root: QWidget) -> dict[str, WorkbenchRegionMetric]:
    return {
        name: widget_metric(root, name)
        for name in (
            TOOLBAR_OBJECT,
            CONFIG_RAIL_OBJECT,
            WORKSPACE_CANVAS_OBJECT,
            RESULT_RAIL_OBJECT,
            STATUS_STRIP_OBJECT,
        )
    }


def visual_contract_issues(root: QWidget) -> list[dict[str, object]]:
    metrics = workbench_region_metrics(root)
    issues: list[dict[str, object]] = []
    for name, metric in metrics.items():
        if not metric.visible or metric.width <= 0 or metric.height <= 0:
            issues.append({"kind": "missing_workbench_region", "widget": name})

    config = metrics[CONFIG_RAIL_OBJECT]
    workspace = metrics[WORKSPACE_CANVAS_OBJECT]
    result = metrics[RESULT_RAIL_OBJECT]
    if config.visible and config.width < CONFIG_RAIL_MIN_WIDTH:
        issues.append(
            {"kind": "config_rail_width", "widget": CONFIG_RAIL_OBJECT, "width": config.width}
        )
    if workspace.visible and workspace.width < WORKSPACE_CANVAS_MIN_WIDTH:
        issues.append(
            {
                "kind": "workspace_canvas_width",
                "widget": WORKSPACE_CANVAS_OBJECT,
                "width": workspace.width,
            }
        )
    if result.visible and result.width < RESULT_RAIL_MIN_WIDTH:
        issues.append(
            {"kind": "result_rail_width", "widget": RESULT_RAIL_OBJECT, "width": result.width}
        )
    if config.visible and workspace.visible and result.visible:
        if not (config.x < workspace.x < result.x):
            issues.append(
                {
                    "kind": "region_order",
                    "widget": "workbench",
                    "positions": {"config": config.x, "workspace": workspace.x, "result": result.x},
                }
            )
    return issues
