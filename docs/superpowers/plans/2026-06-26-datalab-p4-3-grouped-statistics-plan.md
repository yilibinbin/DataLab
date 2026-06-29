# DataLab P4.3 Grouped Statistics Implementation Plan

Status: finalized after Codex and Antigravity Gemini Pro review under no-Claude policy
Date: 2026-06-26

## 1. Preconditions

- Approved roadmap:
  `docs/superpowers/specs/2026-06-20-datalab-p3-p4-analysis-roadmap-spec.md`.
- P4.1 multi-column statistics is implemented and locally validated.
- P4.2 covariance/correlation matrix is implemented through a pre-scalar-parse
  statistics workflow branch and accepted under Codex/Gemini review.
- P4.3 spec:
  `docs/superpowers/specs/2026-06-26-datalab-p4-3-grouped-statistics-spec.md`.
- Current user constraint: do not use Claude for review.
- Preserve the dirty worktree. Do not clean, revert, stage, commit, package, or
  publish unrelated files.

## 2. Architecture Decisions

1. Grouped statistics remains inside the statistics family and uses
   `JobMode.STATISTICS`, but workflow selection and statistics method stay
   separate: `workflow_mode == "grouped_statistics"` and `stats_mode` remains
   `mean` / `descriptive` / `weighted_sigma`.
2. Per-group computation reuses existing `build_statistics_requests()` /
   `run_statistics()` behavior. No second statistics math engine.
3. A group-aware input collector is mandatory because current statistics
   parsing produces all-numeric rows and cannot preserve text group labels.
4. First-release group order is first appearance in source rows.
5. First-release group comparisons/deltas are deferred. Hypothesis tests are
   deferred to P4.5, and descriptive group deltas require a later explicit
   reviewed slice.
6. Use dedicated grouped payload/snapshot branches rather than encoding group
   identity through display labels.
7. Grouped statistics requests must dispatch before
   `datalab_core.statistics.run_statistics()` parses scalar `values`, because
   grouped requests carry raw table rows and a text group column.

## 3. Slice P4.3-A: Group-Aware Input And Core Payload

