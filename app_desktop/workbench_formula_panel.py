from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QSize, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app_desktop.formula_preview import (
    FormulaPreviewLabel,
    update_formula_preview_with_empty_text,
)
from formula_help import get_function_tooltip
from app_desktop.theme import (
    WORKBENCH_FORMULA_EDITOR_MAX_HEIGHT,
    WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT,
    WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT,
    WORKBENCH_FORMULA_TITLE_ROW_MAX_HEIGHT,
    workbench_formula_caption_style,
    workbench_message_surface_style,
    workbench_title_text_style,
)
from app_desktop.workbench_layout import reparent_widget
from app_desktop.ui_schema_binder import (
    SCHEMA_KEY_PROPERTY,
    SCHEMA_LABEL_EN_PROPERTY,
    SCHEMA_LABEL_ZH_PROPERTY,
    TOOLTIP_EN_PROPERTY,
    TOOLTIP_ZH_PROPERTY,
)
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, FormulaMount


class _CurrentPageSizeStack(QStackedWidget):
    """Stack whose layout footprint follows the visible action page."""

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override name
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override name
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()


def build_formula_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_formula_panel")
    panel.setMinimumHeight(72)
    panel.setMaximumHeight(WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT)
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    title_row = QWidget()
    title_row.setObjectName("workbench_formula_title_row")
    title_row.setMaximumHeight(WORKBENCH_FORMULA_TITLE_ROW_MAX_HEIGHT)
    title_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    title_layout = QHBoxLayout(title_row)
    title_layout.setContentsMargins(0, 0, 0, 0)
    title_layout.setSpacing(6)

    owner.workbench_formula_panel_title = QLabel(owner._tr("公式预览", "Formula preview"))
    owner.workbench_formula_panel_title.setObjectName("workbench_formula_panel_title")
    owner.workbench_formula_panel_title.setWordWrap(True)
    owner.workbench_formula_panel_title.setStyleSheet(workbench_title_text_style())
    title_layout.addWidget(owner.workbench_formula_panel_title, 1)

    owner.workbench_formula_actions_stack = _CurrentPageSizeStack()
    owner.workbench_formula_actions_stack.setObjectName("workbench_formula_actions_stack")
    owner.workbench_formula_actions_stack.setMaximumHeight(WORKBENCH_FORMULA_TITLE_ROW_MAX_HEIGHT)
    owner.workbench_formula_actions_stack.setSizePolicy(
        QSizePolicy.Policy.Minimum,
        QSizePolicy.Policy.Maximum,
    )
    owner.workbench_formula_empty_actions_page = QWidget()
    owner.workbench_formula_empty_actions_page.setObjectName("workbench_formula_actions_empty")
    empty_actions_layout = QHBoxLayout(owner.workbench_formula_empty_actions_page)
    empty_actions_layout.setContentsMargins(0, 0, 0, 0)
    empty_actions_layout.setSpacing(6)
    owner.workbench_formula_actions_stack.addWidget(owner.workbench_formula_empty_actions_page)
    title_layout.addWidget(owner.workbench_formula_actions_stack, 0)
    owner.workbench_formula_function_button = QPushButton()
    owner.workbench_formula_function_button.setObjectName("workbench_formula_function_button")
    owner.workbench_formula_function_button.setFlat(True)
    owner.workbench_formula_function_button.clicked.connect(lambda: owner._show_error_functions())
    _localize_function_button(owner)
    empty_actions_layout.addWidget(owner.workbench_formula_function_button)
    _reserve_formula_actions_width(owner, owner.workbench_formula_empty_actions_page)
    layout.addWidget(title_row)

    owner.workbench_formula_description_label = QLabel("")
    owner.workbench_formula_description_label.setObjectName("workbench_formula_description_label")
    owner.workbench_formula_description_label.setWordWrap(True)
    owner.workbench_formula_description_label.setStyleSheet(
        workbench_message_surface_style(kind="description")
    )
    owner.workbench_formula_description_label.hide()
    layout.addWidget(owner.workbench_formula_description_label)

    owner.workbench_formula_editor_stack = QStackedWidget()
    owner.workbench_formula_editor_stack.setObjectName("workbench_formula_editor_stack")
    owner.workbench_formula_editor_stack.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Maximum,
    )
    layout.addWidget(owner.workbench_formula_editor_stack)

    owner.workbench_formula_preview_label = FormulaPreviewLabel()
    owner.workbench_formula_preview_label.setObjectName("workbench_formula_preview_label")
    owner.workbench_formula_preview_label.setMinimumHeight(92)
    _localize_preview_label(owner, owner.workbench_formula_preview_label)
    layout.addWidget(owner.workbench_formula_preview_label)

    owner.workbench_formula_error_label = QLabel("")
    owner.workbench_formula_error_label.setObjectName("workbench_formula_error_label")
    owner.workbench_formula_error_label.setWordWrap(True)
    owner.workbench_formula_error_label.setStyleSheet(
        workbench_message_surface_style(kind="error")
    )
    owner.workbench_formula_error_label.hide()
    layout.addWidget(owner.workbench_formula_error_label)

    owner._workbench_active_formula_attr = ""

    owner._workbench_formula_refresh_timer = QTimer(owner)
    owner._workbench_formula_refresh_timer.setSingleShot(True)
    owner._workbench_formula_refresh_timer.setInterval(120)
    owner._workbench_formula_refresh_timer.timeout.connect(owner.refresh_workbench_formula_panel)
    owner._workbench_formula_focus_filter = _FormulaFocusFilter(owner)
    _install_formula_focus_filters(owner)
    return panel


