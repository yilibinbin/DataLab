# DataLab Code Review R9 — Ultradeep Multi-Agent Review

**Date:** 2026-04-24
**Repository:** `DataLab-review/` (snapshot of `DataLab/` at commit `f128225` + scientific modules added in follow-up commit)
**Branch:** `review/r9-ultradeep`
**Reviewers (parallel agents):**
- `security-reviewer` — OWASP / secrets / injection
- `architect` — system design, coupling, refactor sequencing
- `python-reviewer` — PEP-8, idioms, type-safety, threading
- `general-purpose` (math focus) — numerical correctness & stability of every algorithm

> **Codex adversarial review: NOT RUN.**
> The Codex CLI on this ChatGPT-account session refused all requested
> models (`gpt-5.5`, `gpt-5`, `gpt-5-codex`, `o3` — each returns
> "model not supported when using Codex with a ChatGPT account" or "does
> not exist"). The four-agent review below replaces that gap with
> independent, role-separated passes; an external Codex/OpenAI API-key
> session is recommended as a follow-up adversarial pass.

---

## 1. Executive Summary

| Severity | Count | Examples |
|----------|-------|----------|
| **CRITICAL** | 8 | LaTeX shell-escape, `mp.dps` cross-thread race, "LM" fitter is actually gradient-Newton, AIC/BIC dependent on `noise_floor()` clamp, hardcoded fallback secret |
| **HIGH** | 16 | Unused `validate_latex_content`, raw column-header interpolation, SymPy `parse_expr`, DoS via `Gamma`/`Hyp2f1`, `_dual_msg` re-defined in two modules, covariance double-counts variance for `1/σ²` weights, fitter does not allow mid-run cancellation |
| **MEDIUM** | 17 | `_legacy_impl.py` 75 KB legacy debt, mixin attribute leakage, levin "fallback to last value" hides failure, `precision_guard` upper bound 1 M dps is a footgun, mutable Result dataclasses |
| **LOW** | 8 | CSV `1.23(456)` parser silently allows σ > value, inconsistent naming `sigma_list` vs `sigmas_for_fit`, missing warning on N=1 weighted mean |

**Overall verdict for shipping to production:** **DO NOT MERGE** until the 8 CRITICAL items are addressed. The math/numerics layer is correct in *intent* but several formulas behave incorrectly in edge cases (perfect fits, inverse-variance weights, sub-meV chemistry). The web layer has at least one shell-injection-class issue (LaTeX engine input) that must be fixed before any public deployment.

---

## 2. How Codex Adversarial Review Failed (for the record)

| Attempt | Model | Error |
|---------|-------|-------|
| 1 | `gpt-5.5` | `model gpt-5.5 does not exist` |
| 2 | `gpt-5` (with `--base main`) | `--base cannot be used with [PROMPT]` (CLI argument conflict) |
| 3 | `gpt-5` (no `--base`) | `gpt-5 not supported when using Codex with a ChatGPT account` |
| 4 | `gpt-5-codex` | same restriction |
| 5 | `o3` | same restriction |

Action: re-run `/codex:adversarial-review --background` once an OpenAI API key is configured (`export OPENAI_API_KEY=…` and remove the ChatGPT auth) — the configuration knobs live in `~/.codex/config.toml`.

---

## 3. CRITICAL Findings (must-fix before merge)

### C1. LaTeX engine path is unvalidated — shell injection class
- **Files:** `app_web/logic/latex_engine.py` (engine selection), `data_extrapolation_latex_latest.py` (legacy shim that compiles)
- **Issue:** The user-supplied LaTeX engine path (`pdflatex`/`xelatex` or a custom path picked via the GUI's "选择引擎路径") is passed to `subprocess` without validation that it points to an executable LaTeX binary. A custom path can be any executable; a malicious config file could substitute it.
- **Fix:** Whitelist allowed binary names + require an absolute path that resolves to a known LaTeX engine. Reject if not.

### C2. `validate_latex_content` is defined but unused
- **File:** `data_extrapolation_latex_latest.py` (and the `datalab_latex/` package facade)
- **Issue:** A `validate_latex_content` function exists to detect dangerous LaTeX (e.g., `\write18`, `\input{|cmd}`) but is **never called** before compilation. With `-shell-escape` (some TeX distros default it on), arbitrary shell execution is possible.
- **Fix:** Wire `validate_latex_content` into the compile path; add `-no-shell-escape` to the engine arguments.

### C3. Raw column-header interpolation in LaTeX tables
- **File:** `datalab_latex/latex_tables.py` and friends
- **Issue:** Column headers from CSVs flow into `\multicolumn{...}{...}{HEADER}` without LaTeX-escaping `& % $ # _ { } ~ ^ \`. A header like `a_b` typesets as math mode subscript; a header like `\write18{rm -rf}` is even worse.
- **Fix:** Escape via the existing `latex_formatting.escape_latex` helper in every table writer.

### C4. SymPy `parse_expr` accepts arbitrary Python — sandbox escape
- **File:** `fitting/constraints.py`
- **Issue:** Constraints typed by the user are parsed with `sympy.parse_expr` without `evaluate=False` and without restricting the parser's namespace to the safe symbol whitelist. SymPy's `parse_expr` is documented to allow `__import__`-style escapes when `evaluate=True` if the local namespace is broad.
- **Fix:** Use `sympy.parse_expr(expr, transformations=standard_transformations, local_dict=ALLOWED_SYMBOLS, global_dict={})` and reject anything that produces a `Function` outside the whitelist.

### C5. Hardcoded fallback secret in Flask app
- **File:** `app_web/server.py`
- **Issue:** When `DATALAB_WEB_SECRET` is not set, a hardcoded fallback string is used. Sessions/CSRF protection are then deterministic across deployments.
- **Fix:** Refuse to start in non-debug mode if `DATALAB_WEB_SECRET` is unset. Replace the fallback with a randomly-generated per-process secret in debug mode only, plus a console warning.

### C6. `mp.dps` race across QThreads (desktop) and Flask threads (web)
- **Files:** `shared/precision.py:31-46`, `app_desktop/workers_core.py`, `app_web/` (Flask threads)
- **Issue:** `precision_guard` sets the **process-global** `mpmath.mp.dps` and restores it in `finally`. Thread A's `precision_guard(50)` clobbers Thread B's `precision_guard(200)` mid-flight. The desktop `CalcJob`/`FitJob`/`AutoFitJob` workers run on QThreads concurrently; the web app uses Flask's threaded server.
- **Fix:** Use mpmath's `MPContext` and create a per-thread context, or wrap `precision_guard` with a `threading.RLock` and serialize all numerical work. Document the choice; the lock approach is simpler but reduces parallel throughput on multi-core machines.

### C7. "LM" fitter is actually gradient-zero Newton (no LM safety net)
- **File:** `fitting/hp_fitter.py:451-463`
- **Issue:** Despite the name and docs, the fitter calls `mp.findroot` on the **gradient** of χ². There is no Marquardt damping `λ`, no trust region, no χ²-decrease-on-step gate. The only resilience is multi-seed retry. On rank-deficient or near-singular Hessians, `mp.findroot` raises and the user gets `cov_warning="singular"` plus possibly converged-to-wrong-minimum parameter values.
- **Fix:** Either rename and document honestly ("Newton on the score function") **or** implement true LM:
  ```
  Build (J^T W J + λ·diag(J^T W J)) Δp = J^T W r
  Accept Δp iff χ² decreases; else λ ×= 10
  Stop on |Δχ²|/χ² < tol AND ||g||∞ < tol
  ```

### C8. AIC/BIC ranking depends on `noise_floor()`, which depends on `mp.dps`
- **Files:** `fitting/hp_fitter.py:205-208`, `fitting/auto_models.py:246-249`, `fitting/model_selector.py:97-100`, `shared/numerics.py:13`
- **Issue:** When χ² → 0 (perfect fit), the code substitutes `noise = 10^(-max(30, dps//2))` and feeds it into `n·log(noise)`. So **the same data ranked at `dps=50` versus `dps=200` flips the AIC ordering** for any model that achieves χ² < eps. At `dps=10` the floor is `10⁻³⁰`, which is **stricter** than mpmath's actual ε at that precision (`10⁻¹⁰`).
- **Fix:** When `chi2 ≤ mp.eps · Σ|y|²/n`, set `aic = -inf` (perfect fit) and break ties by parameter count. Or use `noise = mp.eps * (Σ|y|²/n)` instead of `dps`-derived floor.

---

## 4. HIGH Findings

### H1. `_dual_msg` re-defined locally in two modules
- **Files:** `extrapolation_methods/accelerators.py`, `extrapolation_methods/power_law.py`
- **Issue:** Both files define their own `_dual_msg(zh, en)` instead of importing the shared one. Drift risk.
- **Fix:** Move the canonical helper to `shared/messages.py` and import.

### H2. Covariance double-counts variance when weights are `1/σ²`
- **Files:** `fitting/hp_fitter.py:249-250`, `fitting/auto_models.py:258, 267`
- **Issue:** Both fitters always apply `cov = (J^T W J)^-1 · χ²/dof`. For inverse-variance weighting the rescale is wrong — for "good" fits with χ²/dof ≈ 1 it's harmless; for bad fits it inflates errors by `√(χ²/dof)`.
- **Fix:** Add `weight_kind ∈ {"unit","relative","inverse_variance"}` and only rescale for the first two.

### H3. Fitter has no mid-run cancellation
- **Files:** `fitting/hp_fitter.py`, `app_desktop/workers_core.py:FitJob`
- **Issue:** Once `mp.findroot` is in its iteration loop there is no way for the GUI to abort. A high-`dps` fit can hang the worker for tens of minutes.
- **Fix:** Pass a `cancel_flag` callable; check it inside `_residual_callable`.

### H4. AIC `k` = number of basis functions, not free parameters
- **File:** `fitting/auto_models.py:248-249`
- **Issue:** Linear models report `k = cols`, but `fit_custom_model` reports `k = free_param_count`. When the custom model has fixed parameters the two are on different scales — the cross-model ranking in `model_selector` then favors whichever family happens to use fewer "k" by convention.
- **Fix:** Re-emit `k = free_param_count` from each fit and recompute AIC in the ranker.

### H5. `_legacy_impl.py` is 2 088 / 75 KB lines of legacy debt
- **File:** `_legacy_impl.py` (was the pre-package monolith)
- **Issue:** Imports flow through a backwards-compat shim (`data_extrapolation_latex_latest.py`); editing the package or the shim diverges silently. Tests don't all exercise both paths.
- **Fix:** Inventory which symbols are still imported from the shim, migrate them to the package, then delete `_legacy_impl.py`.

### H6. `sigma_list` vs `sigmas_for_fit` naming inconsistency
- **File:** `app_web/logic/fitting.py:805` (and surroundings)
- **Issue:** Two names for the same uncertainty list. One path passes `sigma_list`, the other `sigmas_for_fit`. Easy to swap by accident.
- **Fix:** Pick one (`sigmas`), refactor.

### H7. `mp.dps` directly assigned in `fitting/plot_fitting.py:39-51`
- **File:** `fitting/plot_fitting.py`
- **Issue:** Bypasses `precision_guard`, contributing to the race condition above.
- **Fix:** Wrap in `with precision_guard(...)`.

### H8. Wynn-ε "cancellation_indicator" extracted from a dummy column
- **File:** `extrapolation_methods/accelerators.py:130-134`
- **Issue:** mpmath's epsilon table interleaves dummy even-index columns. `last_row[-2]` happens to be the dummy column; using `|last_row[-2]|` as a cancellation magnitude is misleading.
- **Fix:** Use `|last_row[-1] − last_row[-3]|` for the error estimate (already done) and drop the cancellation_indicator field — or rename it to clarify what it is.

### H9. Wynn-ε at exactly N=3 emits no error estimate
- **File:** `extrapolation_methods/accelerators.py`
- **Issue:** When the input has the minimum-allowed length, `last_row` has length 1 and the error-estimate branch is skipped. Downstream code falls back to `sqrt(noise_floor())`, which is meaningless.
- **Fix:** At N=3 set `error_estimate = |last_row[0] − mp_sequence[1]|`.

### H10. Power-law solver picks min-residual root without domain check
- **File:** `extrapolation_methods/power_law.py:135-158`
- **Issue:** Multiple seeds, picks smallest `|residual(p)|`. No bound on `p`. Physical use cases want `p ∈ (0, 10)`.
- **Fix:** Add an optional `p_bounds=(0, 10)`; reject candidates outside.

### H11. Numerical Jacobian step optimal for first derivative, not nested differencing
- **Files:** `datalab_latex/derivatives.py:100-130`, `fitting/hp_fitter.py`
- **Issue:** `mp.findroot` re-differences the gradient internally. Cumulative error for the implicit Hessian is `O(ε^{1/2})` — at `dps=10` that's only ~5 digits.
- **Fix:** Build the residuals' Jacobian symbolically when SymPy succeeds; use the closed-form `J^T J` for LM.

### H12. DoS via `Gamma`/`Hyp2f1`/`BesselY` near singularities
- **Files:** `datalab_latex/expression_engine.py:73-79`
- **Issue:** mpmath's `hyp2f1` near `|z|=1` and `gamma` at large arguments can take seconds-to-minutes per call. A user-supplied formula evaluated thousands of times in a Monte-Carlo error-propagation run can hang the web request.
- **Fix:** Add a per-evaluation timeout (`signal.alarm` or `concurrent.futures.ThreadPoolExecutor` with `wait(timeout=…)`).

### H13. `print()` calls in library code
- **Files:** several modules under `extrapolation_methods/`, `fitting/`
- **Issue:** Library code should use `logging`, not `print`. PyInstaller-bundled apps lose the output to a hidden stream on Windows.
- **Fix:** Replace with `logging.getLogger(__name__).warning(...)`.

### H14. Bare/`Exception` catches that swallow useful errors
- **Files:** several places in `app_web/blueprints/api.py`, `fitting/`
- **Issue:** `except Exception: pass` patterns hide bugs and make debugging painful.
- **Fix:** Catch the specific exception types; re-raise unknown ones; log with stack trace at `ERROR` level.

### H15. RMSE divides χ² by Σw, which only matches y-units when weights are dimensionless
- **File:** `fitting/hp_fitter.py:181, 188`
- **Issue:** `rmse = sqrt(chi2/total_weight)` is correct only for dimensionless weights. With raw `1/σ²` weights it has units of `[y]^4`, which is meaningless.
- **Fix:** `rmse = sqrt(Σ rᵢ² / n)` independent of weighting.

### H16. Web app uses Flask development server in production examples
- **Files:** `README.md`, `QUICK_START.md`
- **Issue:** Both docs show `python app_web/server.py` as the run command. The deploy doc correctly specifies Waitress (Windows) / Gunicorn (Linux) — but new readers can miss it.
- **Fix:** Add a banner "Development only" to the dev-server command and link the deploy doc immediately.

---

## 5. MEDIUM Findings (17 — abridged)

- **`precision_guard` upper bound 1 000 000 dps** (`shared/precision.py:8`) — cap at 10 000.
- **`noise_floor` stricter than achievable precision at `dps=10`** (`shared/numerics.py:13`) — use `mp.eps · ⟨|y|²⟩` instead.
- **Levin "fallback to last value" silently masks failure** (`extrapolation_methods/accelerators.py:188-201`) — flag `unreliable=True`.
- **Numerical 2nd partials lose half precision** (`datalab_latex/derivatives.py:138-206`) — prefer symbolic Hessian; document `O(ε^{1/2})` for fallback.
- **Mixin attribute leakage** (`app_desktop/window_*_mixin.py`) — define `__slots__` or document required class attributes.
- **`Result` dataclasses are mutable** — switch to `@dataclass(frozen=True)`.
- **Power-law default precision 50 is borderline for sub-meV chemistry** (`extrapolation_methods/power_law.py:26`) — bump default to 80.
- **Sample/effective-DOF formulas inconsistent** (`statistics_utils.py:207, 244`) — pick one convention, document.
- **`std_mean = 1/√Σw` only correct for inverse-variance weights** (`statistics_utils.py:223`) — guard against other weight kinds.
- **CSV `1.23(456)` allows σ > value with no warning** (`datalab_latex/latex_tables_error_propagation.py:55-131`).
- **PyInstaller spec is hand-tuned** — needs a regen-from-scratch test in CI to catch drift.
- **Power-law `_too_close` uses `mp.mpf("1")` floor** (`extrapolation_methods/power_law.py:80-84`) — wrong for tiny values; use pure relative scale.
- **`Hyp2f1`/`BesselY` branch-cut behavior not surfaced** — log a warning when result is `mpc` or `nan`.
- **`Power(-2, 0.5)` returns mpc, downstream raises `ValueError`** (`datalab_latex/expression_engine.py:87`) — catch and emit a clear "complex result" message.
- **Parallel `auto_models` fits not multi-process** — currently sequential; for n>20 models a worker pool would help.
- **Long functions (>50 lines)** — `fit_custom_model`, `_run_extrapolation_internal`, several Flask handlers — refactor into helpers.
- **Long files (>800 lines)** — `_legacy_impl.py`, `latex_tables.py`, `window.py` mixins combined.

---

## 6. LOW Findings (8 — abridged)

- N=1 weighted mean returns σ=0 silently — should warn.
- Several module-level functions missing type hints.
- f-strings vs `.format` mixed inconsistently.
- A handful of `# TODO` markers older than 6 months.
- One unused import in `app_web/blueprints/docs.py`.
- Inconsistent Bessel-correction defaults across `statistics_utils.py` callers.
- Welford's algorithm correctly used in MC sampling — confirmed.
- Constraint Jacobian propagation is correct — confirmed.

---

## 7. Architecture Findings (architect agent)

1. **`precision_guard` duplication risk** — three call sites bypass it; centralize.
2. **No mid-fit cancellation** — see H3.
3. **`_legacy_impl.py` 75 KB technical debt** — see H5.
4. **Mixin attribute leakage** — `ExtrapolationWindow` is composed from 7 mixins each setting attributes on `self` without declaration; any rename must grep across all 7.
5. **`mp.dps` race on desktop** — see C6.
6. **Comprehensive module dependency map produced** (see architect raw output) — `shared/` is correctly the leaf; one cycle exists between `fitting/model_parser.py` ↔ `data_extrapolation_latex_latest.py` (via the safe-eval re-import).

**Recommended 8-step refactor sequence (architect agent's prioritization):**
1. Add `threading.RLock` to `precision_guard`. (1 day)
2. Replace `_dual_msg` local copies with shared helper. (½ day)
3. Wire `validate_latex_content` and disable `-shell-escape`. (½ day)
4. Escape LaTeX column headers. (½ day)
5. Cancellation flag plumbed through fitters. (2 days)
6. AIC `k` accounting unified. (1 day)
7. LM-with-damping replaces gradient-Newton. (5 days, with regression suite)
8. Migrate symbols off `_legacy_impl.py`, then delete. (5 days, plenty of grep)

---

## 8. Math/Numerics Verdict (general-purpose agent, math focus)

- **Richardson:** SOUND. Correctly delegates to `mp.richardson`; N≥4 guard is correct.
- **Wynn-ε / Shanks:** SOUND-WITH-CAVEATS. Misleading cancellation_indicator; missing error estimate at N=3.
- **Power-law:** FRAGILE for edge cases. Multi-root solver with no domain bounds; default precision borderline.
- **"LM" fitting:** FRAGILE — works but mislabeled and over-rescales errors. See C7, H2.
- **AIC/BIC:** SOUND-WITH-CAVEATS. Formula correct; `k` and `noise_floor` clamp issues. See C8, H4.
- **Error propagation:** SOUND. Symbolic Jacobian + Hessian path is correct (verified `½(H σᵢσⱼ)² == ½ H² σᵢ²σⱼ²`); numerical fallback loses half precision.
- **Weighted statistics:** SOUND-WITH-CAVEATS. Bessel correction handled; Kish vs `Σw²/Σw²` formulas inconsistent.
- **Uncertainty parsing `1.23(4)[-2]`:** SOUND with one warning gap.

**16 specific test cases the math agent recommended adding** are listed verbatim in the agent transcript at `/private/tmp/.../tasks/a0850db25693718da.output` (see "Suggested test cases that should exist" section) — they cover Wynn-ε at N=3, Richardson on Leibniz, power-law degeneracies, LM rank-deficiency, AIC `k` accounting, inverse-variance covariance, and `noise_floor` invariance under `dps`.

---

## 9. Top-10 Unified Action List (in priority order)

| # | Action | Severity | Files | Est. effort |
|---|--------|----------|-------|-------------|
| 1 | Disable `-shell-escape`, wire `validate_latex_content` | C1, C2 | LaTeX engine call site | 0.5 d |
| 2 | Add `threading.RLock` (or per-thread context) to `precision_guard` | C6 | `shared/precision.py` | 1 d |
| 3 | Escape LaTeX column headers via `escape_latex` | C3 | `datalab_latex/latex_tables*.py` | 0.5 d |
| 4 | Refuse to start without `DATALAB_WEB_SECRET` in production | C5 | `app_web/server.py` | 0.25 d |
| 5 | Restrict SymPy `parse_expr` to whitelist namespace | C4 | `fitting/constraints.py` | 1 d |
| 6 | Implement true LM with `λ` damping + step gating, OR rename to "Newton solver" | C7 | `fitting/hp_fitter.py` | 5 d |
| 7 | Fix AIC/BIC: drop `noise_floor` floor; unify `k = free_param_count`; emit `-inf` for χ² → 0 | C8, H4 | `fitting/{hp_fitter,auto_models,model_selector}.py`, `shared/numerics.py` | 1.5 d |
| 8 | Add `weight_kind` flag; suppress `χ²/dof` rescale for `1/σ²` weights | H2 | `fitting/hp_fitter.py`, `fitting/auto_models.py` | 1 d |
| 9 | Plumb cancel-flag through fitter | H3 | `fitting/hp_fitter.py`, `app_desktop/workers_core.py` | 2 d |
| 10 | Replace local `_dual_msg` copies with shared helper | H1 | `extrapolation_methods/{accelerators,power_law}.py`, new `shared/messages.py` | 0.5 d |

**Total est: ~13 person-days** to clear CRITICAL+HIGH.

---

## 10. How to Use This Report

- **`git checkout review/r9-ultradeep`** in `DataLab-review/` → this branch contains only `CODE_REVIEW_R9.md`.
- The actual code on this branch is otherwise identical to `main` (which contains the snapshot at `DataLab/` HEAD as of 2026-04-24).
- Open issues / sub-PRs against the *original* `DataLab` repository for each top-10 item; this review repo is reference material, not the authoritative codebase.
- Re-run the Codex adversarial pass once an OpenAI API key is available — `/codex:adversarial-review --background` from `DataLab/` (the original).
- Re-run the math review with the 16 proposed test cases turned into actual `pytest` cases first; the test failures are likely to surface additional bugs that this report missed.

---

*End of CODE_REVIEW_R9.md*
