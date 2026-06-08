"""Adapters for the compact result overview in the workbench rail."""

from __future__ import annotations

from typing import Any

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


def refresh_result_overview(owner: Any) -> None:
    rows = list(getattr(owner, "_csv_rows", []) or [])
    headers = list(getattr(owner, "_csv_headers", []) or [])
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
    if rows:
        extra_zh = f"（显示前 {len(visible_rows)} 行）" if len(visible_rows) < len(rows) else ""
        row_word = "row" if len(rows) == 1 else "rows"
        column_word = "column" if len(headers) == 1 else "columns"
        extra_en = f" (showing first {len(visible_rows)} {row_word})" if len(visible_rows) < len(rows) else ""
        owner.workbench_result_overview.setText(
            owner._tr(
                f"结果数据：{len(rows)} 行，{len(headers)} 列{extra_zh}",
                f"Result data: {len(rows)} {row_word}, {len(headers)} {column_word}{extra_en}",
            )
        )
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
    table.resizeColumnsToContents()
