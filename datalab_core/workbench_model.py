from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from ._payload import normalize_json_payload


_V1_SCHEMA_VERSION = 1
_DISPLAY_ONLY_UNIT_FAMILIES = ("root_solving", "fitting", "statistics")


@dataclass(frozen=True)
class WorkbenchModel:
    """Qt-free workbench state model with v1 workspace hash compatibility."""

    current_mode: str
    compute: Mapping[str, Any]
    ui: Mapping[str, Any] = field(default_factory=dict)
    result_snapshot: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] | None = None
    history: Mapping[str, Any] | None = None
    title: str = "Untitled"
    language: str = "auto"
    schema_version: int = _V1_SCHEMA_VERSION

    @classmethod
    def from_v1_manifest(
        cls,
        manifest: Mapping[str, Any],
        *,
        allow_legacy_floats: bool = False,
        lenient_ui: bool = False,
    ) -> "WorkbenchModel":
        from shared.workspace_schema import validate_manifest

        if not isinstance(manifest, Mapping):
            raise TypeError("manifest must be a mapping.")
        manifest_copy = copy.deepcopy(dict(manifest))
        validate_manifest(manifest_copy)
        return cls.from_v1_workspace(
            manifest_copy["workspace"],
            allow_legacy_floats=allow_legacy_floats,
            lenient_ui=lenient_ui,
        )

    @classmethod
    def from_v1_workspace(
        cls,
        workspace: Mapping[str, Any],
        *,
        allow_legacy_floats: bool = False,
        lenient_ui: bool = False,
    ) -> "WorkbenchModel":
        if not isinstance(workspace, Mapping):
            raise TypeError("workspace must be a mapping.")

        current_mode = _optional_text(workspace.get("current_mode"), default="fitting", field_name="current_mode")
        compute = _normalize_compute_workspace(
            workspace,
            current_mode=current_mode,
            allow_legacy_floats=allow_legacy_floats,
        )
        result_snapshot = normalize_json_payload(
            _legacy_float_payload(
                _mapping_or_empty(workspace.get("result_snapshot"), field_name="result_snapshot"),
                allow_legacy_floats=allow_legacy_floats,
            ),
            path="result_snapshot",
        )
        history = None
        if "history" in workspace:
            from .history import history_store_from_json

            history_payload = normalize_json_payload(
                _mapping_or_empty(workspace.get("history"), field_name="history"),
                path="history",
            )
            history = normalize_json_payload(
                history_store_from_json(history_payload).to_json(),
                path="history",
            )
        provenance = None
        if "provenance" in workspace:
            from .recipe_provenance import normalize_workspace_provenance

            provenance_payload = normalize_workspace_provenance(workspace.get("provenance"))
            provenance = normalize_json_payload(provenance_payload, path="provenance")

        return cls(
            title=_optional_text(workspace.get("title"), default="Untitled", field_name="title"),
            current_mode=current_mode,
            language=_optional_text(workspace.get("language"), default="auto", field_name="language"),
            compute=compute,
            ui=_normalize_ui(workspace.get("ui"), lenient=lenient_ui),
            result_snapshot=result_snapshot,
            provenance=provenance,
            history=history,
        )

    def compute_hash(self) -> str:
        from shared.workspace_schema import compute_workspace_hash

        return cast(str, compute_workspace_hash(self.to_v1_workspace()))

    def to_v1_workspace(self) -> dict[str, Any]:
        compute = copy.deepcopy(self.compute)
        workspace = {
            "title": self.title,
            "current_mode": self.current_mode,
            "language": self.language,
            "ui": copy.deepcopy(self.ui),
            "data": compute.get("data") or {},
            "constants": compute.get("constants") or {},
            "config": compute.get("config") or {},
            "result_snapshot": copy.deepcopy(self.result_snapshot),
        }
        if self.history is not None:
            workspace["history"] = copy.deepcopy(self.history)
        if self.provenance is not None:
            workspace["provenance"] = copy.deepcopy(self.provenance)
        return workspace

    @property
    def formula_preview_languages(self) -> dict[str, str]:
        """Deprecated compatibility view for removed preview-language UI state."""
        return {}

    def formula_preview_language(self, schema_key: str) -> str | None:
        if not isinstance(schema_key, str):
            raise TypeError("formula preview schema key must be a string.")
        return None

    def with_formula_preview_language(self, schema_key: str, language: str) -> "WorkbenchModel":
        _formula_preview_text(schema_key, field_name="schema key")
        _formula_preview_text(language, field_name="language")
        return self

    def without_formula_preview_language(self, schema_key: str) -> "WorkbenchModel":
        _formula_preview_text(schema_key, field_name="schema key")
        return self


