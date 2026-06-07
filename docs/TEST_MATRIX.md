# DataLab Test Matrix

## Automated (recommended every change)

Run from `data_extrapolation_gui/DataLab`:

- Syntax compile: `python -m compileall -q .`
- Unit/integration tests: `pytest -q`

### Installer Update Release Gate

- macOS `.pkg` is signed and notarized before auto-installable release
  status.
- Windows Inno installer is Authenticode-signed before
  auto-installable release status.
- `updates.json` contains only metadata, size, and SHA-256 values;
  installer arguments are constructed by application code.
- Offline startup performs no network request unless automatic updates
  were enabled.

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
- Implicit fitting performance:
  - `tests/test_implicit_performance_regression.py` verifies that nonlinear-output implicit models keep the user-facing output-space objective while using automatic SciPy or analytic-implicit acceleration.
  - `tests/test_implicit_scipy_backend.py` covers the automatic SciPy candidate gate, accepted-candidate materialization, rejected/error fallback, full-route timing labels (`start_norm`, candidate fit, rematerialization, comparator), fresh implicit-cache spot checks, unweighted `data_sigmas` skip, dependent-parameter skip, and numeric mpmath comparator fallback when analytic derivatives are unavailable.
  - `tests/test_implicit_seed_hints.py` and `tests/test_implicit_model.py` cover configured/warm/hint seed ordering, bounded seed attempt diagnostics, and root-branch audit fields.
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

Desktop GUI click workflows are a release gate:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_workspace_controller.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

Then, for each page (Extrapolation / Error Propagation / Fitting / Statistics):

- Input mode: file + manual (each alone, and both combined).
- Precision controls: `mp.dps` changes + display digits/scientific toggle; confirm result panel updates without recomputation.
- LaTeX controls: input digits, uncertainty digits, `use_dcolumn`, `latex_group_size`, segmented tables (if enabled).
- Export: CSV/LaTeX/PDF (where supported), and verify preview matches saved files.
- Help: function list/help panel and all “?” tooltips/dialogs in both `zh/en`.
