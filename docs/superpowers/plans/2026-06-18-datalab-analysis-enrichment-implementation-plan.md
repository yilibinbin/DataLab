# DataLab Analysis Enrichment Implementation Plan

Date: 2026-06-18

Status: Approved after Codex/Gemini/Claude convergence review

Spec: `docs/superpowers/specs/2026-06-18-datalab-analysis-enrichment-spec.md`

## 1. Goal

Implement the approved all-priority analysis-enrichment spec in staged, independently shippable slices. The plan must preserve DataLab's current maintainability direction:

- calculation families route through existing `datalab_core` request/result envelopes when those envelopes exist;
- semantic result rows are produced before desktop, web, CSV, LaTeX, plots, or workspace snapshots render them;
- shared CSV, LaTeX, plot, and workspace snapshot logic replaces duplicated UI-owned serialization;
- P1/P2 scientific features land only after the P0 schema/rendering foundation is covered by tests;
- P3/P4 items remain planned but require separate implementation specs before coding.

## 2. Non-Goals For This Plan

- Do not implement P3 report/history/workflow or P4 advanced analysis directly from this plan.
- Do not add a new standalone statistics subsystem.
- Do not bypass existing fitting, root-solving, or uncertainty `datalab_core` service handlers.
- Do not add opaque automatic model ranking or automatic outlier deletion.
- Do not rewrite the GUI architecture as part of this analysis-enrichment work.

## 3. Global Engineering Rules

1. Start each implementation slice from a cleanly described diff scope. In this repository, unrelated dirty files may exist; only stage files touched for the slice.
2. Add failing or contract tests before changing behavior where practical.
3. Keep semantic data in core/shared layers and keep UI adapters thin.
4. Use stable semantic keys (`label_key`, `message_key`, `render_group`) in core output. Localized strings are adapter output only.
5. Preserve legacy public fields during migration, including statistics `v_min`/`v_max` to payload `min`/`max` mapping.
6. Treat warnings as public semantic output even when they travel through `ResultEnvelope.warnings`.
7. Every slice must update docs/examples only when the feature is user-visible in that slice.
8. Every slice must be revertible without breaking unrelated modules.
9. Before code changes, every implementation slice must add a routing table using the canonical columns from the spec: feature family, core producer, core payload/schema, desktop surface, web surface, LaTeX/report surface, plot surface, workspace/examples, docs, and tests. The routing table is a gate, not optional documentation.

## 4. Initial Coverage Matrix

This matrix is binding for the implementation plan. P0 rows cover current behavior and key mappings. P1/P2 rows become binding in the slice that introduces the corresponding metrics or diagnostics.

