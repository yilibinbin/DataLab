# DataLab — Round-3 Full-Package Review (recommendations only)

**Scope:** strict swarm review of the entire package on the post-R2 state
(main's merged audit fixes + PR#76). **No fixes applied** — this is a
recommendation document.

**Method (three independent gates):**
1. **Swarm review** — 84 agents across 16 dimensions (9 defect dimensions +
   7 quality/soft dimensions).
2. **Internal adversarial verification** — every defect finding challenged by
   2 skeptics + tie-breaker (default *false-positive* unless reproduced from
   current code).
3. **External adversarial re-review** — Codex (gpt-5.5, xhigh) re-adjudicated
   each surviving defect against the live code; the primary session model
   independently re-verified the contested ones. (Second external CLI — Claude
   headless / gpt-5.1-codex — was unavailable this run: no headless auth /
   not on account; noted for transparency.)

**Funnel:** 28 raw defect findings → 9 survived internal verification →
**8 confirmed** after external re-review (**1 rejected**). Plus **68 soft
recommendations**.

> R2's 17 fixes (F1–F15 + linecache test-isolation + #76 timeout) are already
> merged and were excluded from this round.

---

## Executive summary

| Bucket | Count | Notes |
|---|---|---|
| Confirmed defects | 8 | 2× LaTeX-injection (extrapolation table), 1 numeric, 1 precision-loss, 1 info-leak, 3 silent-error |
| Rejected (external) | 1 | #2 security-shim — production already hard-raises |
| Soft: maintainability | 20 | large files, duplicated helpers, boilerplate |
| Soft: performance | 10 | hp_fitter matrix construction hotspots |
| Soft: testing | 14 | coverage gaps + weak assertions |
| Soft: type-safety | 9 | dynamic attrs on dataclasses, Any leaks |
| Soft: documentation | 7 | missing env-var docs, ARCHITECTURE drift |
| Soft: bilingual | 7 | single-language user strings |

**Overall health:** good. No critical runtime defects survived verification.
The most actionable items are the **two extrapolation-table LaTeX escaping
gaps** (same class as R2's F14, which only fixed the error-propagation table)
and the **SSE high-precision loss**.

---

## Verified defects (external-adjudicated)

### High-value

**D1 — Extrapolation-table LaTeX caption is unescaped (injection / broken compile)**
`datalab_latex/latex_tables_extrapolation.py:309`
User `caption` (web: `app_web/logic/extrapolation.py:174`) is embedded raw in
`\caption{...}`. Sibling tables escape via `_escape_latex_text`; this one
doesn't — R2's F14 fixed only `error_propagation`. Special chars (`& _ $ # % ~ ^ \ { }`)
break compilation or inject commands. **Fix:** escape `caption_text`. Effort: S.
*(Codex CONFIRMED; primary-model CONFIRMED.)*

**D2 — Extrapolation-table column headers are unescaped**
`datalab_latex/latex_tables_extrapolation.py:410`
User headers (`app_web/logic/extrapolation.py:200`) embedded raw in
`\multicolumn{1}{c}{...}`. Same class as D1. **Fix:** escape each header. Effort: S.
*(Codex CONFIRMED; primary-model CONFIRMED.)*

**D3 — SSE fit response drops high precision**
`app_web/blueprints/sse.py:461`
`params = {k: float(v) ...}` / `param_errors_stat` cast mp.mpf → float (~17
digits), destroying results computed at mp_precision=80+. Desktop serializes via
`mp.nstr`. **Fix:** serialize with `mp.nstr(v, precision)`. **Codex refinement:**
`app_web/openapi.py:66` declares these as numbers — update the schema/clients
too, or emit strings consistently. Effort: M. *(Codex CONFIRMED + refinement.)*

### Medium

**D4 — Effective sample size skipped for tiny-but-valid W2**
`datalab_core/statistics_compute.py:380`
After the `W2 > 0` guard (line 372), `elif not mp.almosteq(W2, mp.mpf("0"))`
suppresses `effective_n` for tiny positive W2 (`almosteq(1e-50,0)==True`,
verified). **Fix:** replace the `elif` with `else:` (W2 is already known >0 &
finite). Effort: S. *(Codex CONFIRMED; primary-model CONFIRMED.)*

**D5 — help_specs endpoint leaks raw exception text**
`app_web/blueprints/api.py:269`
Public GET `/api/help_specs` returns `str(exc)` (paths/internals). SSE/pages use
a sanitizer. **Fix:** return `type(exc).__name__`, log full server-side. Effort: S.

### Low (silent error-handling — surface via logging)

**D6** `app_web/logic/fitting.py:970` — plot render swallows all exceptions →
`None` with no log. **Fix:** `logger.exception(...)` before returning None. Effort: S.

**D7** `fitting/runner.py:213` — observed-linear `except ValueError: pass`
loses the fallback reason. **Fix:** record reason in `fallback_history`
(Codex: init `fallback_history` before the `try`). Effort: S.

**D8** `formula_help.py:78` — help-specs load returns `{}` on any OSError/JSON
error with no log. **Fix:** log tried paths + error before the empty fallback. Effort: S.

### Rejected by external review

**~~Dev-mode disables LaTeX sandboxing~~** `app_web/_security_shim.py:92` —
**FALSE_POSITIVE.** Production hard-`raise`s a `RuntimeError` on security-import
failure (`_security_shim.py:42`); the dev fallback logs at ERROR ("DEV UNSAFE
MODE") *and* the fallback `compile_latex_safe` still forces `-no-shell-escape`
(guards `\write18`). Only the heuristic content-filter is absent in dev
fallback — defense-in-depth behind a hard control. Not a real production gap.
*(Codex FALSE_POSITIVE; primary-model confirmed the raise + shell-escape guard.)*

---

## Improvement recommendations (soft — not adversarially verified)

### Maintainability (20)
- `app_desktop/window.py` — monolithic (8 mixins, 150+ methods); several
  100–150-line methods (`_on_stats_mode_change:1328`, `_refresh_display_format:2902`,
  `_initialize_workspace_tracking:732`, `__init__:476`); a repeated
  getattr/hasattr/setVisible visibility pattern (~21×) → extract a
  `set_visible_if(attr, cond)` helper.
- Duplicated helpers across statistics modules: `_bool_option` (4 modules),
  `_string_option` (3) → hoist to one shared module.
- `shared/plotting.py` (2080 lines, 62 funcs) — split by workflow.

### Performance (10) — concentrated in `fitting/hp_fitter.py`
- `:341` JᵀJ built via repeated row indexing; `:333` redundant model
  evaluations during covariance; `:343` repeated `mp.mpf(0)` allocs; `:140`
  redundant `mp.nstr` for dedup keys; `:436` double-nested error-propagation
  loop without early exit. These are the high-precision hot path — worth
  profiling before optimizing.

### Testing (14)
- No tests: `precision_guard` edge/clamp cases (`shared/precision.py:40`),
  `_coerce_int`, safe_eval div/mod-by-zero (`shared/expression_engine.py:232`),
  `combine_error_components` NaN/Inf (`fitting/hp_fitter.py:63`), constraint DAG
  failures (`fitting/constraints.py:133`). Several weak assertions flagged.

### Type-safety (9)
- `fitting/implicit_model.py:171` dynamic attribute attachment to a dataclass;
  `fitting/hp_fitter.py:256` `getattr` on a required field. Consider widening
  mypy --strict beyond the current 4 roots.

### Documentation (7)
- `docs/web/deploy.en.md` missing `DATALAB_SSE_DISABLE_RATE_LIMIT` and LaTeX
  security env vars; `docs/ARCHITECTURE.md` predates `datalab_core/`.

### Bilingual (7)
- Assorted single-language user-facing strings not using `_dual_msg` (details in
  the finding set).

---

## Prioritized action list

1. **D1 + D2** (extrapolation LaTeX escaping) — same class as a shipped R2 fix,
   small, user-data-driven. Do first.
2. **D3** (SSE precision loss) — defeats the product's core value on the web fit
   path; pair with the OpenAPI schema update.
3. **D4** (effective_n) — one-line correctness fix.
4. **D5–D8** (info-leak + silent errors) — small, batchable logging/sanitizing.
5. Soft items — schedule as maintenance; hp_fitter perf only after profiling.

*Generated by the R3 swarm review; verified via internal 2-skeptic gate +
external Codex adjudication + primary-model re-verification. No code changed.*
