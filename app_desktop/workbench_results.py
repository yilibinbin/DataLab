"""Adapters for the compact result overview in the workbench rail."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import table_style


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
    owner.workbench_result_table = table
    layout.addWidget(table)
    return widget


def refresh_result_overview(owner: Any) -> None:
    rows = list(getattr(owner, "_csv_rows", []) or [])
    headers = list(getattr(owner, "_csv_headers", []) or [])
    table = owner.workbench_result_table
    table.clear()
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels([str(header) for header in headers])
    for row_index, row in enumerate(rows):
        for col_index, header in enumerate(headers):
            value = row.get(header, "") if isinstance(row, dict) else ""
            table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
    if rows:
        owner.workbench_result_overview.setText(
            owner._tr(
                f"结果数据：{len(rows)} 行，{len(headers)} 列",
                f"Result data: {len(rows)} rows, {len(headers)} columns",
            )
        )
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
    table.resizeColumnsToContents()
