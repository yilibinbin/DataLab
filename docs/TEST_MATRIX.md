# DataLab Test Matrix

## Automated (recommended every change)

Run from `data_extrapolation_gui/DataLab`:

- Syntax compile: `python -m compileall -q .`
- Unit/integration tests: `pytest -q`

## What the automated tests cover

### Extrapolation

- Methods: `quadratic`, `power_law`, `custom`, `shanks`, `wynn_epsilon`, `levin_u` (variants `u/t/v`), `richardson` (requires ≥4 terms).
- Uncertainty reference: default reference column, `auto_max_diff`.
- Table generation:
  - `generate_latex_table`: `use_dcolumn` on/off, `latex_group_size` (incl. `0`), `result_uncertainty_digits`, `table_segments` splitting.
- Display/LaTeX consistency for tiny uncertainties: guards against low `mp.dps` causing re-rounding.

### Error Propagation

- Methods: Taylor (order 1/2), Monte Carlo, and method aliases (`mc`, `monte_carlo`, `montecarlo`, `monte-carlo`).
- Theory checks: nonlinear examples vs analytic results and Monte Carlo sanity.
- Table generation:
  - `generate_error_propagation_table`: `use_dcolumn` on/off, `latex_group_size`, `result_uncertainty_digits`, `used_columns` filtering, `table_segments`.

### Fitting

- Custom expression parsing security (rejects unsafe expressions).
- Fit correctness: exact linear model recovers parameters, residuals ≈ 0.
- Covariance matrix sanity (shape/symmetry).
- Branch coverage:
  - `data_sigmas` systematic uncertainty refits (sys errors non-zero).
  - `weights` branch (avoids double counting systematic component).

### Statistics

- Mean modes: sample vs population variance denominator.
- Weighted mean: known-case correctness, σ=0 anchor behavior, variance toggle.
- LaTeX generation: `generate_statistics_latex` (via existing tests).

### Web (Flask)

- API smoke tests:
  - `/api/ui-specs`
  - `/api/function-help`
  - `/api/help_specs` (placeholder substitution)
  - `/api/method-help/<key>` (404 on invalid key)

## Manual GUI checklist (PySide6 Desktop)

Automated tests do not click through the desktop GUI. For release verification, run:

`python ./data_extrapolation_gui.py`

Then, for each page (Extrapolation / Error Propagation / Fitting / Statistics):

- Input mode: file + manual (each alone, and both combined).
- Precision controls: `mp.dps` changes + display digits/scientific toggle; confirm result panel updates without recomputation.
- LaTeX controls: input digits, uncertainty digits, `use_dcolumn`, `latex_group_size`, segmented tables (if enabled).
- Export: CSV/LaTeX/PDF (where supported), and verify preview matches saved files.
- Help: function list/help panel and all “?” tooltips/dialogs in both `zh/en`.

