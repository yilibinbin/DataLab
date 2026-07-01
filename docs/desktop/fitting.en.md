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
- Explicit selected-fit comparison

Model-specific parameters appear dynamically on the left.

## Explicit Selected-Fit Comparison

The explicit selected-fit comparison mode runs only the fits you enter in the candidate
JSON editor. Each entry must provide its own identifier, label, and model
settings. Supported candidate families are `polynomial`, `inverse_power`, and
`custom`.

Example candidate JSON:

```json
[
  {
    "candidate_id": "linear",
    "label": "Linear",
    "model_type": "polynomial",
    "poly_degree": 1
  },
  {
    "candidate_id": "inverse_1_2",
    "label": "Inverse powers 1-2",
    "model_type": "inverse_power",
    "inverse_min": 1,
    "inverse_max": 2
  },
  {
    "candidate_id": "custom_a",
    "label": "Custom a*x+b",
    "model_type": "custom",
    "model_expr": "a*x+b"
  }
]
```

The result panel shows a comparison table for the listed fits. CSV export uses
the same comparison row order, and LaTeX output writes a comparison table when
LaTeX generation is enabled. Workspaces save the candidate JSON under
`config.fitting.comparison_candidates` so the same explicit list is restored
with the project.

## Custom and Self-Consistent/Implicit Models

Custom formulas and self-consistent/implicit models share the workbench formula
card, parameter table, and constants table. Formula input uses
DataLab/Mathematica-compatible syntax, and the preview button renders the
current expression as LaTeX-style math. Preview is display-only and does not
change computation. The parameter table is still populated from the active
formula and can be edited manually; disabled constants are not substituted into
the fit.

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
