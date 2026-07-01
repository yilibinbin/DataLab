# DataLab P4.7-E Broader Unit Metadata Integration Plan

Status: E1/E2/E3/E4/E5/E6 are complete for their stated scope under Codex +
Antigravity Gemini Pro review. Claude is not used for this plan.
Date: 2026-06-28

Parent spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-7-unit-aware-calculations-spec.md`

Parent plan:
`docs/superpowers/plans/2026-06-26-datalab-p4-7-unit-aware-calculations-plan.md`

## 1. Scope

P4.7-E extends the already-reviewed P4.7 unit annotation contract beyond error
propagation. The first broader slice is display-only unit metadata for:

- root solving;
- fitting;
- statistics, including matrix, grouped, bootstrap, hypothesis, and
  time-series workflows.

This slice does not introduce unit conversion, active expression validation, or
unit algebra for these families. Unsupported active modes must fail closed with
diagnostics or request-construction errors instead of silently running as
unitless.

## 2. Current Code Facts

- `shared.unit_annotations.normalize_unit_annotations()` already owns the
  editable `datalab.units.annotations.v1` schema and rejects JSON floats,
  unsupported modes, malformed namespaces, and active validation without pint.
- `shared.unit_expression_validation.validate_expression_units()` exists, but
  is currently only wired into the error-propagation family. Reusing it for
  root solving, fitting, or statistics would need separate expression semantics
  and tests.
- `datalab_core.uncertainty` already normalizes `units`, validates
  `validate_expression`, stores the normalized object in the result payload,
  and projects labels through text/CSV/LaTeX/plots.
- `datalab_core.root_solving.build_root_solving_request()` and
  `run_root_solving()` currently have no `units` input or payload field.
- `datalab_core.fitting.build_fitting_request()` and `run_fitting()` currently
  have no `units` input or payload field. Fitting parameters already flow as
  optimizer metadata and must not become optimizer constraints.
- `datalab_core.statistics.run_statistics()` and the advanced statistics
  workflow payloads currently have no family-level `units` field. Statistics
  workflow semantics differ enough that units must remain labels unless a
  later reviewed feature defines method-specific unit algebra.
- Workspace save/restore currently persists `config.error.units` only.
  `config.root_solving.units`, `config.fitting.units`, and
  `config.statistics.units` are named by the spec but not broadly wired.
- `normalize_unit_annotations()` requires annotation keys to be canonical
  identifiers. Root/fitting/statistics column labels may be arbitrary UI text,
  so each family needs a reviewed raw-label-to-canonical-symbol map before
  annotations can be validated.

## 3. Design Decisions

1. Reuse `shared.unit_annotations`; do not add a second unit parser or schema.
2. For P4.7-E, accept only `enabled=false` or `enabled=true,
   mode="display_only"` for root/fitting/statistics. `validate_expression` and
   any future `convert_outputs` mode fail closed for these families.
3. Store normalized family units in the core result payload and semantic
   snapshot as `payload["units"]` / `snapshot["units"]` only when a units config
   is supplied.
4. Keep numeric payload shapes unchanged. Unit labels are separate metadata and
   never wrap or mutate numeric strings.
5. Keep fitting parameter units as display/report metadata only. They must not
   change initial values, fixed flags, bounds, constraints, covariance, or
   optimizer arrays.
6. Keep statistics units as value/sigma/output labels only. Do not infer that
   variance is squared units, that standard error is a different quantity, or
   that covariance/correlation matrices have derived unit algebra in this
   slice.
7. Web remains deferred for these families. If Web encounters active non-error
   units, it must preserve display-only metadata or fail closed; it must not
   claim active unit-aware calculations.
8. Unit annotations are keyed by canonical symbols, not raw UI labels. Raw
   labels are display metadata only. Duplicate or colliding canonical symbols
   must reject unit config instead of guessing.

## 4. Implementation Slices

### E1. Shared Family Unit Normalizer

Status: complete.

Add small shared helpers, likely in `shared/unit_annotations.py`, for
family-specific display-only normalization:

- Input: raw units mapping, allowed symbols per namespace, and family name.
- Output: normalized units mapping or `None`.
- Behavior:
  - `None` remains `None`;
  - `enabled=false` normalizes through the existing schema and may be retained
    only if needed for workspace round-trip;
  - `enabled=true, mode="display_only"` is accepted;
  - active modes fail with a clear error such as
    `root_solving units only support display_only in this release`.
- Add or reuse a canonical symbol-map helper for table-style labels:
  - converts raw labels to safe identifiers;
  - detects collisions;
  - returns display metadata so outputs can still show original labels;
  - rejects annotations keyed by raw labels unless they match the canonical key.

Verification:

- Unitless requests are unchanged.
- Display-only config normalizes with allowed namespace enforcement.
- Active modes fail closed for root/fitting/statistics.
- No-pint display-only path works.
- Raw labels with spaces/punctuation are either mapped deterministically or
  rejected with a clear collision diagnostic.

### E2. Core Request And Payload Carrying

Status: complete for root solving, fitting, and statistics core payloads.

Add optional `units` parameters to:

- `build_root_solving_request()`;
- `build_fitting_request()`;
- `run_statistics()` input handling and relevant advanced workflow request
  paths.

The core request builders normalize units using family-specific allowed symbols:

- root:
  - `inputs`: data headers and known row-value symbols;
  - `constants`: constants rows/text names;
  - `outputs`: root unknown names where known, otherwise `result`;
  - `parameters`: empty.
- fitting:
  - `inputs`: model variable names and/or source column names only when
    canonical and unambiguous;
  - `constants`: custom constants;
  - `parameters`: fitting parameter names;
  - `outputs`: target column or `result`.
- statistics:
  - `inputs`: selected value/sigma/time/group column names when canonical and
    unambiguous;
  - `constants` and `parameters`: empty;
  - `outputs`: selected value columns where applicable, otherwise `result`.

If canonical symbol mapping is ambiguous, the builder must reject the units
config rather than guess.

Update workspace validation so `config.root_solving.units`,
`config.fitting.units`, and `config.statistics.units` are accepted only under
the same display-only contract. Active modes in these family configs fail
closed until later slices define semantics.

Verification:

- Core unitless tests continue unchanged.
- New display-only units appear in result payloads without changing numeric
  results.
- Malformed or active units fail before computation and do not run a unitless
  fallback.

### E3. Semantic Snapshots, History, And Report Provenance

Status: complete for this slice. Root and statistics semantic snapshots
preserve `units`; fitting has no dedicated core semantic snapshot builder, so
its unit metadata is preserved as semantic snapshot provenance where fitting
snapshots exist. History comparison and report bundle attachment preservation
are covered by focused tests.

Thread normalized `units` into semantic snapshots:

- `build_root_result_snapshot()`;
- fitting semantic snapshot builder path, or if fitting lacks a core semantic
  snapshot builder, the Desktop/workspace semantic cache bridge must keep
  family units as provenance only;
- `build_statistics_result_snapshot()` and advanced statistics snapshot
  builders.

Reuse existing history/report metadata behavior where snapshots contain a
top-level `units` object. Do not duplicate units into metric rows.

Verification:

- Unit labels survive workspace save/restore and semantic refresh.
- History comparison emits metadata changes through the existing
  `_unit_metadata_summary()` path.
- Report bundles preserve unit metadata in snapshots.

### E4. Text, CSV, LaTeX, And Plot Labels

Status: root text/CSV/LaTeX sub-slice, statistics text/CSV sub-slice, and
statistics LaTeX/plot/display sub-slice are complete; fitting
text/CSV/LaTeX/plot label surfaces remain.

Project display-only units only at label boundaries:

- root:
  - text/CSV include `root_unit` or display labels for root value and
    uncertainty columns;
  - plots append units to root/value axes where applicable;
  - LaTeX keeps numeric cells pure and uses escaped header labels.
- fitting:
  - parameter table text/CSV/LaTeX include a separate `parameter_unit` field or
    escaped header label;
  - x/y plot axes append input/output units;
  - residual plots append output unit to residual axis.
- statistics:
  - scalar and advanced statistics text/CSV include `value_unit` or
    `sigma_unit` columns only when unit metadata is active;
  - LaTeX table headers/captions carry units but numeric cells remain pure;
  - plot y-axis labels append value units. Correlation heatmaps remain unitless;
    covariance matrix units are display provenance only until a separate
    covariance-unit algebra plan exists.

Verification:

- dcolumn/siunitx LaTeX still compiles because numeric cells stay numeric.
- Existing unitless CSV headers remain unchanged.
- Plot data arrays are unchanged.

Root sub-slice completion notes:

- Added shared display helpers for unit lookup by direct key, canonical label
  key, and optional `result` fallback.
- Root semantic Markdown/CSV adds a `root_unit`/`unit` column only when unit
  metadata exists.
- Root LaTeX adds text-only unit and failure columns as needed; numeric cells
  remain pure dcolumn/siunitx inputs.
- Desktop core-request root execution carries normalized unit metadata into
  the result payload and LaTeX writer.
- Validation: focused root/unit/LaTeX/Desktop worker tests -> 83 passed;
  py_compile, Ruff, and scoped diff-check passed. Gemini reviewed, two valid
  findings were fixed, and final re-review returned PASS.

Statistics text/CSV sub-slice completion notes:

- Ordinary statistics semantic text/CSV now adds `value_unit` and
  `uncertainty_unit` columns only when `units.outputs` has explicit output
  annotations.
- Unit lookup is a direct output-annotation lookup by metric key and reviewed
  uncertainty-key mapping; it does not infer dimensions from input units.
- Input-only units preserve the old text and CSV shape.
- Validation: focused statistics text/CSV unit tests -> 4 passed; py_compile,
  Ruff, and scoped diff-check passed. Gemini found the input-only CSV-shape
  risk, it was fixed, and final re-review returned PASS.

Statistics LaTeX/plot/display sub-slice completion notes:

- Promoted public statistics output unit lookup helpers so text/CSV, LaTeX,
  and GUI display paths use the same metric-key and uncertainty-key mapping.
- `generate_statistics_latex()` and `generate_statistics_latex_batches()` now
  accept optional display-only units. Input units appear only in text headers,
  output units appear in a text-only summary unit column, and numeric cells
  remain pure dcolumn/siunitx inputs.
- Ordinary Desktop statistics display now carries units through result text,
  CSV headers/rows, LaTeX generation, plot y-axis labels, and remembered
  result payloads when units metadata is present.
- Background worker LaTeX generation now uses the same single-batch writer as
  the foreground GUI, and falls back to the batch writer only for multi-batch
  outputs.
- Validation: focused statistics LaTeX/plot/Desktop/worker/core unit gate ->
  65 passed; py_compile, Ruff, and scoped diff-check passed. Gemini found
  worker single-batch parity, plot fallback, and helper-test coverage gaps;
  all were fixed and Gemini re-review returned PASS.

Fitting text/CSV/LaTeX/plot sub-slice completion notes:

- `FitResultPayload` now carries optional normalized display-only units from
  the core fitting service payload, including subprocess result
  serialization/deserialization.
- Desktop fitting Markdown and CSV rendering add unit columns only when unit
  metadata is present. Parameter units are row-local; RMSE uses the fitting
  output/result unit. Unitless outputs keep the existing table/header shape.
- `build_fit_latex_block()` now accepts optional fitting units and adds a
  text-only `Unit` column when any row has a unit. Numeric cells remain pure
  dcolumn/siunitx values; input target rows and RMSE use the output unit, and
  parameter/stat/sys rows use parameter units.
- Fitting plots now accept unit-aware labels. x/y/residual axes use input and
  output units, while the parameter axis receives a unit only when all
  displayed parameters share the same unit.
- Validation: fitting Markdown/LaTeX/plot/worker/core gate -> 95 passed;
  py_compile, Ruff, and scoped diff-check passed. Codex main-thread review
  found no actionable issue. Antigravity Gemini Pro first review produced
  four stale-snippet false positives; exact line-numbered re-review returned
  PASS.

### E5. Desktop Workspace Controls

Status: complete under the Codex + Antigravity Gemini Pro review policy.

Use the existing unit editor patterns from error propagation, but keep first
implementation conservative:

- Add hidden/internal config carrying first, so existing examples/workspaces can
  round-trip `config.<family>.units`.
- Add visible controls only after the core/output surfaces have tests.
- When visible, controls must use shared editor/table components and localized
  labels/tooltips, not duplicated per-family parsing code.
- Active mode choices for root/fitting/statistics must not expose
  `validate_expression` until family-specific validation semantics are reviewed.

Verification:

- Workspace capture/restore preserves `config.root_solving.units`,
  `config.fitting.units`, and `config.statistics.units`.
- Display-only units mark the workspace dirty/stale through the existing config
  hash.
- Visible controls, when enabled, round-trip through the same schema keys.

Implementation notes:

- Added one shared Desktop display-only unit control builder for root solving,
  fitting, and statistics. It reuses `ConstantsEditor`, localized labels and
  tooltips, schema keys, and the same visible-body toggle behavior.
- Added shared Desktop unit collection for display-only families. It reuses the
  existing `_unit_rows_to_map()` validation for blank/half-filled/duplicate
  rows and never exposes `validate_expression`.
- Wired visible units into root-solving core requests, fitting core requests,
  and the standard/multi-column statistics core request path. Advanced
  statistics branches are intentionally not hard-wired in this sub-slice
  because at least the time-series payload validator currently rejects extra
  payload keys before snapshot unit wrapping; advanced branch unit semantics
  need a separate reviewed payload contract.
- Workspace capture/restore now preserves and clears
  `config.root_solving.units`, `config.fitting.units`, and
  `config.statistics.units`. Missing legacy configs clear visible controls
  instead of leaving stale UI state.
- Validation before review: focused new tests -> 7 passed; affected Desktop,
  workspace, worker, and units tests -> 119 passed; py_compile, Ruff, and
  scoped diff-check passed.
- Review gate: Codex main-thread review found no actionable issue. The
  Antigravity companion wrapper hung without output and was stopped; the direct
  `agy --model "Gemini 3.1 Pro (High)"` read-only review completed and returned
  PASS with no actionable findings.

### E6. Advanced Statistics Display-Only Unit Projection

Status: complete under Codex + Antigravity Gemini Pro review. Claude was not
used.

Goal: close the gap left by E5 for advanced statistics workflows. Core
statistics requests can already carry normalized display-only units into
advanced payloads and snapshots, but the specialized renderers for
matrix/grouped/bootstrap/hypothesis/time-series bypass the ordinary statistics
unit-column path. E6 makes those units visible only at label/output boundaries.

Scope:

- Bootstrap confidence intervals:
  - Text/CSV: add `value_unit` only when `units.outputs` maps the bootstrap
    metric key or a reviewed alias such as `result`.
  - LaTeX: add a text-only `Unit` column to the metric table only when at least
    one metric has a unit; leave numeric cells formatted exclusively by the
    existing dcolumn/siunitx helpers.
  - Plots: append the output unit to the distribution x-axis label only when
    an explicit output unit exists.
- Hypothesis tests:
  - Text/CSV/LaTeX: add units only for scientific effect/statistic rows that
    map to explicit output annotations. Do not add units to p-values, alpha,
    reject-null decisions, diagnostics, degrees of freedom, or metadata rows.
  - No hypothesis-test numeric semantics change; units remain display-only.
- Time-series rolling/EWMA:
  - Text/CSV: add `value_unit` and `uncertainty_unit` columns only when
    explicit output annotations exist for the value column or `result`.
  - LaTeX: label observed/result/uncertainty headers with units or add
    text-only unit headers without modifying numeric cells.
  - Plots: append value/output unit to observed and rolling/EWMA axes; do not
    infer time units from the time/index column.
- Grouped statistics:
  - Text/CSV: add unit columns using explicit output annotations by metric key
    or selected value-column key. Do not infer units from group labels or from
    input-only units.
  - LaTeX/plots, if routed through existing grouped export helpers, follow the
    same text-only unit-column rule. If no dedicated grouped LaTeX/plot path
    exists, record the omission as a deferred export surface instead of
    claiming coverage.
- Covariance/correlation matrix:
  - Correlation remains unitless.
  - Covariance units are provenance only in this slice; no derived unit algebra
    is displayed unless a future reviewed plan defines exact covariance unit
    semantics.
  - Text/CSV may include a `unit` provenance column only when the value is an
    explicit display-only output annotation, not a derived unit guess.
- Desktop:
  - Standard statistics already passes visible unit controls to core requests.
    E6 may route the same display-only config into advanced statistics branches
    only through the existing `units` request input and snapshot wrapping, never
    by adding arbitrary keys to strict advanced payloads.
  - Active modes remain hidden/rejected. The GUI must not expose
    `validate_expression` for statistics.

Implementation constraints:

- Reuse `shared.unit_annotations` and existing statistics unit helpers. Do not
  introduce a second unit parser or per-workflow duplicate schema.
- Keep unitless text/CSV/LaTeX shapes byte-for-byte compatible where feasible.
  New unit columns appear only when output annotations are present.
- Never append unit text inside numeric cells. dcolumn/siunitx formatting
  receives the same numeric strings as before.
- No unit conversion, no dimensional validation, no variance/std/covariance
  derived-unit inference, and no automatic inference from column names.
- Web remains deferred for advanced statistics unit display unless a separate
  reviewed Web parity slice is created.

Verification:

- Focused core renderer tests for bootstrap, hypothesis, time-series, grouped,
  and matrix unitless stability plus explicit-output-unit display.
- LaTeX tests for bootstrap/hypothesis/time-series unit labels with dcolumn and
  siunitx enabled, proving numeric cells remain pure.
- Plot-label tests for bootstrap/time-series where existing plot helpers exist.
- Desktop advanced statistics tests proving visible statistics units are
  passed to advanced core requests without adding extra advanced-payload keys
  and without breaking strict validators.
- Ruff, py_compile, scoped diff-check, and Codex + Antigravity Gemini Pro
  implementation review.

Plan review notes:

- Codex main-thread review found no blocker after the key-mapping,
  numeric-cell purity, and strict-payload constraints were made explicit.
- Antigravity Gemini Pro reviewed the plan against the current specialized
  statistics renderers and returned PASS with no actionable findings.
- Implementation review notes:
  - Codex main-thread review found and fixed the `result` unit fallback
    boundary so unknown statistics output keys still return no unit.
  - Antigravity Gemini Pro found two valid implementation issues: advanced
    payload validators allowed optional `units` without structural validation,
    and bootstrap/time-series LaTeX column specs were derived from formatted
    LaTeX strings. Both were fixed by validating `units` through the shared
    display-only normalizer and computing column specs from raw payload values.
  - Gemini re-review returned PASS. A reported missing-assertion issue in the
    Desktop time-series test was a truncated-snippet false positive; the full
    test asserts snapshot, text, CSV, LaTeX, and plot-axis units.
  - Validation: focused E6 units selection -> 58 passed; related statistics
    core/advanced/LaTeX/Desktop statistics files -> 253 passed; py_compile,
    Ruff, and scoped diff-check passed.

## 5. Tests

Add focused tests before broad GUI tests:

- `tests/test_units_annotations.py` display-only family helper tests.
- `tests/test_datalab_core_root_solving.py` display-only units payload/snapshot
  tests and active-mode fail-closed tests.
- `tests/test_datalab_core_fitting.py` display-only units payload tests and
  parameter-units-do-not-affect-fit tests.
- `tests/test_datalab_core_statistics.py` or focused advanced statistics tests
  for units payload preservation and unitless CSV/header stability.
- Workspace controller tests for `config.<family>.units` capture/restore.
- Workspace schema tests for accepted display-only family units and rejected
  active/malformed family units.
- LaTeX tests for dcolumn/siunitx-safe label-only units.
- Plot-label tests for axis labels without data changes.

## 6. Non-Goals For This Slice

- No unit conversion.
- No dimensional validation for root equations, fit expressions, or statistics.
- No covariance derived-unit algebra.
- No parameter-unit constraints or optimizer scaling.
- No Web active-unit execution parity.
- No automatic inference from column names.

## 7. Review Gate

Use only:

- Codex main-thread review;
- Antigravity Gemini Pro review.

Claude review is disabled by current user instruction.

P4.7-E may start implementation only after both reviews have no actionable
findings. Any valid finding must be folded back into this plan and the parent
P4.7 plan before code changes.
