# DataLab Desktop Documentation

This directory contains **offline documentation for the DataLab desktop application (PySide6)**, written around the desktop UI design and workflows.

## What you can do in the desktop app

The desktop app provides four main modules:

- Extrapolation: extrapolate multi-column sequence data and output the limit and uncertainty
- Error propagation: compute formulas on uncertain inputs and propagate uncertainties
- Fitting: fit explicit models and output parameters, metrics, residuals and curves
- Statistics: compute (weighted/unweighted) statistics and mean estimates

Common capabilities:

- Multiprecision computation via `mpmath`
- Unified result area: Values / Log / LaTeX / PDF Preview
- CSV export, LaTeX table generation, optional PDF compilation
- Log axes in fitting plots (`log-x` / `log-y`), with automatic fallback for non-positive data

## Where to start

- Read the User Guide for the desktop layout and basic workflow.
- For algorithms and output definitions (covariance, propagation, etc.), read “Theory Notes”.
- Then open the module page you need (Extrapolation / Error Propagation / Fitting / Statistics).
- For exporting and typesetting, see “Export & Typesetting”.
