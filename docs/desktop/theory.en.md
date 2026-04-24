# DataLab Theory Notes (Models, Algorithms, Output Fields)

This page summarizes the mathematics and outputs produced by the current DataLab implementation (code behavior is the source of truth).

---

## 1. Unified Data Representation

- High-precision numbers: `mpmath.mp.mpf` with configurable `mp.dps`.
- Uncertainty σ input:
  - parentheses notation `value(digits)[exp]`
  - or a separate sigma column.

---

## 2. Unified Safe Expression Language

Custom extrapolation, error propagation, and custom fit models reuse the same safe parser and whitelist: `data_extrapolation_latex_latest.py:safe_eval`.

- Allowed operators: `+ - * / ** %` and unary `+/-`
- Mathematica-style: `Sin[x]`, `^` → `**`
- Forbidden: attribute access, keyword args, and non-whitelisted AST nodes

Constants: `Pi`, `E` (case-sensitive)

Functions (capitalized): `Sin`, `Cos`, `Tan`, `Exp`, `Log`, `Sqrt`, `Erf`, `Gamma`, `Zeta`, `BesselJ`, etc.

---

## 3. Extrapolation

- Quadratic 3-point:
  - `V = ((C - B)^2)/(B - A) + C`
  - `U = max(|V-A|, |V-B|, |V-C|)`
- Power-law: `E(x) = E_inf + a*x^{-p}` solved from three `(x,E)` points
- Accelerators: Richardson / Shanks (Wynn ε) / Levin
- Non-quadratic methods use `U = |V - reference|` (default reference = 3rd column; `auto_max_diff` supported)

Outputs per row: `value`, `uncertainty`, `method`, `details` (reference column, parameters/metadata).

---

## 4. Error Propagation

- Taylor (order 1/2): derivative-based propagation; order 2 includes Hessian contributions and applies a mean correction to the reported value (`≈ E[f]`).
- Monte Carlo: samples independent normal inputs and returns sample mean ± standard deviation.
- Partials: symbolic (Sympy) when possible; numerical finite differences otherwise (adaptive `h` with `mp.dps`).
- Optional per-input variance contributions (Taylor only)

Outputs per row: `value`, `uncertainty`, optional `contributions`.

---

## 5. Fitting

- Objective:
  - unweighted `χ² = Σ r_i^2`
  - weighted `χ² = Σ w_i r_i^2` (typical `w_i = 1/σ_i^2`)
- Linear models: QR least squares (rows scaled by `sqrt(w_i)` when weighted)
- Custom/nonlinear models:
  - expression evaluated via `safe_eval`
  - numerical parameter partials
  - solve `∂χ²/∂p_j=0` using `mp.findroot`
  - templates: power-limit `A*x**(-p)+C`, Padé(m|n)

Covariance:

- `Cov ≈ (J^T J)^{-1} * (χ²/dof)`, with `J_{i,j} = ∂y_model/∂p_j` (weighted row scaling if applicable)
- parameter σ from `sqrt(diag(Cov))`

Outputs: parameters, stat/sys/total errors, covariance, residuals, fitted curve, and metrics (`chi2`, `AIC`, `BIC`, `R2`, `RMSE`, ...).

Implementation note (current code):

- Desktop: “statistical weighting” builds `w=1/σ²` for weighted χ²/covariance, and does not add a separate systematic term (to avoid double counting).
- Web: the current `fit_weighted` flag feeds σ into ±σ refits (systematic estimate) and does not apply weighted χ².
