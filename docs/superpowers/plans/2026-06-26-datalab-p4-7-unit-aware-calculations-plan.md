# DataLab P4.7 Unit-Aware Calculations Implementation Plan

Status: finalized after Codex, Antigravity/Gemini, and Antigravity/Claude review
Date: 2026-06-26

Spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-7-unit-aware-calculations-spec.md`

## 1. Preconditions

- Claude CLI / claude-for-codex review is disabled. If a Claude-family review is
  needed, use an Antigravity/agy Claude model only.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse `shared.units` and the existing optional `pint` extra; do not create a
  second unit system.
- Do not change existing unitless workspace semantics.
- Do not expose unit-aware calculations until high-precision formatting,
  validator, workspace, and output gates pass.

## 2. Key Design Decisions

1. Units are optional metadata on existing workflows, not a new top-level mode.
2. First visible release is opt-in with `display_only` and
   `validate_expression`. `convert_outputs` remains hidden/unavailable until a
   later reviewed slice defines full result-payload conversion.
3. Pint is the preferred dimensional backend when available; no-pint
   validation/conversion fails closed.
4. `shared.units.to_siunitx()` currently uses `float(magnitude)` and must not be
   used for high-precision DataLab result formatting until wrapped or replaced.
5. Addition/subtraction require exact units in every first-release active mode.
   Compatible but non-identical final output units reject until the later
   conversion slice.
6. Unit annotations live in semantic snapshots and workspaces, not rendered
   caches.
7. The authoritative editable workspace path is `config.<family>.units`.
   Result snapshots copy executed unit metadata for regeneration only.
8. P4.7 does not change P3.1 uncertainty-budget aggregation. Compatibility
   metadata is provenance for a later budget-schema plan.

## 3. Slice P4.7-A: Harden Shared Unit Utilities

Goal: make existing unit helpers safe enough for DataLab result surfaces.

Likely files:

- `shared/units.py`
- `tests/test_units_integration.py`
- new `tests/test_units_precision_formatting.py`

Implementation:

- Add a high-precision-safe LaTeX unit formatting helper, for example
  `format_quantity_latex(magnitude_text, unit, *, use_siunitx=True)`, that
  accepts strings/mpmath values without converting through Python `float`.
- Keep `to_siunitx()` backward-compatible if existing tests need it, but route
  new DataLab result tables through the high-precision helper.
- Add unit-string escaping/validation helper(s) for LaTeX/HTML contexts.
- Add a backend metadata helper that reports pint availability/version when
  available.
- Add a high-precision conversion helper that either:
  - configures pint to use a high-precision numeric type accepted by DataLab; or
  - extracts a conversion factor and applies it through mpmath/Decimal without
    Python `float`.
  Conversion paths that cannot avoid binary-float scaling must fail closed for
  `convert_outputs`.
- Reject affine/offset conversions in the first release. If future support is
  added, the transform must separate nominal-value offset handling from
  uncertainty scale-only conversion.
- Reject affine/offset units entirely in all first-release active validation and
  conversion modes. Catch pint offset-unit exceptions such as
  `OffsetUnitCalculusError` and return clean diagnostics instead of crashes.
- Reject logarithmic or otherwise non-multiplicative units in all active
  validation/conversion modes. `display_only` may keep them as escaped labels.

Verification:

- Long decimal strings and mpmath values are preserved.
- Compatible-unit conversions preserve high-precision magnitudes or emit
  explicit diagnostics instead of truncating through `float`.
- Affine conversions such as Celsius/Fahrenheit emit
  `unit_affine_conversion_unsupported`.
- Exact annotations using affine/offset/logarithmic units also fail active
  validation/conversion with clean diagnostics, even when no conversion target
  is requested.
- Pint absent path imports cleanly and display-only formatting still works.
- Malformed unit strings produce diagnostics, not crashes.
- Existing unit tests continue to pass.

## 4. Slice P4.7-B: Annotation DTOs, Validators, Workspace Schema

Goal: define the portable unit metadata contract.

Likely files:

- new `datalab_core/units.py` or `shared/unit_annotations.py`
- `shared/workspace_schema.py`
- `datalab_core/workspace_v2.py`
- `tests/test_units_annotations.py`
- `tests/test_workspace_io.py`

Implementation:

- Add `UnitAnnotations` DTO or mapping normalizer for:
  - enabled flag;
  - mode;
  - backend metadata;
  - inputs/constants/parameters/outputs maps;
  - conversion targets only after the later conversion slice is enabled;
  - optional compatibility metadata: `quantity_space`,
    `denominator_semantics`, and `aggregation_model`;
  - diagnostics in semantic result snapshots only, not editable workspace config.
- Add closed validator for `datalab.units.annotations.v1`.
- Reject unsafe unit strings, unsupported modes, malformed annotation maps,
  malformed compatibility metadata, conversion targets without source
  annotations, and validation/conversion when pint is unavailable.
- Split editable config from execution metadata. `config.error.units` stores only
  deterministic user-authored fields; `backend_available`, backend version,
  diagnostics, and conversion provenance are computed at execution time and
  stored only in semantic snapshots/history/report artifacts.
- Add workspace save/restore storage without changing unitless workspaces.
- Store first-release error-propagation unit configuration at
  `config.error.units`; later slices use `config.root_solving.units`,
  `config.fitting.units`, and `config.statistics.units`.
- Ensure `workspace_hash_payload()` and history input signatures include active
  unit configuration through the existing `config` path. Do not treat
  `result_snapshot.units` or rendered caches as the editable/hash-authoritative
  source.
- Normalize annotation keys to the same canonical symbols used by the error
  propagation evaluator after header normalization and formula rewriting. Store
  raw headers/UI labels separately as display metadata.

Verification:

- JSON no-float/unit metadata validation.
- Legacy workspaces without units restore unchanged.
- Unit-enabled workspaces round-trip annotations and diagnostics.
- Changing unit mode, annotations, or compatibility metadata changes workspace
  hash/history input signatures; changing only rendered caches does not.
  Conversion-target hash tests belong to the later conversion slice.
- Backend availability/version/diagnostics never persist in `config` and never
  change workspace input hashes.
- Headers with spaces/punctuation/duplicates validate against
  `_normalize_header_to_symbol(header, index)` identifiers, and formulas using
  legacy `x1` aliases are rewritten before validation rather than persisted as
  annotation keys.
- Compatibility metadata round-trips as provenance only. Existing P3.1 budget
  extraction ignores it or emits `unit_budget_compatibility_deferred` until a
  separate row-schema plan is implemented.
- Malformed annotations fail closed.

## 5. Slice P4.7-C: Expression Dimensional Validation

Goal: validate units conservatively through existing expression infrastructure.

Likely files:

- `shared/expression_names.py`
- `shared/expression_registry.py`
- new unit validation module
- `tests/test_units_expression_validation.py`

Implementation:

- Reuse existing safe expression parsing/identifier detection.
- Map annotated identifiers to unit placeholders.
- Implement an allowlist for dimensional operations:
  - add/subtract identical units in all active modes;
  - multiply/divide;
  - all powers use literal numeric exactly-unitless AST constants only,
    rejecting named constants, variables, and exponents that are only
    dimensionless by unit cancellation such as `cm/m`, regardless of the base;
  - `abs` preserving units and `sqrt` matching power `0.5`;
  - exact no-unit requirements for `exp`/`log`;
  - exact no-unit or `rad` requirements for direct trigonometric functions;
  - inverse trigonometric rules: `asin`/`acos`/`atan` exactly-unitless inputs
    returning radians. `atan2` remains fail-closed in the first implementation
    slice because the shared expression registry, numeric expression engines,
    and symbolic export maps do not yet support it consistently; a later
    expression-engine slice may add `atan2` with identical-unit or exactly
    unitless argument-pair rules.
- Require the final expression unit to exactly match the declared output unit in
  `validate_expression`. Compatible but non-identical final output units reject
  in the visible release.
- Keep `convert_outputs` unavailable until a later slice defines full payload
  conversion for value, uncertainty, variances, sensitivities, Monte Carlo,
  comparison diagnostics, plots, history, reports, and budget provenance.
- Emit `unit_validation_unavailable` for unsupported functions or expression
  forms.
- Keep numeric formula evaluation unchanged.

Verification:

- Compatible and incompatible add/subtract cases.
- Compatible-but-different add/subtract units are rejected in all active modes
  unless a later expression-rewrite slice exists.
- Multiplication/division/power cases, including rejection of named constants,
  variables, and dimensionless-by-cancellation expressions as exponents for all
  bases.
- Final output exact-unit matching in `validate_expression`; compatible
  non-identical final output units reject until the conversion slice.
- Exactly-unitless `sin`, `exp`, `log` checks.
- Degree-valued trigonometric arguments are rejected until an expression-rewrite
  slice can scale them to radians before numeric evaluation.
- `asin`/`acos`/`atan` reject dimensionless composite inputs such as `cm/m`.
- `atan2` fails closed as an unsupported function until a later
  expression-engine slice adds it across the registry, evaluators, exporters,
  and dimensional validator together.
- `sqrt` and `abs` dimensional behavior.
- Affine/offset unit use emits clean diagnostics without unhandled pint
  exceptions.
- Unsupported expression forms produce diagnostics without running unsafe code.

## 6. Slice P4.7-D: Error Propagation First Integration

Goal: integrate units into one high-value workflow before broad rollout.

Likely files:

- `datalab_core/uncertainty.py`
- `shared/error_propagation_engine.py`
- `app_desktop/views/error.py`
- `app_desktop/workspace_controller.py`
- `tests/test_datalab_core_uncertainty.py`
- `tests/test_desktop_error_propagation_ui.py`

Implementation:

- Add optional unit annotations to error-propagation request/payload/snapshot.
- Thread unit config through `CalcJob` and the core request builder before
  execution. Disable the legacy unitless fallback path whenever
  `units.enabled=true`; request-construction, validation, or backend failures
  must produce failed unit diagnostics, not legacy unitless evaluation.
- Add Desktop controls for unit annotations using the existing constants/input
  table patterns.
- Support `display_only` and `validate_expression` first; `convert_outputs`
  remains hidden until the later full-payload conversion slice.
- Store units in snapshots and workspaces.
- Render unit labels in text/CSV/LaTeX/plot labels.
- Keep this as the first visible release boundary. Root/fitting/statistics unit
  surfaces remain hidden or unavailable until Slice P4.7-E gates pass.
- Keep Web `/error` unit-aware validation/conversion unavailable. Web may ignore
  or render inert display-only provenance only for `mode="display_only"`. If
  `config.error.units` has `units_enabled=true` with `validate_expression` or
  `convert_outputs`, Web must fail closed before evaluation/save with
  `unit_evaluation_unsupported_on_web` until a separate Web parity plan exists.
- For `display_only`, Web save/update routes must merge-preserve the existing
  `config.<family>.units` block when frontend payloads omit unit fields. If that
  preservation cannot be proven, Web save fails closed rather than deleting unit
  annotations.

Verification:

- Unitless error propagation output is unchanged.
- Unit-enabled display-only output includes labels only.
- Dimensional validation catches incompatible formulas.
- Incompatible units and no-pint active mode fail without falling back to the
  legacy unitless evaluator.
- Workspace/template behavior is preserved.
- Unit config changes affect staleness and history input signatures.
- LaTeX compiles with dcolumn and siunitx options.
- Web route/template tests prove active unit validation/conversion controls are
  not exposed or executed, and active unit workspaces fail closed rather than
  silently calculating unitless values.
- Web save/update tests prove display-only unit config is preserved or saving
  fails closed before data loss.

## 7. Slice P4.7-E: Broader Workflow Integration

Goal: extend unit metadata to root solving, fitting, and statistics labels after
the shared contract is stable. These are later visible slices, not part of the
first release gate.

Likely files:

- `datalab_core/root_solving.py`
- `datalab_core/fitting.py`
- `datalab_core/statistics.py`
- corresponding desktop views and workspace controller paths
- focused tests per family

Implementation:

- Add display-only unit labels first for root, fitting, and statistics.
- Add validation/conversion only where expression dimensional semantics are
  reviewed and covered.
- Ensure fitting parameter units are metadata, not constraints on optimizer
  numeric arrays.
- Ensure statistics units are labels unless a later reviewed feature defines
  unit algebra for statistics transformations.

Verification:

- Unitless behavior unchanged in all families.
- Unit labels survive workspace/history/report.
- Unsupported validation paths emit diagnostics instead of success.
- First-release error-propagation-only behavior remains unchanged until each
  family slice has workspace/output/report/history tests.
- Root/fitting/statistics tests are later-slice gates; they are not required for
  the first visible error-propagation release.

## 8. Slice P4.7-F: Output, History, Budget, Docs, Examples

Goal: make unit-aware outputs consistent across the app.

Likely files:

- `datalab_latex/*`
- `shared/plotting.py`
- `datalab_core/history_compare.py`
- `datalab_core/report_bundle.py`
- docs and example-workspace generator

Implementation:

- Add shared unit-aware label rendering for text/CSV/LaTeX/plots.
- Add history comparison for unit annotation changes.
- Keep P3.1 budget aggregation unchanged. If budget UI/report surfaces encounter
  unit metadata, they treat it as provenance or emit
  `unit_budget_compatibility_deferred`; they do not add unit-based totals until
  a later plan extends `datalab_core/uncertainty_budget.py` and the budget row
  schema.
- Add report-bundle unit metadata from semantic snapshots.
- Add example workspace(s) for unit-validated error propagation.
- Document pint optionality and no-pint behavior.

Verification:

- CSV/LaTeX/plot labels include units safely.
- Report bundle preview regenerates units from snapshots.
- Budget output remains unchanged except optional provenance/diagnostic text.
- Example workspaces open as templates and run.

## 9. Release Gate For P4.7

No user-visible P4.7 release should ship until:

- high-precision unit formatting is safe;
- unit annotation validators are closed;
- at least error propagation supports workspace, text, CSV, LaTeX, plot, and
  report behavior;
- no-pint behavior is explicit and tested;
- legacy unitless workflows remain unchanged.
- root/fitting/statistics surfaces remain hidden or explicitly deferred unless
  their later-slice tests and routing table entries are complete.
- active Web validation/conversion remains unavailable unless a separate Web
  parity slice lands.
- budget aggregation remains unchanged unless a separate P3.1 budget-schema
  slice lands.
