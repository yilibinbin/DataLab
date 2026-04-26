# Changelog

All notable changes to DataLab are documented in this file.
DataLab follows [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

## [2.0.0] — 2026-04-26

First public release. Desktop is shipped as one-click installable
macOS / Windows bundles with Python, PySide6, and the full scientific
stack embedded — no external runtime needed.

### Added
- **Sequence extrapolation** — Richardson, Wynn-ε, Levin u-transform,
  custom power-law formulas
- **Curve fitting** — automatic model selection by AIC/BIC + optional
  MCMC posterior refinement
- **Error propagation** — `1.23(4)[-2]` compact uncertainty syntax +
  SymPy-based symbolic partial derivatives
- **Weighted statistics** — weighted mean, standard error, RMS
  dispersion
- **LaTeX export + inline PDF preview** — Tectonic engine by default
  (auto-downloaded to `~/.datalab/bin/`, no TeX Live install needed);
  pdflatex / xelatex still selectable
- **Bilingual UI** — 中文 / English toggleable from the menu
- **5 bundled example files** under `examples/` covering all four
  modes
- **Two frontends, one core** — PySide6 desktop + Flask web app share
  the same `extrapolation_methods/`, `fitting/`, `datalab_latex/`,
  `shared/` packages

### Fixed
- siunitx v2 / v3 (incl. Tectonic-bundled v3.0.49) full
  compatibility — `digit-group-size` guard date = 2024-01-01
- Pathological fit parameters no longer produce 21-digit integers
  like `4(1543551156637860)[\text{-18}]` in LaTeX output
- LaTeX tab — line-number gutter + engine selector moved to the
  semantically correct location (was previously inside the compute
  panel)
- Data table — equal column widths + add/remove row & column
  buttons (previously could only add)
- Windows GBK / CP936 encoded `.tex` files now load correctly
- MCMC pre-flight + health checks prevent NaN walkers from
  contaminating the chain
- `DataLab.spec` paths are portable — any clone can build, not just
  the original author's machine

### Tests
- `pytest -q` → **769 passed, 11 skipped**
- Coverage spans high-precision Mathematica reference values, all four
  modes end-to-end, and every LaTeX output path

[Unreleased]: https://github.com/yilibinbin/datalab-review-r9/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/yilibinbin/datalab-review-r9/releases/tag/v2.0.0
