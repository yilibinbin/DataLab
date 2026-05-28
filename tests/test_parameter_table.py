from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from app_desktop.parameter_table import ParameterTable


@pytest.mark.parametrize("constraints_enabled", [False, True])
def test_parameter_table_detect_preserves_matching_rows_and_drops_orphans(qtbot, constraints_enabled):
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
    ]


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
