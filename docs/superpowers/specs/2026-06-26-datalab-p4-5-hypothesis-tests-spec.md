# DataLab P4.5 Hypothesis Tests Spec

Status: draft for non-Claude review
Date: 2026-06-26

## 1. Goal

Add explicit hypothesis-test workflows to the statistics family. Users choose a
test, supply the required columns and null-hypothesis parameters, and DataLab
returns test statistics, degrees of freedom where applicable, p-values,
effect-size/context rows, diagnostics, CSV, LaTeX, workspace/history snapshots,
and report-bundle output.

Hypothesis tests must be visibly separate from descriptive statistics,
covariance/correlation, grouped statistics, and bootstrap CI. The output must
surface assumptions and invalid-input diagnostics; it must not present p-values
as descriptive estimates.

## 2. Non-Goals

- No automatic "choose the right test" mode in the first release.
- No claims that p-values prove practical significance.
- No hidden conversion of high-precision inputs to binary float when
  `precision_digits > 16`.
- No arbitrary Python/statistical plugin execution.
- No cross-family uncertainty-budget totals from hypothesis-test p-values.
- No Web UI in the first implementation slice unless a separate reviewed plan
  adds it.

## 3. Workflow Semantics

Hypothesis tests are a statistics workflow branch:

- `workflow_mode = "hypothesis_tests"`
- test type lives in a separate `test_kind` field
- existing `stats_mode` remains the descriptive/statistics-method selector and
  must not be overloaded with hypothesis-test names

Required common controls:

- test kind;
- value column(s) required by that test;
- alternative hypothesis: `two_sided`, `less`, or `greater` where applicable;
- alpha/significance level for display diagnostics, default `0.05`;
- null-hypothesis parameters, such as `mu0` or expected probabilities/counts;
- optional continuity correction only for tests that define it.

All user-entered numeric parameters must use the same safe numeric parser used
for DataLab inputs and constants. Python floats are not allowed in persisted
payloads or snapshots.

## 4. Test Coverage Roadmap

### 4.1 First Release Scope

The first release supports tests that are useful, common, and bounded:

1. One-sample t-test.
   - Input: one numeric value column and null mean `mu0`.
   - Statistic: `t = (mean - mu0) / (s / sqrt(n))`.
   - Degrees of freedom: `n - 1`.
   - Requires `n >= 2` and finite nonzero sample standard deviation unless the
     zero-variance case is exactly diagnostic.

2. Paired t-test.
   - Input: two paired numeric columns with equal row count.
   - Statistic: one-sample t-test on `A - B` against null mean difference
     `delta0`, default `0`.
   - Requires at least two finite paired differences.

3. Welch two-sample t-test.
   - Input: two independent numeric columns.
   - Statistic: Welch's unequal-variance t-test.
   - Degrees of freedom: Welch-Satterthwaite approximation.
   - Requires at least two finite values per group and positive finite variance
     in at least one group; zero-variance edge cases must be explicit
     diagnostics.

4. Exact sign test.
   - Input: one numeric value column with null median `m0`, or paired
     differences with null difference `delta0`.
   - Ties at the null value are dropped and reported.
   - P-value uses the exact binomial distribution.

5. Chi-square goodness-of-fit test.
   - Input: observed count column and either expected count column or expected
     probability column.
   - Expected counts must be nonnegative and sum-compatible with observed
     counts.
   - Degrees of freedom: category count minus one minus explicit fitted
     parameter count.
   - Expected-count adequacy warnings are diagnostic, not silent rejection,
     unless expected count is zero where observed count is positive.

### 4.2 Per-Test Definitions

The following definitions are normative for first-release results.

#### One-Sample T-Test (`one_sample_t`)

- Inputs: `value_column`, `mu0` default `0`, `alternative`.
- Direction: statistic is observed mean minus `mu0`.
- Formula:
  - `mean = sum(x_i) / n`
  - `s2 = sum((x_i - mean)^2) / (n - 1)`
  - `se = sqrt(s2 / n)`
  - `t = (mean - mu0) / se`
  - `df = n - 1`
- Alternatives:
  - `two_sided`: `p = 2 * min(CDF_t(t, df), SF_t(t, df))`
  - `greater`: `H1: mean > mu0`, `p = SF_t(t, df)`
  - `less`: `H1: mean < mu0`, `p = CDF_t(t, df)`
