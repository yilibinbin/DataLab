# DataLab Analysis Enrichment Spec

Date: 2026-06-18

Status: Approved after Codex/Gemini/Claude convergence review

Related context:
- `docs/superpowers/plans/2026-06-18-datalab-code-view-map.md`
- `docs/superpowers/plans/2026-06-18-independent-statistics-feature-enrichment-plan.md`
- `datalab_core/statistics.py`
- `datalab_core/statistics_compute.py`
- `app_desktop/views/statistics.py`
- `statistics_utils.py`

## 1. Goal

Turn DataLab from a set of separate calculation tools into a more complete scientific analysis workbench while preserving the current maintainability direction:

- one shared input/constants path;
- one UI-neutral core request/result envelope per calculation family;
- one mode-specific result formatter per output surface;
- shared LaTeX/table/plot helpers;
- runnable example workspaces for important workflows.

This spec covers all valuable feature tiers identified by Codex, Gemini/Antigravity, and Claude. It is not limited to the first implementation slice. The implementation plan must still stage the work so lower-risk additive improvements land before cross-module workflow changes.

## 2. Non-Goals

- Do not add a separate statistics subsystem outside `datalab_core.statistics` and existing desktop/web adapters.
- Do not replace existing fitting, root-solving, error propagation, input parsing, LaTeX, or plotting engines.
- Do not silently mutate user data for outlier handling; diagnostics may flag rows, but automatic deletion is out of scope.
- Do not add automatic model ranking or opaque "best method" selection.
- Do not build a full notebook execution engine in this spec. Report/history improvements must remain compatible with current `.datalab` workspace snapshots.

## 3. Current Architecture Constraints

### 3.1 Existing Statistics Surface

The current statistics core is narrow:

- `compute_statistics()` supports arithmetic mean and sigma-weighted mean.
- Returned metrics are `mean`, `std_mean`, `std`, `v_min`, `v_max`, `method_label`, `dropped`, condition-specific `effective_n`, condition-specific `zero_sigma_anchor`, and `warnings`.
- Desktop GUI exposes only value column, optional sigma column, statistics mode, weighted variance, and sample/population controls.
- Existing docs/examples teach weighted mean rather than broader statistics.

### 3.2 Required Extension Boundary

Any statistics extension must pass through:

1. `datalab_core.statistics_compute.compute_statistics()` for numeric computation.
2. `datalab_core.statistics.run_statistics()` for JSON-safe payload.
3. `datalab_core.statistics.statistics_payload_to_compute_result()` for legacy desktop/web adapters.
4. `app_desktop.views.statistics` for localized controls.
5. `app_desktop.window_statistics_mixin` and `app_web.logic.statistics` for display and parity.
6. `statistics_utils.py` for LaTeX output.
7. example workspace generator and docs.

No new mode must bypass this path.

The current desktop statistics implementation has two calculation surfaces that must be reconciled before adding metrics:

- an interactive direct path in `app_desktop.window_statistics_mixin` that calls `compute_statistics()` and hand-writes markdown;
- a batch/core-envelope path through `app_desktop.workers_core`, `build_statistics_requests()`, `run_statistics()`, and `statistics_payload_to_compute_result()`.

There is also a core-request projection in `app_desktop.window_extrapolation_mixin` for statistics jobs. P0 must make the interactive path, batch/core-envelope path, and projection path consume or preserve the same statistics result schema. Until they are unified, tests must prove that every metric emitted by `compute_statistics()` is either serialized by `run_statistics()` or explicitly marked internal-only.

### 3.3 Cross-Module Result Principle

New diagnostics must be represented as typed or schema-like result data before they are rendered. Markdown, CSV, LaTeX, plots, and workspace snapshots must consume the same semantic data instead of recomputing values independently.

For calculation families that already have a `datalab_core` request/result handler, that handler is the owning producer/schema boundary. Domain objects and worker functions may remain as implementation details or legacy adapters, but new diagnostics must be serialized through the core envelope before desktop/web/report adapters render them.

CSV builders and LaTeX builders are output serialization logic, not UI logic. New or changed CSV generation must live in a shared core/formatting layer consumed by desktop and web. New or changed LaTeX generation must live in a shared non-UI LaTeX layer, preferably `datalab_latex`, with desktop/web writers acting only as adapters or compatibility wrappers during migration.

Workspace persistence must store a JSON-safe semantic `result_snapshot` rather than relying only on rendered markdown, CSV rows, LaTeX source, or image attachments. The snapshot must include a schema version, calculation family/mode, metric rows, diagnostic rows, row flags, plot spec keys and plot metadata, source payload metadata, warnings, precision/uncertainty settings, and compatibility metadata needed to restore the result overview. The semantic snapshot is the source of truth. Rendered text/CSV/LaTeX should be regenerated from it on restore whenever deterministic; legacy rendered artifacts may remain only as invalidatable compatibility/performance caches. P3 result history, comparison, and report bundles must consume `result_snapshot` instead of parsing presentation strings or duplicating workspace persistence logic.

