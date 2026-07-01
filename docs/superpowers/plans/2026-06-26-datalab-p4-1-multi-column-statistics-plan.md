# DataLab P4.1 Multi-Column Statistics Implementation Plan

Status: implemented and locally validated under no-Claude constraint
Date: 2026-06-26

## 1. Preconditions

- Approved spec:
  `docs/superpowers/specs/2026-06-26-datalab-p4-1-multi-column-statistics-spec.md`.
- Claude review is disabled by current user instruction.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse existing single-column statistics compute, semantic rows, CSV/LaTeX,
  plotting, workspace, and history/report infrastructure.

## 2. Key Design Decisions

1. Multi-column means "repeat the existing single-column statistics pipeline for
   an ordered list of value columns"; it does not compute cross-column
   relationships.
2. `statistics.value_column` remains backward-compatible. New
   `statistics.value_columns` is the canonical multi-column setting.
3. The first implementation uses one shared sigma column for all selected value
   columns. Per-column sigma mapping is deferred.
4. Semantic row keys must be column-scoped before entering snapshots/history
   compare so duplicate metric keys such as `mean` do not collide. User-facing
   labels stay unscoped; matching/source keys carry the column.
5. Desktop display should use existing result text/CSV setters and workbench
   snapshot capture paths.
6. Desktop statistics execution must converge onto the same core request path
   used by Web statistics. Do not keep adding behavior to the legacy direct
   `compute_statistics()` GUI path.

## 3. Slice P4.1-A: Core Multi-Column Helper

Goal: add UI-neutral core helpers that produce per-column statistics results by
reusing existing request builder and compute handler.

Likely files:

- `datalab_core/statistics.py`
- `tests/test_datalab_core_statistics.py`

Implementation:

- Add a small parser/normalizer for selected value columns:
  `normalize_statistics_value_columns(value_column, value_columns, headers)`.
- Add `build_multi_column_statistics_requests(...)` or equivalent that returns
  column-tagged `StatisticsRequestBatch` groups.
- Add `run_multi_column_statistics(...)` helper only if it avoids duplicated
  orchestration in Desktop/Web. If added, it should submit normal
  `ComputeJobRequest` objects and convert payloads through the existing
  `statistics_payload_to_compute_result()` adapter for legacy display helpers.
- Keep existing `build_statistics_requests()` and `run_statistics()` behavior
  unchanged for one-column callers.

Verification:

- Ordered selected columns.
- Empty multi-column list falls back to `value_column`.
- Duplicate and missing columns fail before calculation.
- Per-column results match separate `build_statistics_requests()` /
  `run_statistics()` calls.
- Shared sigma behavior for weighted mode.
- JSON no-float guard for any new wrapper payload.

## 4. Slice P4.1-B: Snapshot, CSV, And Render Integration

Goal: represent multi-column statistics in existing semantic statistics
snapshots without key collisions.

Likely files:

- `datalab_core/statistics.py`
- `tests/test_datalab_core_statistics.py`
- Possibly `app_desktop/workspace_controller.py` if snapshot capture needs a
  small adapter.

Implementation:

- Extend snapshot payload assembly to accept multiple column result entries.
- Add `source.value_columns`, `source.column_count`, and per-batch
  `source.value_column`, `source.column_index`, and `source.batch_index`.
- Column-scope semantic matching without extending the closed `AnalysisRow`
  schema: keep metric `key` unchanged, set `AnalysisRow.source` to the selected
  value column for metric rows only, and make statistics history comparison use
  `(source, key)` for metric alignment. Do not overwrite row-flag `source`
  values because outlier display uses them.
- Ensure `render_statistics_snapshot_outputs()` returns CSV headers including
  `column` when more than one value column exists.
- Keep one-column restored output byte-compatible where practical.
- Update `datalab_core.history_compare._compare_statistics()` or its row-index
  helper so multi-column rows align by column name plus metric. Do not rely on
  duplicate-key suffixes such as `mean#2`.

Verification:

- Snapshot JSON contains no floats.
- Rendered text has one column section per selected column.
- CSV includes `column`, `batch`, `metric`, `value`, `uncertainty` for
  multi-column and preserves existing headers for single-column unless an
  explicit compatibility decision changes it.
- History comparison sees distinct column-scoped metric rows.
- Reordered selected columns render in the user-selected order, while history
  comparison aligns by column identity and metric identity.
- P3.1 budget extractor can display multi-column statistics rows as diagnostics.

## 5. Slice P4.1-C: Desktop GUI And Workspace

Goal: expose multi-column selection in Desktop while preserving old workspaces.

Likely files:

- `app_desktop/views/statistics.py`
- `app_desktop/window_statistics_mixin.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/workbench_specs.py`
- `tests/test_desktop_statistics_ui.py`
- `tests/test_workspace_controller.py`
- `tests/test_desktop_gui_schema_scan.py`

Implementation:

- Relabel the value-column field as Value columns / 数值列.
- Accept comma-separated text in the existing compact control.
- Add a helper/detect action only if it can reuse existing input table metadata
  without introducing a large new widget.
