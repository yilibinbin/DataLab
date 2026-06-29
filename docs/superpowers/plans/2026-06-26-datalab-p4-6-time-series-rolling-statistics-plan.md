# DataLab P4.6 Time-Series Smoothing And Rolling Statistics Implementation Plan

Status: draft for non-Claude review
Date: 2026-06-26

Spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-6-time-series-rolling-statistics-spec.md`

## 1. Preconditions

- Claude review is disabled by current user instruction.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse existing statistics value-column collection, precision settings,
  semantic snapshots, CSV/LaTeX/plot/report boundaries, workspace saving, and
  parallel/resource settings.
- Reuse shared input-section parsing and safe numeric conversion, but add a
  P4.6 collector shape that preserves raw time/index strings. Do not force
  non-numeric time labels through the all-numeric statistics parser.
- Do not implement forecasting, time-width windows, interpolation, automatic
  sorting, or Savitzky-Golay in the first visible release.

## 2. Key Design Decisions

1. Time-series smoothing is a statistics workflow branch:
   `workflow_mode = "time_series_rolling"`.
2. `series_method` is separate from `stats_mode`; do not overload the existing
   statistics-method selector.
3. First release supports `rolling_mean`, `rolling_median`, `rolling_std`, and
   `ewma`.
4. Windows are row-count based. Optional time/index columns are used for labels,
   provenance, and monotonicity diagnostics, not sorting or time-width windows.
5. Rolling arithmetic uses mpmath under `precision_guard`; it must not route
   through NumPy/Pandas floats.
6. Initial uncertainty propagation is conservative: rolling mean may propagate
   independent sigmas; other methods emit explicit unavailable diagnostics.
7. Plots use shared plot specs/renderers, not GUI-local Matplotlib code.

## 3. Slice P4.6-A: Core Rolling/EWMA Engine

Goal: add a UI-neutral, precision-safe series engine.

Likely files:

- New `datalab_core/statistics_time_series.py` or equivalent.
- `datalab_core/statistics_compute.py` only if shared helper extraction is
  needed for median/std parity.
- `datalab_core/statistics.py` only for workflow dispatch hooks.
- `tests/test_datalab_core_statistics_time_series.py`.

Implementation:

- Add option normalization for:
  - `series_method`;
  - selected value columns;
  - optional time/index column;
  - `window_size`, `alignment`, `min_periods`;
  - rolling std denominator;
  - EWMA `alpha` or `span`, and `adjust`.
- Add a P4.6 input collector that:
  - parses selected value/sigma columns with existing safe numeric parsing;
  - preserves optional time/index labels as raw strings;
  - records optional numeric time/index parse results only for monotonicity
    diagnostics;
  - preserves source row IDs and raw-cell diagnostics.
- Add shared helper(s) for median and standard deviation definitions if current
  statistics code keeps them private. Existing ordinary statistics and P4.6
  should use one implementation where practical.
- Implement row-count rolling window generation for right/center alignment.
- Implement rolling mean, median, and standard deviation with mpmath.
- Implement EWMA adjusted and unadjusted with mpmath.
- Preserve source row IDs and effective window source IDs.
- Store observed input values/uncertainties per point so plots and reports can
  regenerate from semantic snapshots alone.
- Emit diagnostics for insufficient windows, invalid options, non-monotonic
  time/index metadata, and unavailable uncertainty propagation.
- Return a JSON-safe payload with numeric strings and integer counts.

Verification:

- Reference tests for rolling mean/median/std with right and center alignment.
- EWMA formula tests for adjusted/unadjusted modes and span-to-alpha
  conversion.
- Sample/population rolling std parity with existing statistics definitions.
- Invalid method, invalid window, and invalid alpha/span are rejected before
  payload/snapshot creation with diagnostics. Insufficient windows in otherwise
  valid requests yield `null` point values and point-level diagnostics.
- Rolling-mean uncertainty tests cover `sqrt(sum(sigma_j^2)) / n`, recorded
  `uncertainty_assumptions`, no-sigma behavior, explicit multi-column
  value-to-sigma mapping, and invalid/negative/non-finite sigma diagnostics.
- Median/std/EWMA with sigma mappings emit `series_uncertainty_not_available`
  diagnostics rather than fabricated uncertainties.
- JSON floats are absent/rejected.

## 4. Slice P4.6-B: Statistics Workflow Dispatch And Validators

Goal: integrate the core engine into the statistics family without duplicating
ordinary statistics paths.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/statistics_time_series.py`
- `tests/test_datalab_core_statistics.py`
- `tests/test_datalab_core_statistics_time_series.py`

Implementation:

- Add `validate_statistics_time_series_payload()`.
- Add result-cache kind `statistics_time_series`.
- Add workflow dispatch for `workflow_mode == "time_series_rolling"` while
  keeping `stats_mode` as ordinary statistics-method state.
- Reuse P4.1 value-column ordering and source-row normalization.
- Use the P4.6 series collector for time/index preservation. When nullable
  collection exists, integrate it through the shared collector rather than
  custom parsing. Until then, value/sigma cells fail closed on invalid numeric
  input while time/index labels remain raw strings.
- Add `validate_statistics_time_series_snapshot()` or a similarly closed
  snapshot validator.

Verification:

- Payload validator catches malformed point lists, mismatched source-row IDs,
  JSON floats, incompatible window/EWMA option combinations, and invalid
  diagnostics.
- Validator enforces `status`/`value` invariants, `skipped_source_row_ids`
  presence, and observed-series fields required for plot regeneration.