### 3.4 Feature Routing Table

Every implementation slice must include a routing table before code changes. The table must use the same columns as the canonical routing table below: feature family, exact producer, core payload/schema, desktop renderer, web renderer if one exists, LaTeX/report writer, plot function, workspace/example impact, docs, and tests.

Initial routing requirements:

| Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
|---|---|---|---|---|---|---|---|---|---|
| Statistics | `datalab_core.statistics_compute.compute_statistics`, `datalab_core.statistics.run_statistics`, `datalab_core.statistics.statistics_payload_to_compute_result` | `datalab_core.results.ResultEnvelope`, `StatisticsRequestBatch`, P0 statistics result rows | `app_desktop.window_statistics_mixin._run_statistics_mode`, `_render_statistics_text`; `app_desktop.workers_core._execute_calc_job`; `app_desktop.window_extrapolation_mixin` statistics projection; `app_desktop.views.statistics.build_statistics_mode_view`; legacy `_build_stats_csv_rows` and plot adapters must be migrated or wrapped by shared serializers/renderers before expansion | `app_web.logic.statistics._run_statistics` | shared LaTeX builder, initially `statistics_utils.generate_statistics_latex` / `generate_statistics_latex_batches`, with any new or changed LaTeX generation routed through `datalab_latex` or a shared non-UI wrapper | planned `shared.analysis_plot_specs.StatisticsPlotSpec` plus one shared render-from-spec implementation consumed by desktop and web adapters | semantic `result_snapshot`, `examples/catalog.py`, `tools/generate_example_workspaces.py` | `docs/desktop/statistics.*.md`, `docs/desktop/theory.*.md`, `examples/README.md` | `tests/test_datalab_core_statistics.py`, `tests/test_statistics_modes_and_flags.py`, `tests/test_statistics_mathematica_reference.py`, `tests/test_statistics_weighted.py`, desktop/web/LaTeX/CSV/plot parity tests |
| Fitting diagnostics | `datalab_core.fitting.build_fitting_request`, `datalab_core.fitting.run_fitting`, `datalab_core.fitting.fitting_payload_to_fit_result`; domain calculators `FitResult`, `fitting.statistics.compute_fit_statistics`, `fitting.runner`, `fitting.hp_fitter`, `fitting.implicit_model` remain implementation details or subprocess adapters | `datalab_core.results.ResultEnvelope`, core fitting payload from `run_fitting` / `serialize_fit_result`, fitting diagnostic rows | `app_desktop.window_fitting_formatters_mixin._format_fit_display`; legacy `_build_fit_csv_rows` must be migrated or wrapped by a shared CSV serializer; desktop `FitResultPayload` remains an adapter detail, not the core schema; `app_desktop.window_fitting_residuals_mixin._render_fit_plot_bytes` consumes plot specs | `app_web.logic.fitting._run_fit` when equivalent output exists | shared fitting LaTeX builder in `datalab_latex` or a shared non-UI wrapper; existing `app_desktop.fitting_latex_writer` and `app_web.logic.fitting._generate_fitting_latex` become adapters only | planned `shared.analysis_plot_specs.FittingPlotSpec`; shared render-from-spec adapter for `fitting.plot_fitting.render_fitting_overview` / residual plots | semantic `result_snapshot`, fitting example workspaces and docs | `docs/desktop/fitting.*.md`, `docs/desktop/theory.*.md` | `tests/test_fit_statistics.py`, fitting display/LaTeX/CSV/plot tests, web fitting parity tests where applicable |
| Root diagnostics | `datalab_core.root_solving.build_root_solving_request`, `datalab_core.root_solving.run_root_solving`, `datalab_core.root_solving.root_batch_payload_to_result`; domain functions `root_solving.batch.solve_root_batch`, `root_solving.solver`, `root_solving.models`, `root_solving.uncertainty_policy` remain implementation details | `datalab_core.results.ResultEnvelope`, `RootBatchResult` payload, root diagnostic rows | `root_solving.formatting.render_root_result`, `root_solving.formatting.render_root_batch_result`; `app_desktop.workers_core._execute_root_solving_job_payload` is legacy/subprocess adapter and must not become the schema owner | none currently | shared root LaTeX builder in `datalab_latex` or a shared non-UI wrapper; existing `app_desktop.root_latex_writer` becomes an adapter only | planned `shared.analysis_plot_specs.RootPlotSpec`; shared render-from-spec adapter around `root_solving.plotting.render_nominal_root_plots` | semantic `result_snapshot`, root example workspaces and docs | `docs/desktop/root-solving.*.md`, `docs/desktop/theory.*.md` | root-solving core/formatting/plot/LaTeX tests |
| Error diagnostics | `datalab_core.uncertainty.build_uncertainty_request`, `datalab_core.uncertainty.run_uncertainty`, `datalab_core.uncertainty.uncertainty_payload_to_results`; shared error propagation engine remains implementation detail | `datalab_core.results.ResultEnvelope`, error propagation result payload, diagnostic rows, contribution rows | `app_desktop.window_extrapolation_mixin._on_calc_finished`; duplicated `app_desktop.workers_core` / `workers_qt` contribution summary and plot helpers must be consolidated behind shared contribution-row and render-from-spec functions before enrichment | `app_web.logic.error_propagation` | `datalab_latex.latex_tables_error_propagation.generate_error_propagation_table`; existing web `_render_error_latex` becomes an adapter only | planned `shared.analysis_plot_specs.ErrorPropagationPlotSpec`; one shared contribution render-from-spec implementation consumed by desktop worker and web adapters | semantic `result_snapshot`, error example workspaces and docs | `docs/desktop/uncertainty.*.md`, `docs/desktop/theory.*.md` | error propagation engine, contribution rows, desktop-internal worker parity, web parity, plot, CSV, and LaTeX tests |

