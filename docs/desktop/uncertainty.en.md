# Error Propagation (Desktop)

The error propagation module evaluates formulas on uncertain inputs and automatically propagates uncertainties.

## Inputs

- Data table: first row = headers, remaining rows = data
- Constants (optional): provided as text or a file; propagated together with the data
- Formula: an expression defined on the input variables

## Method Selection (Taylor / Monte Carlo)

Two propagation methods are available:

- **Taylor (derivative)**: fast approximation
  - **order=1**: linear propagation (default)
  - **order=2**: includes Hessian (second-derivative) contributions and applies a mean correction to the reported value (closer to Monte Carlo mean)
- **Monte Carlo**: samples each input from an independent normal distribution and returns “sample mean ± standard deviation”
  - You can set the sample count (≥ 100) and an optional seed (reproducible runs)

## Formula Syntax

The desktop app uses the same parsing rules as the computation core:

- Functions use Mathematica-style names and brackets (e.g., `Sin[x]`, `Log[x]`, `Exp[x]`)
- Variables can be referenced by header names or supported aliases (see the in-app hints)

Use the function help button to view supported functions and examples.

## Outputs

After computation you will get:

- Per-row result value and combined uncertainty
- Uncertainty contribution plot (if enabled)
- LaTeX table (parentheses notation)

Note:

- Contribution breakdown is only available for Taylor modes (Monte Carlo does not return per-variable contributions).
