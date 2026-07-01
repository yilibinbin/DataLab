from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app_desktop.recipe_preview import (
    _apply_recipe_patch_to_window,
    apply_recipe_to_window,
    build_recipe_preview,
)
from app_desktop.window import ExtrapolationWindow
from datalab_core.recipes import RecipeValidationError


def test_recipe_preview_auto_binds_and_reports_missing_columns() -> None:
    recipe = _recipe()

    complete = build_recipe_preview(recipe, data_columns=("Value", "Sigma"), lang="zh")
    missing = build_recipe_preview(recipe, data_columns=("Temperature",), lang="en")

    assert complete.title == "加权平均"
    assert complete.apply_request is not None
    assert [item.bound_column for item in complete.required_inputs] == ["Value", "Sigma"]
    assert complete.diagnostics == ()
    assert missing.apply_request is None
    assert [diagnostic["role"] for diagnostic in missing.diagnostics] == ["value", "sigma"]


def test_apply_recipe_to_window_updates_statistics_controls_and_preserves_identity(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    original_path = Path("/tmp/original.datalab")
    template_source = Path("/tmp/template.datalab")
    window._workspace_path = original_path
    window._workspace_template_source = template_source
    window._workspace_dirty = False
    window._data_stack.setCurrentIndex(1)
    window.manual_data_edit.setPlainText("Temperature Error\n1.0 0.1\n2.0 0.2\n")

    patch = apply_recipe_to_window(
        window,
        _recipe(),
        apply_request=_apply_request(value_column="Temperature", sigma_column="Error"),
    )

    assert patch["current_mode"] == "statistics"
    assert window.mode_combo.currentData() == "statistics"
    assert window.stats_value_column_edit.text() == "Temperature"
    assert window.stats_sigma_column_edit.text() == "Error"
    assert window.stats_mode_combo.currentData() == "weighted_sigma"
    assert window._workspace_path == original_path
    assert window._workspace_template_source == template_source
    assert window._workspace_dirty is True
    provenance = window._workspace_provenance["recipe"]
    assert provenance["recipe_id"] == "weighted_mean_basic"
    assert provenance["user_modified"] is False

    window.stats_value_column_edit.setText("Other")
    assert window._workspace_provenance["recipe"]["user_modified"] is True


def test_apply_error_recipe_to_window_updates_error_controls_and_preserves_identity(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    original_path = Path("/tmp/original-error.datalab")
    template_source = Path("/tmp/template-error.datalab")
    window._workspace_path = original_path
    window._workspace_template_source = template_source
    window._workspace_dirty = False
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "C", "value": "9"}])

    patch = apply_recipe_to_window(
        window,
        _error_recipe(),
        apply_request=_error_apply_request(length_column="Distance", time_column="Duration"),
        data_columns=("Distance", "Duration"),
        rows=(("12.0(1)", "2.0(1)"), ("13.0(2)", "2.5(1)")),
        precision_digits=32,
        uncertainty_digits=1,
    )

    assert patch["current_mode"] == "error"
    assert window.mode_combo.currentData() == "error"
    assert window.formula_edit.toPlainText() == "Distance / Duration"
    assert window.error_method_combo.currentData() == "taylor"
    assert window.error_order_spin.value() == 1
    assert window.error_mc_samples_spin.value() == 5000
    assert window.error_mc_seed_edit.text() == ""
    assert window._workspace_path == original_path
    assert window._workspace_template_source == template_source
    assert window._workspace_dirty is True
    provenance = window._workspace_provenance["recipe"]
    assert provenance["recipe_id"] == "speed_from_distance_time"
    assert provenance["user_modified"] is False


