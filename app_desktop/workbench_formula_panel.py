from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from app_desktop.formula_preview import FormulaPreviewLabel, update_formula_preview
from app_desktop.ui_schema_binder import SCHEMA_LABEL_EN_PROPERTY, SCHEMA_LABEL_ZH_PROPERTY
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, FormulaMount


def build_formula_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_formula_panel")
    panel.setMinimumHeight(72)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    owner.workbench_formula_panel_title = QLabel(owner._tr("公式预览", "Formula preview"))
    owner.workbench_formula_panel_title.setObjectName("workbench_formula_panel_title")
    layout.addWidget(owner.workbench_formula_panel_title)

    owner.workbench_formula_preview_label = FormulaPreviewLabel()
    owner.workbench_formula_preview_label.setObjectName("workbench_formula_preview_label")
    owner.workbench_formula_preview_label.setMinimumHeight(44)
    _localize_preview_label(owner, owner.workbench_formula_preview_label)
    layout.addWidget(owner.workbench_formula_preview_label)

    owner._workbench_active_formula_attr = ""
    owner._workbench_formula_refresh_timer = QTimer(owner)
    owner._workbench_formula_refresh_timer.setSingleShot(True)
    owner._workbench_formula_refresh_timer.setInterval(120)
    owner._workbench_formula_refresh_timer.timeout.connect(owner.refresh_workbench_formula_panel)
    owner._workbench_formula_focus_filter = _FormulaFocusFilter(owner)
    _install_formula_focus_filters(owner)
    return panel


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
    panel = getattr(owner, "workbench_formula_panel", None)
    label = getattr(owner, "workbench_formula_preview_label", None)
    if label is None:
        return
    title = getattr(owner, "workbench_formula_panel_title", None)
    mount = current_formula_mount(owner)
    if mount is None:
        if title is not None:
            title.setText(owner._tr("公式预览", "Formula preview"))
        if panel is not None:
            panel.setVisible(False)
        label.clear()
        _localize_preview_label(owner, label)
        return

    if panel is not None:
        panel.setVisible(True)
    editor = getattr(owner, mount.editor_attr)
    if title is not None:
        title.setText(_formula_mount_title(owner, editor, mount))
    text = editor.toPlainText().strip() if hasattr(editor, "toPlainText") else editor.text().strip()
    update_formula_preview(label, text, lhs=mount.lhs)
    _localize_preview_label(owner, label)


def _formula_editor_available(owner: Any, editor: QWidget | None) -> bool:
    if editor is None or not editor.isVisibleTo(owner):
        return False
    is_read_only = getattr(editor, "isReadOnly", None)
    return not (callable(is_read_only) and bool(is_read_only()))


def _localize_preview_label(owner: Any, label: QWidget) -> None:
    text = owner._tr("点击放大公式", "Click to enlarge formula")
    label.setToolTip(text)
    label.setAccessibleDescription(text)


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
