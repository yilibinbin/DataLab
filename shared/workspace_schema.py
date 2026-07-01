from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any


SCHEMA = "datalab.workspace.v1"
SCHEMA_VERSION = 1

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PLOT_ATTACHMENTS = 64
MAX_SOURCE_ATTACHMENTS = 2
MAX_PLOT_BYTES = 20 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024

DISPLAY_ONLY_COMMON_KEYS = {
    "display_scientific",
    "display_digits",
}


class WorkspaceValidationError(ValueError):
    """Raised when a `.datalab` workspace is malformed or unsafe."""


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_relevant_config(config: Mapping[str, Any]) -> dict[str, Any]:
    relevant: dict[str, Any] = copy.deepcopy(dict(config))
    common = relevant.get("common")
    if isinstance(common, dict):
        for key in DISPLAY_ONLY_COMMON_KEYS:
            common.pop(key, None)
    return relevant


def workspace_hash_payload(workspace: Mapping[str, Any]) -> dict[str, Any]:
    """Return the v1 computation-affecting workspace payload."""

    return {
        "current_mode": workspace.get("current_mode"),
        "data": copy.deepcopy(workspace.get("data")),
        "constants": copy.deepcopy(workspace.get("constants")),
        "config": _hash_relevant_config(workspace.get("config") or {}),
    }


def workspace_hash_canonical_bytes(workspace: Mapping[str, Any]) -> bytes:
    """Return canonical bytes for the v1 computation-affecting workspace payload."""

    return canonical_json(workspace_hash_payload(workspace))


def compute_workspace_hash(workspace: dict[str, Any]) -> str:
    """Compute the v1 staleness hash for computation-affecting state."""

    return sha256_bytes(workspace_hash_canonical_bytes(workspace))


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict):
        raise WorkspaceValidationError("manifest must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise WorkspaceValidationError(f"schema must be {SCHEMA!r}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise WorkspaceValidationError("schema_version must be 1")
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict):
        raise WorkspaceValidationError("workspace must be an object")
    for key in ("current_mode", "data", "constants", "config", "result_snapshot"):
        if key not in workspace:
            raise WorkspaceValidationError(f"workspace.{key} is required")
    _validate_optional_unit_annotations(workspace)
    _validate_optional_recipe_provenance(workspace)
    _validate_optional_history(workspace)


def _validate_optional_unit_annotations(workspace: dict[str, Any]) -> None:
    config = workspace.get("config")
    if not isinstance(config, Mapping):
        return
    _validate_optional_family_units(config, "error", active_allowed=True)
    for family in ("root_solving", "fitting", "statistics"):
        _validate_optional_family_units(config, family, active_allowed=False)


def _validate_optional_family_units(
    config: Mapping[str, Any],
    family: str,
    *,
    active_allowed: bool,
) -> None:
    family_config = config.get(family)
    if not isinstance(family_config, Mapping) or "units" not in family_config:
        return
    try:
        from shared.unit_annotations import (
            UnitAnnotationError,
            normalize_display_only_family_units,
            normalize_unit_annotations,
        )

        if active_allowed:
            normalize_unit_annotations(family_config.get("units"))
        else:
            normalize_display_only_family_units(
                family_config.get("units"),
                family=family,
            )
    except (TypeError, UnitAnnotationError, ValueError) as exc:
        raise WorkspaceValidationError(f"workspace.config.{family}.units is invalid: {exc}") from exc


def _validate_optional_recipe_provenance(workspace: dict[str, Any]) -> None:
    if "provenance" not in workspace:
        return
    try:
        from datalab_core.recipe_provenance import normalize_workspace_provenance

        normalize_workspace_provenance(workspace.get("provenance"))
    except (TypeError, ValueError) as exc:
        raise WorkspaceValidationError(f"workspace.provenance is invalid: {exc}") from exc


def _validate_optional_history(workspace: dict[str, Any]) -> None:
    if "history" not in workspace:
        return
    history = workspace.get("history")
    if not isinstance(history, dict):
        raise WorkspaceValidationError("workspace.history must be an object")
    try:
        from datalab_core.history import history_store_from_json

        history_store_from_json(history)
    except (TypeError, ValueError) as exc:
        raise WorkspaceValidationError(f"workspace.history is invalid: {exc}") from exc


def collect_manifest_attachment_paths(manifest: dict[str, Any]) -> set[str]:
    workspace = manifest.get("workspace") or {}
    paths: set[str] = set()
    for section_name in ("data", "constants"):
        section = workspace.get(section_name) or {}
        if isinstance(section, dict):
            raw_path = section.get("raw_bytes_path")
            if isinstance(raw_path, str) and raw_path:
                paths.add(raw_path)
    result = workspace.get("result_snapshot") or {}
    if isinstance(result, dict):
        for plot in result.get("plots") or []:
            if isinstance(plot, dict):
                path = plot.get("path")
                if isinstance(path, str) and path:
                    paths.add(path)
    return paths


def validate_manifest_attachment_hashes(
    manifest: dict[str, Any],
    attachments: dict[str, bytes],
) -> None:
    workspace = manifest.get("workspace") or {}
    for section_name in ("data", "constants"):
        section = workspace.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        raw_path = section.get("raw_bytes_path")
        expected_hash = section.get("original_bytes_sha256")
        if isinstance(raw_path, str) and raw_path:
            if raw_path not in attachments:
                raise WorkspaceValidationError(f"missing source attachment: {raw_path}")
            if isinstance(expected_hash, str) and expected_hash and sha256_bytes(attachments[raw_path]) != expected_hash:
                raise WorkspaceValidationError(f"source attachment hash mismatch: {raw_path}")

    result = workspace.get("result_snapshot") or {}
    if not isinstance(result, dict):
        return
    for plot in result.get("plots") or []:
        if not isinstance(plot, dict):
            continue
        path = plot.get("path")
        expected_hash = plot.get("sha256")
        fmt = plot.get("format")
        if not isinstance(path, str) or not path:
            raise WorkspaceValidationError("plot path is required")
        if fmt != "png" or not path.endswith(".png"):
            raise WorkspaceValidationError(f"plot attachment must be png: {path}")
        if path not in attachments:
            raise WorkspaceValidationError(f"missing plot attachment: {path}")
        if isinstance(expected_hash, str) and expected_hash and sha256_bytes(attachments[path]) != expected_hash:
            raise WorkspaceValidationError(f"plot attachment hash mismatch: {path}")
