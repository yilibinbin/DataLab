from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from shared.workspace_schema import canonical_json, sha256_bytes, workspace_hash_canonical_bytes, workspace_hash_payload

from ._payload import normalize_json_payload
from .recipe_provenance import RecipeProvenanceError, normalize_workspace_provenance


HISTORY_ENTRY_SCHEMA = "datalab.history.entry.v1"
HISTORY_STORE_SCHEMA = "datalab.history.store.v1"
HISTORY_SCHEMA_VERSION = 1

DEFAULT_RECENT_ENTRIES = 20
DEFAULT_PINNED_ENTRIES = 5
DEFAULT_TOTAL_SEMANTIC_BYTES = 25 * 1024 * 1024
DEFAULT_ENTRY_SEMANTIC_BYTES = 2 * 1024 * 1024

_SEMANTIC_KEYS = {"schema", "snapshot_version", "family", "kind", "language", "status", "input_signature", "result"}
_HISTORY_STATUSES = {"success", "warning", "failed", "stale", "restored"}
_INPUT_SIGNATURE_KEYS = {"current_mode", "workspace_hash", "data_hash", "constants_hash", "formula_model", "options"}
_FORMULA_MODEL_KEYS = {
    "model",
    "model_name",
    "expression",
    "formula",
    "equation",
    "equations",
    "function",
    "target",
    "variables",
    "unknowns",
    "x_column",
    "y_column",
}
_RENDERED_CACHE_KEYS = {
    "attachments",
    "cache",
    "caches",
    "csv",
    "csv_text",
    "latex",
    "latex_document",
    "latex_source",
    "markdown",
    "pdf",
    "pdf_path",
    "plot_count",
    "plot_spec_keys",
    "plots",
    "preview",
    "preview_cache",
    "rendered_cache",
    "rendered_cache_fields",
    "rendered_caches",
    "rendered_caches_authoritative",
}


class HistoryValidationError(ValueError):
    """Raised when a history entry/store is malformed or not JSON-safe."""


class HistoryPruneError(ValueError):
    """Raised when bounded history cannot preserve required semantic data."""


