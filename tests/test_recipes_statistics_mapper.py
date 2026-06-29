from __future__ import annotations

from typing import Any

from datalab_core.recipes import (
    RecipeValidationError,
    build_recipe_statistics_requests,
    build_recipe_workspace_patch,
    normalize_recipe,
    resolve_recipe_bindings,
)
from datalab_core.statistics import build_multi_column_statistics_requests


def test_recipe_statistics_mapper_auto_binds_exact_suggested_columns() -> None:
    recipe = normalize_recipe(_recipe())

    resolution = resolve_recipe_bindings(recipe, data_columns=("Value", "Sigma"))

    assert resolution.is_complete
    assert resolution.diagnostics == ()
    assert resolution.apply_request is not None
    assert resolution.apply_request["bindings"]["inputs"]["data"] == {
        "sigma": {"kind": "data_column", "column_id": "Sigma"},
        "value": {"kind": "data_column", "column_id": "Value"},
    }


def test_recipe_statistics_mapper_reports_missing_bindings_without_patch() -> None:
    recipe = normalize_recipe(_recipe())

    resolution = resolve_recipe_bindings(recipe, data_columns=("Temperature",))

    assert not resolution.is_complete
    assert resolution.apply_request is None
    assert [diagnostic["role"] for diagnostic in resolution.diagnostics] == ["value", "sigma"]
    assert {diagnostic["code"] for diagnostic in resolution.diagnostics} == {"binding_required"}


def test_recipe_statistics_mapper_accepts_explicit_different_column_names() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(value_column="Temperature", sigma_column="Error")

    patch = build_recipe_workspace_patch(
        recipe,
        apply_request,
        headers=("Temperature", "Error"),
        rows=(("1.0", "0.1"), ("2.0", "0.2")),
    )

    assert patch == {
        "current_mode": "statistics",
        "config": {
            "statistics": {
                "mode": "weighted_sigma",
                "sample": True,
                "sigma_column": "Error",
                "value_column": "Temperature",
                "value_columns": ["Temperature"],
                "weighted_variance": True,
            }
        },
    }


def test_recipe_statistics_mapper_validates_bound_columns_before_patch() -> None:
    recipe = normalize_recipe(_recipe())

    try:
        build_recipe_workspace_patch(
            recipe,
            _apply_request(value_column="Temperature", sigma_column="Missing"),
            headers=("Temperature", "Error"),
            rows=(("1.0", "0.1"),),
        )
    except RecipeValidationError as exc:
        assert "unresolved" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected unresolved binding error")


def test_recipe_statistics_mapper_requires_all_declared_columns_before_patch() -> None:
    recipe = normalize_recipe(_recipe())
    recipe["inputs"]["data"]["required_columns"].append(
        {"id": "weight", "suggested_name": "Weight", "role": "weight", "type": "number"}
    )

    try:
        build_recipe_workspace_patch(
            recipe,
            _apply_request(value_column="Value", sigma_column="Sigma"),
            headers=("Value", "Sigma"),
            rows=(("1.0", "0.1"),),
    )
    except RecipeValidationError as exc:
        assert "unresolved: weight" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing required role error")


def test_recipe_workspace_patch_requires_family_validation_before_mutation() -> None:
    recipe = normalize_recipe(_recipe())

    try:
        build_recipe_workspace_patch(
            recipe,
            _apply_request(value_column="Value", sigma_column="Sigma"),
            headers=("Value", "Sigma"),
            rows=(),
        )
    except ValueError as exc:
        assert "at least one value" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected data validation error before patch is returned")


def test_recipe_statistics_mapper_rejects_explicit_duplicate_headers() -> None:
    recipe = normalize_recipe(_recipe())
    resolution = resolve_recipe_bindings(
        recipe,
        data_columns=("Value", "Value", "Sigma"),
        apply_request=_apply_request(value_column="Value", sigma_column="Sigma"),
    )

    assert not resolution.is_complete
    assert resolution.apply_request is None
    assert resolution.diagnostics == (
        {
            "namespace": "data",
            "role": "value",
            "code": "binding_column_ambiguous",
            "message": "Bound column is ambiguous: Value",
            "suggested_name": "Value",
        },
    )


def test_recipe_statistics_requests_match_manual_statistics_configuration() -> None:
    recipe = normalize_recipe(_recipe())
    apply_request = _apply_request(value_column="Temperature", sigma_column="Error")
    headers = ("Temperature", "Error")
    rows = (
        ("1.0", "0.1"),
        ("2.0", "0.2"),
        ("3.0", "0.3"),
    )

    from_recipe = build_recipe_statistics_requests(
        recipe,
        apply_request,
        headers=headers,
        rows=rows,
        precision_digits=50,
        uncertainty_digits=1,
    )
    manual = build_multi_column_statistics_requests(
        headers=headers,
        rows=rows,
        value_columns="Temperature",
        sigma_col="Error",
        stats_mode="weighted_sigma",
        use_sample=True,
        use_weighted_variance=True,
        precision_digits=50,
        uncertainty_digits=1,
        request_id_prefix="recipe-weighted_mean_basic",
    )

    assert from_recipe == manual


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
