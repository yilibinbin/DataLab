# DataLab P4.7 Unit-Aware Calculations Spec

Status: finalized after Codex, Antigravity/Gemini, and Antigravity/Claude review
Date: 2026-06-26

## 1. Goal

Add optional unit metadata and dimensional checks to DataLab calculations without
changing the meaning of existing unitless workspaces. Users can annotate input
columns, constants, selected outputs, and report tables with units. DataLab can
validate dimensional compatibility, convert compatible units when explicitly
requested, and render unit-aware results in text, CSV, LaTeX, plots, workspaces,
history, and report bundles.

P4.7 must reuse the existing optional `shared.units` / pint integration where
possible, but it must harden that boundary for DataLab's high-precision numeric
policy before unit-aware results become visible.

## 2. Non-Goals

- No implicit reinterpretation of existing numeric input as unit-bearing.
- No automatic unit inference from column names such as `V` or `length_mm`.
- No arbitrary unit definitions or user-executed Python code in the first
  release.
- No symbolic dimensional proof for every possible user expression in the first
  release. Unsupported formulas produce diagnostics rather than unsafe claims.
- No mandatory pint dependency for the base app. Unit-aware calculations are
  optional and must fail closed or degrade clearly when pint is unavailable.

## 3. Existing Boundary To Reuse And Harden

The repository already contains `shared.units` with:

- `HAS_PINT`
- `get_registry()`
- `parse_quantity(text)`
- `convert_to_si(text)`
- `to_siunitx(magnitude, unit)`

P4.7 must not create a competing unit system. However, before exposing units in
core calculations, the implementation must fix or wrap current precision risks:

- `to_siunitx()` currently converts magnitude through `float(magnitude)`. That
  is acceptable only for legacy fallback display tests, not for high-precision
  DataLab result formatting.
- Add a high-precision-safe unit formatting helper that preserves decimal
  strings/mpmath values and escapes units consistently.
- Unit conversion that changes numeric magnitudes must not use Python `float`.
  The implementation must either configure pint with a high-precision numeric
  type suitable for DataLab, or extract an exact/decimal conversion factor from
  pint and apply it through DataLab's existing high-precision numeric engine.
  If neither path is available for a multiplicative unit pair,
  `convert_outputs` must fail closed with a diagnostic. Affine or offset
  conversions, such as Celsius/Fahrenheit, are explicitly unsupported in the
  first release.

## 4. Workflow Semantics

Units are metadata on existing calculation workflows, not a new top-level
calculation mode.

First visible release surface:

- error propagation inputs/constants and final output unit;

Later reviewed surfaces after the shared contract is stable:

- root solving unknowns/constants and root units;
- custom/self-consistent fitting input/output labels and parameter units;
- statistics value/sigma columns as display/report units only unless a later
  feature adds unit algebra for statistics workflows.

Every unit-aware job has:

- `units_enabled`, default `false`;
- unit annotations for selected inputs/constants/outputs;
- dimensional-check mode:
  - `display_only`
  - `validate_expression`
  - `convert_outputs` (later reviewed slice only; hidden/unavailable in the
    first visible error-propagation release)

`display_only` attaches units to labels/exports but does not validate formulas.
`validate_expression` checks dimensional compatibility where supported and
requires expression result units to match explicit output units exactly, not
merely by compatible dimension. `convert_outputs` is explicitly deferred from
the first visible P4.7 release because converting only the displayed final value
would leave uncertainty, variance, sensitivity, Monte Carlo, comparison, plot,
history, and budget/report diagnostics in mixed source/target units. A later
reviewed slice must define a full payload conversion contract before exposing
conversion controls.

The later `convert_outputs` slice supports multiplicative conversions only.
Affine conversions with offsets, such as Celsius/Fahrenheit temperature scales
or any future offset/gauge-style unit transform, must fail closed with
`unit_affine_conversion_unsupported`. Logarithmic units such as decibel-style
scales are also rejected in active validation/conversion modes unless a later
reviewed slice defines their numeric semantics.

