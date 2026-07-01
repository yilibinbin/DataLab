# DataLab P4.2 Covariance And Correlation Matrix Spec

Status: finalized after Codex and Antigravity Gemini Pro review
Date: 2026-06-26

## 1. Goal

Add a statistics-module matrix workflow that computes covariance and
correlation matrices across explicitly selected numeric columns. The result
must be a first-class DataLab result: deterministic text, CSV, LaTeX, plot
metadata, workspace/history restore, report-bundle export, and explicit
correlation metadata that future budget aggregation can inspect.

P4.2 must not silently enable total uncertainty aggregation. It only supplies
candidate covariance/correlation metadata. Any future P3.1-C total-budget mode
must still prove denominator, quantity-space, unit, aggregation-model, and
correlation compatibility before using it.

## 2. Non-Goals

- No weighted covariance in the first release. The existing sigma column means
  per-observation measurement uncertainty for single-column statistics; it is
  not a reviewed multivariate row-weight model.
- No imputation of missing or non-finite cells.
- No hypothesis tests, p-values, partial correlations, PCA, regression, or
  clustering.
- No automatic column selection that changes the user's requested matrix.
- No cross-family total-budget aggregation.
- No Web UI in the first implementation slice unless a separate reviewed plan
  adds it. The core result shape must remain UI-neutral.

## 3. User Semantics

### 3.1 Inputs

P4.2 reuses the statistics value-columns setting introduced in P4.1:

- Users must select at least two numeric value columns.
- Column order is user-visible and is preserved in text, CSV, LaTeX, plots, and
  snapshots.
- Duplicate columns are rejected before computation.
- Missing columns are rejected before computation.

The statistics workflow selector gains a matrix workflow, tentatively
`workflow_mode="covariance_correlation"`. This follows the later
statistics workflow split used by bootstrap, hypothesis tests, and
time-series smoothing; `stats_mode` remains the scalar statistics method
selector and must not be overloaded with workflow names. In this workflow:

- the value-columns field is required and must contain at least two columns;
- the sample/population control selects the denominator policy;
- a new missing-data policy control selects listwise or pairwise deletion;
- sigma-column, weighted-variance, and trim-fraction controls are hidden or
  disabled because they do not apply to first-release matrix computation.

### 3.2 Missing-Data Policy

P4.2 supports two explicit policies.

Current Desktop statistics parsing returns fully numeric `mp.mpf` rows and
rejects unparseable cells before statistics code runs. Therefore P4.2 requires a
matrix-specific nullable collection layer before any pairwise/listwise policy is
exposed in the GUI:

- The collector reads the active input bundle/source rows and selected columns
  into `mp.mpf | None` cells plus stable source row IDs.
- It must reuse the existing shared input parsing/normalization boundary where
  possible rather than adding a second ad hoc parser.
- Empty manual-table cells and explicitly supported missing markers may become
  `None`.
- Text that is not a supported missing marker, `NaN`, and infinity remain input
  errors, not missing values.
- Whitespace text input cannot represent an empty middle cell reliably; pairwise
  examples/tests must cover input forms that preserve empty cells, such as the
  manual table or a delimited file/text path if already supported.

Listwise deletion is the default and the only policy whose correlation metadata
may be marked as a candidate for future total-budget aggregation:

- A row is included only when every selected column has a finite numeric value.
- All covariance and correlation cells share the same row count and source row
  IDs.
- The covariance matrix is computed from one aligned data matrix.
- If no rows remain, the calculation fails with a user-facing diagnostic.

Pairwise deletion is optional and diagnostic-only for future budget use:

- Each pair of columns uses rows where both columns have finite numeric values.
- Pairwise counts are stored per cell.
- Correlation cells use pair-specific means and variances from the same
  pairwise rows.
- The pair-specific means and variances used for each correlation cell are
  stored as numeric strings in `correlation_components`, so the result remains
  auditable even when off-diagonal correlations cannot be reconstructed from
  the matrix diagonal.
- The resulting matrix may be non-positive-semidefinite, so
  `budget_eligible` must be false.
- Cells with insufficient rows are null and produce diagnostics.

No policy may coerce blanks, text, NaN, or infinity into numeric values.

The service boundary must preserve this distinction. Matrix requests must not
enter the existing scalar statistics `_parse_values()` path before the
workflow dispatch, because that path expects a one-dimensional numeric series.
`run_statistics()` must inspect `workflow_mode` first, route
`workflow_mode="covariance_correlation"` to the matrix collector, and keep
scalar value/sigma parsing inside the scalar, bootstrap, hypothesis, and
time-series branches that need it.

### 3.3 Denominator Policy

The existing sample/population setting controls covariance denominators:

- Sample mode uses `n - 1` and requires at least two observations for a cell.
- Population mode uses `n` and requires at least one observation for covariance.
- Correlation requires positive finite variances for both columns. If a column
  variance is zero, the affected correlation cells are null and diagnostics
  explain that correlation is unavailable.

The output stores both the denominator mode and the effective count/denominator
per cell.

