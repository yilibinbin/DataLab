from __future__ import annotations

from typing import Any

import pytest

from datalab_core.fitting import build_fitting_request
from datalab_core.jobs import JobMode
from datalab_core.recipes import (
    RecipeValidationError,
    build_recipe_fitting_request,
    build_recipe_workspace_patch,
    normalize_recipe,
    recipe_workflow_route,
    resolve_recipe_bindings,
)


def test_fitting_recipe_normalizes_and_routes() -> None:
    recipe = normalize_recipe(_recipe())
    route = recipe_workflow_route("fitting", "fitting.custom")

    assert recipe["family"] == "fitting"
    assert recipe["workflow_mode"] == "fitting.custom"
    assert recipe["configuration"]["fitting"]["model"] == "custom"
    assert route.current_mode == "fitting"
    assert route.config_section == "fitting"
    assert route.job_mode is JobMode.FITTING
    assert route.result_family == "fitting"


def test_fitting_recipe_mapper_resolves_columns_into_workspace_patch() -> None:
    recipe = normalize_recipe(_recipe())

    patch = build_recipe_workspace_patch(
        recipe,
        _apply_request(x_column="Time", y_column="Signal"),
        headers=("Time", "Signal"),
        rows=(("1.0", "2.0"), ("2.0", "4.1"), ("3.0", "5.9")),
        precision_digits=32,
        uncertainty_digits=2,
    )

    assert patch == {
        "current_mode": "fitting",
        "config": {
            "fitting": {
                "model": "custom",
                "expression": "a*x + b",
                "target_column": "Signal",
                "weighted": True,
                "mcmc_refine": False,
                "variables": [{"name": "x", "column": "Time"}],
                "constraints_enabled": False,
                "parameter_rows": [
                    {"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""},
                    {"name": "b", "initial": "0", "fixed": "", "min": "", "max": ""},
                ],
                "parameter_orphans": [],
                "comparison_candidates": "",
                "custom_constants": {
                    "enabled": False,
                    "rows": [],
                    "view": "table",
                    "text": "",
                    "numeric_mode": "uncertainty",
                },
                "implicit": {},
            }
        },
    }


def test_fitting_recipe_request_matches_manual_custom_fitting_request() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(x_column="Time", y_column="Signal")
    headers = ("Time", "Signal")
    rows = (("1.0", "2.0"), ("2.0", "4.1"), ("3.0", "5.9"))

    from_recipe = build_recipe_fitting_request(
        recipe,
        apply_request,
        headers=headers,
        rows=rows,
        precision_digits=40,
        uncertainty_digits=2,
    )
    manual = build_fitting_request(
        model_type="custom",
        headers=headers,
        data_rows=rows,
        variable_map={"x": "Time"},
        target_column="Signal",
        model_expr="a*x + b",
        parameter_config={
            "a": {"initial": "1"},
            "b": {"initial": "0"},
        },
        parameter_names=("a", "b"),
        weighted=True,
        precision_digits=40,
        uncertainty_digits=2,
        request_id="recipe-linear_custom_fit",
    )

    assert from_recipe == manual


def test_fitting_recipe_auto_binds_exact_suggested_columns() -> None:
    recipe = normalize_recipe(_recipe())

    resolution = resolve_recipe_bindings(recipe, data_columns=("Time", "Signal"))

    assert resolution.is_complete
    assert resolution.apply_request is not None
    assert resolution.apply_request["bindings"]["inputs"]["data"] == {
        "x_data": {"kind": "data_column", "column_id": "Time"},
        "y_data": {"kind": "data_column", "column_id": "Signal"},
    }


def test_fitting_recipe_rejects_parameter_rows_that_no_longer_match_expression() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["expression"] = "a*x"

    with pytest.raises(RecipeValidationError, match="extra: b"):
        normalize_recipe(recipe)


def test_fitting_recipe_rejects_missing_inferred_parameter_row() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["parameter_rows"] = [{"name": "a", "initial": "1"}]

    with pytest.raises(RecipeValidationError, match="missing: b"):
        normalize_recipe(recipe)


def test_fitting_recipe_rejects_empty_parameter_initial_value() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["parameter_rows"][0]["initial"] = ""

    with pytest.raises(RecipeValidationError, match="initial is required"):
        normalize_recipe(recipe)


def test_fitting_recipe_rejects_expression_syntax_before_patch() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["expression"] = "a*x +"
    recipe["configuration"]["fitting"]["parameter_rows"] = [{"name": "a", "initial": "1"}]

    with pytest.raises(RecipeValidationError, match="expression is invalid"):
        normalize_recipe(recipe)


def test_fitting_recipe_rejects_constraint_values_when_constraints_disabled() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["parameter_rows"][0]["min"] = "0"

    with pytest.raises(RecipeValidationError, match="constraints_enabled is false"):
        normalize_recipe(recipe)


def test_fitting_recipe_accepts_constraint_values_when_constraints_enabled() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["constraints_enabled"] = True
    recipe["configuration"]["fitting"]["parameter_rows"][0]["min"] = "0"

    normalized = normalize_recipe(recipe)

    assert normalized["configuration"]["fitting"]["constraints_enabled"] is True
    assert normalized["configuration"]["fitting"]["parameter_rows"][0]["min"] == "0"


def test_fitting_recipe_rejects_unsupported_model_until_specific_mapper_exists() -> None:
    recipe = _recipe()
    recipe["configuration"]["fitting"]["model"] = "self_consistent"

    with pytest.raises(RecipeValidationError, match="unsupported fitting model"):
        normalize_recipe(recipe)


def _apply_request(*, x_column: str, y_column: str) -> dict[str, Any]:
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
