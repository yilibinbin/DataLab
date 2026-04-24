# Statistics (Desktop)

The statistics module computes statistics and mean estimates for a selected value column (optionally with `σ`).

## Inputs and Modes

- Select the value column by header name
- When `σ` is available, weighted statistics can be used (weight `w=1/σ²`)
- Rows with missing or non-positive `σ` are skipped with a log message
  - If `σ=0` exists: it is treated as an infinite-weight anchor; conflicting `σ=0` values are rejected

## Outputs

Depending on the selected mode, the result area may include:

- Mean and standard error
- Standard deviation, min and max
- Weighted effective sample size `n_eff` (Kish formula) and other diagnostics

## Export

- CSV export is available
- LaTeX table generation and optional PDF compilation can be enabled
