"""Manual data table must support BOTH add and remove for rows + cols.

Pre-fix the toolbar exposed only ``+ 行`` and ``+ 列``; users could
inflate the table to arbitrary size but had no way to undo. The fix
adds ``- 行`` / ``- 列`` helpers (with a one-row / one-column minimum
so the user always has somewhere to type).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

from app_desktop.panels import (  # noqa: E402
    _add_table_column,
    _add_table_row,
    _remove_table_column,
    _remove_table_row,
)


class _Holder:
    def __init__(self, rows: int = 4, cols: int = 3) -> None:
        self.manual_table = QTableWidget(rows, cols)


@pytest.fixture(scope="module")
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def holder(_app, qtbot):
    return _Holder(rows=4, cols=3)


def test_add_row_increments_row_count(holder):
    before = holder.manual_table.rowCount()
    _add_table_row(holder)
    assert holder.manual_table.rowCount() == before + 1


def test_add_column_increments_column_count(holder):
    before = holder.manual_table.columnCount()
    _add_table_column(holder)
    assert holder.manual_table.columnCount() == before + 1


def test_remove_row_decrements_row_count(holder):
    before = holder.manual_table.rowCount()
    _remove_table_row(holder)
    assert holder.manual_table.rowCount() == before - 1


def test_remove_column_decrements_column_count(holder):
    before = holder.manual_table.columnCount()
    _remove_table_column(holder)
    assert holder.manual_table.columnCount() == before - 1


def test_remove_row_keeps_at_least_one_row(_app):
    """Floor of 1 — the user always needs somewhere to type."""
    h = _Holder(rows=1, cols=3)
    _remove_table_row(h)
    assert h.manual_table.rowCount() == 1


def test_remove_column_keeps_at_least_one_column(_app):
    h = _Holder(rows=4, cols=1)
    _remove_table_column(h)
    assert h.manual_table.columnCount() == 1
