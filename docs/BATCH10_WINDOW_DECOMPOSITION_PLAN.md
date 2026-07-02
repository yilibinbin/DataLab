# Batch 10 — `ExtrapolationWindow` decomposition (staged plan, no code yet)

> R3-soft KEEP `[_idx 17]`; CODE_REVIEW_2026 §2.5 (high). **This document is a
> plan only.** Each stage is a separate, independently-mergeable PR gated by the
> project review workflow (cluster tests + 3-model + CodeRabbit + full-suite).
>
> **Revised after two-model external adversarial review (Codex / gpt-5.5 +
> Antigravity / Gemini), each finding re-verified against the code.** Gemini's
> verdict was **REJECT** (not safe to execute as originally written); it agreed
> with every Codex finding and added the Qt-MRO-severance, precedence-reversal,
> and Stage-3 worker-placement hazards below. Net: the shim/MRO approach is
> viable, but "behavior-identical pure move" is only credible with the expanded
> Stage-0 characterization first — original staging was ROI-first, this revision
> is safety-first.
>
> ### Critical MRO hazards (Gemini, verified) — must be encoded in Stage 0
> - **Qt base severs the MRO chain.** `ExtrapolationWindow(QMainWindow, …Mixins)`
>   has `QMainWindow` **leftmost** (window.py:467). PySide6 C++ wrappers do NOT
>   cooperatively call `super()`, so any Qt lifecycle override (`closeEvent`,
>   `resizeEvent`, `__init__`) in a split mixin is **silently ignored**. → The
>   plan MUST forbid split mixins from overriding Qt event handlers (or audit for
>   dormant ones being ignored today).
> - **Splitting reverses definition precedence.** In the monolith a method at the
>   *bottom* shadows a duplicate at the *top*. Split sequentially into A(top) /
>   B / C(bottom) and composed `class Shim(A, B, C)`, left-to-right MRO makes
>   **A shadow C** — the opposite of the original. → Stage 0 must **strictly
>   prohibit duplicate method names across sibling mixins** (a test that fails on
>   any cross-sibling name collision).

## Current state (measured)

- `app_desktop/window.py` — **3197 lines**, `ExtrapolationWindow` with **~150
  methods**, composed of **7 mixins** (MRO order):
  `WindowLatexPdfMixin, WindowI18nMixin, WindowImagesMixin,
  WindowStatisticsMixin, WindowDataMixin, WindowFittingMixin,
  WindowExtrapolationMixin`.
- Mixin sizes (the god-files):
  - `window_statistics_mixin.py` — **1921** ← biggest
  - `window_extrapolation_mixin.py` — **1128**
  - `window_latex_pdf_mixin.py` — 969
  - fitting already split into 4 (`formatters` 561 / `residuals` 614 /
    `models` 673) behind a 67-line shim — **the proven pattern**.
  - `window_data_mixin.py` 646, `window_i18n_mixin.py` 423,
    `window_images_mixin.py` 388.
- `app_desktop/views/` (extrapolation/fitting/statistics/error/root_solving.py,
  ~3524 lines) already extracts **widget construction** via
  `build_*_mode_view(owner)` functions. The mixins hold **behavior**
  (run/format/handlers). The separation is: `views/` = build UI, mixins = drive
  it.

## Guiding constraints (why this is staged, not one refactor)

1. **Public API stable.** `window.py` must keep inheriting the same mixin names;
   external imports (`from app_desktop.window_* import Window*Mixin`) keep
   working. Follow the `WindowFittingMixin` shim: an empty subclass that composes
   split files and re-exports the original name. Zero caller changes per stage.
2. **MRO discipline.** Method-resolution order is load-bearing (some mixins
   override same-named methods). Any split must preserve left-to-right MRO;
   pin it explicitly and document the order (as the fitting shim does).
3. **Behavior-identical.** No logic changes inside a split — pure move. Verify
   with the existing per-mode desktop UI tests + full suite each stage.
4. **Surgical, reversible.** One mixin per PR. If a split reveals a real coupling
   bug, fix it in its own commit, not silently.
5. **Test coverage first.** Before splitting a mixin, confirm the per-mode UI
   test file exercises its public methods (statistics/extrapolation/fitting all
   have `test_desktop_*_ui.py`). Add characterization tests for any method with
   no coverage BEFORE moving it.

## Staged sequence (safest-first, one PR each)

### Stage 0 — Guardrails (prep) — **GO, but expanded per review**
- Characterization tests: for each mixin to split, list public methods + confirm
  coverage; fill gaps with thin output-pinning tests. No production change.
- **(review) MRO / provider-order snapshot:** capture `ExtrapolationWindow.__mro__`
  and each split's base order in a test so a re-order is caught.
- **(review) Shim overrides are NOT always empty:** `window_fitting_mixin.py:48`
  overrides `_on_fit_finished` and calls `super()` before adding fallback-history
  UI. Stage 0 must add checks for (a) duplicate method names across siblings,
  (b) intentional shim-level overrides, (c) **no `__init__` in split mixins**
  (construction order is load-bearing) — and a construction test proving signal
  slots exist before `build_*_mode_view()` runs.
- **(review) Import-stability is broader than `Window*Mixin`:** tests import
  internal helpers directly, e.g. `_statistics_raw_table_preserving_cells` from
  `window_statistics_mixin.py` (`test_desktop_statistics_ui.py:705`), and the
  release matrix names old FQNs (`test_release_test_matrix.py:70`). Any split
  must **re-export moved internals** from the original module OR update that
  evidence deliberately — Stage 0 enumerates these direct-import sites.
