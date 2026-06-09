"""Adapters for the compact result overview in the workbench rail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import table_style

MAX_RESULT_OVERVIEW_ROWS = 50
MAX_RESULT_OVERVIEW_TABLE_HEIGHT = 220
MAX_RESULT_OVERVIEW_STATE_ROWS = 100

ResultOverviewKind = Literal["none", "running", "tabular", "plot", "text", "plot_text", "empty_success", "failed"]


@dataclass(frozen=True, slots=True)
class ResultOverviewState:
    kind: ResultOverviewKind
    preview_rows: tuple[dict[str, object], ...] = ()
    total_rows: int = 0
    headers: tuple[str, ...] = ()
    has_plot: bool = False
    has_text: bool = False


def build_result_overview(owner: Any) -> QWidget:
    widget = QWidget()
    widget.setObjectName("workbench_result_overview_panel")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    owner.workbench_result_overview = QLabel(owner._tr("暂无结果", "No results"))
    owner.workbench_result_overview.setObjectName("workbench_result_overview")
    layout.addWidget(owner.workbench_result_overview)

    table = QTableWidget()
    table.setObjectName("workbench_result_table")
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(table_style())
    table.setMaximumHeight(MAX_RESULT_OVERVIEW_TABLE_HEIGHT)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    owner.workbench_result_table = table
    layout.addWidget(table)
    return widget


def _has_plot_result(owner: Any) -> bool:
    if getattr(owner, "result_plot_bytes", None):
        return True
    if getattr(owner, "_result_plot_base_pixmap", None) is not None:
        return True
    for attr in ("current_fit_figures", "current_stats_figures", "current_error_figures", "current_extrap_figures"):
        if getattr(owner, attr, None):
            return True
    return False


def _has_text_result(owner: Any) -> bool:
    return bool(str(getattr(owner, "_last_result_rendered_text", "") or "").strip())


def _overview_state(owner: Any) -> ResultOverviewState:
    workbench_state = str(getattr(owner, "_workbench_result_state", "none") or "none")
    raw_rows = list(getattr(owner, "_csv_rows", []) or [])
    headers = tuple(str(header) for header in (getattr(owner, "_csv_headers", []) or []))
    has_plot = _has_plot_result(owner)
    has_text = _has_text_result(owner)

    if workbench_state == "failed":
        return ResultOverviewState("failed", has_plot=has_plot, has_text=has_text)
    if workbench_state == "running":
        return ResultOverviewState("running", has_plot=has_plot, has_text=has_text)
    if raw_rows or headers:
        preview_rows = tuple(dict(row) for row in raw_rows[:MAX_RESULT_OVERVIEW_STATE_ROWS] if isinstance(row, dict))
        return ResultOverviewState(
            "tabular",
            preview_rows=preview_rows,
            total_rows=len(raw_rows),
            headers=headers,
            has_plot=has_plot,
            has_text=has_text,
        )
    if has_plot and has_text:
        return ResultOverviewState("plot_text", has_plot=True, has_text=True)
    if has_plot:
        return ResultOverviewState("plot", has_plot=True)
    if has_text:
        return ResultOverviewState("text", has_text=True)
    if workbench_state == "complete":
        return ResultOverviewState("empty_success")
    return ResultOverviewState("none")


def _format_tabular_summary(owner: Any, total_rows: int, column_count: int, visible_count: int) -> str:
    extra_zh = f"（显示前 {visible_count} 行）" if visible_count < total_rows else ""
    row_word = "row" if total_rows == 1 else "rows"
    column_word = "column" if column_count == 1 else "columns"
    extra_en = f" (showing first {visible_count} {row_word})" if visible_count < total_rows else ""
    return owner._tr(
        f"结果数据：{total_rows} 行，{column_count} 列{extra_zh}",
        f"Result data: {total_rows} {row_word}, {column_count} {column_word}{extra_en}",
    )


def refresh_result_overview(owner: Any) -> None:
    state = _overview_state(owner)
    rows = list(state.preview_rows)
    headers = list(state.headers)
    visible_rows = rows[:MAX_RESULT_OVERVIEW_ROWS]
    table = owner.workbench_result_table
    table.clear()
    table.setRowCount(len(visible_rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels([str(header) for header in headers])
    for row_index, row in enumerate(visible_rows):
        for col_index, header in enumerate(headers):
            value = row.get(header, "") if isinstance(row, dict) else ""
            table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
    if state.kind == "tabular":
        summary = _format_tabular_summary(owner, state.total_rows, len(headers), len(visible_rows))
        if state.has_plot and state.has_text:
            owner.workbench_result_overview.setText(
                summary + owner._tr("；另有图片和文本", "; plot and text also available")
            )
        elif state.has_plot:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有图片", "; plot also available"))
        elif state.has_text:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有文本", "; text also available"))
        else:
            owner.workbench_result_overview.setText(summary)
    elif state.kind == "plot_text":
        owner.workbench_result_overview.setText(
            owner._tr("结果已生成；有图片和文本；无表格数据", "Result ready; plot and text available; no tabular data")
        )
    elif state.kind == "plot":
        owner.workbench_result_overview.setText(owner._tr("结果已生成；无表格数据", "Result ready; no tabular data"))
    elif state.kind == "text":
        owner.workbench_result_overview.setText(owner._tr("文本结果已生成；无表格数据", "Text result ready; no tabular data"))
    elif state.kind == "failed":
        owner.workbench_result_overview.setText(owner._tr("计算失败", "Calculation failed"))
    elif state.kind == "running":
        owner.workbench_result_overview.setText(owner._tr("计算中", "Running"))
    elif state.kind == "empty_success":
        owner.workbench_result_overview.setText(owner._tr("计算完成；无可显示结果", "Calculation complete; no displayable result"))
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
    table.resizeColumnsToContents()
