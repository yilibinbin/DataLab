from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any, cast

import pytest

from datalab_core.history import (
    DEFAULT_ENTRY_SEMANTIC_BYTES,
    DEFAULT_PINNED_ENTRIES,
    DEFAULT_RECENT_ENTRIES,
    DEFAULT_TOTAL_SEMANTIC_BYTES,
    HISTORY_ENTRY_SCHEMA,
    HISTORY_SCHEMA_VERSION,
    HistoryEntry,
    HistoryLimits,
    HistoryPruneError,
    HistoryStore,
    HistoryValidationError,
    build_history_semantic_snapshot,
    canonical_history_bytes,
    history_entry_from_json,
    history_store_from_json,
)
from shared.workspace_schema import canonical_json, compute_workspace_hash, sha256_bytes, workspace_hash_payload


def _workspace() -> dict[str, Any]:
    return {
        "title": "Ignored",
        "current_mode": "fitting",
        "language": "en",
        "ui": {"main_tab": "results"},
        "data": {
            "source_kind": "manual_table",
            "canonical_table": {"headers": ["x", "y"], "rows": [["1", "2"], ["2", "4"]]},
            "decoded_text": "x y\n1 2\n2 4",
        },
        "constants": {"enabled": False},
        "config": {
            "common": {"precision_digits": 50, "display_digits": 8, "display_scientific": False},
            "fitting": {"model": "custom", "expression": "a*x"},
        },
        "result_snapshot": {
            "status": "success",
            "summary": {"slope": "2"},
            "markdown": "rendered",
            "latex_source": "\\begin{table}\\end{table}",
            "plots": [{"path": "attachments/plots/plot.png"}],
            "rendered_cache_fields": ["markdown", "latex_source", "plots"],
        },
    }


def _entry(
    entry_id: str,
    *,
    workspace: dict[str, Any] | None = None,
    pinned: bool = False,
    rendered_cache: dict[str, object] | None = None,
) -> HistoryEntry:
    return HistoryEntry.from_workspace_snapshot(
        entry_id=entry_id,
        label=entry_id,
        created_at=f"2026-06-20T00:00:{entry_id[-2:].zfill(2)}Z",
        workspace=workspace or _workspace(),
        family="fitting",
        kind="fit_single",
        pinned=pinned,
        rendered_cache=rendered_cache,
    )


def _unique_entry(entry_id: str, value: str, *, pinned: bool = False) -> HistoryEntry:
    workspace = _workspace()
    workspace["data"]["canonical_table"]["rows"].append([value, value])
    workspace["data"]["decoded_text"] = f"x y\n1 2\n{value} {value}"
    return _entry(entry_id, workspace=workspace, pinned=pinned)


def test_history_defaults_match_slice_limits() -> None:
    assert DEFAULT_RECENT_ENTRIES == 20
    assert DEFAULT_PINNED_ENTRIES == 5
    assert DEFAULT_TOTAL_SEMANTIC_BYTES == 25 * 1024 * 1024
    assert DEFAULT_ENTRY_SEMANTIC_BYTES == 2 * 1024 * 1024


def test_history_entry_rejects_json_floats_in_semantic_data() -> None:
    workspace = _workspace()
    workspace["config"]["fitting"]["initial"] = 1.5

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        _entry("e01", workspace=workspace)

    payload = _entry("e02").to_json()
    payload["semantic_snapshot"]["result"]["value"] = 1.0
    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        history_entry_from_json(payload)


def test_history_entry_semantic_snapshot_is_deeply_immutable_after_construction() -> None:
    semantic = _entry("e01").to_json()["semantic_snapshot"]
    entry = HistoryEntry(
        entry_id="e02",
        label="e02",
        created_at="2026-06-20T00:00:02Z",
        semantic_snapshot=semantic,
    )
    before = entry.to_json()

    semantic["status"] = "failed"
    semantic["input_signature"]["workspace_hash"] = "sha256:mutated"
    semantic["result"]["summary"]["slope"] = "999"

    assert entry.to_json() == before

    with pytest.raises(TypeError):
        cast(Any, entry.semantic_snapshot)["status"] = "failed"
    with pytest.raises(TypeError):
        entry.semantic_snapshot["input_signature"]["workspace_hash"] = "sha256:mutated"
    with pytest.raises(TypeError):
        entry.semantic_snapshot["result"]["summary"]["slope"] = "999"

    assert entry.to_json() == before