@dataclass(frozen=True)
class HistoryLimits:
    recent_entries: int = DEFAULT_RECENT_ENTRIES
    pinned_entries: int = DEFAULT_PINNED_ENTRIES
    total_semantic_bytes: int = DEFAULT_TOTAL_SEMANTIC_BYTES
    entry_semantic_bytes: int = DEFAULT_ENTRY_SEMANTIC_BYTES

    def __post_init__(self) -> None:
        for field_name in (
            "recent_entries",
            "pinned_entries",
            "total_semantic_bytes",
            "entry_semantic_bytes",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise HistoryValidationError(f"{field_name} must be a non-negative integer.")


@dataclass(frozen=True)
class HistoryEntry:
    entry_id: str
    label: str
    created_at: str
    semantic_snapshot: Mapping[str, Any]
    pinned: bool = False
    provenance: Mapping[str, Any] | None = None
    rendered_cache: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _required_text(self.entry_id, "entry_id"))
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        object.__setattr__(self, "created_at", _required_text(self.created_at, "created_at"))
        if not isinstance(self.pinned, bool):
            raise HistoryValidationError("pinned must be a boolean.")

        semantic = normalize_json_payload(self.semantic_snapshot, path="semantic_snapshot")
        semantic_plain = _plain_json(semantic)
        if not isinstance(semantic_plain, dict):
            raise HistoryValidationError("semantic_snapshot must be a JSON object.")
        _validate_semantic_snapshot(semantic_plain)
        object.__setattr__(self, "semantic_snapshot", semantic)

        if self.provenance is not None:
            try:
                provenance = normalize_workspace_provenance(self.provenance)
            except RecipeProvenanceError as exc:
                raise HistoryValidationError(f"history entry provenance is invalid: {exc}") from exc
            object.__setattr__(self, "provenance", normalize_json_payload(provenance, path="provenance"))

        if self.rendered_cache is None:
            return
        cache = normalize_json_payload(self.rendered_cache, path="rendered_cache")
        cache_plain = _plain_json(cache)
        if not isinstance(cache_plain, dict):
            raise HistoryValidationError("rendered_cache must be a JSON object.")
        object.__setattr__(self, "rendered_cache", cache)

    @classmethod
    def from_workspace_snapshot(
        cls,
        *,
        entry_id: str,
        label: str,
        created_at: str,
        workspace: Mapping[str, Any],
        family: str,
        kind: str,
        snapshot_version: int = HISTORY_SCHEMA_VERSION,
        result_snapshot: Mapping[str, Any] | None = None,
        pinned: bool = False,
        provenance: Mapping[str, Any] | None = None,
        rendered_cache: Mapping[str, Any] | None = None,
    ) -> "HistoryEntry":
        semantic_snapshot = build_history_semantic_snapshot(
            workspace=workspace,
            family=family,
            kind=kind,
            snapshot_version=snapshot_version,
            result_snapshot=result_snapshot,
        )
        return cls(
            entry_id=entry_id,
            label=label,
            created_at=created_at,
            pinned=pinned,
            semantic_snapshot=semantic_snapshot,
            provenance=provenance or _history_provenance_from_workspace(workspace),
            rendered_cache=rendered_cache,
        )

    @property
    def family(self) -> str:
        return str(self.semantic_snapshot["family"])

    @property
    def kind(self) -> str:
        return str(self.semantic_snapshot["kind"])

    @property
    def snapshot_version(self) -> int:
        return int(self.semantic_snapshot["snapshot_version"])

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_history_bytes(self.semantic_snapshot)

    @property
    def semantic_hash(self) -> str:
        return sha256_bytes(self.canonical_bytes)

    @property
    def identity_bytes(self) -> bytes:
        payload: dict[str, Any] = {"semantic_snapshot": _plain_json(self.semantic_snapshot)}
        if self.provenance is not None:
            payload["provenance"] = _plain_json(self.provenance)
        return canonical_json(payload)

    @property
    def identity_hash(self) -> str:
        return sha256_bytes(self.identity_bytes)

    @property
    def semantic_size_bytes(self) -> int:
        return len(self.canonical_bytes)

    @property
    def provenance_size_bytes(self) -> int:
        if self.provenance is None:
            return 0
        return len(canonical_json(_plain_json(self.provenance)))

    @property
    def rendered_cache_size_bytes(self) -> int:
        if self.rendered_cache is None:
            return 0
        return len(canonical_json(_plain_json(self.rendered_cache)))

    def without_rendered_cache(self) -> "HistoryEntry":
        if self.rendered_cache is None:
            return self
        return replace(self, rendered_cache=None)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entry_id": self.entry_id,
            "label": self.label,
            "created_at": self.created_at,
            "pinned": self.pinned,
            "semantic_snapshot": _plain_json(self.semantic_snapshot),
        }
        if self.rendered_cache is not None:
            payload["rendered_cache"] = _plain_json(self.rendered_cache)
        if self.provenance is not None:
            payload["provenance"] = _plain_json(self.provenance)
        return payload


