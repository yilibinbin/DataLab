from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QTableWidgetItem  # noqa: E402

from app_desktop.parameter_table import ParameterTable  # noqa: E402


@pytest.mark.parametrize("constraints_enabled", [False, True])
def test_parameter_table_detect_preserves_matching_rows_and_marks_orphans(qtbot, constraints_enabled):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_constraints_enabled(constraints_enabled)
    table.set_rows(
        [
            {"name": "B", "initial": "2", "fixed": "3", "min": "1", "max": "4"},
            {"name": "gone", "initial": "9", "fixed": "", "min": "", "max": ""},
            {"name": "A", "initial": "1", "fixed": "", "min": "0", "max": ""},
        ]
    )

    table.set_detected_names(["A", "B", "C"])

    assert table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "0", "max": ""},
        {"name": "B", "initial": "2", "fixed": "3", "min": "1", "max": "4"},
        {"name": "C", "initial": "", "fixed": "", "min": "", "max": ""},
        {"name": "gone", "initial": "9", "fixed": "", "min": "", "max": ""},
    ]
    assert table.compute_rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "0", "max": ""},
        {"name": "B", "initial": "2", "fixed": "3", "min": "1", "max": "4"},
        {"name": "C", "initial": "", "fixed": "", "min": "", "max": ""},
    ]
    assert table.orphan_names() == {"gone"}


def test_parameter_table_detect_preserves_empty_manual_rows(qtbot):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_rows([{"name": "A", "initial": "1"}])
    table.add_parameter_row()
    row_count = table.rowCount()

    table.set_detected_names(["A", "B"])

    assert table.rowCount() == row_count + 1
    assert table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": ""},
    ]
    assert table.compute_rows() == table.rows()
    assert table.orphan_names() == set()
    assert [
        (table.item(table.rowCount() - 1, column).text() if table.item(table.rowCount() - 1, column) else "")
        for column in range(table.columnCount())
    ] == ["", "", "", "", ""]


def test_parameter_table_detect_preserves_multiple_empty_manual_rows(qtbot):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_rows([{"name": "A", "initial": "1"}])
    table.add_parameter_row()
    table.add_parameter_row()

    table.set_detected_names(["A", "B"])

    assert table.rowCount() == 4
    assert table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": ""},
    ]
    assert table.is_row_empty(2)
    assert table.is_row_empty(3)


def test_parameter_table_detect_preserves_unnamed_draft_rows(qtbot):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_rows([{"name": "A", "initial": "1"}])
    table.add_parameter_row({"initial": "1.5"})

    table.set_detected_names(["A", "B"])

    assert table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": ""},
        {"name": "", "initial": "1.5", "fixed": "", "min": "", "max": ""},
    ]
    assert table.compute_rows() == table.rows()
    assert table.orphan_names() == set()


def test_parameter_table_owns_empty_row_detection(qtbot):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.add_parameter_row()

    assert table.is_row_empty(0)
    table.setItem(0, 1, QTableWidgetItem(" 1 "))
    assert not table.is_row_empty(0)
    assert not table.is_row_empty(-1)
    assert not table.is_row_empty(1)


def test_parameter_table_ignores_constraints_when_disabled(qtbot):
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_rows([{"name": "A", "initial": "1", "fixed": "2", "min": "0", "max": "3"}])

    table.set_constraints_enabled(False)
    assert table.parameter_config(validate=True) == {"A": {"initial": "1"}}

    table.set_constraints_enabled(True)
    assert table.parameter_config(validate=True) == {
        "A": {"initial": "1", "fixed": "2", "min": "0", "max": "3"}
    }