- Invalid diagnostics: `n < 2`, non-finite values, zero standard error unless
  reported as a deterministic zero-variance diagnostic without p-value.

#### Paired T-Test (`paired_t`)

- Inputs: `value_column_a`, `value_column_b`, `delta0` default `0`,
  `alternative`.
- Pairing: rows are paired by original source row ID/order. No independent
  dropping that shifts one column relative to the other is allowed.
- Direction: differences are `d_i = A_i - B_i`.
- Formula: one-sample t-test on `d_i` against `delta0`.
- Alternatives:
  - `greater`: `H1: mean(A - B) > delta0`
  - `less`: `H1: mean(A - B) < delta0`
  - `two_sided`: `H1: mean(A - B) != delta0`
- Invalid diagnostics: unequal paired row availability, `n < 2`, non-finite
  paired values, or zero standard error without an exact deterministic
  diagnostic.

#### Welch Two-Sample T-Test (`welch_t`)

- Inputs: independent `value_column_a`, `value_column_b`, `delta0` default `0`,
  `alternative`.
- Direction: effect is `mean(A) - mean(B) - delta0`.
- Formula:
  - `se2 = s_a^2 / n_a + s_b^2 / n_b`
  - `t = (mean_a - mean_b - delta0) / sqrt(se2)`
  - `df = se2^2 / ((s_a^2 / n_a)^2 / (n_a - 1) + (s_b^2 / n_b)^2 / (n_b - 1))`
- Alternatives:
  - `greater`: `H1: mean(A) - mean(B) > delta0`, `p = SF_t(t, df)`
  - `less`: `H1: mean(A) - mean(B) < delta0`, `p = CDF_t(t, df)`
  - `two_sided`: `p = 2 * min(CDF_t(t, df), SF_t(t, df))`
- Invalid diagnostics: `n_a < 2`, `n_b < 2`, non-finite values, `se2 <= 0`,
  or undefined Welch degrees of freedom.

#### Exact Sign Test (`sign_test`)

- Modes:
  - one-sample: inputs `value_column`, `m0` default `0`;
  - paired: inputs `value_column_a`, `value_column_b`, `delta0` default `0`.
- Direction:
  - one-sample signs use `x_i - m0`;
  - paired signs use `A_i - B_i - delta0`.
- Ties exactly equal to zero are dropped and reported as `tie_count`.
- Let `k_pos` be positive signs and `n_eff = k_pos + k_neg`.
- Null distribution: `K ~ Binomial(n_eff, 0.5)`.
- Alternatives:
  - `greater`: `H1` positive shift, `p = P(K >= k_pos)`
  - `less`: `H1` negative shift, `p = P(K <= k_pos)`
  - `two_sided`: `p = min(1, 2 * min(P(K <= k_pos), P(K >= k_pos)))`
- Invalid diagnostics: `n_eff == 0`, non-finite values, or unsupported mode.

#### Chi-Square Goodness-Of-Fit (`chi_square_gof`)

- Inputs:
  - `observed_count_column`;
  - either `expected_count_column` or `expected_probability_column`;
  - `fitted_parameter_count`, default `0`.
- Observed counts must be finite, integer-valued, and nonnegative.
- Expected counts/probabilities must be finite and nonnegative.
- If probabilities are supplied, they are normalized only when their sum is
  positive and finite; expected counts are `total_observed * p_i / sum(p_i)`.
  The payload records whether probability normalization was applied.
- Expected counts from a count column must sum to the observed total within a
  reviewed tolerance or produce a diagnostic; the first release should prefer
  fail-fast unless a clear rescaling option is added.
- Statistic: `X2 = sum((observed_i - expected_i)^2 / expected_i)`.
- Degrees of freedom: `df = category_count - 1 - fitted_parameter_count`;
  require `df > 0`.
- P-value: upper tail only, `p = P(ChiSquare_df >= X2)`.
- Invalid diagnostics: observed total <= 0, expected count < 0, expected count
  equals zero with positive observed count, `df <= 0`, or non-integer observed
  counts.

### 4.3 Later Slices

These tests are valuable but require separate reviewed slices:

- Student equal-variance two-sample t-test with explicit variance-equality
  assumption.