| Condition | Core producer | Expected semantic rows | Legacy/key mapping | Required surfaces | Required tests |
|---|---|---|---|---|---|
| Arithmetic mean, sample mode | `compute_statistics()` -> `run_statistics()` -> `statistics_payload_to_compute_result()` | mean, standard error, standard deviation, variance where exposed, min, max, row count, method metadata, sample policy | `v_min` <-> payload `min`; `v_max` <-> payload `max`; warnings through envelope | desktop direct, desktop batch, statistics projection, web, CSV, LaTeX, semantic `result_snapshot` | core round trip, path parity, LaTeX options, workspace restore |
| Arithmetic mean, population mode | same as above | mean, standard error, standard deviation, variance where exposed, min, max, row count, method metadata, population policy | same mapping; `std_mean` remains legacy display field and must not be used as Student-t CI sample SE | same surfaces | population/sample distinction tests, CI sample-SE guard when CI lands |
| Bare `mean` mode string | same as above | same as arithmetic mean, with sample/population policy resolved by the existing toggle | backward compatibility for legacy `mean`; must reduce to covered sample/population behavior | same surfaces | regression test covering both toggle outcomes for bare `mean` |
| Weighted normal case | same as above | weighted mean, analytical known-sigma SE, effective sample size, weighted chi-square, dof, reduced chi-square, Birge ratio, weighted known-sigma CI when P1.3 lands | condition-specific `effective_n`; warnings through envelope | same surfaces | weighted reference fixture, known-sigma CI including `n = 1`, chi-square/Birge fixtures |
| Weighted zero-sigma anchor | same as above | anchor diagnostic, anchor value, explicit absence of weighted chi-square and CI | condition-specific `zero_sigma_anchor`; no hidden CI row | same surfaces | zero-sigma-anchor fixture, absence-of-CI test |
| Weighted dropped-row case | same as above | dropped-row diagnostic, dropped count, row count consistency | warnings through envelope and diagnostic rows | same surfaces | invalid/blank sigma row fixture, warning parity |
| Descriptive `n >= 4` | same as above, after P1.1 | count, mean, std, variance, SE, min, max, median, Q1, Q3, IQR, MAD, skewness, excess kurtosis, robust diagnostics | same min/max mapping | same surfaces plus docs/examples | reference values, desktop/web/CSV/LaTeX/workspace parity |
| Descriptive small-`n` | same as above, after P1.1 | available metrics plus semantic diagnostics for unavailable variance/skewness/kurtosis | unavailable values blank/non-finite with diagnostic keys | same surfaces | `n < 2`, `n < 3`, `n < 4` fixtures |
| Zero variance descriptive | same as above, after P1.1 | finite location/dispersion rows where valid; blank/non-finite skewness/kurtosis plus zero-variance diagnostic | no divide-by-zero fallback | same surfaces | zero-variance fixture |
| Outlier flag contexts | same as above, after P1.4 | sigma-based flags, robust modified-z flags, MAD-zero fallback flags, source row ids | source provenance from parser; no automatic exclusion | same surfaces | two-tailed robust outlier, MAD-zero, source-row parity |
| Fitting diagnostics | `datalab_core.fitting.run_fitting()` plus existing fit-statistics domain helpers | fit metric rows, residual diagnostics, parameter correlation rows, plot specs | existing `FitResult` compatibility retained | desktop, web where fitting exists, CSV, LaTeX, semantic `result_snapshot`, plots | fit statistics no-dup tests, web parity or explicit deferral |
| Root diagnostics | `datalab_core.root_solving.run_root_solving()` | root quality rows, classification tags, plot specs | existing `RootBatchResult` compatibility retained | desktop, CSV/LaTeX if enabled, semantic `result_snapshot`, plots | sign-change/double/boundary/unclassified fixtures |
| Error diagnostics | `datalab_core.uncertainty.run_uncertainty()` | contribution rows, Taylor/MC diagnostics, plot specs | existing uncertainty result compatibility retained | desktop, web where error propagation exists, CSV, LaTeX, semantic `result_snapshot`, plots | contribution and Taylor/MC fixtures, worker parity |

## 5. P0 Foundation Slices

### P0.1 Baseline Audit And Test Harness

Purpose: lock current behavior before changing result schemas.

Tasks:

- Add or refresh a coverage matrix document/test fixture for current statistics modes and current fitting/root/error output surfaces.
- Add regression tests for:
  - `compute_statistics()` to `run_statistics()` to `statistics_payload_to_compute_result()` round trip;
  - desktop interactive statistics path;
  - desktop batch/core-envelope statistics path;
  - `app_desktop.window_extrapolation_mixin` statistics projection path;
  - web statistics path where available;
  - current statistics LaTeX output with existing options;
  - condition-specific `effective_n` and `zero_sigma_anchor`;
  - `ResultEnvelope.warnings` preservation;
  - high-precision preservation under `precision_guard`.
- Record current duplicated output paths that must be migrated:
  - desktop statistics CSV/plot helpers;
  - fitting CSV and LaTeX writer wrappers;
  - root LaTeX writer wrapper;
  - error propagation contribution summary/plot helpers in `workers_core` and `workers_qt`;
  - web LaTeX helpers that duplicate desktop behavior.

Verification:

- Focused pytest for existing statistics/fitting/root/error result tests.
- A failing-if-missing coverage invariant test skeleton for the initial matrix in Section 4, including the `v_min`/`v_max` mapping and an internal-only allowlist.
- `git diff --check`.

Stop condition:

- No feature code beyond tests and documentation of the baseline.

### P0.2 Shared Analysis Row Schema

Purpose: define the minimal semantic row boundary used by later slices.

Tasks:

- Add shared row dataclasses or disciplined typed dictionaries in a core/shared module, with fields from the spec:
  - `key`, `label_key`, `value`, `uncertainty`, `source`, `row_index`, `method`, `severity`, `message_key`, `render_group`;
  - field support must allow later provisional fields without forcing P0 output to emit unused values.
- Add JSON serialization/deserialization helpers that reject JSON floats where existing numeric-payload rules require string payloads.
- Add tests for stable keys, optional fields, warnings rows, and localization boundary.
- Add the first implementation of the mode-and-condition coverage invariant test. In P0.2 it covers surfaces that already exist at this point: core output, payload/envelope warnings, desktop direct output, desktop batch output, and web output where available. P0.4 extends the same invariant to semantic `result_snapshot`; P0.5 extends it to shared CSV and shared LaTeX output. The invariant must eventually fail if a public statistics result item exists in core output but is absent from any applicable surface.
- Keep the first implementation narrow: bind only rows produced by the current statistics foundation.

