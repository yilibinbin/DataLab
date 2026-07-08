"""Excel-like cell copy for QTableWidgets.

Selecting a rectangular block and pressing Ctrl/Cmd+C copies it to the clipboard as TSV
(tab-separated columns, newline-separated rows) so it pastes cleanly into Excel/Sheets. This is
copy-only and self-contained (no paste/window coupling), so any table can opt in with one call.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QTableWidget


class _CellCopyFilter(QObject):
    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.matches(QKeySequence.StandardKey.Copy):
            if _copy_selection_as_tsv(self._table):
                return True
        return super().eventFilter(obj, event)


def _copy_selection_as_tsv(table: QTableWidget) -> bool:
    ranges = table.selectedRanges()
    if not ranges:
        return False
    top = min(r.topRow() for r in ranges)
    bottom = max(r.bottomRow() for r in ranges)
    left = min(r.leftColumn() for r in ranges)
    right = max(r.rightColumn() for r in ranges)
    lines = []
    for row in range(top, bottom + 1):
        cells = []
        for col in range(left, right + 1):
            item = table.item(row, col)
            cells.append(item.text() if item is not None else "")
        lines.append("\t".join(cells))
    QApplication.clipboard().setText("\n".join(lines))
    return True


def install_cell_copy(table: QTableWidget) -> None:
    """Give ``table`` Excel-like block copy (Ctrl/Cmd+C → TSV). Idempotent per table."""
    if getattr(table, "_datalab_cell_copy_installed", False):
        return
    table.installEventFilter(_CellCopyFilter(table))
    table._datalab_cell_copy_installed = True