Affine/offset or otherwise non-multiplicative units are rejected entirely in all
first-release active validation and conversion modes, including when such a unit
appears only as an exact source/output annotation. `display_only` may preserve
these strings as escaped labels because no numeric claim is made. The validator
must catch pint offset-unit exceptions, such as `OffsetUnitCalculusError`, and
convert them into a clean `unit_affine_calculus_unsupported` diagnostic rather
than allowing crashes or server errors.

Compatible-but-different operands such as `1 m + 2 cm` are rejected in every
first-release active mode. Supporting them requires a later reviewed
expression-rewrite/input-normalization slice that injects high-precision
conversion factors before numeric evaluation.

## 5. Unit Annotation Model

Add a UI-neutral unit annotation object:

```json
{
  "schema": "datalab.units.annotations.v1",
  "enabled": true,
  "mode": "validate_expression",
  "annotations": {
    "inputs": {"x": "m", "t": "s"},
    "constants": {"g": "m/s^2"},
    "parameters": {"a": "m/s^2"},
    "outputs": {"y": "m"}
  },
  "compatibility": {
    "outputs": {
      "y": {
        "quantity_space": "length",
        "denominator_semantics": "absolute",
        "aggregation_model": "none"
      }
    }
  }
}
```

Rules:

- Unit strings are user data and must be escaped in LaTeX/HTML.
- Persisted numeric magnitudes remain numeric strings from the existing
  calculation payloads; unit annotations do not wrap numbers in JSON objects
  unless a later schema version has a reviewed need.
- `conversions` is omitted and rejected in the first visible release. It may be
  added to this schema only by the later `convert_outputs` slice after full
  payload conversion semantics are implemented.
- Unit annotations must be stored in workspaces and semantic snapshots alongside
  the existing result family, not in rendered text caches.
- The authoritative editable workspace location is the host family config, not
  the rendered result snapshot. First visible release stores error propagation
  unit settings at `workspace["config"]["error"]["units"]`. Later reviewed
  slices use `workspace["config"]["root_solving"]["units"]`,
  `workspace["config"]["fitting"]["units"]`, and
  `workspace["config"]["statistics"]["units"]` for their own family settings.
  Because `shared.workspace_schema.workspace_hash_payload()` already includes
  `config`, active unit modes and annotation/conversion changes must affect
  workspace staleness hashes and history input signatures. The `units` object in
  semantic result snapshots is a copy of the executed configuration plus
  diagnostics/provenance for regeneration; it is not the authoritative editable
  source.
- Editable unit annotations are keyed by the same canonical symbols that the
  calculation engine evaluates after input-header normalization and formula
  rewriting, not by raw UI labels. For error propagation this means validation
  uses the disambiguated symbols produced by
  `shared.error_propagation_engine._normalize_header_to_symbol(header, index)`.
  Legacy `x1`, `x2`, ... aliases may be accepted only in formula text and must
  be rewritten before unit validation; they are not persisted as annotation
  keys. Raw headers, source column indexes, and localized labels are stored
  separately as display metadata. Validators must reject ambiguous mappings
  caused by duplicate normalized headers, punctuation/space normalization
  collisions, or annotations for identifiers that are not present in the
  rewritten formula.
- Editable config stores only deterministic user-authored fields: `enabled`,
  `mode`, `annotations`, `compatibility`, and, in the later conversion slice,
  `conversions`. Execution metadata such as `backend_available`, backend
  version, conversion provenance, and diagnostics is computed at run time and
  stored only in semantic result snapshots/history/report artifacts. Backend
  availability must not be persisted in `workspace.config` or affect workspace
  input hashes.
- Unit strings alone do not authorize P3.1 budget aggregation. Optional
  compatibility metadata (`quantity_space`, `denominator_semantics`, and
  `aggregation_model`) is recorded as provenance for future budget compatibility,
  but P4.7 explicitly defers changing P3.1 aggregation semantics. Existing
  budget extractors must ignore unit metadata or emit a clear
  `unit_budget_compatibility_deferred` diagnostic until a later plan extends the
  budget row schema and aggregation rules.

## 6. Expression Validation Policy

