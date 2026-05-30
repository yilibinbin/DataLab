# Fitting (Desktop)

The fitting module fits explicit models to your data. It outputs parameters, uncertainties, and goodness-of-fit metrics, and can generate curve/residual plots.

## Data and Uncertainties

- Inputs support `x, y` (and optional `σ`)
- When `σ` is detected, you can choose whether to use statistical weighting (to avoid double-counting statistical and systematic errors)

## Model Selection

The desktop app provides explicit fitting models:

- Polynomial models
- Inverse-power series
- Padé and power-limit models
- Custom nonlinear and self-consistent/implicit models

Model-specific parameters appear dynamically on the left.

## Plots and Log Axes

When plots are enabled, the result area can show:

- Fit curve and data points
- Residual plot

You can also enable `log-x` / `log-y`:

- If the data contains non-positive values, the corresponding log axis is automatically disabled with a log message

## Outputs and Export

- Parameters and metrics are shown and can be exported as CSV
- LaTeX table generation and optional PDF compilation are available (depending on the TeX engine and settings)