Features that touch a module with an existing web adapter must include web parity or explicitly document why the web surface is deferred. Root-solving is currently desktop-only, so root diagnostics do not require web parity unless a web root adapter is added later.

### 3.5 Shared Diagnostic Rows

Before adding new per-module diagnostics, define a shared diagnostic row shape for P0-P2 work. Statistics metric rows, row flags, fitting residual diagnostics, root residual diagnostics, and error propagation diagnostics must be compatible with this shape or explicitly mapped to it.

P0 must freeze only the fields emitted by the statistics foundation slice and required for immediate renderer parity. Fields and plot keys first needed by fitting, root-solving, error propagation, or P3 uncertainty-budget work are provisional until the slice that emits them lands. They may be added in those later slices, but P0 tests must not bind unused future fields or plot keys solely because they are listed here for cross-module direction.

Common P0-P2 fields:

- `key`: stable machine key;
- `label_key`: stable semantic label key. Presentation layers map this key to localized Chinese/English labels;
- `value`: numeric/text value when applicable;
- `uncertainty`: optional uncertainty value;
- `source`: optional input/parameter/equation/source name; provisional until a slice emits it;
- `row_index`: optional stable source row or source line identifier; statistics row flags must carry parser-provided provenance rather than recomputing row positions after filtering;
- `method`: diagnostic method or statistic definition; provisional until a slice emits it;
- `severity`: `info`, `warning`, or `error`;
- `message_key`: optional stable semantic message key. Presentation layers map this key to localized Chinese/English messages;
- `render_group`: metric, diagnostic, row_flag, or plot_annotation.

Core compute modules and core payloads must not emit UI-localized strings as authoritative data. During migration, legacy fields such as `method_label` may remain for compatibility, but new rows must use semantic keys and perform localization in desktop/web/report adapters.

P0 statistics request construction must define row provenance before P1 row flags land. `StatisticsRequestBatch` / `ComputeJobRequest.inputs` must be able to carry stable source row or line identifiers from desktop, web, file, and batch parsing paths. P1 row flags must report those identifiers, and parser/provenance parity tests must cover desktop direct, desktop batch/core-envelope, and web inputs.

P3 uncertainty-budget rows must either extend this shape or provide an explicit mapping in the separate P3 uncertainty-budget spec.

### 3.6 Shared Plot Specs

Plot additions must define semantic plot specs before rendering. `shared.plotting` centralizes backend/font behavior, but it is not by itself a semantic plot contract.

Each plot spec must define the fields needed by the slice that introduces the plot. Statistics plot keys below are binding when statistics plots land. Fitting/root/error plot keys are roadmap keys until their slices add concrete plot specs and tests.

- stable plot key, such as `statistics.histogram`, `statistics.box`, `statistics.qq`, `statistics.weighted_residual`, `fitting.residual`, `fitting.correlation_heatmap`, `root.nominal`, or `error.contribution`;
- plot type;
- input series and units/labels;
- computed annotations such as mean, median, roots, residual thresholds, or uncertainty bands;
- axis scale for each axis (`linear`, `log`, or explicit unsupported);
- axis sharing/linkage requirements, such as shared x-axis for fit/residual plots;
- binning, quantile, or reference-line rules where relevant;
- warnings and fallback behavior;
- deterministic test fixture expectations.

Desktop and web plot adapters must render from the same plot spec through a shared render-from-spec implementation where both surfaces exist. A shared semantic spec without a shared render function is not sufficient for enriched plots. Existing duplicated desktop worker renderers, such as contribution plots in `workers_core` and `workers_qt`, must be consolidated or wrapped so the visual data construction and plotting rules live in one place and are covered by desktop-internal parity tests.

Statistics plot specs must include these initial keys:

- `statistics.histogram`: values, optional sigma, histogram bins by deterministic rule, mean marker, median marker, optional flagged-row markers.
- `statistics.box`: values, Q1, median, Q3, whisker rule, outlier flags.
- `statistics.qq`: sorted standardized values against normal quantiles; visual diagnostic only, no formal normality verdict in the first release.
- `statistics.weighted_residual`: x/index axis, residual `x_i - mean`, standardized residual when sigma is available, and horizontal lines at `0`, `+3`, and `-3`.

