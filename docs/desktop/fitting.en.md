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

## Custom and Self-Consistent/Implicit Models

Custom formulas and self-consistent/implicit models share the workbench formula
card, parameter table, and constants table. Use the formula preview syntax
selector to inspect DataLab-compatible, Python-style, or Mathematica-style
display rendering. This is preview-only and does not change computation. The
parameter table is still populated from the active formula and can be edited
manually; disabled constants are not substituted into the fit.

Self-consistent/implicit models cover problems such as `u = g(x, u, parameters)`
and `y = f(x, u, parameters)`. For each data point, DataLab solves the
self-consistent variable first and then evaluates the output expression for the
fit target. Start with stable initial guesses and bounds before adding more
parameters or increasing precision.

## Plots and Log Axes

When plots are enabled, the result area can show:

- Fit curve and data points
- Residual plot

You can also enable `log-x` / `log-y`:

- If the data contains non-positive values, the corresponding log axis is automatically disabled with a log message

## Outputs and Export

- Parameters and metrics are shown and can be exported as CSV
- LaTeX table generation and optional PDF compilation are available (depending on the TeX engine and settings)