Verification:

- Core unit tests for row serialization.
- Static import hygiene check for avoiding desktop/web dependencies in the shared row module.

Stop condition:

- No UI rendering migration until the row schema tests are green.

### P0.3 Statistics Source Provenance

Purpose: make future row flags stable across desktop, web, file, and batch parsing paths.

Tasks:

- Extend statistics request construction so `StatisticsRequestBatch` / `ComputeJobRequest.inputs` can carry stable source row or source line identifiers.
- Route provenance through:
  - desktop direct statistics;
  - desktop batch/core-envelope statistics;
  - `window_extrapolation_mixin` statistics projection;
  - web statistics parsing.
- Add parity tests proving the same input row produces the same row identifier across supported paths.
- Do not change visible output yet unless the row id already appears in existing warnings.

Verification:

- Desktop/web/core provenance tests.
- Workspace open/run tests for existing statistics examples.

Stop condition:

- P1 outlier flags must not start until this slice is complete.

### P0.4 Semantic Result Snapshot

Purpose: stop future report/history/compare features from parsing rendered strings for any active calculation family.

Tasks:

- Define JSON-safe `result_snapshot` schema with:
  - schema version;
  - calculation family and mode;
  - metric rows;
  - diagnostic rows;
  - row flags;
  - warnings;
  - plot spec keys and plot metadata;
  - source payload metadata;
  - precision and uncertainty display settings;
  - compatibility metadata for result overview restore.
- Store the semantic snapshot through the existing workspace model/controller path.
- Restore the snapshot into result state and regenerate deterministic text/CSV/LaTeX from the semantic snapshot where possible.
- Treat legacy rendered text/CSV/LaTeX/image artifacts as invalidatable compatibility/performance caches, not as authoritative data.
- Add migration behavior for old workspaces that only contain rendered output.
- Apply the baseline schema first to statistics, then require fitting, root-solving, and error propagation slices to map their new diagnostics into the same `result_snapshot` contract before exposing those diagnostics.
- Define family-specific snapshot adapters for:
  - statistics rows and warnings;
  - fitting result/diagnostic rows and plot specs;
  - root batch rows, diagnostic rows, and plot specs;
  - error propagation result rows, contribution rows, Taylor/MC diagnostics, and plot specs.

Verification:

- Workspace round-trip tests for old and new workspaces.
- Result overview restore tests.
- Family-specific snapshot tests before each P2 family exposes new diagnostics.
- No duplicate `.datalab` persistence logic outside existing workspace controller/model boundaries.

Stop condition:

- P3 report/history/compare remains blocked until semantic snapshots exist for all required result families.

### P0.5 Shared CSV And LaTeX Serialization

Purpose: prevent desktop and web from formatting the same semantic rows differently.

Tasks:

- Add shared CSV serializers that consume semantic result rows and are called by desktop and web adapters.
- Add shared non-UI LaTeX builder adapters for statistics first. Existing `statistics_utils` may remain as a wrapper if that minimizes churn; any new or changed LaTeX logic must be in `datalab_latex` or a shared non-UI module.
- Mark legacy UI CSV/LaTeX helpers as wrappers or migrate callers to shared builders.
- Add coverage for:
  - dcolumn on/off;
  - siunitx on/off if supported;
  - grouping size 0 and non-zero;
  - Chinese/English captions;
  - warnings and diagnostic rows.

Verification:

- LaTeX option matrix for affected modules.
- CSV parity tests for desktop and web.
- Compile generated LaTeX with the supported local engine matrix.

Stop condition:

- New statistics/fitting/root/error rows cannot be added to UI-only writers.

### P0.6 Shared Plot Spec And Render Boundary

Purpose: ensure semantic plot specs and rendering rules do not diverge by surface.

Tasks:

- Add `StatisticsPlotSpec`, `FittingPlotSpec`, `RootPlotSpec`, and `ErrorPropagationPlotSpec` skeletons only as needed by each slice.
- For statistics first, define plot specs for histogram, box, QQ, and weighted residual plots.
- Add one shared render-from-spec implementation for each plot family when the plot lands.
- Consolidate existing error-propagation contribution summary/plot logic so `workers_core` and `workers_qt` consume shared contribution rows and shared render-from-spec logic.
- Add `plot_only` annotation semantics so plot-only visual aids do not pollute text/CSV/LaTeX rows.

Verification:

- Deterministic image tests or image-metadata tests.
- Desktop-internal worker parity tests for contribution plots.
- Desktop/web plot parity where a web plot exists.
- CJK font tests for generated plots.

