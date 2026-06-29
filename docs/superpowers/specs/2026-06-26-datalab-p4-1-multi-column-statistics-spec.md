# DataLab P4.1 Multi-Column Descriptive Statistics Spec

Status: revised after Codex/non-Claude review
Date: 2026-06-26

## 1. Goal

Allow the statistics module to compute descriptive/statistical summaries for
multiple selected numeric value columns in one run. The first release is a
side-by-side per-column summary. It must reuse the existing single-column
statistics core, semantic rows, CSV/LaTeX serializers, plotting boundaries,
history snapshots, and workspace persistence.

## 2. Non-Goals

- No covariance/correlation matrix in P4.1. Cross-column covariance belongs to
  P4.2.
- No grouped statistics. Grouped summaries belong to P4.3.
- No hypothesis tests or pairwise significance claims.
- No implicit column auto-selection that can surprise users. Users choose the
  columns explicitly, with optional helper detection only.
- No Web UI implementation in the first slice unless a later small plan adds it
  explicitly. The core API should still be UI-neutral enough for Web reuse.

## 3. Semantics

### 3.1 Input Columns

The existing `statistics.value_column` remains the single-column field for
backward compatibility. P4.1 adds a multi-column field, tentatively
`statistics.value_columns`, whose value is an ordered list of column names.

Resolution rules:

1. If `value_columns` is non-empty, run multi-column mode using that list.
2. If `value_columns` is empty or absent, fall back to existing `value_column`.
3. Duplicate column names are rejected with a diagnostic.
4. Missing columns are rejected before any calculation starts.
5. Non-numeric values are handled by the existing parser and request builder
   behavior; P4.1 does not add a separate coercion layer.

### 3.2 Sigma Columns

Initial P4.1 keeps sigma handling conservative:

- For unweighted/descriptive modes, sigma columns are optional and used only by
  existing warning/outlier/plot behavior where already supported.
- For weighted modes, users may provide one shared sigma column through the
  existing `statistics.sigma_column`.
- Per-value-column sigma mapping is deferred unless a later dedicated plan adds
  a table-based mapping UI. P4.1 must not guess `A_sigma` for `A`.
- If the shared sigma column is provided, it is used for every selected value
  column. Length, positivity, non-finite, and missing-row behavior remain the
  current single-column behavior.

### 3.3 Calculation

For each selected value column:

1. Build one or more existing `StatisticsRequestBatch` objects with
   `build_statistics_requests(...)`.
2. Submit each request through the existing statistics compute handler.
3. Convert result payloads through existing `statistics_payload_to_compute_result`
   where legacy display helpers still need legacy dictionaries.
4. Attach source metadata identifying the value column and batch index.

The mathematical result for each column must equal running the existing
single-column statistics command separately with the same options.

Desktop execution must use the same core request/result conversion path as Web
statistics (`build_statistics_requests()` -> core service/`run_statistics()` ->
`statistics_payload_to_compute_result()`). P4.1 must not add another GUI-local
loop around `compute_statistics()` because that would make the desktop and core
paths drift.

### 3.4 Output Ordering

Outputs preserve the user's selected column order. Within each column, existing
batch ordering and metric ordering are preserved.

### 3.5 Precision Policy

Use the existing statistics precision settings:

- `precision_digits` controls core arithmetic and high-precision parsing.
- `uncertainty_digits` controls uncertainty display.
- P4.1 must not introduce a new precision option.
- Aggregation across columns is not performed, so there is no new precision
  accumulation rule.

## 4. Data Model

### 4.1 Core Result Envelope

Add a small UI-neutral multi-column wrapper rather than changing the
single-column `run_statistics()` payload shape:

```python
{
  "schema": "datalab.statistics.multicolumn.v1",
  "columns": [
    {
      "value_column": "A",
      "batches": [
        {
          "index": 1,
          "request_id": "statistics-A-1",
          "row_count": 10,
          "result": <existing statistics payload>,
          "warnings": [...]
        }
      ]
    }
  ]
}
```

The exact Python surface can be a dataclass or plain helper functions, but it
must be JSON-safe and reject Python floats at serialized boundaries.

### 4.2 Semantic Snapshot

Reuse `datalab.result_snapshot.statistics` with existing `batches`, adding
column-aware source metadata. P4.1 may represent each selected column as one or
more batch snapshots:

- `source.value_column`: selected value column for that batch.
- `source.column_index`: 1-based selected-column index.
- `source.batch_index`: 1-based batch/segment index within that selected
  column.
- `source.batch_count`: existing semantics for segment count.
- `source.column_count`: number of selected value columns at snapshot level.
- `source.value_columns`: ordered selected column names at snapshot level.

No new statistics snapshot schema is required unless implementation discovers
that existing render/restore semantics cannot represent multiple columns
without ambiguity. If a new schema is needed, stop and write a revised plan.

