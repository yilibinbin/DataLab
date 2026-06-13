from __future__ import annotations

import os

import mpmath as mp
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QWidget  # noqa: E402

from fitting.auto_models import AUTO_MODELS  # noqa: E402


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _select_model(win, model_type: str) -> None:
    if hasattr(win, "mode_combo"):
        mode_index = win.mode_combo.findData("fitting")
        assert mode_index >= 0
        win.mode_combo.setCurrentIndex(mode_index)
    index = win.fit_model_combo.findData(model_type)
    assert index >= 0
    win.fit_model_combo.setCurrentIndex(index)


def test_implicit_controls_exist_and_method_options(window) -> None:
    _select_model(window, "self_consistent")

    assert window.fit_box.property("datalab_view_module") == "app_desktop.views.fitting"
    assert window.fit_model_combo.currentData() == "self_consistent"
    assert window.implicit_variable_edit.text() == "u"
    assert window.implicit_equation_edit.toPlainText() == ""
    assert "a + b*Cos[u] + c*x" in window.implicit_equation_edit.placeholderText()
    assert window.implicit_output_edit.toPlainText() == ""
    assert "u" in window.implicit_output_edit.placeholderText()
    assert window.implicit_initial_edit.text() == "0.3"
    assert window.implicit_tolerance_edit.text() == "1e-30"
    assert window.implicit_max_iterations_spin.value() == 80
    assert {
        window.implicit_method_combo.itemData(index)
        for index in range(window.implicit_method_combo.count())
    } == {"fixed_point", "root"}
    assert not window.implicit_model_widget.isHidden()