## 4. Priority Model

Priorities are product and engineering priorities, not release labels.

- P0: Foundations needed to prevent drift and duplicated code.
- P1: High-value, contained scientific features.
- P2: High-value diagnostics with moderate fan-out.
- P3: Larger workflow/reporting features.
- P4: Longer-term advanced analysis features.

Implementation must preserve backwards compatibility for existing workspaces, current result fields, and existing statistics mode strings.

## 5. P0 Foundations

### 5.1 Statistics Result Schema

Introduce a shared internal representation for statistics outputs before broadening metrics.

Required data concepts:

- input summary: selected value column, sigma source, row count, dropped row count;
- method metadata: mode id, semantic method label key, sample/population policy, weighted variance policy;
- metric rows: stable key, semantic `label_key`, value, optional uncertainty, optional unitless/numeric formatting hint, `render_group`; localized labels are produced only by desktop, web, LaTeX, and report adapters;
- diagnostic rows: warnings, flags, effective sample size, consistency metrics;
- optional row flags: row index, label, reason, severity.

This can be implemented as dataclasses or a disciplined dict schema, but the schema must be documented and tested. Existing compute-result fields (`mean`, `std_mean`, `std`, `v_min`, `v_max`, etc.) and JSON payload fields (`mean`, `std_mean`, `std`, `min`, `max`, etc.) must remain present for compatibility during migration, with the `v_min`/`v_max` to `min`/`max` adapter mapping tested explicitly.

Warnings are part of the public semantic result even if they continue to travel through `ResultEnvelope.warnings` during migration. Coverage tests may treat the envelope warnings channel as serialized output, but adapters must map those warnings into diagnostic rows or an explicitly tested warnings collection before rendering.

The schema must include a mode-and-condition-aware coverage invariant:

- every public metric, diagnostic row, row flag, and plot annotation returned or derived by `compute_statistics()` for a specific `(mode, condition)` is serialized by `run_statistics()`, deserialized by `statistics_payload_to_compute_result()`, and represented in the shared result rows for that same context; or
- the item is a public field with an intentional boundary rename documented in a tested key-mapping table; or
- the item is explicitly marked internal-only in a tested allowlist.

Initial public key mappings:

- compute-result `v_min` maps to JSON payload `min` and back to legacy compute-result `v_min`;
- compute-result `v_max` maps to JSON payload `max` and back to legacy compute-result `v_max`.

The implementation plan must define the initial coverage matrix. It must include at least:

- arithmetic modes (`mean`, `mean_sample`, `mean_population`): mean, standard error, standard deviation, variance where exposed, min, max, row count, method metadata, and sample/population policy;
- descriptive mode with `n >= 4`: all descriptive metrics, robust metrics, and row flags when triggers are present;
- descriptive small-`n` cases: unavailable skewness/kurtosis diagnostics;
- weighted normal case: weighted mean, analytical known-sigma standard error, effective sample size, chi-square, dof, reduced chi-square, Birge ratio, and weighted known-sigma CI when conditions are met;
- weighted zero-sigma anchor case: anchor diagnostics and explicit absence of weighted chi-square/CI;
- weighted dropped-row case: dropped-row diagnostic and row count consistency;
- outlier-flag contexts: sigma-based and MAD-based flags only when their trigger data exists.

Coverage matrix rows are binding when their producing feature lands. P0 tests cover current arithmetic and current weighted rows plus the `v_min`/`v_max` key mapping; P1/P2 rows become mandatory in the same implementation slice that introduces the corresponding metrics or diagnostics. The allowlist is only for internal-only values. It must not be used to hide public-but-conditional output.

### 5.2 Shared Rendering Contract

Statistics output renderers must share the same metric rows and semantic snapshot:

- desktop interactive markdown/result table;
- desktop batch markdown/result table;
- CSV export;
- single-run and batch LaTeX writers;
- web display and CSV output;
- workspace result snapshot.

Adding a metric, diagnostic, row flag, plot annotation, or uncertainty-budget row must not require hand-writing inconsistent labels or formatting in separate adapters. CSV rows must be produced by a shared serializer from the semantic rows. LaTeX rows must be produced by a shared non-UI builder. Plot-only annotations must either reference a backing metric/diagnostic row or be explicitly marked `plot_only` in the plot spec so text/CSV/LaTeX coverage tests do not force them into non-plot surfaces. The first implementation may keep current writers as wrappers, but must add tests that fail if a public result item exists in `compute_statistics()` and is missing from payload/envelope warnings, desktop interactive output, desktop batch output, web output, shared CSV output, shared LaTeX output, or workspace semantic `result_snapshot`.

### 5.3 Test Matrix Baseline

Before feature additions, add or confirm tests for:

