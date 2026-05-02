#!/usr/bin/env python3
"""Desktop GUI entry point for DataLab (PySide6)."""

from __future__ import annotations

import multiprocessing
import os
import sys

# Frozen multiprocessing workers must be diverted before Qt imports.
multiprocessing.freeze_support()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared.ui_keyguards import ArrowKeyGuard

from .resources import _apply_system_theme, resolve_resource_path
from .window import ExtrapolationWindow


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

    if os.name == "nt":
        pref = _apply_system_theme(app)
        window = ExtrapolationWindow()
        window._windows_light_pref = pref if pref is not None else window._windows_light_pref
    else:
        window = ExtrapolationWindow()

    window.show()
    sys.exit(app.exec())


__all__ = [
    "ExtrapolationWindow",
    "main",
    "resolve_resource_path",
]


if __name__ == "__main__":
    main()
