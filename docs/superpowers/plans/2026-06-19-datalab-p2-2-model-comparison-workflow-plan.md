# Implementation Plan: P2.2 Model Comparison Table Workflow

Date: 2026-06-19

Status: Planning slice accepted; P2.2A core-only implementation started on 2026-06-19.

Parent plan: `docs/superpowers/plans/2026-06-18-datalab-analysis-enrichment-implementation-plan.md`

## Overview

P2.2 needs a model-comparison table, but the exact reusable multi-fit producer required by the parent plan does not currently exist. The existing multi-fit path, `fitting.model_selector.auto_fit_dataset()`, is not suitable because it enumerates `AUTO_MODELS`, appends `_sequence_model()`, and returns `best_model` by AIC. P2.2 should therefore introduce a separate explicit comparison workflow: users choose the fits to compare, the orchestrator runs one existing single-fit producer per selected entry, and the table renders stored `FitResult` metrics as sortable evidence without choosing a winner.

## Requirements

- Use a user-selected candidate list and an explicit comparison orchestrator.
- Do not call `auto_fit_dataset()` or expose automatic model selection through Desktop, Web, docs, workspace config, CLI, or exports.
- Return one `FitResult` per successful candidate from existing single-fit producers.
- Consume `FitResult.chi2`, `FitResult.reduced_chi2`, `FitResult.aic`, `FitResult.bic`, `FitResult.rmse`, and `FitResult.r2`; do not duplicate metric formulas.
- Exclude `_sequence_model()` from P2.2 because it uses sequence-acceleration heuristics rather than comparable least-squares fit metrics.
- Do not emit `best_model`, `winner`, recommendations, or automatic highlighting. Sorting is allowed; selection is not.
- Cover Desktop, Web, CSV, LaTeX, workspace snapshot/config, plot, docs, and tests.
- Keep `tests/test_auto_fit_removed.py` and legacy auto-fit migration guardrails green.

## Audit Findings

- Safe single-fit producers:
  - `FitRunner.fit()` handles explicit `custom` and `self_consistent` model problems.
  - `fit_linear_model()` handles one explicit built-in linear-basis definition at a time.
  - `datalab_core.fitting.run_fitting()` runs a single direct fitting request and serializes one `FitResult`.
- Unsafe multi-fit path:
  - `auto_fit_dataset()` loops over `AUTO_MODELS`, optional extras/customs, and `_sequence_model()`.
  - It computes `best_model` by minimum AIC.
  - `_sequence_model()` constructs heuristic AIC/BIC/RMSE/R2 fields and stores a method-specific uncertainty note, so it is not comparable to ordinary least-squares `FitResult` rows.
- Current fitting output adapters already read official metrics from `FitResult` fields:
  - Desktop markdown/CSV: `WindowFittingFormattersMixin`.
  - Desktop LaTeX: `app_desktop.fitting_latex_writer`.
  - Web display/CSV/LaTeX: `app_web.logic.fitting`.
  - P2.1A diagnostics: `fitting.diagnostic_formatting`.
- Workspace semantic snapshot support is currently statistics-focused; P2.2 must add a fitting-comparison semantic snapshot instead of relying only on rendered markdown/CSV/LaTeX caches.

## Architecture Changes

- New explicit comparison core module: `fitting/model_comparison.py`
  - Define candidate/result dataclasses and row builders.
  - Run one candidate at a time through existing single-fit producers.
  - Build comparison rows only from returned `FitResult` fields and diagnostics/warnings.
- Optional core service wrapper: `datalab_core/fitting_comparison.py`
  - Convert JSON-safe candidate payloads into explicit `ComputeJobRequest` or `ModelProblem` calls.
  - Return a `ResultEnvelope` payload with comparison rows and serialized per-candidate `FitResult`s.
  - Keep this separate from `auto_identifier` and `auto_fit_dataset()`.
