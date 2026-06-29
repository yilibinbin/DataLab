# DataLab P4.3 Grouped Statistics Spec

Status: finalized after Codex and Antigravity Gemini Pro review under no-Claude policy
Date: 2026-06-26

## 1. Goal

Add grouped statistics to the existing statistics module. Users choose one
group/category column and one or more numeric value columns; DataLab computes
the existing statistics summary independently for each group and produces
durable text, CSV, LaTeX, plots, workspace/history snapshots, and report-bundle
outputs.

P4.3 must reuse the existing single-column statistics core and the P4.1
multi-column orchestration pattern. It must not create a second statistics
engine.

## 2. Non-Goals

- No hypothesis tests, p-values, ANOVA, pairwise significance tests, or
  nonparametric tests. Those belong to P4.5.
- No automatic group-column selection.
- No automatic merging of nearly equal labels such as `A`, `a`, and ` A ` beyond
  documented cell normalization.
- No weighted group comparison model beyond the existing per-group weighted
  mean mode.
- No Web UI in the first implementation slice unless a separate reviewed plan
  adds it.

## 3. Input Semantics

### 3.1 Group-Aware Collection

Current statistics parsing produces fully numeric `mp.mpf` rows and therefore
cannot represent a text category column. P4.3 requires a group-aware input
collector before GUI exposure:

- The collector reads the active input bundle or file/text source into raw cells
  while preserving stable source row IDs.
- It reuses the shared input-normalization/parsing boundary where possible, but
  it must preserve raw string cells for high-precision parsing. Helpers such as
  `shared.parsing.parse_clipboard_tabular()` may be used for delimiter,
  rectangular-grid, header, and raw-row handling, but its float-converted
  `rows` output must not become the grouped statistics numeric source.
- Desktop's current `_statistics_raw_table()` is insufficient as the grouped
  collector because it uses whitespace splitting and cannot preserve empty
  middle cells. P4.3 should introduce a shared raw statistics table collector
  and route grouped execution through it; matrix/time-series migration to that
  helper may be a follow-up unless needed for this slice.
- The selected group column is read as text after the same safe cell cleanup
  used for headers/raw cells.
- Selected value columns are parsed through the existing uncertainty/numeric
  parsing path, preserving `mp.mpf` precision and optional sigma values.
- Unsupported numeric text, `NaN`, and infinity remain errors.
- Blank group cells are excluded from grouped computation and reported as
  diagnostics. They are not silently merged into a synthetic group.
- Blank value cells are excluded only for that value column and group, with
  row-count diagnostics. Nonblank malformed value cells fail the calculation.
- Blank-cell semantics are supported only for input forms that preserve empty
  cells, such as the manual table, tab-delimited text, semicolon/comma CSV, or
  an already-normalized workspace canonical table. Whitespace-split text cannot
  reliably represent an empty middle cell and must not be used as the
  blank-cell regression source.

### 3.2 Required Controls

Statistics configuration must keep two separate concepts:

- workflow: normal statistics, covariance/correlation matrix, or grouped
  statistics;
- statistics method: arithmetic mean, descriptive statistics, or weighted mean.

Grouped statistics is therefore represented by a workflow field, tentatively
`workflow_mode = "grouped_statistics"`, while the existing `stats_mode` keeps
its current method values such as `mean`, `descriptive`, and `weighted_sigma`.
Do not overload `stats_mode` with the grouped workflow name.

Required user inputs:

- group column;
- one or more value columns;
- statistics type: arithmetic mean, descriptive statistics, or weighted mean;
- sample/population setting where already applicable.

Existing controls reused:

- value columns from P4.1;
- sigma column, when weighted mean mode is selected;
- sample/population checkbox;
- trim fraction for descriptive statistics.

New controls:

- group column text field or selector;
- optional group order policy, initially fixed to first appearance unless a
  later slice adds sorted order.

## 4. Group Semantics

Group labels are normalized by:

1. stripping leading/trailing whitespace and zero-width/bidi control characters
   through the shared raw-cell cleanup;
2. preserving case and internal spaces;
3. rejecting empty labels as missing group labels.

Default group order is first appearance in the input rows. This keeps output
stable for user-curated tables and avoids locale-dependent sorting. Later sorted
ordering may be added only with a separate UI/schema decision.

