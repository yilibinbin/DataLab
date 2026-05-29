from __future__ import annotations


def test_parameter_table_add_delete_clear_and_orphan_filter(qtbot):
    from app_desktop.parameter_table import ParameterTable

    table = ParameterTable()
    qtbot.addWidget(table)

    table.add_parameter_row({"name": "a", "initial": "1"})
    table.add_parameter_row({"name": "old", "initial": "2"})
    table.mark_orphans({"a"})
    assert table.compute_rows() == [{"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""}]
    assert table.orphan_names() == {"old"}

    table.clear_empty_rows()
    table.delete_rows([1])
    assert table.orphan_names() == set()
