from __future__ import annotations

from typing import Any
import weakref

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import variable_panel_style
from app_desktop.workbench_layout import reparent_widget
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS


def build_variable_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_variable_panel")
    panel.setMinimumHeight(96)
    panel.setStyleSheet(variable_panel_style())
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    header = QWidget()
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(6)
    owner.workbench_variable_title = QLabel(owner._tr("参数与常数", "Parameters and constants"))
    owner.workbench_variable_title.setObjectName("workbench_variable_title")
    header_layout.addWidget(owner.workbench_variable_title, 0)

    owner.workbench_variable_summary = QLabel(owner._tr("未填写", "No entries"))
    owner.workbench_variable_summary.setObjectName("workbench_variable_summary")
    owner.workbench_variable_summary.setWordWrap(True)
    header_layout.addWidget(owner.workbench_variable_summary, 1)

    owner.workbench_variable_toggle_button = QPushButton(owner._tr("折叠", "Collapse"))
    owner.workbench_variable_toggle_button.setObjectName("workbench_variable_toggle_button")
    owner.workbench_variable_toggle_button.setProperty("datalab_variable_toolbar_button", True)
    owner_ref = weakref.ref(owner)

    def _toggle_from_button() -> None:
        current_owner = owner_ref()
        if current_owner is not None:
            _toggle_variable_workspace_panel(current_owner)

    owner.workbench_variable_toggle_button.clicked.connect(_toggle_from_button)
    header_layout.addWidget(owner.workbench_variable_toggle_button, 0)
    layout.addWidget(header)

    owner.workbench_variable_stack = QStackedWidget()
    owner.workbench_variable_stack.setObjectName("workbench_variable_stack")
    layout.addWidget(owner.workbench_variable_stack)
    owner._workbench_variable_pages = {}
    owner._workbench_variable_sections = {}
    owner._workbench_variable_collapsed = False
    return panel


