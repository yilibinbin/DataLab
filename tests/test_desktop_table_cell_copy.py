"""Excel-like block copy on the input-data + constants tables (Ctrl/Cmd+C → TSV)."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidgetItem, QTableWidgetSelectionRange

from app_desktop.table_copy import _copy_selection_as_tsv
from app_desktop.window import ExtrapolationWindow


def _window(qtbot: Any) -> ExtrapolationWindow:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_input_data_block_copies_as_tsv(qtbot: Any) -> None:
    window = _window(qtbot)
    t = window.manual_table
    t.setRowCount(2)
    t.setColumnCount(3)
    for r in range(2):
        for c in range(3):
            t.setItem(r, c, QTableWidgetItem(f"{r}{c}"))
    t.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)
    assert _copy_selection_as_tsv(t) is True
    # 2x2 block → tab-separated columns, newline-separated rows (Excel-pasteable).
    assert QApplication.clipboard().text() == "00\t01\n10\t11"


def test_constants_table_block_copies_as_tsv(qtbot: Any) -> None:
    window = _window(qtbot)
    ct = window.input_constants_editor.table_view
    ct.setRowCount(2)
    for r in range(2):
        ct.setItem(r, 0, QTableWidgetItem(f"name{r}"))
        ct.setItem(r, 1, QTableWidgetItem(f"{r}.5(1)"))
    ct.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)
    assert _copy_selection_as_tsv(ct) is True
    assert QApplication.clipboard().text() == "name0\t0.5(1)\nname1\t1.5(1)"


def test_copy_without_selection_is_noop(qtbot: Any) -> None:
    window = _window(qtbot)
    t = window.manual_table
    t.clearSelection()
    assert _copy_selection_as_tsv(t) is False
