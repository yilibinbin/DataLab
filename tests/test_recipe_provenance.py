from __future__ import annotations

from typing import Any

import pytest

from datalab_core.history import HistoryEntry, HistoryStore, HistoryValidationError, history_entry_from_json
from datalab_core.recipe_provenance import (
    RecipeProvenanceError,
    build_recipe_provenance,
    normalize_workspace_provenance,
)
from datalab_core.report_bundle import (
    ReportBundleValidationError,
    build_report_bundle_manifest,
    read_report_bundle,
    validate_report_manifest,
    write_report_bundle,
)
from datalab_core.workbench_model import WorkbenchModel
from shared.workspace_schema import compute_workspace_hash


def test_recipe_provenance_builds_and_rejects_float_and_object_hooks() -> None:
    provenance = _recipe_provenance()

    assert provenance["schema"] == "datalab.recipe_provenance.v1"
    assert provenance["recipe_id"] == "weighted_mean_basic"
    assert provenance["binding_summary"]["inputs"]["data"]["value"]["column_id"] == "Value"

    with pytest.raises(RecipeProvenanceError, match="JSON floats"):
        normalize_workspace_provenance({"recipe": {**provenance, "user_modified": 1.2}})

    class Hostile:
        def __deepcopy__(self, _memo: object) -> object:  # pragma: no cover - must not run
            raise AssertionError("object hook executed")

    with pytest.raises(RecipeProvenanceError, match="unsupported JSON value type"):
        normalize_workspace_provenance({"recipe": {**provenance, "source_label": Hostile()}})

    with pytest.raises(RecipeProvenanceError, match="unsupported fields"):
        normalize_workspace_provenance({"recipe": provenance, "typo": {}})


def test_workbench_model_round_trips_recipe_provenance_without_hashing_it() -> None:
    workspace = _workspace()
    baseline_hash = compute_workspace_hash(workspace)
    workspace["provenance"] = {"recipe": _recipe_provenance()}

    model = WorkbenchModel.from_v1_workspace(workspace)
    restored = model.to_v1_workspace()

    assert restored["provenance"]["recipe"]["recipe_id"] == "weighted_mean_basic"
    assert model.compute_hash() == baseline_hash


def test_history_keeps_recipe_provenance_out_of_semantic_hash_but_in_dedup_identity() -> None:
    baseline = _history_entry("e01")
    with_recipe = _history_entry("e02", provenance={"recipe": _recipe_provenance(source_label="recipe-a")})
    with_other_recipe = _history_entry("e03", provenance={"recipe": _recipe_provenance(source_label="recipe-b")})

    assert baseline.semantic_hash == with_recipe.semantic_hash
    store = HistoryStore(entries=(with_recipe, with_other_recipe)).deduplicated()

    assert [entry.entry_id for entry in store.entries] == ["e02", "e03"]
    assert HistoryEntry(**with_recipe.to_json()).to_json() == with_recipe.to_json()

    bad_entry = with_recipe.to_json()
    bad_entry["provenance"]["recipe"]["user_modified"] = 1.2
    with pytest.raises(HistoryValidationError, match="provenance is invalid"):
        history_entry_from_json(bad_entry)


def test_report_bundle_round_trips_recipe_provenance_metadata(tmp_path: Any) -> None:
    provenance = _recipe_provenance()
    target = tmp_path / "report.datalab-report.zip"

    manifest = write_report_bundle(
        target,
        semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
        tables={"summary": "metric,value\nmean,1\n"},
        latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
        recipe_provenance=provenance,
    )
    loaded = read_report_bundle(target)

    assert manifest["metadata"]["recipe_provenance"]["recipe_id"] == "weighted_mean_basic"
    assert loaded.manifest["metadata"]["recipe_provenance"] == manifest["metadata"]["recipe_provenance"]

    bad_manifest, _attachments = build_report_bundle_manifest(
        semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
        tables={"summary": "metric,value\nmean,1\n"},
        latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
        recipe_provenance=provenance,
    )
    bad_manifest["metadata"]["recipe_provenance"]["user_modified"] = 1.2
    with pytest.raises(ReportBundleValidationError, match="JSON floats"):
        validate_report_manifest(bad_manifest)

    missing_schema_manifest, _attachments = build_report_bundle_manifest(
        semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
        tables={"summary": "metric,value\nmean,1\n"},
        latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
        recipe_provenance=provenance,
    )
    del missing_schema_manifest["metadata"]["recipe_provenance"]["recipe_id"]
    with pytest.raises(ReportBundleValidationError, match="metadata.recipe_provenance is invalid"):
        validate_report_manifest(missing_schema_manifest)

    with pytest.raises(ReportBundleValidationError, match="metadata.recipe_provenance is invalid"):
        build_report_bundle_manifest(
            semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
            tables={"summary": "metric,value\nmean,1\n"},
            latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
            recipe_provenance={**provenance, "recipe_id": ""},
        )


def _recipe_provenance(*, source_label: str = "weighted recipe") -> dict[str, Any]:
    return build_recipe_provenance(
        recipe_id="weighted_mean_basic",
        recipe_schema_version=1,
        recipe_payload=_recipe(),
        apply_request=_apply_request(),
        generated_config={
            "statistics": {
                "mode": "weighted_sigma",
                "value_column": "Value",
                "value_columns": ["Value"],
                "sigma_column": "Sigma",
                "sample": True,
                "weighted_variance": True,
            }
        },
        source_label=source_label,
        applied_at="2026-06-28T00:00:00Z",
    )


def _apply_request() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.apply.v1",
        "recipe_id": "weighted_mean_basic",
        "bindings": {
            "inputs": {
                "data": {
                    "value": {"kind": "data_column", "column_id": "Value"},
                    "sigma": {"kind": "data_column", "column_id": "Sigma"},
                }
            }
        },
    }


def _recipe() -> dict[str, Any]:
    return {
        "schema": "datalab.recipe.v1",
        "schema_version": 1,
        "id": "weighted_mean_basic",
        "title": {"en": "Weighted mean"},
        "family": "statistics",
        "workflow_mode": "statistics.standard",
    }


def _workspace() -> dict[str, Any]:
    return {
        "title": "Untitled",
        "current_mode": "statistics",
        "language": "auto",
        "ui": {},
        "data": {"canonical_table": {"headers": ["Value", "Sigma"], "rows": [["1", "0.1"]]}},
        "constants": {},
        "config": {
            "common": {"precision_digits": 50},
            "statistics": {"mode": "weighted_sigma", "value_column": "Value", "sigma_column": "Sigma"},
        },
        "result_snapshot": {"present": False},
    }


def _history_entry(entry_id: str, *, provenance: dict[str, Any] | None = None) -> HistoryEntry:
    workspace = _workspace()
    if provenance is not None:
        workspace["provenance"] = provenance
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=entry_id,
        created_at="2026-06-28T00:00:00Z",
        workspace=workspace,
        family="statistics",
        kind="statistics_single",
        result_snapshot={"family": "statistics", "kind": "statistics_single", "status": "success"},
    )
