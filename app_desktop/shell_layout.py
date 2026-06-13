"""Conservative shell widgets for the desktop workbench."""

from __future__ import annotations

from app_desktop.workbench_toolbar import _dynamic_owner, _translate, build_workbench_toolbar

from PySide6.QtWidgets import QWidget


def build_workbench_bar(owner: object) -> QWidget:
    """Build the top workbench toolbar without replacing existing attributes."""
    bar = build_workbench_toolbar(owner)
    dynamic_owner = _dynamic_owner(owner)
    dynamic_owner.workbench_bar = bar
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
