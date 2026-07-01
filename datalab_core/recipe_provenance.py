from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from shared.workspace_schema import canonical_json, sha256_bytes

RECIPE_PROVENANCE_SCHEMA = "datalab.recipe_provenance.v1"
RECIPE_PROVENANCE_SCHEMA_VERSION = 1
MAX_RECIPE_PROVENANCE_BYTES = 16 * 1024
MAX_RECIPE_PROVENANCE_TEXT = 512
MAX_BINDING_SUMMARY_BYTES = 8 * 1024

_ALLOWED_RECIPE_KEYS = {
    "schema",
    "schema_version",
    "recipe_id",
    "recipe_schema_version",
    "source_kind",
    "source_label",
    "source_sha256",
    "binding_summary",
    "binding_sha256",
    "generated_config_sha256",
    "applied_at",
    "user_modified",
}
_SOURCE_KINDS = {"bundled", "file", "inline", "generated", "unknown"}


class RecipeProvenanceError(ValueError):
    """Raised when recipe provenance is malformed or exceeds limits."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_recipe_provenance(
    *,
    recipe_id: str,
    recipe_schema_version: int,
    recipe_payload: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    generated_config: Mapping[str, Any],
    source_kind: str = "inline",
    source_label: str = "",
    applied_at: str | None = None,
    user_modified: bool = False,
) -> dict[str, Any]:
    binding_summary = _json_plain(apply_request.get("bindings", {}), path="binding_summary")
    _ensure_json_size(binding_summary, MAX_BINDING_SUMMARY_BYTES, "binding_summary")
    provenance = {
        "schema": RECIPE_PROVENANCE_SCHEMA,
        "schema_version": RECIPE_PROVENANCE_SCHEMA_VERSION,
        "recipe_id": _text(recipe_id, "recipe_id"),
        "recipe_schema_version": _int(recipe_schema_version, "recipe_schema_version"),
        "source_kind": _source_kind(source_kind),
        "source_sha256": sha256_bytes(canonical_json(_json_plain(recipe_payload, path="recipe_payload"))),
        "binding_summary": binding_summary,
        "binding_sha256": sha256_bytes(canonical_json(binding_summary)),
        "generated_config_sha256": sha256_bytes(canonical_json(_json_plain(generated_config, path="generated_config"))),
        "applied_at": _timestamp(applied_at or utc_timestamp(), "applied_at"),
        "user_modified": bool(user_modified),
    }
    if source_label:
        provenance["source_label"] = _text(source_label, "source_label")
    return normalize_recipe_provenance(provenance)


def normalize_workspace_provenance(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RecipeProvenanceError("workspace provenance must be an object")
    normalized = _json_plain(value, path="provenance")
    if not isinstance(normalized, dict):
        raise RecipeProvenanceError("workspace provenance must be an object")
    unknown = set(normalized) - {"recipe"}
    if unknown:
        raise RecipeProvenanceError(f"workspace provenance contains unsupported fields: {', '.join(sorted(unknown))}")
    recipe = normalized.get("recipe")
    if recipe is not None:
        normalized["recipe"] = normalize_recipe_provenance(recipe)
    _ensure_json_size(normalized, MAX_RECIPE_PROVENANCE_BYTES, "provenance")
    return normalized


def normalize_recipe_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeProvenanceError("recipe provenance must be an object")
    raw = _json_plain(value, path="recipe_provenance")
    if not isinstance(raw, dict):
        raise RecipeProvenanceError("recipe provenance must be an object")
    unknown = set(raw) - _ALLOWED_RECIPE_KEYS
    if unknown:
        raise RecipeProvenanceError(f"recipe provenance contains unsupported fields: {', '.join(sorted(unknown))}")
    if raw.get("schema") != RECIPE_PROVENANCE_SCHEMA:
        raise RecipeProvenanceError(f"recipe provenance schema must be {RECIPE_PROVENANCE_SCHEMA!r}")
    if raw.get("schema_version") != RECIPE_PROVENANCE_SCHEMA_VERSION:
        raise RecipeProvenanceError("recipe provenance schema_version must be 1")
    normalized: dict[str, Any] = {
        "schema": RECIPE_PROVENANCE_SCHEMA,
        "schema_version": RECIPE_PROVENANCE_SCHEMA_VERSION,
        "recipe_id": _text(raw.get("recipe_id"), "recipe_id"),
        "recipe_schema_version": _int(raw.get("recipe_schema_version"), "recipe_schema_version"),
        "source_kind": _source_kind(raw.get("source_kind")),
        "source_sha256": _hash_text(raw.get("source_sha256"), "source_sha256"),
        "binding_sha256": _hash_text(raw.get("binding_sha256"), "binding_sha256"),
        "generated_config_sha256": _hash_text(raw.get("generated_config_sha256"), "generated_config_sha256"),
        "applied_at": _timestamp(raw.get("applied_at"), "applied_at"),
        "user_modified": _bool(raw.get("user_modified"), "user_modified"),
    }
    if raw.get("source_label") is not None:
        normalized["source_label"] = _text(raw.get("source_label"), "source_label")
    if raw.get("binding_summary") is not None:
        binding_summary = _json_plain(raw.get("binding_summary"), path="binding_summary")
        _ensure_json_size(binding_summary, MAX_BINDING_SUMMARY_BYTES, "binding_summary")
        normalized["binding_summary"] = binding_summary
    _ensure_json_size(normalized, MAX_RECIPE_PROVENANCE_BYTES, "recipe provenance")
    return normalized


def mark_recipe_provenance_modified(provenance: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if provenance is None:
        return None
    normalized = normalize_workspace_provenance(provenance)
    recipe = normalized.get("recipe")
    if isinstance(recipe, dict):
        recipe["user_modified"] = True
        normalized["recipe"] = normalize_recipe_provenance(recipe)
    return normalized


def _json_plain(value: Any, *, path: str) -> Any:
    if isinstance(value, float):
        raise RecipeProvenanceError(f"JSON floats are not allowed at {path}")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecipeProvenanceError(f"{path} keys must be strings")
            output[key] = _json_plain(item, path=f"{path}.{key}")
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [_json_plain(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise RecipeProvenanceError(f"unsupported JSON value type at {path}: {type(value).__name__}")


def _ensure_json_size(value: Any, limit: int, field_name: str) -> None:
    if len(canonical_json(value)) > limit:
        raise RecipeProvenanceError(f"{field_name} exceeds {limit} bytes")


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecipeProvenanceError(f"{field_name} must be a non-empty string")
    text = value.strip()
    if len(text) > MAX_RECIPE_PROVENANCE_TEXT:
        raise RecipeProvenanceError(f"{field_name} is too long")
    if any(ord(char) < 32 for char in text):
        raise RecipeProvenanceError(f"{field_name} contains control characters")
    return text


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecipeProvenanceError(f"{field_name} must be an integer")
    if value < 1:
        raise RecipeProvenanceError(f"{field_name} must be positive")
    parsed: int = value
    return parsed


def _bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise RecipeProvenanceError(f"{field_name} must be a boolean")
    return value


def _source_kind(value: Any) -> str:
    text = _text(value, "source_kind")
    if text not in _SOURCE_KINDS:
        raise RecipeProvenanceError(f"unsupported source_kind: {text}")
    return text


def _hash_text(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    prefix = "sha256:"
    digest = text[len(prefix) :] if text.startswith(prefix) else ""
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RecipeProvenanceError(f"{field_name} must be a sha256 digest")
    return text


def _timestamp(value: Any, field_name: str) -> str:
    text = _text(value, field_name)
    parseable = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise RecipeProvenanceError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise RecipeProvenanceError(f"{field_name} must include a timezone")
    return text


__all__ = [
    "MAX_BINDING_SUMMARY_BYTES",
    "MAX_RECIPE_PROVENANCE_BYTES",
    "RECIPE_PROVENANCE_SCHEMA",
    "RECIPE_PROVENANCE_SCHEMA_VERSION",
    "RecipeProvenanceError",
    "build_recipe_provenance",
    "mark_recipe_provenance_modified",
    "normalize_recipe_provenance",
    "normalize_workspace_provenance",
    "utc_timestamp",
]