- Shared formatting boundary: `fitting/comparison_formatting.py`
  - CSV rows, visible table rows, and LaTeX table data consume comparison rows.
  - No chi-square/AIC/BIC/RMSE/R2 formulas here.
- Desktop adapter changes:
  - `app_desktop/views/fitting.py`: add explicit selected-fits comparison controls if Desktop UI is included in the slice.
  - `app_desktop/window_fitting_models_mixin.py`: collect selected candidate specs and dispatch the comparison job.
  - `app_desktop/window_fitting_formatters_mixin.py`: render comparison rows through the shared formatter.
  - `app_desktop/workspace_controller.py`: capture/restore comparison config and semantic snapshot.
- Web adapter changes:
  - `app_web/templates/fit.html`: add explicit selected-fits comparison input and sortable table.
  - `app_web/logic/fitting.py`: dispatch comparison candidates through the core comparison wrapper and reuse shared formatting.
- LaTeX:
  - Add a shared non-UI comparison table builder under `datalab_latex` or a Qt-free fitting formatter module.
  - Desktop and Web call the same builder.
- Plot:
  - Extend shared fitting plot specs only if overlay plots are in scope.
  - Allowed plot behavior: overlay selected successful fit curves/residuals and show the same comparison rows as plot/table metadata.
  - Disallowed plot behavior: best-fit highlighting, AIC winner annotation, or sequence-acceleration overlays.

## Implementation Steps

### Phase 1: Contract And Guardrails

1. **Add comparison contract tests** (File: `tests/test_fit_model_comparison.py`)
   - Action: Create RED tests for explicit candidate order, one `FitResult` per candidate, failure rows, and sentinel metric consumption.
   - Why: Locks the workflow before implementation.
   - Dependencies: None.
   - Risk: Low.

2. **Add auto-fit non-use guard** (File: `tests/test_fit_model_comparison.py`)
   - Action: Monkeypatch `fitting.model_selector.auto_fit_dataset`, `fitting.model_selector._sequence_model`, `fitting.model_selector.AUTO_MODELS`, and `fitting.auto_models.AUTO_MODELS` access to fail if P2.2 comparison calls them.
   - Why: Prevents reviving automatic model selection through a new name.
   - Dependencies: Step 1.
   - Risk: Medium.

3. **Keep public auto-fit removal tests mandatory** (File: `docs/TEST_MATRIX.md`)
   - Action: Add P2.2 evidence requiring `tests/test_auto_fit_removed.py` and `tests/test_workspace_auto_fit_migration.py`.
   - Why: Public UI/docs/export guardrails must remain green.
   - Dependencies: None.
   - Risk: Low.

P2.2A implementation note: the first code slice is intentionally limited to the
UI-neutral orchestrator and shared row formatting. Desktop, Web, LaTeX,
workspace snapshot, and plot integration remain deferred because no public
entry point is added in P2.2A.

### Phase 2: Explicit Orchestrator

4. **Define candidate/result types** (File: `fitting/model_comparison.py`)
   - Action: Add `FitComparisonCandidate`, `FitComparisonEntry`, `FitComparisonRow`, and `FitComparisonResult`.
   - Why: Makes selected-fit comparison explicit and testable.
   - Dependencies: Phase 1.
   - Risk: Low.

5. **Run explicit candidates through single-fit producers** (File: `fitting/model_comparison.py`)
   - Action: For built-in linear-basis candidates, call `fit_linear_model()` with the selected definition; for custom/self-consistent candidates, call `FitRunner.fit()`.
   - Why: Reuses existing fit producers and preserves P0.7 metric consolidation.
   - Dependencies: Step 4.
   - Risk: Medium.

6. **Build comparison rows from stored metrics only** (File: `fitting/model_comparison.py`)
   - Action: Copy `free_parameter_count`, `chi2`, `reduced_chi2`, `aic`, `bic`, `rmse`, `r2`, warnings, and status from candidate metadata and `FitResult`.
   - Why: Prevents formula drift.
   - Dependencies: Step 5.
   - Risk: Medium.