Stop condition:

- P1/P2 plot enhancements must wait for this boundary.

### P0.7 Fit Statistics Consolidation

Purpose: avoid adding a third formula source for fit metrics.

Tasks:

- Audit existing AIC/BIC/RMSE/R2/chi-square/dof calculations.
- Ensure fitting diagnostics and model comparison consume `FitResult` and `fitting.statistics.compute_fit_statistics()`.
- Add tests that fail if desktop/web/LaTeX compute these metrics independently.
- Document the exact multi-fit producer needed before model comparison can be implemented.

Verification:

- Fit-statistics unit tests.
- Display/LaTeX parity tests for existing fit metrics.

Stop condition:

- P2 fitting diagnostics can proceed after single-fit metrics are consolidated.
- Model-comparison table remains blocked until a multi-fit producer or scoped orchestrator is specified. The producer must enumerate comparable model fits, return one `FitResult` per candidate from existing single-fit producers, and consume the stored `FitResult` metrics; it must not introduce another local AIC/BIC/R²/RMSE formula path.

## 6. P1 Statistics Enrichment Slices

### P1.1 Descriptive Statistics Mode

Tasks:

- Add `descriptive` mode through `compute_statistics()` and `run_statistics()`.
- Implement:
  - count, mean, std, variance, standard error, min, max;
  - median, Q1, Q3, IQR;
  - MAD;
  - adjusted Fisher-Pearson skewness in sample mode;
  - population third standardized moment in population mode;
  - bias-corrected Fisher excess kurtosis in sample mode;
  - population fourth standardized central moment minus 3 in population mode.
- Use Hyndman-Fan type 7 quantiles.
- Emit semantic diagnostics for `n < 2`, `n < 3`, `n < 4`, and zero variance.
- Add localized UI mode labels and docs/tooltips.
- Route the mode through `statistics_payload_to_compute_result()`.
- Update `app_desktop.views.statistics` and any web mode metadata needed for localized selection and help text.

Verification:

- Reference tests against known values and Mathematica/NumPy fixtures.
- Small-n and zero-variance tests.
- Desktop/web/CSV/LaTeX/workspace snapshot parity.

### P1.2 Weighted Consistency Diagnostics

Tasks:

- Add weighted chi-square, dof, reduced chi-square, Birge ratio, and Kish effective sample size diagnostics.
- Keep current weighted mean and standard error behavior compatible.
- Emit diagnostics for insufficient dof, zero-sigma anchor, dropped rows, and invalid sigma rows.

Verification:

- Weighted normal, zero-sigma-anchor, dropped-row, and single-row fixtures.
- Warnings-channel tests.
- Documentation of assumptions.

### P1.3 Confidence Intervals

Tasks:

- Add shared distribution-quantile helpers under `precision_guard`:
  - Student-t inverse CDF via regularized incomplete beta relationship;
  - normal inverse CDF;
  - reference fixtures for common levels.
- Add unweighted Student-t CI using dedicated `mean_sample_se_for_ci = sample_std / sqrt(n)` and `dof = n - 1`, independent of displayed sample/population `std_mean`.
- Add weighted known-sigma CI using `weighted_se_known_sigma = sqrt(1 / sum(w_i))` for at least one finite non-zero-sigma weighted point when zero-sigma anchor handling is inactive.
- Label population-mode CI carefully as sample-inference output, or suppress it if the implementation cannot make the assumption clear in UI/docs.
- If CI is enabled by default, update parity snapshots and example workspaces in the same slice.

Verification:

- t and normal quantile reference tests.
- rejection tests for `dof <= 0` and confidence levels outside `(0, 1)`.
- monotonic inversion behavior tests for Student-t inverse CDF.
- `n < 2` unweighted suppression test.
- weighted `n = 1` known-sigma CI test.
- weighted variance/SE disabled branch test: either clearly label the analytical interval as known-sigma weighted CI or suppress it with a diagnostic.
- population-mode label/tooltip/docs test.

### P1.4 Outlier Flags

Tasks:

- Add sigma-based advisory flag for `abs(x_i - mean) > 3 * sigma_i`.
- Add robust advisory flag for `abs(0.6745 * (x_i - median) / MAD) > 3.5`.
- For `MAD == 0`, flag any non-median value and emit zero-MAD fallback diagnostic.
- Use parser-provided row provenance.
- Do not delete or exclude flagged rows automatically.

Verification:

- Two-tailed robust outlier tests.
- MAD-zero tests.
- Row provenance tests.
- Display/CSV/LaTeX/workspace parity tests.