def _normalize_compute_workspace(
    workspace: Mapping[str, Any],
    *,
    current_mode: str,
    allow_legacy_floats: bool,
) -> Mapping[str, Any]:
    compute_workspace: Mapping[str, Any] = {
        "current_mode": current_mode,
        "data": _mapping_or_empty(workspace.get("data"), field_name="data"),
        "constants": _mapping_or_empty(workspace.get("constants"), field_name="constants"),
        "config": _mapping_or_empty(workspace.get("config"), field_name="config"),
    }
    compute_workspace = _normalize_raw_unit_configs_before_legacy_float(compute_workspace)
    compute_workspace = _legacy_float_payload(
        compute_workspace,
        allow_legacy_floats=allow_legacy_floats,
    )
    normalized = normalize_json_payload(compute_workspace, path="compute")
    if not isinstance(normalized, Mapping):
        raise TypeError("compute workspace must be a mapping.")
    return _normalize_unit_configs_in_compute(normalized)


def _normalize_raw_unit_configs_before_legacy_float(compute: Mapping[str, Any]) -> Mapping[str, Any]:
    return _normalize_unit_configs(compute, refreeze=False)


def _normalize_unit_configs_in_compute(compute: Mapping[str, Any]) -> Mapping[str, Any]:
    return _normalize_unit_configs(compute, refreeze=True)


def _normalize_unit_configs(compute: Mapping[str, Any], *, refreeze: bool) -> Mapping[str, Any]:
    config = compute.get("config")
    if not isinstance(config, Mapping):
        return compute
    families = ("error", *_DISPLAY_ONLY_UNIT_FAMILIES)
    has_unit_config = False
    for family in families:
        family_config = config.get(family)
        if isinstance(family_config, Mapping) and "units" in family_config:
            has_unit_config = True
            break
    if not has_unit_config:
        return compute

    normalized = _mutable_json_copy(compute)
    mutable_config = normalized.get("config")
    if not isinstance(mutable_config, dict):
        return compute
    for family in families:
        mutable_family = mutable_config.get(family)
        if not isinstance(mutable_family, dict) or "units" not in mutable_family:
            continue
        mutable_family["units"] = _normalize_unit_config_for_family(family, mutable_family.get("units"))
    if not refreeze:
        return cast(Mapping[str, Any], normalized)
    refrozen = normalize_json_payload(normalized, path="compute")
    if not isinstance(refrozen, Mapping):
        raise TypeError("compute workspace must be a mapping.")
    return refrozen


def _normalize_unit_config_for_family(family: str, units: Any) -> dict[str, Any] | None:
    from shared.unit_annotations import (
        UnitAnnotationError,
        normalize_display_only_family_units,
        normalize_unit_annotations,
    )

    try:
        if family == "error":
            return normalize_unit_annotations(units)
        return normalize_display_only_family_units(units, family=family)
    except UnitAnnotationError as exc:
        raise TypeError(f"config.{family}.units is invalid: {exc}") from exc


def _mutable_json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {copy.deepcopy(key): _mutable_json_copy(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [_mutable_json_copy(item) for item in value]
    return copy.deepcopy(value)


def _normalize_ui(raw_ui: Any, *, lenient: bool = False) -> dict[str, Any]:
    if raw_ui is None:
        return {}
    if not isinstance(raw_ui, Mapping):
        raise TypeError("ui must be a mapping.")
    ui = copy.deepcopy(dict(raw_ui))
    # Preview-language UI state was removed. Keep old workspaces readable, but
    # do not expose or re-save their legacy formula_preview metadata.
    ui.pop("formula_preview", None)
    return ui


def _formula_preview_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"formula preview {field_name} must be a non-empty string.")
    return value


def _legacy_float_payload(value: Any, *, allow_legacy_floats: bool) -> Any:
    if not allow_legacy_floats:
        return value
    if isinstance(value, float):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key) if isinstance(key, float) else key: _legacy_float_payload(
                item,
                allow_legacy_floats=allow_legacy_floats,
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _legacy_float_payload(item, allow_legacy_floats=allow_legacy_floats)
            for item in value
        ]
    return value


def _mapping_or_empty(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return value


def _optional_text(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    return value
