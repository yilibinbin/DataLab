# DataLab P4.6 Time-Series Smoothing And Rolling Statistics Spec

Status: draft for non-Claude review
Date: 2026-06-26

## 1. Goal

Add a statistics-family workflow for ordered-series analysis: rolling
mean/median/standard deviation and exponential weighted moving average (EWMA).
Users select one or more numeric value columns, optionally select an index/time
column for display and ordering validation, configure window/alignment options,
and receive structured series outputs, diagnostics, CSV, LaTeX, plots,
workspace/history snapshots, and report-bundle output.

The feature must help users inspect trends and local variability without
creating a second statistics module. It must reuse DataLab's existing numeric
parsing, precision policy, result snapshots, table/export helpers, plotting
boundaries, workspace saving, and parallel/resource settings.

## 2. Non-Goals

- No ARIMA, spectral analysis, forecasting, decomposition, or anomaly model in
  the first release.
- No time-width windows in the first release. Windows are row-count based.
- No automatic interpolation or resampling of irregularly sampled data.
- No hidden reordering of rows unless a later reviewed option explicitly adds
  sorting. First release preserves input order and reports time/index ordering
  diagnostics.
- No Savitzky-Golay in the first visible release unless a later reviewed slice
  defines its precision, boundary, and dependency policy. It remains a roadmap
  candidate, not part of the P4.6 first release gate.
- No Web UI in the first implementation slice unless a separate reviewed plan
  adds it.

## 3. Workflow Semantics

Time-series smoothing is a statistics workflow branch:

- `workflow_mode = "time_series_rolling"`
- `series_method` selects the series operation:
  - `rolling_mean`
  - `rolling_median`
  - `rolling_std`
  - `ewma`
- existing `stats_mode` remains the ordinary descriptive/statistics-method
  selector and must not be overloaded with rolling/smoothing workflow names

Common controls:

- selected value column(s), reusing P4.1 ordered value-column selection;
- optional sigma/uncertainty column mapping for `rolling_mean` only. This must
  be explicit and must not guess `A_sigma` for `A`;
- optional time/index column for labels and monotonicity diagnostics;
- `window_size` for rolling methods, integer `>= 1`;
- `alignment` for rolling methods: `right` or `center`;
- `min_periods`, integer `>= 1` and `<= window_size`;
- standard-deviation denominator for `rolling_std`: `sample` or `population`;
- EWMA smoothing parameter as exactly one of:
  - `alpha`, `0 < alpha <= 1`; or
  - `span`, numeric `>= 1`, converted by the documented formula
    `alpha = 2 / (span + 1)`;
- optional `adjust` for EWMA, default `false`, with explicit formula.

Numeric controls use the same safe numeric parser as DataLab inputs and
constants. Persisted payloads and snapshots must not contain Python floats.

## 4. Input Semantics

### 4.1 Series Input Collector

P4.6 needs a small statistics-family collector extension because the optional
time/index column may be non-numeric user metadata. It must reuse the shared
input-section parsing and existing safe numeric conversion for value/sigma cells,
but it must not send the entire row through the current all-numeric statistics
collector.

The collector output is:

- parsed numeric value series for selected value columns;
- optional parsed numeric sigma series for explicitly mapped sigma columns;
- raw time/index labels as strings, plus optional numeric parse results used
  only for monotonicity diagnostics;
- stable source row IDs;
- raw/blank-cell diagnostics that match existing input-normalization behavior.

This collector is P4.6-specific at the orchestration boundary, not a second
statistics math engine. Ordinary rolling calculations still consume normalized
numeric series and source-row IDs.

### 4.2 Value Columns

P4.6 reuses P4.1 value-column normalization:

- user selection order is preserved;
- each selected value column is processed independently;
- output rows keep source row IDs from the parsed input;
- missing/blank value behavior follows whichever nullable collector exists from
  P4.2/P4.3. If that collector is not implemented yet, P4.6 fails closed on
  invalid value/sigma cells while still preserving raw time/index labels.

### 4.3 Time/Index Column

The optional time/index column is metadata for labels, provenance, and
diagnostics. It does not change numeric calculations in the first release.

Rules:

- If no time/index column is selected, DataLab uses a 1-based row index for
  display and plotting.