def test_history_entry_semantic_snapshot_cannot_inject_float_after_construction() -> None:
    entry = _entry("e01")
    before = entry.to_json()

    with pytest.raises(TypeError):
        cast(Any, entry.semantic_snapshot)["result"]["value"] = 1.0
    with pytest.raises(TypeError):
        entry.semantic_snapshot["result"]["summary"]["slope"] = 1.0

    assert entry.to_json() == before
    assert entry.canonical_bytes == canonical_history_bytes(before["semantic_snapshot"])


def test_history_entry_rendered_cache_is_deeply_immutable_after_construction() -> None:
    rendered_cache: dict[str, object] = {
        "markdown": "before",
        "plots": [{"path": "attachments/plots/plot.png"}],
    }
    entry = _entry("e01", rendered_cache=rendered_cache)
    before = entry.to_json()

    rendered_cache["markdown"] = "after"
    rendered_cache["plots"] = [{"path": "attachments/plots/changed.png"}]

    assert entry.to_json() == before
    assert entry.rendered_cache is not None
    with pytest.raises(TypeError):
        cast(Any, entry.rendered_cache)["markdown"] = "after"
    with pytest.raises(TypeError):
        entry.rendered_cache["plots"][0]["path"] = "attachments/plots/changed.png"

    assert entry.to_json() == before


def test_history_hash_is_stable_across_key_order_display_options_and_rendered_fields() -> None:
    left = _workspace()
    right = {
        "result_snapshot": {
            "plots": [{"path": "attachments/plots/changed.png"}],
            "latex_source": "changed",
            "markdown": "changed",
            "summary": {"slope": "2"},
            "status": "success",
        },
        "ui": {"main_tab": "input", "selected_tab": "plot"},
        "language": "en",
        "title": "Changed",
        "config": {
            "fitting": {"expression": "a*x", "model": "custom"},
            "common": {"display_scientific": True, "display_digits": 12, "precision_digits": 50},
        },
        "constants": {"enabled": False},
        "data": {
            "decoded_text": "x y\n1 2\n2 4",
            "canonical_table": {"rows": [["1", "2"], ["2", "4"]], "headers": ["x", "y"]},
            "source_kind": "manual_table",
        },
        "current_mode": "fitting",
    }

    assert _entry("e01", workspace=left).canonical_bytes == _entry("e02", workspace=right).canonical_bytes


def test_history_semantic_snapshot_requires_and_preserves_p33_fields() -> None:
    entry = _entry("e01")
    semantic = entry.semantic_snapshot
    signature = semantic["input_signature"]

    assert semantic["language"] == "en"
    assert semantic["status"] == "success"
    assert set(signature) == {"current_mode", "workspace_hash", "data_hash", "constants_hash", "formula_model", "options"}
    assert signature["formula_model"] == {"expression": "a*x", "model": "custom"}
    assert "calculation" not in semantic
    assert "data" not in signature
    assert "constants" not in signature
    assert "config" not in signature
    assert history_entry_from_json(entry.to_json()).to_json() == entry.to_json()

    for field_name in ("language", "status", "input_signature"):
        payload = entry.to_json()
        del payload["semantic_snapshot"][field_name]
        with pytest.raises(HistoryValidationError, match=field_name):
            history_entry_from_json(payload)


def test_history_entry_rejects_status_outside_spec_enum() -> None:
    payload = _entry("e01").to_json()
    payload["semantic_snapshot"]["status"] = "queued"

    with pytest.raises(HistoryValidationError, match="semantic_snapshot.status"):
        history_entry_from_json(payload)


def test_history_builder_missing_status_falls_back_to_allowed_failed_status() -> None:
    workspace = _workspace()
    workspace["result_snapshot"] = {"summary": {"slope": "2"}}

    entry = _entry("e01", workspace=workspace)

    assert entry.semantic_snapshot["status"] == "failed"


def test_history_semantic_snapshot_preserves_explicit_empty_result_snapshot() -> None:
    workspace = _workspace()
    workspace["result_snapshot"] = {"status": "success", "summary": {"slope": "2"}}

    semantic = build_history_semantic_snapshot(
        workspace=workspace,
        family="fitting",
        kind="fit_single",
        result_snapshot={},
    )

    assert semantic["result"] == {}
    assert semantic["status"] == "failed"


def test_history_semantic_snapshot_rejects_non_mapping_result_snapshot() -> None:
    with pytest.raises(HistoryValidationError, match="semantic_snapshot.result"):
        build_history_semantic_snapshot(
            workspace=_workspace(),
            family="fitting",
            kind="fit_single",
            result_snapshot=cast(Any, []),
        )