def populate_formula_workspace_panel(owner: Any) -> None:
    stack = getattr(owner, "workbench_formula_editor_stack", None)
    if stack is None or bool(getattr(owner, "_workbench_formula_populated", False)):
        return
    population_error = getattr(owner, "_workbench_formula_population_error", None)
    if isinstance(population_error, RuntimeError):
        cached_missing = getattr(owner, "_workbench_formula_population_missing_attrs", ())
        if cached_missing:
            if _missing_formula_mount_attrs(owner):
                raise _fresh_population_error(population_error)
            owner._workbench_formula_population_error = None
            owner._workbench_formula_population_missing_attrs = ()
        else:
            # Non-missing-attribute failures are implementation defects rather
            # than user-repairable state. Keep the cached failure state so later
            # refreshes do not repeat a partial reparent/populate pass, but
            # raise a fresh exception instance to avoid traceback growth.
            raise _fresh_population_error(population_error)
    if bool(getattr(owner, "_workbench_formula_populating", False)):
        raise RuntimeError("Formula workbench population is already in progress")
    owner._workbench_formula_populating = True
    try:
        _populate_formula_workspace_panel(owner, stack)
        owner._workbench_formula_population_error = None
        owner._workbench_formula_population_missing_attrs = ()
    except RuntimeError as exc:
        owner._workbench_formula_population_error = exc
        owner._workbench_formula_population_missing_attrs = tuple(_missing_formula_mount_attrs(owner))
        raise
    except Exception as exc:
        error = RuntimeError("Formula workbench population failed")
        owner._workbench_formula_population_error = error
        owner._workbench_formula_population_missing_attrs = tuple(_missing_formula_mount_attrs(owner))
        raise error from exc
    finally:
        owner._workbench_formula_populating = False


def _fresh_population_error(error: RuntimeError) -> RuntimeError:
    message = str(error).strip() or error.__class__.__name__
    return RuntimeError(message)