- core statistics payload round trip;
- desktop and web statistics parity for existing modes;
- direct desktop statistics path, batch/core-envelope statistics path, and `app_desktop.window_extrapolation_mixin` statistics projection path parity;
- LaTeX option matrix coverage for statistics rows with `dcolumn`, `siunitx`, grouping enabled/disabled, and bilingual captions;
- example workspace open-and-run coverage for statistics;
- high-precision preservation under `precision_guard`.

### 5.4 Fit Statistics Consolidation

Before implementing model comparison or new fitting diagnostics, identify all existing fit metric computations. New model comparison output must consume existing `FitResult` fields and `fitting.statistics.compute_fit_statistics()` results, or consolidate duplicated AIC/BIC/RMSE/R2 logic first. It must not introduce a third metric formula in UI/report code.

## 6. P1 Statistics Enrichment

### 6.1 Descriptive Statistics Mode

Add a `descriptive` statistics mode for one selected value column.

Required metrics:

- count `n`;
- mean;
- standard deviation and variance;
- standard error;
- min and max;
- median;
- Q1 and Q3;
- IQR;
- MAD, defined as median absolute deviation from the median;
- skewness;
- kurtosis with an explicit definition in docs and tooltips.

Definition requirements:

- Quantile interpolation uses the Hyndman-Fan type 7 method, equivalent to NumPy's default linear percentile method: position `h = 1 + (n - 1) * p`, with linear interpolation between adjacent sorted values. Use this for Q1, median, Q3, and any percentile output unless a later spec changes it.
- Variance follows the existing sample/population checkbox for arithmetic statistics: sample variance uses `n - 1`, population variance uses `n`.
- Skewness is the adjusted Fisher-Pearson standardized moment coefficient when `n >= 3` in sample mode; population mode uses the population third standardized central moment.
- Kurtosis is reported as excess kurtosis. In sample mode, use the bias-corrected Fisher excess kurtosis when `n >= 4`; in population mode, use population fourth standardized central moment minus 3.
- For `n < 2`, variance/std-dependent metrics must return a non-crashing empty/non-finite state with a localized warning.
- For `n < 3`, sample skewness is unavailable; for `n < 4`, sample excess kurtosis is unavailable. The result must show a blank/non-finite value and a localized diagnostic row rather than falling back silently.
- If variance is zero, skewness and kurtosis must return a blank/non-finite value with a semantic diagnostic key indicating zero variance; do not divide by zero or report a misleading finite moment.

UI requirements:

- Add localized statistics mode label: "Descriptive statistics" / "描述性统计".
- Existing sample/population control must clearly state which metrics it affects.
- Sigma column may remain optional and ignored for descriptive mode unless a future weighted descriptive mode is implemented.

### 6.2 Robust Summary Metrics

The descriptive mode must include robust metrics useful for noisy scientific data:

- median;
- MAD;
- IQR;
- optional trimmed mean in a later slice, controlled by a trim fraction.

Trimmed mean is P1.5: valuable, but it introduces a user option. It must be added only after the base descriptive payload is stable.

### 6.3 Weighted Mean Consistency Diagnostics

For `weighted_sigma` mode, add diagnostics that tell users whether the scatter is consistent with reported sigma values:

- weighted chi-square of the mean: `chi2 = sum(w_i * (x_i - mean)^2)`, where `w_i = 1 / sigma_i^2` for every finite positive sigma used in the weighted mean;
- degrees of freedom: `dof = n_used - 1`;
- reduced chi-square: `reduced_chi2 = chi2 / dof` when `dof > 0`;
- Birge ratio: `sqrt(reduced_chi2)` when valid;
- localized warnings for insufficient dof, conflicting zero sigma anchors, or dropped sigma rows.

These diagnostics must be additive. Existing mean and standard error behavior must not change.

### 6.4 Confidence Interval for Mean

Add optional confidence interval reporting for the mean.

Default:

- 95% confidence interval;
- enabled by default in result output when enough degrees of freedom exist;
- no extra GUI control in the first slice unless implementation requires a confidence-level selector.
- because default CI rows intentionally change rendered statistics output, the CI slice must re-cut affected parity snapshots, LaTeX expectations, and example workspaces in the same change. If that fixture churn is not acceptable for a release, the CI row must remain disabled or hidden until the baseline is intentionally updated.

Calculation:

- Unweighted mean: Student-t interval using a dedicated sample standard error field, `mean_sample_se_for_ci = sample_std / sqrt(n)`, and `dof = n - 1`. This field must use the unbiased sample standard deviation regardless of whether the displayed statistics mode currently shows sample or population standard deviation. It must not blindly reuse `std_mean` in population mode. If `n < 2`, suppress the Student-t CI with a diagnostic unless a future feature explicitly supplies a known population sigma and normal interval.
- Weighted mean: first release reports the analytical known-sigma interval `mean ± z_(1-alpha/2) * sqrt(1 / sum(w_i))` when at least one finite, non-zero-sigma weighted point is used and zero-sigma anchor handling is inactive. Use the normal quantile, not Student-t, because the standard error comes from supplied sigma values rather than sample-estimated scatter.
- Weighted CI must use a dedicated analytical standard error field, `weighted_se_known_sigma = sqrt(1 / sum(w_i))`. It must not reuse the current `std_mean` blindly because existing weighted mode can report either inverse-variance uncertainty or scatter-based standard error depending on the variance toggle.
- If the user disables weighted variance/SE behavior, the analytical CI may still be shown only when it is clearly labeled as "known-sigma weighted CI"; otherwise suppress the CI with a diagnostic. Do not mix the scatter-based `std_mean` with the known-sigma CI formula.
- Degrees-of-freedom definitions must stay separate: `n_used - 1` is used for weighted consistency chi-square; Kish `effective_n = W^2 / W2` remains an effective sample-size diagnostic; existing weighted sample-variance correction remains a variance-estimator detail; the analytical weighted z interval does not use Student-t dof.
- Optional Birge-adjusted weighted interval is a later diagnostic: if implemented, it must explicitly multiply the analytical weighted standard error by `max(1, Birge ratio)` and label the interval as over-dispersion adjusted. It must not silently replace the analytical interval.
- Student-t critical values must be computed under `precision_guard` as the inverse CDF of Student's t distribution. Implement the inverse through a tested shared helper based on the regularized incomplete beta relationship, with documented monotonic root/inversion behavior and reference values for common degrees of freedom. The helper must reject `dof <= 0` and confidence levels outside `(0, 1)`.
- Normal critical values for weighted known-sigma intervals must come from the same shared distribution-quantile helper layer and be tested against reference values.

Precision:

- Distribution quantiles must run inside `precision_guard`.
- Degenerate cases must produce explicit warnings, not crashes.

### 6.5 Outlier Flags

Add advisory outlier diagnostics:

- sigma-based flag: absolute residual above `3 * sigma` when sigma is available and positive;
- robust flag: absolute modified z-score above `3.5`, computed as `abs(0.6745 * (x - median) / MAD)` when MAD is positive.
- MAD-zero case: when `MAD == 0`, flag any value with `|x - median| > 0` as a robust outlier and attach a semantic diagnostic key indicating zero MAD fallback. Do not silently disable robust outlier detection.

Rules:

- Do not remove outliers automatically.
- Flags must include row index, value, metric used, and reason.
- Result tables may show a compact flagged-row list; detailed row-level output can be deferred until report-bundle work.

### 6.6 Statistics Plots

Add optional plots for statistics mode:

- histogram with mean and median markers;
- box plot;
- QQ plot for normality inspection;
- weighted residual plot for weighted mean consistency.

These must reuse shared plotting helpers, including CJK-safe fonts.

## 7. P2 Fitting Diagnostics

### 7.1 Parameter Correlation Matrix

Compute and display parameter correlations from existing covariance and parameter error data.

Requirements:

- correlation matrix table with values in `[-1, 1]`;
- diagonal must be `1` when finite;
- non-finite covariance or zero parameter error must produce blank/NaN cells plus warnings;
- optional heatmap plot using shared plotting helpers.

### 7.2 Goodness-of-Fit Diagnostics

Add:

- chi-square goodness-of-fit p-value when weighted chi-square and degrees of freedom are valid. Use the upper-tail chi-square survival probability `Q(dof / 2, chi2 / 2)` under `precision_guard`;
- residual QQ plot and residual histogram as visual diagnostics only. Do not report a formal normality verdict in the first release;
- standardized residual table. When sigma values are available, use `z_i = residual_i / sigma_i`; when only weights are available, use `z_i = residual_i * sqrt(w_i)`; when unweighted, report normalized residual `residual_i / RMSE` and label it as normalized rather than sigma-standardized;
- max standardized residual summary.

These are diagnostics only. They must not change fit results or model ranking.

### 7.3 Residual and Band Plots

Add:

- residual plot with zero line and optional sigma bands;
- histogram/QQ plot of residuals;
- confidence and prediction bands for supported models when covariance and parameter Jacobian are available. For a model prediction `f(x, p)` with parameter covariance `C`, let `J_p(x)` be the row vector Jacobian of `f` with respect to the fitted parameters `p`, evaluated at `x`; the confidence-band standard uncertainty is `sqrt(J_p(x) C J_p(x)^T)`. Prediction bands add residual variance only when a finite residual variance estimate is available and the result is clearly labeled as a prediction band.

Rules:

- If covariance or Jacobian is unavailable, fall back to existing plot and show a warning.
- Band generation must be performance guarded for large datasets.
- Plots must be deterministic in tests.

### 7.4 Model Comparison Table

For workflows that run multiple fits or batches, expose a comparison table:

- model name;
- free parameter count;
- chi-square;
- reduced chi-square;
- AIC;
- BIC;
- RMSE;
- R2;
- warnings.

This must present evidence only; no automatic "winner" selection.

