# Phase C Findings — Multi-stage Adversarial Pipeline

> **Pipeline (per user request 2026-04-25):**
> Stage 1 — Deep review (3 reviewers, no fixes) ✅
> Stage 2 — Code-quality 2nd-pass review (no fixes) ✅
> Stage 3 — Codex adversarial validation of Stage 1+2 findings ✅
> Stage 4 — Local counter-adversary review of codex verdicts ✅
> Stage 5 — Consolidated confirmed findings ✅
> Stage 6 — Apply fixes (only validated items) ⏳
> Stage 7 — Run /simplify cleanup ⏳

**Scope:** `git diff 6650a9a..HEAD` — collaborate.py, sse.py, streaming.py, _security_shim.py, server.py, collab.js, workers_core.py, auto_models.py, cli/main.py, batch_config.py, conftest.py + their tests.

**Unverified-fix stash:** `stash@{0}` (collaborate.py rewrite, sse.py rewrite, _security_shim.py mpmath_lock re-export). Restore selectively per Stage 5 list.

---

## Stage 5 — Confirmed actionable findings

After three independent rounds of validation, only these are real bugs / quality issues. All other Stage 1+2 raw findings were FALSE_POSITIVE or duplicates (rationale below).

| # | Final Sev | File:line | Action |
|---|-----------|-----------|--------|
| S1-01 | **HIGH** | `app_web/blueprints/collaborate.py:506` | Counter-adversary upgraded codex's MED. Non-string `participant` → `participant[:N]` raises `TypeError` post-registry-write. Bind `participant_name = str(...)[:MAX]` once, use everywhere. |
| S1-07 | **HIGH** | `app_web/blueprints/sse.py:184-200` | x/y CSV parsed as `float` truncates 60-digit input to 17 digits before `mp.mpf` materialization. Parse as STRING, materialize inside `precision_guard` block. |
| S1-02 | MED | `app_web/blueprints/collaborate.py:233,263` | `dict(...)` shallow snapshot. Use `copy.deepcopy(shared_state)` so nested-list/dict reads don't race with `set_state`. |
| S1-04 | MED | `app_web/blueprints/collaborate.py:362-364` | `json.dumps(default=str)` accepts mp.mpf / sets / custom objects, stringifies them silently, then they end up in shared_state. Validate values are JSON-native (str/int/float/bool/None/list/dict) recursively. |
| S1-05 | MED | `app_web/blueprints/collaborate.py:423,498-501` | `_sid_to_joined: dict[sid, tuple]` overwrites on multi-session join. Change to `dict[sid, set[(session_id, name)]]`; `disconnect` iterates and leaves all. |
| S1-06 | MED | `app_web/blueprints/collaborate.py:135,285-305` | `set[str]` participant collapse. Switch to `dict[name, refcount]`. |
| S1-09 | MED | `app_web/blueprints/collaborate.py:360-374` | `_validate_patch` checks top-level keys only. Nested `{"x": {"__proto__": "y"}}` slips through. Recursive validator with depth cap. |
| S1-12 | MED | `app_web/blueprints/collaborate.py:437-443` | join_token via `?token=` query arg leaks via Referer / access logs. Document as legacy fallback only; prefer `X-Collab-Token` header. |
| S1-13 | MED | `app_web/blueprints/sse.py:60` | New `_MP_SERIAL_LOCK` is a SECOND mpmath lock, distinct from `app_web.security._mpmath_lock` used by every other view. Concurrent /fit POST + SSE → race on mp.dps. Re-export the existing lock via `_security_shim` and reuse. |
| S1-14 | MED | `app_web/blueprints/collaborate.py:set_state` | Per-patch cap enforced; total `shared_state` is unbounded across patches. Add `MAX_SHARED_STATE_BYTES` check after merge. |
| S2-09 | MED | `tests/test_web_sse_fit_endpoint.py:238-265` (`test_rate_limit_gc_evicts_old_ips`) | Test passes for the wrong reason: timestamps are recent so GC evicts nothing; assertion `<= 256` is trivially true. Inject expired timestamps directly into `_RATE_HISTORY`, run GC, assert count drops. |
| S1-08 | LOW | `cli/batch_config.py:_coerce_job` | YAML is operator-controlled, but `name: "../etc/cron"` writing JSON anywhere is bad hygiene. Validate `name` against `[A-Za-z0-9][A-Za-z0-9_\-]{0,127}`. |
| S1-10 | LOW | `app_web/blueprints/sse.py:418-430` | Broad `except Exception` per model masks programmer bugs as "AllModelsFailed". Narrow to `ValueError, ArithmeticError, RuntimeError, NotImplementedError`. |
| S1-15 | LOW | `app_web/blueprints/sse.py:143` | `DATALAB_SSE_DISABLE_RATE_LIMIT` bypass silent. Log WARNING once per process when active. |
| S1-19 | LOW | `app_web/static/js/collab.js:14` | Header docstring says "no auth"; token model exists. Rewrite. |
| S2-07 | LOW | `tests/test_collab_integration.py` | GET /collab/session test asserts status only, not that response body lacks `join_token`. Add explicit assertion. |
| S2-13 | LOW | `tests/conftest.py:24` | `DATALAB_DEBUG=1` set globally — production fail-fast path can't be tested in-process. Document the limitation; suggest subprocess pattern. |

