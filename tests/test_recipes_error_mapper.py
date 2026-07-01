from __future__ import annotations

from typing import Any

import pytest

from datalab_core.jobs import JobMode
from datalab_core.recipes import (
    RecipeValidationError,
    build_recipe_uncertainty_request,
    build_recipe_workspace_patch,
    normalize_recipe,
    recipe_workflow_route,
    resolve_recipe_bindings,
)
from datalab_core.uncertainty import build_uncertainty_request


def test_error_recipe_normalizes_and_routes() -> None:
    recipe = normalize_recipe(_recipe())
    route = recipe_workflow_route("error", "error.standard")

    assert recipe["family"] == "error"
    assert recipe["workflow_mode"] == "error.standard"
    assert recipe["configuration"]["error"]["formula"] == "length / time"
    assert recipe["configuration"]["error"]["method"] == "taylor"
    assert recipe["configuration"]["error"]["order"] == 1
    assert route.current_mode == "error"
    assert route.config_section == "error"
    assert route.job_mode is JobMode.UNCERTAINTY
    assert route.result_family == "uncertainty"


def test_error_recipe_mapper_rewrites_role_formula_to_bound_columns() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(length_column="Distance", time_column="Duration")

    patch = build_recipe_workspace_patch(
        recipe,
        apply_request,
        headers=("Distance", "Duration"),
        rows=(("12.0(1)", "2.0(1)"), ("13.0(2)", "2.5(1)")),
        precision_digits=32,
        uncertainty_digits=1,
    )

    assert patch == {
        "current_mode": "error",
        "config": {
            "error": {
                "formula": "Distance / Duration",
                "method": "taylor",
                "order": 1,
                "mc_samples": 5000,
                "mc_seed": "",
                "collect_monte_carlo_distribution": False,
            }
        },
    }


def test_error_recipe_request_matches_manual_uncertainty_configuration() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(length_column="Distance", time_column="Duration")
    headers = ("Distance", "Duration")
    rows = (("12.0(1)", "2.0(1)"), ("13.0(2)", "2.5(1)"))

    from_recipe = build_recipe_uncertainty_request(
        recipe,
        apply_request,
        headers=headers,
        rows=rows,
        precision_digits=40,
        uncertainty_digits=2,
    )
    manual = build_uncertainty_request(
        headers=headers,
        rows=rows,
        formula="Distance / Duration",
        propagation_method="taylor",
        propagation_order=1,
        mc_samples=5000,
        mc_seed=None,
        collect_monte_carlo_distribution=False,
        precision_digits=40,
        uncertainty_digits=2,
        request_id="recipe-speed_from_distance_time",
    )

    assert from_recipe == manual


def test_error_recipe_auto_binds_exact_suggested_columns() -> None:
    recipe = normalize_recipe(_recipe())

    resolution = resolve_recipe_bindings(recipe, data_columns=("Distance", "Duration"))

    assert resolution.is_complete
    assert resolution.apply_request is not None
    assert resolution.apply_request["bindings"]["inputs"]["data"] == {
        "length": {"kind": "data_column", "column_id": "Distance"},
        "time": {"kind": "data_column", "column_id": "Duration"},
    }


def test_error_recipe_rejects_undeclared_formula_symbol() -> None:
    recipe = _recipe()
    recipe["configuration"]["error"]["formula"] = "length / time + offset"

    with pytest.raises(RecipeValidationError, match="offset"):
        normalize_recipe(recipe)


def test_error_recipe_rejects_bound_columns_that_cannot_be_formula_symbols() -> None:
    recipe = normalize_recipe(_recipe())

    with pytest.raises(RecipeValidationError, match="ASCII identifier"):
        build_recipe_workspace_patch(
            recipe,
            _apply_request(length_column="Distance (m)", time_column="Duration"),
            headers=("Distance (m)", "Duration"),
            rows=(("12.0(1)", "2.0(1)"),),
        )


def test_error_recipe_patch_validates_uncertainty_request_before_returning_patch() -> None:
    recipe = normalize_recipe(_recipe())

    with pytest.raises(ValueError, match="at least one row|segments"):
        build_recipe_workspace_patch(
            recipe,
            _apply_request(length_column="Distance", time_column="Duration"),
            headers=("Distance", "Duration"),
            rows=(),
        )


def _apply_request(*, length_column: str, time_column: str) -> dict[str, Any]:
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


def _recipe() -> dict[str, Any]:
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