@dataclass(frozen=True)
class HistoryPruneReport:
    dropped_rendered_cache_entry_ids: tuple[str, ...] = ()
    dropped_entry_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoryStore:
    current: HistoryEntry | None = None
    entries: tuple[HistoryEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.current is not None and not isinstance(self.current, HistoryEntry):
            raise HistoryValidationError("current must be a HistoryEntry or None.")
        entries = tuple(self.entries)
        if any(not isinstance(entry, HistoryEntry) for entry in entries):
            raise HistoryValidationError("entries must contain HistoryEntry values.")
        object.__setattr__(self, "entries", entries)

    def add_entry(self, entry: HistoryEntry) -> "HistoryStore":
        if not isinstance(entry, HistoryEntry):
            raise HistoryValidationError("entry must be a HistoryEntry.")
        return replace(self, entries=(entry, *self.entries)).deduplicated()

    def with_current(self, entry: HistoryEntry, *, keep_previous: bool = True) -> "HistoryStore":
        if not isinstance(entry, HistoryEntry):
            raise HistoryValidationError("entry must be a HistoryEntry.")
        entries = self.entries
        if keep_previous and self.current is not None:
            entries = (self.current, *entries)
        return HistoryStore(current=entry, entries=entries).deduplicated()

    def deduplicated(self) -> "HistoryStore":
        seen: dict[str, list[bytes]] = {}
        current = self.current
        if current is not None:
            seen[current.identity_hash] = [current.identity_bytes]
        deduped: list[HistoryEntry] = []
        for entry in self.entries:
            canonical = entry.identity_bytes
            matches = seen.setdefault(entry.identity_hash, [])
            if any(canonical == existing for existing in matches):
                continue
            matches.append(canonical)
            deduped.append(entry)
        if tuple(deduped) == self.entries:
            return self
        return HistoryStore(current=current, entries=tuple(deduped))

    def prune_for_save(
        self,
        limits: HistoryLimits | None = None,
    ) -> tuple["HistoryStore", HistoryPruneReport]:
        active_limits = limits or HistoryLimits()
        store = self.deduplicated()
        dropped_caches: list[str] = []
        dropped_entries: list[str] = []

        if store.current is not None:
            _ensure_entry_fits(store.current, active_limits, is_current=True)

        entries: list[HistoryEntry] = []
        for entry in store.entries:
            if entry.semantic_size_bytes > active_limits.entry_semantic_bytes:
                if entry.pinned:
                    raise HistoryPruneError("pinned history entry exceeds the per-entry semantic limit.")
                dropped_entries.append(entry.entry_id)
            else:
                entries.append(entry)

        if _store_size(store.current, entries) > active_limits.total_semantic_bytes:
            current = store.current.without_rendered_cache() if store.current is not None else None
            if current is not store.current and current is not None:
                dropped_caches.append(current.entry_id)
            stripped_entries: list[HistoryEntry] = []
            for entry in entries:
                stripped = entry.without_rendered_cache()
                if stripped is not entry:
                    dropped_caches.append(stripped.entry_id)
                stripped_entries.append(stripped)
            store = HistoryStore(current=current, entries=tuple(stripped_entries))
            entries = list(store.entries)
        else:
            store = HistoryStore(current=store.current, entries=tuple(entries))

        pinned_count = sum(1 for entry in entries if entry.pinned)
        if pinned_count > active_limits.pinned_entries:
            raise HistoryPruneError("pinned history entries exceed the configured limit.")

        entries = _prune_recent_count(entries, active_limits.recent_entries, dropped_entries)
        while _store_size(store.current, entries) > active_limits.total_semantic_bytes:
            drop_index = _oldest_unpinned_index(entries)
            if drop_index is None:
                raise HistoryPruneError("history cannot fit without dropping current or pinned semantic data.")
            dropped_entries.append(entries[drop_index].entry_id)
            del entries[drop_index]

        pruned = HistoryStore(current=store.current, entries=tuple(entries))
        return pruned, HistoryPruneReport(
            dropped_rendered_cache_entry_ids=tuple(dropped_caches),
            dropped_entry_ids=tuple(dropped_entries),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": HISTORY_STORE_SCHEMA,
            "schema_version": HISTORY_SCHEMA_VERSION,
            "current": self.current.to_json() if self.current is not None else None,
            "entries": [entry.to_json() for entry in self.entries],
        }


def build_history_semantic_snapshot(
    *,
    workspace: Mapping[str, Any],
    family: str,
    kind: str,
    snapshot_version: int = HISTORY_SCHEMA_VERSION,
    result_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(workspace, Mapping):
        raise HistoryValidationError("workspace must be a mapping.")
    if isinstance(snapshot_version, bool) or not isinstance(snapshot_version, int) or snapshot_version < 1:
        raise HistoryValidationError("snapshot_version must be a positive integer.")
    raw_result = result_snapshot if result_snapshot is not None else workspace.get("result_snapshot")
    result = strip_rendered_cache_fields({} if raw_result is None else raw_result)
    semantic = {
        "schema": HISTORY_ENTRY_SCHEMA,
        "snapshot_version": snapshot_version,
        "family": _required_text(family, "family"),
        "kind": _required_text(kind, "kind"),
        "language": _required_text(workspace.get("language", "auto"), "language"),
        "status": _history_status(result),
        "input_signature": build_history_input_signature(workspace),
        "result": result,
    }
    normalized = normalize_json_payload(semantic, path="history_semantic_snapshot")
    plain = _plain_json(normalized)
    if not isinstance(plain, dict):
        raise HistoryValidationError("history semantic snapshot must be an object.")
    _validate_semantic_snapshot(plain)
    return plain


def build_history_input_signature(workspace: Mapping[str, Any]) -> dict[str, Any]:
    payload = workspace_hash_payload(workspace)
    normalized = normalize_json_payload(payload, path="history_input_signature")
    plain = _plain_json(normalized)
    if not isinstance(plain, dict):
        raise HistoryValidationError("history input signature payload must be an object.")

    current_mode = plain.get("current_mode")
    raw_config = plain.get("config")
    config: Mapping[str, Any] = raw_config if isinstance(raw_config, Mapping) else {}
    raw_mode_config = config.get(current_mode) if isinstance(current_mode, str) else None
    mode_config: Mapping[str, Any] = raw_mode_config if isinstance(raw_mode_config, Mapping) else {}

    return {
        "current_mode": current_mode,
        "workspace_hash": sha256_bytes(workspace_hash_canonical_bytes(plain)),
        "data_hash": sha256_bytes(canonical_json(plain.get("data"))),
        "constants_hash": sha256_bytes(canonical_json(plain.get("constants"))),
        "formula_model": _formula_model_summary(mode_config),
        "options": _options_signature(config, mode_config),
    }


def canonical_history_bytes(semantic_snapshot: Mapping[str, Any]) -> bytes:
    normalized = normalize_json_payload(semantic_snapshot, path="semantic_snapshot")
    plain = _plain_json(normalized)
    if not isinstance(plain, dict):
        raise HistoryValidationError("semantic_snapshot must be a JSON object.")
    _validate_semantic_snapshot(plain)
    return canonical_json(plain)


def strip_rendered_cache_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise HistoryValidationError("semantic result keys must be strings.")
            if key in _RENDERED_CACHE_KEYS or key.endswith("_cache") or key.endswith("_cache_metadata"):
                continue
            cleaned[key] = strip_rendered_cache_fields(item)
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [strip_rendered_cache_fields(item) for item in value]
    return value


def history_entry_from_json(payload: Mapping[str, Any]) -> HistoryEntry:
    if not isinstance(payload, Mapping):
        raise HistoryValidationError("history entry payload must be a JSON object.")
    allowed = {"entry_id", "label", "created_at", "pinned", "semantic_snapshot", "provenance", "rendered_cache"}
    unknown = set(payload) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise HistoryValidationError(f"history entry contains unsupported fields: {names}.")
    semantic = payload.get("semantic_snapshot")
    if not isinstance(semantic, Mapping):
        raise HistoryValidationError("semantic_snapshot must be a JSON object.")
    rendered = payload.get("rendered_cache")
    if rendered is not None and not isinstance(rendered, Mapping):
        raise HistoryValidationError("rendered_cache must be a JSON object.")
    provenance = payload.get("provenance")
    if provenance is not None and not isinstance(provenance, Mapping):
        raise HistoryValidationError("provenance must be a JSON object.")
    entry_id = payload.get("entry_id")
    label = payload.get("label")
    created_at = payload.get("created_at")
    pinned = payload.get("pinned", False)
    if not isinstance(entry_id, str):
        raise HistoryValidationError("entry_id must be a string.")
    if not isinstance(label, str):
        raise HistoryValidationError("label must be a string.")
    if not isinstance(created_at, str):
        raise HistoryValidationError("created_at must be a string.")
    if not isinstance(pinned, bool):
        raise HistoryValidationError("pinned must be a boolean.")
    return HistoryEntry(
        entry_id=entry_id,
        label=label,
        created_at=created_at,
        pinned=pinned,
        semantic_snapshot=semantic,
        provenance=provenance,
        rendered_cache=rendered,
    )


def history_store_from_json(payload: Mapping[str, Any]) -> HistoryStore:
    if not isinstance(payload, Mapping):
        raise HistoryValidationError("history store payload must be a JSON object.")
    allowed = {"schema", "schema_version", "current", "entries"}
    unknown = set(payload) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise HistoryValidationError(f"history store contains unsupported fields: {names}.")
    if payload.get("schema") != HISTORY_STORE_SCHEMA:
        raise HistoryValidationError(f"history store schema must be {HISTORY_STORE_SCHEMA!r}.")
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise HistoryValidationError("history store schema_version must be 1.")
    raw_current = payload.get("current")
    if raw_current is not None and not isinstance(raw_current, Mapping):
        raise HistoryValidationError("current must be a history entry object or null.")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes, bytearray, memoryview)):
        raise HistoryValidationError("entries must be a JSON array.")
    entries: list[HistoryEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise HistoryValidationError("entries must contain history entry objects.")
        entries.append(history_entry_from_json(raw_entry))
    return HistoryStore(
        current=history_entry_from_json(raw_current) if raw_current is not None else None,
        entries=tuple(entries),
    )


def _validate_semantic_snapshot(snapshot: Mapping[str, Any]) -> None:
    unknown = set(snapshot) - _SEMANTIC_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise HistoryValidationError(f"semantic_snapshot contains unsupported fields: {names}.")
    missing = _SEMANTIC_KEYS - set(snapshot)
    if missing:
        names = ", ".join(sorted(missing))
        raise HistoryValidationError(f"semantic_snapshot is missing required fields: {names}.")
    if snapshot.get("schema") != HISTORY_ENTRY_SCHEMA:
        raise HistoryValidationError(f"semantic_snapshot.schema must be {HISTORY_ENTRY_SCHEMA!r}.")
    version = snapshot.get("snapshot_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise HistoryValidationError("semantic_snapshot.snapshot_version must be a positive integer.")
    _required_text(snapshot.get("family"), "semantic_snapshot.family")
    _required_text(snapshot.get("kind"), "semantic_snapshot.kind")
    _required_text(snapshot.get("language"), "semantic_snapshot.language")
    status = _required_text(snapshot.get("status"), "semantic_snapshot.status")
    if status not in _HISTORY_STATUSES:
        names = ", ".join(sorted(_HISTORY_STATUSES))
        raise HistoryValidationError(f"semantic_snapshot.status must be one of: {names}.")
    _validate_input_signature(snapshot.get("input_signature"))
    if not isinstance(snapshot.get("result"), Mapping):
        raise HistoryValidationError("semantic_snapshot.result must be a JSON object.")


def _validate_input_signature(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise HistoryValidationError("semantic_snapshot.input_signature must be a JSON object.")
    unknown = set(value) - _INPUT_SIGNATURE_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise HistoryValidationError(f"semantic_snapshot.input_signature contains unsupported fields: {names}.")
    missing = _INPUT_SIGNATURE_KEYS - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise HistoryValidationError(f"semantic_snapshot.input_signature is missing required fields: {names}.")
    for field_name in ("workspace_hash", "data_hash", "constants_hash"):
        _required_text(value.get(field_name), f"semantic_snapshot.input_signature.{field_name}")
    if not isinstance(value.get("formula_model"), Mapping):
        raise HistoryValidationError("semantic_snapshot.input_signature.formula_model must be a JSON object.")
    if not isinstance(value.get("options"), Mapping):
        raise HistoryValidationError("semantic_snapshot.input_signature.options must be a JSON object.")
    forbidden = {"data", "constants", "config"}
    leaked = forbidden & set(value)
    if leaked:
        names = ", ".join(sorted(leaked))
        raise HistoryValidationError(f"semantic_snapshot.input_signature contains raw workspace fields: {names}.")


def _history_provenance_from_workspace(workspace: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = workspace.get("provenance")
    if raw is None:
        return None
    provenance = normalize_workspace_provenance(raw)
    return provenance or None


def _history_status(result: Any) -> str:
    if isinstance(result, Mapping):
        status = result.get("status")
        if isinstance(status, str) and status in _HISTORY_STATUSES:
            return status
    return "failed"


def _formula_model_summary(mode_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _compact_metadata_value(mode_config[key])
        for key in sorted(_FORMULA_MODEL_KEYS & set(mode_config))
    }


def _options_signature(config: Mapping[str, Any], mode_config: Mapping[str, Any]) -> dict[str, Any]:
    raw_common = config.get("common")
    common_options: Mapping[str, Any] = raw_common if isinstance(raw_common, Mapping) else {}
    mode_options: dict[str, Any] = {key: value for key, value in mode_config.items() if key not in _FORMULA_MODEL_KEYS}
    options: dict[str, Mapping[str, Any]] = {
        "common": common_options,
        "mode": mode_options,
    }
    return {
        "hash": sha256_bytes(canonical_json(options)),
        "keys": {
            "common": sorted(options["common"]),
            "mode": sorted(options["mode"]),
        },
        "summary": {
            "common": _compact_options_summary(options["common"]),
            "mode": _compact_options_summary(options["mode"]),
        },
    }


def _compact_options_summary(options: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in options.items():
        if isinstance(value, (str, int, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = {"hash": sha256_bytes(canonical_json(value))}
    return summary


def _compact_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= 200:
            return value
        return {"prefix": value[:200], "sha256": sha256_bytes(value.encode("utf-8"))}
    if isinstance(value, (int, bool)) or value is None:
        return value
    return {"hash": sha256_bytes(canonical_json(value))}


def _plain_json(value: Any) -> Any:
    return copy.deepcopy(value)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoryValidationError(f"{field_name} must be a non-empty string.")
    return value


def _ensure_entry_fits(entry: HistoryEntry, limits: HistoryLimits, *, is_current: bool) -> None:
    if entry.semantic_size_bytes + entry.provenance_size_bytes <= limits.entry_semantic_bytes:
        return
    if is_current:
        raise HistoryPruneError("current history entry exceeds the per-entry semantic limit.")
    raise HistoryPruneError("history entry exceeds the per-entry semantic limit.")


def _store_size(current: HistoryEntry | None, entries: Sequence[HistoryEntry]) -> int:
    current_size = (
        0
        if current is None
        else current.semantic_size_bytes + current.provenance_size_bytes + current.rendered_cache_size_bytes
    )
    entries_size = sum(
        entry.semantic_size_bytes + entry.provenance_size_bytes + entry.rendered_cache_size_bytes
        for entry in entries
    )
    return current_size + entries_size


def _prune_recent_count(
    entries: Sequence[HistoryEntry],
    recent_limit: int,
    dropped_entries: list[str],
) -> list[HistoryEntry]:
    kept: list[HistoryEntry] = []
    unpinned_seen = 0
    for entry in entries:
        if entry.pinned:
            kept.append(entry)
            continue
        unpinned_seen += 1
        if unpinned_seen <= recent_limit:
            kept.append(entry)
        else:
            dropped_entries.append(entry.entry_id)
    return kept


def _oldest_unpinned_index(entries: Sequence[HistoryEntry]) -> int | None:
    for index in range(len(entries) - 1, -1, -1):
        if not entries[index].pinned:
            return index
    return None
