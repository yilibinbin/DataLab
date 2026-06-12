from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ._payload import normalize_json_payload


_V1_SCHEMA_VERSION = 1
FORMULA_PREVIEW_LANGUAGES = frozenset(("datalab", "python", "mathematica", "latex"))


@dataclass(frozen=True)
class WorkbenchModel:
    """Qt-free workbench state model with v1 workspace hash compatibility."""

    current_mode: str
    compute: Mapping[str, Any]
    ui: Mapping[str, Any] = field(default_factory=dict)
    result_snapshot: Mapping[str, Any] = field(default_factory=dict)
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

        return cls(
            title=_optional_text(workspace.get("title"), default="Untitled", field_name="title"),
            current_mode=current_mode,
            language=_optional_text(workspace.get("language"), default="auto", field_name="language"),
            compute=compute,
            ui=_normalize_ui(workspace.get("ui"), lenient=lenient_ui),
            result_snapshot=result_snapshot,
        )

    def compute_hash(self) -> str:
        from shared.workspace_schema import compute_workspace_hash

        return compute_workspace_hash(self.to_v1_workspace())

    def to_v1_workspace(self) -> dict[str, Any]:
        compute = copy.deepcopy(self.compute)
        return {
            "title": self.title,
            "current_mode": self.current_mode,
            "language": self.language,
            "ui": copy.deepcopy(self.ui),
            "data": compute.get("data") or {},
            "constants": compute.get("constants") or {},
            "config": compute.get("config") or {},
            "result_snapshot": copy.deepcopy(self.result_snapshot),
        }

    @property
    def formula_preview_languages(self) -> dict[str, str]:
        raw_preview = self.ui.get("formula_preview")
        if not isinstance(raw_preview, Mapping):
            return {}
        return _normalize_formula_preview(raw_preview)

    def formula_preview_language(self, schema_key: str) -> str | None:
        if not isinstance(schema_key, str):
            raise TypeError("formula preview schema key must be a string.")
        return self.formula_preview_languages.get(schema_key)

    def with_formula_preview_language(self, schema_key: str, language: str) -> "WorkbenchModel":
        schema_key = _formula_preview_text(schema_key, field_name="schema key")
        language = _formula_preview_text(language, field_name="language")
        preview = self.formula_preview_languages
        preview[schema_key] = language
        return self._replace_formula_preview_languages(preview)

    def without_formula_preview_language(self, schema_key: str) -> "WorkbenchModel":
        schema_key = _formula_preview_text(schema_key, field_name="schema key")
        preview = self.formula_preview_languages
        preview.pop(schema_key, None)
        return self._replace_formula_preview_languages(preview)

    def _replace_formula_preview_languages(self, preview: Mapping[str, str]) -> "WorkbenchModel":
        ui = copy.deepcopy(dict(self.ui))
        normalized = _normalize_formula_preview(preview)
        if normalized:
            ui["formula_preview"] = normalized
        else:
            ui.pop("formula_preview", None)
        return replace(self, ui=ui)


def _normalize_compute_workspace(
    workspace: Mapping[str, Any],
    *,
    current_mode: str,
    allow_legacy_floats: bool,
) -> Mapping[str, Any]:
    compute_workspace = {
        "current_mode": current_mode,
        "data": _mapping_or_empty(workspace.get("data"), field_name="data"),
        "constants": _mapping_or_empty(workspace.get("constants"), field_name="constants"),
        "config": _mapping_or_empty(workspace.get("config"), field_name="config"),
    }
    compute_workspace = _legacy_float_payload(
        compute_workspace,
        allow_legacy_floats=allow_legacy_floats,
    )
    normalized = normalize_json_payload(compute_workspace, path="compute")
    if not isinstance(normalized, Mapping):
        raise TypeError("compute workspace must be a mapping.")
    return normalized


def _normalize_ui(raw_ui: Any, *, lenient: bool = False) -> dict[str, Any]:
    if raw_ui is None:
        return {}
    if not isinstance(raw_ui, Mapping):
        raise TypeError("ui must be a mapping.")
    ui = copy.deepcopy(dict(raw_ui))
    if "formula_preview" in ui:
        preview = ui.get("formula_preview")
        if preview is None:
            ui.pop("formula_preview", None)
        else:
            try:
                ui["formula_preview"] = _normalize_formula_preview(preview)
            except (TypeError, ValueError):
                if not lenient:
                    raise
                ui.pop("formula_preview", None)
    return ui


def _normalize_formula_preview(raw_preview: Any) -> dict[str, str]:
    if not isinstance(raw_preview, Mapping):
        raise TypeError("ui.formula_preview must be a mapping.")
    normalized: dict[str, str] = {}
    for key, value in raw_preview.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("ui.formula_preview keys and values must be strings.")
        if key and value:
            normalized[key] = _normalize_formula_preview_language(value)
    return normalized


def _formula_preview_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"formula preview {field_name} must be a non-empty string.")
    return value


def _normalize_formula_preview_language(language: str) -> str:
    normalized = _formula_preview_text(language, field_name="language")
    if normalized not in FORMULA_PREVIEW_LANGUAGES:
        allowed = ", ".join(sorted(FORMULA_PREVIEW_LANGUAGES))
        raise ValueError(
            f"Unsupported formula preview language: {normalized!r}. "
            f"Expected one of: {allowed}."
        )
    return normalized


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
