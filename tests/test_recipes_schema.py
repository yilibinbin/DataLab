from __future__ import annotations

import json
from typing import Any

import pytest

from datalab_core.jobs import JobMode
from datalab_core.recipes import (
    MAX_INPUT_ROLES,
    MAX_NESTING_DEPTH,
    MAX_PLACEHOLDERS,
    MAX_RECIPE_BYTES,
    RecipeValidationError,
    declared_recipe_roles,
    loads_recipe_apply_json,
    loads_recipe_json,
    normalize_recipe,
    normalize_recipe_apply_request,
    recipe_workflow_route,
)


def test_valid_minimal_statistics_recipe_normalizes_and_routes() -> None:
    recipe = normalize_recipe(_recipe())

    assert recipe["schema"] == "datalab.recipe.v1"
    assert recipe["schema_version"] == 1
    assert recipe["family"] == "statistics"
    assert recipe["workflow_mode"] == "statistics.standard"
    assert recipe["configuration"]["statistics"] == {
        "mode": "weighted_sigma",
        "sigma_column": "${inputs.data.sigma}",
        "value_column": "${inputs.data.value}",
    }
    assert recipe["exports"] == {"latex": True, "plots": True, "report_bundle": False}
    assert declared_recipe_roles(recipe)["data"] == {"value", "sigma"}

    route = recipe_workflow_route("statistics", "statistics.standard")
    assert route.current_mode == "statistics"
    assert route.config_section == "statistics"
    assert route.job_mode is JobMode.STATISTICS
    assert route.result_family == "statistics"
    assert route.accepted_binding_namespaces == frozenset({"data"})


def test_recipe_id_accepts_documented_slug_format() -> None:
    payload = _recipe()
    payload["id"] = "weighted-mean-basic"

    recipe = normalize_recipe(payload)
    request = normalize_recipe_apply_request(
        {
            "schema": "datalab.recipe.apply.v1",
            "recipe_id": "weighted-mean-basic",
            "bindings": {
                "inputs": {
                    "data": {
                        "value": {"kind": "data_column", "column_id": "Value"},
                        "sigma": {"kind": "data_column", "column_id": "Sigma"},
                    }
                }
            },
        },
        recipe_id="weighted-mean-basic",
        declared_roles=declared_recipe_roles(recipe),
    )

    assert recipe["id"] == "weighted-mean-basic"
    assert request["recipe_id"] == "weighted-mean-basic"


def test_recipe_json_loader_rejects_duplicate_keys_and_json_floats() -> None:
    duplicate = '{"schema":"datalab.recipe.v1","schema":"datalab.recipe.v1"}'
    with pytest.raises(RecipeValidationError, match="duplicate JSON key"):
        loads_recipe_json(duplicate)

    payload = _recipe()
    payload["configuration"]["statistics"]["threshold"] = 1.2
    text = json.dumps(payload)
    with pytest.raises(RecipeValidationError, match="JSON floats"):
        loads_recipe_json(text)

    with pytest.raises(RecipeValidationError, match="non-finite"):
        loads_recipe_json('{"schema":"datalab.recipe.v1","id":NaN}')

    with pytest.raises(RecipeValidationError, match="byte limit"):
        loads_recipe_json(" " * (MAX_RECIPE_BYTES + 1))

    with pytest.raises(RecipeValidationError, match="nesting depth"):
        loads_recipe_json("[" * (MAX_NESTING_DEPTH + 1) + "0" + "]" * (MAX_NESTING_DEPTH + 1))

    with pytest.raises(RecipeValidationError, match="integer is too long"):
        loads_recipe_json('{"schema":"datalab.recipe.v1","id":' + "1" * 10000 + "}")