DataLab expressions are entered in the existing Mathematica-like safe expression
syntax and translated through DataLab's expression engines. P4.7 must validate
dimensions by reusing the safe expression AST/identifier detection where
available:

- Variables/constants with unit annotations become symbolic quantity placeholders
  for dimensional evaluation.
- Supported operators/functions are limited to a reviewed allowlist.
- Addition/subtraction require identical units in all first-release active
  modes. Compatible-but-different units, such as `m` and `cm`, require a future
  reviewed expression-rewrite slice that injects high-precision conversion
  factors before numeric evaluation.
- Multiplication/division follow dimensional algebra and preserve exact unit
  provenance. Every power exponent in first-release active modes must be a
  literal numeric AST constant with exactly no unit, regardless of whether the
  base currently carries units. Named constants, variables, or
  dimensionless-by-cancellation expressions such as `cm/m` are rejected as power
  exponents until a later validator can inject the exponent's actual numeric
  value into dimensional evaluation without dummy placeholders.
- `abs` preserves the input unit exactly.
- `sqrt` follows the same dimensional rule as raising the input to a
  dimensionless constant power of `0.5`.
- Transcendental functions must not accept units that require scaling before
  numeric evaluation. `exp` and `log` require exactly no unit.
- Direct trigonometric functions (`sin`, `cos`, `tan`) may accept exactly no
  unit or exactly radians (`rad`) because the numeric engine evaluates raw
  magnitudes as radians. Degrees and other angle units are rejected until a
  future expression-rewrite slice injects high-precision conversion factors
  before numeric evaluation.
- Inverse trigonometric functions (`asin`, `acos`, `atan`) require arguments with
  exactly no unit, not merely dimensionless-by-cancellation units such as
  `cm/m`, and return radians. Two-argument inverse tangent (`atan2`) remains
  fail-closed in the first implementation slice because the shared expression
  registry, numeric expression engines, and symbolic export maps do not yet
  support it consistently. A later expression-engine slice may add `atan2`
  across all of those surfaces with identical-unit or exactly unitless
  argument-pair rules.
- The final expression unit must exactly match the declared output unit before
  the numeric engine result is accepted. Dimensionally compatible but
  non-identical final output units are rejected in the first visible release.
  They are accepted only by the later `convert_outputs` slice after that slice
  defines full result-payload conversion and records high-precision conversion
  factors/provenance.
- Unsupported functions or data-dependent branches emit
  `unit_validation_unavailable`, not a false success.

Formula evaluation must remain owned by the existing numeric engines. Unit
validation is a pre-flight or post-flight semantic check, not a replacement
calculation engine.

## 7. Routing Table

P4.7 implementation must use the same family-owned boundaries as the rest of
P3/P4:

| Family | Core producer | Snapshot/schema | Desktop surface | Web surface | CSV/LaTeX/plot | Workspace/history/report | Docs/tests |
|---|---|---|---|---|---|---|---|
| Error propagation | `datalab_core.uncertainty` and `shared.error_propagation_engine` | host uncertainty snapshot plus `units` object | `app_desktop/views/error.py`, `workspace_controller` | Web parity deferred in first release; Web remains unitless/display-only until a separate route plan | existing error-propagation CSV/LaTeX/plot helpers with unit labels | workspace unit metadata, history context rows, report provenance | uncertainty docs, unit annotation tests, desktop UI tests, LaTeX compile tests |
| Root solving | `datalab_core.root_solving` | root snapshot plus `units` object | root-solving view after error-propagation release | deferred | root text/LaTeX/plot labels only until validation semantics are reviewed | workspace/history/report provenance | root unit display tests in later slice |
| Fitting | `datalab_core.fitting` and fitting shared engine | fitting snapshot plus `units` object | fitting view after error-propagation release | deferred | fitting text/LaTeX/plot labels and parameter-unit metadata | workspace/history/report provenance | fitting unit label tests in later slice |
| Statistics | `datalab_core.statistics` | statistics snapshot plus `units` object | statistics view display/report labels only | deferred | statistics table/plot axis labels only | workspace/history/report provenance | statistics unit label tests in later slice |