### P1.5 Trimmed Mean

Precondition:

- Base descriptive payload and shared rendering are stable.

Tasks:

- Add optional trimmed mean controlled by a trim fraction.
- Add localized control/help text only if the option is exposed in the same slice.
- Keep the default output unchanged unless the slice explicitly re-cuts parity snapshots and examples.

Verification:

- Trim fraction validation tests.
- Reference fixtures for symmetric and asymmetric data.
- Display/CSV/LaTeX/workspace parity when exposed.

### P1.6 Statistics Plots

Tasks:

- Implement histogram, box, QQ, and weighted residual plot specs.
- Render via shared render-from-spec functions.
- Add optional plot generation controls only if existing plot options cannot cover this.

Verification:

- Deterministic plot tests.
- CJK font rendering tests.
- Desktop/web parity where applicable.

## 7. P2 Diagnostics Slices

### P2.1 Fitting Diagnostics

Preconditions:

- Shared fitting CSV serializer and shared fitting LaTeX builder/wrapper are in place.
- Fitting diagnostics have a family-specific semantic `result_snapshot` adapter.
- Existing web fitting surface either participates in parity or the slice explicitly documents a narrowly scoped deferral before code changes.

Tasks:

- Add parameter correlation matrix from covariance and parameter errors.
- Correlation values must be bounded in `[-1, 1]`; finite diagonal cells must be `1`; non-finite covariance or zero parameter error must produce blank/NaN cells plus semantic warnings.
- Add optional parameter correlation heatmap using the shared fitting plot spec and render-from-spec boundary.
- Add chi-square p-value with upper-tail chi-square survival probability `Q(dof / 2, chi2 / 2)`.
- Compute the chi-square p-value under `precision_guard`, with validity tests for invalid dof, non-finite chi-square, and reference p-values.
- Add standardized residual table and max standardized residual summary.
- Add residual, histogram, QQ, confidence-band, and prediction-band plots where covariance/Jacobian are available. Residual QQ and histogram plots are visual diagnostics only; do not report a formal normality verdict in the first release.
- Use `J_p(x) C J_p(x)^T` for confidence-band uncertainty.
- Prediction bands must add residual variance only when a finite residual variance estimate is available; otherwise suppress the prediction band with a diagnostic and still allow the confidence band when valid.
- Keep diagnostics evidence-only; no automatic winner.

Verification:

- Covariance finite/non-finite tests.
- Correlation bound, finite diagonal, zero-parameter-error, and non-finite warning tests.
- Residual normalization tests for sigma, weights, and unweighted data.
- Band tests with performance guards.
- Shared CSV/LaTeX/plot/workspace parity tests.
- Web fitting diagnostics parity tests or an explicit, reviewed deferral.

### P2.2 Model Comparison Table

Precondition:

- Identify an exact multi-fit producer. If none exists, write a separate scoped workflow plan before implementation.

Tasks:

- Expose model name, free parameter count, chi-square, reduced chi-square, AIC, BIC, RMSE, R2, and warnings.
- Consume existing fit-statistics outputs only.
- Do not select a winner automatically.

Verification:

- Multi-model fixture tests.
- No duplicated metric formula tests.
- Result snapshot and LaTeX/CSV parity.

### P2.3 Root-Solving Diagnostics

Preconditions:

- Shared non-UI root LaTeX builder/wrapper is in place, with `app_desktop.root_latex_writer` reduced to an adapter.
- Shared root CSV serializer is in place if root CSV output is exposed.
- Root diagnostics have a family-specific semantic `result_snapshot` adapter.

Tasks:

- Add solver status, residual norm, per-equation residuals, iteration/function-evaluation count when available, Jacobian condition estimate when available, initial guess/bracket summary, and failure hints.
- Add scan diagnostics:
  - interval where each root was found;
  - sign-change evidence;
  - duplicate-root merge notes;
  - failed interval reasons;
  - classification tag set using the spec's exact criteria: `complex` only in complex-solving modes, `bracketed_sign_change` for opposite-sign endpoints, `boundary` within cluster/merge tolerance of a scan boundary, and `suspected_tangent_or_repeated` only when no sign change is observed, residual is below `residual_tolerance`, a distinct finite-difference pair exists, `delta_x != 0`, `slope = delta_f / delta_x`, `x_scale = max(abs(x_right - x_left), configured_scan_step, cluster_tolerance)`, and `abs(slope) * x_scale <= residual_tolerance`. No new relative tolerance may be added. If no distinct pair exists, `delta_x == 0`, or no tag applies, emit `unclassified` unless another tag applies.