Each selected value column is grouped independently. A row can contribute to
value column `A` while being absent from value column `B` if `B` is blank and
the collector supports blank value cells.

## 5. Computation

For each selected value column and group:

1. Build the same statistics request that a single-column ungrouped run would
   use for that group's numeric values.
2. Submit it through `JobMode.STATISTICS` / `run_statistics()`.
3. Convert results through `statistics_payload_to_compute_result()` where
   legacy display helpers need the legacy dictionary shape.
4. Attach source metadata: group label, group index, value column, selected
   source row IDs, and input row count.

The per-group result must equal running the existing single-column statistics
pipeline on only that group's rows with the same options.

The grouped workflow must dispatch before the scalar `values` parser in
`datalab_core.statistics.run_statistics()`, because grouped requests carry
headers/raw rows/value-column names rather than a single top-level `values`
sequence. This mirrors the P4.2 matrix branch and prevents the standard
statistics parser from rejecting text group labels before grouped collection
runs.

Minimum group-size policy:

- The existing statistics core remains authoritative. For example, sample
  variance warnings for `n < 2` come from the existing core.
- P4.3 adds group-level diagnostics when a group has no numeric values for a
  selected column.
- Groups with at least one numeric value are retained so the core can emit the
  same warnings/results as an ungrouped run would.

## 6. Optional Descriptive Deltas

Initial group comparison is descriptive only:

- no significance claims;
- no p-values;
- no confidence intervals for between-group differences unless a later reviewed
  slice adds them.

Reference-group UI and descriptive delta rows are deferred from the first
visible P4.3 release. The initial grouped workflow delivers grouped summaries,
exports, plots, workspace/history/report integration, and diagnostics only. The
docs and tests must make clear that between-group comparisons are descriptive
scope for a later slice, not hidden hypothesis tests.

## 7. Core Payload Shape

Add a UI-neutral grouped statistics payload:

```python
{
  "schema": "datalab.statistics.grouped.v1",
  "workflow_mode": "grouped_statistics",
  "stats_mode": "descriptive",
  "group_column": "Sample",
  "value_columns": ["A", "B"],
  "group_order": ["control", "treated"],
  "groups": [
    {
      "group": "control",
      "group_index": 1,
      "group_source_row_ids": ["1", "2", "3"],
      "columns": [
        {
          "value_column": "A",
          "input_row_count": 3,
          "row_count": 3,
          "included_source_row_ids": ["1", "2", "3"],
          "skipped_source_row_ids": [],
          "result": "<existing statistics payload>",
          "warnings": []
        }
      ]
    }
  ],
  "diagnostics": []
}
```

Requirements:

- Numeric results remain inside existing statistics payloads and therefore use
  existing string-safe result formatting.
- Group labels and column names are plain strings and must be escaped only at
  the output boundary.
- Group-level `group_source_row_ids` describe all rows carrying that group label.
  Per-column `included_source_row_ids` describe the actual numeric rows used by
  that group/value-column statistics request. These may differ when blank value
  cells are excluded per column.
- Payload validation must reject Python floats, unsupported group structures,
  duplicate group indices, duplicate value-column entries inside a group,
  mismatched source-row IDs, and malformed embedded statistics results.
- Payload and snapshot validation must reject JSON floats and invalid numeric
  strings in embedded statistics results. Existing standard-statistics
  `"nan"` string sentinels remain allowed only for unavailable standard
  descriptive metrics that the ungrouped statistics core already emits.
  Optional future descriptive-delta rows must be finite.

## 8. Semantic Snapshot

Reuse the statistics family with a grouped branch:

```python
{
  "schema": "datalab.result_snapshot.statistics",
  "schema_version": 1,
  "family": "statistics",
  "mode": "grouped_statistics",
  "source": {
    "group_column": "Sample",
    "value_columns": ["A", "B"],
    "group_order": ["control", "treated"],
    "group_count": 2
  },
  "groups": [...],
  "diagnostic_rows": [...],
  "compatibility": {
    "result_cache_kind": "statistics_grouped",
    "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
    "rendered_caches_authoritative": false
  }
}
```

