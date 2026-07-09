from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_desktop.fitting_input_normalization import (
    constants_rows_to_text,
    normalize_constants_state,
    parse_constants_text,
)
from app_desktop.theme import constants_editor_style
from app_desktop.widget_hints import set_accessible_description


_TABLE_VIEW = 0
_TEXT_VIEW = 1

class _HelpButton(QPushButton):
    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt API override
        super().setToolTip(text)
        set_accessible_description(self, text)
        self.setVisible(bool(text.strip()))


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
        if numeric_mode not in {"uncertainty", "mpmath"}:
            raise ValueError(f"Unsupported constants numeric mode: {numeric_mode}")
        self._min_rows = max(1, int(min_rows))
        self._syncing = False
        self._numeric_mode = numeric_mode
        self._table_revision = 0
        self._text_source_table_revision = -1
        self._inputs_visible = True
        self._constructed = False
        self._add_row_label = "+ 行"
        self._remove_row_label = "- 行"
        self._clear_label = "清除"
        self._table_view_label = "表格视图"
        self._text_view_label = "文本视图"
        self.setProperty("datalab_constants_card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(52)
        self.setStyleSheet(constants_editor_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # The checkbox is legacy/hidden; keep it for callers that still poke it, but it no longer
        # occupies its own header row (the summary + ? sit in the controls row, like the data card).
        self.checkbox = QCheckBox(checkbox_text)
        self.checkbox.setChecked(bool(checked))
        self.checkbox.toggled.connect(self._on_checked_changed)
        self.checkbox.hide()

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
        # Row-count summary (mirrors the data card's "N 行"), then the ? help button — both on the
        # RIGHT of the controls row, not a separate header line.
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("constants_summary")
        controls_layout.addWidget(self.summary_label)
        self.help_button = _HelpButton("?")
        self.help_button.setFlat(True)
        self.help_button.setFocusPolicy(Qt.NoFocus)
        self.help_button.setFixedWidth(24)
        self.help_button.hide()
        controls_layout.addWidget(self.help_button)
        layout.addWidget(self.controls_widget)

        self.stack = QStackedWidget()
        self.table_view = QTableWidget(self._min_rows, 2)
        self.table_view.setHorizontalHeaderLabels(["Name", "Value"])
        self.table_view.setMinimumHeight(120)
        self.table_view.itemChanged.connect(self._on_table_changed)
        # Excel-like block copy (Ctrl/Cmd+C → TSV).
        from app_desktop.table_copy import install_cell_copy

        install_cell_copy(self.table_view)
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
        self._update_summary()
        self._constructed = True

    def set_embedded_in_workbench(self, embedded: bool) -> None:
        embedded = bool(embedded)
        self.setProperty("datalab_constants_embedded", embedded)
        layout = self.layout()
        if layout is not None:
            margin = 0 if embedded else 8
            layout.setContentsMargins(margin, margin, margin, margin)
        self.setStyleSheet(constants_editor_style(embedded=embedded))
        self.style().unpolish(self)
        self.style().polish(self)

    def refresh_theme_style(self) -> None:
        """Re-apply the (theme-dependent) editor style for the current embedded state. Its style is
        otherwise set once at construction/embedding, so a live light↔dark toggle would leave the
        button colors stale — the theme refresh calls this."""
        embedded = bool(self.property("datalab_constants_embedded"))
        self.setStyleSheet(constants_editor_style(embedded=embedded))
        self.style().unpolish(self)
        self.style().polish(self)

    def set_control_labels(
        self,
        *,
        add_row: str,
        remove_row: str,
        clear: str,
        table_view: str,
        text_view: str,
    ) -> None:
        self._add_row_label = add_row
        self._remove_row_label = remove_row
        self._clear_label = clear
        self._table_view_label = table_view
        self._text_view_label = text_view
        self.add_button.setText(add_row)
        self.remove_button.setText(remove_row)
        self.clear_button.setText(clear)
        self._update_toggle_label()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt-style API
        self.checkbox.setChecked(bool(checked))

    def set_table_headers(self, name: str, value: str) -> None:
        self.table_view.setHorizontalHeaderLabels([name, value])

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt API override
        super().setToolTip(text)
        set_accessible_description(self, text)
        self.checkbox.setToolTip(text)
        set_accessible_description(self.checkbox, text)
        self.help_button.setToolTip(text)
        self.table_view.setToolTip(text)
        set_accessible_description(self.table_view, text)
        self.text_view.setToolTip(text)
        set_accessible_description(self.text_view, text)

    def isChecked(self) -> bool:  # noqa: N802 - Qt-style API
        try:
            return bool(self.constants_dict(validate=False))
        except Exception:
            return False

    def using_text_view(self) -> bool:
        return self.stack.currentIndex() == _TEXT_VIEW

    def numeric_mode(self) -> str:
        return self._numeric_mode

    def set_numeric_mode(self, mode: str) -> None:
        if mode not in {"uncertainty", "mpmath"}:
            raise ValueError(f"Unsupported constants numeric mode: {mode}")
        if self._numeric_mode != mode:
            self._numeric_mode = mode
            self._emit_changed()

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

    def inputs_visible(self) -> bool:
        return self._inputs_visible

    def rows(self) -> list[dict[str, str]]:
        if self.using_text_view():
            return self._text_rows(self.text_view.toPlainText())
        return self._table_rows()

    def set_rows(self, rows: Iterable[dict[str, Any]] | dict[str, Any] | None) -> None:
        clean_rows = normalize_constants_state(
            enabled=True,
            rows=rows,
            numeric_mode=self._numeric_mode,
        ).persisted_rows()
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
        return normalize_constants_state(
            enabled=True,
            view="text" if self.using_text_view() else "table",
            rows=self.rows(),
            text=self.text_view.toPlainText(),
            numeric_mode=self._numeric_mode,
        ).compute_dict(validate=validate)

    def _on_checked_changed(self, checked: bool) -> None:
        if self._constructed and checked and self.parentWidget() is None and not self.isVisible():
            self.show()
        self._apply_inputs_visibility()
        self._emit_changed()

    def _apply_inputs_visibility(self) -> None:
        visible = self._inputs_visible
        self.controls_widget.setVisible(visible)
        self.stack.setVisible(visible)
        self.controls_widget.setEnabled(visible)
        self.stack.setEnabled(visible)

    def _update_summary(self) -> None:
        """Show the number of filled constant rows (mirrors the data card's "N 行")."""
        label = getattr(self, "summary_label", None)
        if label is None:
            return
        try:
            count = len([r for r in self.rows() if (r.get("name") or r.get("value"))])
        except Exception:
            count = 0
        label.setText(f"{count} 行")

    def _emit_changed(self, *_args: object) -> None:
        self._update_summary()
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
        self.view_toggle_button.setText(self._table_view_label if self.using_text_view() else self._text_view_label)

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
        return constants_rows_to_text(rows)

    @staticmethod
    def _text_rows(text: str) -> list[dict[str, str]]:
        return parse_constants_text(text)
