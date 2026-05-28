from __future__ import annotations

import os

import mpmath as mp
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fitting.auto_models import AUTO_MODELS  # noqa: E402


@pytest.fixture
def window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _select_model(win, model_type: str) -> None:
    index = win.fit_model_combo.findData(model_type)
    assert index >= 0
    win.fit_model_combo.setCurrentIndex(index)


def test_implicit_controls_exist_and_method_options(window) -> None:
    _select_model(window, "self_consistent")

    assert window.fit_model_combo.currentData() == "self_consistent"
    assert window.implicit_variable_edit.text() == "u"
    assert window.implicit_equation_edit.text() == "a + b*Cos[u] + c*x"
    assert window.implicit_output_edit.text() == "u"
    assert window.implicit_initial_edit.text() == "0.3"
    assert window.implicit_tolerance_edit.text() == "1e-30"
    assert window.implicit_max_iterations_spin.value() == 80
    assert {
        window.implicit_method_combo.itemData(index)
        for index in range(window.implicit_method_combo.count())
    } == {"fixed_point", "root"}
    assert not window.implicit_model_widget.isHidden()


def test_default_implicit_config_uses_x_as_variable_not_parameter(window) -> None:
    _select_model(window, "self_consistent")

    config = window._collect_implicit_config()

    assert config["x_variables"] == ("x",)
    assert config["implicit_variable"] == "u"
    assert config["equation"] == "a + b*Cos[u] + c*x"
    assert config["output_expression"] == "u"
    assert config["parameter_names"] == ("a", "b", "c")
    assert "x" not in config["parameter_names"]
    assert "u" not in config["parameter_names"]


def test_quantum_defect_preset_and_parameter_inference(window) -> None:
    _select_model(window, "self_consistent")
    window._apply_quantum_defect_preset()

    config = window._collect_implicit_config()

    assert config["x_variables"] == ("n",)
    assert config["implicit_variable"] == "delta"
    assert config["equation"] == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
    assert config["output_expression"] == "En - R*c/(n-delta)^2"
    assert config["method"] == "fixed_point"
    assert config["initial"] == "0"
    assert config["tolerance"] == "1e-30"
    assert config["max_iterations"] == 80
    assert config["parameter_names"] == ("d0", "d2", "d4", "En")
    assert "R" not in config["parameter_names"]
    assert "c" not in config["parameter_names"]
    assert config["constants"] == {"R": "10973731.568160", "c": "299792458"}


def test_builtin_constants_do_not_hide_generic_parameter_names(window) -> None:
    _select_model(window, "self_consistent")

    window.implicit_variable_edit.setText("u")
    window.implicit_equation_edit.setText("K + R*x + c*u")
    window.implicit_output_edit.setText("u + K + R + c")
    generic_config = window._collect_implicit_config()
    assert generic_config["parameter_names"] == ("K", "R", "c")
    assert generic_config["constants"] == {}

    window.implicit_equation_edit.setText("d0 + d2/(n-u)^2")
    window.implicit_output_edit.setText("En + R*c/(n-u)^2")
    window._reset_variable_rows(default_var="n", default_column="A")
    physical_config = window._collect_implicit_config()
    assert "R" in physical_config["parameter_names"]
    assert "c" in physical_config["parameter_names"]
    assert physical_config["constants"] == {}


def test_implicit_validation_rejects_blank_expressions_and_bad_variable(window) -> None:
    _select_model(window, "self_consistent")
    window._apply_quantum_defect_preset()

    window.implicit_equation_edit.setText("")
    with pytest.raises(ValueError, match="Implicit equation|隐式方程"):
        window._collect_implicit_config()

    window.implicit_equation_edit.setText("d0")
    window.implicit_output_edit.setText("")
    with pytest.raises(ValueError, match="Output expression|输出表达式"):
        window._collect_implicit_config()

    window.implicit_output_edit.setText("En")
    window.implicit_variable_edit.setText("bad-name")
    with pytest.raises(ValueError, match="valid identifier|有效标识符"):
        window._collect_implicit_config()


def test_prepare_fit_job_passes_implicit_definition(window) -> None:
    _select_model(window, "self_consistent")
    window._apply_quantum_defect_preset()

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


def test_auto_models_do_not_include_self_consistent() -> None:
    assert "self_consistent" not in {definition.identifier for definition in AUTO_MODELS}
