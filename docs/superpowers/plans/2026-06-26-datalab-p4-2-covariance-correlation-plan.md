# DataLab P4.2 Covariance And Correlation Matrix Implementation Plan

Status: finalized after Codex and Antigravity Gemini Pro review
Date: 2026-06-26

## 1. Preconditions

- Approved roadmap:
  `docs/superpowers/specs/2026-06-20-datalab-p3-p4-analysis-roadmap-spec.md`.
- P4.1 multi-column statistics is implemented and locally validated.
- P4.2 spec:
  `docs/superpowers/specs/2026-06-26-datalab-p4-2-covariance-correlation-spec.md`.
- Current user constraint: do not use Claude for review; use Codex plus
  Antigravity Gemini Pro.
- Preserve the dirty worktree. Do not clean, revert, stage, commit, package, or
  publish unrelated files.

## 2. Architecture Decisions

1. Implement matrix statistics inside the statistics family, not as a separate
   one-off module. The GUI entry point is the statistics panel.
2. Add a dedicated matrix payload and matrix semantic snapshot branch instead
   of flattening matrix cells into scalar `AnalysisRow` metric rows.
3. Keep the existing `JobMode.STATISTICS` service boundary and dispatch on
   `workflow_mode == "covariance_correlation"` rather than introducing a new
   job mode. This matches the established statistics workflow split used by
   bootstrap, hypothesis tests, and time-series smoothing. `stats_mode` remains
   the scalar statistics method selector and must not carry workflow names.
4. Keep listwise deletion as the default and the only first-release policy that
   may mark correlation metadata as budget-candidate data.
5. Support pairwise deletion as an explicit user option, but mark it
   `budget_eligible=false` because pairwise matrices may not be
   positive-semidefinite.
6. Defer weighted covariance. Existing sigma weighting is not a reviewed row
   weight model for multivariate covariance.
7. Reuse existing numeric formatting, LaTeX preamble, plot font, workspace,
   history, and report-bundle boundaries.

## 3. Slice P4.2-A: Core Matrix Compute

Goal: add UI-neutral covariance/correlation computation with JSON-safe payloads.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/statistics_compute.py` if the pure math helper belongs there
- `shared/input_normalization.py` or the current shared input-bundle boundary if
  nullable matrix collection needs a reusable parser hook
- `app_desktop/window_data_mixin.py` only if a Desktop adapter is needed to
  preserve blank manual-table cells before numeric parsing
- `tests/test_datalab_core_statistics.py`
- `tests/test_shared_input_sections.py` or a focused parser test if a shared
  nullable collector is added

Implementation:

- Add a matrix-specific nullable row collector before exposing missing-data
  policies. It must return selected-column `mp.mpf | None` values and stable
  source row IDs. It must not rely on the existing all-numeric
  `_parse_generic_table()` result for pairwise/listwise deletion because that
  path rejects missing/unparseable cells before matrix code runs.
- Treat empty preserved cells and explicitly supported missing markers as
  `None`; reject arbitrary text, `NaN`, and infinity as input errors.
- Add a small dataclass or request helper for matrix settings:
  selected columns, missing policy, denominator policy, precision, source row
  IDs.
- Route matrix requests through `ComputeJobRequest(mode=JobMode.STATISTICS, ...,
  inputs["workflow_mode"]="covariance_correlation")` and add the branch inside
  `run_statistics()` before the scalar statistics branch.
- Refactor `run_statistics()` so `workflow_mode` is inspected before scalar
  parsing. The existing `_parse_values()` and `_parse_source_row_ids(count=
  len(values))` calls must move into the branches that operate on a
  one-dimensional numeric series. The matrix branch must consume its own raw
  selected-column rows through the nullable matrix collector, otherwise
  missing cells would be rejected before pairwise/listwise policy code runs.
- Reuse `normalize_statistics_value_columns()` for ordered column validation,
  then require at least two columns in matrix mode.
- Add a row collector that returns selected-column `mp.mpf` values plus source
  row IDs without converting display values back from compute-DPS strings.
- Use mpmath arithmetic and stable summation (`mp.fsum`); do not use Python
  `float`, NumPy float arrays, or formatted request/display strings for matrix
  math.
- Implement listwise matrix compute:
  - reject empty included rows;
  - compute means, covariance, correlation, counts, denominators;
  - emit diagnostics for zero variance and insufficient counts.
- Implement pairwise matrix compute:
  - compute each cell from pair-specific included rows;
  - store per-cell counts and denominators;
  - emit diagnostics for null cells and non-budget eligibility.
- Add payload normalization that rejects Python floats and non-finite numeric
  strings.
- Add `validate_statistics_matrix_payload()` and require it at core output.
  Validation must cover matrix shape, row/column count, numeric-string
  finiteness, count/denominator consistency, symmetry, correlation bounds,
  diagonal/null rules, and `correlation_components`.
- Validation must also enforce the budget metadata gate: `budget_eligible` is
  false unless the policy is listwise and every correlation cell is finite.
  Listwise zero-variance columns therefore produce diagnostics and
  `budget_eligible=false`, not a budget-candidate matrix with null cells.

Verification:

- Nullable input collection preserves source row IDs and distinguishes missing
  cells from malformed text.
- Hand-calculated 2x2 and 3x3 listwise examples.
- Pairwise deletion with unequal counts.
- Pairwise correlation stores pair-local means/variances sufficient to audit
  off-diagonal correlation cells.
- Sample/population denominator differences.
- Zero-variance correlation null cells and diagnostics.
- High-precision cancellation regression.
- Duplicate, missing, and one-column selection errors.
- JSON no-float/no-nonfinite guard.

## 4. Slice P4.2-B: Semantic Snapshot, Render, CSV, History

Goal: make matrix results durable and comparable without parsing display text.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/history_compare.py`
- `app_desktop/workspace_controller.py`
- `tests/test_datalab_core_statistics.py`
- `tests/test_history_compare.py`
- `tests/test_workspace_controller.py`