- Freeze the file-size ratchet baselines for the new split files.

### Stage 1 — Split `window_statistics_mixin.py` (1921 → ~4 files) — biggest win
Mirror the fitting shim. Suggested responsibility split (validate against the
actual method groupings before coding):
- `window_statistics_formatters_mixin.py` — result-text / CSV-row / snapshot
  rendering helpers (pure-ish).
- `window_statistics_modes_mixin.py` — per-mode execution + dispatch
  (`_run_statistics_mode` and the standard/bootstrap/hypothesis/time-series/
  matrix/grouped paths).
- `window_statistics_results_mixin.py` — worker-result handlers + plot wiring.
- `window_statistics_mixin.py` — 67-line shim composing the above, MRO-pinned,
  re-exporting `WindowStatisticsMixin`. Public import unchanged.
- **Verdict: CONDITIONAL-GO (review).** **`_on_stats_mode_change` lives in
  `window.py`, NOT in the statistics mixin** (its visibility logic touches
  `views/statistics.py:379` and is called from `workspace_controller.py:981`).
  Do NOT pull it into Stage 1 — either freeze it explicitly in `window.py` or
  make a separate stats-visibility stage. The snapshot/semantic-output path is
  the other tricky seam. Split stats into smaller PRs if the first is too large.

### Stage 2 — `window_extrapolation_mixin.py` (1128) — **NO-GO as written; re-scope (review)**
**This mixin is misnamed for splitting purposes: it is a cross-family run
controller, not extrapolation-only.** Its `run_calculation()` dispatches direct
statistics + fitting paths (`window_extrapolation_mixin.py:389`),
`_on_calc_finished()` handles statistics results (`:582`), and it owns the
root/error/statistics/fitting **unit collectors** (`:1035`). A naive
"extrapolation run" split would break stats/fitting/root/unit-propagation.
Re-scope as a **cross-family run-controller split** with full mode coverage:
first extract the pure formatters and the unit-collectors (self-contained), and
only then consider separating the dispatch — treating it as its own multi-PR
track, not a low-medium extrapolation task. F10's mode-switch/result-clear timing
must move verbatim. **Park until Stage 1 + 3 are done and characterized.**

### Stage 3 — Split `window_latex_pdf_mixin.py` (969 → ~2 files) — **GO (cleanest)**
- Separate compile-worker orchestration from PDF-preview/zoom UI.
- **(review, Gemini) Also extract the two workers.** `_TectonicInstallWorker`
  (`window_latex_pdf_mixin.py:55`) and `_LatexCompileWorker` (`:135`) are `QThread`
  subclasses defined *inside* this mixin, whereas all other workers
  (`CalcWorker`, `FitWorker`, `RootSolvingWorker`, …) live in `workers_qt.py`.
  Amend Stage 3 to move these two to `workers_qt.py` for architectural
  consistency (do it as part of, or just before, the split).
- **Risk: low.** Self-contained; good coverage in `test_update_*` /
  `test_latex_compile_*`.

### Stage 4 — Typed window facade `Protocol` — **NO-GO for Batch 10 (review)**
A `WindowFacade` Protocol would have to cover **182 distinct `owner.*` names**
across `app_desktop/views/*.py`, and the project already records broad desktop
statistics mypy as blocked by dynamic-mixin-attr debt (`task_plan.md:277`). One
giant Protocol is noisy and brittle. **Do not bundle into Batch 10.** If pursued
later, do it as narrow **per-view / per-helper Protocols**, as its own typing
spike — not a window-wide facade.

### Explicitly NOT in scope
- No "delegating controllers" rewrite / no MVC re-architecture. The mixin+shim
  composition is the target end-state — it already fits every file in one editor
  view and keeps the public API. A full controller rewrite is high-risk with no
  proven payoff and is **not recommended**.

## Effort / risk summary (post-review verdicts)

| Stage | File | Effort | Risk | Verdict |
|---|---|---|---|---|
| 0 | (tests + MRO/import characterization) | S-M | none | **GO — expanded** |
| 1 | statistics_mixin | M | medium | **CONDITIONAL-GO** (keep `_on_stats_mode_change` out; split into smaller PRs) |
| 3 | latex_pdf_mixin | S-M | low | **GO — cleanest** |
| 2 | extrapolation_mixin (run-controller) | L | med-high | **NO-GO as written** — re-scope as cross-family run-controller, park |
| 4 | Protocol facade | L | — | **NO-GO for Batch 10** — separate narrow typing spike |

**Revised recommendation (safety-first):**
1. **Stage 0** — build the characterization/MRO/import-stability guardrails first
   (this is what makes every later "pure move" provable). Do this next if Batch 10
   proceeds.
2. **Stage 3** (latex_pdf) — the cleanest, lowest-risk split; good second PR to
   validate the shim mechanics on real code.
3. **Stage 1** (statistics) — biggest win, but only after 0+3, and only with
   `_on_stats_mode_change` frozen in `window.py`; split into small PRs.
4. **Stage 2** (the run-controller) — re-scope and revisit LAST, or not at all.
5. **Stage 4** — out of scope.

Do NOT attempt a monolithic "decompose the whole window" PR. Order changed from
1→2→3 to **0 → 3 → 1 → (2 re-scoped)** on review: do the provably-safe splits
first, defer the cross-family run-controller.

## Open question for maintainer
- Proceed with Stages 0–3 now, or park Batch 10 (the god-class works, is tested,
  and the value is maintainability-only)? The per-stage payoff is real but purely
  structural — no user-facing change and no bug fixed.
