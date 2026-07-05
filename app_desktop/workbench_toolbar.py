"""Modern icon toolbar for the desktop workbench."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from app_desktop.theme import TOOLBAR_HEIGHT, workbench_toolbar_style
from app_desktop.workbench_visual_contract import TOOLBAR_OBJECT


class _OwnerProtocol(Protocol):
    def _register_text(self, widget: object, zh: str, en: str, attr: str = "setText") -> None: ...

    def _tr(self, zh: str, en: str) -> str: ...

    def style(self) -> QStyle: ...


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


def _standard_icon(owner: object, icon: QStyle.StandardPixmap):
    typed_owner = cast(_OwnerProtocol, owner)
    return typed_owner.style().standardIcon(icon)


def make_toolbar_button(
    owner: object,
    text_zh: str,
    text_en: str,
    object_name: str,
    icon: QStyle.StandardPixmap,
    *methods: str,
    tooltip_zh: str,
    tooltip_en: str,
) -> QToolButton:
    button = QToolButton()
    button.setObjectName(object_name)
    button.setText(_translate(owner, text_zh, text_en))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setIcon(_standard_icon(owner, icon))
    button.setIconSize(QSize(20, 20))
    button.setAutoRaise(True)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button.clicked.connect(_call_owner(owner, *methods))

    translated_tooltip = _translate(owner, tooltip_zh, tooltip_en)
    button.setToolTip(translated_tooltip)
    button.setAccessibleName(_translate(owner, text_zh, text_en))
    button.setAccessibleDescription(translated_tooltip)

    register = getattr(owner, "_register_text", None)
    if callable(register):
        typed_owner = cast(_OwnerProtocol, owner)
        typed_owner._register_text(button, text_zh, text_en)
        typed_owner._register_text(button, text_zh, text_en, "setAccessibleName")
        typed_owner._register_text(button, tooltip_zh, tooltip_en, "setToolTip")
        typed_owner._register_text(button, tooltip_zh, tooltip_en, "setAccessibleDescription")

    return button


def build_workbench_toolbar(owner: object) -> QWidget:
    dynamic_owner = _dynamic_owner(owner)
    toolbar = QFrame()
    toolbar.setObjectName(TOOLBAR_OBJECT)
    toolbar.setFrameShape(QFrame.Shape.NoFrame)
    toolbar.setMinimumHeight(TOOLBAR_HEIGHT)
    toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    toolbar.setStyleSheet(workbench_toolbar_style())

    layout = QHBoxLayout(toolbar)
    layout.setContentsMargins(10, 4, 10, 4)
    layout.setSpacing(8)

    identity_label = QLabel("DataLab")
    identity_label.setObjectName("workbench_identity_label")
    layout.addWidget(identity_label)
    layout.addSpacing(6)

    # Compute-mode selector slot (left of the workspace buttons). The real
    # ``mode_combo`` is created later in ``panels.build_ui`` (after this toolbar),
    # so we reserve a labelled slot here and let ``panels.py`` insert the combo into
    # ``_toolbar_mode_slot`` once it exists (lazy/after-build, like the option panels).
    mode_label = QLabel("模式：")
    mode_label.setObjectName("workbench_mode_label")
    register = getattr(owner, "_register_text", None)
    if callable(register):
        register(mode_label, "模式：", "Mode:")
    layout.addWidget(mode_label)
    mode_slot = QHBoxLayout()
    mode_slot.setContentsMargins(0, 0, 0, 0)
    mode_slot.setSpacing(0)
    dynamic_owner._toolbar_mode_slot = mode_slot
    layout.addLayout(mode_slot)
    layout.addSpacing(8)

    dynamic_owner.new_workspace_button = make_toolbar_button(
        owner,
        "新建",
        "New",
        "new_workspace_button",
        QStyle.StandardPixmap.SP_FileIcon,
        "new_workspace",
        tooltip_zh="新建空白工作区。",
        tooltip_en="Create a blank workspace.",
    )
    dynamic_owner.open_workspace_button = make_toolbar_button(
        owner,
        "打开",
        "Open",
        "open_workspace_button",
        QStyle.StandardPixmap.SP_DirOpenIcon,
        "open_workspace",
        tooltip_zh="打开已有 .datalab 工作区。",
        tooltip_en="Open an existing .datalab workspace.",
    )
    dynamic_owner.save_workspace_button = make_toolbar_button(
        owner,
        "保存",
        "Save",
        "save_workspace_button",
        QStyle.StandardPixmap.SP_DialogSaveButton,
        "save_workspace",
        tooltip_zh="保存当前工作区；示例模板会要求另存为。",
        tooltip_en="Save the current workspace; example templates require Save As.",
    )
    dynamic_owner.open_examples_button = make_toolbar_button(
        owner,
        "示例",
        "Examples",
        "open_examples_button",
        QStyle.StandardPixmap.SP_FileDialogListView,
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

    layout.addSpacing(8)

    dynamic_owner.workbench_run_button = make_toolbar_button(
        owner,
        "运行",
        "Run",
        "workbench_run_button",
        QStyle.StandardPixmap.SP_MediaPlay,
        "run_extrapolation",
        "run_calculation",
        tooltip_zh="运行当前配置的计算。",
        tooltip_en="Run the calculation with the current configuration.",
    )
    dynamic_owner.workbench_stop_button = make_toolbar_button(
        owner,
        "停止",
        "Stop",
        "workbench_stop_button",
        QStyle.StandardPixmap.SP_MediaStop,
        "stop_calculation",
        "_stop_current_worker",
        tooltip_zh="停止正在运行的计算。",
        tooltip_en="Stop the running calculation.",
    )
    layout.addWidget(dynamic_owner.workbench_run_button)
    layout.addWidget(dynamic_owner.workbench_stop_button)

    # 计算 / LaTeX inline-options toggle buttons. They open normal (non-popup) panels
    # dropped under the toolbar — see app_desktop.workbench_options_panel. Only the
    # checkable buttons live here; panels.py builds + fills the panels once the real
    # option controls exist (lazy/after-build), then binds each button to its panel.
    dynamic_owner.workbench_compute_options_button = make_toolbar_button(
        owner,
        "计算",
        "Compute",
        "workbench_compute_options_button",
        QStyle.StandardPixmap.SP_ComputerIcon,
        tooltip_zh="精度与并行/资源选项。",
        tooltip_en="Precision and parallel/resource options.",
    )
    dynamic_owner.workbench_compute_options_button.setCheckable(True)
    dynamic_owner.workbench_latex_options_button = make_toolbar_button(
        owner,
        "LaTeX",
        "LaTeX",
        "workbench_latex_options_button",
        QStyle.StandardPixmap.SP_FileDialogDetailedView,
        tooltip_zh="LaTeX 输出选项。",
        tooltip_en="LaTeX output options.",
    )
    dynamic_owner.workbench_latex_options_button.setCheckable(True)
    layout.addWidget(dynamic_owner.workbench_compute_options_button)
    layout.addWidget(dynamic_owner.workbench_latex_options_button)

    layout.addStretch(1)

    dynamic_owner.job_status_label = QLabel()
    dynamic_owner.job_status_label.setObjectName("job_status_label")
    dynamic_owner.job_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    dynamic_owner.workspace_status_label = QLabel()
    dynamic_owner.workspace_status_label.setObjectName("workspace_status_label")
    dynamic_owner.workspace_status_label.setAlignment(
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
    )
    layout.addWidget(dynamic_owner.job_status_label)
    layout.addWidget(dynamic_owner.workspace_status_label)

    layout.addSpacing(8)

    dynamic_owner.docs_button = make_toolbar_button(
        owner,
        "文档",
        "Docs",
        "docs_button",
        QStyle.StandardPixmap.SP_MessageBoxQuestion,
        "_open_docs",
        "_show_docs",
        tooltip_zh="打开离线桌面帮助文档。",
        tooltip_en="Open the offline desktop documentation.",
    )
    dynamic_owner.check_updates_button = make_toolbar_button(
        owner,
        "检查更新",
        "Updates",
        "check_updates_button",
        QStyle.StandardPixmap.SP_BrowserReload,
        "check_for_updates",
        "_check_for_updates",
        tooltip_zh="检查 GitHub 发布页上的新版本。",
        tooltip_en="Check GitHub releases for a newer version.",
    )
    layout.addWidget(dynamic_owner.docs_button)
    layout.addWidget(dynamic_owner.check_updates_button)

    return toolbar