def test_apply_root_recipe_to_window_updates_root_controls_and_preserves_identity(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    original_path = Path("/tmp/original-root.datalab")
    template_source = Path("/tmp/template-root.datalab")
    window._workspace_path = original_path
    window._workspace_template_source = template_source
    window._workspace_dirty = False

    patch = apply_recipe_to_window(
        window,
        _root_recipe(),
        apply_request=_root_apply_request(target_column="A"),
        data_columns=("A",),
        rows=(("4.0(2)",), ("9.0(3)",)),
        precision_digits=32,
        uncertainty_digits=2,
    )

    assert patch["current_mode"] == "root_solving"
    assert window.mode_combo.currentData() == "root_solving"
    assert window.root_equations_edit.toPlainText() == "x^2 - A"
    assert window.root_mode_combo.currentData() == "scalar"
    assert window.root_unknowns_table.rows() == [{"name": "x", "initial": "2", "lower": "", "upper": ""}]
    assert window.root_uncertainty_method_combo.currentData() == "taylor"
    assert window.root_uncertainty_order_spin.value() == 1
    assert window.root_monte_carlo_samples_spin.value() == 2000
    assert window.root_monte_carlo_seed_edit.text() == ""
    assert window._workspace_path == original_path
    assert window._workspace_template_source == template_source
    assert window._workspace_dirty is True
    provenance = window._workspace_provenance["recipe"]
    assert provenance["recipe_id"] == "root_of_column"
    assert provenance["user_modified"] is False


def test_apply_fitting_recipe_to_window_updates_custom_fit_controls_and_preserves_identity(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    original_path = Path("/tmp/original-fit.datalab")
    template_source = Path("/tmp/template-fit.datalab")
    window._workspace_path = original_path
    window._workspace_template_source = template_source
    window._workspace_dirty = False

    patch = apply_recipe_to_window(
        window,
        _fitting_recipe(),
        apply_request=_fitting_apply_request(x_column="Time", y_column="Signal"),
        data_columns=("Time", "Signal"),
        rows=(("1.0", "2.0"), ("2.0", "4.1"), ("3.0", "5.9")),
        precision_digits=32,
        uncertainty_digits=2,
    )

    assert patch["current_mode"] == "fitting"
    assert window.mode_combo.currentData() == "fitting"
    assert window.fit_model_combo.currentData() == "custom"
    assert window.fit_expr_edit.toPlainText() == "a*x + b"
    assert window.fit_target_edit.text() == "Signal"
    assert window.fit_weighted_checkbox.isChecked() is True
    assert window.fit_mcmc_refine.isChecked() is False
    assert [(var.text(), col.text()) for var, col, _ in window.variable_rows] == [("x", "Time")]
    assert window.custom_constraints_checkbox.isChecked() is False
    assert window.custom_params_table.rows() == [
        {"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "b", "initial": "0", "fixed": "", "min": "", "max": ""},
    ]
    assert window.custom_constants_editor.isChecked() is False
    assert window.custom_constants_editor.rows() == []
    assert window._workspace_path == original_path
    assert window._workspace_template_source == template_source
    assert window._workspace_dirty is True
    provenance = window._workspace_provenance["recipe"]
    assert provenance["recipe_id"] == "linear_custom_fit"
    assert provenance["user_modified"] is False


def test_apply_recipe_to_window_validates_before_mutating_controls(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window._data_stack.setCurrentIndex(1)
    window.manual_data_edit.setPlainText("Temperature Error\n")
    window._workspace_dirty = False
    before_mode = window.mode_combo.currentData()
    before_value_column = window.stats_value_column_edit.text()

    with pytest.raises(ValueError, match="header and at least one data row"):
        apply_recipe_to_window(
            window,
            _recipe(),
            apply_request=_apply_request(value_column="Temperature", sigma_column="Error"),
        )

    assert window.mode_combo.currentData() == before_mode
    assert window.stats_value_column_edit.text() == before_value_column
    assert window._workspace_dirty is False


def test_apply_recipe_to_window_rejects_partial_explicit_dataset(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    with pytest.raises(RecipeValidationError, match="provided together"):
        apply_recipe_to_window(window, _recipe(), data_columns=("Value", "Sigma"))


def test_recipe_patch_application_validates_patch_before_mode_mutation(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    before_mode = window.mode_combo.currentData()

    with pytest.raises(RecipeValidationError, match="statistics config is invalid"):
        _apply_recipe_patch_to_window(window, {"current_mode": "statistics", "config": {"statistics": None}})

    assert window.mode_combo.currentData() == before_mode


def test_error_recipe_patch_application_validates_patch_before_mode_mutation(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    before_mode = window.mode_combo.currentData()

    with pytest.raises(RecipeValidationError, match="error config is invalid"):
        _apply_recipe_patch_to_window(window, {"current_mode": "error", "config": {"error": None}})

    assert window.mode_combo.currentData() == before_mode


def test_root_recipe_patch_application_validates_patch_before_mode_mutation(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    before_mode = window.mode_combo.currentData()

    with pytest.raises(RecipeValidationError, match="root_solving config is invalid"):
        _apply_recipe_patch_to_window(window, {"current_mode": "root_solving", "config": {"root_solving": None}})

    assert window.mode_combo.currentData() == before_mode


def test_fitting_recipe_patch_application_validates_patch_before_mode_mutation(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    before_mode = window.mode_combo.currentData()

    with pytest.raises(RecipeValidationError, match="fitting config is invalid"):
        _apply_recipe_patch_to_window(window, {"current_mode": "fitting", "config": {"fitting": None}})

    assert window.mode_combo.currentData() == before_mode


def _apply_request(*, value_column: str, sigma_column: str) -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "weighted_mean_basic",
        "bindings": {
            "inputs": {
                "data": {
                    "value": {"kind": "data_column", "column_id": value_column},
                    "sigma": {"kind": "data_column", "column_id": sigma_column},
                }
            }
        },
    }


def _error_apply_request(*, length_column: str, time_column: str) -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "speed_from_distance_time",
        "bindings": {
            "inputs": {
                "data": {
                    "length": {"kind": "data_column", "column_id": length_column},
                    "time": {"kind": "data_column", "column_id": time_column},
                }
            }
        },
    }


def _root_apply_request(*, target_column: str) -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "root_of_column",
        "bindings": {
            "inputs": {
                "data": {
                    "target": {"kind": "data_column", "column_id": target_column},
                }
            }
        },
    }


def _fitting_apply_request(*, x_column: str, y_column: str) -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "linear_custom_fit",
        "bindings": {
            "inputs": {
                "data": {
                    "x_data": {"kind": "data_column", "column_id": x_column},
                    "y_data": {"kind": "data_column", "column_id": y_column},
                }
            }
        },
    }


def _recipe() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.v1",
        "id": "weighted_mean_basic",
        "title": {"en": "Weighted mean", "zh": "加权平均"},
        "description": {"en": "Compute a weighted mean from values and sigma."},
        "family": "statistics",
        "workflow_mode": "statistics.standard",
        "inputs": {
            "data": {
                "required_columns": [
                    {
                        "id": "value",
                        "suggested_name": "Value",
                        "role": "value",
                        "type": "number_with_uncertainty",
                    },
                    {
                        "id": "sigma",
                        "suggested_name": "Sigma",
                        "role": "sigma",
                        "type": "number",
                    },
                ]
            },
            "constants": [],
        },
        "configuration": {
            "statistics": {
                "value_column": "${inputs.data.value}",
                "sigma_column": "${inputs.data.sigma}",
                "mode": "weighted_sigma",
            }
        },
        "exports": {"latex": True, "plots": True, "report_bundle": False},
        "examples": [{"workspace": "statistics.datalab"}],
    }


def _error_recipe() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.v1",
        "id": "speed_from_distance_time",
        "title": {"en": "Speed from distance and time", "zh": "距离和时间求速度"},
        "description": {"en": "Propagate uncertainty for speed = distance / time."},
        "family": "error",
        "workflow_mode": "error.standard",
        "inputs": {
            "data": {
                "required_columns": [
                    {
                        "id": "length",
                        "suggested_name": "Distance",
                        "role": "value",
                        "type": "number_with_uncertainty",
                    },
                    {
                        "id": "time",
                        "suggested_name": "Duration",
                        "role": "value",
                        "type": "number_with_uncertainty",
                    },
                ]
            },
            "constants": [],
        },
        "configuration": {
            "error": {
                "formula": "length / time",
                "method": "taylor",
                "order": 1,
            }
        },
        "exports": {"latex": True, "plots": True, "report_bundle": False},
        "examples": [{"workspace": "error-propagation.datalab"}],
    }


def _root_recipe() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.v1",
        "id": "root_of_column",
        "title": {"en": "Root of a data column", "zh": "数据列求根"},
        "description": {"en": "Solve x^2 - A = 0 for each row of A."},
        "family": "root_solving",
        "workflow_mode": "root.standard",
        "inputs": {
            "data": {
                "required_columns": [
                    {
                        "id": "target",
                        "suggested_name": "A",
                        "role": "value",
                        "type": "number_with_uncertainty",
                    }
                ]
            },
            "constants": [],
        },
        "configuration": {
            "root_solving": {
                "equations": ["x^2 - target"],
                "mode": "scalar",
                "unknowns": [{"name": "x", "initial": "2"}],
                "uncertainty_options": {"method": "taylor", "taylor_order": 1},
            }
        },
        "exports": {"latex": True, "plots": True, "report_bundle": False},
        "examples": [{"workspace": "root-solving.datalab"}],
    }


def _fitting_recipe() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.v1",
        "id": "linear_custom_fit",
        "title": {"en": "Linear custom fit", "zh": "线性自定义拟合"},
        "description": {"en": "Fit y = a*x + b using the custom fitting model."},
        "family": "fitting",
        "workflow_mode": "fitting.custom",
        "inputs": {
            "data": {
                "required_columns": [
                    {
                        "id": "x_data",
                        "suggested_name": "Time",
                        "role": "x",
                        "type": "number",
                    },
                    {
                        "id": "y_data",
                        "suggested_name": "Signal",
                        "role": "y",
                        "type": "number_with_uncertainty",
                    },
                ]
            },
            "constants": [],
        },
        "configuration": {
            "fitting": {
                "model": "custom",
                "expression": "a*x + b",
                "variables": [{"name": "x", "column": "${inputs.data.x_data}"}],
                "target_column": "${inputs.data.y_data}",
                "weighted": True,
                "constraints_enabled": False,
                "parameter_rows": [
                    {"name": "a", "initial": "1"},
                    {"name": "b", "initial": "0"},
                ],
            }
        },
        "exports": {"latex": True, "plots": True, "report_bundle": False},
        "examples": [{"workspace": "fitting-custom.datalab"}],
    }