def test_history_input_signature_reuses_workspace_hash_contract_without_raw_blobs() -> None:
    baseline = _workspace()
    display_changed = copy.deepcopy(baseline)
    display_changed["config"]["common"]["display_digits"] = 12
    display_changed["config"]["common"]["display_scientific"] = True

    baseline_entry = _entry("e01", workspace=baseline)
    changed_entry = _entry("e02", workspace=display_changed)
    signature = baseline_entry.semantic_snapshot["input_signature"]
    shared_payload = workspace_hash_payload(baseline)

    assert signature["workspace_hash"] == compute_workspace_hash(baseline)
    assert signature["data_hash"] == sha256_bytes(canonical_json(shared_payload["data"]))
    assert signature["constants_hash"] == sha256_bytes(canonical_json(shared_payload["constants"]))
    assert baseline_entry.semantic_snapshot["input_signature"] == changed_entry.semantic_snapshot["input_signature"]
    assert baseline_entry.canonical_bytes == changed_entry.canonical_bytes
    assert "decoded_text" not in signature
    assert "canonical_table" not in signature


def _change_data(workspace: dict[str, Any]) -> None:
    workspace["data"]["canonical_table"]["rows"].append(["3", "6"])


def _change_constants(workspace: dict[str, Any]) -> None:
    workspace["constants"] = {"enabled": True, "values": {"c": "3"}}


def _change_config(workspace: dict[str, Any]) -> None:
    workspace["config"]["fitting"]["expression"] = "a*x+b"


@pytest.mark.parametrize(
    "mutate",
    [_change_data, _change_constants, _change_config],
)
def test_history_hash_changes_for_calculation_affecting_inputs(mutate: Callable[[dict[str, Any]], None]) -> None:
    baseline = _workspace()
    changed = copy.deepcopy(baseline)
    mutate(changed)

    assert _entry("e01", workspace=baseline).semantic_hash != _entry("e02", workspace=changed).semantic_hash


def test_history_canonical_bytes_include_schema_snapshot_version_family_and_kind() -> None:
    baseline = _entry("e01")
    changed_family = HistoryEntry.from_workspace_snapshot(
        entry_id="e02",
        label="e02",
        created_at="2026-06-20T00:00:02Z",
        workspace=_workspace(),
        family="statistics",
        kind="fit_single",
    )
    changed_kind = HistoryEntry.from_workspace_snapshot(
        entry_id="e03",
        label="e03",
        created_at="2026-06-20T00:00:03Z",
        workspace=_workspace(),
        family="fitting",
        kind="fit_comparison",
    )
    changed_version = HistoryEntry.from_workspace_snapshot(
        entry_id="e04",
        label="e04",
        created_at="2026-06-20T00:00:04Z",
        workspace=_workspace(),
        family="fitting",
        kind="fit_single",
        snapshot_version=2,
    )

    assert baseline.semantic_snapshot["schema"] == HISTORY_ENTRY_SCHEMA
    assert baseline.semantic_snapshot["snapshot_version"] == HISTORY_SCHEMA_VERSION
    assert baseline.semantic_hash != changed_family.semantic_hash
    assert baseline.semantic_hash != changed_kind.semantic_hash
    assert baseline.semantic_hash != changed_version.semantic_hash


