"""Conservative shell widgets for the desktop workbench."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class _OwnerProtocol(Protocol):
    def _register_text(self, widget: object, zh: str, en: str, attr: str = "setText") -> None: ...

    def _tr(self, zh: str, en: str) -> str: ...


def _dynamic_owner(owner: object) -> Any:
    return cast(Any, owner)


def _translate(owner: object, zh: str, en: str) -> str:
    translate = getattr(owner, "_tr", None)
    if callable(translate):
        typed_owner = cast(_OwnerProtocol, owner)
        return typed_owner._tr(zh, en)
    return zh


def _call_owner(owner: object, *method_names: str) -> Callable[[bool], None]:
    """Return a Qt slot that resolves the owner method at click time."""

    def _slot(_checked: bool = False) -> None:
        for method_name in method_names:
            method = getattr(owner, method_name, None)
            if callable(method):
                try:
                    method(_checked)
                except TypeError:
                    method()
                return

    return _slot


def _button(
    owner: object,
    text_zh: str,
    text_en: str,
    object_name: str,
    *methods: str,
    tooltip_zh: str = "",
    tooltip_en: str = "",
) -> QPushButton:
    button = QPushButton(text_zh)
    button.setObjectName(object_name)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button.clicked.connect(_call_owner(owner, *methods))
    if tooltip_zh or tooltip_en:
        button.setToolTip(_translate(owner, tooltip_zh, tooltip_en))
        button.setAccessibleDescription(_translate(owner, tooltip_zh, tooltip_en))
    register = getattr(owner, "_register_text", None)
    if callable(register):
        typed_owner = cast(_OwnerProtocol, owner)
        typed_owner._register_text(button, text_zh, text_en)
        if tooltip_zh or tooltip_en:
            typed_owner._register_text(button, tooltip_zh, tooltip_en, "setToolTip")
            typed_owner._register_text(button, tooltip_zh, tooltip_en, "setAccessibleDescription")
    return button


def build_workbench_bar(owner: object) -> QWidget:
    """Build the top workbench bar without replacing existing controls."""
    dynamic_owner = _dynamic_owner(owner)
    bar = QFrame()
    bar.setObjectName("workbench_bar")
    bar.setFrameShape(QFrame.Shape.NoFrame)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(6)

    dynamic_owner.new_workspace_button = _button(
        owner,
        "新建",
        "New",
        "new_workspace_button",
        "new_workspace",
        tooltip_zh="新建空白工作区。",
        tooltip_en="Create a blank workspace.",
    )
    dynamic_owner.open_workspace_button = _button(
        owner,
        "打开",
        "Open",
        "open_workspace_button",
        "open_workspace",
        tooltip_zh="打开已有 .datalab 工作区。",
        tooltip_en="Open an existing .datalab workspace.",
    )
    dynamic_owner.save_workspace_button = _button(
        owner,
        "保存",
        "Save",
        "save_workspace_button",
        "save_workspace",
        tooltip_zh="保存当前工作区；示例模板会要求另存为。",
        tooltip_en="Save the current workspace; example templates require Save As.",
    )
    dynamic_owner.open_examples_button = _button(
        owner,
        "示例",
        "Examples",
        "open_examples_button",
        "open_example_workspace",
        tooltip_zh="打开内置示例工作区作为只读模板。",
        tooltip_en="Open a bundled example workspace as a read-only template.",
    )

    for widget in (
        dynamic_owner.new_workspace_button,
        dynamic_owner.open_workspace_button,
        dynamic_owner.save_workspace_button,
        dynamic_owner.open_examples_button,
    ):
        layout.addWidget(widget)

    layout.addSpacing(10)

    dynamic_owner.workbench_run_button = _button(
        owner,
        "运行",
        "Run",
        "workbench_run_button",
        "run_extrapolation",
        "run_calculation",
        tooltip_zh="运行当前配置的计算。",
        tooltip_en="Run the calculation with the current configuration.",
    )
    dynamic_owner.workbench_stop_button = _button(
        owner,
        "停止",
        "Stop",
        "workbench_stop_button",
        "stop_calculation",
        "_stop_current_worker",
        tooltip_zh="停止正在运行的计算。",
        tooltip_en="Stop the running calculation.",
    )
    layout.addWidget(dynamic_owner.workbench_run_button)
    layout.addWidget(dynamic_owner.workbench_stop_button)

    layout.addStretch(1)

    dynamic_owner.workspace_status_label = QLabel()
    dynamic_owner.workspace_status_label.setObjectName("workspace_status_label")
    dynamic_owner.workspace_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    dynamic_owner.job_status_label = QLabel()
    dynamic_owner.job_status_label.setObjectName("job_status_label")
    dynamic_owner.job_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    layout.addWidget(dynamic_owner.workspace_status_label)
    layout.addWidget(dynamic_owner.job_status_label)

    layout.addSpacing(10)

    dynamic_owner.docs_button = _button(
        owner,
        "文档",
        "Docs",
        "docs_button",
        "_open_docs",
        "_show_docs",
        tooltip_zh="打开离线桌面帮助文档。",
        tooltip_en="Open the offline desktop documentation.",
    )
    dynamic_owner.check_updates_button = _button(
        owner,
        "检查更新",
        "Updates",
        "check_updates_button",
        "check_for_updates",
        "_check_for_updates",
        tooltip_zh="检查 GitHub 发布页上的新版本。",
        tooltip_en="Check GitHub releases for a newer version.",
    )
    layout.addWidget(dynamic_owner.docs_button)
    layout.addWidget(dynamic_owner.check_updates_button)

    update_workbench_status(owner)
    return bar


def update_workbench_status(owner: object) -> None:
    workspace_label = getattr(owner, "workspace_status_label", None)
    if workspace_label is not None:
        dirty = bool(getattr(owner, "_workspace_dirty", False))
        workspace_label.setText(
            _translate(owner, "未保存", "Unsaved") if dirty else _translate(owner, "已保存", "Saved")
        )

    job_label = getattr(owner, "job_status_label", None)
    if job_label is not None:
        has_running_worker = getattr(owner, "_has_running_worker", None)
        running = bool(has_running_worker()) if callable(has_running_worker) else False
        set_workbench_job_status(owner, running=running)


def set_workbench_job_status(owner: object, *, running: bool) -> None:
    job_label = getattr(owner, "job_status_label", None)
    if job_label is not None:
        job_label.setText(
            _translate(owner, "运行中", "Running") if running else _translate(owner, "就绪", "Ready")
        )
