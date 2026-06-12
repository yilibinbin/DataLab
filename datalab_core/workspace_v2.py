from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .workbench_model import WorkbenchModel


SCHEMA = "datalab.workspace.v2"
SCHEMA_VERSION = 2


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    from shared.workspace_schema import WorkspaceValidationError

    if not isinstance(manifest, Mapping):
        raise WorkspaceValidationError("manifest must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise WorkspaceValidationError(f"schema must be {SCHEMA!r}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise WorkspaceValidationError("schema_version must be 2")
    model = manifest.get("model")
    if not isinstance(model, Mapping):
        raise WorkspaceValidationError("model must be an object")
    compute = model.get("compute")
    if not isinstance(compute, Mapping):
        raise WorkspaceValidationError("model.compute must be an object")
    for key in ("data", "constants", "config"):
        if key not in compute:
            raise WorkspaceValidationError(f"model.compute.{key} is required")
        if not isinstance(compute[key], Mapping):
            raise WorkspaceValidationError(f"model.compute.{key} must be a mapping")
    if "result_snapshot" not in model:
        raise WorkspaceValidationError("model.result_snapshot is required")
    if not isinstance(model["result_snapshot"], Mapping):
        raise WorkspaceValidationError("model.result_snapshot must be a mapping")


def model_from_manifest(manifest: Mapping[str, Any]) -> WorkbenchModel:
    validate_manifest(manifest)
    model_payload = copy.deepcopy(dict(manifest["model"]))
    compute = model_payload["compute"]
    workspace = {
        "title": model_payload["title"] if "title" in model_payload else "Untitled",
        "current_mode": model_payload["current_mode"] if "current_mode" in model_payload else "fitting",
        "language": model_payload["language"] if "language" in model_payload else "auto",
        "ui": model_payload["ui"] if "ui" in model_payload else {},
        "data": compute["data"],
        "constants": compute["constants"],
        "config": compute["config"],
        "result_snapshot": model_payload["result_snapshot"],
    }
    return WorkbenchModel.from_v1_workspace(workspace)


def to_v1_workspace(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return model_from_manifest(manifest).to_v1_workspace()


def to_compatible_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    compatible = copy.deepcopy(dict(manifest))
    compatible["workspace"] = to_v1_workspace(manifest)
    return compatible


def collect_attachment_paths(manifest: Mapping[str, Any]) -> set[str]:
    from shared.workspace_schema import collect_manifest_attachment_paths

    return collect_manifest_attachment_paths({"workspace": to_v1_workspace(manifest)})


def validate_attachment_hashes(
    manifest: Mapping[str, Any],
    attachments: dict[str, bytes],
) -> None:
    from shared.workspace_schema import validate_manifest_attachment_hashes

    validate_manifest_attachment_hashes({"workspace": to_v1_workspace(manifest)}, attachments)


__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "collect_attachment_paths",
    "model_from_manifest",
    "to_compatible_manifest",
    "to_v1_workspace",
    "validate_attachment_hashes",
    "validate_manifest",
]
