"""Regression tests for Phase C confirmed findings.

Each test pins a specific bug found by the multi-stage review
pipeline (Stage 1 deep review → Stage 2 quality review → Stage 3
codex adversarial validation → Stage 4 local counter-adversary).
Only findings that survived all four stages are pinned here.

References to S1-NN / S2-NN match `findings.md` in the repo root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app_web.blueprints.collaborate import ErrorCode


# ---------------------------------------------------------------
# S1-01 — non-string ``participant`` must not crash on_join
# ---------------------------------------------------------------
def test_sanitize_participant_name_handles_non_string_input():
    """Codex/counter-adversary HIGH: a client sending
    ``participant: 12345`` (integer) used to crash the SocketIO
    handler with TypeError on ``participant[:N]``. The fix coerces
    once via ``_sanitize_participant_name`` before any slice."""
    from app_web.blueprints.collaborate import (
        MAX_PARTICIPANT_NAME, _sanitize_participant_name,
    )
    assert _sanitize_participant_name(12345) == "12345"
    assert _sanitize_participant_name(None) == "anonymous"
    assert _sanitize_participant_name([1, 2, 3]) == "[1, 2, 3]"
    assert _sanitize_participant_name("") == "anonymous"
    assert _sanitize_participant_name("   ") == "anonymous"
    long_name = "a" * (MAX_PARTICIPANT_NAME + 100)
    assert len(_sanitize_participant_name(long_name)) == MAX_PARTICIPANT_NAME


# ---------------------------------------------------------------
# S1-02 — snapshot deepcopy
# ---------------------------------------------------------------
def test_session_snapshot_is_deepcopied():
    """Without deepcopy, a caller iterating nested dicts/lists
    in shared_state would race with a concurrent set_state that
    mutates the inner object."""
    from app_web.blueprints.collaborate import SessionRegistry

    reg = SessionRegistry()
    s = reg.create()
    reg.set_state(s.session_id, {"history": [1, 2, 3]}, s.join_token)

    snapshot = reg.get(s.session_id)
    assert snapshot is not None

    # Mutate the snapshot's nested list — the live session must NOT see it.
    snapshot.shared_state["history"].append("INJECTED")
    live = reg.get(s.session_id)
    assert live is not None
    assert live.shared_state["history"] == [1, 2, 3], (
        "live state was mutated through the snapshot — deep copy missing"
    )


# ---------------------------------------------------------------
# S1-04 / S1-09 — recursive _validate_patch rejects mp.mpf and
# nested __proto__
# ---------------------------------------------------------------
def test_validate_patch_rejects_mpmath_value_at_top_level():
    import mpmath as mp

    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({"x": mp.mpf("1.5")})
    assert not ok, "mp.mpf must NOT pass _validate_patch (default=str hole)"
    assert code == ErrorCode.PATCH_UNSUPPORTED_TYPE


def test_validate_patch_rejects_mpmath_value_in_nested_list():
    import mpmath as mp

    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({"items": [1, mp.mpf("3.14"), 2]})
    assert not ok
    assert code == ErrorCode.PATCH_UNSUPPORTED_TYPE


def test_validate_patch_rejects_nested_dunder_keys():
    """Pre-fix the validator only checked top-level keys; a payload
    like ``{"x": {"__proto__": "y"}}`` slipped through."""
    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({"outer": {"__proto__": "evil"}})
    assert not ok
    assert code == ErrorCode.PATCH_INVALID_KEY


def test_validate_patch_rejects_deeply_nested_constructor():
    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({
        "a": {"b": {"c": {"constructor": "evil"}}}
    })
    assert not ok
    assert code == ErrorCode.PATCH_INVALID_KEY


def test_validate_patch_rejects_non_finite_floats():
    """NaN and Inf are not JSON-spec compliant; some clients reject
    the entire frame, others silently coerce to null. Reject both."""
    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({"x": float("nan")})
    assert not ok
    assert code == ErrorCode.PATCH_NON_FINITE_NUMBER

    ok, code = _validate_patch({"x": float("inf")})
    assert not ok
    assert code == ErrorCode.PATCH_NON_FINITE_NUMBER


def test_validate_patch_accepts_legitimate_nested_state():
    """Sanity: a realistic UI-state patch with nested dicts and
    lists must still pass."""
    from app_web.blueprints.collaborate import _validate_patch

    ok, code = _validate_patch({
        "dpi": 200,
        "model": "linear",
        "settings": {"log_scale": "x", "show_residuals": True},
        "history": [{"name": "fit1", "aic": 12.5}, {"name": "fit2", "aic": 8.1}],
    })
    assert ok, f"legitimate patch rejected: {code}"


# ---------------------------------------------------------------
# S1-05 — _sid_to_joined supports multi-session per sid
# ---------------------------------------------------------------
def test_session_registry_multi_session_per_sid_via_join_set():
    """Test the lower-level invariant: a SessionRegistry can hold
    independent participant lists for the same display name across
    multiple sessions; one socket joining both must not collapse."""
    from app_web.blueprints.collaborate import SessionRegistry

    reg = SessionRegistry()
    s1 = reg.create()
    s2 = reg.create()
    reg.join(s1.session_id, "alice", s1.join_token)
    reg.join(s2.session_id, "alice", s2.join_token)

    snap1 = reg.get(s1.session_id)
    snap2 = reg.get(s2.session_id)
    assert snap1 is not None and snap2 is not None
    assert "alice" in snap1.participants
    assert "alice" in snap2.participants
    # Leaving s1 must not evict alice from s2.
    reg.leave(s1.session_id, "alice")
    assert reg.get(s1.session_id) is None  # session auto-deleted (empty)
    snap2_after = reg.get(s2.session_id)
    assert snap2_after is not None
    assert "alice" in snap2_after.participants


# ---------------------------------------------------------------
# S1-06 — duplicate-name participants count separately
# ---------------------------------------------------------------
def test_duplicate_participant_names_counted_separately():
    """Two sockets named "alice" each get their own slot; one
    disconnect must not remove the still-connected one."""
    from app_web.blueprints.collaborate import SessionRegistry

    reg = SessionRegistry()
    s = reg.create()
    tok = s.join_token
    reg.join(s.session_id, "alice", tok)
    reg.join(s.session_id, "alice", tok)
    snap = reg.get(s.session_id)
    assert snap is not None
    assert snap.participants.get("alice") == 2

    # First disconnect drops count to 1 — alice still listed.
    reg.leave(s.session_id, "alice")
    snap = reg.get(s.session_id)
    assert snap is not None
    assert snap.participants.get("alice") == 1

    # Second disconnect drops to 0 — name removed, session auto-deletes.
    reg.leave(s.session_id, "alice")
    assert reg.get(s.session_id) is None


# ---------------------------------------------------------------
# S1-07 — SSE x/y string deferral preserves mp.mpf precision
# ---------------------------------------------------------------
def test_sse_string_csv_preserves_high_precision_input():
    """Pre-fix, the SSE endpoint cast x/y to ``float`` immediately,
    truncating 60-digit decimals to 17. Now they're kept as strings
    and converted to mp.mpf inside precision_guard."""
    from app_web.blueprints.sse import (
        _materialise_mpf_pairs, _parse_numeric_csv_strings,
    )
    from shared.precision import precision_guard

    # 30 significant digits — far more than a double can hold.
    high_precision_input = (
        "1.123456789012345678901234567890,"
        "2.987654321098765432109876543210"
    )
    cells = _parse_numeric_csv_strings(high_precision_input, "x")
    assert cells == [
        "1.123456789012345678901234567890",
        "2.987654321098765432109876543210",
    ], "string preservation failed at parse time"

    with precision_guard(50):
        xs, _ = _materialise_mpf_pairs(cells, cells, precision=50)

    # Convert back to string at the same precision and verify the
    # tail digits survive — a double round-trip would have lost
    # them at digit ~17.
    import mpmath as mp
    with precision_guard(50):
        round_tripped = mp.nstr(xs[0], 30)
    # mp.nstr emits in the form "1.12345678901234567890123456789",
    # length and key digits must match the original.
    assert "1.12345678901234567890" in round_tripped, (
        f"high-precision input lost: {round_tripped!r}"
    )


def test_sse_csv_parser_rejects_nan_and_infinity():
    """Defence-in-depth: even though _parse_numeric_csv_strings
    keeps the original string form, it still rejects NaN/Inf so
    a downstream mp.mpf conversion can't accidentally accept them."""
    from app_web.blueprints.sse import _parse_numeric_csv_strings

    with pytest.raises(ValueError, match="non-finite"):
        _parse_numeric_csv_strings("1,nan,3", "x")
    with pytest.raises(ValueError, match="non-finite"):
        _parse_numeric_csv_strings("inf,2,3", "x")
    with pytest.raises(ValueError, match="non-numeric"):
        _parse_numeric_csv_strings("1,2,not-a-number", "x")