- Add root plot enhancements including visible uncertainty bars and automatic inset/local zoom when uncertainty is too small to see.
- Add residual plot for systems when direct function plots are ambiguous.
- Add uncertainty band following the chosen uncertainty propagation method when the data is available.

Verification:

- Sign-change, double-root, boundary-root, zero-`delta_x`, and unclassified near-miss fixtures.
- Desktop result/LaTeX/workspace parity.
- Plot tests for small uncertainty bars, inset behavior, system residual plots, and uncertainty bands.

### P2.4 Error Propagation Diagnostics

Preconditions:

- Shared error CSV serializer and shared error LaTeX builder/wrapper are in place.
- Error propagation diagnostics have a family-specific semantic `result_snapshot` adapter.
- Duplicated contribution summary/plot logic in desktop worker paths is consolidated or wrapped behind one shared implementation.

Tasks:

- Add contribution rows with variable/constant name, variance contribution, percent contribution, absolute sensitivity, relative sensitivity where meaningful, and cumulative contribution percentage.
- Bind cumulative contribution percentage to the consolidated contribution plot spec, including a deterministic cumulative-percentage overlay/series test.
- Add Monte Carlo vs Taylor comparison rows:
  - define `absolute_result_tolerance = 1e-12` and `relative_result_tolerance = 1e-8` as initial defaults, stored as constants in the shared error diagnostics layer and pinned by tests;
  - `practical_floor = max(absolute_result_tolerance, relative_result_tolerance * max(abs(taylor_mean), abs(monte_carlo_mean)))`;
  - `monte_carlo_standard_error = monte_carlo_sigma / sqrt(sample_count)`;
  - mean disagreement threshold uses `max(3 * monte_carlo_standard_error, practical_floor)`;
  - width disagreement compares Taylor standard uncertainty with Monte Carlo output standard deviation;
  - separately report `relative_std_difference = abs(taylor_std - monte_carlo_std) / max(abs(taylor_std), abs(monte_carlo_std))` when both standard deviations are finite and at least one is non-zero; otherwise emit a diagnostic instead of a finite relative difference.
- Add Taylor order 1 vs order 2 comparison rows when both are requested or available.
- Add Monte Carlo distribution plot with mean, standard deviation, and percentile markers.
- Route any rendered formulas in contribution or Taylor/Monte Carlo diagnostics through the existing shared formula rendering/export path; do not add a new formula formatter.
- Reuse the existing error propagation engine and shared contribution renderer.

Verification:

- Contribution sorting, cumulative percentage, and cumulative plot overlay/series tests.
- Taylor-vs-Monte-Carlo controlled fixtures, including pinned absolute/relative tolerance behavior, near-zero mean absolute-tolerance behavior, order 1 vs order 2 comparison, and relative standard-deviation difference reporting.
- Monte Carlo distribution plot tests.
- Worker parity and web parity where applicable.
- LaTeX option matrix coverage.

## 8. P3 Separate-Spec Gates

These features are valuable but must not be implemented directly from this plan.

### P3.1 Cross-Module Uncertainty Budget

Separate spec must decide:

- how to aggregate contribution rows across modules;
- whether to extend semantic rows or define a mapped uncertainty-budget row type;
- how to handle correlated inputs;
- how reports and plots represent budget rows.

### P3.2 Report Bundle

Separate spec must decide:

- report-bundle file structure;
- snapshot size limits;
- PDF/LaTeX compilation strategy;
- example report workspace;
- restore behavior for generated reports.

### P3.3 Workflow History And Compare

Separate spec must decide:

- bounded result-history storage policy;
- comparison UI;
- cross-module transfer rules;
- rollback and workspace bloat controls.

## 9. P4 Roadmap Gates

P4 items require individual specs after P0-P3 contracts are stable:

- multi-column descriptive statistics;
- covariance/correlation matrix;
- grouped statistics;
- bootstrap confidence intervals;
- hypothesis tests;
- time-series smoothing and rolling statistics;
- unit-aware calculations;
- plugin-like analysis recipes.

Each P4 spec must identify existing shared code to reuse before proposing new module logic.

## 10. Documentation And Examples

For each user-visible slice:

- update Chinese and English docs;
- update tooltips and help text;
- add or update example workspaces through `tools/generate_example_workspaces.py`;
- ensure bundled examples open as templates and do not overwrite user files;
- add example smoke tests.

Documentation must explicitly cover:

- statistical definitions and sample/population behavior;
- confidence interval assumptions, including population-mode CI labeling;
- weighted known-sigma vs scatter-based uncertainty;
- outlier flags as advisory only;
- limitations for non-finite, small-n, zero variance, zero MAD, and zero-sigma anchor cases.