- If a time/index column is selected, it is preserved as string metadata and may
  additionally be parsed as numeric for monotonicity diagnostics.
- First release does not sort by the time/index column. It preserves source row
  order.
- Non-monotonic or duplicate time/index values produce advisory diagnostics but
  do not change the result.
- Time-width windows and irregular-sampling weighted windows are deferred.

### 4.4 Sigma/Uncertainty Columns

Sigma columns are optional and method-limited:

- `rolling_mean` may accept explicit sigma/uncertainty columns and propagate
  independent standard uncertainty as defined in Section 6.
- `rolling_median`, `rolling_std`, and `ewma` may preserve the selected sigma
  mapping in the configuration for future compatibility, but first release does
  not compute method-specific propagated uncertainties for them.
- Multi-column runs must require an explicit value-to-sigma mapping when more
  than one value column is selected. Do not infer naming conventions such as
  `A_sigma`.
- If a sigma column is selected, source-row alignment must match the
  corresponding value column. Invalid, negative, or non-finite sigma values
  produce diagnostics rather than silent coercion.

### 4.5 Source Row IDs

Every output point stores:

- source row ID for the output row;
- input source row IDs included in the rolling window;
- skipped source row IDs when a nullable collector exists and blanks are
  skipped.

The parent column entry stores the selected value column name and optional sigma
column. Do not duplicate user column names onto every point unless a later
schema version has a concrete need for row-level column overrides.

Validators must reject row counts, source row IDs, and output point lists that
do not have consistent lengths.

## 5. Mathematical Definitions

Let `x_i` be values in input order and let a rolling window for output index `i`
be `W_i`.

### 5.1 Window Construction

For `alignment = "right"`:

- `W_i` contains rows `max(0, i - window_size + 1)` through `i`.

For `alignment = "center"`:

- `W_i` is centered as closely as possible around `i`;
- for even window sizes, the extra element is on the right side unless a later
  implementation discovers an existing project convention that should be used
  consistently instead;
- edge windows are clipped to available rows.

If `len(W_i) < min_periods`, the output value is `null` and a diagnostic is
recorded for that point. Partial edge windows are otherwise allowed.

### 5.2 Rolling Mean

`rolling_mean_i = sum(x_j for j in W_i) / len(W_i)`

Use mpmath arithmetic under `precision_guard(precision_digits)`. Do not route
through NumPy/Pandas floats.

### 5.3 Rolling Median

`rolling_median_i` uses the same median convention as existing descriptive
statistics.

The first implementation should either call a shared median helper extracted
from existing statistics code or add one shared helper used by both ordinary
statistics and rolling statistics. Do not duplicate median logic.

### 5.4 Rolling Standard Deviation

For `denominator = "sample"`:

`rolling_std_i = sqrt(sum((x_j - mean_i)^2) / (len(W_i) - 1))`

Requires `len(W_i) >= 2`; otherwise the output is `null` with a diagnostic.

For `denominator = "population"`:

`rolling_std_i = sqrt(sum((x_j - mean_i)^2) / len(W_i))`

Requires `len(W_i) >= 1`.

These definitions must match existing statistics sample/population behavior.

### 5.5 EWMA

For `adjust = false`:

- `y_0 = x_0`
- `y_i = alpha * x_i + (1 - alpha) * y_{i-1}`

For `adjust = true`:

`y_i = sum(alpha * (1-alpha)^(i-j) * x_j for j=0..i) /
       sum(alpha * (1-alpha)^(i-j) for j=0..i)`

The payload records the user-entered smoothing parameter and the normalized
`alpha`. EWMA does not use `window_size`, `alignment`, or `min_periods`.

## 6. Uncertainty Policy

Initial P4.6 keeps uncertainty conservative:

- If no sigma column is provided, outputs are descriptive series values only.
- For `rolling_mean`, if a sigma column is provided and the inputs are treated
  as independent, DataLab may propagate standard uncertainty as
  `sqrt(sum(sigma_j^2)) / n` for the window. The payload and snapshot must
  record the per-column uncertainty assumption as `"independent"`.
- For `rolling_median`, `rolling_std`, and EWMA, first release should not invent
  uncertainty propagation. It emits an explicit diagnostic:
  `series_uncertainty_not_available`.
