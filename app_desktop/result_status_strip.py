"""Minimal always-visible result status strip (Part D).

A small footer strip (status badge + method + elapsed) that is always visible so
the calculation status is judgable even when panels collapse. It is built from NEW
widgets and reads the SAME result-state source as the overview card
(``workbench_results._overview_state`` + ``_status_badge``); it does not move or
reuse the pre-existing shell footer (``workbench_status_strip``) or the overview
card's badge.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from app_desktop.workbench_results import _overview_state, _status_badge


def _tr(owner: Any, zh: str, en: str) -> str:
    tr = getattr(owner, "_tr", None)
    return tr(zh, en) if callable(tr) else zh


def _method_label(owner: Any) -> str:
    for attr in ("method_combo", "mode_combo"):
        combo = getattr(owner, attr, None)
        if combo is not None:
            try:
                text = combo.currentText()
            except (RuntimeError, AttributeError):
                text = ""
            if text:
                return text
    return "—"


def _elapsed_label(owner: Any) -> str:
    elapsed = getattr(owner, "_last_result_elapsed", None)
    if isinstance(elapsed, (int, float)) and elapsed >= 0:
        return f"{elapsed:.3f} s"
    return "—"


def build_result_status_strip(owner: Any) -> QWidget:
    """Create the strip and stash its labels on ``owner``. Returns the strip."""
    strip = QFrame()
    strip.setObjectName("result_status_strip")
    layout = QHBoxLayout(strip)
    layout.setContentsMargins(8, 2, 8, 2)
    layout.setSpacing(10)

    status = QLabel()
    status.setObjectName("result_status_strip_status")
    status.setProperty("datalab_result_status", "waiting")
    method = QLabel()
    method.setObjectName("result_status_strip_method")
    elapsed = QLabel()
    elapsed.setObjectName("result_status_strip_elapsed")

    layout.addWidget(status)
    layout.addStretch(1)
    layout.addWidget(method)
    layout.addWidget(elapsed)

    owner._result_status_strip = strip
    owner._result_status_strip_status = status
    owner._result_status_strip_method = method
    owner._result_status_strip_elapsed = elapsed

    refresh_result_status_strip(owner)
    return strip


def refresh_result_status_strip(owner: Any) -> None:
    """Refresh the strip from the shared result-state source."""
    status_label = getattr(owner, "_result_status_strip_status", None)
    if status_label is None:
        return
    state = _overview_state(owner)
    status, label = _status_badge(owner, state)
    status_label.setText(label)
    status_label.setProperty("datalab_result_status", status)
    style = status_label.style()
    style.unpolish(status_label)
    style.polish(status_label)

    method_label = getattr(owner, "_result_status_strip_method", None)
    if method_label is not None:
        method_label.setText(_tr(owner, "方法：", "Method: ") + _method_label(owner))
    elapsed_label = getattr(owner, "_result_status_strip_elapsed", None)
    if elapsed_label is not None:
        elapsed_label.setText(_tr(owner, "用时：", "Elapsed: ") + _elapsed_label(owner))