## 11. Release Quality Gates

Before merging a slice:

- focused pytest for changed core modules;
- affected desktop/web adapter tests;
- LaTeX generation and option matrix tests when output rows change;
- GUI schema/bilingual/help-affordance scan when controls change;
- screenshot/layout tests when controls or plots change;
- example workspace open-and-run tests;
- `python -m ruff check` on touched packages;
- `python -m compileall -q` on touched packages;
- `git diff --check`;
- three-model review for high-risk slices or any slice that changes core schemas, LaTeX, workspace persistence, or plots.

## 12. Rollback Strategy

- Each slice must keep legacy fields during migration.
- UI adapters may wrap shared serializers before old helper deletion.
- Workspace snapshot schema must be versioned and old workspaces must remain readable.
- New output rows should be additive unless a release note and migration test explicitly cover the change.
- Plot and LaTeX changes should preserve cached rendered artifacts when semantic snapshots are absent.
- Any slice that changes default rendered output, such as enabling confidence intervals by default, must declare a decision gate before merge:
  - either re-cut parity snapshots, LaTeX expectations, and example workspaces in the same slice; or
  - keep the new rows hidden/disabled until that baseline update is approved.
- Schema-changing slices must include downgrade/old-workspace readability tests and an adapter-wrapper rollback path.
- Shared serializer/renderer migrations must keep legacy adapter wrappers until all affected desktop/web callers have parity tests.

## 13. Initial Slice Routing Tables

These routing tables are the initial canonical routing contract for this plan. A slice may refine its row before coding, but it must not remove a listed surface without an explicit reviewed deferral.

| Slice | Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
|---|---|---|---|---|---|---|---|---|---|---|
| P0.1 | Baseline audit | Existing producers per family | Existing payloads and legacy fields | Existing desktop paths | Existing web paths where present | Existing writers | Existing plot paths | Current examples/workspaces | Baseline notes only | Existing result/LaTeX/workspace/precision tests plus initial coverage invariant skeleton |
| P0.2 | Shared rows | `datalab_core.statistics` first; shared row helpers | Minimal semantic row schema | Adapter consumers only after row tests | Adapter consumers only after row tests | No writer change except tests | No plot change | No workspace change except schema test fixtures | Internal schema docs | Row serialization, localization-boundary, no-desktop-import tests |
| P0.3 | Source provenance | `build_statistics_requests`, `ComputeJobRequest.inputs` | Statistics request provenance fields | `window_statistics_mixin`, `workers_core`, `window_extrapolation_mixin` | `app_web.logic.statistics` | No LaTeX change unless row ids surface | No plot change | Existing examples unchanged | Help only if visible | Desktop direct/batch/projection/web provenance parity |
| P0.4 | Semantic snapshots | Family adapters for statistics, fitting, root, uncertainty | Versioned `result_snapshot` | `workspace_controller`, result overview restore | Web unaffected unless web snapshot is added later | Cached LaTeX preserved | Cached images preserved | `.datalab` workspace model/controller and examples | Workspace docs when visible | Old/new workspace round trip, family snapshot adapters, restore tests |
| P0.5 | CSV/LaTeX serialization | Shared semantic rows | Shared CSV rows and shared LaTeX data model | Desktop CSV/LaTeX wrappers call shared builders | Web CSV/LaTeX wrappers call shared builders | `datalab_latex` or shared non-UI wrappers | None | Snapshot stores semantic rows, not rendered-only rows | Output docs if visible | CSV parity, LaTeX option matrix, compile matrix |
| P0.6 | Plot boundary | Shared plot specs and render-from-spec helpers | Plot spec payloads and `plot_only` annotations | Desktop plot adapters call shared renderers | Web plot adapters call shared renderers where present | Plot captions via shared metadata | Shared render-from-spec implementation | Plot metadata in `result_snapshot` | Plot docs when visible | Deterministic plot, CJK, desktop-internal worker parity, desktop/web parity |
| P0.7 | Fit statistics consolidation | `fitting.statistics.compute_fit_statistics`, `datalab_core.fitting.run_fitting` | Core fitting payload from `run_fitting` / `serialize_fit_result`, fit-stat rows | Existing fitting display adapters; desktop `FitResultPayload` remains adapter detail only | Existing web fitting where present | Shared fitting LaTeX builder/wrapper | Existing fitting plot adapters | Fitting snapshots unchanged except semantic row mapping | Fitting theory docs if visible | No-duplicate metric formulas, display/LaTeX parity |