Any Web-visible unit feature requires a separate parity plan naming the exact
`app_web` routes/templates/tests. Until then, `/error`, `/fit`, `/stats`, and
the corresponding `app_web/logic/*` adapters/templates may ignore or display
unit metadata only when `mode="display_only"`. If a loaded workspace or request
has `units_enabled=true` with `mode="validate_expression"` or
`mode="convert_outputs"`, Web must fail closed before evaluation or save with a
diagnostic such as `unit_evaluation_unsupported_on_web`. Silently ignoring
active unit metadata would produce divergent numeric results for conversions and
would allow dimensionally invalid formulas to execute. For `display_only`,
Web save/update routes must preserve the existing `config.<family>.units` block
when the frontend omits unit fields; if that merge-preservation cannot be proven,
Web save must fail closed rather than deleting user-authored annotations. Web
routes must not accept active unit mode controls and must not claim unit-aware
results until a Web parity slice exists.

## 8. Payload And Snapshot Integration

Each result family may include a `units` object in its semantic snapshot:

```json
{
  "family": "uncertainty",
  "units": {
    "schema": "datalab.units.annotations.v1",
    "enabled": true,
    "mode": "validate_expression",
    "backend": "pint",
    "backend_available": true,
    "annotations": {
      "inputs": {"x": "m"},
      "outputs": {"f": "N"}
    },
    "compatibility": {
      "outputs": {
        "f": {
          "quantity_space": "force",
          "denominator_semantics": "absolute",
          "aggregation_model": "none"
        }
      }
    },
    "diagnostics": []
  }
}
```

Requirements:

- Numeric values remain JSON-safe strings/integers/nulls as in the host result
  family.
- Unit annotations are optional; absence means legacy unitless behavior.
- Closed validators must reject unsupported modes, unsafe unit strings,
  malformed annotation maps, malformed compatibility metadata, and any
  conversion map before the later conversion slice is enabled.
- Snapshots must store enough metadata to regenerate text/CSV/LaTeX labels and
  report bundles without reading GUI state.

## 9. Output Formatting

### 9.1 Text And CSV

- Text displays units beside labels, not inside numeric strings.
- CSV adds unit columns where useful, such as `value_unit`,
  `uncertainty_unit`, or `output_unit`.
- Existing unitless CSV shapes stay stable unless unit mode is active.

### 9.2 LaTeX

LaTeX unit rendering must be compile-safe:

- table numeric cells continue to use existing dcolumn/siunitx number-formatting
  helpers;
- unit labels live in separate escaped text/siunitx unit cells or captions;
- high-precision numeric strings must not be converted through Python `float`;
- `shared.units.to_siunitx()` may remain as a legacy wrapper, but P4.7 needs a
  high-precision-safe helper before writing unit-bearing DataLab result tables.

### 9.3 Plots

Plot labels may include units. Plot numeric data remains the host family numeric
series. First visible P4.7 does not convert plotted magnitudes. A later
conversion slice must convert or explicitly source-unit-label every affected
series, including uncertainty bands, Monte Carlo summaries, comparison
diagnostics, and contribution plots.

## 10. Workspace, History, Report, Budget

Unit annotations must:

- save/restore in `.datalab` workspaces;
- survive example-template behavior without local paths;
- appear in history comparison as context/configuration changes;
- appear in report bundles from semantic snapshots;
- affect workspace hash and history input signatures when active unit config
  changes, because the authoritative settings live in `workspace.config`;
- remain labels/provenance for P3.1 budget in this slice. Even with
  compatibility metadata present, total aggregation decisions do not change
  until a separate budget-schema plan is implemented.

## 11. Validation

Required tests:

- `shared.units` remains import-safe without pint.
- High-precision-safe unit formatting preserves long decimal strings and
  mpmath values without Python `float` truncation.
- Conversion helper tests may exist below the UI, but visible
  `convert_outputs` controls stay hidden/unavailable until a later slice defines
  full payload conversion. Conversion paths that would require binary-float
  scaling fail closed.
