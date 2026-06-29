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
- Generated plots (if enabled):
  - Taylor: contribution breakdown and cumulative contribution when contribution data exists
  - Monte Carlo: per-row sampled output distribution histogram with mean, standard-deviation, and percentile markers
- LaTeX table (parentheses notation)

Note:

- Contribution breakdown is only available for Taylor modes (Monte Carlo does not return per-variable contributions).

## Unit Annotations

Desktop error propagation can store units for input symbols, constants, and the
single result output.

- **Display only**: units are saved in the workspace and shown in result
  text/CSV/LaTeX/plot labels. Numeric calculation is unchanged.
- **Validate expression**: when `pint` is installed, DataLab checks the formula
  dimensions before evaluation. Incompatible formulas fail before numeric
  calculation. Without `pint`, validation fails closed instead of falling back
  to unitless evaluation.

The bundled `Error propagation: unit labels` example runs in display-only mode
on every installation. With `pint` available, switch its unit mode to
validate-expression to check that `Distance / Time` produces `m/s`.