The comparison-table slice must name an exact multi-fit producer before implementation. Acceptable producers are an existing auto-model/batch-fit workflow that already returns multiple `FitResult` objects, or a new explicitly scoped batch-fit orchestrator. If new orchestration is required, it is a workflow feature, not merely a display diagnostic, and needs its own routing table covering input selection, cancellation, result snapshots, examples, and tests. Single-fit diagnostics must not create duplicate AIC/BIC/RMSE/R2 formulas while waiting for this producer.

## 8. P2 Root-Solving Diagnostics

### 8.1 Solver Quality Summary

For every root-solving result, expose:

- solver status;
- residual norm;
- per-equation residuals for systems;
- iteration count if available;
- Jacobian condition estimate when available;
- initial guess or bracket summary;
- warning/hint text for likely failure causes.

### 8.2 Scan Diagnostics

For scan/multi-root modes:

- interval where each root was found;
- sign-change or bracket evidence;
- duplicate-root merge notes;
- failed intervals and reasons;
- root classification where practical and only by explicit criteria. Classification is a set of tags, not a single exclusive label. Tags are: `complex` only for modes that explicitly solve complex roots; `bracketed_sign_change` when the bracket endpoints have opposite signs; `boundary` when the root is within the configured cluster/merge tolerance of a scan boundary; `suspected_tangent_or_repeated` when no sign change is observed, the residual is below the existing solver residual tolerance, and the local finite-difference slope is small after converting it back to an output-scale change. For the first implementation, use the root scanner's existing tolerance vocabulary and choose two distinct finite-difference points. If no distinct pair is available or `delta_x == 0`, do not emit `suspected_tangent_or_repeated`; fall back to another valid tag or `unclassified`. Otherwise let `slope = delta_f / delta_x`, `x_scale = max(abs(x_right - x_left), configured_scan_step, cluster_tolerance)`, and classify only when `abs(slope) * x_scale <= residual_tolerance`. Do not introduce a new relative tolerance unless a later root-scanner configuration spec adds it and tests all affected modes. Add fixture tests for a simple sign-change root, a double root, a boundary root, a zero-`delta_x` finite-difference case, and an unclassified near miss. If no tag applies, report `unclassified`. Rendering may order tags as `complex`, `bracketed_sign_change`, `suspected_tangent_or_repeated`, `boundary`.

### 8.3 Root Plot Enhancements

Enhance existing plots:

- root markers with uncertainty bars when visible;
- automatic inset or local zoom when uncertainty is too small to see;
- residual plot for systems when direct function plot is ambiguous;
- uncertainty band following the chosen uncertainty propagation method.

## 9. P2 Error Propagation Enhancements

The error propagation module already has Taylor and Monte Carlo methods. Enrich its diagnostics rather than adding parallel algorithms.

Add:

- contribution table sorted by absolute contribution;
- contribution plot and cumulative contribution percentage;
- comparison view for Taylor order 1 vs order 2 when both are requested or available;
- Monte Carlo distribution plot with mean, standard deviation, and percentile markers;
- warning when Taylor and Monte Carlo mean estimates differ by more than both `3 * monte_carlo_standard_error` and a practical effect-size floor. The effect-size floor is `max(absolute_result_tolerance, relative_result_tolerance * max(abs(taylor_mean), abs(monte_carlo_mean)))`; initial tolerances must be specified in the implementation plan and covered by tests. `monte_carlo_standard_error = monte_carlo_sigma / sqrt(sample_count)`. This compares estimated means, not output-distribution widths. Separately report relative difference between Taylor and Monte Carlo output standard deviations when both are available; do not fold that into the mean-disagreement threshold.

All formulas must continue through the shared formula rendering/export path.

## 10. P3 Cross-Module Uncertainty Budget

Create a common "uncertainty budget" concept that can be consumed by statistics, error propagation, fitting, and root solving. This is a high-fan-out P3 feature and requires a separate implementation spec after P0-P2 diagnostic rows and plot specs are proven.

The later P3 spec must decide whether uncertainty-budget rows extend the P0 diagnostic row shape or use a separate schema with an explicit adapter. This document does not authorize adding P3-only fields to P0.

Common row fields:

- source name;
- nominal value if meaningful;
- uncertainty;
- sensitivity or contribution;
- percent contribution where mathematically meaningful;
- method/source type;
- warning.

Module mapping:

- error propagation: existing derivative or Monte Carlo contribution terms;
- root solving: propagated input/constant contributions;
- fitting: parameter covariance/correlation and target sigma influence where defensible;
- statistics: sigma-weighted consistency and row-level influence.

The UI must present this as a shared result panel section, not as separate ad hoc markdown in each module.

## 11. P3 Report Bundle and Plot Gallery

Add a report bundle concept for a completed calculation:

- input data summary;
- constants summary;
- formula/model/equation summary with rendered formula;
- core numeric result table;
- diagnostics;
- plots;
- LaTeX source and compile status;
- warnings/logs;
- reproducibility metadata: DataLab version, precision digits, uncertainty digits, backend, random seed when applicable.

This must reuse the existing right-side result overview and workspace snapshot system. It must not duplicate `.datalab` workspace persistence logic.