def _populate_formula_workspace_panel(owner: Any, stack: QStackedWidget) -> None:
    missing = _missing_formula_mount_attrs(owner)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise RuntimeError(f"Formula workbench cannot populate missing widgets: {missing_text}")
    duplicates = _duplicate_formula_editor_attrs()
    if duplicates:
        duplicate_text = ", ".join(duplicates)
        raise RuntimeError(f"Formula workbench cannot populate duplicate editors: {duplicate_text}")
    duplicate_schema_keys = _duplicate_formula_schema_keys()
    if duplicate_schema_keys:
        duplicate_text = ", ".join(duplicate_schema_keys)
        raise RuntimeError(f"Formula workbench cannot populate duplicate schema keys: {duplicate_text}")
    pages: dict[str, QWidget] = {}
    mounts: dict[str, tuple[QWidget | None, QWidget]] = {}
    wrappers: dict[str, QWidget] = {}
    labels: dict[str, QLabel] = {}
    action_pages: dict[str, QWidget] = {}
    actions_stack = getattr(owner, "workbench_formula_actions_stack", None)
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        page = QWidget()
        page.setObjectName(f"workbench_formula_page_{mode}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        multi_formula = len(spec.formulas) > 1
        editor_row_layout: QHBoxLayout | None = None
        if multi_formula:
            editor_row = QWidget()
            editor_row.setObjectName(f"workbench_formula_editor_row_{mode}")
            editor_row_layout = QHBoxLayout(editor_row)
            editor_row_layout.setContentsMargins(0, 0, 0, 0)
            editor_row_layout.setSpacing(8)
            layout.addWidget(editor_row)
        for mount in spec.formulas:
            editor = getattr(owner, mount.editor_attr, None)
            if editor is None:
                raise RuntimeError(
                    "Formula workbench cannot populate missing widgets: "
                    f"{mount.editor_attr}"
                )
            header = _adjacent_editor_header(owner, editor, mount)
            if header is not None:
                schema_label = getattr(header, "schema_label", None)
                if schema_label is not None:
                    schema_label.setVisible(False)
                if actions_stack is not None:
                    _remove_from_parent_layout(header)
                    header.setParent(None)
                    header.setObjectName(f"workbench_formula_actions_{mount.editor_attr}")
                    actions_stack.addWidget(header)
                    action_pages[mount.editor_attr] = header
            if editor_row_layout is not None:
                wrapper = QWidget()
                wrapper.setObjectName(f"workbench_formula_editor_wrap_{mount.editor_attr}")
                wrapper_layout = QVBoxLayout(wrapper)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                wrapper_layout.setSpacing(4)
                caption = QLabel()
                caption.setObjectName(f"workbench_formula_editor_label_{mount.editor_attr}")
                caption.setStyleSheet(workbench_formula_caption_style())
                wrapper_layout.addWidget(caption)
                reparent_widget(wrapper_layout, editor)
                editor_row_layout.addWidget(wrapper, 1)
                labels[mount.editor_attr] = caption
                wrappers[mount.editor_attr] = wrapper
            else:
                reparent_widget(layout, editor)
            _prepare_formula_editor_for_workbench(editor)
            mounts[mount.editor_attr] = (header, editor)
        layout.addStretch(1)
        stack.addWidget(page)
        pages[mode] = page
    owner._workbench_formula_pages = pages
    owner._workbench_formula_mount_widgets = mounts
    owner._workbench_formula_mount_wrappers = wrappers
    owner._workbench_formula_mount_labels = labels
    owner._workbench_formula_action_pages = action_pages
    owner._workbench_formula_populated = True


def _missing_formula_mount_attrs(owner: Any) -> list[str]:
    return [
        attr
        for spec in MODE_WORKBENCH_SPECS.values()
        for mount in spec.formulas
        for attr in (mount.editor_attr, mount.preview_button_attr)
        if getattr(owner, attr, None) is None
    ]


def _duplicate_formula_editor_attrs() -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.formulas:
            if mount.editor_attr in seen:
                duplicates.add(mount.editor_attr)
            seen.add(mount.editor_attr)
    return sorted(duplicates)


def _duplicate_formula_schema_keys() -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.formulas:
            if mount.schema_key in seen:
                duplicates.add(mount.schema_key)
            seen.add(mount.schema_key)
    return sorted(duplicates)


def _prepare_formula_editor_for_workbench(editor: QWidget) -> None:
    editor.setMaximumHeight(WORKBENCH_FORMULA_EDITOR_MAX_HEIGHT)
    editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)


def _remove_from_parent_layout(widget: QWidget) -> None:
    parent = widget.parentWidget()
    parent_layout = parent.layout() if parent is not None else None
    if parent_layout is None:
        # Widgets with no parent layout have no layout item to remove. The
        # caller owns any later ``setParent``.
        return
    parent_layout.removeWidget(widget)


