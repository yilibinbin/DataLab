# DataLab P4.4 Bootstrap Confidence Intervals Implementation Plan

Status: draft for non-Claude review
Date: 2026-06-26

Spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-4-bootstrap-confidence-intervals-spec.md`

## 1. Preconditions

- Claude review is disabled by current user instruction.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse existing statistics value-column collection, statistics formulas,
  semantic snapshots, CSV/LaTeX/plot/report boundaries, and parallel settings.
- Do not implement BCa, weighted bootstrap, grouped bootstrap, hypothesis
  tests, or Web UI in this slice unless a later reviewed plan changes scope.

## 2. Key Design Decisions

1. Bootstrap is a statistics workflow branch:
   `workflow_mode = "bootstrap_confidence_intervals"`.
2. First release uses percentile bootstrap only. BCa is deferred because it
   needs jackknife acceleration and additional numerical validation.
3. First-release targets are `mean`, `median`, `trimmed_mean`, `std`, and
   `variance`.
4. Multi-column behavior follows P4.1: each selected value column is
   bootstrapped independently and output order follows user selection.
5. Deterministic parallelism is mandatory when a seed is provided. Worker count
   and process/thread selection must not change seeded results.
6. Distribution metadata reuses `datalab.monte_carlo_distribution_summary`.
   Because that schema currently stores 2.5/50/97.5 percentiles, first-release
   bootstrap confidence level is fixed to 95%. Arbitrary confidence levels are a
   later shared distribution-schema extension.
7. Existing sigma/weighted controls are not part of P4.4 first release.
8. Persisted snapshots store compact summaries only, not raw bootstrap
   replicate arrays.

## 3. Slice P4.4-A: Core Bootstrap Engine

Goal: add a UI-neutral, deterministic bootstrap core for statistics targets.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/statistics_compute.py` only if existing statistic helpers need
  extraction for parity.
- Possibly new `datalab_core/statistics_bootstrap.py` if keeping bootstrap
  helpers separate improves maintainability.
- `tests/test_datalab_core_statistics.py` or a new focused
  `tests/test_datalab_core_statistics_bootstrap.py`.

Implementation:

- Add `normalize_statistics_bootstrap_options(...)` for target statistic,
  confidence level, resample count, seed, sample/population, and trim fraction.
- Extract or add a shared scalar-statistic evaluator that exactly matches
  existing `compute_statistics()` definitions for eligible targets.
- Add deterministic percentile bootstrap:
  - stable replicate index order;
  - stable per-replicate index generation when seeded;
  - no Python float conversion for statistic values;
  - bounded cancellation checks.
- Add compact distribution summary creation using the same field names and
  validation constraints as error-propagation Monte Carlo summaries. Prefer
  extracting a shared distribution-summary builder used by both error
  propagation and bootstrap instead of copying the private Monte Carlo helper.
- Use `precision_guard(precision_digits)`.
- Return a JSON-safe payload with numeric strings and integer counts.

Verification:

- Parity tests against `compute_statistics()` for all eligible targets.
- Seeded repeatability in serial mode.
- Degenerate input produces zero-width intervals where mathematically expected.
- Invalid target, non-95% confidence level in the first release,
  too-small/too-large resample count, and insufficient sample size fail with
  clear diagnostics.
- JSON floats are rejected or absent from the payload.

## 4. Slice P4.4-B: Parallel Execution

Goal: make bootstrap resampling use the existing parallel backend without
changing results.

Likely files:

- `datalab_core/statistics.py` or `datalab_core/statistics_bootstrap.py`
- `datalab_core/parallel_options.py` only if existing option normalization needs
  a statistics call site, not a new policy.
- `shared/parallel_backend.py` should not need changes unless a defect is found.
- `tests/test_parallel_backend.py` only if shared backend behavior changes.
- Focused bootstrap parallel tests.

Implementation:

- Convert `request.options.parallel` into `ParallelConfig` through an existing
  shared mapping helper. If the only available mapper is a module-private helper
  such as the root-solving engine's internal mapper, extract a public shared
  `ParallelConfig` mapping helper first; do not duplicate parallel option
  parsing in statistics.
- Run replicate chunks through `ParallelMapExecutor.map_pure(...,
  workload=ParallelWorkload.CPU_MPMATH)`.
- Preserve deterministic output by either:
  - pre-generating replicate index tuples before parallel map; or
  - deriving one independent deterministic seed per replicate and sorting
    results by replicate index.
- Store the RNG schedule/algorithm label in the payload and snapshot metadata.
- Respect nested parallel policy and serial fallback.
- Keep process payloads top-level and picklable. Do not rely on an implicit
  pickling fallback because the current shared backend raises `TypeError` for
  non-picklable process callables or payloads.

Verification:

- Same seed and options produce identical CI/distribution in serial,
  process-preferred, and auto modes.
- Parallel controls are passed through from Desktop job construction.
- Nested parallel policy can force serial without changing results.
- Process-preferred execution uses picklable top-level tasks and does not raise
  backend pickling errors.

## 5. Slice P4.4-C: Payload Validators And Semantic Snapshot

