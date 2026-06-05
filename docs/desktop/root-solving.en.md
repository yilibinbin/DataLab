# Root Solving

The root-solving module solves equations in the form `F(...)=0`. Enter one equation per line. Scalar, scan-multiple, polynomial, and system modes share the same safe expression handling, constants substitution, precision setting, and uncertainty parser.

## Inputs

- Equations: residual expressions such as `x^2 - A`; DataLab solves them as zero equations.
- Unknowns: names, initial values, and optional lower/upper bounds. Bounds are recommended for scan-multiple mode.
- Input data: when data rows are present, roots are solved row by row; without data rows, DataLab solves a single problem.
- Constants: disabled by default. Enabled constants enter the expression scope but are not treated as unknowns.

## Modes

- Scalar: one unknown, one real root.
- Scan multiple roots: scan an interval and return multiple roots.
- Polynomial: return roots of a univariate polynomial.
- System: solve coupled equations with multiple unknowns.

## Uncertainty

Inputs may use compact notation such as `1.23(4)` or `3.2898419602500(36)[+9]`. Taylor propagation reuses the derivative-based approach from error propagation; Monte Carlo samples uncertain inputs and resolves the roots. The result view and LaTeX output use compact value-with-uncertainty notation controlled by the global uncertainty-digits option.

## Plots

When “Generate plots” is enabled, scalar roots show the residual curve and root marker. Tiny root uncertainties get automatic local inset plots while the main plot remains true scale. Two-dimensional systems show zero-contour curves and their intersection. Higher-dimensional systems do not generate a plot and report a warning.