| Slice | Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
|---|---|---|---|---|---|---|---|---|---|---|
| P1.1 | Descriptive statistics | `compute_statistics`, `run_statistics`, `statistics_payload_to_compute_result` | Descriptive metric rows and diagnostics | Statistics mode view, desktop direct/batch/projection renderers | Web statistics mode where present | Shared statistics LaTeX builder | No new plot in this slice | Statistics `result_snapshot`, descriptive example | Statistics docs/tooltips | Reference values, small-n, zero-variance, all-surface parity |
| P1.2 | Weighted consistency | Same statistics producer path | Weighted diagnostic rows and warnings | Same statistics renderers | Web statistics | Shared statistics LaTeX builder | No new plot unless weighted residual is included later | Statistics snapshot and weighted example | Weighted consistency docs | Weighted normal, zero-sigma anchor, dropped-row, warnings parity |
| P1.3 | Confidence intervals | Same statistics producer path plus shared quantile helper | CI rows, dedicated SE fields, diagnostics | Same statistics renderers and CI labels/tooltips | Web statistics | Shared statistics LaTeX builder | No plot change | Snapshot and CI example; baseline re-cut gate if default visible | CI assumption docs | Quantile references, `n < 2`, weighted `n = 1`, population-mode label tests |
| P1.4 | Outlier flags | Same statistics producer path with provenance | Row flag rows | Compact flag display in statistics UI | Web statistics if row flags surface | Shared statistics LaTeX builder | Optional markers only through plot specs later | Snapshot and outlier example | Advisory outlier docs | Two-tailed robust, MAD-zero, row provenance, all-surface parity |
| P1.5 | Trimmed mean | Same statistics producer path | Trimmed-mean metric rows and option metadata | Statistics UI option if exposed | Web statistics if option exposed | Shared statistics LaTeX builder | No plot change | Snapshot/example only if exposed | Trimmed-mean docs | Trim-fraction validation, reference fixtures, parity |
| P1.6 | Statistics plots | Same statistics producer path plus plot spec helpers | Statistics plot specs and `plot_only` annotations | Desktop plot adapters | Web plot adapters where present | Captions from shared metadata | Histogram, box, QQ, weighted residual shared renderers | Plot metadata in snapshot and examples | Plot docs | Deterministic plot, CJK, desktop/web parity |

| Slice | Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
|---|---|---|---|---|---|---|---|---|---|---|
| P2.1 | Fitting diagnostics | `datalab_core.fitting.run_fitting`, `fitting.statistics.compute_fit_statistics` | Fitting diagnostic rows, correlation rows, residual rows | Fitting display, CSV wrapper, plot adapter | Web fitting parity or explicit deferral | Shared fitting LaTeX builder/wrapper | Correlation heatmap, residual/hist/QQ/bands through shared specs | Fitting snapshot and diagnostics example | Fitting diagnostics docs | Covariance, residual normalization, bands, web parity/deferral, shared output parity |
| P2.2 | Model comparison | Exact multi-fit producer or separate orchestrator spec | Comparison rows from existing fit statistics | Comparison table adapter | Web parity or deferral if exposed | Shared fitting LaTeX builder/wrapper | Optional comparison plot only via spec | Snapshot and example only after producer exists | Model comparison docs | Multi-model fixture, no duplicate formulas, snapshot/CSV/LaTeX parity |
| P2.3 | Root diagnostics | `datalab_core.root_solving.run_root_solving` | Root quality rows, classification tags, plot specs | Root result renderer and desktop worker adapter | None currently | Shared root LaTeX builder/wrapper | Root markers, inset, system residual, uncertainty band | Root snapshot and diagnostic example | Root-solving diagnostics docs | Sign-change, double, boundary, unclassified, plot and LaTeX tests |
| P2.4 | Error diagnostics | `datalab_core.uncertainty.run_uncertainty` | Contribution rows, Taylor/MC rows, plot specs | Error result renderer and worker adapters | Web error propagation where present | Shared error LaTeX builder/wrapper | Contribution, cumulative, MC distribution plots | Error snapshot and diagnostics example | Error diagnostics docs | Contribution, tolerance, Taylor/MC, order comparison, worker/web parity, LaTeX matrix |

## 14. Completion Criteria

This plan is complete when:

- P0 shared schema, snapshot, CSV, LaTeX, and plot boundaries are implemented and tested;
- P1 statistics features are implemented with parity across core, desktop, web, CSV, LaTeX, plots, examples, and workspace snapshots;
- P2 fitting/root/error diagnostics are implemented through existing core envelopes and shared renderers;
- P3/P4 items have separate approved specs before implementation;
- release quality gates pass for every landed slice.
