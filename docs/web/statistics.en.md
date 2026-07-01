# Statistics

Compute (weighted or unweighted) statistical averages for data with optional uncertainties.

Desktop-only statistics workflows such as covariance/correlation matrices,
grouped statistics, Bootstrap confidence intervals, hypothesis tests, and
time-series smoothing are documented in the Desktop statistics guide.

## Quick Workflow

1. **Input data**: provide a single-column table (uncertainty is optional)
   ```
   A
   1152842742.723(12)
   1152842742.740(18)
   1152842742.727(14)
   ```

2. **Choose statistics mode**:
   - **Simple mean**: arithmetic mean
   - **Descriptive statistics**: mean, optional trimmed mean, spread, quantiles, MAD, skewness, and excess kurtosis
   - **Sample variance**: enable “use sample standard deviation”
   - **Weighted variance**: enable “use weighted variance”

3. **Review results**:
    - mean ± standard error
    - 95% mean confidence interval
    - min / max / standard deviation
    - median, Q1/Q3, IQR, MAD, skewness, excess kurtosis, and optional trimmed mean in descriptive mode
    - effective sample size (when applicable, Kish formula)

## Mode Notes

### Simple mean
Computes the arithmetic mean and standard deviation.

### Sample variance
Uses the sample standard deviation (denominator `n-1`).

### Confidence interval
Unweighted modes report a 95% Student-t confidence interval for the mean using `sample_std/sqrt(n)`, even when population mode is selected for displayed variance. Weighted mode reports a known-sigma normal interval using `sqrt(1/Σwᵢ)` unless a `σ=0` anchor is active.

### Descriptive statistics
Computes count, mean, optional trimmed mean, standard error, standard deviation, variance, min/max, median, Q1/Q3, IQR, MAD, skewness, and excess kurtosis. Quantiles use Hyndman-Fan type 7 interpolation. Sample variance requires `n>=2`, sample skewness requires `n>=3`, sample excess kurtosis requires `n>=4`, and zero-variance data reports skewness/kurtosis as unavailable diagnostics. Trimmed mean sorts finite values, removes `floor(n * trim_fraction)` values from each tail, and averages the remaining values. Blank or `0` disables trimming; invalid or too-large fractions are rejected.

### Weighted variance
Computes weighted statistics using the provided uncertainties:

- Weight: `w = 1/σ²` (rows with missing `σ` are skipped)
- Weighted mean: `x̄_w = Σ(wᵢ xᵢ) / Σwᵢ`
- Standard error of the weighted mean: `SE(x̄_w) = sqrt(1 / Σwᵢ)`
- Weighted standard deviation (scatter): numerator uses `Σ wᵢ (xᵢ-x̄_w)²`; in sample mode the denominator is `Σwᵢ - Σwᵢ²/Σwᵢ` (in population mode it is `Σwᵢ`)

Edge cases:

- If `σ=0` exists: it is treated as an “infinite-weight anchor” (mean/uncertainty come from that point); conflicting `σ=0` values are rejected