- No covariance-aware rolling propagation ships until P4.2/P3 budget metadata
  provides a reviewed covariance interface.

If uncertainty propagation is implemented for rolling mean, it must use the same
uncertain-value formatting and table conventions as existing modules.

## 7. Payload Schema

Add a UI-neutral statistics series payload:

```json
{
  "schema": "datalab.statistics.time_series.v1",
  "workflow_mode": "time_series_rolling",
  "series_method": "rolling_mean",
  "value_columns": ["A"],
  "sigma_columns": {"A": "A_sigma"},
  "uncertainty_assumptions": {"A": "independent"},
  "time_column": "t",
  "window": {
    "type": "row_count",
    "size": 2,
    "alignment": "right",
    "min_periods": 2,
    "denominator": null
  },
  "ewma": null,
  "columns": [
    {
      "value_column": "A",
      "sigma_column": "A_sigma",
      "column_index": 1,
      "row_count": 3,
      "source_row_ids": ["1", "2", "3"],
      "uncertainty_assumption": "independent",
      "points": [
        {
          "index": 1,
          "source_row_id": "1",
          "time": "0.0",
          "observed_value": "1.00",
          "observed_uncertainty": "0.10",
          "value": null,
          "uncertainty": null,
          "window_source_row_ids": ["1"],
          "skipped_source_row_ids": [],
          "window_size_effective": 1,
          "status": "insufficient_window"
        },
        {
          "index": 2,
          "source_row_id": "2",
          "time": "1.0",
          "observed_value": "2.00",
          "observed_uncertainty": "0.20",
          "value": "1.50",
          "uncertainty": "0.111803398874989",
          "window_source_row_ids": ["1", "2"],
          "skipped_source_row_ids": [],
          "window_size_effective": 2,
          "status": "ok"
        },
        {
          "index": 3,
          "source_row_id": "3",
          "time": "2.0",
          "observed_value": "3.00",
          "observed_uncertainty": "0.30",
          "value": "2.50",
          "uncertainty": "0.180277563773199",
          "window_source_row_ids": ["2", "3"],
          "skipped_source_row_ids": [],
          "window_size_effective": 2,
          "status": "ok"
        }
      ],
      "diagnostics": []
    }
  ],
  "diagnostics": []
}
```

Requirements:

- Numeric values are strings; unavailable values are `null`; counts and indexes
  are integers.
- Python floats are rejected at serialized boundaries.
- `window` and `ewma` are mutually exclusive according to `series_method`.
- `sigma_columns` maps selected value columns to explicit sigma columns. It is
  empty or absent when no sigma propagation is requested.
- `uncertainty_assumptions` maps selected value columns to the assumption used
  for propagated uncertainties. It is empty or absent when no uncertainty values
  are propagated. Column-level `uncertainty_assumption` must match the root
  mapping for that value column.
- Each point stores the observed input value needed to regenerate plots from the
  snapshot alone. When an observed uncertainty exists, it is stored in
  `observed_uncertainty`.
- `status == "insufficient_window"` requires `value == null`; `status == "ok"`
  requires a numeric string `value`.
- `skipped_source_row_ids` is always present, using an empty list when no
  nullable collector skips rows.
- A closed validator, tentatively `validate_statistics_time_series_payload()`,
  must validate schema, method, selected columns, row counts, source-row ID
  parity, point ordering, numeric strings, window/EWMA option compatibility,
  and diagnostics.

## 8. Semantic Snapshot

Reuse the statistics family with a time-series branch:

```json
{
  "schema": "datalab.result_snapshot.statistics",
  "schema_version": 1,
  "family": "statistics",
  "mode": "time_series_rolling",
  "source": {
    "value_columns": ["A"],
    "sigma_columns": {"A": "A_sigma"},
    "uncertainty_assumptions": {"A": "independent"},
    "column_count": 1,
    "time_column": "t",
    "series_method": "rolling_mean",
    "window": {"type": "row_count", "size": 2, "alignment": "right", "min_periods": 2},
    "ewma": null
  },
  "time_series": [
    {
      "value_column": "A",
      "sigma_column": "A_sigma",
      "series_method": "rolling_mean",
      "points": [
        {
          "index": 1,
          "source_row_id": "1",
          "time": "0.0",
          "observed_value": "1.00",
          "observed_uncertainty": "0.10",
          "value": null,
          "uncertainty": null,
          "window_source_row_ids": ["1"],
          "skipped_source_row_ids": [],
          "window_size_effective": 1,
          "status": "insufficient_window"
        }
      ]
    }
  ],
  "diagnostic_rows": [...],
  "plot_metadata": {...},
  "compatibility": {
    "result_cache_kind": "statistics_time_series",
    "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
    "rendered_caches_authoritative": false
  }
}
```

