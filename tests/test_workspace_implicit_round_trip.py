from __future__ import annotations

from pathlib import Path


def _set_combo_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_workspace_round_trips_implicit_fit_config(qtbot, tmp_path: Path) -> None:
    from app_desktop.window import ExtrapolationWindow

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source._reset_variable_rows(default_var="x", default_column="A")
    source._add_variable_row(default_var="z", default_column="C")
    source.implicit_variable_edit.setText("u")
    source.implicit_equation_edit.setPlainText("a + b*Cos[u] + c*x + d*z")
    source.implicit_output_edit.setPlainText("u + z")
    source.implicit_initial_edit.setText("0.3")
    source.implicit_tolerance_edit.setText("1e-30")
    source.implicit_max_iterations_spin.setValue(123)
    source.implicit_timeout_spin.setValue(420)
    _set_combo_data(source.implicit_method_combo, "root")
    source._reset_implicit_param_rows(
        [
            {"name": "a", "initial": "0.1"},
            {"name": "b", "initial": "0.2"},
            {"name": "c", "initial": "0.4"},
            {"name": "d", "initial": "0.5"},
            {"name": "old", "initial": "9"},
        ]
    )
    source.implicit_params_table.mark_orphans({"a", "b", "c", "d"})
    source._reset_implicit_constants_rows({"unit": "1"})
    source.implicit_constants_editor.use_text_view(True)
    source.implicit_constants_editor.set_raw_text("unit 1\n")

    path = tmp_path / "implicit.datalab"
    assert source._save_workspace_to_path(path)

    restored = ExtrapolationWindow()
    qtbot.addWidget(restored)
    assert restored._open_workspace_from_path(path)

    assert restored.fit_model_combo.currentData() == "self_consistent"
    assert restored.implicit_variable_edit.text() == "u"
    assert restored.implicit_equation_edit.toPlainText() == "a + b*Cos[u] + c*x + d*z"
    assert restored.implicit_output_edit.toPlainText() == "u + z"
    assert restored.implicit_initial_edit.text() == "0.3"
    assert restored.implicit_tolerance_edit.text() == "1e-30"
    assert restored.implicit_max_iterations_spin.value() == 123
    assert restored.implicit_timeout_spin.value() == 420
    assert restored.implicit_method_combo.currentData() == "root"
    # The workbench constants editor no longer has an enable checkbox; a
    # non-empty editor is active, so its content round-trips and feeds the fit.
    assert restored.implicit_constants_editor.isChecked()
    assert restored.implicit_constants_editor.using_text_view()
    assert restored.implicit_constants_editor.raw_text() == "unit 1\n"
    assert restored.implicit_constants_editor.constants_dict(validate=False) == {"unit": "1"}
    assert restored._collect_implicit_constants() == {"unit": "1"}
    assert restored.implicit_params_table.orphan_names() == {"old"}
    assert {"name": "old", "initial": "9", "fixed": "", "min": "", "max": ""} in restored.implicit_params_table.rows()
    assert {"name": "old", "initial": "9", "fixed": "", "min": "", "max": ""} not in restored.implicit_params_table.compute_rows()
    assert restored._collect_implicit_parameter_config(["a", "b", "c", "d"]) == {
        "a": {"initial": "0.1"},
        "b": {"initial": "0.2"},
        "c": {"initial": "0.4"},
        "d": {"initial": "0.5"},
    }
    assert [(row[0].text(), row[1].text()) for row in restored.variable_rows] == [
        ("x", "A"),
        ("z", "C"),
    ]
