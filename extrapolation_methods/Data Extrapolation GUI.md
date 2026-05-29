# Data Extrapolation GUI  
# Fitting Module – Technical Design Specification  
**Version**: 1.0  
**Author**: Hao Fang  
**Module**: High-Precision Fitting (sympy + mpmath)  

---

# 1. Overview

This document defines the complete design of the **Data Fitting Module** for the Data Extrapolation GUI. The system already supports:

- sequence extrapolation  
- power-law extrapolation  
- high-precision error propagation  
- arbitrary-precision computation via mpmath  

The new module introduces:

1. **Custom multi-parameter, multi-variable nonlinear fitting**  
2. **Explicit fitting modes with AIC/BIC metrics for manual comparison**  
3. **Full statistical evaluation and uncertainty estimation**  
4. **A visualization panel** with automatic plotting and export  
5. **Parameter constraints support**  
6. **High-precision symbolic differentiation (sympy)**  
7. **Manual comparison across supported explicit models**

---

# 2. Functional Requirements

## 2.1 Custom Model Fitting

The system shall allow users to define arbitrary functions:

\[
f(x_1, x_2, ..., x_N; p_1, p_2, ..., p_M)
\]

with full support for:

- multi-dimensional input variables  
- multiple parameters  
- symbolic parsing through **sympy**  
- automatic derivative generation (∂f/∂pₖ)  
- arbitrary precision evaluation through **mpmath**  
- nonlinear least-squares solution via `mp.findroot` or gradient-based minimization  

The system returns:

- fitted parameters  
- parameter uncertainties (variance from Hessian)  
- χ², reduced χ²  
- R², RMSE  
- residual vectors  
- confidence intervals  

## 2.2 Parameter Constraints

Support:

- fixed parameters  
- upper and lower bounds  
- linear or functional constraints: e.g. `p2 = 2*p1`  
- parameter initial values  

Parameter specification (example):

```json
{
  "p1": {"initial": 0.1, "min": 0, "max": 1},
  "p2": {"initial": 1.0, "expr": "2*p1"},
  "p3": {"initial": 3.0}
}
```

---

# 2.3 Explicit Model Selection

The software fits the dataset with the model explicitly selected by the user.
Supported model families are polynomial, inverse-power series, Padé,
power-limit templates, custom expressions, and desktop self-consistent/implicit
models. AIC/BIC and residual plots are reported so users can compare repeated
runs manually.

### Model Comparison

For each selected model run:

1. Fit is performed
2. χ², AIC, BIC are computed
3. Residuals and fitted curves are exported

System outputs:

- selected model parameters
- model quality metrics
- fitted curve and residual plots

---

# 2.4 Fitting Quality Metrics

Returned:

- χ²  
- reduced χ²  
- AIC  
- BIC  
- R²  
- RMSE  
- residual statistics  
- parameter covariance matrix  
- parameter uncertainties  
- confidence intervals  

---

# 3. Algorithm Design

## 3.1 Symbolic Parsing

User expression:

```
f_expr = "a*x**2 + b*y + c"
```

System:

1. sympy parses variables and parameters  
2. builds symbolic expression  
3. computes analytical derivatives:

\[
\frac{\partial f}{\partial p_k}
\]

4. lambdifies both f and ∂f/∂pₖ into **mpmath** functions  

Allows arbitrary precision and stability.

---

## 3.2 Nonlinear Least-Squares Solver

The χ² function:

\[
\chi^2(p) = \sum_i (f(x_i) - y_i)^2
\]

We solve:

\[
\frac{\partial \chi^2}{\partial p_k} = 0
\]

using `mp.findroot`.

Optionally:

- gradient descent  
- Levenberg-Marquardt (mp implementation)  
- covariance extraction via Hessian  

---

## 3.3 Auto Model Selector

For each candidate model:

1. Fit parameters  
2. Evaluate:
   - χ²  
   - AIC  
   - BIC  

\[
AIC = 2k + n\ln(\chi^2/n)
\]

\[
BIC = k\ln(n) + n\ln(\chi^2/n)
\]

3. Choose model with minimum AIC  
4. Store per-model results for comparison  

---

# 4. Visualization System

## 4.1 Right-Side Fitting Plot Panel

### Required Plots

1. **Scatter plot with error bars**  
2. **Fitted curve** for the selected explicit model  
3. **Residual plot**  
4. **Extrapolation plot (x→∞ or n→∞)**  
5. **Comparison of manually selected explicit model curves**  

### Plot Features

- LaTeX axis and labels  
- logarithmic / power / reciprocal coordinate transforms:  
  - log x  
  - log y  
  - log-log  
  - 1/x  
  - 1/x²  
  - arbitrary user-defined transform  
- high DPI (300+)  
- PDF / EPS / PNG / SVG export  
- arbitrary-precision evaluation via mpmath  
- custom colormap  
- customizable markers  

---

# 5. Software Architecture

```
fitting/
├── model_parser.py         # sympy parsing of custom expressions
├── hp_fitter.py            # high-precision solver (sympy+mpmath)
├── auto_models.py          # low-level explicit linear-basis definitions
├── model_selector.py       # AIC/BIC model ranking
├── constraints.py          # parameter constraints engine
├── plot_fitting.py         # complete plotting toolkit
└── report.py               # unified result structure + LaTeX output
```

---

# 6. API Specification

## 6.1 Custom Fit API

```python
fit_custom(
    f_expr="a*x**2 + b*y + c",
    args={"x": x_data, "y": y_data},
    params={"a": 1.0, "b": 1.0, "c": 0.0},
    constraints={
        "a": {"min": 0},
        "b": {},
        "c": {}
    },
    precision=100
)
```

Returns:

```json
{
  "params": {...},
  "errors": {...},
  "chi2": ...,
  "R2": ...,
  "residuals": [...],
  "fitted_curve": [...]
}
```

---

## 6.2 Auto Model Fit API

```python
result = fit_auto(x_data, y_data)
```

Returns:

```json
{
  "best_model": "power_law",
  "model_results": {
      "power_law": {...},
      "exponential": {...},
      "rydberg": {...},
      "shanks": {...}
  },
  "comparison": {...}
}
```

---

# 7. Export Capabilities

The module must support exporting:

- PDF  
- EPS  
- PNG  
- SVG  
- LaTeX tables  

Applied to:

- fitted curves  
- residual plots  
- extrapolation plots  
- multi-model comparison plots  

---

# 8. Future Extensions

Possible enhancements:

- Bootstrap uncertainty estimation  
- Bayesian inference / MCMC sampling  
- Joint multi-dataset global fitting  
- Integration with CODATA physical constants  
- Built-in atomic units conversion in fitting interface  

---

# END OF DOCUMENT
