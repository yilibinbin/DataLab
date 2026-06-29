from __future__ import annotations

from typing import Any

from datalab_core import workspace_v2
from datalab_core.recipe_provenance import build_recipe_provenance


def _recipe_provenance() -> dict[str, Any]:
    return build_recipe_provenance(
        recipe_id="weighted_mean_basic",
        recipe_schema_version=1,
        recipe_payload={"schema": "datalab.recipe.v1", "schema_version": 1, "recipe_id": "weighted_mean_basic"},
        apply_request={"bindings": {}},
        generated_config={"statistics": {"mode": "mean"}},
        applied_at="2026-06-28T00:00:00Z",
    )


def _v2_manifest(*, with_provenance: bool) -> dict[str, Any]:
    model: dict[str, Any] = {
        "title": "X",
        "current_mode": "fitting",
        "language": "en",
        "compute": {"data": {}, "constants": {}, "config": {}},
        "result_snapshot": {"present": False},
    }
    if with_provenance:
        model["provenance"] = {"recipe": _recipe_provenance()}
    return {
        "schema": "datalab.workspace.v2",
        "schema_version": 2,
        "app": {"name": "DataLab", "version": "2.0.2"},
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
        "model": model,
    }


def test_workspace_v2_load_preserves_model_provenance() -> None:
    # A v2 manifest carrying model.provenance must round-trip the recipe-provenance
    # audit trail on load, exactly like model.history does. Dropping it loses
    # recipe_id/version/source for any externally-generated or migrated v2 file.
    manifest = _v2_manifest(with_provenance=True)
    workspace_v2.validate_manifest(manifest)

    restored = workspace_v2.to_v1_workspace(manifest)

    assert "provenance" in restored
    assert restored["provenance"]["recipe"]["recipe_id"] == "weighted_mean_basic"


def test_workspace_v2_load_without_provenance_omits_it() -> None:
    manifest = _v2_manifest(with_provenance=False)
    workspace_v2.validate_manifest(manifest)

    restored = workspace_v2.to_v1_workspace(manifest)

    assert "provenance" not in restored