def _adjacent_editor_header(owner: Any, editor: QWidget, mount: FormulaMount) -> QWidget | None:
    parent = editor.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is None:
        return None
    index = layout.indexOf(editor)
    if index <= 0:
        return None
    preview_button = getattr(owner, mount.preview_button_attr, None)
    if isinstance(preview_button, QWidget):
        header = _direct_layout_child_containing(parent, preview_button)
        if header is not None:
            header_index = layout.indexOf(header)
            if header_index == index - 1:
                return header
    return None


def _direct_layout_child_containing(parent: QWidget | None, child: QWidget) -> QWidget | None:
    current: QWidget | None = child
    while current is not None and current.parentWidget() is not parent:
        current = current.parentWidget()
    return current


class _FormulaFocusFilter(QObject):
    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn:
            owner = self._owner
            mode = str(owner.mode_combo.currentData() or "")
            spec = MODE_WORKBENCH_SPECS.get(mode)
            if spec is None:
                return False
            for mount in spec.formulas:
                editor = getattr(owner, mount.editor_attr, None)
                if not _formula_editor_available(owner, editor):
                    continue
                viewport = editor.viewport() if hasattr(editor, "viewport") else None
                is_child_widget = isinstance(watched, QWidget) and editor.isAncestorOf(watched)
                if watched is editor or watched is viewport or is_child_widget:
                    owner._workbench_active_formula_attr = mount.editor_attr
                    schedule_formula_workspace_refresh(owner, mount.editor_attr)
                    return False
        return False


def _install_formula_focus_filters(owner: Any) -> None:
    focus_filter = owner._workbench_formula_focus_filter
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.formulas:
            editor = getattr(owner, mount.editor_attr, None)
            if editor is None:
                continue
            editor.installEventFilter(focus_filter)
            if hasattr(editor, "viewport"):
                editor.viewport().installEventFilter(focus_filter)


def _widget_or_child_has_focus(widget: QWidget) -> bool:
    focused = QApplication.focusWidget()
    return focused is widget or (focused is not None and widget.isAncestorOf(focused))


def current_formula_mount(owner: Any) -> FormulaMount | None:
    mode = str(owner.mode_combo.currentData() or "")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return None
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if _formula_editor_available(owner, editor) and _widget_or_child_has_focus(editor):
            return mount
    active_attr = getattr(owner, "_workbench_active_formula_attr", "")
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if mount.editor_attr == active_attr and _formula_editor_available(owner, editor):
            return mount
    visible_mounts: list[FormulaMount] = []
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if _formula_editor_available(owner, editor):
            visible_mounts.append(mount)
    if visible_mounts:
        return visible_mounts[0]
    return None


def refresh_formula_workspace_panel(owner: Any) -> None:
    label = getattr(owner, "workbench_formula_preview_label", None)
    if label is None:
        return
    if not bool(getattr(owner, "_workbench_formula_populated", False)):
        populate_formula_workspace_panel(owner)
    panel = getattr(owner, "workbench_formula_panel", None)
    stack = getattr(owner, "workbench_formula_editor_stack", None)
    title = getattr(owner, "workbench_formula_panel_title", None)
    mode = str(owner.mode_combo.currentData() or "")
    pages = getattr(owner, "_workbench_formula_pages", {})
    page = pages.get(mode)
    if page is not None and stack is not None:
        stack.setCurrentWidget(page)
    _sync_formula_mount_visibility(owner, mode)
    _localize_function_button(owner)
    if panel is not None:
        panel.setMaximumHeight(_formula_panel_max_height(owner, mode))
    _refresh_formula_mount_labels(owner, mode)
    mount = current_formula_mount(owner)
    if mount is None:
        if title is not None:
            title.setText(owner._tr("公式预览", "Formula preview"))
        _show_formula_actions(owner, None)
        _show_formula_function_button(owner, False)
        if panel is not None:
            panel.setVisible(False)
        label.clear()
        _set_formula_description(owner, None)
        _set_formula_error(owner, "")
        _localize_preview_label(owner, label)
        return

    if panel is not None:
        panel.setVisible(True)
    editor = getattr(owner, mount.editor_attr)
    if title is not None:
        title.setText(_formula_panel_title(owner, mode))
    _show_formula_actions(owner, mount)
    _show_formula_function_button(owner, True)
    actions_stack = getattr(owner, "workbench_formula_actions_stack", None)
    if actions_stack is not None:
        _reserve_formula_actions_width(owner, actions_stack.currentWidget())
    _set_formula_description(owner, mount)
    text = editor.toPlainText().strip() if hasattr(editor, "toPlainText") else editor.text().strip()
    result = update_formula_preview_with_empty_text(
        label,
        text,
        lhs=mount.lhs,
        constrain_size=True,
        empty_text=owner._tr(
            "输入公式后将在此渲染预览；点击预览可放大查看。",
            "Enter a formula to render a preview here; click the preview to enlarge it.",
        ),
    )
    if result is not None and not result.ok and text:
        _set_formula_error(
            owner,
            owner._tr("预览错误：", "Preview error: ") + result.error_message,
        )
    else:
        _set_formula_error(owner, "")
    _localize_preview_label(owner, label)