- Store/restore `statistics.value_columns`; preserve `statistics.value_column`
  as first selected column for compatibility.
- Route execution through the P4.1-A/B core helpers.
- Replace the direct desktop `compute_statistics()` execution path for
  statistics runs with the core request/service path already used by
  `app_web.logic.statistics`. The legacy formatters may remain, but their
  inputs should come from `statistics_payload_to_compute_result()`.
- Use existing result text/CSV setters; do not create a new result tab.

Verification:

- GUI schema metadata/tooltips updated and language refresh works.
- Old workspace with `value_column` restores as one selected column.
- New workspace with `value_columns` restores all selected columns.
- Running the GUI path produces multi-column text and CSV.
- GUI schema scan remains clean.

## 6. Slice P4.1-D: LaTeX And Plots

Goal: export multi-column statistics without duplicating numeric formatting or
claiming cross-column analysis.

Likely files:

- `statistics_utils.py`
- `datalab_latex/latex_tables_common.py`
- `app_desktop/window_statistics_mixin.py`
- `shared/plotting.py` or existing statistics plotting wrappers if metadata
  labels are enough.
- Focused LaTeX/plot tests.

Implementation:

- Prefer one table per selected column using existing statistics table builder.
- If multiple input columns are present in the input table, each per-column
  LaTeX table should still use the selected value column and its shared sigma
  source consistently; do not emit unrelated input columns as if they were part
  of that column's statistical sample.
- Add column heading/caption suffixes.
- Reuse current dcolumn/siunitx preamble and numeric formatting.
- Generate existing per-column plots with column-aware labels/metadata.
- Do not add overlay or covariance plots.
- Update workspace/report-bundle plot capture if needed so all statistics
  gallery images are attached with column-aware metadata. Current workspace
  capture has a known single-active-image path, so this is not optional for
  P4.1-D.

Verification:

- LaTeX option matrix covers at least one multi-column dcolumn and one siunitx
  case.
- No raw unsafe column names in LaTeX; names are escaped.
- Plot count and labels match selected columns.
- Workspace capture/restore and report-bundle export/preview retain every
  per-column plot, not just `result_plot_bytes`.
- Existing single-column LaTeX tests continue to pass.

## 7. Slice P4.1-E: Integration Docs, Examples, And Release Gates

Goal: make the feature discoverable and prevent regressions in adjacent P3
features.

Likely files:

- `docs/desktop/statistics.*.md`
- `docs/web/statistics.*.md` if Web is explicitly deferred.
- `examples/workspaces/statistics.datalab` or a new template example if the
  example generator supports it.
- `docs/TEST_MATRIX.md`
- History/report/budget focused tests.

Implementation:

- Document comma-separated value columns and explicit non-goals.
- Add/update an example workspace that computes independent summaries for
  several numeric columns.
- Add release-matrix evidence for core, Desktop, LaTeX, plot, workspace, and
  P3 integration behavior.

Verification:

- Example workspace opens as a template and runs.
- Focused docs tests pass if docs guardrails exist.
- Report bundle export/preview can carry the multi-column snapshot.
- History compare and budget dashboard still work.

## 8. Review And Quality Gates

Before implementation:

- Codex main-thread review of spec and plan.
- Non-Claude subagent review of spec and plan.
- Gemini/Antigravity review only if available and responsive; do not block
  indefinitely. Claude must not be used under the current user instruction.

Per slice:

- Write or update focused tests first.
- Run focused pytest for touched behavior.
- Run GUI schema scan for Desktop changes.
- Run Ruff, compileall, feasible mypy, and whitespace checks.
- Run non-Claude read-only review after each substantive slice.

Final local validation:

- Precision-preserving worker/direct desktop regressions: 2 passed.
- P4.1 focused statistics gate: 130 passed, 226 deselected.
- P4.1 plus history/report-bundle gate: 183 passed, 226 deselected.
- Scoped Ruff, compileall, and diff-check passed for touched P4.1 files.
- Claude was not used by user instruction. A non-Claude Codex subagent review
  did not return before timeout and was closed without a verdict.

Implementation notes:

- Desktop statistics now uses the core request/service path and rebuilds display
  sample values from original parsed rows through `StatisticsRequestBatch`
  source-row IDs, so display/plot/LaTeX values are not truncated to compute DPS.
- Workspace capture/restore stores all active statistics gallery PNGs with
  column metadata.
- History entries store plot metadata only in `rendered_cache`; report-bundle
  export resolves those metadata paths against workspace attachments so bundles
  can include all per-column statistics plots without embedding binary data in
  history JSON.

## 9. Stop Conditions

- If existing statistics snapshot schema cannot safely represent multiple
  columns, stop and revise the spec before adding a new schema.
- If GUI width/scroll behavior regresses, stop before making the control visible.
- If LaTeX requires duplicated number-formatting logic, stop and extract a
  shared helper instead.
- If a request would require covariance/correlation, defer to P4.2.