7. **Reject or defer non-comparable candidates** (File: `fitting/model_comparison.py`)
   - Action: Exclude `_sequence_model()` entirely and mark future non-least-squares/heuristic entries as out of scope unless a later spec defines comparability.
   - Why: Keeps the table scientifically honest.
   - Dependencies: Step 5.
   - Risk: Low.

### Phase 3: Core Payload And Shared Formatting

8. **Add JSON-safe comparison service wrapper** (File: `datalab_core/fitting_comparison.py` or `datalab_core/fitting.py`)
   - Action: Normalize selected candidate payloads, call the explicit orchestrator, and serialize per-candidate `FitResult`s through existing fit serialization.
   - Why: Gives Desktop/Web/workspace one stable payload.
   - Dependencies: Phase 2.
   - Risk: Medium.

9. **Add shared comparison CSV/table rows** (File: `fitting/comparison_formatting.py`)
   - Action: Produce rows with `candidate_id`, `order`, `model_label`, `status`, `free_parameters`, `chi2`, `reduced_chi2`, `aic`, `bic`, `rmse`, `r2`, `warnings`, and `error`.
   - Why: Desktop and Web must not duplicate row formatting.
   - Dependencies: Step 8.
   - Risk: Low.

10. **Add shared LaTeX comparison table** (File: `datalab_latex/latex_tables_fitting.py` or existing Qt-free fitting LaTeX module)
    - Action: Render the same comparison rows with dcolumn/siunitx/group-size behavior aligned to fitting LaTeX.
    - Why: LaTeX output must match CSV/visible rows.
    - Dependencies: Step 9.
    - Risk: Medium.

### Phase 4: Desktop And Web Surfaces

11. **Desktop selected-fits UI** (Files: `app_desktop/views/fitting.py`, `app_desktop/window_fitting_models_mixin.py`)
    - Action: Add explicit comparison controls such as “Add current fit to comparison” and “Run selected-fit comparison”; default row order stays user order.
    - Why: Users must choose the entries; the app must not infer them.
    - Dependencies: Phase 3.
    - Risk: High.

12. **Desktop output/export/workspace** (Files: `app_desktop/window_fitting_formatters_mixin.py`, `app_desktop/window_fitting_residuals_mixin.py`, `app_desktop/workspace_controller.py`)
    - Action: Render comparison table, CSV, LaTeX, optional overlay plot, and semantic `result_snapshot` from the shared comparison payload.
    - Why: P2.2 is an output-surface feature, not only a core helper.
    - Dependencies: Step 11.
    - Risk: High.

13. **Web selected-fits UI** (Files: `app_web/templates/fit.html`, `app_web/logic/fitting.py`)
    - Action: Add explicit selected-fit comparison form fields and render sortable evidence rows plus CSV/LaTeX downloads.
    - Why: The current web fitting path already has fitting parity and should not drift.
    - Dependencies: Phase 3.
    - Risk: High.

14. **Plot surface** (Files: `shared/plotting.py`, `fitting/plot_fitting.py`, desktop/web plot adapters)
    - Action: If implemented in P2.2, add a shared comparison overlay spec for successful selected fits. Suppress overlay for multi-dimensional or failed candidates and keep the table primary.
    - Why: Plot behavior must share the same data as the table and remain evidence-only.
    - Dependencies: Steps 11-13.
    - Risk: Medium.

### Phase 5: Docs And Evidence

15. **Update user docs without auto-fit language** (Files: `docs/desktop/fitting.*.md`, `docs/web/fitting.*.md`)
    - Action: Describe “selected-fit comparison” and sortable evidence rows. Avoid public phrases guarded by `tests/test_auto_fit_removed.py`, including automatic selection claims.
    - Why: Product copy must not imply automatic fitting has returned.
    - Dependencies: Phase 4.
    - Risk: Medium.

