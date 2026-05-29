# DataLab Theory Notes (Models, Algorithms, Output Fields)

This page summarizes the mathematics and the concrete outputs produced by the current DataLab implementation (source-of-truth = code behavior).

---

## 1. Unified Data Representation

### 1.1 High-precision numbers

All core computations use `mpmath` (`mp.mpf`) with a configurable `mp.dps` (decimal digits of precision).

### 1.2 Uncertainty (σ) input formats

1) **Parentheses notation**: `value(digits)[exp]`

- `1.2345(67)` means `1.2345 ± 0.0067`
- `1.2345(67)[-2]` means `(1.2345 ± 0.0067) × 10^-2`

2) **Separate σ column**: provide a dedicated `sigma` column (or pick it in the UI).

### 1.3 Header normalization and aliases

Column headers are normalized into safe identifiers (non-alphanumerics → `_`, leading digit → prefixed). Legacy aliases:

- Error propagation: `x1/x2/...` are rewritten to canonical column symbols.
- Custom extrapolation: supports headers, `x1/x2/...`, plus `A/B/C` for the first three columns.

---

## 2. Unified Safe Expression Language (Custom Extrapolation / Error Propagation / Custom Fit Models)

All three custom-expression features reuse the same parser and the same whitelist: `data_extrapolation_latex_latest.py:safe_eval`.

### 2.1 Syntax and safety rules (AST whitelist)

- Allowed: numeric literals, variables, parentheses, `+ - * / ** %`, unary `+/-`, and calls to whitelisted functions.
- Mathematica-style is supported: `Sin[x]` (`[]` auto → `()`), `^` auto → `**`.
- Forbidden: attribute access (`a.__class__`), keyword arguments, string/object constants, and any non-whitelisted AST nodes.

### 2.2 Supported constants and functions

Constants (case-sensitive): `Pi`, `E`

Functions (capitalized):

- Basics: `Sin`, `Cos`, `Tan`, `Asin`, `Acos`, `Atan`, `Sinh`, `Cosh`, `Tanh`, `Asinh`, `Acosh`, `Atanh`
- Exp/Log: `Exp`, `Log`, `Ln`, `Log10`, `Sqrt`, `Power`
- Common: `Abs`, `Erf`, `Gamma`
- Special: `Zeta`, `Hyp0f1`, `Hyp1f1`, `Hyp2f1`, `PolyLog`, `BesselJ`, `BesselY`, `Airy`

---

## 3. Extrapolation

For each data row, extrapolation produces an extrapolated value `V`, an uncertainty estimate `U`, plus method metadata.

### 3.1 Default three-point formula (quadratic)

Given `A,B,C`:

- `V = ((C - B)^2) / (B - A) + C`
- `U = max(|V-A|, |V-B|, |V-C|)`

### 3.2 Power-law extrapolation (power_law)

Model: `E(x) = E_inf + a * x^(-p)`

Given `(E1,E2,E3)` and `(x1,x2,x3)`:

- `R = (E1-E2)/(E2-E3)`
- Solve `(x1^{-p}-x2^{-p})/(x2^{-p}-x3^{-p}) = R` for `p`
- `a = (E1-E2)/(x1^{-p}-x2^{-p})`
- `E_inf = E1 - a*x1^{-p}`

### 3.3 Sequence accelerators (Richardson / Shanks / Wynn ε / Levin u)

Backed by `mpmath` routines and returning extra `metadata` (e.g. error estimates).

### 3.4 Uncertainty `U` for non-quadratic methods: reference-column difference

For `power_law` / accelerators / `custom`:

- `U = |V - reference|`

The reference column defaults to the 3rd column; `auto_max_diff` can pick the column that maximizes `|V - col_i|` for a conservative `U`.

### 3.5 Extrapolation outputs

Per-row fields:

- `value` (V), `uncertainty` (U), `method`
- `details` (e.g. `reference_column`, power-law `exponent/amplitude`, accelerator metadata, custom `formula`)

---

## 4. Error Propagation

For each row of uncertain inputs, compute `f(x)` and propagate σ.

### 4.1 First-order propagation

- `σ_f = sqrt( Σ ( ∂f/∂x_i * σ_i )^2 )`

For `order=2`, the implementation adds Hessian (second-derivative) contributions and applies a mean correction to the reported value (closer to Monte Carlo mean):