- Validator enforces sigma mapping consistency, column-level
  `uncertainty_assumption` parity with root `uncertainty_assumptions`, and
  absence of uncertainty values for unsupported methods.
- Multi-column payload preserves selected order.
- Old statistics workspaces and jobs continue to run ordinary statistics.

## 5. Slice P4.6-C: Semantic Snapshot, Text, CSV

Goal: make time-series outputs durable and exportable from semantic data.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/results.py` only if generic row helpers are needed.
- `tests/test_datalab_core_statistics.py`
- `tests/test_workspace_controller.py`

Implementation:

- Add a statistics snapshot branch for `mode == "time_series_rolling"`.
- Store structured `time_series` entries and diagnostic rows.
- Add `render_statistics_time_series_snapshot_outputs(snapshot)` returning
  `(markdown_text, csv_rows, csv_headers)`.
- Route `render_statistics_snapshot_outputs()` to the time-series renderer for
  this mode.
- Regenerate text and CSV from `snapshot["time_series"]`; do not parse rendered
  text or rendered caches.
- Ensure `snapshot["time_series"]` contains observed values/uncertainties as
  well as rolling/EWMA outputs so plots and reports do not require raw input
  tables.

Verification:

- Snapshot round-trip has no JSON floats.
- Text and CSV regenerate from semantic snapshot.
- CSV includes column, row, time, method, value, uncertainty, status, and window
  source rows.
- History comparison row identity is column/method-aware.

## 6. Slice P4.6-D: Desktop GUI And Workspace

Goal: expose rolling/smoothing in Desktop statistics settings.

Likely files:

- `app_desktop/views/statistics.py`
- `app_desktop/window_statistics_mixin.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/workbench_specs.py`
- `tests/test_desktop_statistics_ui.py`
- `tests/test_workspace_controller.py`
- `tests/test_desktop_gui_schema_scan.py`

Implementation:

- Add or reuse a statistics workflow selector with a Time-series / rolling
  branch.
- Add `series_method` selector and dynamically visible controls:
  - value columns;
  - optional sigma/uncertainty column mapping for `rolling_mean`;
  - optional time/index column;
  - rolling window size, alignment, min periods;
  - rolling std denominator only for `rolling_std`;
  - EWMA alpha/span and adjust only for `ewma`.
- Hide irrelevant descriptive/weighted/bootstrap/hypothesis controls while this
  workflow is active.
- Route execution through the core time-series request path.
- Store/restore workflow, selected columns, time/index column, method, window,
  sigma mappings, EWMA, denominator configuration, and uncertainty assumption
  in workspace files.
- Keep legacy workspaces restoring normal statistics mode.

Verification:

- GUI schema metadata, help text, and language refresh.
- Running Desktop time-series workflow produces text, CSV, semantic snapshot,
  and optional plots.
- Workspace save/restore preserves configuration and output.
- GUI schema scan remains clean with no hidden required controls left active.

## 7. Slice P4.6-E: LaTeX And Plots

Goal: export series outputs without duplicating formatting or plotting logic.

Likely files:

- `datalab_latex/latex_tables_common.py` or a statistics-specific helper.
- `shared/plotting.py`
- `app_desktop/window_statistics_mixin.py`
- `tests/test_latex_generation_consistency.py`
- `tests/test_plotting_backend.py`

Implementation:

- Add LaTeX table generation from semantic time-series entries.
- Reuse existing dcolumn/siunitx numeric formatting helpers.
- Escape value/time column names and method labels.
- Add shared `StatisticsTimeSeriesPlotSpec` or a compatible extension to the
  existing statistics plot spec.
- Render observed series plus rolling/smoothed line; add uncertainty band only
  when uncertainty values exist.
- Preserve plot metadata for workspace/report export.

Verification:

- LaTeX compiles for dcolumn and siunitx modes.
- Uncertainty digits, input precision, and digit grouping are respected.
- Plot specs render nonblank PNGs for row-index and explicit time/index cases.
- Workspace/report bundle preserves all plot attachments.

## 8. Slice P4.6-F: History, Report, Budget, Docs, Examples

Goal: make the workflow consistent with the rest of the P3/P4 surfaces.

Likely files:

- `datalab_core/history_compare.py`
- `datalab_core/report_bundle.py`
- `app_desktop/history_compare_panel.py`
- `docs/desktop/statistics.en.md`
- `docs/desktop/statistics.zh.md`
- `docs/web/statistics.en.md` only if Web route is included
- `examples/README.md`
- `tools/generate_example_workspaces.py`
- `docs/TEST_MATRIX.md`

Implementation:

- Add same-family history comparison for method/options/final-value/diagnostic
  deltas.
- Ensure report bundle export/preview includes time-series tables and plots
  from semantic snapshots.
- Add budget-dashboard diagnostic extraction only; no cross-family total budget.
- Add example workspace(s):
  - rolling mean/median trend example;
  - EWMA smoothing example.
- Update user docs and test matrix.

Verification:

- History comparison does not collide rows across columns/methods.
- Report bundle export/preview has no stale rendered-cache dependency.
- Example workspaces open and compute.
- Documentation covers window alignment, min periods, EWMA alpha/span, and
  uncertainty limitations.

## 9. Release Gate For P4.6

No user-visible P4.6 release should ship until slices A-F pass:

- core formulas and validators;
- semantic snapshot/text/CSV;
- Desktop GUI/workspace;
- LaTeX/plot/export;
- history/report/budget/docs/examples;
- focused GUI schema scan and relevant release test-matrix entries.