Semantic rows used for matching/history comparison must be column-scoped without
changing the user-facing labels. P4.1 must not extend `AnalysisRow` with ad hoc
fields because that JSON schema is intentionally closed. The concrete
representation is:

- keep metric `key` values such as `mean`, `std`, and `row_count` unchanged;
- write the selected value column into the existing `AnalysisRow.source` field
  for metric rows in multi-column snapshots;
- make statistics history comparison align metric rows by `(source, key)`;
- leave row-flag `source` semantics unchanged, because outlier flags already use
  it for the flag metric.

## 5. Desktop GUI

### 5.1 Controls

Desktop statistics panel should keep the current single-line `value_column`
control as a compact multi-column entry:

- Label: "Value columns" / "数值列".
- Accept comma-separated names such as `A, B, C`.
- Preserve old workspaces by loading `value_column` into the first entry.
- Provide a helper action to insert/detect numeric columns from the input table.
- Tooltips must explain that multiple columns are run independently and that
  covariance/correlation is not computed here.

The existing sigma column, statistics mode, sample/population, weighted
variance, and trim fraction controls remain shared options for all selected
columns.

### 5.2 Result Display

The result panel should show one section per selected column. It must avoid
duplicating "numeric results" and "result data" content:

- Markdown/text: column heading, mode, row count, metric table.
- CSV: include `column`, `batch`, `metric`, `value`, `uncertainty`.
- CSV/header ordering should be deterministic: `column`, `batch`, `metric`,
  `value`, `uncertainty` for multi-column output. Existing single-column CSV
  headers should remain unchanged unless a compatibility test is intentionally
  updated.
- Result overview/history: a single semantic statistics snapshot containing all
  selected columns.

### 5.3 Workspace

Workspace save/restore stores `statistics.value_columns` when multi-column mode
is used. For backward compatibility:

- Old workspaces with only `value_column` restore as one selected column.
- New workspaces may still include `value_column` as the first selected column
  for compatibility if existing schema conventions require it.

## 6. LaTeX

P4.1 must reuse existing statistics LaTeX table formatting and dcolumn/siunitx
policy. Acceptable first-release output:

- One table per selected column, using the current statistics table builder.
- Or one long table with a leading `Column` column if that can reuse shared
  serializers without duplicating numeric formatting.

The first implementation should choose the smaller change. Numeric cells must
continue to obey `latex_input_precision`, `uncertainty_digits`,
`latex_group_size`, and dcolumn/siunitx settings.

## 7. Plots

Initial plotting:

- Generate existing statistics plots per selected column.
- Plot labels and image metadata include the column name.
- No multi-column overlay plot in P4.1 because overlay semantics and covariance
  interpretation belong to later work.
- Workspace snapshots and report bundles must preserve all per-column statistics
  plots, not only the currently visible image. Plot metadata must include stable
  order, role, column name, and title so restore/report preview can reconstruct
  the gallery.

## 8. History, Compare, Report Bundles, Budget

Multi-column statistics snapshots must remain usable by:

- History capture/restore.
- Same-family history comparison.
- Report bundle export/preview.
- P3.1 budget dashboard diagnostic extraction.

If existing history comparison sees metric rows with the same key from multiple
columns, implementation must make the row keys or source identifiers
column-scoped so rows do not collide.

The existing history comparison `_row_key()` path currently indexes statistics
rows by `key` first. P4.1 must add an explicit statistics comparison path or
row-source key so same metric names from different columns align by
`(column, metric)` rather than by insertion suffixes such as `mean#2`.

## 9. Validation

Required tests:

- Core request builder/helper: selected columns run independently and preserve
  order.
- Mathematical parity: each selected column equals a separate single-column run.
- Missing/duplicate column diagnostics.
- Shared sigma column behavior in weighted mode.
- Semantic snapshot render/CSV restore with column-scoped rows.
- Desktop GUI schema metadata, tooltips, workspace round-trip, and result CSV.
- LaTeX output with at least siunitx and dcolumn option coverage.
- Plot routing creates per-column plot metadata without overlay claims.
- Workspace/report snapshot tests prove all per-column plot attachments survive
  capture/restore/export, including non-active gallery images.
- History comparison does not collide metric rows across columns.
- Same selected columns in different orders preserve user-visible output order
  and history comparison still aligns by column name plus metric, not by
  ordinal position only.
- JSON-float safety for any new wrapper payload.

## 10. Delivery Slices

1. Core helper and tests.
2. Semantic snapshot/render/CSV integration.
3. Desktop GUI/workspace integration.
4. LaTeX/plot routing.
5. History/report/budget regression gates and docs/examples.

Each slice requires focused tests, Ruff, compileall, feasible mypy, whitespace
checks, and non-Claude review.
