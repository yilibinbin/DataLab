# DataLab P4.4 Bootstrap Confidence Intervals Spec

Status: draft for non-Claude review
Date: 2026-06-26

## 1. Goal

Add a statistics-family bootstrap workflow that estimates confidence intervals
for selected scalar statistics by resampling the selected value column with
replacement. The result must be a first-class DataLab result: deterministic
text, CSV, LaTeX, plot metadata, workspace/history restore, report-bundle
export, and reproducible resampling when a seed is provided.

P4.4 must reuse the existing statistics computation definitions, the existing
parallel/resource configuration, and the Monte Carlo distribution
summary/plotting pattern already used by error propagation. It must not create a
second random-sampling UI or a second distribution-plot schema.

## 2. Non-Goals

- No BCa bootstrap in the first release. Bias-corrected/accelerated intervals
  require jackknife acceleration, additional validation, and separate tests.
- No bootstrap p-values, hypothesis tests, or claims about group differences.
  Hypothesis tests belong to P4.5.
- No weighted bootstrap in the first release. The current statistics sigma
  column represents measurement uncertainty for weighted means, not a reviewed
  row-resampling probability model.
- No grouped, stratified, block, time-series, residual, parametric, or
  wild-bootstrap modes in the first release.
- No raw bootstrap sample persistence by default. Durable results store compact
  summaries, CI endpoints, counts, seed, configuration, and histogram metadata.
- No Web UI in the first implementation slice unless a separate reviewed plan
  adds it.

## 3. User Semantics

### 3.1 Workflow And Controls

P4.4 is a statistics workflow, not a new top-level module. It must follow the
P4.3 distinction between workflow and statistic method:

- `workflow_mode = "bootstrap_confidence_intervals"`
- existing `stats_mode` keeps its current meanings when it is used to define a
  target statistic such as arithmetic mean or descriptive statistics
- bootstrap-specific options live under a `bootstrap` configuration object

Required controls:

- value columns: one or more selected numeric columns, reusing P4.1 ordered
  value-column semantics;
- target statistic: first-release options are `mean`, `median`,
  `trimmed_mean`, `std`, and `variance`;
- confidence level, fixed to `0.95` in the first release;
- resample count, default `2000`;
- seed, optional;
- sample/population policy when the target statistic needs a denominator;
- trim fraction when the target statistic is `trimmed_mean`;
- generate plots, reusing the existing result-plot switch.

Controls that do not apply in the first release must be hidden or disabled:

- sigma column and weighted-variance controls;
- covariance/correlation and grouped-statistics controls;
- pairwise/listwise missing-data policy.

### 3.2 Input Semantics

Each selected value column is bootstrapped independently. Input collection reuses
the current statistics numeric parser and P4.1 value-column normalization:

- selected columns must exist and be unique;
- every included value must be finite and numeric;
- invalid numeric text, `NaN`, and infinity fail the calculation;
- missing/blank value policy is not introduced in P4.4. If nullable collection
  from P4.2/P4.3 is not implemented yet, bootstrap uses the current fully
  numeric statistics collection behavior.

The mathematical result for a single selected column must be reproducible from
the same input values, bootstrap options, and seed, independent of GUI state.

### 3.3 Eligible Target Statistics

First-release targets:

- `mean`: arithmetic mean.
- `median`: type-7 median, matching existing descriptive statistics.
- `trimmed_mean`: trim each tail by `floor(n * trim_fraction)`, matching
  existing descriptive statistics.
- `std`: standard deviation with sample/population denominator from the existing
  sample-mode control.
- `variance`: variance with sample/population denominator from the existing
  sample-mode control.

The implementation may compute these targets through a shared helper that uses
the same formulas as `compute_statistics()`. If it cannot prove formula parity
for a target, that target must stay hidden until a parity test exists.

`weighted_sigma` is explicitly deferred. If users select weighted mean while
bootstrap workflow is active, the GUI must either switch to an eligible target
or emit a clear unsupported diagnostic before computation starts.

## 4. Bootstrap Algorithm

### 4.1 Percentile Bootstrap

For input values `x_1 ... x_n`, target statistic `T`, sample count `B`, and
confidence level `c = 0.95`:

1. For each bootstrap replicate `b = 1..B`, draw `n` indices with replacement
   from `[0, n)`.
2. Compute `T_b = T(x_{i_1}, ..., x_{i_n})`.
3. Sort finite `T_b` values.
4. Let `alpha = (1 - c) / 2 = 0.025`.
5. CI lower is the type-7 quantile at `alpha`.
6. CI upper is the type-7 quantile at `1 - alpha`.
7. Store the original statistic `T_original`, bootstrap mean, bootstrap
   standard deviation, CI endpoints, finite/rejected counts, and distribution
   summary.

