from __future__ import annotations

from typing import Any

import pytest

from datalab_core.jobs import JobMode
from datalab_core.recipes import (
    RecipeValidationError,
    build_recipe_root_solving_request,
    build_recipe_workspace_patch,
    normalize_recipe,
    recipe_workflow_route,
    resolve_recipe_bindings,
)
from datalab_core.root_solving import build_root_solving_request


def test_root_recipe_normalizes_and_routes() -> None:
    recipe = normalize_recipe(_recipe())
    route = recipe_workflow_route("root_solving", "root.standard")

    assert recipe["family"] == "root_solving"
    assert recipe["workflow_mode"] == "root.standard"
    assert recipe["configuration"]["root_solving"]["equations"] == ["x^2 - target"]
    assert route.current_mode == "root_solving"
    assert route.config_section == "root_solving"
    assert route.job_mode is JobMode.ROOT_SOLVING
    assert route.result_family == "root_solving"


def test_root_recipe_mapper_rewrites_role_equation_to_bound_columns() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(target_column="A")

    patch = build_recipe_workspace_patch(
        recipe,
        apply_request,
        headers=("A",),
        rows=(("4.0(2)",), ("9.0(3)",)),
        precision_digits=32,
        uncertainty_digits=2,
    )

    assert patch == {
        "current_mode": "root_solving",
        "config": {
            "root_solving": {
                "schema": 1,
                "equations": "x^2 - A",
                "mode": "scalar",
                "unknowns": [
                    {
                        "name": "x",
                        "initial": "2",
                        "lower": "",
                        "upper": "",
                        "source": "manual",
                    }
                ],
                "uncertainty_options": {
                    "method": "taylor",
                    "taylor_order": 1,
                    "monte_carlo_samples": 2000,
                    "monte_carlo_seed": "",
                },
            }
        },
    }


def test_root_recipe_request_matches_manual_root_configuration() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(target_column="A")
    headers = ("A",)
    rows = (("4.0(2)",), ("9.0(3)",))

    from_recipe = build_recipe_root_solving_request(
        recipe,
        apply_request,
        headers=headers,
        rows=rows,
        precision_digits=40,
        uncertainty_digits=2,
    )
    manual = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=(
            {
                "name": "x",
                "initial": "2",
                "lower": "",
                "upper": "",
                "source": "manual",
            },
        ),
        data_headers=headers,
        data_rows=rows,
        constants_enabled=False,
        constants_rows=(),
        mode="scalar",
        scan_config={},
        uncertainty_options={
            "method": "taylor",
            "taylor_order": 1,
            "monte_carlo_samples": 2000,
            "monte_carlo_seed": "",
        },
        precision_digits=40,
        uncertainty_digits=2,
        request_id="recipe-root_of_column",
    )

    assert from_recipe == manual


def test_root_recipe_auto_binds_exact_suggested_column() -> None:
    recipe = normalize_recipe(_recipe())

    resolution = resolve_recipe_bindings(recipe, data_columns=("A",))

    assert resolution.is_complete
    assert resolution.apply_request is not None
    assert resolution.apply_request["bindings"]["inputs"]["data"] == {
        "target": {"kind": "data_column", "column_id": "A"}
    }


def test_root_recipe_rejects_undeclared_equation_symbol() -> None:
    recipe = _recipe()
    recipe["configuration"]["root_solving"]["equations"] = ["x^2 - missing"]

    with pytest.raises(RecipeValidationError, match="missing"):
        normalize_recipe(recipe)


def test_root_recipe_rejects_control_char_in_multiline_equation() -> None:
    recipe = _recipe()
    recipe["configuration"]["root_solving"]["equations"] = "x^2\t- target"

    with pytest.raises(RecipeValidationError, match="control characters"):
        normalize_recipe(recipe)


def test_root_recipe_rejects_bound_columns_that_cannot_be_equation_symbols() -> None:
    recipe = normalize_recipe(_recipe())

    with pytest.raises(RecipeValidationError, match="ASCII identifier"):
        build_recipe_workspace_patch(
            recipe,
            _apply_request(target_column="Target value"),
            headers=("Target value",),
            rows=(("4.0(2)",),),
        )


def test_root_recipe_rejects_scan_config_until_workspace_persistence_exists() -> None:
    recipe = _recipe()
    recipe["configuration"]["root_solving"]["scan_config"] = {"enabled": True}

    with pytest.raises(RecipeValidationError, match="scan_config"):
        normalize_recipe(recipe)


def _apply_request(*, target_column: str) -> dict[str, Any]:
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


def _recipe() -> dict[str, Any]:
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
