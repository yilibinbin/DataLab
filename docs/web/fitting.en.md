# Fitting

Fit an explicit model to data and obtain best-fit parameters and goodness-of-fit metrics.

## Quick Workflow

1. **Input data**: upload or paste an `x y` table (optional `σ`)
   ```
   x y
   1.0  2.1(5)
   2.0  4.2(5)
   3.0  6.0(5)
   ```

2. **Choose fitting mode**:
   - **Polynomial**: set degree
   - **Inverse power series**: set power range
   - **Padé**: set numerator and denominator order
   - **Power-limit**: use the `A*x**(-p)+C` template
   - **Custom model**: provide a custom expression
   - **Selected-fit comparison**: explicitly list the fits to compare as JSON

3. **Options**:
   - Weighted fit: use uncertainties as weights (if provided)
   - Log scale: choose log-x, log-y, or log-log (when plots are enabled)

4. **Review results**:
   - parameter estimates and uncertainties
   - quality metrics (χ², AIC, BIC, R², RMSE)
   - fitted curve and residual plots
   - selected-fit comparison table, CSV, and LaTeX table

## Supported Model Families

- polynomial fits
- inverse power series
- Padé approximants
- power-limit template
- custom models

## Selected-Fit Comparison

The Web page supports selected-fit comparison mode. This mode does not generate
or filter fit entries; explicitly list each fit in the `fit_comparison_candidates`
text box, for example:

```json
[
  {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
  {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2}
]
```

The comparison table preserves JSON list order and reports each fit entry's
status, free-parameter count, χ², reduced χ², AIC, BIC, RMSE, R², warnings, and
errors. CSV download and LaTeX output use the same comparison rows.

The desktop GUI also supports self-consistent/implicit fitting. The web page
currently exposes the explicit model subset listed above.