`AnalysisRow` remains a scalar-row schema. For grouped statistics,
`AnalysisRow.source` is non-authoritative display/compatibility metadata only.
Durable metric identity must live in the structured `groups` list, where group
label and value-column identity are separate fields. History comparison and
workspace restore must not parse `AnalysisRow.source` strings to recover group
or column identity.

Workspace restore and history rendering must detect `mode ==
"grouped_statistics"` and use a grouped renderer rather than the P4.1
per-column renderer.

Closed validators, tentatively `validate_statistics_grouped_payload()` and
`validate_statistics_grouped_snapshot()`, must guard core output, snapshot build,
restore rendering, history comparison, LaTeX, plotting, and report export.

## 9. Text, CSV, And LaTeX

### Text

Text output shows:

- group column;
- selected value columns;
- one section per group, then per selected value column;
- row counts and diagnostics;
- no between-group delta rows in the first visible P4.3 release.

### CSV

CSV uses long form:

`group`, `column`, `batch`, `metric`, `value`, `uncertainty`

If descriptive deltas are implemented, they use:

`comparison`, `reference_group`, `group`, `column`, `metric`, `delta`

The first visible P4.3 release does not emit comparison/delta rows. Keep this
CSV shape reserved for a later explicitly reviewed comparison slice.

### LaTeX

LaTeX output must reuse existing statistics numeric formatting:

- one table per group/value-column pair, or a long grouped summary table if it
  can reuse existing numeric formatters;
- `latex_input_precision`, `uncertainty_digits`, `latex_group_size`, dcolumn,
  and siunitx behavior must remain consistent with existing statistics tables;
- group labels and column names are escaped at the output boundary;
- no duplicated number-formatting logic.

## 10. Plots

Initial grouped plots:

- per-group existing statistics plots are allowed but may produce too many
  images;
- the recommended first plot is a grouped mean/uncertainty overview per value
  column when `mean` and `std_mean` are available;
- if a plot cannot be generated from available metrics, fail closed with a
  diagnostic and still show text/CSV.

Plotting must route through `shared.plotting`, reuse CJK font handling, and
close Matplotlib figures reliably. Plot metadata must include group label,
value column, plot key, and stable order.

## 11. Workspace, History, Report Bundle

Workspace snapshot capture stores:

- `result_cache_kind = "statistics_grouped"`;
- the semantic grouped snapshot;
- long-form CSV rows;
- cached LaTeX source when generated;
- plot metadata/attachments when plots are enabled.

History comparison for grouped statistics:

- aligns by group label, value column, and metric identity;
- reports added/removed groups and columns;
- reports statistics mode/sample-population/trim-policy mismatches;
- does not compare grouped snapshots to ungrouped scalar/matrix snapshots except
  as same-family metadata-only/unavailable diagnostics.

Report bundles regenerate grouped LaTeX from the semantic snapshot. Existing
rendered LaTeX cache may be included as a rendered artifact, but it is not the
authoritative source for grouped tables.

## 12. Validation

Required tests:

- group-aware collector supports text group labels and high-precision numeric
  values;
- blank group labels excluded with diagnostics;
- blank value cells excluded per group/column using an input mode that preserves
  empty cells, and whitespace text explicitly documented/tested as unable to
  represent empty middle cells;
- nonblank malformed numeric values fail;
- per-group results equal isolated ungrouped statistics runs;
- multi-value-column grouped output preserves group order and selected-column
  order;
- sample/population and trim settings propagate to each group;
- weighted mean mode uses the existing sigma column per group;
- grouped payload/snapshot validators reject floats, invalid numeric strings,
  and malformed structures while preserving existing standard `"nan"`
  descriptive-metric sentinels;
- text/CSV render deterministically from semantic snapshot;
- history comparison aligns by group + column + metric;
- LaTeX siunitx and dcolumn grouped output, including escaped group labels;
- plot metadata and attachments survive workspace/report-bundle round trip;
- GUI schema scan covers group-column controls and visibility behavior;
- example workspace opens as a template and runs.

## 13. Delivery Order

1. Group-aware input collector and core grouped payload.
2. Semantic snapshot, text/CSV rendering, and history comparison.
3. LaTeX and plot routing.
4. Desktop GUI/workspace/report-bundle integration.
5. Docs, examples, release-matrix evidence, and final local gates.

Each slice must preserve unrelated dirty worktree changes and must not stage,
commit, package, or publish unless explicitly requested.
