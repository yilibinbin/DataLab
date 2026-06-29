# Statistics (Desktop)

The statistics module computes statistics and mean estimates for a selected value column (optionally with `σ`).

## Inputs and Modes

- Select the value column by header name
- Descriptive statistics mode reports count, mean, optional trimmed mean, standard error, standard deviation, variance, min/max, median, Q1/Q3, IQR, MAD, skewness, and excess kurtosis
- When `σ` is available, weighted statistics can be used (weight `w=1/σ²`)
- Rows with missing or non-positive `σ` are skipped with a log message
  - If `σ=0` exists: it is treated as an infinite-weight anchor; conflicting `σ=0` values are rejected

## Covariance / Correlation Matrix

The Statistics workflow selector can compute covariance and correlation
matrices for two or more explicitly selected value columns. Enter columns as a
comma-separated list such as `A, B, C`.

- Listwise deletion is the default: a row is used only when every selected
  column has a finite value
- Pairwise deletion is optional: each column pair uses its own jointly valid
  rows, and the result is diagnostic-only for future budget aggregation
- The sample/population checkbox selects the covariance denominator (`n-1` or
  `n`)
- Weighted covariance is intentionally deferred; the existing sigma column is
  measurement uncertainty, not a reviewed multivariate row-weight model
- CSV uses long-form rows (`matrix`, `row_column`, `column`, `value`, `count`,
  `denominator`), LaTeX exports covariance and correlation tables, and plot
  generation creates a correlation heatmap when all correlation cells are
  finite

## Grouped Statistics

The Statistics workflow selector can group rows by a text column and run the
existing scalar statistics for each group and selected value column. This keeps
grouped calculations on the same precision, weighting, uncertainty, CSV,
LaTeX, plot, workspace, history, and report-bundle paths as ordinary
statistics.

- The group column is a required label column; blank group labels are excluded
  with diagnostics
- Value columns can be a comma-separated list such as `Signal, Reference`
- Embedded bracket uncertainties are supported; an explicit sigma column can
  override embedded uncertainties for all selected value columns
- The first visible release preserves first-seen group order and emits
  long-form rows keyed by group, column, metric, value, and uncertainty
- Grouped outputs are diagnostic context for the uncertainty-budget dashboard;
  they are not treated as independent physical variance contributions

## Bootstrap Confidence Intervals

The Statistics workflow selector can run Bootstrap confidence intervals for a
selected value column. The first release uses percentile Bootstrap with a fixed
95% interval (`2.5%`, `50%`, `97.5%`) so its distribution summary stays
compatible with the shared Monte Carlo summary and plotting code.

- Supported target statistics: mean, median, trimmed mean, standard deviation, and variance
- Optional seed makes the replicate schedule deterministic across serial and parallel execution
- Resample count is bounded by the core calculator; small examples can use 100 resamples, while real analysis should use a larger count
- Bootstrap output is preserved in workspaces, history, CSV, LaTeX, plots, and report bundles
- In the uncertainty-budget dashboard, Bootstrap intervals are diagnostic context only; they are not treated as physical variance contributions

## Hypothesis Tests

The Statistics workflow selector can also run first-release hypothesis tests
from the same embedded table data used by ordinary statistics. The visible
Desktop release includes:

- One-sample t-test
- Paired t-test using `A - B`
- Welch two-sample t-test
- Exact sign test
- Chi-square goodness-of-fit test

The null parameter, alternative, alpha level, second column, expected-count or
expected-probability source, and fitted-parameter count are stored in the
workspace. Results are regenerated from the structured hypothesis-test payload
when workspaces, history entries, CSV, LaTeX, and report bundles are rendered.
P-values and reject/not-reject decisions are diagnostic context; they are not
treated as uncertainty-budget variance contributions.

## Time-Series / Rolling Statistics

The Statistics workflow selector can run ordered-series calculations without
creating a separate module. The first release preserves input row order and
uses row-count windows; it does not sort by the time/index column and does not
perform time-width resampling.

- Rolling methods: mean, median, and standard deviation
- EWMA smoothing supports exactly one parameter: `alpha` or `span`, where
  `span` is converted by `alpha = 2 / (span + 1)`
- Rolling windows can be right-aligned or centered; `min_periods` controls
  whether edge points are emitted or marked as insufficient-window diagnostics
- Optional time/index columns are labels and monotonicity diagnostics only
- Propagated uncertainty is available only for rolling mean with an explicit
  aligned sigma column and independent-input assumption
- Time-series outputs are preserved in workspaces, history, CSV, LaTeX, plots,
  and report bundles. In the uncertainty-budget dashboard they are diagnostic
  series context, not variance contributions.

## Outputs

Depending on the selected mode, the result area may include:

- Mean and standard error
- 95% mean confidence interval. Unweighted modes use a Student-t interval with the sample standard deviation, including population display mode; weighted mode uses a known-sigma normal interval when no `σ=0` anchor is active
- Standard deviation, min and max
- Descriptive quantiles use Hyndman-Fan type 7 interpolation; sample variance/skewness/kurtosis and zero-variance moments surface warning diagnostics when unavailable
- Optional descriptive trimmed mean sorts finite values, removes `floor(n * trim_fraction)` values from each tail, and averages the remaining values. Blank or `0` disables it; invalid or too-large fractions are rejected by the core calculation
- Weighted effective sample size `n_eff` (Kish formula) and other diagnostics

## Export

- CSV export is available
- LaTeX table generation and optional PDF compilation can be enabled
- The bundled `Statistics matrix: covariance and correlation` example
  demonstrates a listwise covariance/correlation workflow with embedded data
- The bundled `Grouped statistics: multi-group means` example demonstrates
  grouped weighted statistics over two embedded value columns
- The bundled `Statistics: Bootstrap confidence interval` example demonstrates a deterministic seeded Bootstrap workspace with embedded data
- The bundled `Statistics: one-sample t-test` example demonstrates a one-sample hypothesis-test workspace with embedded data
- The bundled `Time series: rolling mean` and `Time series: EWMA smoothing`
  examples demonstrate row-count rolling output, EWMA smoothing, and embedded
  data that can be calculated immediately after opening