Implementation:

- Extend statistics snapshot construction to accept `statistics_matrix`
  payloads.
- Add `statistics_matrix` to the workspace semantic-kind allowlist for the
  statistics family.
- Add `snapshot["matrices"]` and `snapshot["correlation_metadata"]` while
  preserving scalar `AnalysisRow` only for diagnostics.
- Add `validate_statistics_matrix_snapshot()` and call it before snapshot build
  returns, before restore rendering, before history comparison, before plotting,
  and before report export. Do not depend on generic JSON normalization alone.
- Extend `render_statistics_snapshot_outputs()` with a matrix branch:
  deterministic text plus long-form CSV headers
  `matrix,row_column,column,value,count,denominator`.
- Extend history comparison for two matrix statistics snapshots:
  - align by matrix kind plus row/column names;
  - compare numeric cells with existing precision guard policy;
  - report added/removed columns and mode/policy mismatches as diagnostics;
  - fail closed when the matrix shape is malformed.
- Ensure scalar P4.1 statistics snapshots and P4.2 matrix snapshots do not
  collide in same-family comparison.

Verification:

- Snapshot JSON no-float.
- Restore renderer emits covariance and correlation matrices.
- CSV long form is deterministic.
- History compare aligns reordered selected columns by name.
- Malformed matrix snapshots fail closed with diagnostics.

## 5. Slice P4.2-C: LaTeX And Plotting

Goal: export matrix results using existing formatting and shared plotting.

Likely files:

- `statistics_utils.py`
- `datalab_latex/latex_tables_common.py` or a new small
  `datalab_latex/latex_tables_statistics_matrix.py`
- `shared/plotting.py`
- `tests/test_latex_generation_consistency.py`
- `tests/test_plotting_backend.py`

Implementation:

- Add a matrix LaTeX writer that emits covariance and correlation tables.
- Reuse `_format_table_value()` and existing dcolumn/siunitx helpers for
  numeric cells.
- Use safe centered text cells for null values so dcolumn documents compile.
- Prefer `\multicolumn{1}{c}{--}` for null cells in numeric columns.
- Add a correlation heatmap spec/renderer. Prefer extracting a generic helper
  from the fitting correlation heatmap rather than duplicating rendering logic.
- Validate square/symmetric/unit-diagonal correlation matrices before plotting.
- Suppress the heatmap with a diagnostic when pairwise/null-cell results are not
  complete finite matrices.
- Store heatmap metadata using the existing plot-gallery fields:
  `role=statistics`, `plot_key=statistics.correlation_heatmap`, and selected
  column metadata.

Verification:

- siunitx and dcolumn matrix LaTeX tests.
- Null-cell dcolumn compile-safety test.
- Heatmap PNG bytes for valid matrix.
- Fail-closed heatmap tests for malformed shape, non-finite values, bad
  diagonal, and out-of-range correlations.
- CJK label smoke test if labels contain CJK text.

## 6. Slice P4.2-D: Desktop GUI, Workspace, Report Bundle

Goal: expose the matrix workflow in Desktop without adding duplicate controls.

Likely files:

- `app_desktop/views/statistics.py`
- `app_desktop/window.py`
- `app_desktop/window_statistics_mixin.py`
- `app_desktop/workers_core.py`
- `app_desktop/workers_qt.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/report_bundle_export.py`
- `tests/test_desktop_statistics_ui.py`
- `tests/test_app_desktop_workers_core.py`
- `tests/test_desktop_gui_schema_scan.py`
- `tests/test_desktop_history_panel.py`