def _set_formula_error(owner: Any, message: str) -> None:
    label = getattr(owner, "workbench_formula_error_label", None)
    if label is None:
        return
    label.setText(message)
    label.setVisible(bool(message))


def _set_formula_description(owner: Any, mount: FormulaMount | None) -> None:
    label = getattr(owner, "workbench_formula_description_label", None)
    if label is None:
        return
    if mount is None:
        label.setText("")
        label.setProperty(SCHEMA_KEY_PROPERTY, "")
        label.hide()
        return
    editor = getattr(owner, mount.editor_attr, None)
    text = _formula_description_text(owner, editor)
    label.setProperty(SCHEMA_KEY_PROPERTY, mount.schema_key)
    label.setText(text)
    label.setToolTip(text)
    label.setAccessibleDescription(text)
    formula_text = _formula_editor_text(editor)
    label.setVisible(bool(text) and not formula_text)


def _formula_editor_text(editor: QWidget | None) -> str:
    if editor is None:
        return ""
    if hasattr(editor, "toPlainText"):
        return str(editor.toPlainText()).strip()
    if hasattr(editor, "text"):
        return str(editor.text()).strip()
    return ""


def _formula_description_text(owner: Any, editor: QWidget | None) -> str:
    if editor is None:
        return ""
    tooltip = _localized_widget_tooltip(owner, editor)
    placeholder = _widget_placeholder(editor)
    parts: list[str] = []
    if tooltip:
        parts.append(tooltip.rstrip("。."))  # keep the combined caption compact
    if placeholder:
        example_prefix = owner._tr("示例：", "Example: ")
        normalized_placeholder = placeholder.strip()
        if normalized_placeholder and normalized_placeholder not in parts:
            parts.append(f"{example_prefix}{normalized_placeholder}")
    return " · ".join(parts)


def _localized_widget_tooltip(owner: Any, widget: QWidget) -> str:
    is_en = getattr(owner, "_is_en", None)
    prop = TOOLTIP_EN_PROPERTY if callable(is_en) and bool(is_en()) else TOOLTIP_ZH_PROPERTY
    value = str(widget.property(prop) or "").strip()
    if value:
        return value
    return str(widget.toolTip() or "").strip()


def _widget_placeholder(widget: QWidget) -> str:
    placeholder = getattr(widget, "placeholderText", None)
    if callable(placeholder):
        return str(placeholder() or "").strip()
    return ""


def _formula_panel_max_height(owner: Any, mode: str) -> int:
    visible_count = len(_visible_formula_mounts(owner, mode))
    if visible_count > 1:
        return WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT
    return WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT


def _formula_panel_title(owner: Any, mode: str) -> str:
    visible_count = len(_visible_formula_mounts(owner, mode))
    if visible_count > 1:
        return owner._tr("模型公式", "Model formulas")
    return owner._tr("公式预览", "Formula preview")