def populate_variable_workspace_panel(owner: Any) -> None:
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None or stack.count() > 0:
        return
    pages = getattr(owner, "_workbench_variable_pages", None)
    if pages is None:
        pages = {}
        owner._workbench_variable_pages = pages
    sections: dict[str, list[tuple[QFrame, tuple[str, ...]]]] = {}
    callbacks: list[Any] = []
    connected_widgets: set[int] = set()
    owner_ref = weakref.ref(owner)
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        page = QWidget()
        page.setObjectName(f"workbench_variable_page_{mode}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        mode_sections: list[tuple[QFrame, tuple[str, ...]]] = []
        for mount in _mounts_in_panel_order(spec):
            section, title_layout, body_layout = _make_variable_section(owner, mode, mount)
            tracked_attrs: list[str] = []
            for attr in _mount_attrs_in_visual_order(mount):
                widget = getattr(owner, attr, None)
                if widget is not None:
                    tracked_attrs.append(attr)
                    _prepare_mounted_variable_widget(widget, mount, attr)
                    _connect_variable_change_signal(owner_ref, widget, callbacks, connected_widgets)
                    destination = _mount_attr_destination(attr, mount)
                    if destination == "title":
                        reparent_widget(title_layout, widget, stretch=1)
                    else:
                        reparent_widget(body_layout, widget)
            if tracked_attrs:
                layout.addWidget(section)
                mode_sections.append((section, tuple(tracked_attrs)))
        layout.addStretch(1)
        stack.addWidget(page)
        pages[mode] = page
        sections[mode] = mode_sections
    owner._workbench_variable_sections = sections
    owner._workbench_variable_changed_callbacks = callbacks


def _connect_variable_change_signal(
    owner_ref: weakref.ReferenceType[Any],
    widget: QWidget,
    callbacks: list[Any],
    connected_widgets: set[int],
) -> None:
    if id(widget) in connected_widgets:
        return
    signal = getattr(widget, "changed", None)
    if signal is None or not hasattr(signal, "connect"):
        signal = getattr(widget, "toggled", None)
    if signal is None or not hasattr(signal, "connect"):
        return
    connected_widgets.add(id(widget))

    def _refresh_variable_summary(*_args: object) -> None:
        owner = owner_ref()
        if owner is not None:
            refresh_variable_workspace_panel(owner)

    callbacks.append(_refresh_variable_summary)
    signal.connect(_refresh_variable_summary)


def _mounts_in_panel_order(spec: Any) -> tuple[Any, ...]:
    if spec.mode_key == "fitting":
        return spec.parameters + spec.constants + spec.tables
    if spec.mode_key == "root_solving":
        return spec.tables + spec.constants + spec.parameters
    return spec.parameters + spec.tables + spec.constants


def _make_variable_section(owner: Any, mode: str, mount: Any) -> tuple[QFrame, QHBoxLayout, QVBoxLayout]:
    section = QFrame()
    section.setObjectName(f"workbench_variable_section_{mode}_{mount.widget_attr}")
    section.setProperty("datalab_variable_section_card", True)
    section.setProperty("datalab_variable_section_role", mount.role)
    section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    outer = QVBoxLayout(section)
    outer.setContentsMargins(10, 8, 10, 10)
    outer.setSpacing(8)

    title_row = QWidget()
    title_layout = QHBoxLayout(title_row)
    title_layout.setContentsMargins(0, 0, 0, 0)
    title_layout.setSpacing(6)
    outer.addWidget(title_row)

    if not any(_is_header_companion_attr(attr) for attr in mount.companion_attrs):
        title = QLabel(_section_title(owner, mount.role))
        title.setObjectName(f"{section.objectName()}_title")
        title.setProperty("datalab_variable_section_title", True)
        title_layout.addWidget(title, 1)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(8)
    outer.addWidget(body)
    return section, title_layout, body_layout


def _section_title(owner: Any, role: str) -> str:
    if role == "constants":
        return owner._tr("常数", "Constants")
    if role == "unknowns":
        return owner._tr("未知量", "Unknowns")
    if role == "parameters":
        return owner._tr("参数", "Parameters")
    return owner._tr("设置", "Settings")


def _mount_attrs_in_visual_order(mount: Any) -> tuple[str, ...]:
    pre_attrs = tuple(attr for attr in mount.companion_attrs if _is_header_companion_attr(attr))
    post_attrs = tuple(attr for attr in mount.companion_attrs if attr not in pre_attrs)
    return pre_attrs + (mount.widget_attr,) + post_attrs


def _mount_attr_destination(attr: str, mount: Any) -> str:
    if attr in mount.companion_attrs and _is_header_companion_attr(attr):
        return "title"
    return "body"


def _is_header_companion_attr(attr: str) -> bool:
    return attr.endswith("_header_widget")


def _prepare_mounted_variable_widget(widget: QWidget, mount: Any, attr: str) -> None:
    if attr == mount.widget_attr and hasattr(widget, "set_embedded_in_workbench"):
        widget.set_embedded_in_workbench(True)
    if attr in mount.companion_attrs:
        _mark_variable_toolbar_buttons(widget)


def _mark_variable_toolbar_buttons(widget: QWidget) -> None:
    if isinstance(widget, QPushButton):
        widget.setProperty("datalab_variable_toolbar_button", True)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    for button in widget.findChildren(QPushButton):
        button.setProperty("datalab_variable_toolbar_button", True)
        button.style().unpolish(button)
        button.style().polish(button)


def refresh_variable_workspace_panel(owner: Any) -> None:
    panel = getattr(owner, "workbench_variable_panel", None)
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None:
        return
    if panel is not None:
        panel.setStyleSheet(variable_panel_style())
    summary = getattr(owner, "workbench_variable_summary", None)
    mode = str(owner.mode_combo.currentData() or "")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    has_variables = bool(spec and (spec.parameters or spec.tables or spec.constants))
    if not has_variables:
        title = getattr(owner, "workbench_variable_title", None)
        if title is not None:
            title.setText(owner._tr("参数与常数", "Parameters and constants"))
        if summary is not None:
            summary.setText(owner._tr("未填写", "No entries"))
        if panel is not None:
            panel.setVisible(False)
        return
    pages = getattr(owner, "_workbench_variable_pages", {})
    page = pages.get(mode)
    if page is not None:
        stack.setCurrentWidget(page)
    for section, attrs in getattr(owner, "_workbench_variable_sections", {}).get(mode, []):
        _refresh_variable_section_title(owner, section)
        section.setVisible(
            any(
                (widget := getattr(owner, attr, None)) is not None and not widget.isHidden()
                for attr in attrs
            )
        )
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
    title = getattr(owner, "workbench_variable_title", None)
    if title is not None:
        title.setText(_panel_title(owner, mode))
    if summary is not None:
        summary.setText(_variable_summary_text(owner, mode))
    _refresh_variable_toggle(owner, page_has_visible_variables)
    if stack is not None:
        stack.setVisible(page_has_visible_variables and not bool(getattr(owner, "_workbench_variable_collapsed", False)))


def _toggle_variable_workspace_panel(owner: Any) -> None:
    owner._workbench_variable_collapsed = not bool(getattr(owner, "_workbench_variable_collapsed", False))
    refresh_variable_workspace_panel(owner)


def _refresh_variable_toggle(owner: Any, panel_has_variables: bool) -> None:
    button = getattr(owner, "workbench_variable_toggle_button", None)
    if button is None:
        return
    collapsed = bool(getattr(owner, "_workbench_variable_collapsed", False))
    button.setVisible(panel_has_variables)
    button.setText(owner._tr("展开", "Expand") if collapsed else owner._tr("折叠", "Collapse"))
    button.setToolTip(
        owner._tr("显示参数、常数和未知量设置", "Show parameter, constant, and unknown settings")
        if collapsed
        else owner._tr("隐藏参数、常数和未知量设置", "Hide parameter, constant, and unknown settings")
    )


def _variable_summary_text(owner: Any, mode: str) -> str:
    counts: dict[str, int] = {"parameters": 0, "constants": 0, "unknowns": 0}
    for section, attrs in getattr(owner, "_workbench_variable_sections", {}).get(mode, []):
        if not section.isVisible():
            continue
        role = str(section.property("datalab_variable_section_role") or "")
        if role not in counts:
            continue
        counts[role] += _section_row_count(owner, attrs)
    parts_zh: list[str] = []
    parts_en: list[str] = []
    for role in ("parameters", "unknowns", "constants"):
        count = counts.get(role, 0)
        if count <= 0:
            continue
        label_zh, singular_en, plural_en = _summary_role_labels(role)
        parts_zh.append(f"{count} 个{label_zh}")
        parts_en.append(f"{count} {singular_en if count == 1 else plural_en}")
    if not parts_zh:
        return owner._tr("未填写", "No entries")
    return owner._tr(" / ".join(parts_zh), " / ".join(parts_en))


def _summary_role_labels(role: str) -> tuple[str, str, str]:
    if role == "constants":
        return "常数", "constant", "constants"
    if role == "unknowns":
        return "未知量", "unknown", "unknowns"
    return "参数", "parameter", "parameters"


def _section_row_count(owner: Any, attrs: tuple[str, ...]) -> int:
    count = 0
    for attr in attrs:
        widget = getattr(owner, attr, None)
        if widget is None or widget.isHidden():
            continue
        rows = getattr(widget, "rows", None)
        if rows is None:
            continue
        if hasattr(widget, "isChecked") and not widget.isChecked():
            continue
        try:
            row_values = rows()
        except RuntimeError:
            continue
        count += len(row_values)
    return count


def _refresh_variable_section_title(owner: Any, section: QFrame) -> None:
    role = str(section.property("datalab_variable_section_role") or "")
    for label in section.findChildren(QLabel):
        if bool(label.property("datalab_variable_section_title")):
            label.setText(_section_title(owner, role))


def _panel_title(owner: Any, mode: str) -> str:
    roles = tuple(
        str(section.property("datalab_variable_section_role") or "")
        for section, _attrs in getattr(owner, "_workbench_variable_sections", {}).get(mode, [])
        if section.isVisible()
    )
    if roles == ("constants",):
        return owner._tr("常数", "Constants")
    if "unknowns" in roles and "constants" in roles:
        return owner._tr("未知量与常数", "Unknowns and constants")
    if "unknowns" in roles:
        return owner._tr("未知量", "Unknowns")
    if "constants" in roles and "parameters" in roles:
        if roles.index("parameters") < roles.index("constants"):
            return owner._tr("参数与常数", "Parameters and constants")
        return owner._tr("常数与参数", "Constants and parameters")
    if "parameters" in roles:
        return owner._tr("参数", "Parameters")
    return owner._tr("参数与常数", "Parameters and constants")