## 4. Mathematical Definitions

For listwise data matrix `X` with columns `c_i` and included row count `n`:

- `mean_i = sum(X[:, i]) / n`
- `cov_ij = sum((X[:, i] - mean_i) * (X[:, j] - mean_j)) / denom`
- `denom = n - 1` in sample mode, `n` in population mode
- `corr_ij = cov_ij / sqrt(cov_ii * cov_jj)` when both variances are positive

For pairwise mode, the same formulas are applied to each pair's included
two-column submatrix.

All arithmetic uses the existing statistics precision setting and mpmath
precision guard. P4.2 introduces no new precision option. The implementation
must use mpmath values and stable summation such as `mp.fsum`; it must not route
matrix math through Python `float`, NumPy float arrays, or formatted display
strings.

## 5. Core Result Shape

Add a UI-neutral statistics matrix payload, either as a new helper result or a
new branch in the existing statistics core module. The payload matrix maps use
this shape:

The examples below are illustrative. Any `...` marker is prose abbreviation,
not an allowed serialized value; real payloads must contain complete lists.

```python
{
  "schema": "datalab.statistics.matrix.v1",
  "mode": "covariance_correlation",
  "columns": ["A", "B"],
  "missing_policy": "listwise",
  "denominator": "sample",
  "row_count": 12,
  "source_row_ids": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
  "matrices": {
    "covariance": {
      "values": [["1.0", "0.2"], ["0.2", "4.0"]],
      "counts": [[12, 12], [12, 12]],
      "denominators": [[11, 11], [11, 11]]
    },
    "correlation": {
      "values": [["1", "0.1"], ["0.1", "1"]],
      "counts": [[12, 12], [12, 12]],
      "denominators": [[11, 11], [11, 11]]
    }
  },
  "correlation_components": {
    "mean_x": [["2", "2"], ["3", "3"]],
    "mean_y": [["2", "3"], ["2", "3"]],
    "variance_x": [["1", "1"], ["4", "4"]],
    "variance_y": [["1", "4"], ["1", "4"]]
  },
  "diagnostics": [],
  "correlation_metadata": {
    "source": "statistics_covariance_correlation",
    "row_alignment": "listwise",
    "weighted": false,
    "budget_eligible": true
  }
}
```

Requirements:

- Numeric matrix cells are strings; unavailable cells are `null`.
- Counts and denominators are integers or null.
- The payload must reject Python floats and non-finite numeric strings at
  snapshot/export boundaries.
- Matrices must be square and match the selected column count.
- Correlation values must be in `[-1, 1]` within a small validation tolerance.
  Diagonal cells are `1` only when the corresponding variance is positive;
  otherwise they are null with diagnostics.
- `correlation_components` is required for pairwise mode and optional for
  listwise mode. When present, it must have the same square shape as the
  correlation matrix and contain only finite numeric strings or nulls matching
  unavailable correlation cells.
- A closed validator, tentatively `validate_statistics_matrix_payload()`, must
  validate shape, numeric strings, counts, denominators, null consistency,
  symmetry, diagonal rules, and metadata before any payload leaves core code.

## 6. Semantic Snapshot

Reuse the statistics family but add a matrix branch to the semantic snapshot:

```python
{
  "schema": "datalab.result_snapshot.statistics",
  "schema_version": 1,
  "family": "statistics",
  "mode": "covariance_correlation",
  "source": {
    "value_columns": ["A", "B"],
    "column_count": 2,
    "missing_policy": "listwise",
    "denominator": "sample",
    "row_count": 12,
    "source_row_ids": ["1", "2", "...", "12"]
  },
  "matrices": [
    {
      "kind": "covariance",
      "columns": ["A", "B"],
      "values": [["1.0", "0.2"], ["0.2", "4.0"]],
      "counts": [[12, 12], [12, 12]],
      "denominators": [[11, 11], [11, 11]]
    }
  ],
  "diagnostic_rows": [...],
  "correlation_metadata": {...},
  "compatibility": {
    "result_cache_kind": "statistics_matrix",
    "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
    "rendered_caches_authoritative": false
  }
}
```

`AnalysisRow` remains a scalar-row schema. Do not encode matrix cells as many
metric `AnalysisRow` objects unless a reviewed helper explicitly round-trips
cell coordinates through existing fields without collisions. The preferred
representation is a dedicated `matrices` list on the statistics snapshot plus
diagnostic `AnalysisRow` entries for warnings/errors.

Workspace restore and history rendering must detect the matrix branch
(`mode == "covariance_correlation"` or equivalent normalized workflow
metadata) and use a matrix renderer rather than the P4.1 per-column batch
renderer.

A second closed validator, tentatively `validate_statistics_matrix_snapshot()`,
must guard snapshot build, restore rendering, history comparison, plotting, and
report export. `normalize_json_payload()` alone is not enough because it does
not understand ragged matrices, non-finite numeric strings, or matrix metadata
invariants.

## 7. Display, CSV, And LaTeX

### 7.1 Text Display

The result text shows:

- selected columns;
- missing-data policy;
- denominator mode;
- row count summary;
- covariance matrix;
- correlation matrix;
- diagnostics.

### 7.2 CSV

CSV uses long form for stable headers and arbitrary column names:

`matrix`, `row_column`, `column`, `value`, `count`, `denominator`

Unavailable numeric cells use an empty value with diagnostics available in the
text result. This avoids generating dynamic CSV headers that change with the
selected column set.

### 7.3 LaTeX

LaTeX output emits two matrix tables:

- covariance matrix;
- correlation matrix.

The implementation must reuse existing numeric formatting policy:

- `format_value_for_latex_file()` / `_format_table_value()` for numeric cells;
- existing dcolumn/siunitx column-spec helpers;
- `latex_group_size`;
- `latex_input_precision`;
- existing escaping for row/column labels.

Null cells render as a safe centered text marker such as `--`, not as a raw
numeric cell. The dcolumn path must compile when null cells are present; the
preferred representation is `\multicolumn{1}{c}{--}` for null cells in numeric
columns.

## 8. Plots

Initial plot output is a correlation heatmap:

- one plot for the correlation matrix;
- fixed color scale `[-1, 1]`;
- labels are selected column names;
- cell annotations are rounded display values;
- invalid/malformed matrix data fails closed without a plot;
- CJK font handling and `plt.close()` behavior follow `shared.plotting`.
- pairwise matrices with null cells do not emit a heatmap; pairwise matrices
  that are complete and finite may still be plotted, but remain
  `budget_eligible=false`.

The implementation may extract a generic matrix-heatmap helper from the
existing fitting parameter-correlation heatmap, but it must not duplicate
near-identical rendering logic.

Covariance heatmaps are deferred because covariance scale is unit-dependent and
can be visually misleading without additional normalization controls.

## 9. Workspace, History, Report Bundle

Workspace snapshot capture stores:

- `result_cache_kind = "statistics_matrix"`;
- the semantic matrix snapshot;
- CSV long-form rows;
- cached LaTeX source when generated;
- correlation heatmap metadata and PNG attachment if plots are enabled.

The workspace semantic-kind allowlist must explicitly include
`statistics_matrix` for the statistics family. It must not accidentally render
matrix snapshots through the P4.1 scalar/batch renderer.

History compare for two statistics matrix snapshots:

- compares only matching matrix cells by matrix kind and column pair;
- aligns by column names, not by selected-column ordinal alone;
- reports added/removed columns;
- reports denominator/missing-policy mismatches as diagnostics;
- does not compare matrix snapshots to P4.1 scalar statistics snapshots except
  as same-family metadata-only/unavailable diagnostics.

Report bundles include the matrix text/CSV/LaTeX and heatmap attachment through
the existing report-bundle attachment path.

Matrix LaTeX for report bundles is regenerated from the semantic matrix
snapshot using the same matrix LaTeX writer used by the GUI. Existing rendered
LaTeX cache may be included as an attachment when available, but it is not the
authoritative source for report-bundle matrix tables.

## 10. Budget Metadata Policy

P4.2 exports `correlation_metadata` for future budget features only.

`budget_eligible` may be true only when:

- missing policy is listwise;
- matrix is unweighted;
- all selected rows are aligned;
- every correlation cell is finite;
- the matrix validates as square, symmetric, and unit diagonal;
- all values are dimensionless correlation coefficients.

Even when `budget_eligible` is true, P4.2 does not aggregate budgets. P3.1-C
must still perform quantity-space, unit, denominator, and aggregation-model
checks before consuming the metadata.

The validator must enforce this policy, not only document it. If any
correlation cell is null or non-finite, including listwise zero-variance cases,
`budget_eligible` must be false or the payload must be rejected.

## 11. Validation

Required tests:

- Core listwise covariance/correlation against hand-calculated data.
- Core pairwise counts and null cells for insufficient pairs.
- Sample vs population denominator.
- Duplicate/missing column rejection.
- At least one high-precision cancellation regression.
- Zero-variance correlation diagnostics.
- JSON-float and non-finite string rejection at payload/snapshot boundaries.
- Semantic snapshot render and CSV long-form restore.
- History comparison aligns by column names and cell coordinates.
- LaTeX siunitx and dcolumn matrix output, including null-cell compile safety.
- Correlation heatmap spec/render fail-closed behavior.
- Desktop GUI visibility/tooltip/schema scan for matrix mode, including a
  `statistics.matrix.missing_policy` schema key and choices metadata for the
  missing-data policy combo.
- Workspace save/restore of matrix mode.
- Report-bundle export/preview includes the correlation heatmap.

## 12. Delivery Order

1. Core matrix computation and payload validation.
2. Semantic snapshot, text/CSV rendering, and history comparison.
3. LaTeX matrix tables and shared heatmap plotting.
4. Desktop GUI/workspace/report-bundle integration.
5. Docs, examples, release-matrix evidence, and final local gates.

Each implementation slice must preserve unrelated dirty worktree changes and
must not stage, commit, package, or publish unless explicitly requested.