- Affine conversions, including Celsius/Fahrenheit, fail closed in the first
  release. Future affine support must separately test nominal-value offsets and
  uncertainty scale-only conversion.
- Pint-present and pint-absent behavior for display-only, validation, and
  conversion modes.
- Unit annotation validators reject malformed maps, unsafe unit strings,
  conversion targets before the conversion slice is enabled, and conversions
  without source annotations in the later conversion slice.
- Annotation namespace tests prove validators use canonical rewritten symbols,
  not raw headers, and reject duplicate/ambiguous normalized headers,
  punctuation/space collisions, and stale annotations for missing identifiers.
- Compatibility metadata validators reject missing/unknown quantity-space,
  denominator, or aggregation values when a budget integration path requests
  them.
- Expression dimensional checks for add/subtract, multiply/divide, powers,
  exactly-unitless power exponents, exact transcendental argument units, and
  unsupported functions.
- Power tests reject named constants, variables, and
  dimensionless-by-cancellation expressions as exponents for all bases; literal
  numeric exponents remain allowed.
- Trigonometric tests allow raw unitless/radian magnitudes but reject degrees or
  other angle units that would require pre-evaluation scaling. `exp`/`log`
  require exactly no unit.
- Inverse trigonometric tests cover `asin`/`acos`/`atan` exactly-unitless inputs,
  rejection of dimensionless composite inputs such as `cm/m`, and fail-closed
  behavior for registry-unsupported `atan2`.
- `sqrt` and `abs` tests prove dimensional behavior matches power/identity
  rules.
- Offset/affine unit tests prove active validation modes emit
  `unit_affine_calculus_unsupported` or `unit_affine_conversion_unsupported`
  diagnostics rather than unhandled pint exceptions.
- Offset/affine/logarithmic unit tests prove active modes reject these units even
  when they are declared as exact input/output units with no conversion request;
  display-only may preserve them as labels.
- Exact-unit validation tests prove `validate_expression` rejects compatible but
  differently scaled add/subtract operands and compatible-but-non-identical final
  output units where the numeric engine would otherwise compute raw magnitudes
  incorrectly.
- Visible-release tests prove `convert_outputs` controls are hidden/unavailable.
  Later conversion-slice tests must prove values and uncertainties scale by
  factor, variances by factor squared, and Monte Carlo/comparison/plot/report
  diagnostics are either converted or explicitly source-unit-labeled.
- Workspace save/restore for unit annotations in error propagation first-release
  config at `config.error.units`.
- Workspace hash/history signature tests prove changing `units_enabled`, unit
  annotations, dimensional-check mode, or compatibility metadata changes the
  computation input signature, while changing only rendered caches does not.
  Conversion-target hash tests belong to the later conversion slice.
- Backend availability/version/diagnostic metadata tests prove those execution
  fields are not persisted in workspace config and do not mutate input hashes.
- Root/fitting/statistics workspace tests are later-slice gates and must not be
  required for the first visible error-propagation release.
- Web route/template tests prove display-only unit metadata is inert, while
  active `validate_expression`/`convert_outputs` unit metadata fails closed with
  `unit_evaluation_unsupported_on_web` before evaluation or save.
- Web save tests prove display-only unit config is preserved when frontend
  payloads omit unit fields, or that save fails closed rather than deleting
  `config.<family>.units`.
- Text/CSV/LaTeX output uses units without breaking existing dcolumn/siunitx
  number formatting.
- History/report metadata uses units as context and provenance. Budget
  aggregation remains unchanged and either ignores unit metadata or reports
  `unit_budget_compatibility_deferred`.

## 12. Delivery Slices

1. Harden `shared.units` with high-precision-safe formatting and validators.
2. Add unit annotation DTO/schema/validators and workspace persistence.
3. Add expression dimensional validation for a conservative allowlist.
4. Wire display-only and validation modes into error propagation first.
5. Extend to root solving/fitting/statistics display labels in later visible
   slices.
6. Add LaTeX/CSV/plot/report/history/docs/examples integration. Budget
   aggregation integration is deferred to a later reviewed P3.1 schema slice.
