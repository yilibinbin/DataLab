I'll produce the plan directly. The task is well-specified with all the data I need inline, so no repo exploration is required.

# DataLab Soft-Recommendations Implementation Plan

## Part 1 — KEEP items grouped into PR-sized mini-batches (safest-first)

### Batch 1 — Docs-only: env-vars + service-layer docs (zero code risk)
**Effort: S combined.** Pure documentation, no behavior change, no tests.
- `docs/web/deploy.en.md:148` — add 5 LaTeX sandbox vars (`DATALAB_LATEX_TIMEOUT`, `_MAX_CPU`, `_MAX_MEM`, `_MAX_FILE`, `_MAX_PROC`) from `app_web/latex_security.py:30-41` to the Optional config table. `[_idx 22]`
- `docs/web/deploy.en.md:148` — add `DATALAB_SSE_DISABLE_RATE_LIMIT` row (from `app_web/blueprints/sse.py:178`). `[_idx 23]`
- `CLAUDE.md:48` — expand env-var list to include the 8 missing vars (`DATALAB_TRUST_PROXY_HEADERS`, the 5 LaTeX vars, `DATALAB_LATEX_ENGINE`), or add a one-line pointer to `deploy.en.md`. `[_idx 27]`
- `docs/ARCHITECTURE.md:78` — add a `datalab_core` service-layer section between "Computation modules" and "Cross-cutting conventions"; cross-reference CLAUDE.md rather than duplicating. `[_idx 26]`

### Batch 2 — Docstrings-only (public-API + safety-contract docs)
**Effort: S combined.** Pure docstrings, no code paths touched.
- `fitting/hp_fitter.py:536` — add docstring to `fit_custom_model` (purpose, 8 params + equal-length constraint, `model_factory` semantics, `FitResult` return, `ValueError` conditions). `[_idx 25]`
- `shared/precision.py:46` — expand `precision_guard` docstring (document `clamp_min`/`clamp_max`, defaults + safety implications, MIN/MAX constants, example). `[_idx 28]`

### Batch 3 — Bilingual error messages (`_dual_msg` consistency)
**Effort: S combined.** String-only changes; add `_dual_msg` import where missing.
- `fitting/mcmc_fitter.py:146` — wrap the validation `ValueError`s (lines 146, 148, 153, 159) with `_dual_msg`. Note: SKIP bucket flags that partial wrapping is inconsistent — wrap **all four** in this function together, not just one. `[_idx 62]`
- `fitting/constraints.py:342` — wrap the Chinese-only `无法解析表达式` `ValueError` with `_dual_msg`. `[_idx 66]`
- Add 2-3 tests asserting the `" / "` bilingual separator is present.

### Batch 4 — Small type-safety cleanups in fitting/
**Effort: S–M combined.** All under mypy `--strict` perimeter (`fitting.*`); verify `mypy fitting` clean after.
- `fitting/hp_fitter.py:256` — replace `getattr(state, "dependent_defs", None)` with `not state.dependent_defs` (required field). `[_idx 53]`
- `fitting/hp_fitter.py:650` — replace defensive `getattr` on required `ModelSpecification.expression`. `[_idx 56]`
- `fitting/model_parser.py:40-42` — add `TypeAlias` annotation to `MpfCallable`. `[_idx 58]`
- `fitting/model_parser.py:57` (M) — add optional typed fields (`implicit_definition`, `implicit_diagnostics`, `set_implicit_point_index`) to `ModelSpecification`; update `implicit_model.py:171-173` to set them instead of `setattr`. This is the larger piece — can split into its own PR if review prefers. `[_idx 54]`

### Batch 5 — hp_fitter numerical perf (localized, established patterns)
**Effort: S combined.** Local refactors using existing mpmath idioms; must re-verify residuals on cluster (per project review gate), not local mac.
- `fitting/hp_fitter.py:342` — compute `J^T J` via `jacobian.T * jacobian` (mp.matrix) instead of nested loops, matching `auto_models.py`. `[_idx 43]`
- `fitting/hp_fitter.py:325,342,345,396,400,409,435` — cache a single `mp.mpf("0")` and reuse in covariance / dependent-error loops. `[_idx 45]`

### Batch 6 — Test-gap fills (new tests only, no production changes)
**Effort: S each, but many files — batch or split by area.** Additive tests only.
- New `tests/test_shared_precision.py` — consolidate three overlapping recs: `_coerce_int` edge cases (inf/nan/OverflowError/non-numeric) `[_idx 29]`; direct `precision_guard` tests (invalid dps, clamp boundaries, `clamp_min>clamp_max`, dps=1) `[_idx 30]`; parameterized clamping boundaries (clamp_min=0, inverted ranges, None, near-MAX) `[_idx 39]`. Merge into one file to avoid duplication.
- `shared/expression_engine.py` — direct `_ast_metrics` depth/node-count tests `[_idx 41]`.
- `fitting/hp_fitter.py:102` — direct tests for `_generate_seed_variants` helpers (scale factors, zero handling, dedup, empty/single seed) `[_idx 42]`.
- `fitting/constraints.py:73` — `ParameterState.compose()` edge cases. **Note the load-bearing finding:** `zip(self.free_params, free_vector)` silently truncates on length mismatch — the test should assert this raises (and likely a 1-line guard added to `compose()` to make it fail loud). Also NaN/Inf, boundary clamping, invalid dependent math. `[_idx 36]`