- `E[f] ≈ f(μ) + 1/2 * Σ_i (∂²f/∂x_i²) * σ_i²`
- `Var[f] ≈ Σ_i (∂f/∂x_i)² σ_i² + 1/2 * tr((H Σ)²)`

Here `H` is the Hessian and `Σ` is the input covariance matrix; the current implementation assumes diagonal `Σ` (independent inputs).

### 4.2 Partials: symbolic first, numerical fallback

The implementation tries symbolic differentiation (Sympy) first, and falls back to numerical finite differences when needed.

Numerical partials use central differences:

- `∂f/∂x ≈ (f(x+h) - f(x-h)) / (2h)`

The step size `h` is adaptive with `mp.dps` (rule of thumb: order-1 `h ~ eps^(1/3)`, order-2 `h ~ eps^(1/4)`, scaled by `max(1,|x|)`), balancing truncation and rounding errors.

### 4.3 Referenced-input detection

An AST scan detects which columns/constants are actually referenced; only those are used for propagation (fallback = use all on parse failure).

### 4.4 Outputs

Per-row:

- `value`:
  - Taylor `order=1`: `f(μ)` at the working point
  - Taylor `order=2`: `≈ E[f]` (with mean correction)
  - Monte Carlo: sample mean
- `uncertainty`: standard uncertainty (standard deviation)
- optional `contributions` (variance contributions per input)

---

## 5. Fitting

Fit `(x_i, y_i)` to a model and report parameters, uncertainties, covariance, and goodness-of-fit metrics.

### 5.1 χ² objective and weights

Residuals: `r_i = y_model(x_i; p) - y_i`

- Unweighted: `χ² = Σ r_i^2`
- Weighted: `χ² = Σ w_i r_i^2` (typical `w_i = 1/σ_i^2`)

`dof = n - k` (n points, k free parameters).

### 5.2 Explicit linear models (polynomial / 1/x^p)

Linear-in-parameters form `y ≈ Σ b_j φ_j(x)` solved via QR least squares (weighted by scaling rows with `sqrt(w_i)` when applicable).

### 5.3 Nonlinear / custom expressions (including templates: power_limit, Padé)

Custom model expressions are parsed via `fitting/model_parser.py:build_model_specification`:

- Evaluation uses the same `safe_eval` as extrapolation/error-propagation.
- Parameter partials are numerical (central difference).
- Optimization solves `∂χ²/∂p_j = 0` using `mp.findroot`, trying multiple seed variants.

Templates:

- Power-law limit: `A*x**(-p) + C` (constraint `p ≥ 0.1`)
- Padé(m|n): `(a0 + a1 x + ... + a_m x^m) / (1 + b1 x + ... + b_n x^n)`

### 5.4 What is covariance? How is it computed?

Near the optimum, approximate:

- Jacobian `J_{i,j} = ∂y_model/∂p_j` at the solution (rows scaled by `sqrt(w_i)` if weighted)
- `Cov ≈ (J^T J)^{-1} * σ²`, with `σ² ≈ χ²/dof`
- Parameter standard errors: `σ(p_j) = sqrt(Cov_{j,j})`

Singular/ill-conditioned cases trigger warnings and `NaN` uncertainties.

### 5.5 FitResult outputs

- `params`, `param_errors_stat/sys/total` (and compatibility `param_errors`)
- `covariance`, `residuals`, `fitted_curve`
- metrics: `chi2`, `reduced_chi2`, `aic`, `bic`, `r2`, `rmse`
- `details`: expression, weighted flag, boundary/covariance warnings, etc.

Implementation note (current code):

- Desktop: “statistical weighting” builds `w=1/σ²` for weighted χ²/covariance, and does not add a separate systematic term (to avoid double counting).
- Web: the current `fit_weighted` flag feeds σ into ±σ refits (systematic estimate) and does not apply weighted χ².

---

## 6. Statistics

Arithmetic/weighted means with optional σ:

- Mean, standard deviation (sample/population), standard error, min/max
- Weighted mean uses `w=1/σ^2`, and may report effective `n_eff = (Σw)^2/Σ(w^2)`

---

## 7. Export & Typesetting

All modules can format results in parentheses notation and generate:

- CSV
- LaTeX tables (optionally aligned via `dcolumn`/`siunitx`)
- optional PDF compilation in supported environments