def _visible_formula_mounts(owner: Any, mode: str) -> list[FormulaMount]:
    if not bool(getattr(owner, "_workbench_formula_populated", False)):
        return []
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return []
    mounts: list[FormulaMount] = []
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if _formula_editor_available(owner, editor):
            mounts.append(mount)
    return mounts


def _sync_formula_mount_visibility(owner: Any, mode: str) -> None:
    if not bool(getattr(owner, "_workbench_formula_populated", False)):
        return
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return
    widgets = getattr(owner, "_workbench_formula_mount_widgets", {})
    wrappers = getattr(owner, "_workbench_formula_mount_wrappers", {})
    for mount in spec.formulas:
        header, editor = widgets.get(mount.editor_attr, (None, getattr(owner, mount.editor_attr, None)))
        visible = _formula_editor_candidate(editor)
        if header is not None:
            header.setVisible(visible)
        wrapper = wrappers.get(mount.editor_attr)
        if wrapper is not None:
            wrapper.setVisible(visible)


def _refresh_formula_mount_labels(owner: Any, mode: str) -> None:
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return
    labels = getattr(owner, "_workbench_formula_mount_labels", {})
    for mount in spec.formulas:
        label = labels.get(mount.editor_attr)
        editor = getattr(owner, mount.editor_attr, None)
        if label is not None and editor is not None:
            label.setText(_formula_mount_title(owner, editor, mount))


def _show_formula_actions(owner: Any, mount: FormulaMount | None) -> None:
    stack = getattr(owner, "workbench_formula_actions_stack", None)
    if stack is None:
        return
    if mount is None:
        empty_page = getattr(owner, "workbench_formula_empty_actions_page", None)
        if empty_page is not None:
            _attach_formula_function_button(owner, empty_page)
            stack.setCurrentWidget(empty_page)
            _reserve_formula_actions_width(owner, empty_page)
        return
    pages = getattr(owner, "_workbench_formula_action_pages", {})
    page = pages.get(mount.editor_attr)
    if page is not None:
        _attach_formula_function_button(owner, page)
        stack.setCurrentWidget(page)
        _reserve_formula_actions_width(owner, page)
        return
    empty_page = getattr(owner, "workbench_formula_empty_actions_page", None)
    if empty_page is not None:
        _attach_formula_function_button(owner, empty_page)
        stack.setCurrentWidget(empty_page)
        _reserve_formula_actions_width(owner, empty_page)


def _attach_formula_function_button(owner: Any, page: QWidget) -> None:
    button = getattr(owner, "workbench_formula_function_button", None)
    if button is None:
        return
    layout = page.layout()
    if layout is None:
        raise RuntimeError("Formula action page has no layout")
    if layout.indexOf(button) >= 0:
        _reserve_formula_actions_width(owner, page)
        return
    _remove_from_parent_layout(button)
    layout.addWidget(button)
    _reserve_formula_actions_width(owner, page)


def _reserve_formula_actions_width(owner: Any, page: QWidget) -> None:
    stack = getattr(owner, "workbench_formula_actions_stack", None)
    if stack is None:
        return
    layout = page.layout()
    if layout is not None:
        layout.activate()
    page.adjustSize()
    required_width = _formula_action_page_required_width(page)
    if required_width <= 0:
        return
    _clear_other_formula_action_page_minimums(stack, page)
    page.setMinimumWidth(required_width)
    stack.setMinimumWidth(required_width)
    stack.updateGeometry()


def _clear_other_formula_action_page_minimums(stack: QStackedWidget, current_page: QWidget) -> None:
    for index in range(stack.count()):
        candidate = stack.widget(index)
        if candidate is not None and candidate is not current_page:
            candidate.setMinimumWidth(0)