# ---------------------------------------------------------------
# S1-08 — CLI batch job name basename regex
# ---------------------------------------------------------------
def test_batch_config_rejects_path_traversal_in_name(tmp_path: Path):
    """An operator-controlled YAML containing
    ``name: "../etc/cron"`` would otherwise write the JSON to
    arbitrary paths. The new regex stops it at parse time."""
    from cli.batch_config import load_batch_config

    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n3,4\n", encoding="utf-8")
    yaml_path = tmp_path / "batch.yml"
    yaml_path.write_text(
        f"""
jobs:
  - name: "../etc/cron.d/evil"
    operation: fit
    data_path: {data_path}
    output_dir: {tmp_path}
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safe basename"):
        load_batch_config(yaml_path)


def test_batch_config_rejects_slash_in_name(tmp_path: Path):
    from cli.batch_config import load_batch_config

    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n", encoding="utf-8")
    yaml_path = tmp_path / "batch.yml"
    yaml_path.write_text(
        f"""
jobs:
  - name: "outer/inner"
    operation: fit
    data_path: {data_path}
    output_dir: {tmp_path}
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safe basename"):
        load_batch_config(yaml_path)


def test_batch_config_rejects_leading_dot_in_name(tmp_path: Path):
    """``.evil`` would create a hidden file in output_dir; while
    not a traversal, it surprises operators inspecting the dir."""
    from cli.batch_config import load_batch_config

    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n", encoding="utf-8")
    yaml_path = tmp_path / "batch.yml"
    yaml_path.write_text(
        f"""
jobs:
  - name: ".secret"
    operation: fit
    data_path: {data_path}
    output_dir: {tmp_path}
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safe basename"):
        load_batch_config(yaml_path)


def test_batch_config_accepts_normal_basename(tmp_path: Path):
    """Sanity: typical names still work."""
    from cli.batch_config import load_batch_config

    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n", encoding="utf-8")
    yaml_path = tmp_path / "batch.yml"
    yaml_path.write_text(
        f"""
jobs:
  - name: linear-fit_2
    operation: fit
    data_path: {data_path}
    output_dir: {tmp_path}
""".strip(),
        encoding="utf-8",
    )
    config = load_batch_config(yaml_path)
    assert config.jobs[0].name == "linear-fit_2"


# ---------------------------------------------------------------
# S1-13 — SSE uses the SAME mpmath lock as the rest of the web app
# ---------------------------------------------------------------
def test_sse_mp_serial_lock_is_app_wide_mpmath_lock():
    """SSE must serialise mp.dps writes against the existing
    ``app_web.security._mpmath_lock`` used by every
    @mpmath_synchronized view, not introduce a SECOND lock that
    races with /fit POSTs on mp.dps."""
    from app_web._security_shim import mpmath_lock as shim_lock
    from app_web.blueprints import sse as sse_mod

    assert sse_mod._MP_SERIAL_LOCK is shim_lock, (
        "SSE introduced a separate mpmath lock; concurrent /fit POST + "
        "SSE can race on mp.dps. Re-use _security_shim.mpmath_lock."
    )


# ---------------------------------------------------------------
# S1-14 — set_state enforces MAX_SHARED_STATE_BYTES
# ---------------------------------------------------------------
def test_set_state_rejects_oversized_merged_state():
    """Per-patch cap exists, but successive patches could grow
    shared_state without bound. The total-state cap stops that."""
    from app_web.blueprints.collaborate import (
        MAX_PATCH_BYTES, MAX_SHARED_STATE_BYTES, SessionRegistry,
    )

    reg = SessionRegistry()
    s = reg.create()
    tok = s.join_token

    # Each patch is just under the per-patch cap (50 KiB).
    half_full = "x" * (MAX_PATCH_BYTES - 200)
    # Up to ~10 patches fit within the 512 KiB total cap; after that
    # set_state must return None to signal the cap was hit.
    n_total_chunks = (MAX_SHARED_STATE_BYTES // MAX_PATCH_BYTES) + 5
    accepted = 0
    rejected = 0
    for i in range(n_total_chunks):
        result = reg.set_state(s.session_id, {f"k{i}": half_full}, tok)
        if result is not None:
            accepted += 1
        else:
            rejected += 1
    # We must have hit the cap before all chunks went through.
    assert rejected > 0, (
        "MAX_SHARED_STATE_BYTES cap not enforced: every patch accepted"
    )
    # And we must have accepted at least a few chunks (cap not too tight).
    assert accepted > 0


# ---------------------------------------------------------------
# S1-15 — DATALAB_SSE_DISABLE_RATE_LIMIT logs a warning once
# ---------------------------------------------------------------
def test_rate_limit_bypass_env_var_emits_warning(monkeypatch, caplog):
    """A production deploy with this env var accidentally set
    silently disables the limiter; a single WARNING surfaces it."""
    import logging

    from app_web.blueprints import sse as sse_mod

    # Reset the lru_cache so the warning will fire in this test.
    sse_mod._warn_rate_bypass_once.cache_clear()
    monkeypatch.setenv("DATALAB_SSE_DISABLE_RATE_LIMIT", "1")

    with caplog.at_level(logging.WARNING, logger="app_web.blueprints.sse"):
        result = sse_mod._check_rate_limit("10.0.0.1")

    assert result is True, "bypass env var must return True"
    warns = [r for r in caplog.records if "DISABLE_RATE_LIMIT" in r.message]
    assert warns, "expected a single WARNING log on first bypass"

    # Subsequent calls must NOT re-warn (once-flag).
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app_web.blueprints.sse"):
        sse_mod._check_rate_limit("10.0.0.1")
    second_warns = [r for r in caplog.records if "DISABLE_RATE_LIMIT" in r.message]
    assert not second_warns, "warning should fire ONCE per process, not on every call"