def test_fitting_panel_uses_workbench_section_card_for_model_controls(window) -> None:
    assert window.fit_box.objectName() == "fitting_mode_view"
    assert window.fit_box.property("datalab_view_module") == "app_desktop.views.fitting"
    assert window.fit_box.property("datalab_workbench_section_host") is True

    card = window.fit_box.findChild(QFrame, "fitting_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "fitting"
    card_children = card.findChildren(QWidget)
    for widget in (
        window.fit_model_combo,
        window.fit_mcmc_refine,
        window.fit_model_hint,
        window.inverse_power_widget,
        window.pade_widget,
        window.poly_degree_widget,
        window.implicit_model_widget,
    ):
        assert widget.parentWidget() is card or widget.parentWidget() in card_children


def test_implicit_ui_is_formula_first_and_generic(window) -> None:
    _select_model(window, "self_consistent")

    assert not window.implicit_model_widget.isHidden()
    assert hasattr(window, "implicit_equation_edit")
    assert hasattr(window, "implicit_equation_preview_button")
    assert hasattr(window, "implicit_output_edit")
    assert hasattr(window, "implicit_output_preview_button")
    assert window.implicit_equation_edit.minimumHeight() >= 70
    assert window.implicit_output_edit.minimumHeight() >= 70

    assert window.implicit_variable_edit.text() == "u"
    assert window.implicit_equation_edit.toPlainText() == ""
    assert "a + b*Cos[u] + c*x" in window.implicit_equation_edit.placeholderText()
    assert window.implicit_output_edit.toPlainText() == ""
    assert "u" in window.implicit_output_edit.placeholderText()
    assert window.implicit_timeout_spin.value() == 300
    assert not hasattr(window, "quantum_defect_preset_btn") or not window.quantum_defect_preset_btn.isVisible()


def test_default_implicit_config_uses_x_as_variable_not_parameter(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_equation_edit.setPlainText("a + b*Cos[u] + c*x")
    window.implicit_output_edit.setPlainText("u")

    config = window._collect_implicit_config(validate_parameters=False)

    assert config["x_variables"] == ("x",)
    assert config["implicit_variable"] == "u"
    assert config["equation"] == "a + b*Cos[u] + c*x"
    assert config["output_expression"] == "u"
    assert config["timeout_seconds"] == 300
    assert config["parameter_names"] == ("a", "b", "c")
    assert "x" not in config["parameter_names"]
    assert "u" not in config["parameter_names"]


def test_fresh_custom_model_uses_empty_expression_with_placeholder(window) -> None:
    _select_model(window, "custom")

    assert window.fit_expr_edit.toPlainText() == ""
    assert "A*x**(-p) + C" in window.fit_expr_edit.placeholderText()
    assert window.fit_expr_edit.isReadOnly() is False
    assert window.fit_expr_edit.property("datalab_schema_key") == "fitting.custom.expression"
    assert window.fit_expr_edit.property("datalab_schema_required") is True


def test_non_custom_model_preview_is_populated_and_read_only(window) -> None:
    _select_model(window, "polynomial")

    assert window.fit_expr_edit.toPlainText()
    assert "b0" in window.fit_expr_edit.toPlainText()
    assert window.fit_expr_edit.isReadOnly() is True


def test_fitting_and_implicit_controls_have_schema_bindings(window) -> None:
    assert window.fit_model_combo.property("datalab_schema_key") == "fitting.model"
    assert window.fit_model_combo.property("datalab_schema_choices") is True
    assert window.custom_constants_editor.property("datalab_schema_key") == "fitting.custom.constants"
    assert window.custom_params_table.property("datalab_schema_key") == "fitting.custom.parameters"

    _select_model(window, "self_consistent")

    assert window.implicit_equation_edit.property("datalab_schema_key") == "fitting.implicit.equation"
    assert window.implicit_equation_edit.property("datalab_schema_required") is True
    assert window.implicit_equation_preview_button.property("datalab_schema_key") == "fitting.implicit.equation"
    assert window.implicit_output_edit.property("datalab_schema_key") == "fitting.implicit.output_expression"
    assert window.implicit_output_edit.property("datalab_schema_required") is True
    assert window.implicit_output_preview_button.property("datalab_schema_key") == (
        "fitting.implicit.output_expression"
    )
    assert window.implicit_variable_edit.property("datalab_schema_key") == "fitting.implicit.variable"
    assert window.implicit_initial_edit.property("datalab_schema_key") == "fitting.implicit.initial"
    assert window.implicit_tolerance_edit.property("datalab_schema_key") == "fitting.implicit.tolerance"
    assert window.implicit_max_iterations_spin.property("datalab_schema_key") == (
        "fitting.implicit.max_iterations"
    )
    assert window.implicit_method_combo.property("datalab_schema_key") == "fitting.implicit.method"
    assert window.implicit_method_combo.property("datalab_schema_choices") is True
    assert window.implicit_timeout_spin.property("datalab_schema_key") == "fitting.implicit.timeout_seconds"
    assert window.implicit_constants_editor.property("datalab_schema_key") == "fitting.implicit.constants"
    assert window.implicit_params_table.property("datalab_schema_key") == "fitting.implicit.parameters"


def test_implicit_detect_defaults_to_x_when_no_variable_rows(window) -> None:
    _select_model(window, "self_consistent")
    window.variable_rows = []
    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("a + b*x + c*u")
    window.implicit_output_edit.setPlainText("u + d*x")
    window.implicit_params_table.set_rows([])

    window._refresh_implicit_parameter_rows()

    names = [row["name"] for row in window.implicit_params_table.rows()]
    assert names == ["a", "b", "c", "d"]
    assert "x" not in names
    assert "u" not in names


def test_explicit_physical_constants_are_visible_not_builtin(window) -> None:
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("delta")
    window.implicit_equation_edit.setPlainText("d0 + d2/(n-delta)^2 + d4/(n-delta)^4")
    window.implicit_output_edit.setPlainText("En - R*c/(n-delta)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    window._reset_implicit_constants_rows({"R": "10973731.568160", "c": "299792458"})

    config = window._collect_implicit_config(validate_parameters=False)

    assert config["x_variables"] == ("n",)
    assert config["implicit_variable"] == "delta"
    assert config["equation"] == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
    assert config["output_expression"] == "En - R*c/(n-delta)^2"
    assert config["method"] == "fixed_point"
    assert config["initial"] == "0.3"
    assert config["tolerance"] == "1e-30"
    assert config["max_iterations"] == 80
    assert config["parameter_names"] == ("d0", "d2", "d4", "En")
    assert "R" not in config["parameter_names"]
    assert "c" not in config["parameter_names"]
    assert config["constants"] == {"R": "10973731.568160", "c": "299792458"}


def test_builtin_constants_do_not_hide_generic_parameter_names(window) -> None:
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("K + R*x + c*u")
    window.implicit_output_edit.setPlainText("u + K + R + c")
    generic_config = window._collect_implicit_config(validate_parameters=False)
    assert generic_config["parameter_names"] == ("K", "R", "c")
    assert generic_config["constants"] == {}

    window.implicit_equation_edit.setPlainText("d0 + d2/(n-u)^2")
    window.implicit_output_edit.setPlainText("En + R*c/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    physical_config = window._collect_implicit_config(validate_parameters=False)
    assert "R" in physical_config["parameter_names"]
    assert "c" in physical_config["parameter_names"]
    assert physical_config["constants"] == {}


def test_implicit_validation_rejects_blank_expressions_and_bad_variable(window) -> None:
    _select_model(window, "self_consistent")
    window._apply_quantum_defect_preset()

    window.implicit_equation_edit.setPlainText("")
    with pytest.raises(ValueError, match="Implicit equation|隐式方程"):
        window._collect_implicit_config()

    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("")
    with pytest.raises(ValueError, match="Output expression|输出表达式"):
        window._collect_implicit_config()

    window.implicit_output_edit.setPlainText("En")
    window.implicit_variable_edit.setText("bad-name")
    with pytest.raises(ValueError, match="valid identifier|有效标识符"):
        window._collect_implicit_config()


def test_prepare_fit_job_passes_implicit_definition(window) -> None:
    from datalab_core.jobs import JobMode

    _select_model(window, "self_consistent")
    window._apply_quantum_defect_preset()
    window._reset_implicit_param_rows(
        {
            "d0": {"initial": "0.1"},
            "d2": {"initial": "0.0"},
            "d4": {"initial": "0.0"},
            "En": {"initial": "-0.01"},
        }
    )

    dataset = (
        ["A", "B"],
        [(mp.mpf("2"), mp.mpf("0.75")), (mp.mpf("3"), mp.mpf("0.9"))],
        [(None, None), (None, None)],
    )

    job = window._prepare_fit_job(
        dataset,
        generate_latex=False,
        output_path="",
        verbose=False,
        render_plots=False,
    )

    assert job.model_type == "self_consistent"
    assert job.parameter_names == ["d0", "d2", "d4", "En"]
    assert job.model_expr == "En - R*c/(n-delta)^2"
    assert job.implicit_definition is not None
    assert job.implicit_definition.x_variables == ("n",)
    assert job.implicit_definition.implicit_variable == "delta"
    assert job.implicit_definition.parameters == ("d0", "d2", "d4", "En")
    assert job.implicit_definition.constants == {"R": "10973731.568160", "c": "299792458"}
    assert job.implicit_definition.solve_options.method == "fixed_point"
    assert job.core_request is not None
    assert job.core_request.mode is JobMode.FITTING
    assert job.core_request.inputs["model_type"] == "self_consistent"
    assert job.core_request.inputs["model_expr"] == "En - R*c/(n-delta)^2"
    assert job.core_request.inputs["target_column"] == "B"
    assert job.core_request.inputs["target_series"] == ["0.75", "0.9"]
    assert job.core_request.inputs["timeout_seconds"] == "300.0"
    assert job.core_request.inputs["implicit_definition"] == {
        "x_variables": ["n"],
        "implicit_variable": "delta",
        "equation": "d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        "output_expression": "En - R*c/(n-delta)^2",
        "parameters": ["d0", "d2", "d4", "En"],
        "constants": {"R": "10973731.568160", "c": "299792458"},
        "solve_options": {
            "method": "fixed_point",
            "initial": "0",
            "tolerance": "1e-30",
            "max_iterations": 80,
        },
    }


def test_implicit_parameter_table_supplies_initial_values_without_constraints(window) -> None:
    window.show()
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("d0 + d2/(n-u)^2")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    if hasattr(window, "_reset_implicit_constants_rows"):
        window._reset_implicit_constants_rows({})

    assert window.variable_rows[0][0].text() == "n"
    assert window.variable_rows[0][1].text() == "A"
    assert not hasattr(window, "enable_constraints_checkbox")
    assert not window.implicit_constraints_checkbox.isChecked()
    assert hasattr(window, "implicit_params_table")

    window._reset_implicit_param_rows(
        {
            "d0": {"initial": "0.3"},
            "d2": {"initial": "0.0"},
            "En": {"initial": "-0.01214"},
            "K": {"initial": "-0.007"},
        }
    )

    table = window.implicit_params_table
    rows = {
        table.item(row, 0).text(): table.item(row, 1).text()
        for row in range(table.rowCount())
    }
    assert rows == {"d0": "0.3", "d2": "0.0", "En": "-0.01214", "K": "-0.007"}

    dataset = (
        ["A", "B"],
        [(mp.mpf("4"), mp.mpf("-0.0126")), (mp.mpf("5"), mp.mpf("-0.0125"))],
        [(None, None), (None, None)],
    )
    job = window._prepare_fit_job(
        dataset,
        generate_latex=False,
        output_path="",
        verbose=False,
        render_plots=False,
    )

    assert job.parameter_names == ["d0", "d2", "En", "K"]
    assert job.parameter_config == {
        "d0": {"initial": "0.3"},
        "d2": {"initial": "0.0"},
        "En": {"initial": "-0.01214"},
        "K": {"initial": "-0.007"},
    }


def test_implicit_parameter_table_remains_visible_when_constraints_disabled(window) -> None:
    window.show()
    _select_model(window, "self_consistent")

    assert window.implicit_params_table.isVisible()
    window.implicit_constraints_checkbox.setChecked(False)

    assert window.implicit_params_table.isVisible()
    assert window.implicit_param_refresh_btn.isVisible()


def test_implicit_constraints_checkbox_is_above_constants(window) -> None:
    window.show()
    _select_model(window, "self_consistent")

    page_layout = window.workbench_variable_stack.currentWidget().layout()
    sections = [
        page_layout.itemAt(index).widget()
        for index in range(page_layout.count())
        if page_layout.itemAt(index).widget() is not None
    ]
    constraint_section = window.implicit_constraints_checkbox.parentWidget()
    while constraint_section is not None and not constraint_section.property("datalab_variable_section_card"):
        constraint_section = constraint_section.parentWidget()
    constants_section = window.implicit_constants_editor.parentWidget()
    while constants_section is not None and not constants_section.property("datalab_variable_section_card"):
        constants_section = constants_section.parentWidget()

    constraint_index = sections.index(constraint_section) if constraint_section in sections else -1
    constants_index = sections.index(constants_section) if constants_section in sections else -1

    assert constraint_index >= 0
    assert constants_index >= 0
    assert constraint_index < constants_index


def test_implicit_parameter_table_preserves_high_precision_text(window) -> None:
    _select_model(window, "self_consistent")
    precise = "1.23456789012345678901234567890123456789"
    tiny = "1e-120"
    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("a")
    window.implicit_output_edit.setPlainText("u")
    window.implicit_constraints_checkbox.setChecked(True)
    window._reset_implicit_param_rows(
        {
            "a": {"fixed": precise, "min": tiny, "max": "2"},
        }
    )

    assert window._collect_implicit_parameter_config(["a"]) == {
        "a": {"fixed": precise, "min": tiny, "max": "2"}
    }


def test_implicit_constants_table_excludes_constants_from_parameters(window) -> None:
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    window._reset_implicit_constants_rows({"K": "-0.007"})

    config = window._collect_implicit_config(validate_parameters=False)

    assert config["constants"] == {"K": "-0.007"}
    assert config["parameter_names"] == ("d0", "En")
    assert "K" not in config["parameter_names"]


def test_implicit_constants_table_rejects_duplicate_names(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_implicit_constants_rows({})

    window.implicit_constants_editor.set_rows(
        [{"name": "K", "value": "-0.007"}, {"name": "K", "value": "1.0"}]
    )

    with pytest.raises(ValueError, match="Duplicate constant name|常数名称重复"):
        window._collect_implicit_config(validate_parameters=False)


def test_implicit_constants_table_rejects_invalid_numeric_values(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_implicit_constants_rows({"K": "not-a-number"})

    with pytest.raises(ValueError, match="Invalid value for constant K|常数 K 的取值无效"):
        window._collect_implicit_config(validate_parameters=False)


def test_implicit_constants_accept_compact_uncertainty_notation(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_implicit_constants_rows({"K": "1.23(4)"})

    config = window._collect_implicit_config(validate_parameters=False)

    assert config["constants"] == {"K": "1.23(4)"}


def test_implicit_parameter_detection_ignores_custom_parameter_table(window) -> None:
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")

    window.custom_constraints_checkbox.setChecked(True)
    window._reset_custom_param_rows({"A": {"initial": "1.0"}})

    config = window._collect_implicit_config(validate_parameters=False)

    assert config["parameter_names"] == ("d0", "En", "K")
    assert "A" not in config["parameter_names"]

    window._refresh_implicit_parameter_rows()
    table = window.implicit_params_table
    detected = [
        table.item(row, 0).text()
        for row in range(table.rowCount())
        if table.item(row, 0) is not None and table.item(row, 0).text() not in table.orphan_names()
    ]
    assert detected == ["d0", "En", "K"]


def test_implicit_detect_bypasses_invalid_constant_values_and_replaces_stale_rows(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setPlainText("d0 + d2/(n-u)^2")
    window.implicit_output_edit.setPlainText("En - CR/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    window.implicit_constants_editor.setChecked(True)
    window.implicit_constants_editor.set_rows([{"name": "CR", "value": ""}])

    window._refresh_implicit_parameter_rows()
    window.implicit_params_table.add_parameter_row({"name": "manual", "initial": "3"})
    window.implicit_equation_edit.setPlainText("d0")
    window._refresh_implicit_parameter_rows()

    assert window.implicit_params_table.rows() == [
        {"name": "d0", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "En", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "manual", "initial": "3", "fixed": "", "min": "", "max": ""},
    ]


def test_implicit_parameter_detection_marks_workspace_dirty(window) -> None:
    _select_model(window, "self_consistent")
    window.implicit_equation_edit.setPlainText("d0")
    window.implicit_output_edit.setPlainText("En - K/(x-u)^2")
    window._reset_implicit_param_rows({})
    window._workspace_dirty = False

    window._refresh_implicit_parameter_rows()

    assert window._workspace_dirty is True


def test_implicit_persisted_controls_mark_workspace_dirty(window) -> None:
    _select_model(window, "self_consistent")

    for label, setter in (
        ("variable", lambda: window.implicit_variable_edit.setText(window.implicit_variable_edit.text() + "_changed")),
        ("equation", lambda: window.implicit_equation_edit.setPlainText(window.implicit_equation_edit.toPlainText() + " + 0")),
        ("output", lambda: window.implicit_output_edit.setPlainText(window.implicit_output_edit.toPlainText() + " + 0")),
        ("initial", lambda: window.implicit_initial_edit.setText(window.implicit_initial_edit.text() + "1")),
        ("tolerance", lambda: window.implicit_tolerance_edit.setText(window.implicit_tolerance_edit.text() + "1")),
        (
            "method",
            lambda: window.implicit_method_combo.setCurrentIndex(
                (window.implicit_method_combo.currentIndex() + 1) % window.implicit_method_combo.count()
            ),
        ),
        ("max_iterations", lambda: window.implicit_max_iterations_spin.setValue(window.implicit_max_iterations_spin.value() + 1)),
        ("timeout", lambda: window.implicit_timeout_spin.setValue(window.implicit_timeout_spin.value() + 1)),
    ):
        window._workspace_dirty = False
        setter()
        assert window._workspace_dirty is True, label


def test_auto_models_do_not_include_self_consistent() -> None:
    assert "self_consistent" not in {definition.identifier for definition in AUTO_MODELS}