Implementation:

- Add `Covariance/correlation matrix` to the statistics workflow selector. Do
  not add it to `stats_mode_combo`; that combo remains the scalar method
  selector.
- Add a missing-data policy combo shown only in matrix mode:
  listwise default, pairwise optional.
- Give the missing-data policy combo schema metadata and help text:
  `datalab_schema_key="statistics.matrix.missing_policy"`,
  `datalab_schema_choices=True`, and a tooltip explaining listwise vs pairwise
  deletion.
- Reuse the existing sample/population checkbox for denominator mode, with
  tooltip text updated in matrix mode.
- Hide or disable sigma, weighted variance, trim, and scalar-method controls in
  matrix workflow mode.
- Route matrix execution through the new core helper. Do not compute matrix
  values in GUI formatting code.
- In matrix workflow mode, bypass GUI/worker paths that call
  `_parse_generic_table()` or otherwise reduce the table to all-numeric scalar
  values before request construction. The Desktop request builder must package
  raw selected-column cell strings, headers, and source row IDs for the core
  nullable matrix collector so preserved blanks/missing markers reach the
  matrix workflow intact.
- Display matrix text/CSV through existing result setters.
- Add a `statistics_matrix` branch wherever the desktop currently refreshes
  scalar-only cached results, including display-format refresh paths.
- Generate LaTeX and heatmap when the existing output checkboxes request them.
- Capture/restore matrix workflow mode in workspace config and semantic result
  snapshot.
- Ensure report-bundle export includes matrix text/CSV/LaTeX and heatmap
  attachment through the existing attachment resolver.
- Update workspace plot-mode fallback so `statistics_matrix` restores to the
  statistics image gallery and preserves `statistics.correlation_heatmap`
  metadata.
- Regenerate report-bundle matrix LaTeX from the semantic snapshot. A cached
  `latex_source` may be carried as rendered cache, but it is not authoritative.

Verification:

- GUI schema scan has no missing help affordances and no horizontal overflow.
- `tests/test_desktop_statistics_ui.py` verifies the matrix workflow entry,
  the missing-data policy combo schema key/choices/tooltip, and visibility
  behavior.
- Matrix controls visibility toggles correctly when the mode changes.
- GUI click-run test for a small listwise matrix.
- Workspace round-trip restores mode, selected columns, missing policy, result
  text, CSV, and heatmap.
- Report-bundle export includes the heatmap when generated.

## 7. Slice P4.2-E: Docs, Examples, And Gate Wiring

Goal: make the feature discoverable and release-testable.

Likely files:

- `docs/desktop/statistics.en.md`
- `docs/desktop/statistics.zh.md`
- `docs/web/statistics.*.md` only to mention Desktop-only status if needed
- `examples/workspaces/statistics.datalab` or a new matrix example workspace
- `tools/generate_example_workspaces.py`
- `docs/TEST_MATRIX.md`
- `tests/test_desktop_example_workspace_menu.py`
- `tests/test_release_test_matrix.py`

Implementation:

- Document listwise vs pairwise deletion, sample/population denominator, and
  the weighted-covariance deferral.
- Add a small example workspace with three correlated columns and a matrix
  calculation.
- Mark example workspaces as templates as existing examples do.
- Add release-matrix evidence for core, GUI, LaTeX, plot, workspace/history, and
  report-bundle behavior.

Verification:

- Example opens as template and runs.
- Docs guard tests pass.
- Release test matrix mentions P4.2 gates without adding stale commands.

## 8. Non-Claude Review Plan

Claude is explicitly disabled by current user instruction.

Before implementation:

1. Codex main-thread review of this spec and plan.
2. Codex subagent or local read-only review focused on schema, math, GUI, and
   maintainability risks.
3. Antigravity Gemini Pro adversarial review. If the tool fails or times out,
   record the tool limitation and do not count it as a PASS.

No implementation starts until accepted findings from available non-Claude
reviews are reconciled into the spec/plan.

Per implementation slice:

- Write focused tests before or with the implementation.
- Run focused pytest for touched behavior.
- Run GUI schema scan for Desktop changes.
- Run Ruff, compileall, feasible mypy, and diff checks.
- Use non-Claude review for substantive slices.

## 9. Stop Conditions

- If matrix output requires duplicating numeric LaTeX formatting, stop and
  extract/reuse a shared helper first.
- If GUI matrix mode causes left-panel overflow or hidden controls, stop before
  continuing feature work.
- If pairwise metadata is accidentally exposed as budget-eligible, stop and fix
  the semantic metadata gate.
- If weighted covariance is requested during this slice, defer it to a separate
  reviewed plan.
- If malformed matrix snapshots can render as valid numbers, stop and harden
  validation before adding GUI integration.