Structured `time_series` entries are authoritative. Rendered text, CSV, LaTeX,
and plot files are caches or exports and must regenerate from the semantic
snapshot.

The semantic snapshot must be self-contained for output regeneration. It cannot
depend on the original editable input table or cached plot bytes to rebuild the
observed-plus-smoothed plot.

Add a second closed validator, tentatively
`validate_statistics_time_series_snapshot()`, and route
`render_statistics_snapshot_outputs()` to
`render_statistics_time_series_snapshot_outputs(snapshot)` when
`snapshot["mode"] == "time_series_rolling"`.

## 9. Text, CSV, LaTeX, And Plots

### 9.1 Text

Text output shows:

- method;
- selected value column;
- time/index column or row-index fallback;
- window/alignment/min-periods or EWMA alpha;
- point count and null/diagnostic count;
- a compact preview table for the series;
- diagnostics.

### 9.2 CSV

CSV long-form columns:

`column`, `row`, `time`, `method`, `value`, `uncertainty`, `status`,
`window_source_rows`

The CSV must be regenerated from `snapshot["time_series"]` and must not parse
rendered text.

### 9.3 LaTeX

LaTeX output must use existing `datalab_latex` table helpers and numeric-format
policy:

- escape value/time column names;
- preserve dcolumn/siunitx compatibility;
- obey uncertainty digits, input precision, and digit grouping policies;
- include method and window/EWMA settings in caption or notes;
- combine value and uncertainty in the same display cell when an uncertainty is
  available, following existing module conventions.

### 9.4 Plots

Time-series plots reuse `shared.plotting` rather than GUI-local Matplotlib code:

- observed series plus one or more smoothed/rolling series lines;
- optional uncertainty band only when uncertainty values exist;
- null/insufficient-window points are omitted from the smoothed line but may be
  represented by diagnostics;
- plot metadata includes method, column, time column, window/EWMA settings, and
  plot order.

## 10. History, Compare, Report Bundle, Budget

Time-series snapshots must integrate with:

- workspace capture/restore;
- same-family history comparison;
- report bundle export/preview;
- P3.1 budget dashboard as diagnostics only.

History comparison may compare:

- method and option changes;
- point-count changes;
- per-column final value delta;
- diagnostic count changes.

Rolling descriptive series should not be treated as physical uncertainty-budget
totals.

## 11. Validation

Required tests:

- Rolling mean/median/std reference cases for right and center alignment.
- `min_periods` and edge-window null diagnostics.
- EWMA adjusted and unadjusted formulas.
- Sample/population rolling standard deviation parity with ordinary statistics.
- Rolling-mean uncertainty propagation:
  `sqrt(sum(sigma_j^2)) / n`, recorded `uncertainty_assumptions`, no-sigma
  behavior, explicit multi-column value-to-sigma mapping, invalid/negative/
  non-finite sigma diagnostics, and `series_uncertainty_not_available` for
  median/std/EWMA when sigma mappings are present.
- Optional time/index column preservation and non-monotonic diagnostics.
- JSON no-float validation for payload and snapshot.
- Multi-column output preserves selected-column order and per-column source row
  IDs.
- Desktop GUI schema metadata, help text, language refresh, workspace
  round-trip, and result CSV.
- LaTeX dcolumn and siunitx coverage.
- Plot routing creates observed-plus-smoothed series plots without GUI-local
  plotting.
- Workspace/report-bundle export/preview preserve plot attachments.
- History comparison does not collide rows across columns or methods.

## 12. Delivery Slices

1. Shared rolling/EWMA core helpers, validators, and tests.
2. Statistics semantic snapshot/render/CSV integration.
3. Desktop GUI/workspace wiring.
4. LaTeX and plot routing.
5. History/report/budget/docs/examples/test-matrix integration.