- Mann-Whitney U test.
- Wilcoxon signed-rank test.
- Two-proportion z-test or exact Fisher/binomial alternatives.
- Chi-square independence test for contingency tables.
- ANOVA and Kruskal-Wallis.
- Multiple-comparison correction for families of tests.

Deferred tests must stay invisible in the GUI until their implementation and
validation slices are complete.

## 5. Numeric And Precision Policy

P4.5 must support two numeric paths:

1. Double-precision fast path.
   - Allowed when `precision_digits <= 16`.
   - May use `scipy.stats` for distribution p-values and reference
     cross-checks.
   - The payload must record `backend = "scipy"` and the SciPy version where
     available.

2. High-precision path.
   - Required when `precision_digits > 16`.
   - Test statistics are computed with mpmath under `precision_guard`.
   - Distribution p-values must either use reviewed mpmath formulas/integrals or
     emit an explicit `p_value_unavailable_high_precision` diagnostic.
   - The implementation must not silently call SciPy/double p-values for
     high-precision runs.

Distribution requirements:

- t-distribution CDF/survival should use a reviewed mpmath incomplete-beta
  formula or a documented numerical integration helper with tests against SciPy
  at moderate precision.
- Exact sign-test p-values should use integer/binomial arithmetic or mpmath
  summation; no SciPy dependency is needed.
- Chi-square CDF/survival should use reviewed mpmath incomplete-gamma formulas
  or emit an explicit high-precision-unavailable diagnostic until implemented.

If a p-value is unavailable, the test may still return the test statistic,
degrees of freedom, effect/context rows, and diagnostics, but it must not show a
fake or approximate p-value.

## 6. Input Semantics

First-release collection reuses existing statistics numeric-column parsing:

- selected columns must exist and be unique where required;
- every included value/count/expected value must be finite and numeric;
- invalid numeric text, `NaN`, and infinity fail the calculation;
- blanks/missing values are not introduced by P4.5 unless the relevant P4.2/P4.3
  nullable collector is already implemented and explicitly reused.

For paired tests, rows are paired by source row ID and original row order. The
implementation must not independently drop values from one column and shift the
other column.

For two-sample independent tests, the two selected columns represent two groups.
Grouping by a category column is deferred to a later grouped-testing slice.

## 7. Core Payload Shape

Add a UI-neutral hypothesis-test payload under the statistics core:

```python
{
  "schema": "datalab.statistics.hypothesis_test.v1",
  "workflow_mode": "hypothesis_tests",
  "test_kind": "one_sample_t",
  "alternative": "two_sided",
  "alpha": "0.05",
  "backend": "mpmath",
  "precision_used": 50,
  "inputs": {
    "value_columns": ["A"],
    "source_row_ids": ["1", "2", "3"],
    "null_parameters": {"mu0": "0"}
  },
  "result": {
    "statistic_name": "t",
    "statistic": "2.31",
    "degrees_of_freedom": "9",
    "p_value": "0.046",
    "reject_null": true,
    "effect_rows": [
      {"key": "mean_difference", "value": "0.12"},
      {"key": "standard_error", "value": "0.052"}
    ]
  },
  "diagnostics": []
}
```

Requirements:

- Numeric values are strings; counts are integers; unavailable p-values are
  `null` plus diagnostics.
- Python floats are rejected at payload and snapshot boundaries.
- `reject_null` is present only when p-value and alpha are both available and
  valid.
- `backend`, `precision_used`, test kind, alternative, alpha, input columns,
  null parameters, and source row IDs are required for reproducibility.
- A closed validator, tentatively
  `validate_statistics_hypothesis_payload()`, must validate schema, test-kind
  requirements, numeric strings, finite p-value in `[0, 1]`, degrees of freedom,
  source-row ID parity, and diagnostics.

## 8. Semantic Snapshot

Reuse the statistics family with a hypothesis-test branch:

```python
{
  "schema": "datalab.result_snapshot.statistics",
  "schema_version": 1,
  "family": "statistics",
  "mode": "hypothesis_tests",
  "source": {
    "test_kind": "one_sample_t",
    "value_columns": ["A"],
    "alternative": "two_sided",
    "alpha": "0.05",
    "backend": "mpmath"
  },
  "hypothesis_test": {...},
  "metric_rows": [...],
  "diagnostic_rows": [...],
  "compatibility": {
    "result_cache_kind": "statistics_hypothesis_test",
    "rendered_cache_fields": ["markdown", "csv", "latex_source"],
    "rendered_caches_authoritative": false
  }
}
```

