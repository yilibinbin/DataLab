# CODE_REVIEW_R10 — Multi-Agent Full-Repo Audit

**Date**: 2026-04-24
**Branch**: `review/r10-full-audit-and-fixes`
**Baseline**: `efd1cea` (R9 ultradeep review), 162 tests passing in 11.85s.
**Reviewers**:
1. `code-reviewer` agent — code quality, maintainability, Python idioms (Stage 1)
2. `security-reviewer` agent — Priority 1 attack surfaces + R9 regression check (Stage 2a)
3. `architect` agent — numerical correctness of scientific core (Stage 2b)
4. Human-led adversarial verification — every CRITICAL/HIGH claim verified against source (Stage 3). Codex subagent attempted but refused due to plan-mode confusion; its role was filled by direct reproduction of findings below.

---

## Executive summary

| Severity | Count |
|---|---|
| **CRITICAL** | **5** |
| **HIGH** | **10** |
| MEDIUM | 11 |
| LOW | 5 |
| **Total** | **31** |

**Verdict: BLOCK** until the five CRITICAL issues are fixed.

**R9 regression status**: One R9 CRITICAL was **not fixed** and remains live (`validate_latex_content` dead). Three R9 CRITICAL fixes verified. See §R9 audit below.

**Scope of this PR**: Fix all 5 CRITICAL + all 10 HIGH with regression tests. MEDIUM/LOW deferred to `findings.md` backlog.

---

## CRITICAL findings

### C1 — `validate_latex_content` dead code (R9 regression)
- **Severity**: CRITICAL (defense-in-depth gap + R9 regression)
- **File**: `app_web/latex_security.py:207` (definition). Call sites: **none in production**. Invocations limited to `app_web/test_security.py` and `tests/test_latex_security_include_traversal.py`.
- **Verified call sites of `compile_latex_safe`**: `app_web/logic/{extrapolation.py:184, error_propagation.py:197, fitting.py:949, statistics.py:235}`. None of them first validate the content.
- **Why it matters**: `-no-shell-escape` is the primary defense (correctly enforced, R9 C1 fixed). `validate_latex_content` is documented as defense in depth — blocks `\write18`, `\openout`, and path-traversal `\input{../…}` before the LaTeX process is spawned. It is dead; tests alone cover it.
- **Fix**: In `app_web/latex_security.py:compile_latex_safe`, call `validate_latex_content(tex_text)` at the top; on `False`, append warnings and return `None` without running the subprocess.
- **Regression test**: `tests/test_latex_security_content_is_called.py` — patch `subprocess.run` and assert it is NOT called for a tex input containing `\write18{id}`; warnings list contains the bilingual `" / "`-separated warning.

### C2 — Hardcoded fallback `SECRET_KEY = "datalab-web-dev"` in production path
- **Severity**: CRITICAL (session/CSRF forgery)
- **File**: `app_web/server.py:32`. Warning emitted at lines 73–80 does not prevent startup.
- **Why it matters**: If `DATALAB_WEB_SECRET` is unset in production (easy operator mistake), sessions and CSRF tokens are HMAC-signed with a publicly-known, git-history-visible string. Session forgery → CSRF bypass → state-changing requests forged.
- **Sibling reference**: `app_web/server_security_patch.py:64-69` already has the correct pattern (`secrets.token_hex(32)`) — this R10 finding is that the patch was never applied to `server.py`.
- **Fix**: In `create_app()`, if `DATALAB_WEB_SECRET` unset AND `DATALAB_DEBUG` falsy → `raise RuntimeError(...)` with bilingual message. In debug mode, generate per-process `secrets.token_hex(32)` (not a constant string).
- **Regression test**: `tests/test_server_secret_key_required.py` — asserts `create_app()` raises without `DATALAB_WEB_SECRET` when `DATALAB_DEBUG` is unset; asserts debug-mode SECRET_KEY is never `"datalab-web-dev"`.