Goal: collect text group labels plus high-precision numeric value columns and
compute per-group statistics through the existing core.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/statistics_compute.py` only if a pure helper belongs there
- `shared/input_normalization.py` or existing shared parsing boundary
- `app_desktop/window_data_mixin.py` only for adapter hooks that preserve raw
  group cells
- `tests/test_datalab_core_statistics.py`
- `tests/test_shared_input_sections.py` or focused collector tests

Implementation:

- Add `normalize_grouped_statistics_columns(...)` for group/value/sigma column
  validation.
- Add a shared raw statistics table collector instead of reusing Desktop's
  `_statistics_raw_table()` directly. It must preserve raw string cells,
  headers, rectangular row shape, blank middle cells for delimiter-preserving
  inputs, and stable source row IDs.
- The shared collector may use `shared.parsing.parse_clipboard_tabular()` for
  delimiter/header/raw-row handling, but must not use its float-converted
  `rows` as the numeric source. High-precision numeric parsing remains the
  responsibility of the statistics collector/core path.
- Add a group-aware collector returning:
  - normalized headers;
  - ordered group labels;
  - source row IDs;
  - per value column grouped `mp.mpf` values;
  - per value column grouped sigma values when weighted mode applies;
  - row-level diagnostics for blank group/value cells.
- Support blank-cell behavior only for input forms that preserve empty cells.
  Whitespace-split text cannot represent empty middle cells reliably; tests must
  use manual-table or delimited-input evidence for blank-cell cases.
- Explicitly forbid implementing the grouped collector by calling
  `_collect_fitting_dataset()` or `_parse_generic_table()`, because those paths
  coerce/reject text group labels and cannot preserve empty middle cells.
- Prefer extracting/reusing a raw-cell helper around the shared parsing boundary
  (`shared.parsing.parse_clipboard_tabular` or equivalent raw-row path) and
  direct manual table/canonical-table cell access for GUI data.
- Reuse existing uncertainty/numeric parsing for selected numeric value/sigma
  cells.
- Add `run_grouped_statistics()` and a `run_statistics()` branch for
  `workflow_mode == "grouped_statistics"` before scalar `_parse_values()` so
  text group labels are not rejected by the normal single-column path.
- Add `validate_statistics_grouped_payload()` at core output.

Verification:

- text group labels work;
- group order follows first appearance;
- per-group result parity with isolated single-column runs;
- multi-value-column grouping preserves selected-column order;
- blank group labels and blank value cells produce documented diagnostics;
- blank-value tests use an input mode that preserves empty cells, while
  whitespace text behavior is explicitly documented;
- direct tests prove that whitespace-only input is not the blank-middle-cell
  regression source;
- malformed numeric text fails;
- weighted mean uses the same sigma semantics per group;
- JSON-float and malformed payload rejection.

## 4. Slice P4.3-B: Semantic Snapshot, Text/CSV, History

Goal: make grouped results durable without parsing rendered text.

Likely files:

- `datalab_core/statistics.py`
- `datalab_core/history_compare.py`
- `app_desktop/workspace_controller.py`
- `tests/test_datalab_core_statistics.py`
- `tests/test_history_compare.py`
- `tests/test_workspace_controller.py`

Implementation:

- Extend statistics snapshot construction for `statistics_grouped`.
- Add dedicated `groups` list and grouped `source` metadata.
- Store group-level all-row IDs separately from per-column included/skipped
  source-row IDs so blank value cells cannot make row provenance ambiguous.
- Add `validate_statistics_grouped_snapshot()` and call it before snapshot
  build returns, restore rendering, history compare, LaTeX, plotting, and report
  export.
- Add grouped branch to `render_statistics_snapshot_outputs()` with long-form
  CSV headers:
  `group,column,batch,metric,value,uncertainty`.
- Extend history comparison:
  - align by group label + value column + metric;
  - report added/removed groups and columns;
  - emit diagnostics for mode/option mismatches;
  - fail closed on malformed grouped snapshots.
- Add `statistics_grouped` to the workspace semantic-kind allowlist.

Verification:

- snapshot JSON no-float;
- deterministic text/CSV render;
- restore renderer works without result-cache dictionaries;
- history compare aligns reordered groups by group label, not ordinal only;
- validators reject invalid numeric strings in embedded statistics payloads,
  preserve existing standard `"nan"` sentinels for unavailable descriptive
  metrics, and require future descriptive-delta rows to be finite;
- grouped vs ungrouped statistics comparison is metadata-only/unavailable.

## 5. Slice P4.3-C: LaTeX And Plots

Goal: export grouped statistics without duplicated formatting.

Likely files:

- `statistics_utils.py`
- `datalab_latex/latex_tables_common.py` or a small grouped statistics LaTeX
  helper
- `shared/plotting.py`
- `tests/test_latex_generation_consistency.py`
- `tests/test_plotting_backend.py`

Implementation:

- Add grouped statistics LaTeX writer:
  - preferably a long summary table using existing summary-row builders and
    numeric cell formatters;
  - no copied numeric formatting logic;
  - escape group labels and column names.
- Add grouped mean overview plot spec when `mean` and `std_mean` are available.
- Avoid creating excessive per-group plot galleries by default; per-group full
  plots can be a later option.
- Store plot metadata with group/value-column context.
- Do not implement reference-group deltas in the LaTeX or plot slice; leave the
  reserved CSV/delta schema inactive until a later comparison slice.

Verification:

- siunitx and dcolumn output compile-safety tests;
- labels with LaTeX-special characters are escaped;
- grouped mean overview plot emits PNG bytes and fails closed for missing
  metrics;
- CJK label smoke if existing plot tests support it.

## 6. Slice P4.3-D: Desktop GUI, Workspace, Report Bundle

Goal: expose grouped statistics in Desktop with minimal new controls.

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

- Add or reuse a statistics workflow selector for `Grouped statistics`; do not
  put the grouped workflow into the existing statistics-method combo that stores
  `stats_mode`.
- Add a group-column field shown only in grouped mode.
- Reuse value columns, sigma column, sample/population, weighted variance, and
  trim controls where applicable.
- Route grouped execution through the core grouped helper before Desktop calls
  `_collect_fitting_dataset()` or any other all-numeric collector. The Desktop
  branch should mirror the matrix/time-series raw-row workflow and pass raw
  headers/rows/source IDs into the statistics service.
- Add `statistics_grouped` branches to cached display refresh and plot restore
  paths.
- Update exact desktop/workspace integration points:
  - `app_desktop.workspace_controller._SEMANTIC_SNAPSHOT_KIND_BY_FAMILY`;
  - `app_desktop.workspace_controller._plot_mode_from_snapshot`;
  - `app_desktop.window.ExtrapolationWindow._refresh_display_format`;
  - report-bundle export/preview paths that regenerate semantic CSV/LaTeX and
    attach plot binaries.
- Capture/restore grouped config in workspace state.
- Regenerate grouped LaTeX from semantic snapshots for report bundles.

Verification:

- GUI schema scan has bound labels/tooltips and no horizontal overflow;
- mode switching shows/hides group controls correctly;
- GUI click-run test for a small grouped table;
- workspace round-trip restores config and grouped results;
- stale cached display refresh uses the grouped renderer;
- history restore uses grouped semantic output;
- report bundle includes grouped CSV/LaTeX/plot attachments regenerated from the
  semantic snapshot.

## 7. Slice P4.3-E: Docs, Examples, Release Matrix

Goal: make grouped statistics discoverable and release-testable.

Likely files:

- `docs/desktop/statistics.en.md`
- `docs/desktop/statistics.zh.md`
- `examples/workspaces/statistics.datalab` or a dedicated grouped example
- `tools/generate_example_workspaces.py`
- `docs/TEST_MATRIX.md`
- `tests/test_desktop_example_workspace_menu.py`
- `tests/test_release_test_matrix.py`

Implementation:

- Document group column semantics, first-appearance order, blank-cell behavior,
  and no-hypothesis-test scope.
- Add an example with text groups and at least two value columns.
- Update release-matrix evidence for core, GUI, LaTeX, plot, workspace/history,
  and report-bundle gates.

Verification:

- example opens as template and runs;
- docs guard tests pass;
- release matrix references concrete grouped-statistics gates.

## 8. Non-Claude Review Plan

Claude is disabled by current user instruction.

Before implementation:

1. Codex main-thread review of this spec and plan.
2. Codex subagent review focused on parser boundary, schema compatibility,
   statistics correctness, GUI maintainability, LaTeX/plot/report risks when
   subagent capacity is available; otherwise record main-thread Codex review as
   the Codex gate and do not block on thread-limit/tooling failure.
3. Antigravity Gemini Pro review. If unavailable, failing, or off-target,
   record as a tool limitation rather than a PASS.

No implementation starts until accepted findings from available non-Claude
reviews are reconciled into the spec/plan.

Per implementation slice:

- Write focused tests before or with implementation.
- Run focused pytest for touched behavior.
- Run GUI schema scan for Desktop changes.
- Run Ruff, compileall, feasible mypy, and diff checks.
- Use non-Claude review for substantive slices.

## 9. Stop Conditions

- If text group labels require duplicating parser logic, stop and extract a
  shared collector.
- If grouped snapshots cannot be validated without parsing display labels, stop
  and revise the schema.
- If grouped LaTeX duplicates numeric formatting, stop and extract/reuse a
  shared helper.
- If GUI grouped mode causes left-panel overflow or stale hidden controls, stop
  before continuing feature work.
- If hypothesis-test semantics are needed, defer to P4.5 instead of adding them
  here.