The structured `hypothesis_test` payload is authoritative. `AnalysisRow` rows
summarize key values for display/history/budget diagnostics only. Workspace
restore, history comparison, report export, and LaTeX generation must route by
`mode == "hypothesis_tests"` and must not parse rendered text.

## 9. Display, CSV, LaTeX, And Plots

### Text

Text output shows:

- test name;
- null and alternative hypotheses;
- assumptions/validity diagnostics;
- sample sizes and dropped/tied counts where applicable;
- statistic, degrees of freedom, p-value, alpha, and reject/not-reject decision
  when available;
- effect/context rows.

### CSV

CSV long form:

`test`, `metric`, `value`, `uncertainty`, `note`

Rows include statistic, degrees of freedom, p-value, alpha, decision,
effect/context rows, and diagnostics.

### LaTeX

LaTeX output must use existing `datalab_latex` table helpers and numeric-format
policy:

- escape labels and hypotheses;
- preserve dcolumn/siunitx compatibility;
- avoid raw `%` signs in numeric cells;
- record backend/precision and assumptions in notes;
- compile representative tests under the existing LaTeX option matrix.

### Plots

First release does not require plots. Optional later plots include:

- paired-difference distribution plot;
- two-group box/violin plot;
- observed vs expected count bar plot.

If plots are added, they must use shared plot spec/render helpers and metadata,
not ad hoc Matplotlib calls from GUI code.

## 10. History, Report Bundle, Budget

Hypothesis-test snapshots must integrate with:

- workspace capture/restore;
- same-family history comparison;
- report bundle export/preview;
- P3.1 budget dashboard as diagnostics only.

History comparison may compare statistic, p-value, alpha, decision, backend,
and assumption diagnostics. P-values are not variance contributions and must not
feed cross-family uncertainty totals.

Concrete integration contract:

- Add a statistics snapshot renderer branch, tentatively
  `render_statistics_hypothesis_snapshot_outputs(snapshot)`, returning the same
  shape as existing statistics renderers: `(markdown_text, csv_rows,
  csv_headers)`.
- `render_statistics_snapshot_outputs()` routes to that branch when
  `snapshot["mode"] == "hypothesis_tests"`.
- Text, CSV, LaTeX, report-bundle sections, history comparison rows, and budget
  diagnostics all read `snapshot["hypothesis_test"]`; they must not use
  `metric_rows` or rendered cache text as authoritative input.
- Report-bundle export uses the statistics semantic CSV/LaTeX regeneration path
  for `statistics_hypothesis_test` result kinds.
- History comparison keys are `(test_kind, metric_key)` for scalar test-level
  metrics and `(test_kind, effect_key)` for effect/context rows. When two value
  columns define direction, comparison metadata must include ordered
  `value_columns`.
- Budget extraction keys are diagnostic-only:
  `(family="statistics", category="hypothesis_test", source_key=test_kind,
  label_key=metric_key)`. No p-value row may be emitted as a variance
  contribution.

## 11. Validation

Required tests:

- Core t-test results against SciPy for `precision_digits <= 16`.
- High-precision path tests that prove no SciPy/double p-values are used when
  `precision_digits > 16`.
- Exact sign-test binomial cases with ties.
- Chi-square goodness-of-fit cases with expected counts and probabilities.
- Invalid inputs: insufficient sample size, zero variance, malformed expected
  counts, unsupported alternative, invalid alpha, and non-finite values.
- JSON no-float payload and snapshot validation.
- Workspace save/restore and history comparison.
- CSV/LaTeX regeneration from semantic snapshot and LaTeX compile coverage.
- GUI schema/help/language tests for visible controls.

## 12. Delivery Slices

1. Core hypothesis-test DTOs, validators, and one-sample t plus sign-test
   engine.
2. Add paired t, Welch t, and chi-square goodness-of-fit.
3. Semantic snapshot/render/CSV/LaTeX integration.
4. Desktop GUI/workspace wiring.
5. History/report/budget/docs/examples/test-matrix integration.
6. Optional later test families from Section 4.3.

No user-visible hypothesis-test release should ship until slices 1-5 are
complete for all first-release tests in Section 4.1. Slice 1 may be merged only
as hidden core infrastructure.
