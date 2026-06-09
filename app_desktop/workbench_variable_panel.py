from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from app_desktop.workbench_layout import reparent_widget
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS


def build_variable_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_variable_panel")
    panel.setMinimumHeight(96)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    owner.workbench_variable_title = QLabel(owner._tr("参数与常数", "Parameters and constants"))
    owner.workbench_variable_title.setObjectName("workbench_variable_title")
    layout.addWidget(owner.workbench_variable_title)

    owner.workbench_variable_stack = QStackedWidget()
    owner.workbench_variable_stack.setObjectName("workbench_variable_stack")
    layout.addWidget(owner.workbench_variable_stack)
    owner._workbench_variable_pages = {}
    return panel


def populate_variable_workspace_panel(owner: Any) -> None:
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None or stack.count() > 0:
        return
    pages = getattr(owner, "_workbench_variable_pages", None)
    if pages is None:
        pages = {}
        owner._workbench_variable_pages = pages
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        page = QWidget()
        page.setObjectName(f"workbench_variable_page_{mode}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for mount in spec.parameters + spec.tables + spec.constants:
            for attr in _mount_attrs_in_visual_order(mount):
                widget = getattr(owner, attr, None)
                if widget is not None:
                    reparent_widget(layout, widget)
        layout.addStretch(1)
        stack.addWidget(page)
        pages[mode] = page


def _mount_attrs_in_visual_order(mount: Any) -> tuple[str, ...]:
    pre_attrs = tuple(attr for attr in mount.companion_attrs if "header" in attr)
    post_attrs = tuple(attr for attr in mount.companion_attrs if attr not in pre_attrs)
    return pre_attrs + (mount.widget_attr,) + post_attrs


def refresh_variable_workspace_panel(owner: Any) -> None:
    panel = getattr(owner, "workbench_variable_panel", None)
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None:
        return
    title = getattr(owner, "workbench_variable_title", None)
    if title is not None:
        title.setText(owner._tr("参数与常数", "Parameters and constants"))
    mode = str(owner.mode_combo.currentData() or "")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    has_variables = bool(spec and (spec.parameters or spec.tables or spec.constants))
    if not has_variables:
        if panel is not None:
            panel.setVisible(False)
        return
    pages = getattr(owner, "_workbench_variable_pages", {})
    page = pages.get(mode)
    if page is not None:
        stack.setCurrentWidget(page)
    page_has_visible_variables = False
    if page is not None and page.layout() is not None:
        for index in range(page.layout().count()):
            item = page.layout().itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.isVisibleTo(page):
                page_has_visible_variables = True
                break
    if panel is not None:
        panel.setVisible(page_has_visible_variables)