P3 report bundles require a separate implementation spec after P0-P2 diagnostic rows and plot specs are stable. This document defines desired capability and constraints, not immediate implementation permission.

## 12. Example Gallery Expansion

Every new capability must have a runnable example workspace unless the relevant section explicitly defers the example to a later spec.

Required new examples for P1/P2-capable releases:

- descriptive statistics with outlier and robust summary;
- weighted mean consistency check;
- confidence interval for repeated measurements;
- fitting diagnostics with correlated parameters;
- root-solving failure-to-diagnosis example;
- error propagation Taylor vs Monte Carlo comparison;

Deferred examples:

- report bundle example, which belongs to the separate report-bundle implementation spec from Section 11.

Rules:

- Generate example workspaces via existing tooling, not by hand-editing binary `.datalab` files.
- Example workspaces must open as templates and must not overwrite bundled examples.
- Each example must pass default calculation smoke tests.

## 13. P3 GUI Workflow Enhancements

Add workflow affordances without building a full notebook engine:

- result history for the current workspace session;
- compare two or more result snapshots;
- copy report section as Markdown/LaTeX;
- "send result to next module" affordances where safe, such as statistics summary to fitting notes or root result to constants.

Rules:

- Result history must be opt-in or bounded to avoid bloated workspace files.
- Snapshot comparison must use stable result schema, not screenshots.
- Any cross-module transfer must be explicit and reversible.
- Workflow history and cross-module transfer require separate implementation specs after report bundle storage semantics are decided.

## 14. P4 Advanced Analysis Candidates

These are valuable but must wait until P0-P3 contracts are stable:

- multi-column descriptive statistics;
- covariance/correlation matrix across columns;
- grouped statistics by category column;
- bootstrap confidence intervals;
- hypothesis tests such as t-test, chi-square consistency test, normality tests;
- time-series smoothing and rolling statistics;
- unit-aware calculations;
- plugin-like analysis recipes.

P4 items require separate specs before implementation.

## 15. Localization and Documentation

All user-visible labels, tooltips, warnings, result metric labels, LaTeX captions, and docs must support Chinese and English.

Documentation must explain:

- exact statistical definitions;
- sample vs population behavior;
- quantile interpolation method;
- weighted consistency formulas;
- confidence interval assumptions;
- outlier flags as advisory only;
- limitations for non-finite, small-n, and zero-uncertainty cases.

## 16. Validation Requirements

Each feature slice must include:

- core numeric unit tests with high precision;
- edge case tests for empty/singleton/non-finite/zero-sigma inputs;
- two-tailed robust outlier fixtures when modified z-score flags are added;
- desktop/web parity tests when web supports the same surface;
- result payload round-trip tests;
- mode-and-condition coverage-invariant tests from Section 5.1;
- direct desktop statistics path, batch/core-envelope path, and statistics projection path parity tests from Sections 3.2 and 5.3;
- desktop-internal worker parity tests for any pre-existing duplicated worker path that a slice enriches, especially contribution summary/plot paths in error propagation;
- LaTeX generation tests and option-matrix coverage when rows are added;
- GUI schema/bilingual/help-affordance scans for new controls;
- screenshot or widget-level layout tests when controls are added;
- example workspace open-and-run tests when examples are added;
- performance guard tests for plot bands, bootstrap, or large batch operations.

## 17. Rollout Strategy

Recommended rollout:

1. P0 schema/rendering foundation.
2. P0 shared diagnostic row shape and shared plot spec contract.
3. P0 shared output serialization foundation: semantic `result_snapshot`, shared CSV serializer, shared LaTeX-builder adapters, and shared render-from-spec plot boundary.
4. P0 fit-statistics consolidation check.
5. P0/P2 duplicated contribution summary/plot consolidation before enriching error diagnostics.
6. P1 statistics descriptive mode and weighted consistency diagnostics.
7. P1 confidence interval and outlier flags.
8. P1/P2 statistics plots from shared plot specs and shared render functions.
9. P2 fitting diagnostics.
10. P2 root-solving diagnostics.
11. P2 error propagation diagnostics.
12. P3 uncertainty budget under a separate implementation spec that decides whether to extend or adapt the P0 diagnostic row shape.
13. P3 report bundle and examples under a separate implementation spec.
14. P3 workflow history/compare under a separate implementation spec.
15. Separate P4 specs.

Each rollout stage must be independently shippable and revertible.

## 18. Review Checklist

Three-model review must reject this spec if:

- it proposes duplicated parsing, constants, LaTeX, plotting, or workspace logic;
- any feature bypasses the `datalab_core` request/result envelope where one already exists;
- statistics additions do not account for desktop, web, LaTeX, CSV, and workspace result surfaces;
- formulas or statistical definitions are ambiguous;
- confidence interval or p-value features lack small-sample and non-finite behavior;
- outlier handling can silently modify user data;
- large workflow features are scheduled before P0/P1 foundations;
- testing is not strong enough to catch drift across GUI, backend, LaTeX, examples, and docs.
