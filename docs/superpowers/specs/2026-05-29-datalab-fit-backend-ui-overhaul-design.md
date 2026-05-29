# DataLab Fit Backend and GUI Overhaul Design

## Status

Approved design for implementation planning.

## Goals

DataLab should expose fitting as explicit, reproducible scientific workflows.
The fitting UI should show only real configuration parameters, and the backend
should choose efficient solvers without exposing implementation details to
ordinary users.

This design covers five linked changes:

1. Remove automatic fitting completely.
2. Unify custom and self-consistent fitting behind one optimizer boundary.
3. Optimize implicit fitting for common and general cases.
4. Replace inline formula previews with clear preview dialogs.
5. Ship tested example workspaces for each major calculation module.

## Non-Goals

- Do not keep automatic fitting as a hidden product feature.
- Do not expose a normal-user "SciPy vs mpmath" backend selector.
- Do not make formula rendering part of computation.
- Do not rewrite every calculation module in one implementation step.
- Do not promise arbitrary speedups for all implicit models.

## Fitting Information Architecture

The fitting panel will keep only explicit model choices:

- polynomial;
- inverse-power series;
- Pade;
- power-limit;
- custom model;
- self-consistent / implicit model.

The UI will remove automatic fitting from menus, controls, workers, tests, and
documentation. Existing workspaces that contain automatic-fit state will open in
a degraded mode: DataLab will ignore the obsolete automatic-fit configuration,
preserve the rest of the workspace, and report the ignored feature once.

The fitting panel will group settings by purpose:

- data mapping: variables, target column, and weighting;
- calculation control: calculation precision, timeout, cancellation, and
  global parallel settings;
- model definition: only the controls required by the selected model;
- results: parameters, uncertainties, covariance, residuals, statistics, plots,
  and LaTeX.

Implementation details such as "new backend" flags will not appear in the
normal UI.

## Optimizer Selection

The user will configure calculation precision, not backend names. The current
label "多精度位数 (mpmath)" will become "计算精度".

Backend selection will be automatic:

- If calculation precision is less than or equal to 16 and the model shape is
  supported, DataLab will use the SciPy double-precision optimizer.
- If calculation precision is greater than 16, DataLab will use the high
  precision mpmath path.
- If SciPy is unavailable, unsupported, or fails, DataLab will fall back to the
  mpmath path and record the fallback in logs and result details.

Result details will include the actual backend, for example
`optimizer_backend=scipy_least_squares` or
`optimizer_backend=mpmath_high_precision`.

## Unified Fitting Boundary

Custom and self-consistent fitting will share one execution boundary:

- `ModelProblem` describes variables, targets, weights, constants, expressions,
  safe-eval behavior, and model type.
- `ParameterState` continues to own initial values, fixed values, bounds, and
  dependent parameter expressions.
- `FitOptimizer` chooses a solver and returns a standard `FitResult`.

All supported paths must preserve:

- statistical weighting from uncertainty columns;
- fixed parameters;
- bounds;
- dependent parameters;
- constants;
- safe expression evaluation;
- covariance and parameter uncertainties when meaningful;
- chi-square, reduced chi-square, AIC, BIC, RMSE, and residuals;
- workspace save and restore;
- LaTeX report generation.

## Implicit Model Strategies

Self-consistent models have several mathematically distinct cases.

### Observed Implicit Variable, Linear Parameters

When the output expression is the implicit variable itself and the implicit
equation is linear in free parameters, DataLab will fit:

```text
RHS(x, u_observed, params) ~= u_observed
```

This path avoids point-by-point implicit solves. It uses weighted QR least
squares in the selected precision domain. The quantum-defect d8 case belongs
to this class.

### Observed Implicit Variable, Nonlinear Parameters

When the output expression is the implicit variable itself but the equation is
nonlinear in parameters, DataLab will still avoid solving the implicit variable
for each point. It will minimize the observed-variable residual directly with
the selected nonlinear optimizer.

### General Implicit Output

For general models:

```text
u = g(x, u, params)
y = f(x, u, params)
```

DataLab must solve the implicit variable per point. This path will use:

- cached solves keyed by variables and parameters;
- warm starts where possible;
- explicit cancellation checks;
- bounded diagnostics for solve failures;
- SciPy acceleration only when precision and model constraints allow it.

Future support for multiple implicit variables should extend the implicit
solver layer, not the GUI or `FitResult` protocol.

## Formula Preview

Inline formula preview labels will be removed from configuration panels. Each
formula editor will have a title row with a preview button:

```text
Self-consistent equation:                         [Preview]
[ formula editor ]
```

Clicking the button opens a dialog. The dialog will show:

- a high-contrast rendered formula;
- the original expression text;
- a copy action for the expression;
- a clear error message if rendering fails.

The dialog will use a system panel or light formula surface, even in dark mode,
so black formulas never render on a black background. Formula rendering failure
will not block computation.

This removes the formula preview currently appearing below the MCMC checkbox.

## Parameter and Constants Editors

Custom fitting and self-consistent fitting will share one parameter table
component.

The parameter table header will provide:

- add parameter;
- delete selected parameter;
- detect parameters;
- clear empty rows.

Parameter detection will merge with existing rows. It will keep user-provided
initial values, fixed values, bounds, and expressions, and add only missing
detected parameters.

Custom fitting and self-consistent fitting will also share the reusable
constants editor. When "Enable constants" is unchecked, the editor will hide
its table, text view, and buttons. It will keep draft content so users can
restore it by re-enabling constants.

Constants text view will match the error-propagation constants format.
Disabled constants will not enter compute payloads, but workspace files will
preserve their draft content with `constants_enabled=false`.

## Example Workspaces

The repository will include generated example workspaces in
`examples/workspaces/`. The installer will ship them on macOS and Windows.

The app will add an "Open Example Workspace" entry. The entry will list examples
by module and open a copied workspace, not the installed original.

The first example set will cover:

- extrapolation;
- error propagation;
- statistics;
- custom fitting;
- self-consistent / implicit fitting;
- high-precision fitting;
- automatic SciPy acceleration through precision less than or equal to 16;
- constants;
- parameter constraints;
- weighted fitting.

Each example workspace will contain input data, configuration, a result
snapshot, and enough context for a user to rerun it.

## LaTeX and Verification

Verification will be staged.

Each implementation phase will run focused unit, integration, workspace, and
GUI smoke tests. The final phase will run release-level verification:

- all example workspaces open;
- all example calculations execute;
- LaTeX is generated for every module that supports it;
- LaTeX compiles where a TeX engine is available;
- GUI smoke tests cover the fitting panel, formula dialogs, constants editor,
  parameter table, and examples entry;
- macOS and Windows packages include example workspaces;
- update and packaging tests remain green.

Deleting automatic fitting must remove automatic-fit reports from LaTeX. Fitting
reports will describe the selected model, parameters, uncertainty treatment,
statistics, residuals, and configuration.

## Implementation Phases

### Phase 1: Fit UI Cleanup and Automatic-Fit Removal

Remove automatic fitting from GUI, backend, workspaces, tests, and docs. Add
old-workspace degradation tests.

### Phase 2: Unified Fitting Boundary

Introduce the shared problem and optimizer boundary. Keep current behavior for
existing mpmath paths before adding new optimization behavior.

### Phase 3: Implicit and Custom Optimizer Strategies

Add observed-implicit-variable nonlinear handling, SciPy acceleration for
precision less than or equal to 16, fallback diagnostics, and regression cases.

### Phase 4: Formula Preview and Editor Unification

Replace inline previews with preview dialogs. Add parameter add/delete controls.
Fix constants editor hiding and shared behavior.

### Phase 5: Examples and Release Verification

Generate example workspaces, add the app menu entry, test examples, verify
LaTeX, and run release-level package checks.

## Risks and Controls

- Automatic-fit removal is breaking. Old workspaces must degrade clearly.
- SciPy acceleration must never silently change high-precision runs.
- SciPy fallback must be visible in logs and result details.
- General implicit solving can still be slow. It needs diagnostics, timeout,
  and cancellation tests.
- Formula preview must remain display-only.
- Example workspaces must be generated or validated by tests to prevent drift.

## Acceptance Criteria

- No automatic fitting entry remains in normal GUI, backend execution, or
  generated reports.
- Users configure calculation precision, not optimizer implementation names.
- Precision less than or equal to 16 can trigger SciPy acceleration when safe.
- Precision greater than 16 uses high-precision mpmath behavior.
- Quantum-defect d8 weighted fitting remains fast and correct.
- Custom and implicit fitting share result semantics.
- Formula previews open only through buttons and are readable in light and dark
  themes.
- Constants editor hides its inputs when disabled and preserves drafts.
- Parameter rows can be added, removed, detected, and merged.
- Example workspaces ship with the app and run in automated verification.
- LaTeX generation and compilation checks cover representative modules.