def test_history_dedup_compares_canonical_bytes_when_hashes_collide(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _entry("e01")
    changed_workspace = copy.deepcopy(_workspace())
    changed_workspace["data"]["canonical_table"]["rows"].append(["3", "6"])
    second = _entry("e02", workspace=changed_workspace)

    monkeypatch.setattr("datalab_core.history.sha256_bytes", lambda data: "sha256:forced")

    store = HistoryStore(entries=(first, second, first)).deduplicated()

    assert [entry.entry_id for entry in store.entries] == ["e01", "e02"]


def test_history_pruning_drops_rendered_caches_before_semantic_entries() -> None:
    current = _entry("e00")
    cached_workspace = _workspace()
    cached_workspace["data"]["canonical_table"]["rows"].append(["3", "6"])
    cached = _entry("e01", workspace=cached_workspace, rendered_cache={"markdown": "x" * 200})
    plain = _unique_entry("e02", "4")
    semantic_total = current.semantic_size_bytes + cached.semantic_size_bytes + plain.semantic_size_bytes
    limit = HistoryLimits(total_semantic_bytes=semantic_total + 10)

    pruned, report = HistoryStore(current=current, entries=(cached, plain)).prune_for_save(limit)

    assert report.dropped_rendered_cache_entry_ids == ("e01",)
    assert report.dropped_entry_ids == ()
    assert pruned.entries[0].rendered_cache is None
    assert [entry.entry_id for entry in pruned.entries] == ["e01", "e02"]


def test_history_pruning_enforces_recent_limit_while_preserving_pinned_entries() -> None:
    pinned = tuple(_unique_entry(f"p0{index}", f"p{index}", pinned=True) for index in range(5))
    unpinned = tuple(_unique_entry(f"e0{index}", f"e{index}") for index in range(4))
    store = HistoryStore(entries=(*pinned, *unpinned))
    limits = HistoryLimits(recent_entries=2, pinned_entries=5)

    pruned, report = store.prune_for_save(limits)

    assert [entry.entry_id for entry in pruned.entries] == [
        "p00",
        "p01",
        "p02",
        "p03",
        "p04",
        "e00",
        "e01",
    ]
    assert report.dropped_entry_ids == ("e02", "e03")


def test_history_pruning_rejects_too_many_pinned_entries_loudly() -> None:
    store = HistoryStore(entries=tuple(_unique_entry(f"p0{index}", f"p{index}", pinned=True) for index in range(6)))

    with pytest.raises(HistoryPruneError, match="pinned"):
        store.prune_for_save(HistoryLimits(pinned_entries=5))


def test_history_pruning_drops_oversized_noncurrent_entries_but_preserves_current() -> None:
    oversized_workspace = _workspace()
    oversized_workspace["result_snapshot"] = {"status": "success", "semantic_blob": "x" * 200}
    current = _entry("e00")
    oversized = _entry("e01", workspace=oversized_workspace)
    limits = HistoryLimits(entry_semantic_bytes=current.semantic_size_bytes + 20)

    pruned, report = HistoryStore(current=current, entries=(oversized,)).prune_for_save(limits)

    assert pruned.entries == ()
    assert report.dropped_entry_ids == ("e01",)

    with pytest.raises(HistoryPruneError, match="current"):
        HistoryStore(current=oversized).prune_for_save(limits)


def test_history_pruning_rejects_oversized_pinned_entry_loudly() -> None:
    oversized_workspace = _workspace()
    oversized_workspace["result_snapshot"] = {"status": "success", "semantic_blob": "x" * 200}
    current = _entry("e00")
    oversized = _entry("e01", workspace=oversized_workspace, pinned=True)
    limits = HistoryLimits(entry_semantic_bytes=current.semantic_size_bytes + 20)

    with pytest.raises(HistoryPruneError, match="pinned"):
        HistoryStore(current=current, entries=(oversized,)).prune_for_save(limits)


def test_history_total_limit_prunes_oldest_unpinned_entries_without_dropping_current() -> None:
    current = _entry("e00")
    newest = _unique_entry("e01", "3")
    oldest = _unique_entry("e02", "4")
    limit = current.semantic_size_bytes + newest.semantic_size_bytes + 5

    pruned, report = HistoryStore(current=current, entries=(newest, oldest)).prune_for_save(
        HistoryLimits(total_semantic_bytes=limit),
    )

    assert [entry.entry_id for entry in pruned.entries] == ["e01"]
    assert report.dropped_entry_ids == ("e02",)

    with pytest.raises(HistoryPruneError, match="current"):
        HistoryStore(current=current).prune_for_save(
            HistoryLimits(total_semantic_bytes=current.semantic_size_bytes - 1),
        )


def test_history_json_round_trip_fails_closed_on_malformed_entries() -> None:
    store = HistoryStore(current=_entry("e00"), entries=(_entry("e01"),))
    payload = store.to_json()

    assert history_store_from_json(payload).to_json() == payload

    bad_store = copy.deepcopy(payload)
    bad_store["extra"] = True
    with pytest.raises(HistoryValidationError, match="unsupported"):
        history_store_from_json(bad_store)

    bad_entry = copy.deepcopy(payload["entries"][0])
    bad_entry["semantic_snapshot"]["schema"] = "bad"
    with pytest.raises(HistoryValidationError, match="schema"):
        history_entry_from_json(bad_entry)


def test_canonical_history_bytes_are_utf8_sorted_and_compact() -> None:
    semantic = _entry("e01").semantic_snapshot
    encoded = canonical_history_bytes(semantic)

    assert encoded == canonical_history_bytes(copy.deepcopy(semantic))
    assert b'"input_signature":' in encoded
    assert b": " not in encoded
    assert encoded.decode("utf-8")