### C3 — `sample_mp_function` bypasses `precision_guard`
- **Severity**: CRITICAL (concurrency — silently wrong numerical results)
- **File**: `fitting/plot_fitting.py:37-51`. Directly assigns `mp.dps = precision`, manually restores in `finally`.
- **Why it matters**: `mp.dps` is process-global in mpmath. `sample_mp_function` is called from the web plot-generation path, which runs under the same WSGI worker as computation routes. The web core's `@mpmath_synchronized` lock protects `_run_*` functions but does NOT cover plot sampling. A concurrent plot request + fitting request can corrupt each other's precision mid-computation → silently wrong numbers.
- **Adversarial note**: An exception raised between `previous_dps = mp.dps` (line 38) and `mp.dps = precision` (line 40) leaks `previous_dps` unrestored. The try/finally is placed too late. `precision_guard` handles this correctly.
- **Fix**: Replace the manual save/restore with `with precision_guard(precision): ...` from `shared.precision`.
- **Regression test**: `tests/test_plot_fitting_precision_guard.py` — monkey-patch `shared.precision.precision_guard` to a spy, assert it is invoked; assert `mp.dps` is unchanged after `sample_mp_function` raises inside the inner loop.

### C4 — `mp.findroot` called with no `tol`/`maxsteps` — "high-precision" fitter capped at 10 Newton steps
- **Severity**: CRITICAL (silently wrong numerical results at requested precision)
- **File**: `fitting/hp_fitter.py:453, 458`. Both call sites are `mp.findroot(...)` with **no tolerance, no iteration cap, no verifier**.
- **Why it matters**: mpmath's `MDNewton` (multivariate default) has `maxsteps=10` by default, independent of `mp.dps`. A user setting `dps=200` expects 200 correct digits; the solver stops at 10 iterations, reporting whatever Newton happened to reach. Convergence at high precision is silently truncated. For ill-conditioned models (Padé-like, exponential-combo) the reported best-fit can be off by many digits with **no** error or warning.
- **Fix**: Pass `tol=mp.mpf(10)**(-(mp.dps - 5))` and `maxsteps=max(50, mp.dps)` to both `findroot` calls; record `convergence_norm` in `FitResult.details`; post-check `‖∇χ²‖ ≤ tol` and raise/warn if not.
- **Regression test**: `tests/test_hp_fitter_high_precision_convergence.py` — fit `y = A·exp(-k·x)` with synthetic data generated at `dps=200`, assert `|A - A_true| / A_true < 10**-150`.

### C5 — `AutoModel M5 (1/x series)` missing `requires_positive_x=True`
- **Severity**: CRITICAL (user-data crash, silent numerical instability)
- **File**: `fitting/auto_models.py:115`. The basis (`_inverse_basis`) is `[1, 1/x, 1/x²]` — undefined at x=0 and ill-conditioned near zero.
- **Verified contrast**: M4, M4B, M6, M8 all set `requires_positive_x=True`. Only M5 is missing it.
- **Why it matters**: Running auto-fit on data containing 0 → deep `mp.qr` failure with opaque message ("QR decomposition failed") rather than a bilingual pre-fit validation error. The auto-selector may also silently pick M5 even when the data straddles zero.
- **Fix**: Add `requires_positive_x=True` to the `AutoModelDefinition("M5", ..., *_inverse_basis(), ["A", "B", "C"])` call at line 115.
- **Regression test**: `tests/test_auto_models_m5_positive_x.py` — call `auto_fit_dataset` with `x_data=[0.0, 1.0, 2.0]`, assert a bilingual `ValueError` (containing `" / "`) is raised before reaching QR.

---

## HIGH findings

### H1 — `validate_latex_content` fallback in `_security_shim.py` omits `-no-shell-escape`
- **File**: `app_web/_security_shim.py:52`
- The fallback `cmd` has no `-no-shell-escape` flag. If the primary `latex_security` import fails, production falls through to an insecure compile.
- **Fix**: Add `-no-shell-escape` to the fallback `cmd`; also raise on import failure rather than silently installing a less-safe compile path.
- **Test**: `tests/test_security_shim_fallback_hardened.py`.