def test_recipe_rejects_yaml_unknown_keys_urls_and_traversal() -> None:
    with pytest.raises(RecipeValidationError, match="valid JSON"):
        loads_recipe_json("schema: datalab.recipe.v1\nid: weighted\n")

    payload = _recipe()
    payload["run"] = "print('unsafe')"
    with pytest.raises(RecipeValidationError, match="unsupported field"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["examples"] = [{"workspace": "https://example.test/statistics.datalab"}]
    with pytest.raises(RecipeValidationError, match="URL"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["examples"] = [{"workspace": "../statistics.datalab"}]
    with pytest.raises(RecipeValidationError, match="path traversal"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["examples"] = [{"workspace": "C:/Users/me/statistics.datalab"}]
    with pytest.raises(RecipeValidationError, match="absolute path"):
        normalize_recipe(payload)


def test_recipe_rejects_bad_placeholders_and_undeclared_roles() -> None:
    payload = _recipe()
    payload["configuration"]["statistics"]["value_column"] = "prefix-${inputs.data.value}"
    with pytest.raises(RecipeValidationError, match="whole-field"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["configuration"]["statistics"]["value_column"] = "${inputs.data.value.name}"
    with pytest.raises(RecipeValidationError, match="whole-field"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["configuration"]["statistics"]["value_column"] = "${inputs.data.missing}"
    with pytest.raises(RecipeValidationError, match="undeclared"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["title"]["en"] = "${inputs.data.value}"
    with pytest.raises(RecipeValidationError, match="must not contain recipe placeholders"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["inputs"]["constants"] = [{"id": "c"}]
    payload["configuration"]["statistics"]["value_column"] = "${inputs.constants.c}"
    with pytest.raises(RecipeValidationError, match="does not accept inputs.constants"):
        normalize_recipe(payload)


def test_recipe_rejects_duplicate_role_ids_and_excessive_roles() -> None:
    payload = _recipe()
    payload["inputs"]["data"]["required_columns"].append(
        {"id": "value", "suggested_name": "Other", "role": "value", "type": "number"}
    )
    with pytest.raises(RecipeValidationError, match="duplicate role id"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["inputs"]["data"]["required_columns"] = [
        {"id": f"col_{index}", "suggested_name": f"C{index}", "role": "value", "type": "number"}
        for index in range(MAX_INPUT_ROLES + 1)
    ]
    with pytest.raises(RecipeValidationError, match="too many roles|role limit"):
        normalize_recipe(payload)


def test_recipe_enforces_resource_limits() -> None:
    payload = _recipe()
    current = payload
    for index in range(MAX_NESTING_DEPTH + 2):
        current["configuration"] = {"statistics": {"value_column": "${inputs.data.value}", "mode": "mean"}}
        current["extra" if index == 0 else f"extra_{index}"] = {}
        current = current["extra" if index == 0 else f"extra_{index}"]
    with pytest.raises(RecipeValidationError, match="nesting|unsupported field"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["configuration"]["statistics"]["value_column"] = "${inputs.data.value}"
    payload["description"]["en"] = " ".join("${inputs.data.value}" for _ in range(MAX_PLACEHOLDERS + 1))
    with pytest.raises(RecipeValidationError, match="placeholder limit"):
        normalize_recipe(payload)


def test_recipe_programmatic_mapping_checks_depth_before_recursive_float_scan() -> None:
    payload: dict[str, object] = {}
    current = payload
    for index in range(MAX_NESTING_DEPTH + 2):
        child: dict[str, object] = {}
        current[f"child_{index}"] = child
        current = child
    current["value"] = 1.2

    with pytest.raises(RecipeValidationError, match="nesting depth"):
        normalize_recipe(payload)


def test_recipe_programmatic_validation_does_not_execute_object_hooks() -> None:
    class HostileScalar:
        def __deepcopy__(self, _memo: object) -> object:  # pragma: no cover - must not run
            raise AssertionError("validator executed object hook")

    payload = _recipe()
    payload["description"]["en"] = HostileScalar()

    with pytest.raises(RecipeValidationError, match="unsupported JSON value type"):
        normalize_recipe(payload)


def test_recipe_apply_request_normalizes_bindings_and_rejects_mismatches() -> None:
    recipe = normalize_recipe(_recipe())
    declared = declared_recipe_roles(recipe)
    request = normalize_recipe_apply_request(
        {
            "schema": "datalab.recipe.apply.v1",
            "recipe_id": "weighted_mean_basic",
            "bindings": {
                "inputs": {
                    "data": {
                        "value": {"kind": "data_column", "column_id": "Temperature"},
                        "sigma": {"kind": "data_column", "column_id": "Sigma"},
                    }
                }
            },
        },
        recipe_id="weighted_mean_basic",
        declared_roles=declared,
    )

    assert request["schema_version"] == 1
    assert request["bindings"]["inputs"]["data"]["value"] == {
        "kind": "data_column",
        "column_id": "Temperature",
    }

    bad_role = {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "weighted_mean_basic",
        "bindings": {"inputs": {"data": {"missing": {"kind": "data_column", "column_id": "A"}}}},
    }
    with pytest.raises(RecipeValidationError, match="undeclared"):
        normalize_recipe_apply_request(bad_role, declared_roles=declared)

    with pytest.raises(RecipeValidationError, match="does not match"):
        normalize_recipe_apply_request(
            {**bad_role, "recipe_id": "other_recipe"},
            recipe_id="weighted_mean_basic",
            declared_roles=declared,
        )


def test_recipe_apply_json_rejects_duplicate_bindings_and_unsafe_column_ids() -> None:
    with pytest.raises(RecipeValidationError, match="duplicate JSON key"):
        loads_recipe_apply_json(
            """
            {
              "schema": "datalab.recipe.apply.v1",
              "recipe_id": "weighted_mean_basic",
              "bindings": {"inputs": {"data": {
                "value": {"kind": "data_column", "column_id": "A"},
                "value": {"kind": "data_column", "column_id": "B"}
              }}}
            }
            """
        )

    declared = {"data": {"value"}}
    with pytest.raises(RecipeValidationError, match="URL"):
        normalize_recipe_apply_request(
            {
                "schema": "datalab.recipe.apply.v1",
                "recipe_id": "weighted_mean_basic",
                "bindings": {
                    "inputs": {
                        "data": {
                            "value": {"kind": "data_column", "column_id": "https://example.test/A"}
                        }
                    }
                },
            },
            declared_roles=declared,
        )

    with pytest.raises(RecipeValidationError, match="absolute path"):
        normalize_recipe_apply_request(
            {
                "schema": "datalab.recipe.apply.v1",
                "recipe_id": "weighted_mean_basic",
                "bindings": {
                    "inputs": {
                        "data": {
                            "value": {"kind": "data_column", "column_id": "/tmp/A"}
                        }
                    }
                },
            },
            declared_roles=declared,
        )

    with pytest.raises(RecipeValidationError, match="path traversal"):
        normalize_recipe_apply_request(
            {
                "schema": "datalab.recipe.apply.v1",
                "recipe_id": "weighted_mean_basic",
                "bindings": {
                    "inputs": {
                        "data": {
                            "value": {"kind": "data_column", "column_id": r"..\\..\\A"}
                        }
                    }
                },
            },
            declared_roles=declared,
        )


def test_recipe_rejects_unsupported_workflow_and_configuration_keys() -> None:
    payload = _recipe()
    payload["workflow_mode"] = "statistics.bootstrap"
    with pytest.raises(RecipeValidationError, match="unsupported recipe workflow"):
        normalize_recipe(payload)

    payload = _recipe()
    payload["configuration"]["statistics"]["unknown"] = "value"
    with pytest.raises(RecipeValidationError, match="unsupported field"):
        normalize_recipe(payload)


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
