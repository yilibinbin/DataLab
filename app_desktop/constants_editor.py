from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import mpmath as mp
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from datalab_latex.latex_tables_error_propagation import parse_uncertainty_format
from fitting.model_parser import is_reserved_expression_name


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_VIEW = 0
_TEXT_VIEW = 1


class ConstantsEditor(QWidget):
    """Reusable constants editor with draft-preserving table/text views."""

    changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        min_rows: int = 4,
        checked: bool = False,
        checkbox_text: str = "启用常数设置",
        numeric_mode: str = "uncertainty",
    ) -> None:
        super().__init__(parent)
        self._min_rows = max(1, int(min_rows))
        self._syncing = False
        self._numeric_mode = numeric_mode
        self._table_revision = 0
        self._text_source_table_revision = -1
        self._inputs_visible = True
        self._constructed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.checkbox = QCheckBox(checkbox_text)
        self.checkbox.setChecked(bool(checked))
        self.checkbox.toggled.connect(self._on_checked_changed)
        layout.addWidget(self.checkbox)

        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.add_button = QPushButton("+ 行")
        self.remove_button = QPushButton("- 行")
        self.clear_button = QPushButton("清除")
        self.view_toggle_button = QPushButton("文本视图")
        self.add_button.clicked.connect(self._add_row)
        self.remove_button.clicked.connect(self._remove_row)
        self.clear_button.clicked.connect(self.clear)
        self.view_toggle_button.clicked.connect(self._toggle_view)
        controls_layout.addWidget(self.add_button)
        controls_layout.addWidget(self.remove_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.view_toggle_button)
        controls_layout.addStretch()
        layout.addWidget(self.controls_widget)

        self.stack = QStackedWidget()
        self.table_view = QTableWidget(self._min_rows, 2)
        self.table_view.setHorizontalHeaderLabels(["Name", "Value"])
        self.table_view.setMinimumHeight(120)
        self.table_view.itemChanged.connect(self._on_table_changed)
        self.stack.addWidget(self.table_view)

        self.text_view = QPlainTextEdit()
        self.text_view.setMinimumHeight(120)
        self.text_view.setPlaceholderText(
            "# One constant per line: name value\n"
            "# Blank lines and lines starting with # are allowed\n"
            "ALPHA 7.2973525693(11)[-3]"
        )
        self.text_view.textChanged.connect(self._on_text_changed)
        self.stack.addWidget(self.text_view)
        self.stack.setCurrentIndex(_TABLE_VIEW)
        layout.addWidget(self.stack)

        self._on_checked_changed(self.checkbox.isChecked())
        self._constructed = True

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt-style API
        self.checkbox.setChecked(bool(checked))

    def isChecked(self) -> bool:  # noqa: N802 - Qt-style API
        return bool(self.checkbox.isChecked())

    def using_text_view(self) -> bool:
        return self.stack.currentIndex() == _TEXT_VIEW

    def use_text_view(self, enabled: bool) -> None:
        if enabled and self.stack.currentIndex() != _TEXT_VIEW:
            if not self.text_view.toPlainText().strip() or self._text_source_table_revision != self._table_revision:
                self._set_raw_text(self._rows_to_text(self._table_rows()), source_table_revision=self._table_revision)
            self.stack.setCurrentIndex(_TEXT_VIEW)
        elif not enabled and self.stack.currentIndex() != _TABLE_VIEW:
            self._set_table_rows(self._text_rows(self.text_view.toPlainText()))
            self._text_source_table_revision = self._table_revision
            self.stack.setCurrentIndex(_TABLE_VIEW)
        self._update_toggle_label()

    def set_inputs_visible(self, visible: bool) -> None:
        self._inputs_visible = bool(visible)
        self._apply_inputs_visibility()

    def rows(self) -> list[dict[str, str]]:
        if self.using_text_view():
            return self._text_rows(self.text_view.toPlainText())
        return self._table_rows()

    def set_rows(self, rows: Iterable[dict[str, Any]] | dict[str, Any] | None) -> None:
        if isinstance(rows, dict):
            clean_rows = [{"name": str(name), "value": str(value)} for name, value in rows.items()]
        elif rows is None:
            clean_rows = []
        else:
            clean_rows = [
                {"name": str(row.get("name") or ""), "value": str(row.get("value") or "")}
                for row in rows
                if isinstance(row, dict)
            ]
        self._set_table_rows(clean_rows)
        if self.using_text_view():
            self.text_view.setPlainText(self._rows_to_text(clean_rows))

    def text(self) -> str:
        return self._rows_to_text(self.rows())

    def raw_text(self) -> str:
        return self.text_view.toPlainText()

    def set_raw_text(self, text: str) -> None:
        self._set_raw_text(text or "", source_table_revision=self._table_revision)

    def set_text(self, text: str) -> None:
        self._set_raw_text(text or "", source_table_revision=-1)
        if not self.using_text_view():
            self._set_table_rows(self._text_rows(text or ""))
            self._text_source_table_revision = self._table_revision

    def clear(self) -> None:
        self._set_table_rows([])
        self._set_raw_text("", source_table_revision=self._table_revision)
        self._emit_changed()

    def constants_dict(self, *, validate: bool = True) -> dict[str, str]:
        constants: dict[str, str] = {}
        for row in self.rows():
            name = row["name"].strip()
            value = row["value"].strip()
            if not name and not value:
                continue
            if not validate and (not name or not value):
                continue
            if not name:
                raise ValueError("Constant name cannot be empty.")
            if not _IDENTIFIER_RE.fullmatch(name):
                raise ValueError(f"Invalid constant name: {name}")
            if is_reserved_expression_name(name):
                raise ValueError(f"Constant name is reserved: {name}")
            if not value:
                raise ValueError(f"Constant {name} needs a value.")
            if name in constants:
                raise ValueError(f"Duplicate constant name: {name}")
            if validate:
                self._validate_value(name, value)
            constants[name] = value
        return constants

    def _validate_value(self, name: str, value: str) -> None:
        try:
            if self._numeric_mode == "mpmath":
                mp.mpf(value)
            else:
                parse_uncertainty_format(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid value for constant {name}.") from exc

    def _on_checked_changed(self, checked: bool) -> None:
        if self._constructed and checked and self.parentWidget() is None and not self.isVisible():
            self.show()
        self._apply_inputs_visibility()
        self._emit_changed()

    def _apply_inputs_visibility(self) -> None:
        visible = self._inputs_visible and self.checkbox.isChecked()
        self.controls_widget.setVisible(visible)
        self.stack.setVisible(visible)
        self.controls_widget.setEnabled(visible)
        self.stack.setEnabled(visible)

    def _emit_changed(self, *_args: object) -> None:
        if not self._syncing:
            self.changed.emit()

    def _on_table_changed(self, *_args: object) -> None:
        if not self._syncing:
            self._table_revision += 1
        self._emit_changed()

    def _on_text_changed(self) -> None:
        if not self._syncing:
            self._text_source_table_revision = -1
        self._emit_changed()

    def _add_row(self) -> None:
        if self.using_text_view():
            text = self.text_view.toPlainText()
            self._set_raw_text(text + ("\n" if text else ""), source_table_revision=-1)
            return
        self.table_view.insertRow(self.table_view.rowCount())
        self._emit_changed()

    def _remove_row(self) -> None:
        if self.using_text_view():
            rows = self._text_rows(self.text_view.toPlainText())
            if rows:
                rows.pop()
            self._set_raw_text(self._rows_to_text(rows), source_table_revision=-1)
            return
        if self.table_view.rowCount() <= 0:
            return
        self.table_view.removeRow(self.table_view.rowCount() - 1)
        self._emit_changed()

    def _toggle_view(self) -> None:
        self.use_text_view(not self.using_text_view())
        self._emit_changed()

    def _update_toggle_label(self) -> None:
        self.view_toggle_button.setText("表格视图" if self.using_text_view() else "文本视图")

    def _table_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in range(self.table_view.rowCount()):
            name_item = self.table_view.item(row, 0)
            value_item = self.table_view.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            value = value_item.text().strip() if value_item else ""
            if name or value:
                rows.append({"name": name, "value": value})
        return rows

    def _set_table_rows(self, rows: list[dict[str, str]]) -> None:
        self._syncing = True
        try:
            self.table_view.clearContents()
            self.table_view.setRowCount(max(self._min_rows, len(rows)))
            for row_index, row in enumerate(rows):
                self.table_view.setItem(row_index, 0, QTableWidgetItem(row.get("name", "")))
                self.table_view.setItem(row_index, 1, QTableWidgetItem(row.get("value", "")))
        finally:
            self._syncing = False
        self._table_revision += 1
        self._emit_changed()

    def _set_raw_text(self, text: str, *, source_table_revision: int) -> None:
        self._syncing = True
        try:
            self.text_view.setPlainText(text)
        finally:
            self._syncing = False
        self._text_source_table_revision = source_table_revision
        self._emit_changed()

    @staticmethod
    def _rows_to_text(rows: Iterable[dict[str, str]]) -> str:
        lines = []
        for row in rows:
            name = str(row.get("name") or "").strip()
            value = str(row.get("value") or "").strip()
            if name or value:
                lines.append(f"{name} {value}".strip())
        return "\n".join(lines)

    @staticmethod
    def _text_rows(text: str) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                name, value = stripped.split("=", 1)
                name = name.strip()
                value = value.strip()
            else:
                parts = stripped.split(None, 1)
                if len(parts) == 1:
                    name, value = parts[0].strip(), ""
                else:
                    name, value = parts[0].strip(), parts[1].strip()
            if name or value:
                rows.append({"name": name, "value": value})
        return rows
