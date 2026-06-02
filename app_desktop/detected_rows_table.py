from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

SOURCE_DETECTED = "detected"
SOURCE_MANUAL = "manual"


class DetectedRowsController:
    """Preserve manual rows while replacing stale detected rows by name."""

    def __init__(
        self,
        table_view: QTableWidget,
        *,
        columns: Sequence[str],
        name_column: str = "name",
        min_rows: int = 0,
        on_changed: Any | None = None,
    ) -> None:
        self.table_view = table_view
        self.columns = tuple(columns)
        self.name_column = name_column
        self.min_rows = max(0, int(min_rows))
        self._on_changed = on_changed
        if self.name_column not in self.columns:
            raise ValueError(f"name_column {self.name_column!r} is not in columns")

    def rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row_index in range(self.table_view.rowCount()):
            row = self.row(row_index)
            if any(row.values()):
                source = self.row_source(row_index)
                if source == SOURCE_DETECTED:
                    row["source"] = source
                rows.append(row)
        return rows

    def all_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row_index in range(self.table_view.rowCount()):
            row = self.row(row_index)
            source = self.row_source(row_index)
            if source == SOURCE_DETECTED:
                row["source"] = source
            rows.append(row)
        return rows

    def row(self, row_index: int) -> dict[str, str]:
        return {
            key: self.cell_text(row_index, column_index)
            for column_index, key in enumerate(self.columns)
        }

    def add_row(self, row: dict[str, Any] | None = None) -> int:
        row_values = row or {}
        row_index = self.table_view.rowCount()
        self.table_view.insertRow(row_index)
        for column_index, key in enumerate(self.columns):
            self.table_view.setItem(row_index, column_index, QTableWidgetItem(self._string_value(row_values.get(key))))
        self.set_row_source(row_index, self.source_value(row_values.get("source")))
        return row_index

    def delete_rows(self, rows: Iterable[int]) -> None:
        for row_index in sorted({int(row) for row in rows}, reverse=True):
            if 0 <= row_index < self.table_view.rowCount():
                self.table_view.removeRow(row_index)
        self._emit_changed()

    def is_row_empty(self, row_index: int) -> bool:
        if row_index < 0 or row_index >= self.table_view.rowCount():
            return False
        return not any(self.cell_text(row_index, column_index) for column_index in range(len(self.columns)))

    def set_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        clean_rows = [self._clean_row(row) for row in rows]
        self._set_table_rows(clean_rows)

    def set_detected_names(self, names: Sequence[str], *, keep_orphans: bool = True) -> set[str]:
        all_rows = self.all_rows()
        existing = {
            row[self.name_column]: row
            for row in all_rows
            if row.get(self.name_column, "").strip()
        }
        seen: set[str] = set()
        detected_rows: list[dict[str, str]] = []
        for raw_name in names:
            name = str(raw_name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            row = dict(existing.get(name, {self.name_column: name}))
            if not keep_orphans:
                row["source"] = SOURCE_DETECTED
            detected_rows.append(self._clean_row(row))
        orphan_rows = [
            self._clean_row(row)
            for row in all_rows
            if self._has_visible_values(row)
            and (not row.get(self.name_column, "").strip() or row[self.name_column] not in seen)
            and (keep_orphans or row.get("source") != SOURCE_DETECTED)
        ]
        empty_rows = [
            self._clean_row(row)
            for row in all_rows
            if not self._has_visible_values(row)
        ]
        self._set_table_rows(detected_rows + orphan_rows + empty_rows)
        return seen

    def cell_text(self, row: int, column: int) -> str:
        item = self.table_view.item(row, column)
        return item.text().strip() if item else ""

    @staticmethod
    def source_value(value: Any) -> str:
        return SOURCE_DETECTED if str(value or "").strip() == SOURCE_DETECTED else SOURCE_MANUAL

    def row_source(self, row_index: int) -> str:
        item = self.table_view.item(row_index, self.columns.index(self.name_column))
        if item is None:
            return SOURCE_MANUAL
        data = item.data(Qt.ItemDataRole.UserRole)
        return self.source_value(data)

    def set_row_source(self, row_index: int, source: str) -> None:
        column = self.columns.index(self.name_column)
        item = self.table_view.item(row_index, column)
        if item is None:
            item = QTableWidgetItem("")
            self.table_view.setItem(row_index, column, item)
        item.setData(Qt.ItemDataRole.UserRole, self.source_value(source))

    def mark_row_manual(self, row_index: int) -> None:
        if 0 <= row_index < self.table_view.rowCount():
            self.set_row_source(row_index, SOURCE_MANUAL)

    def _set_table_rows(self, rows: list[dict[str, str]]) -> None:
        self.table_view.clearContents()
        self.table_view.setRowCount(max(self.min_rows, len(rows)))
        for row_index, row in enumerate(rows):
            for column_index, key in enumerate(self.columns):
                self.table_view.setItem(row_index, column_index, QTableWidgetItem(row.get(key, "")))
            self.set_row_source(row_index, self.source_value(row.get("source")))
        self._emit_changed()

    def _clean_row(self, row: dict[str, Any]) -> dict[str, str]:
        clean = {key: self._string_value(row.get(key)) for key in self.columns}
        if self.source_value(row.get("source")) == SOURCE_DETECTED:
            clean["source"] = SOURCE_DETECTED
        return clean

    @staticmethod
    def _has_visible_values(row: dict[str, str]) -> bool:
        return any(value for key, value in row.items() if key != "source")

    @staticmethod
    def _string_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _emit_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()


class DetectedRowsTable(QWidget):
    """Generic Qt table for rows populated by name detection."""

    changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        columns: Sequence[str],
        headers: Sequence[str],
        name_column: str = "name",
        min_rows: int = 0,
    ) -> None:
        super().__init__(parent)
        self._syncing = False
        self._min_rows = max(0, int(min_rows))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table_view = QTableWidget(self._min_rows, len(columns))
        self.table_view.setHorizontalHeaderLabels(list(headers))
        self.table_view.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table_view)
        self.detected_rows_controller = DetectedRowsController(
            self.table_view,
            columns=columns,
            name_column=name_column,
            min_rows=self._min_rows,
            on_changed=self._emit_changed,
        )

    def rows(self) -> list[dict[str, str]]:
        return self.detected_rows_controller.rows()

    def set_rows(self, rows: Iterable[dict[str, Any]] | None) -> None:
        self._syncing = True
        try:
            self.detected_rows_controller.set_rows(rows or [])
        finally:
            self._syncing = False
        self._emit_changed()

    def set_detected_names(self, names: Sequence[str], *, keep_orphans: bool = True) -> set[str]:
        self._syncing = True
        try:
            return self.detected_rows_controller.set_detected_names(names, keep_orphans=keep_orphans)
        finally:
            self._syncing = False
            self._emit_changed()

    def add_row(self, row: dict[str, Any] | None = None) -> None:
        row_index = self.detected_rows_controller.add_row(row)
        self.table_view.clearSelection()
        self.table_view.selectRow(row_index)
        self.table_view.setCurrentCell(row_index, 0)
        self._emit_changed()

    def delete_rows(self, rows: Iterable[int]) -> None:
        self.detected_rows_controller.delete_rows(rows)

    def is_row_empty(self, row_index: int) -> bool:
        return self.detected_rows_controller.is_row_empty(row_index)

    def _emit_changed(self, *_args: object) -> None:
        if not self._syncing:
            self.changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if not self._syncing:
            self.detected_rows_controller.mark_row_manual(item.row())
        self._emit_changed()
