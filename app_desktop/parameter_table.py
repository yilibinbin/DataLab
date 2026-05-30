from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app_desktop.fitting_input_normalization import ParameterRowsState, normalize_parameter_rows

_COLUMNS = ("name", "initial", "fixed", "min", "max")
_HEADERS = ("Name", "Init", "Fixed", "Min", "Max")


class ParameterTable(QWidget):
    """Reusable fitting-parameter table with draft-preserving row APIs."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, min_rows: int = 0) -> None:
        super().__init__(parent)
        self._constraints_enabled = False
        self._syncing = False
        self._min_rows = max(0, int(min_rows))
        self._orphan_names: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table_view = QTableWidget(self._min_rows, len(_COLUMNS))
        self.table_view.setHorizontalHeaderLabels(list(_HEADERS))
        self.table_view.itemChanged.connect(self._emit_changed)
        layout.addWidget(self.table_view)
        self.set_constraints_enabled(False)

    def set_constraints_enabled(self, enabled: bool) -> None:
        self._constraints_enabled = bool(enabled)
        for column in range(2, len(_COLUMNS)):
            self.table_view.setColumnHidden(column, not self._constraints_enabled)
        self._emit_changed()

    def constraints_enabled(self) -> bool:
        return self._constraints_enabled

    def rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row_index in range(self.table_view.rowCount()):
            row = {
                key: self._cell_text(row_index, column)
                for column, key in enumerate(_COLUMNS)
            }
            if any(row.values()):
                rows.append(row)
        return rows

    def compute_rows(self) -> list[dict[str, str]]:
        return self._normalized_state().compute_rows()

    def orphan_names(self) -> set[str]:
        existing = {row["name"].strip() for row in self.rows() if row["name"].strip()}
        self._orphan_names.intersection_update(existing)
        return set(self._orphan_names)

    def mark_orphans(self, active_names: Iterable[str]) -> None:
        active = {str(name).strip() for name in active_names if str(name).strip()}
        self._orphan_names = {
            row["name"].strip()
            for row in self.rows()
            if row["name"].strip() and row["name"].strip() not in active
        }
        self._emit_changed()

    def add_parameter_row(self, row: dict[str, Any] | None = None) -> None:
        row_values = row or {}
        row_index = self.table_view.rowCount()
        self.table_view.insertRow(row_index)
        for column, key in enumerate(_COLUMNS):
            self.table_view.setItem(row_index, column, QTableWidgetItem(self._string_value(row_values.get(key))))
        self.table_view.clearSelection()
        self.table_view.selectRow(row_index)
        self.table_view.setCurrentCell(row_index, 0)
        name = self._string_value(row_values.get("name")).strip()
        if name:
            self._orphan_names.discard(name)
        self._emit_changed()

    def delete_rows(self, rows: Iterable[int]) -> None:
        for row_index in sorted({int(row) for row in rows}, reverse=True):
            if row_index < 0 or row_index >= self.table_view.rowCount():
                continue
            name = self._cell_text(row_index, 0)
            self.table_view.removeRow(row_index)
            if name:
                self._orphan_names.discard(name)
        self._emit_changed()

    def clear_empty_rows(self) -> None:
        empty_rows = [
            row_index
            for row_index in range(self.table_view.rowCount())
            if self.is_row_empty(row_index)
        ]
        self.delete_rows(empty_rows)

    def is_row_empty(self, row_index: int) -> bool:
        if row_index < 0 or row_index >= self.table_view.rowCount():
            return False
        return not any(self._cell_text(row_index, column) for column in range(len(_COLUMNS)))

    def set_rows(self, rows: Iterable[dict[str, Any]] | dict[str, Any] | None) -> None:
        clean_rows = normalize_parameter_rows(
            rows,
            constraints_enabled=self._constraints_enabled,
            orphan_names=self._orphan_names,
        ).persisted_rows()
        self._set_table_rows(clean_rows)
        self.orphan_names()

    def set_names(self, names: Sequence[str], *, preserve: bool = True) -> None:
        if preserve:
            self.set_detected_names(names)
        else:
            self.set_rows([{"name": name, "initial": ""} for name in names])

    def set_detected_names(self, names: Sequence[str]) -> None:
        all_rows = self._all_rows()
        existing = {row["name"]: row for row in all_rows if row["name"]}
        seen: set[str] = set()
        detected_rows: list[dict[str, str]] = []
        for raw_name in names:
            name = str(raw_name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            detected_rows.append(
                existing.get(
                    name,
                    {"name": name, "initial": "", "fixed": "", "min": "", "max": ""},
                )
            )
        orphan_rows = [
            row
            for row in all_rows
            if any(row.values()) and (not row["name"] or row["name"] not in seen)
        ]
        empty_rows = [row for row in all_rows if not any(row.values())]
        self._set_table_rows(detected_rows + orphan_rows + empty_rows)
        self.mark_orphans(seen)

    def parameter_config(self, *, validate: bool = True) -> dict[str, dict[str, str]]:
        return self._normalized_state().compute_config(validate=validate)

    def rowCount(self) -> int:  # noqa: N802 - compatibility with QTableWidget tests
        return self.table_view.rowCount()

    def columnCount(self) -> int:  # noqa: N802
        return self.table_view.columnCount()

    def item(self, row: int, column: int) -> QTableWidgetItem | None:
        return self.table_view.item(row, column)

    def setItem(self, row: int, column: int, item: QTableWidgetItem) -> None:  # noqa: N802
        self.table_view.setItem(row, column, item)

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        previous = bool(super().blockSignals(block))
        self.table_view.blockSignals(block)
        return previous

    def _set_table_rows(self, rows: list[dict[str, str]]) -> None:
        self._syncing = True
        try:
            self.table_view.clearContents()
            self.table_view.setRowCount(max(self._min_rows, len(rows)))
            for row_index, row in enumerate(rows):
                for column, key in enumerate(_COLUMNS):
                    self.table_view.setItem(row_index, column, QTableWidgetItem(row.get(key, "")))
        finally:
            self._syncing = False
        self._emit_changed()

    def _cell_text(self, row: int, column: int) -> str:
        item = self.table_view.item(row, column)
        return item.text().strip() if item else ""

    def _all_rows(self) -> list[dict[str, str]]:
        return [
            {
                key: self._cell_text(row_index, column)
                for column, key in enumerate(_COLUMNS)
            }
            for row_index in range(self.table_view.rowCount())
        ]

    def _normalized_state(self) -> ParameterRowsState:
        return normalize_parameter_rows(
            self.rows(),
            constraints_enabled=self._constraints_enabled,
            orphan_names=self._orphan_names,
        )

    @staticmethod
    def _string_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _emit_changed(self, *_args: object) -> None:
        if not self._syncing:
            self.changed.emit()