---

## Stage 5 — Confirmed FALSE_POSITIVES (no action)

| # | Original claim | Why dismissed |
|---|----------------|---------------|
| S1-03 | `_RATE_ADMISSIONS_SINCE_GC` global declared in conditional → UnboundLocalError | Python `global` is compile-time scope annotation; runtime resolves to module scope regardless of textual position. Lock-protected mutations are correct under GIL. |
| S1-11 | Rate limit `< cutoff` is off-by-one | `[cutoff, now]` half-open interval is standard sliding-window semantics. Exact equality on monotonic floats never happens in practice. |
| S1-16 | No explicit `leave` event → 5-30s heartbeat delay | `socket.disconnect()` sends transport disconnect packet immediately, triggering server `on_disconnect`. No delay. |
| S1-17 | Participant XSS surface | No template / JS file in repo writes participant name via `innerHTML`. JSON emit only. |
| S1-18 | `import time` per-call hot path | `sys.modules` lookup is O(1) cached; cost is negligible compared to socket round-trip. |
| S1-20 | `exponential` and `exp_combo` both → M7 | Deliberate alias (M7 IS the exponential combo model; `exp_basis` → M7B for the basis variant). |
| S2-04 | Nested `precision_guard` corrupts mp.dps | `precision_guard` is save-restore via `@contextmanager`; nested calls are idempotent (inner saves outer's value, sets same value, restores). |
| S2-08 | `_aic` double-call inefficiency | Trivial overhead; not worth the refactor risk. |
| S2-10 | SSE deadline doesn't charge lock-wait | Deadline computed BEFORE lock acquisition; post-lock check correctly captures total elapsed time. |
| S2-11 | `exp_combo` vs `exp_basis` comment ambiguity | Code is unambiguous; cosmetic only. |

---

## Stage 5 — Skip-reasoning for partial / overstated items

- S1-06 was rated HIGH by codex; counter-adversary kept MED. Refcount fix captures the intent without needing per-sid identity tracking (which would be over-engineering for a single-process collab system).
- S1-08 is operator-controlled (YAML auth boundary), but defense-in-depth on filenames costs nothing.
- S2-13 is a test infrastructure issue, not a production bug; documenting is enough.

---

## Stage 6 plan

Selectively restore from `stash@{0}` (where the rewrite already implements the fix correctly), or apply targeted edits where the stash overshot the validated finding:

1. `collaborate.py` — restore most of stashed rewrite EXCEPT:
   - HTML-escape participants (S1-17 was FALSE_POSITIVE) → drop the `html.escape` call from `_sanitize_participant_name`
   - `_monotonic` module-level `import time` move (S1-18 was FALSE_POSITIVE) → keep but harmless; leave the existing in-function import to minimize diff
2. `sse.py` — restore stashed rewrite EXCEPT:
   - Rate-limit `<= cutoff` change (S1-11 was FALSE_POSITIVE) → revert to `< cutoff`
3. `_security_shim.py` — restore the `mpmath_lock` re-export (needed for S1-13)
4. `cli/batch_config.py` — apply `name` regex validator (S1-08, NEW edit)
5. `app_web/static/js/collab.js` — update header docstring (S1-19, NEW edit)
6. `tests/test_web_sse_fit_endpoint.py` — fix GC test (S2-09, NEW edit)
7. `tests/test_collab_integration.py` — add `join_token` absence assertion (S2-07, NEW edit)
8. `tests/conftest.py` — add documentation comment (S2-13, NEW edit)
9. New tests: nested-`__proto__` rejection (S1-09), `set_state` size cap (S1-14), `mp.mpf` precision preservation through SSE (S1-07).
