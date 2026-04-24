# DataLab Web Documentation

Welcome to DataLab Web — a high‑precision tool for extrapolation and uncertainty analysis.

## Quick Navigation

- [User Guide](guide) - How to use the web UI
- [Theory Notes](theory) - Models, algorithms, and output fields (covariance, propagation, etc.)
- [Export & Typesetting](export) - CSV / LaTeX / PDF and display formatting
- [Deployment](deploy) - Server deployment and configuration
- [FAQ](faq) - Troubleshooting and common questions
- [Roadmap](roadmap) - Project plan and future work

## Overview

DataLab Web is a browser-based, high‑precision numerical tool with four main modules:

### Extrapolation
Extrapolate numerical sequences to estimate limits or trends. Supported methods include:
- Power‑law (3-point) extrapolation
- Richardson acceleration
- Shanks transform / Wynn ε algorithm
- Levin u-transform
- Custom formula extrapolation

### Error Propagation
Propagate uncertainties through formulas. Key features:
- Numerical partial derivatives
- Automatic uncertainty synthesis
- Joint propagation of constants and data
- Visualization of uncertainty contributions

### Fitting
Fit datasets and obtain best-fit parameters. Supported modes include:
- Polynomial fitting
- Inverse power series fitting
- Padé approximation
- Preset model library
- Custom model expressions

### Statistics
Compute weighted/unweighted statistics for data (optionally with σ), with multiple statistical modes.

## Input Formats

DataLab Web supports two uncertainty representations:

**Parentheses notation**: `value(uncertainty)[10^exponent]`
```
1.2345(67)       # means 1.2345 ± 0.0067
1.2345(67)[-2]   # means 1.2345 ± 0.0067 × 10^-2
```

**Separate columns**: value and uncertainty in two columns
```
value    sigma
1.2345   0.0067
2.3456   0.0089
```

## Outputs

- **CSV download**: export table data
- **LaTeX**: generate LaTeX table text with parentheses notation
- **PDF export**: optional PDF compilation (requires a LaTeX installation)
- **Plots**: extrapolation trend plots, uncertainty contribution plots, etc.

## Getting Started

1. Choose a module on the home page (Extrapolation / Error Propagation / Fitting / Statistics)
2. Provide input data (paste text or upload a file)
3. Configure parameters and options
4. Click the run button to compute results
5. Download CSV, copy LaTeX, or export PDF

## Getting Help

- Use the **?** help buttons on each page for in-context tips
- Check the [FAQ](faq) for common issues

---

Tip: the **?** buttons provide function lists and parameter explanations.