16. **Update implementation evidence** (File: `docs/TEST_MATRIX.md`)
    - Action: Add P2.2 rows for core orchestrator, Desktop/Web parity, CSV/LaTeX, workspace restore, plot behavior, and auto-fit removal guardrails.
    - Why: Keeps release verification auditable.
    - Dependencies: All prior phases.
    - Risk: Low.

## Testing Strategy

- Unit tests:
  - `tests/test_fit_model_comparison.py`
  - `tests/test_fit_statistics.py`
  - `tests/test_fit_diagnostics.py`
- Desktop tests:
  - `tests/test_fitting_markdown_display.py`
  - `tests/test_fitting_latex_writer.py`
  - `tests/test_desktop_custom_fit_ui.py`
  - `tests/test_workspace_controller.py`
- Web tests:
  - `tests/test_app_web_fitting_latex.py`
  - Web fitting template tests in `tests/test_auto_fit_removed.py`
- Plot tests:
  - `tests/test_plotting_backend.py`
  - `tests/test_web_plot_generation.py` if web overlay/gallery is added.
- Guardrail tests:
  - `tests/test_auto_fit_removed.py`
  - `tests/test_workspace_auto_fit_migration.py`
  - `tests/test_auto_fit_cancellation_and_timeout.py` remains allowed to cover the retained internal auto selector, but P2.2 must not call it.

## Validation Commands

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_fit_model_comparison.py tests/test_fit_statistics.py tests/test_fit_diagnostics.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_fitting_markdown_display.py tests/test_fitting_latex_writer.py tests/test_app_web_fitting_latex.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_controller.py -k "fitting or comparison or result_snapshot"
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_plotting_backend.py tests/test_web_plot_generation.py -k "fitting or comparison"
QT_QPA_PLATFORM=offscreen pytest -q tests/test_release_test_matrix.py
python -m ruff check fitting datalab_core datalab_latex app_desktop app_web tests
python -m compileall -q fitting datalab_core datalab_latex app_desktop app_web tests
python -m mypy fitting/model_comparison.py fitting/comparison_formatting.py datalab_core/fitting_comparison.py
git diff --check
```

## Risks & Mitigations

- **Risk**: P2.2 accidentally revives automatic model selection.
  - Mitigation: Explicit non-use tests for `auto_fit_dataset()`, `_sequence_model()`, `fitting.model_selector.AUTO_MODELS`, and `fitting.auto_models.AUTO_MODELS`; keep public auto-fit removal tests in the required gate.
- **Risk**: Metric formulas are duplicated in comparison rows.
  - Mitigation: Sentinel `FitResult` tests where residuals cannot derive the expected chi-square/AIC/BIC/RMSE/R2 values.
- **Risk**: Non-comparable methods appear beside least-squares fits.
  - Mitigation: Allow only explicitly supported single-fit producers; defer sequence acceleration and heuristic metrics to a separate comparability spec.
- **Risk**: Users interpret sorted rows as an automatic recommendation.
  - Mitigation: Default to user order, allow manual column sorting, and avoid winner/best/recommended labels.
- **Risk**: Desktop/Web comparison forms diverge.
  - Mitigation: Put candidate normalization and row formatting in shared non-UI modules; adapters only collect form/UI state and render rows.
- **Risk**: Workspace snapshots grow too large.
  - Mitigation: Store compact comparison rows plus serialized `FitResult`s only for selected candidates; cap row count or require an explicit warning if a later product decision allows large lists.

## Success Criteria

- [ ] Users can compare only explicitly selected fits.
- [ ] Each successful comparison entry contains one `FitResult`.
- [ ] Official metrics are read from `FitResult` fields only.
- [ ] `_sequence_model()` and heuristic sequence metrics are excluded.
- [ ] No `best_model`, winner, or recommendation is emitted.
- [ ] Desktop, Web, CSV, LaTeX, workspace restore, and plot behavior consume the same comparison payload.
- [ ] `tests/test_auto_fit_removed.py` stays green.
- [ ] P2.2 evidence is recorded in `docs/TEST_MATRIX.md`.