def _formula_action_page_required_width(page: QWidget) -> int:
    layout = page.layout()
    if layout is None:
        return page.sizeHint().width()
    margins = layout.contentsMargins()
    required_width = margins.left() + margins.right()
    visible_items = 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None and not widget.isHidden():
            hint = widget.sizeHint()
            minimum_hint = widget.minimumSizeHint()
            required_width += max(hint.width(), minimum_hint.width(), widget.minimumWidth())
            visible_items += 1
            continue
        spacer = item.spacerItem()
        if spacer is not None:
            required_width += spacer.minimumSize().width()
            visible_items += 1
            continue
        nested_layout = item.layout()
        if nested_layout is not None:
            required_width += max(
                nested_layout.minimumSize().width(),
                nested_layout.sizeHint().width(),
            )
            visible_items += 1
    if visible_items > 1:
        required_width += _effective_layout_spacing(layout, page) * (visible_items - 1)
    return max(required_width, page.sizeHint().width())


def _effective_layout_spacing(layout: QLayout, page: QWidget) -> int:
    spacing = layout.spacing()
    if spacing >= 0:
        return spacing
    style = page.style() or QApplication.style()
    pixel_spacing = style.pixelMetric(QStyle.PixelMetric.PM_LayoutHorizontalSpacing, None, page)
    if pixel_spacing >= 0:
        return pixel_spacing
    return 6


def _formula_editor_available(owner: Any, editor: QWidget | None) -> bool:
    if not _formula_editor_candidate(editor):
        return False
    panel = getattr(owner, "workbench_formula_panel", None)
    if panel is not None and panel.isAncestorOf(editor):
        # The shared panel can be hidden while mode changes are being evaluated;
        # availability should still respect local wrapper/submode visibility.
        return _locally_visible_until(editor, panel)
    return editor.isVisibleTo(owner)


def _locally_visible_until(widget: QWidget, ancestor: QWidget) -> bool:
    current: QWidget | None = widget
    while current is not None and current is not ancestor:
        if current.isHidden():
            return False
        current = current.parentWidget()
    return current is ancestor


def _formula_editor_candidate(editor: QWidget | None) -> bool:
    if editor is None or editor.isHidden():
        return False
    is_read_only = getattr(editor, "isReadOnly", None)
    return not (callable(is_read_only) and bool(is_read_only()))


def _localize_preview_label(owner: Any, label: QWidget) -> None:
    text = owner._tr("点击放大公式", "Click to enlarge formula")
    label.setToolTip(text)
    label.setAccessibleDescription(text)


def _localize_function_button(owner: Any) -> None:
    button = getattr(owner, "workbench_formula_function_button", None)
    if button is None:
        return
    is_en = getattr(owner, "_is_en", None)
    lang = "en" if callable(is_en) and bool(is_en()) else "zh"
    button.setText(owner._tr("函数支持", "Functions"))
    button.setToolTip(get_function_tooltip(lang))
    button.setAccessibleName(button.text())
    button.setAccessibleDescription(button.toolTip())


def _show_formula_function_button(owner: Any, visible: bool) -> None:
    button = getattr(owner, "workbench_formula_function_button", None)
    if button is not None:
        button.setVisible(visible)


def _formula_mount_title(owner: Any, editor: QWidget, mount: FormulaMount) -> str:
    zh = str(editor.property(SCHEMA_LABEL_ZH_PROPERTY) or "")
    en = str(editor.property(SCHEMA_LABEL_EN_PROPERTY) or "")
    fallback = _schema_key_fallback(mount.schema_key)
    zh_title = _with_label_suffix(zh or fallback, "：")
    en_title = _with_label_suffix(en or fallback, ":")
    return owner._tr(zh_title, en_title)


def _schema_key_fallback(schema_key: str) -> str:
    tail = schema_key.rsplit(".", 1)[-1]
    words = tail.replace("_", " ").replace("-", " ").strip()
    return words.title() if words else "Formula"


def _with_label_suffix(text: str, suffix: str) -> str:
    stripped = text.rstrip().rstrip(":：").rstrip()
    return f"{stripped}{suffix}" if stripped else f"Formula{suffix}"


def schedule_formula_workspace_refresh(owner: Any, editor_attr: str | None = None) -> None:
    if editor_attr:
        editor = getattr(owner, editor_attr, None)
        if not _formula_editor_available(owner, editor):
            return
        owner._workbench_active_formula_attr = editor_attr
    timer = getattr(owner, "_workbench_formula_refresh_timer", None)
    if timer is not None:
        timer.start()
