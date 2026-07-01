# Error Propagation

The error propagation mode evaluates a formula on data with uncertainties and propagates the uncertainty to the result.

## Quick Workflow

1. **Input data** using parenthesis uncertainty notation, e.g.
   ```
   E1 E2 E3
   1.0000(5)   0.8000(4)   0.7000(2)
   ```

2. **Input formula** in the “Error propagation formula” box
   - Use column names or aliases `x1`, `x2`, `x3`, ...
   - Functions use Mathematica-style syntax: `Sin[x1]`, `Log[ALPHA]`

3. **Choose a propagation method**
   - **Taylor (derivative)**: fast approximation for “small uncertainties + smooth functions”
     - **order=1**: linearization (the classic first-order propagation)
     - **order=2**: includes Hessian (second-derivative) contributions and applies a mean correction to the reported value (closer to Monte Carlo mean)
   - **Monte Carlo**: samples inputs from independent normal distributions, returns “sample mean ± sample standard deviation”
     - You can set sample count (≥ 100) and an optional seed (for reproducibility)

4. **Optional: add constants**
   - Enable constants
   - Provide a constants list (one per line):
     ```
     ALPHA 7.2973525693(11)[-3]
     BETA 1.0000(5)
     ```

5. **Run**: click “Run Error Propagation & Generate LaTeX”

## Formula Examples

```
x1*ALPHA + x2/x3               # basic arithmetic
Sin[x1]^2 + Cos[x1]^2          # trigonometric functions
Exp[-x1*ALPHA] * x2            # exponential
Log[x1/x2] + Sqrt[x3]          # log + sqrt
```

## Features

- **Numerical partial derivatives**: automatically computes derivatives
- **Uncertainty synthesis**: combines contributions into total uncertainty (Taylor order 1/2)
- **Monte Carlo**: more robust for strong nonlinearity / domain restrictions (returns mean ± std)
- **Constants support**: propagate constants and data together
- **Visualization**: Taylor plots show contribution breakdown and cumulative contribution when contribution data exists; Monte Carlo plots show per-row sampled output distribution histograms with mean, standard-deviation, and percentile markers when Generate plots is enabled

## Units

The Web error-propagation page keeps unit-aware calculation inactive. Display-only
unit metadata may be preserved as provenance, but active validation or conversion
requests are rejected before evaluation. Use the Desktop app for unit labels in
results and for `validate expression` checks when `pint` is installed.

## Notes

- The default assumption is **independent** inputs (no covariance). For correlated inputs, prefer Monte Carlo or handle covariance externally.
- Monte Carlo will skip failed evaluations (e.g. domain errors like `Sqrt[x]` with negative samples); it raises an error if too few samples remain.
- Monte Carlo does not return per-variable contribution breakdown.
