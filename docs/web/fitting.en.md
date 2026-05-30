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

3. **Options**:
   - Weighted fit: use uncertainties as weights (if provided)
   - Log scale: choose log-x, log-y, or log-log (when plots are enabled)

4. **Review results**:
   - parameter estimates and uncertainties
   - quality metrics (χ², AIC, BIC, R², RMSE)
   - fitted curve and residual plots

## Supported Model Families

- polynomial fits
- inverse power series
- Padé approximants
- power-limit template
- custom models

The desktop GUI also supports self-consistent/implicit fitting. The web page
currently exposes the explicit model subset listed above.
