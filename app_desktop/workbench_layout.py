"""Three-zone desktop workbench shell helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import (
    CONFIG_RAIL_WIDTH,
    RESULT_RAIL_WIDTH,
    STATUS_STRIP_HEIGHT,
    WORKSPACE_GUTTER,
    workbench_region_style,
)
from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_MIN_WIDTH,
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_MIN_WIDTH,
    RESULT_RAIL_OBJECT,
    STATUS_STRIP_OBJECT,
    WORKSPACE_CANVAS_MIN_WIDTH,
    WORKSPACE_CANVAS_OBJECT,
)


def _frame(object_name: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setStyleSheet(workbench_region_style())
    return frame


def _scroll_wrapper(
    object_name: str,
    content: QWidget,
    horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarAlwaysOff,
) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    scroll.setStyleSheet(workbench_region_style())
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(horizontal_policy)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    content.setObjectName(f"{object_name}_content")
    scroll.setWidget(content)
    return scroll


def scroll_viewport_overhead(scroll: QScrollArea) -> int:
    return scroll.frameWidth() * 2 + scroll.verticalScrollBar().sizeHint().width()


def make_config_rail() -> tuple[QFrame, QVBoxLayout, QScrollArea]:
    content = _frame(f"{CONFIG_RAIL_OBJECT}_content")
    layout = QVBoxLayout(content)
    layout.setAlignment(Qt.AlignTop)
    layout.setContentsMargins(WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER)
    layout.setSpacing(WORKSPACE_GUTTER)
    scroll = _scroll_wrapper(CONFIG_RAIL_OBJECT, content)
    scroll.setMinimumWidth(CONFIG_RAIL_MIN_WIDTH + scroll_viewport_overhead(scroll))
    return content, layout, scroll


def make_workspace_canvas() -> tuple[QFrame, QVBoxLayout, QScrollArea]:
    content = _frame(f"{WORKSPACE_CANVAS_OBJECT}_content")
    layout = QVBoxLayout(content)
    layout.setAlignment(Qt.AlignTop)
    layout.setContentsMargins(WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER)
    layout.setSpacing(WORKSPACE_GUTTER)
    scroll = _scroll_wrapper(
        WORKSPACE_CANVAS_OBJECT,
        content,
        horizontal_policy=Qt.ScrollBarAsNeeded,
    )
    scroll.setMinimumWidth(WORKSPACE_CANVAS_MIN_WIDTH)
    return content, layout, scroll


def make_result_rail() -> tuple[QFrame, QVBoxLayout]:
    frame = _frame(RESULT_RAIL_OBJECT)
    layout = QVBoxLayout(frame)
    layout.setAlignment(Qt.AlignTop)
    layout.setContentsMargins(WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER)
    layout.setSpacing(WORKSPACE_GUTTER)
    frame.setMinimumWidth(RESULT_RAIL_MIN_WIDTH)
    return frame, layout


def make_status_strip(owner: object) -> tuple[QFrame, QHBoxLayout]:
    strip = _frame(STATUS_STRIP_OBJECT)
    strip.setMinimumHeight(STATUS_STRIP_HEIGHT)
    strip.setMaximumHeight(STATUS_STRIP_HEIGHT)
    layout = QHBoxLayout(strip)
    layout.setContentsMargins(WORKSPACE_GUTTER, 0, WORKSPACE_GUTTER, 0)
    layout.setSpacing(WORKSPACE_GUTTER)

    workspace_label = getattr(owner, "workspace_status_label", None)
    job_label = getattr(owner, "job_status_label", None)
    if workspace_label is not None:
        layout.addWidget(workspace_label)
    layout.addStretch(1)
    if job_label is not None:
        layout.addWidget(job_label)
    return strip, layout


def build_workbench_main_splitter(owner: object) -> QSplitter:
    splitter = QSplitter(Qt.Horizontal)
    splitter.setObjectName("workbench_main_splitter")
    splitter.setHandleWidth(8)
    splitter.setChildrenCollapsible(False)

    config_content, config_layout, config_scroll = make_config_rail()
    workspace_content, workspace_layout, workspace_scroll = make_workspace_canvas()
    result_frame, result_layout = make_result_rail()

    owner.workbench_config_content = config_content
    owner.workbench_config_layout = config_layout
    owner.workbench_config_rail = config_scroll
    owner.workbench_workspace_content = workspace_content
    owner.workbench_workspace_layout = workspace_layout
    owner.workbench_workspace_canvas = workspace_scroll
    owner.workbench_result_rail = result_frame
    owner.workbench_result_layout = result_layout

    splitter.addWidget(config_scroll)
    splitter.addWidget(workspace_scroll)
    splitter.addWidget(result_frame)
    for index in range(splitter.count()):
        splitter.setCollapsible(index, False)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setStretchFactor(2, 0)

    owner_width = int(getattr(owner, "width", lambda: 0)() or 0)
    available = max(
        owner_width,
        CONFIG_RAIL_WIDTH + WORKSPACE_CANVAS_MIN_WIDTH + RESULT_RAIL_WIDTH,
    )
    workspace_width = max(
        WORKSPACE_CANVAS_MIN_WIDTH,
        available - CONFIG_RAIL_WIDTH - RESULT_RAIL_WIDTH,
    )
    splitter.setSizes([CONFIG_RAIL_WIDTH, workspace_width, RESULT_RAIL_WIDTH])
    return splitter


def reparent_widget(layout: QVBoxLayout | QHBoxLayout, widget: QWidget, stretch: int = 0) -> None:
    layout.addWidget(widget, stretch)