### Batch 7 — expression_engine error-contract fix (behavior + tests)
**Effort: S.** Small behavior change with tests.
- `shared/expression_engine.py:248-254` — wrap `ZeroDivisionError` (binary `/` and `%`, lines ~82-84, 253) in bilingual `ValueError` to honor the module's `ValueError`-only contract; add tests for `safe_eval('1/0')` and `safe_eval('1%0')`. Check `fitting/auto_models.py` which currently catches `ZeroDivisionError`. `[_idx 33]`

### Batch 8 — Statistics `_bool_option` dedup
**Effort: M.** Cross-module; do after the low-risk batches since it touches four modules.
- Extract a shared `_bool_option` helper into `statistics/_helpers.py` with an optional `allow_string_variants` param; standardize `statistics_time_series.py:686`, `statistics_matrix.py`, `statistics.py`, `statistics_grouped.py` on the strict (fail-fast) default. `[_idx 21]`
- **Cross-check against SKIP bucket:** two SKIP entries argue against consolidating these same helpers (semantic divergence: bilingual vs non-bilingual errors, string-variant vs strict). Resolve the string-variant/bilingual behavior question **before** coding — see DECIDE Q3.

### Batch 9 — Small maintainability cleanups in window.py / mixins / latex writer
**Effort: S each.** UI-logic refactors with existing test coverage; verify targeted Qt tests after.
- `app_desktop/window.py:1369` — hoist `stats_time_series_method_combo.currentData()` above the 2-element loop (line ~1366). `[_idx 2]`
- `app_desktop/window.py:1387` — consolidate 3-assignment `trim_visible` into one statement (covered by `test_desktop_statistics_ui.py:268`). `[_idx 5]`
- `app_desktop/window_fitting_params_mixin.py:11` — delete the empty `WindowFittingParamsMixin` placeholder file; remove import (`window_fitting_mixin.py:46`) and MRO entry (`:53`). `[_idx 13]`
- `app_desktop/fitting_latex_writer.py:41` — remove single-use `_latex_escape_text` wrapper; replace 4 call sites (265, 267, 282, 331) with direct `latex_escape`. `[_idx 18]`

### Batch 10 — Large staged refactor (own track; sequence LAST)
**Effort: M–XL, risk medium.** Multi-PR effort; do NOT bundle with anything above. Per `CODE_REVIEW_2026.md` §2.5, sequence after CI (P0) and dead-code cleanup.
- `app_desktop/window.py:466` — decompose `ExtrapolationWindow` (3196 LOC / 7 mixins). Staged: (1) split large mixins (statistics 1921 LOC, extrapolation 1128 LOC) via the proven `WindowFittingMixin` shim pattern with public API stable; (2) complete `views/` layer with typed window-facade `Protocol`; (3) only then consider full composition. `[_idx 17]`

---

## Part 2 — DECIDE items (explicit questions for the maintainer)

1. **`_refresh_display_format` refactor `[_idx 7]` (`app_desktop/window.py:2902`, 109 LOC, 10 branches):** The three internal patterns (format-based / snapshot-based / special-case) could partly consolidate, but result kinds have divergent CSV headers/metadata, so extraction needs polymorphic formatters or a data-driven table. **Question: Are new result kinds added often enough to justify the indirection, or does the working, test-covered method stay as-is under the surgical-changes principle?**

2. **Batch 8 sequencing/scope:** The `_bool_option` KEEP `[_idx 21]` directly conflicts with two SKIP verdicts on the same helpers. **Question: Do we standardize on the strict (fail-fast, non-string) behavior across all four statistics modules, and is it acceptable to add `_dual_msg` bilingual imports to `statistics.py` (currently English-only) as part of that unification?**

3. **Batch 10 gating:** **Question: Is P0 (CI) and the dead-code cleanup done, so the `ExtrapolationWindow` staged decomposition can start? If not, this batch stays parked.**

---

## Part 3 — SKIPped items (one-line grouped summary)

Skipped (all justified): **hp_fitter micro-perf false-positives** — sqrt_weights allocation, redundant model-eval/nstr claims, covariance double-loop, dict pre-allocation, `_prepare_points` list conversions (misread Python semantics or negligible vs. mpmath cost); **window.py speculative refactors** — `_on_stats_mode_change` table-driven extraction, `__init__` builder pattern, `_initialize_workspace_tracking` data-driven, test-kind string constants (explicit UI repetition is intentional/low-churn); **already-done or false-positive test claims** — DAG/bilingual constraint tests, `combine_error_components` NaN, sampling-cache precision restoration, Student-t scipy cross-val (coverage already exists); **cosmetic bilingual/typing consistency** — mcmc/output_inversion `ValueError`s that are swallowed internally and never user-visible, `cast()`/mpmath type-annotation notes already documented, `MutableMapping`→`dict` in non-strict `datalab_core`; **large-module splits** — `plotting.py`, `ui_specs.py`, `ui_schema_runtime.py` wrappers (cohesive, low-churn-history, import-churn cost exceeds benefit).