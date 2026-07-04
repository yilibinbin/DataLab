"""Top-level result-overview popover (Part C).

A NEW popup window that mirrors the compact overview card. It is a standalone
top-level ``QWidget`` with ``Qt.WindowType.Popup`` (Qt auto-closes it on an
outside click / focus-out), positioned near the overview card. It CREATES its own
labels that READ from the same result-state source (``workbench_results._overview_state``
+ ``_status_badge``); it never reparents or moves the existing overview widgets —
that is what hid controls before.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from app_desktop.workbench_results import _overview_state, _status_badge


class _OverviewCardClickFilter(QObject):
    """Opens the overview popover when the overview card is clicked.

    An event filter (not a subclass override) keeps the existing card widget
    untouched — no reparenting, no method injection on the card instance.
    """

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            open_result_overview_popover(self._owner)
        return False


def install_overview_popover_trigger(owner: Any) -> None:
    """Install a click filter on the existing overview card (idempotent)."""
    card = getattr(owner, "workbench_result_overview_panel", None)
    if card is None:
        return
    if getattr(owner, "_result_overview_popover_filter", None) is not None:
        return
    click_filter = _OverviewCardClickFilter(owner)
    card.installEventFilter(click_filter)
    owner._result_overview_popover_filter = click_filter
    card.setCursor(Qt.CursorShape.PointingHandCursor)


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
    return _tr(owner, "—", "—")


def _elapsed_label(owner: Any) -> str:
    # No elapsed is currently tracked on the window; surface a neutral placeholder
    # rather than fabricate a duration. Reads the attribute if a future path adds
    # ``_last_result_elapsed`` so this stays a single source of truth.
    elapsed = getattr(owner, "_last_result_elapsed", None)
    if isinstance(elapsed, (int, float)) and elapsed >= 0:
        return f"{elapsed:.3f} s"
    return _tr(owner, "—", "—")


def build_result_overview_popover(owner: Any) -> QWidget:
    """Create (or refresh) the top-level popover widget and return it."""
    popover = getattr(owner, "_result_overview_popover", None)
    if popover is None:
        popover = QWidget(owner, Qt.WindowType.Popup)
        popover.setObjectName("result_overview_popover")
        layout = QVBoxLayout(popover)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel()
        title.setObjectName("result_overview_popover_title")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        fields = (
            ("method", "方法", "Method"),
            ("value", "结果值", "Value"),
            ("uncertainty", "不确定度", "Uncertainty"),
            ("elapsed", "用时", "Elapsed"),
            ("points", "点数", "Points"),
        )
        value_labels: dict[str, QLabel] = {}
        for row, (key, zh, en) in enumerate(fields):
            name_label = QLabel()
            name_label.setObjectName(f"result_overview_popover_{key}_name")
            name_label.setProperty("_zh", zh)
            name_label.setProperty("_en", en)
            value_label = QLabel()
            value_label.setObjectName(f"result_overview_popover_{key}_value")
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
            value_labels[key] = value_label
        layout.addLayout(grid)

        popover._datalab_title = title
        popover._datalab_value_labels = value_labels
        owner._result_overview_popover = popover

    _refresh_popover_contents(owner, popover)
    return popover


def _refresh_popover_contents(owner: Any, popover: QWidget) -> None:
    state = _overview_state(owner)
    status, status_label = _status_badge(owner, state)
    title = popover._datalab_title
    title.setText(_tr(owner, "结果概览", "Result overview") + f" · {status_label}")

    # Refresh the bilingual field name labels.
    for label in popover.findChildren(QLabel):
        zh = label.property("_zh")
        en = label.property("_en")
        if zh is not None and en is not None:
            label.setText(_tr(owner, str(zh), str(en)) + "：")

    rows = state.total_rows if state.kind == "tabular" else 0
    columns = len(state.headers) if state.kind == "tabular" else 0
    values = popover._datalab_value_labels
    values["method"].setText(_method_label(owner))
    values["value"].setText(_value_summary(owner, state, status))
    values["uncertainty"].setText(_uncertainty_summary(owner, state))
    values["elapsed"].setText(_elapsed_label(owner))
    values["points"].setText(str(rows) if rows else _points_fallback(owner, state, columns))


def _value_summary(owner: Any, state: Any, status: str) -> str:
    if state.kind == "tabular":
        return _tr(owner, f"{state.total_rows} 行表格", f"{state.total_rows}-row table")
    if state.has_plot and state.has_text:
        return _tr(owner, "图片 + 文本", "Plot + text")
    if state.has_plot:
        return _tr(owner, "图片", "Plot")
    if state.has_text:
        return _tr(owner, "文本", "Text")
    if status == "running":
        return _tr(owner, "计算中", "Running")
    if status == "failed":
        return _tr(owner, "失败", "Failed")
    return _tr(owner, "—", "—")


def _uncertainty_summary(owner: Any, state: Any) -> str:
    if state.kind == "tabular":
        return _tr(owner, f"{len(state.headers)} 列", f"{len(state.headers)} columns")
    return _tr(owner, "—", "—")


def _points_fallback(owner: Any, state: Any, columns: int) -> str:
    if columns:
        return str(columns)
    return _tr(owner, "0", "0")


def open_result_overview_popover(owner: Any) -> QWidget:
    """Build/refresh the popover, position it near the overview card, and show it."""
    popover = build_result_overview_popover(owner)
    card = getattr(owner, "workbench_result_overview_panel", None)
    if card is not None:
        try:
            global_pos = card.mapToGlobal(card.rect().bottomLeft())
            popover.move(global_pos)
        except (RuntimeError, AttributeError):
            pass
    popover.adjustSize()
    popover.show()
    popover.raise_()
    return popover