All arithmetic uses mpmath under `precision_guard(precision_digits)`. Bootstrap
index generation may use Python integer RNG, but statistic values must not be
converted through Python floats.

### 4.2 Count And Size Bounds

Default resample count: `2000`.

Recommended validation bounds:

- minimum `100`;
- maximum `100000` unless a future performance review raises this limit;
- fail fast when `n < 2` for `std`/`variance` sample mode or when target-specific
  constraints make the statistic undefined;
- reject values that would require persisting raw sample arrays.

The implementation may compute more efficiently than storing every raw
replicate, but CI quantiles and histograms require the finite replicate values
within the current run. Raw replicate values must not be persisted into
workspace snapshots or report bundles.

### 4.3 Determinism And Parallelism

Seed policy:

- If a seed is provided, the same data, options, DataLab version, and target
  statistic must produce the same result in serial and parallel execution.
- If no seed is provided, the run is still valid but explicitly marked
  non-reproducible in diagnostics and metadata.

Parallel policy:

- Use `shared.parallel_config.ParallelConfig` and
  `shared.parallel_backend.ParallelMapExecutor`.
- Use workload `CPU_MPMATH`.
- Do not invent another worker-count setting.
- Respect nested parallel policy.
- Determinism must not depend on worker partitioning. Either pre-generate the
  bootstrap index streams in a stable serial step, or derive per-replicate seeds
  from a documented stable seed schedule and sort/merge results by replicate
  index.
- The chosen RNG schedule and algorithm label must be stored in metadata so a
  later implementation change can be detected instead of silently changing
  seeded results.
- Process-mode functions and payloads must be top-level and picklable. Do not
  rely on an implicit process-pickling fallback: the current shared backend
  raises `TypeError` for non-picklable process callables or payloads. A
  pickling failure is an implementation defect to catch in tests; users can
  choose serial execution through the existing resource policy.

Cancellation must use the existing core/session cancellation hook at bounded
intervals.

## 5. Core Payload Shape

Add a UI-neutral statistics bootstrap payload, either as a new helper branch in
`datalab_core.statistics` or a small sibling module owned by the statistics
core. The payload shape is:

```python
{
  "schema": "datalab.statistics.bootstrap.v1",
  "workflow_mode": "bootstrap_confidence_intervals",
  "target_statistic": "mean",
  "confidence_level": "0.95",
  "resample_count": 2000,
  "seed": 12345,
  "seeded": true,
  "rng_algorithm": "python_random_v1",
  "rng_schedule": "per_replicate_seed_v1",
  "sample_mode": "sample",
  "trim_fraction": null,
  "method": "percentile",
  "columns": [
    {
      "value_column": "A",
      "column_index": 1,
      "row_count": 3,
      "source_row_ids": ["1", "2", "3"],
      "original_statistic": "1.25",
      "distribution": {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 2000,
        "evaluated_sample_count": 2000,
        "accepted_sample_count": 2000,
        "rejected_sample_count": 0,
        "finite_sample_count": 2000,
        "mean": "1.24",
        "std": "0.03",
        "histogram": {"bin_edges": ["1.1", "1.2", "1.3"], "counts": [900, 1100]},
        "percentiles": {"2.5": "1.18", "50": "1.24", "97.5": "1.30"}
      },
      "diagnostics": []
    }
  ],
  "diagnostics": []
}
```

Requirements:

- Numeric values are strings; unavailable values are `null`; counts are
  integers.
- Python floats are rejected at serialized boundaries.
- `original_statistic` is the only column-level scalar value duplicated outside
  the distribution summary. Bootstrap mean, bootstrap standard deviation,
  percentile endpoints, and count values are read from the embedded
  `distribution`; validators must reject any future duplicated aliases unless
  they enforce exact equality with the distribution source.
- `distribution` must reuse the existing Monte Carlo distribution summary
  schema exactly. Because that summary currently stores 2.5/50/97.5
  percentiles, first-release bootstrap confidence intervals are fixed to 95%.
  Supporting arbitrary confidence levels requires a later reviewed extension to
  the shared distribution summary and plot-label schema.
- A closed validator, tentatively `validate_statistics_bootstrap_payload()`,
  must validate schema, counts, numeric strings, CI ordering, confidence level,
  target statistic, selected columns, `len(source_row_ids) == row_count`,
  `rng_algorithm`, `rng_schedule`, target-specific options, and embedded
  distribution summaries.

## 6. Semantic Snapshot

Reuse the statistics family with a bootstrap branch:

```python
{
  "schema": "datalab.result_snapshot.statistics",
  "schema_version": 1,
  "family": "statistics",
  "mode": "bootstrap_confidence_intervals",
  "source": {
    "value_columns": ["A"],
    "column_count": 1,
    "target_statistic": "mean",
    "confidence_level": "0.95",
    "resample_count": 2000,
    "method": "percentile",
    "seed": 12345,
    "seeded": true,
    "rng_algorithm": "python_random_v1",
    "rng_schedule": "per_replicate_seed_v1",
    "sample_mode": "sample",
    "trim_fraction": null
  },
  "bootstrap": [...],
  "diagnostic_rows": [...],
  "plot_metadata": {...},
  "compatibility": {
    "result_cache_kind": "statistics_bootstrap",
    "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
    "rendered_caches_authoritative": false
  }
}
```

`AnalysisRow` remains a scalar-row schema. Bootstrap replicate distribution data
must live in structured `bootstrap` entries, not as many ad hoc analysis rows.
Metric rows may summarize original statistic, CI endpoints, bootstrap mean/std,
and counts for history/budget diagnostics, but durable identity stays in the
structured entries.

Workspace restore, history comparison, plotting, and report export must detect
`mode == "bootstrap_confidence_intervals"` and use bootstrap renderers rather
than the P4.1 ordinary statistics batch renderer.

A second closed validator, tentatively
`validate_statistics_bootstrap_snapshot()`, must guard snapshot build, restore
rendering, history comparison, plotting, LaTeX, and report export.

## 7. Text, CSV, LaTeX, And Plots

### 7.1 Text

Text output shows:

- target statistic;
- percentile method;
- confidence level;
- resample count;
- seed or non-reproducible seed diagnostic;
- one section per selected value column;
- original statistic, CI lower/upper, bootstrap mean/std, accepted/rejected
  counts, and diagnostics.

### 7.2 CSV

CSV long-form columns:

`column`, `target`, `method`, `metric`, `value`, `uncertainty`

Rows include:

- original statistic;
- CI lower;
- CI upper;
- CI width;
- bootstrap mean;
- bootstrap standard deviation;
- counts and diagnostics.

The CSV must be regenerated from the semantic snapshot and must not parse
rendered text.

### 7.3 LaTeX

LaTeX output must use existing `datalab_latex` table helpers and numeric-format
policy:

- escape column names and target labels;
- preserve dcolumn/siunitx compatibility;
- obey uncertainty digits, input precision, and digit grouping policies;
- include method, confidence level, resample count, and seed in caption or notes;
- do not emit raw `%` signs in numeric columns.

### 7.4 Plots

Bootstrap plots reuse the existing Monte Carlo distribution plot pattern:

- histogram of bootstrap statistic values;
- vertical lines for bootstrap mean and 2.5/50/97.5 percentiles;
- plot metadata includes column, target statistic, method, confidence level,
  seed, and plot order.

Supporting arbitrary confidence-level plot labels requires a separate, reviewed
extension to the shared plot labels/schema.

## 8. History, Compare, Report Bundle, Budget

Bootstrap snapshots must integrate with:

- workspace capture/restore;
- same-family history comparison;
- report bundle export/preview;
- P3.1 budget dashboard as diagnostic rows, not as physical uncertainty-budget
  totals.

History comparison may compare:

- original statistic delta;
- CI lower/upper delta;
- CI overlap diagnostic;
- resample count/seed/method changes.

No cross-family uncertainty aggregation may treat bootstrap standard deviation
as a total physical uncertainty without a later reviewed adapter.

## 9. Validation

Required tests:

- Core bootstrap helper parity for `mean`, `median`, `trimmed_mean`, `std`, and
  `variance`.
- Seeded serial/parallel determinism.
- Different seeds produce different replicate sequences for non-degenerate
  inputs.
- Resample-count bounds and target-statistic validation.
- JSON no-float validation for payload and snapshot.
- Embedded distribution summary fail-closed validation reuses the existing Monte
  Carlo distribution rules.
- Multi-column output preserves selected-column order and remains independent
  per column.
- Desktop GUI schema metadata, tooltips, workspace round-trip, and result CSV.
- LaTeX dcolumn and siunitx coverage.
- Plot routing creates one distribution histogram per selected column.
- Workspace/report-bundle export/preview preserve all bootstrap plot
  attachments.
- History comparison does not collide rows across columns.

## 10. Delivery Slices

1. Core bootstrap statistic helper, distribution summary builder, validators,
   and tests.
2. Statistics semantic snapshot/render/CSV integration.
3. Desktop GUI/workspace wiring.
4. LaTeX and plot routing.
5. History/report/budget/docs/examples/test-matrix integration.
