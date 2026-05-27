#!/usr/bin/env python3
"""Desktop GUI entry point for DataLab (PySide6)."""

from __future__ import annotations

import multiprocessing
import os
import sys
from collections.abc import Sequence
from pathlib import Path

WORKSPACE_SUFFIX = ".datalab"


def workspace_paths_from_argv(argv: Sequence[str], *, enabled: bool = True) -> list[Path]:
    if not enabled:
        return []
    paths: list[Path] = []
    end_of_options = False
    for raw in list(argv)[1:]:
        if not raw:
            continue
        if raw == "--":
            end_of_options = True
            continue
        if not end_of_options and raw.startswith("-"):
            continue
        path = Path(raw).expanduser()
        if path.suffix.lower() != WORKSPACE_SUFFIX:
            continue
        paths.append(path)
        break
    return paths


# Frozen multiprocessing workers must be diverted before Qt imports.
multiprocessing.freeze_support()

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication

from shared.ui_keyguards import ArrowKeyGuard

from .resources import _apply_system_theme, resolve_resource_path
from .window import ExtrapolationWindow


def _workspace_path_key(path: Path) -> str:
    return str(path.expanduser())


class WorkspaceOpenDispatcher:
    def __init__(self) -> None:
        self._window: object | None = None
        self._pending: tuple[Path, bool] | None = None
        self._accepted_keys: set[str] = set()

    def set_window(self, window: object) -> None:
        self._window = window
        pending = self._pending
        self._pending = None
        if pending is not None:
            path, confirm_discard = pending
            self._accepted_keys.discard(_workspace_path_key(path))
            self.request_open(path, confirm_discard=confirm_discard)

    def request_open(self, path: Path, *, confirm_discard: bool = True) -> bool:
        path = path.expanduser()
        if path.suffix.lower() != WORKSPACE_SUFFIX:
            return False

        key = _workspace_path_key(path)
        if key in self._accepted_keys:
            return True

        if self._window is None:
            if self._pending is None:
                self._pending = (path, confirm_discard)
                self._accepted_keys.add(key)
            return True

        opened = bool(
            self._window.open_workspace_path(path, confirm_discard=confirm_discard)  # type: ignore[attr-defined]
        )
        if opened:
            self._accepted_keys.add(key)
        return opened


class WorkspaceFileOpenFilter(QObject):
    def __init__(self, dispatcher: WorkspaceOpenDispatcher) -> None:
        super().__init__()
        self._dispatcher = dispatcher

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is None or event.type() != QEvent.Type.FileOpen:
            return False
        if not isinstance(event, QFileOpenEvent):
            return False

        raw_path = event.file()
        if not raw_path:
            raw_path = event.url().toLocalFile()
        if raw_path:
            return self._dispatcher.request_open(Path(raw_path), confirm_discard=True)
        return False


def main() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DataExtrapolationGUI")
        except Exception:
            pass
        try:
            policy = getattr(Qt, "HighDpiScaleFactorRoundingPolicy", None)
            if policy is not None:
                QApplication.setHighDpiScaleFactorRoundingPolicy(policy.PassThrough)  # type: ignore[attr-defined]
        except Exception:
            pass
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)  # type: ignore[attr-defined]
    elif sys.platform.startswith("darwin"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)  # type: ignore[attr-defined]

    app = QApplication(sys.argv)
    app.installEventFilter(ArrowKeyGuard(app))
    workspace_dispatcher = WorkspaceOpenDispatcher()
    workspace_file_filter = WorkspaceFileOpenFilter(workspace_dispatcher)
    app.installEventFilter(workspace_file_filter)
    app._datalab_workspace_file_filter = workspace_file_filter  # type: ignore[attr-defined]

    if os.name == "nt":
        pref = _apply_system_theme(app)
        window = ExtrapolationWindow()
        window._windows_light_pref = pref if pref is not None else window._windows_light_pref
    else:
        window = ExtrapolationWindow()

    workspace_dispatcher.set_window(window)
    window.show()
    for path in workspace_paths_from_argv(sys.argv, enabled=not sys.platform.startswith("darwin")):
        QTimer.singleShot(
            0,
            lambda path=path: workspace_dispatcher.request_open(path, confirm_discard=False),
        )
    sys.exit(app.exec())


__all__ = [
    "ExtrapolationWindow",
    "main",
    "resolve_resource_path",
]


if __name__ == "__main__":
    main()