### H2 — CSRF double-submit fallback + session reseed from cookie
- **File**: `app_web/security.py:40-45, 58-63`
- Two compounding bugs:
  1. `get_csrf_token` **reseeds** the session token from the `datalab_csrf` cookie when the session has none. This lets an attacker (subdomain takeover, same-origin XSS) implant a cookie, which becomes the trusted session token.
  2. `validate_csrf_token` falls back to comparing submitted token against the cookie (self-referential when both come from the attacker's cookie).
- **Fix**: Remove both fallbacks; always generate CSRF token server-side tied to session; reject requests that don't have a proper session-issued token. Keep `httponly=True` on the cookie.
- **Test**: `tests/test_csrf_no_cookie_seeding.py`.

### H3 — Bilingual discipline violations (multiple files)
- **Files**: `app_web/security.py:122, 139-168` (three Chinese-only `ValueError`s in `validate_text_size`, `validate_latex_engine`); `app_desktop/workers_core.py:941` (English-only `Unsupported fit model`); `fitting/constraints.py` possibly others.
- All user-facing error strings must use `_dual_msg(zh, en)` → `"中文 / English"`.
- **Fix**: Replace all offenders with `_dual_msg(...)`.
- **Test**: Extend existing `tests/test_bilingual_errors.py`.

### H4 — SymPy `sp.lambdify(...)` generated lambda exposes `__builtins__`/`__import__`
- **File**: `fitting/constraints.py:191`
- SymPy `lambdify` with `modules="mpmath"` sets the generated function's `__globals__` to the full mpmath namespace, which includes `__builtins__` (a dict containing `__import__`). While exploiting this through the currently-sandboxed `parse_expr` requires effort, it is a defense-in-depth failure — the sandbox is `parse_expr`, not the evaluator.
- **Fix**: Pass `modules=[{ "Sin": mp.sin, "Cos": mp.cos, …, "__builtins__": {} }]` to `lambdify`, or bypass lambdify entirely and evaluate through `expr.subs(...)` + mpmath conversion.
- **Test**: `tests/test_constraints_lambdify_sandbox.py` — assert the returned callable's `__globals__['__builtins__']` is an empty dict (or missing).

### H5 — `safe_eval` does not catch `RecursionError` from `ast.parse`
- **File**: `datalab_latex/expression_engine.py:166-174`
- Deeply nested expressions (`a+a+a+...` ≈10 000 terms, ~60 KB, well under `MAX_TEXT_INPUT_LENGTH=1 000 000`) trigger `RecursionError` in `ast.parse` itself, before MAX_AST_DEPTH is checked. Result: uncaught 500, stack trace leakage in debug.
- **Fix**: Change `except SyntaxError` to `except (SyntaxError, RecursionError, MemoryError)`; add length pre-check `len(expression) > 10_000 → ValueError` before parsing.
- **Test**: Extend `tests/test_safe_eval_security.py` with `test_safe_eval_deeply_nested_expression_raises_value_error`.

### H6 — `_dual_msg` reimplemented in three places
- **Files**: `extrapolation_methods/accelerators.py:13-14`, `extrapolation_methods/power_law.py:13-14`, plus canonical in `data_extrapolation_latex_latest`. Drift risk.
- **Fix**: Centralize in `shared/__init__.py` or a new `shared/i18n.py`; have all sites import from there.
- **Test**: `tests/test_dual_msg_single_source.py` — assert `id(accelerators._dual_msg) == id(power_law._dual_msg) == id(shared._dual_msg)`.

### H7 — `_mp_precision_guard` in workers_core duplicates `shared.precision.precision_guard`
- **File**: `app_desktop/workers_core.py:46-60`
- Direct `mp.mp.dps =` assignment + a parallel implementation of the canonical guard. CLAUDE.md explicitly forbids this; drift risk between the two.
- **Fix**: Delete `_mp_precision_guard`; `from shared.precision import precision_guard` and use it directly.
- **Test**: Implicit in existing precision tests; add a check that `_mp_precision_guard` name is gone.

### H8 — Fitting path never tries `_get_symbolic_partials`
- **File**: `fitting/model_parser.py:105-124`
- The error-propagation code path prefers symbolic SymPy derivatives (cached); the fitting path goes straight to `numerical_partial_derivative`, which is weaker for ill-conditioned models and much slower at high `dps`.
- **Fix**: Mirror the error-propagation path — try `_get_symbolic_partials`, fall back to numerical on failure.
- **Test**: `tests/test_fitting_symbolic_gradient.py` — for `a*exp(-b*x)`, assert the built gradient callable matches `diff(...) → lambdify(...)` output to `eps·100`.

### H9 — `constraints.py` uses second parser with smaller whitelist
- **File**: `fitting/constraints.py:38-50, 205-217`
- `_SAFE_MATH_FUNCS` has 8 functions; `expression_engine._ALLOWED_FUNCTIONS` has ~30. Users cannot write `Erf(a)` in a constraint even though it is allowed in a fit expression.
- **Fix**: Either extend `_SAFE_MATH_FUNCS` to match the canonical list (both casings) or delegate constraint parsing through `safe_eval` + mpmath→sympy conversion.
- **Test**: `tests/test_constraints_function_parity.py`.

### H10 — `power_law._too_close` ε tied to `dps//2`, conflicts with `findroot` tol
- **File**: `extrapolation_methods/power_law.py:80, 86, 103, 189`
- `eps = 10^-max(8, dps//2)` creates inconsistent behavior: at low `dps`, spurious failures; at high `dps`, overly strict.
- **Fix**: Use `eps = mp.eps * mp.mpf("1e6")` — scales naturally with precision.
- **Test**: `tests/test_power_law_eps_scaling.py` — three closely-spaced points that should succeed at `dps=20`.

---

## MEDIUM findings (deferred to `findings.md`)

M1 · `_legacy_impl.py` is orphaned but not deleted — confirmed NOT imported by `app_web/logic/__init__.py`. Downgrade from Stage 1 H#7. Recommendation: delete the file; contains stale security patterns.
M2 · `_precision_guard` imported from shim instead of `shared.precision`. Pure alias cleanup.
M3 · `test_model_selector.py` mutates `mp.mp.dps` directly. Use `precision_guard` fixture.
M4 · `docs.py:156` regex uses `\\1` literal in raw string (actually fine in practice; cleanup only).
M5 · `preexec_fn` + threaded Flask on macOS (documented caveat).
M6 · `_security_shim.py` fallback leaks full LaTeX stderr to warnings list.
M7 · User `mp_precision` not clamped; DoS vector. Cap to ≤ 10 000.
M8 · No rate limiting on `/`, `/error`, `/fit`, `/stats`.
M9 · `combine_error_components` substitutes 0 for missing keys (should be NaN).
M10 · Boundary-hit NaN does not propagate to dependent parameters.
M11 · AIC/BIC noise-floor clamp breaks ranking invariance across `dps`.

## LOW findings (deferred)

L1 · `_collect_params` fallback from `param_errors_total` → `param_errors` (Stage 1 H#8; architect downgraded).
L2 · Scientific DTOs not `frozen=True`.
L3 · M5 lambda `mp.mpf("1")` parsed each call.
L4 · Shanks `error_estimate` missing for minimal `last_row`.
L5 · `_sequence_model` heuristic error in `param_errors_stat["limit"]` field (architect A-8; downgraded — existing `uncertainty_note` mitigates).

---

## §R9 audit

| R9 finding | Status in R10 |
|---|---|
| R9 C1: engine whitelist | ✅ **Fixed** — `validate_latex_engine` + `-no-shell-escape` confirmed in `latex_security.py` |
| R9 C2: `validate_latex_content` dead | ❌ **Still dead** (= R10 C1) |
| R9 C4: `parse_expr` sandbox | ✅ **Fixed** — namespace properly restricted, but lambdify gap new (R10 H4) |
| R9 C5: hardcoded secret | ⚠️ **Partially addressed** — warning added, but fallback still `"datalab-web-dev"` (= R10 C2) |
| R9 C6: `mp.dps` race (web) | ✅ **Fixed** — `@mpmath_synchronized` active on `_run_*`. Desktop path has separate race (R10 H7) |

---

## PR plan

This R10 PR will:
1. Add `CODE_REVIEW_R10.md` (this file).
2. Write RED regression tests for C1–C5 and H1–H5 first (TDD discipline).
3. Implement minimum-diff GREEN fixes for C1–C5.
4. Implement minimum-diff GREEN fixes for H1–H10.
5. Re-run full pytest + coverage; assert no regressions vs. baseline 162 tests.
6. Each commit references the finding ID (`C1`, `H2`, etc.) in the commit body.

MEDIUM/LOW findings become a backlog in `findings.md` for a future PR.