Goal: make bootstrap output durable and fail-closed.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/results.py` only if a generic row helper is needed.
- `tests/test_datalab_core_statistics.py`
- `tests/test_history_compare.py`
- `tests/test_workspace_controller.py`

Implementation:

- Add `validate_statistics_bootstrap_payload()`.
- Add `validate_statistics_bootstrap_snapshot()`.
- Add `build_statistics_bootstrap_result_snapshot(...)` or extend the existing
  statistics snapshot builder with a bootstrap branch.
- Store structured `bootstrap` entries plus diagnostic `AnalysisRow` summaries.
- Add `render_statistics_bootstrap_snapshot_outputs(...)` or extend
  `render_statistics_snapshot_outputs()` to route by
  `mode == "bootstrap_confidence_intervals"`.
- Add CSV regeneration from semantic snapshot.
- Ensure `AnalysisRow` metric summaries are column-scoped without extending the
  closed row schema.

Verification:

- Snapshot round-trip has no JSON floats.
- Malformed embedded distribution summaries fail closed.
- RNG metadata, target-specific options, and source-row ID count parity are
  required and validated.
- Text and CSV are regenerated from semantic snapshot.
- Multi-column bootstrap rows do not collide in history comparison.

## 6. Slice P4.4-D: Desktop GUI And Workspace

Goal: expose bootstrap confidence intervals in Desktop statistics settings.

Likely files:

- `app_desktop/views/statistics.py`
- `app_desktop/window_statistics_mixin.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/workbench_specs.py`
- `tests/test_desktop_statistics_ui.py`
- `tests/test_workspace_controller.py`
- `tests/test_desktop_gui_schema_scan.py`

Implementation:

- Add a separate statistics workflow selector if not already present for P4.2
  and P4.3. Do not overload `stats_mode_combo`.
- Add bootstrap controls: target statistic, fixed 95% confidence display,
  resample count, optional seed, sample/population policy for `std`/`variance`,
  and trim fraction for `trimmed_mean`.
- Hide or disable irrelevant weighted/sigma controls in bootstrap workflow.
- Route execution through the core bootstrap request path.
- Store/restore bootstrap workflow, target statistic, resample count, seed,
  sample/population policy, and trim fraction in workspace config.
- Keep old statistics workspaces restoring normal statistics mode.

Verification:

- GUI schema metadata, help text, and language refresh.
- Running Desktop bootstrap produces text, CSV, semantic snapshot, and optional
  plots.
- Workspace save/restore preserves bootstrap configuration and output.
- `std`/`variance` runs honor restored sample/population policy, and
  `trimmed_mean` runs honor restored trim fraction.
- GUI schema scan remains clean.

## 7. Slice P4.4-E: LaTeX And Plots

Goal: export bootstrap summaries without duplicating number-formatting or plot
logic.

Likely files:

- `datalab_latex/latex_tables_common.py` or a statistics-specific helper.
- `statistics_utils.py` only if legacy entrypoints require a small bridge.
- `shared/plotting.py` only if the existing Monte Carlo distribution plot
  helper needs a label extension.
- `app_desktop/window_statistics_mixin.py`
- `tests/test_latex_generation_consistency.py`
- `tests/test_plotting_backend.py`

Implementation:

- Add bootstrap LaTeX table generation from semantic snapshot entries.
- Reuse existing dcolumn/siunitx numeric formatting helpers.
- Escape column names and method labels.
- Add one distribution plot per selected column using
  `monte_carlo_distribution_plot_spec_from_summary()` and
  `render_monte_carlo_distribution_plot_from_spec()`.
- Keep plot percentile lines at the 95% distribution percentiles. Arbitrary
  confidence-level support is deferred with the shared plot/schema extension.

Verification:

- LaTeX compiles for dcolumn and siunitx modes.
- Numeric digit grouping and uncertainty display policy remain centralized.
- Plot count and metadata match selected columns.
- CJK-safe plotting remains unaffected.

## 8. Slice P4.4-F: History, Report Bundle, Budget, Docs, Examples

Goal: complete first-class integration.

Likely files:

- `app_desktop/workspace_controller.py`
- `datalab_core/history_compare.py`
- `datalab_core/uncertainty_budget.py`
- `app_desktop/report_bundle_export.py`
- `datalab_latex/report_bundle.py`
- `docs/desktop/statistics.en.md`
- `docs/desktop/statistics.zh.md`
- `docs/TEST_MATRIX.md`
- `tools/generate_example_workspaces.py`
- `examples/workspaces/statistics-bootstrap.datalab` or equivalent generated
  template

Implementation:

- Add same-family history comparison for bootstrap endpoints and CI overlap.
- Add report-bundle semantic CSV/LaTeX/plot export from bootstrap snapshots.
- Expose bootstrap rows in budget dashboard as diagnostics only, not physical
  variance contributions.
- Add a small example workspace with deterministic seed.
- Update bilingual docs and test matrix.

Verification:

- History compare fixture for overlapping/non-overlapping bootstrap CIs.
- Report-bundle round-trip with bootstrap plot attachment.
- Budget extractor emits diagnostics but no cross-family total.
- Example workspace opens as template and calculates.
- Docs guardrails pass.

## 9. Review And Quality Gates

Before implementation:

- Codex main-thread review of spec and plan.
- Codex subagent read-only review of spec and plan.
- Gemini/Antigravity review only if available, focused, and responsive.
- Claude must not be used under the current user instruction.
- `git diff --check` for the spec, plan, and planning files.

Per implementation slice:

- Write focused tests first where practical.
- Run focused pytest for touched behavior.
- Run GUI schema scan for Desktop changes.
- Run Ruff, compileall, feasible mypy, and scoped diff-check.
- Run a non-Claude read-only review after substantive code changes.
- Fix accepted findings before starting the next slice.

## 10. Stop Conditions

- If target-statistic formulas cannot be proven identical to existing
  statistics output, hide that target and revise the spec before shipping it.
- If deterministic seeded results differ between serial and parallel execution,
  stop before exposing parallel bootstrap.
- If LaTeX requires local duplicated numeric formatting, stop and extract/reuse
  a shared helper.
- If the GUI requires overloading `stats_mode` with workflow names, stop and add
  a separate workflow field.
- If report/workspace restore needs rendered-cache parsing, stop and add a
  semantic renderer instead.
