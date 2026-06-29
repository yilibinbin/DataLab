# DataLab Test Matrix

## Automated (recommended every change)

Run from `data_extrapolation_gui/DataLab`:

- Syntax compile: `python -m compileall -q .`
- Unit/integration tests: `pytest -q`

## Release Gate

A release cannot proceed while the GUI scan reports issues, screenshot capture fails, any screenshot manifest entry has visual issues, or any packaging resource check fails.

Run the full local gate before packaging:

```bash
python -m compileall -q .
python -m ruff check app_desktop app_web datalab_core datalab_latex fitting shared tests tools formula_help.py statistics_utils.py data_extrapolation_gui.py data_extrapolation_latex_latest.py
python tools/release_import_hygiene.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_app_desktop_views_registry.py tests/test_desktop_workbench_specs.py tests/test_desktop_workbench_state_ownership.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_formula_panel.py tests/test_desktop_workbench_variable_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_render_service.py tests/test_formula_export.py tests/test_formula_latex_export.py tests/test_expression_registry.py tests/test_expression_engine_formula_rendering_integration.py tests/test_formula_preview_rendering.py tests/test_formula_preview_dialog.py tests/test_formula_mathtext_png.py tests/test_formula_renderer_boundary.py tests/test_formula_renderer_value_gate.py tests/test_app_web_extrapolation_latex.py tests/test_app_web_fitting_latex.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_table_segments_and_filtering.py tests/test_latex_generation_consistency.py tests/test_latex_group_size_zero.py tests/test_fitting_latex_writer.py tests/test_latex_tables_facade_exports.py tests/test_latex_security_include_traversal.py tests/test_expression_engine_latex_manual_formatter.py tests/test_latex_formatting_expand_scientific.py tests/test_latex_formatting_spacing_helpers.py tests/test_latex_tables_unit.py tests/test_latex_tables_common_unit.py tests/test_latex_varwidth_regression.py tests/test_sisetup_block.py tests/test_siunitx_column_spec_regression.py tests/test_r10_c1_latex_content_validation_called.py tests/test_latex_compile_worker.py tests/test_desktop_latex_compile_ui.py tests/test_latex_engine_discovery.py tests/test_latex_engine_install.py tests/test_tinytex_install_script.py tests/test_latex_compile_e2e.py tests/test_theory_docs_compile.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_visual_screenshots.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_desktop_editor_affordances.py tests/test_desktop_shared_ui_specs.py tests/test_workspace_controller.py tests/test_packaging_resources.py tests/test_desktop_docs_resources.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_root_solving_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_statistics_ui.py tests/test_desktop_extrapolation_ui.py tests/test_constants_editor.py tests/test_constants_editor_visibility.py tests/test_constants_text_view.py tests/test_constraints_parameter_state.py tests/test_fitting_parameter_inference.py tests/test_parameter_table.py tests/test_parameter_table_editor.py tests/test_desktop_result_schema_ui.py tests/test_desktop_result_workflows.py tests/test_result_view_schema.py tests/test_desktop_theme_tokens.py tests/test_tutorial_overlay.py tests/test_desktop_section_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_bilingual_errors.py tests/test_clipboard_paste_parser.py tests/test_desktop_about_dialog.py tests/test_desktop_global_options_ui.py tests/test_desktop_gui_screenshot_smoke.py tests/test_desktop_mode_stack.py tests/test_desktop_schema_widgets.py tests/test_desktop_shell_layout.py tests/test_qfiledialog_titles_bilingual.py tests/test_splitter_persistence.py tests/test_table_row_col_buttons.py tests/test_ui_schema.py tests/test_ui_schema_audit.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_benchmark_scaffold.py tests/test_cli_batch.py tests/test_crash_reporter.py tests/test_help_specs_single_source.py tests/test_logging_format.py tests/test_model_id_aliases.py tests/test_model_selector.py tests/test_presets.py tests/test_pyproject_metadata.py tests/test_settings_store.py tests/test_r10_c5_m5_requires_positive_x.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_notebook_export.py tests/test_pdf_preview_controller_integration.py tests/test_pdf_preview_page_cache.py tests/test_pdf_preview_raster_backend.py tests/test_pdf_preview_raster_pdftoppm_multi_page.py tests/test_plotting_backend.py
pytest -q tests/test_datalab_core_dtos.py tests/test_datalab_core_statistics.py tests/test_datalab_core_statistics_hypothesis.py tests/test_datalab_core_statistics_matrix.py tests/test_datalab_core_statistics_time_series.py tests/test_datalab_core_statistics_grouped.py tests/test_datalab_core_extrapolation.py tests/test_datalab_core_uncertainty.py tests/test_datalab_core_root_solving.py tests/test_datalab_core_fitting.py tests/test_datalab_core_parallel_options.py tests/test_datalab_core_workbench_model.py tests/test_core_no_qt_imports.py tests/test_phase0_precision_guardrails.py tests/test_phase0_adr_guardrails.py tests/test_release_test_matrix.py tests/test_release_import_hygiene.py tests/test_release_artifact_sizes.py tests/test_update_checker.py tests/test_packaging_qt_excludes.py tests/test_webengine_measurement_evidence.py tests/test_webengine_asset_evidence_tool.py tests/test_webengine_shipping_import_guard.py tests/test_webengine_spike_assets.py tests/test_webengine_spike_contract.py tests/test_webengine_spike_report.py tests/test_webengine_evidence_bundle_tool.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_root_solving_batch.py tests/test_root_solving_expression.py tests/test_root_solving_formatting.py tests/test_root_solving_normalization.py tests/test_root_solving_plotting.py tests/test_root_solving_solver.py tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_latex_writer.py tests/test_r10_c4_findroot_convergence_args.py tests/test_uncertainty_auto_digits.py tests/test_uncertainty_formatter_overflow.py tests/test_shared_uncertainty.py tests/test_error_propagation_latex_display_precision.py tests/test_extrapolation_latex_display_precision.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_error_propagation_higher_order_and_mc.py tests/test_error_propagation_mathematica_reference.py tests/test_error_propagation_method_aliases.py tests/test_error_propagation_second_order_reference.py tests/test_error_propagation_symbolic_derivative.py tests/test_extrapolation_accelerators.py tests/test_extrapolation_high_precision_convergence.py tests/test_extrapolation_mathematica_reference.py tests/test_extrapolation_power_law.py tests/test_statistics_mathematica_reference.py tests/test_statistics_modes_and_flags.py tests/test_statistics_weighted.py tests/test_special_functions_mathematica_reference.py tests/test_units_integration.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_fit_custom_model_same_as_extrapolation.py tests/test_fit_statistics.py tests/test_fitting_input_normalization.py tests/test_fitting_linear_model_sanity.py tests/test_fitting_markdown_display.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py tests/test_fitting_runner_scipy_fallback.py tests/test_fitting_scipy_reference.py tests/test_implicit_d8_runner_regression.py tests/test_implicit_fit_worker_cancellation.py tests/test_mcmc_fitter.py tests/test_mcmc_gui_wiring.py tests/test_mcmc_pre_flight_health.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_parallel_backend.py tests/test_parallel_config.py tests/test_parallel_preferences.py tests/test_sampling_cache.py tests/test_sampling_parallel.py tests/test_safe_eval_ast_nodes_limit.py tests/test_safe_eval_security.py tests/test_symbolic_export.py tests/test_symbolic_math.py tests/test_render_fit_cache.py tests/test_r10_c3_plot_fitting_precision_guard.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_cancellation_and_timeout.py tests/test_auto_fit_removed.py tests/test_bilingual_errors_extrapolation_methods.py tests/test_desktop_custom_fit_ui.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_io.py tests/test_workspace_legacy_fixtures.py tests/test_workspace_auto_fit_migration.py tests/test_workspace_implicit_round_trip.py tests/test_desktop_example_workspace_menu.py tests/test_example_workspaces.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_multiprocessing_entrypoint.py tests/test_gui_shim_exports.py tests/test_safe_read_text_encodings.py tests/test_desktop_workspace_entrypoint.py tests/test_desktop_workspace_menu.py tests/test_desktop_examples_entrypoint.py tests/test_docs_sanity.py tests/test_desktop_docs_smoke.py tests/test_doc_slug_validation.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_app_desktop_bridge_qt.py tests/test_app_desktop_workers_core.py tests/test_phase0_desktop_guardrails.py tests/test_update_controller.py tests/test_app_web_baseline_contracts.py tests/test_app_web_docs_baseline.py tests/test_app_web_route_inventory.py tests/test_app_web_fitting_uncertainty.py tests/test_app_web_sse_baseline.py tests/test_app_web_formula_resources_baseline.py tests/test_app_web_precision_concurrency.py tests/test_web_api_smoke.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_update_payload.py tests/test_update_signing.py tests/test_generate_updates_manifest.py tests/test_update_installer.py tests/test_update_packaging_scripts.py tests/test_update_payload_progress.py tests/test_update_download_worker.py tests/test_update_progress_dialog.py tests/test_update_dialogs.py tests/test_update_preferences.py tests/test_desktop_update_menu.py tests/test_pyinstaller_spec_paths.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_app_icon_asset.py tests/test_implicit_packaging.py tests/test_macos_icon_packaging.py tests/test_macos_icon_preparation.py tests/test_mcmc_packaging_declarations.py tests/test_workspace_file_association_packaging.py
pytest -q tests/test_web_sse_streaming.py tests/test_web_sse_fit_endpoint.py tests/test_openapi_spec.py tests/test_web_theme_toggle.py tests/test_web_plot_generation.py
pytest -q tests/test_web_server_startup_smoke.py tests/test_r10_c2_secret_key_not_hardcoded.py tests/test_security_get_config_value_no_app_context.py app_web/test_security.py
pytest -q tests/test_collaborate_session.py tests/test_collab_integration.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
QT_QPA_PLATFORM=offscreen pytest -q
```

Formula renderer value-gate evidence remains informational while WebEngine is
`NO_GO`; keep it outside the mandatory release-gate command block:

```bash
QT_QPA_PLATFORM=offscreen python tools/formula_renderer_value_gate.py --out build/formula-renderer-value-gate.json
```

The standalone GUI-style LaTeX option matrix remains deferred integration work
until `tests/test_latex_option_matrix.py` and `tools/latex_option_matrix.py`
are brought into tracked source control. Do not treat those untracked artifacts
as mandatory release-gate evidence in a clean checkout.

Build release artifacts after the local gate passes:

```bash
DATALAB_BUILD_PKG=1 ./build_mac_data_gui.sh
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_data_gui.ps1 -BuildInnoInstaller
```

After release artifacts exist, generate the signed update manifest. The
`DATALAB_UPDATE_SIGNING_PRIVATE_KEY_B64` secret must be present in the release
environment; do not use `--allow-unsigned-assets` for release builds.

```bash
python tools/generate_updates_manifest.py --version "$DATALAB_RELEASE_VERSION" --release-url "https://github.com/yilibinbin/DataLab/releases/tag/v$DATALAB_RELEASE_VERSION" --notes-file "$DATALAB_RELEASE_NOTES" --published-at "$DATALAB_RELEASE_PUBLISHED_AT" --min-client-version "$DATALAB_UPDATE_MIN_CLIENT_VERSION" --macos-pkg "dist/DataLab-$DATALAB_RELEASE_VERSION-macOS.pkg" --windows-exe "dist/DataLab-$DATALAB_RELEASE_VERSION-Windows-x64.exe" --output "dist/updates.json"
```

After macOS and Windows packaging complete, record artifact sizes for the
release notes and future WebEngine-size comparisons:

```bash
python tools/record_release_artifact_sizes.py --out build/release-artifact-sizes.json
python tools/webengine_evidence_bundle.py --artifact-manifest build/release-artifact-sizes.json --out-dir build/webengine-evidence
```

`record_release_artifact_sizes.py` fails if no release artifacts are found.
Do not use `--allow-empty` for release evidence; it is only a diagnostic escape
hatch for checking manifest formatting before packaging exists.

The bundle command writes `webengine-assets-template.json`,
`webengine-measurements.json`, and `webengine-spike-report.json` together. The
equivalent explicit commands are:

```bash
python tools/webengine_asset_evidence.py --template --out build/webengine-assets-template.json
python tools/webengine_spike_report.py --artifact-manifest build/release-artifact-sizes.json --asset-manifest build/webengine-assets-template.json --out build/webengine-spike-report.json
```

If a future isolated WebEngine spike records startup, memory, updater, CI, or
IME measurements, pass the validated measurement evidence manifest as well:

```bash
python tools/webengine_measurement_evidence.py --template --out build/webengine-measurements.json
python tools/webengine_spike_report.py --artifact-manifest build/release-artifact-sizes.json --asset-manifest build/webengine-assets-template.json --measurement-evidence build/webengine-measurements.json --out build/webengine-spike-report.json
```

The WebEngine spike report is intentionally `NO_GO` until every G6 security,
offline, measurement, packaging, CI, and platform gate has explicit evidence.
Shipping builds must continue to exclude QtWebEngine modules unless a future
isolated spike passes those gates and updates all packaging entry points in
lockstep.

The screenshot capture gate intentionally switches fitting and extrapolation
scenarios to their custom-expression submodes before grabbing the window. Those
submodes exercise the shared formula workbench panel; the schema scan remains
responsible for the broader default-mode coverage.

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
- P2.4 diagnostics:
  - Contribution helper and plot routing: `shared.error_contributions`, desktop worker wrappers, Web wrapper, and shared plot backend.
  - Semantic evidence: error semantic snapshot, contribution diagnostics, propagation metadata, cumulative contribution overlay rows, Taylor/Monte Carlo comparison rows, sensitivity rows, and Taylor-order comparison rows.
  - Monte Carlo distribution evidence: JSON-safe distribution summary/spec, shared renderer validation, desktop/Web collection gating, and visible distribution plot routing via row plot galleries.
  - Focused tests include `tests/test_datalab_core_uncertainty.py`, `tests/test_shared_error_propagation_engine.py`, `tests/test_app_desktop_workers_core.py`, `tests/test_app_web_precision_concurrency.py`, `tests/test_web_plot_generation.py`, and `tests/test_plotting_backend.py`.

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
- Core service boundary: `SessionService`, shared service factory, Qt bridge
  callback delivery, desktop/Web statistics adapters, and `mp.dps`
  restoration.
- LaTeX generation: `generate_statistics_latex` (via existing tests).
- Bootstrap confidence intervals:
  - Core deterministic seeded percentile Bootstrap uses
    `datalab_core.statistics_bootstrap.run_statistics_bootstrap()` through the
    statistics service branch and reuses the shared Monte Carlo distribution
    summary.
  - Desktop workflow controls, workspace capture/restore, semantic CSV/LaTeX,
    distribution plots, history comparison, report bundle plot attachments, and
    budget diagnostic-only extraction are covered by focused regression tests.
  - `examples/workspaces/statistics-bootstrap.datalab` is generated from
    `tools/generate_example_workspaces.py`, stores data directly, and verifies
    that the default seeded Bootstrap configuration can calculate.
- Hypothesis tests:
  - Core hypothesis-test execution uses
    `datalab_core.statistics_hypothesis.run_statistics_hypothesis()` through
    the statistics service branch. The first visible Desktop release covers
    one-sample t, paired t, Welch t, exact sign test, and chi-square
    goodness-of-fit.
  - Semantic snapshots embed the structured `hypothesis_test` payload as the
    authority. Text, CSV, LaTeX, history comparison, report bundle rendering,
    and workspace restore regenerate or validate against that payload instead
    of trusting stale rendered caches.
  - Desktop controls, workspace capture/restore, localized visibility rules,
    LaTeX export, history comparison, and diagnostic-only uncertainty-budget
    treatment are covered by focused regression tests.
  - `examples/workspaces/statistics-hypothesis.datalab` is generated from
    `tools/generate_example_workspaces.py`, stores data directly, and verifies
    that the default one-sample t-test configuration can calculate.
- Covariance / correlation matrix:
  - Core matrix execution uses
    `datalab_core.statistics_matrix.run_statistics_matrix()` through the
    statistics service branch with nullable raw table rows, selected value
    columns, listwise or pairwise missing-data policy, and sample/population
    denominator selection.
  - Semantic snapshots, long-form CSV, direct LaTeX export, Desktop workspace
    capture/restore, and reusable correlation heatmap rendering are covered by
    focused regression tests.
  - `examples/workspaces/statistics-matrix.datalab` is generated from
    `tools/generate_example_workspaces.py`, stores data directly, and verifies
    that the default covariance/correlation configuration can calculate.
- Grouped statistics:
  - Core grouped execution uses
    `datalab_core.statistics_grouped.run_statistics_grouped()` through the
    statistics service branch before scalar value parsing, preserving raw group
    labels, selected value columns, optional sigma-column override, and source
    row IDs.
  - Semantic snapshots, long-form CSV, direct LaTeX export, grouped mean
    overview plots, Desktop workspace capture/restore, history comparison, and
    report bundle CSV rendering are covered by focused regression tests.
  - `examples/workspaces/statistics-grouped.datalab` is generated from
    `tools/generate_example_workspaces.py`, stores data directly, and verifies
    that the default grouped weighted configuration can calculate.
- Time-series / rolling statistics:
  - Core time-series execution uses
    `datalab_core.statistics_time_series.run_statistics_time_series()` through
    the statistics service branch. The first visible workflow covers rolling
    mean, rolling median, rolling standard deviation, and EWMA.
  - Snapshot rendering, CSV, LaTeX, plots, history comparison, report bundle
    plot attachments, and diagnostic-only uncertainty-budget treatment are
    covered by focused regression tests.
  - Window alignment, `min_periods`, EWMA `alpha`/`span`, independent rolling
    mean sigma propagation, and uncertainty limitations are documented in the
    Desktop statistics docs.
  - `examples/workspaces/statistics-time-series-rolling.datalab` and
    `examples/workspaces/statistics-time-series-ewma.datalab` are generated
    from `tools/generate_example_workspaces.py`, store data directly, and
    verify that their default configurations can calculate.

### P0.1 Baseline Coverage Matrix

This baseline locks the current output surfaces before result schemas are
changed. It is not a feature list; P1/P2 statistics metrics stay out of this
matrix until their implementation slices.

| Current row | Locked current outputs |
| --- | --- |
| Arithmetic mean sample, population, and bare `mean` mode | `mean`, `std_mean`, `std`, `v_min`, `v_max`, row count, and `method_label`; core payload still exposes `min` / `max`, while legacy compute/display dictionaries still expose `v_min` / `v_max`. |
| Weighted normal case | Current weighted mean, `std_mean`, `std`, condition-specific `effective_n`, `dropped = 0`, and current warning behavior. |
| Weighted zero-sigma anchor | Current anchored mean, `std_mean = 0`, `std = 0`, condition-specific `zero_sigma_anchor`, `effective_n`, `dropped`, and explicit warning behavior. |
| Weighted dropped-row case | Dropped-row count, min/max over used rows only, and `ResultEnvelope.warnings` preservation through `statistics_payload_to_compute_result()`. |
| High-precision guard | `precision_guard` / worker precision boundaries preserve high-precision value text and restore global `mp.dps`. |

Current route coverage:

- Core round trip: `datalab_core.statistics_compute.compute_statistics()` ->
  `datalab_core.statistics.run_statistics()` ->
  `datalab_core.statistics.statistics_payload_to_compute_result()`.
- Desktop interactive statistics: `app_desktop.window_statistics_mixin.WindowStatisticsMixin._format_statistics_display()`,
  `_build_stats_csv_rows()` as a wrapper around
  `datalab_core.statistics.statistics_csv_rows_from_result()`,
  `_display_statistics_result()`, and `_render_statistics_plot()`.
- Desktop batch/core-envelope statistics: `app_desktop.workers_core._execute_calc_job()`
  builds requests with `build_statistics_requests()`, submits through
  `create_core_session_service()`, and projects payloads back with
  `statistics_payload_to_compute_result()`.
- Desktop projection path: `app_desktop.window_extrapolation_mixin.WindowExtrapolationMixin.run_calculation()`
  builds `CalcJob.core_request` with current mode/options when possible and
  keeps legacy worker validation authoritative when projection fails.
- Web statistics: `app_web.logic.statistics._run_statistics()` uses the core
  request/service/payload converter, then routes CSV through
  `datalab_core.statistics.statistics_csv_rows_from_result()` and formats plot,
  LaTeX, and optional PDF outputs.
- Statistics LaTeX: `statistics_utils.generate_statistics_latex()` and
  `statistics_utils.generate_statistics_latex_batches()` remain the current
  public writers for direct and batch statistics reports; their statistics
  summary rows come from
  `datalab_latex.latex_tables_common.build_statistics_latex_summary_rows()`.
- P0.1 self-contained statistics LaTeX evidence uses tracked tests such as
  `tests/test_latex_generation_consistency.py::test_statistics_latex` and
  `tests/test_latex_compile_e2e.py::test_latex_compile_e2e`. The broader
  `tests/test_latex_option_matrix.py` / `tools/latex_option_matrix.py`
  release-gate artifacts already referenced above are pre-existing untracked
  files in this worktree and must be included by the later integration commit;
  they are not the only P0.1 statistics LaTeX evidence.

Duplicated output paths to migrate in later slices:

- Statistics desktop CSV/plot helpers:
  `WindowStatisticsMixin._build_stats_csv_rows()` is now a shared CSV wrapper;
  `WindowStatisticsMixin._format_statistics_display()`,
  `WindowStatisticsMixin._render_statistics_plot()`,
  `WindowStatisticsMixin._display_statistics_result()`, and
  `WindowStatisticsMixin._display_statistics_batches()`.
- Fitting CSV and LaTeX wrappers:
  `WindowFittingFormattersMixin._build_fit_csv_rows()`,
  `WindowFittingFormattersMixin._latex_escape()`,
  `WindowFittingFormattersMixin._fit_latex_preamble()`, and
  `WindowFittingFormattersMixin._fit_latex_block()` wrapping
  `app_desktop.fitting_latex_writer`.
- Root diagnostics LaTeX wrapper:
  `WindowExtrapolationMixin._write_root_latex_if_requested()` wrapping
  `app_desktop.root_latex_writer.write_root_latex()`.
- Error contribution summaries and plots:
  `app_desktop.workers_core._build_contribution_summary()`,
  `app_desktop.workers_core._render_contribution_plot()`,
  `app_desktop.workers_core._aggregate_error_contributions()`, plus
  `app_desktop.workers_qt.CalcWorker._build_contribution_summary()`,
  `app_desktop.workers_qt.CalcWorker._render_contribution_plot()`, and
  `app_desktop.workers_qt.CalcWorker._aggregate_error_contributions()`.
- Web LaTeX/plot helpers duplicating desktop behavior:
  `app_web.logic.statistics._format_statistics_rows()`,
  `app_web.logic.statistics._run_statistics()`,
  `app_web.logic.fitting._generate_fitting_latex()`,
  `app_web.logic.extrapolation._render_latex()`,
  `app_web.logic.error_propagation._render_error_latex()`, and
  `app_web.logic.plots._render_statistics_plot()`,
  `_render_extrapolation_plot()`, `_render_contribution_plot()`.

Internal-only allowlist for this baseline:

- Legacy private desktop helpers named in this section may be asserted by
  P0.1 tests only to freeze current behavior before migration.
- No new P1/P2 statistics metrics, public result keys, GUI controls, or
  visible output behavior are allowed in P0.1.

### P0.5 Shared Statistics Serialization Routing

| Surface | Shared boundary | Adapter status | Focused evidence |
| --- | --- | --- | --- |
| Core statistics CSV | `datalab_core.statistics.statistics_csv_rows_from_analysis_rows()` | Source of truth for semantic `AnalysisRow` CSV rows, including warning diagnostics. | `tests/test_datalab_core_statistics.py::test_statistics_csv_serializer_consumes_semantic_rows_and_diagnostics` |
| Desktop statistics CSV | `datalab_core.statistics.statistics_csv_rows_from_result()` | `WindowStatisticsMixin._build_stats_csv_rows()` is a compatibility wrapper that keeps `batch,metric,value,uncertainty` headers. | `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| Web statistics CSV | `datalab_core.statistics.statistics_csv_rows_from_result()` | `app_web.logic.statistics._format_statistics_rows()` is a compatibility wrapper that keeps `metric,value,uncertainty` headers. | `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| Statistics LaTeX summaries and diagnostics | `datalab_latex.latex_tables_common.build_statistics_latex_summary_rows()` / `build_statistics_latex_diagnostic_rows()` | `statistics_utils.generate_statistics_latex*()` remain public compatibility APIs, preserve `latex_group_size=0`, and render current warning diagnostics as compile-safe summary rows. | `tests/test_latex_generation_consistency.py::test_statistics_latex_group_size_zero_keeps_no_grouping_setup_and_diagnostic_row`; `tests/test_latex_compile_e2e.py::test_statistics_latex_zero_sigma_diagnostics_compile_dcolumn_and_siunitx`; `tests/test_latex_compile_e2e.py::test_statistics_latex_options_compile_with_all_discovered_local_engines` covers dcolumn, siunitx-mode, grouping size, diagnostics, and every discovered `compile_latex_safe()` engine (`pdflatex`, `xelatex`, `lualatex`) for English statistics reports; CJK caption compile coverage is limited to XeLaTeX in this tracked P0.5 gate. |

The standalone all-module GUI-style option matrix remains deferred and
non-gated until `tests/test_latex_option_matrix.py` and
`tools/latex_option_matrix.py` are tracked; P0.5 mandatory evidence above is
limited to tracked tests.

### P0.6A Shared Statistics Plot Routing

| Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Existing statistics mean/error-band plot | Current statistics result dictionaries from `compute_statistics()` / `run_statistics()` adapters | Minimal `StatisticsPlotSpec` for point-index x-axis, values, optional error bars, mean line, optional mean±SE band, localized labels/title, and batch suffix; no histogram/box/QQ/weighted-residual fields in P0.6A | `WindowStatisticsMixin._render_statistics_plot()` remains the compatibility wrapper and calls the shared renderer | `app_web.logic.plots._render_statistics_plot()` remains the compatibility wrapper and calls the shared renderer | No CSV/LaTeX behavior change; plot metadata/captions are deferred | Shared render-from-spec helper using `shared.plotting` Agg backend and `apply_cjk_font()` | No workspace/example behavior change in this sub-slice | Internal routing matrix only; visible plot docs unchanged | Shared spec conversion/render tests, desktop direct wrapper, desktop worker wrapper, web wrapper, CJK/backend safety, and existing plotting backend tests |

### P1.6 Statistics Plot Gallery

| Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Statistics histogram, box, QQ, and weighted-residual plots | Current statistics result dictionaries from `compute_statistics()` / `run_statistics()` adapters; no calculation changes | `StatisticsPlotSpec.plot_key` now covers `statistics.series_with_mean`, `statistics.histogram`, `statistics.box`, `statistics.qq`, and `statistics.weighted_residual`; plot-only annotations do not change statistics CSV/LaTeX rows | Existing global `Generate plots` control routes through `WindowStatisticsMixin._render_statistics_plots()` and saves the gallery into the existing stats image list; `_render_statistics_plot()` remains a single-plot compatibility shim | Existing `stats_generate_plots` control routes through `app_web.logic.plots._render_statistics_plots()`; `plot_b64` remains the first image and `plot_b64_list` carries the gallery | No CSV/LaTeX behavior change | Shared render-from-spec helpers in `shared.plotting` using Agg backend and `apply_cjk_font()` for each plot key | Workspace plot-key persistence is unchanged in this slice; no example change | Visible behavior change is covered by this matrix row; no separate user guide copy changed | `tests/test_plotting_backend.py::test_statistics_plot_specs_cover_p1_6_gallery_and_render_png_bytes`; `tests/test_phase0_desktop_guardrails.py::test_statistics_display_result_routes_current_csv_plot_and_snapshot`; `tests/test_app_desktop_workers_core.py::test_statistics_worker_plot_gallery_routes_shared_specs`; `tests/test_web_plot_generation.py::test_web_statistics_plot_gallery_routes_shared_specs`; `tests/test_app_web_precision_concurrency.py::test_web_statistics_generate_plots_returns_gallery` |

### P0.6B Shared Error Contribution Plot Routing

| Feature family | Core producer | Core payload/schema | Desktop surface | Web surface | LaTeX/report surface | Plot surface | Workspace/examples | Docs | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Existing error-propagation contribution bar plot | Current uncertainty result `contributions` maps and existing contribution summary rows | Minimal `ErrorContributionPlotSpec` for current summary labels, percent bars, localized x-axis/title, optional title suffix, existing percent text labels, and no cumulative/diagnostic/`plot_only` fields in P0.6B | `app_desktop.workers_core._render_contribution_plot()` and `app_desktop.workers_qt.CalcWorker._render_contribution_plot()` remain compatibility wrappers and call the shared renderer | `app_web.logic.plots._render_contribution_plot()` keeps aggregating `result.contributions` locally, then calls the shared renderer | No CSV/LaTeX/result-schema behavior change; contribution summaries stay in existing payload rows | Shared render-from-spec helper using `shared.plotting` Agg backend and `apply_cjk_font()` | No workspace/example behavior change in this sub-slice | Internal routing matrix only; visible plot docs unchanged | Shared spec/render PNG tests, desktop core wrapper, Qt worker wrapper, web wrapper, CJK/backend safety, and existing contribution plot tests |

### P0.6C Plot Annotation Serialization Boundary

P0.6 uses `AnalysisRow.render_group="plot_annotation"` for plot-only visual
annotations. These rows are allowed to carry plot labels/messages for renderer
metadata, but they are excluded from regenerated text, statistics CSV rows, and
statistics LaTeX diagnostic/summary rows. Warning and diagnostic rows with
non-plot render groups remain serialized.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Statistics text snapshots | `datalab_core.statistics.render_statistics_snapshot_outputs()` renders only `metric_rows`, `row_flags`, and `diagnostic_rows`; `plot_annotation` rows are not a text row source. | P0.6C boundary note plus snapshot grouping contract from P0.4/P0.5. |
| Statistics CSV | `datalab_core.statistics.statistics_csv_rows_from_analysis_rows()` skips `render_group="plot_annotation"` before warning/diagnostic emission, while preserving warning diagnostics. | `tests/test_datalab_core_statistics.py::test_statistics_csv_serializer_consumes_semantic_rows_and_diagnostics` |
| Statistics LaTeX summaries and diagnostics | `datalab_latex.latex_tables_common.build_statistics_latex_diagnostic_rows()` skips `render_group="plot_annotation"` before warning emission; `build_statistics_latex_summary_rows()` inherits that diagnostic boundary. | `tests/test_latex_generation_consistency.py::test_statistics_latex_summary_rows_include_warning_diagnostics` |

### P0.7 Fit Statistics Consolidation Routing

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Single-fit official metrics | `fitting.statistics.compute_fit_statistics()` is the single source for chi-square, reduced chi-square, AIC, BIC, R², RMSE, and dof in ordinary single-fit producers. `fitting.hp_fitter._compute_statistics()`, the SciPy direct path, `fitting.implicit_model._solve_observed_linear_least_squares()`, and `fitting.auto_models.fit_linear_model()` route through it. | `tests/test_fit_statistics.py::test_auto_linear_model_uses_shared_fit_statistics`; `tests/test_fit_statistics.py::test_observed_implicit_linear_model_uses_shared_fit_statistics`; existing helper contract tests in `tests/test_fit_statistics.py` |
| Desktop markdown display | Desktop fitting display consumes metrics from `FitResult` fields and does not recompute from residuals. | `tests/test_fitting_markdown_display.py::test_fit_text_reads_sentinel_metrics_from_fit_result` |
| Desktop fitting LaTeX | Desktop fitting LaTeX consumes metrics from `FitResult` fields and does not recompute from residuals. | `tests/test_fitting_latex_writer.py::test_build_fit_latex_block_reads_sentinel_metrics_from_fit_result` |
| Web fitting adapters | Web fitting deserializes the core `FitResult` payload, then formats the metric fields for bundle metrics, CSV, and LaTeX. | `tests/test_app_web_fitting_latex.py::test_run_fit_uses_sentinel_fit_result_metrics` |
| Model comparison blocker | `fitting.model_selector._sequence_model()` remains outside P0.7 because it is a sequence-acceleration/model-selection producer with `dof=max(1, n-1)`. Model comparison must wait for a scoped multi-fit producer or orchestrator that returns comparable `FitResult`s from existing single-fit producers and consumes their stored metrics. | Documentation-only blocker for P0.7; no model-comparison table is implemented in this slice. |

### P2.2A Model Comparison Core

P2.2A adds the UI-neutral core for explicit selected-fit comparison only.
Desktop, Web, LaTeX, workspace snapshots, and comparison plots remain deferred
until their own P2.2 surface slices. The core comparison path must not revive
automatic model selection or infer a winner.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Explicit comparison orchestrator | `fitting.model_comparison.compare_selected_fits()` accepts a user-ordered candidate list, runs one existing single-fit producer per candidate, records success and failure rows without aborting the batch, and emits no `best_model`, winner, recommendation, or highlight field. | `tests/test_fit_model_comparison.py` |
| Stored metric consumption | P2.2A comparison rows copy `FitResult.chi2`, `FitResult.reduced_chi2`, `FitResult.aic`, `FitResult.bic`, `FitResult.rmse`, and `FitResult.r2` directly. `free_parameter_count` comes from explicit candidate/model metadata or the same custom-expression parameter inference used by `FitRunner`, not `len(FitResult.params)`. | `tests/test_fit_model_comparison.py::test_compare_selected_fits_reads_stored_metrics_without_recomputing`; `tests/test_fit_model_comparison.py::test_compare_selected_fits_can_use_explicit_runner_for_custom_problem`; `tests/test_fit_model_comparison.py::test_runner_candidate_infers_free_parameters_from_custom_expression`; `tests/test_fit_model_comparison.py::test_runner_candidate_excludes_dependent_parameters_from_free_count` |
| Auto-fit removal guardrail | The P2.2A core does not call or reference `auto_fit_dataset()`, `_sequence_model()`, `fitting.model_selector.AUTO_MODELS`, or `fitting.auto_models.AUTO_MODELS`. Public auto-fit removal and workspace migration guardrails stay mandatory. | `tests/test_fit_model_comparison.py::test_compare_selected_fits_does_not_reference_auto_fit_model_selection`; `tests/test_auto_fit_removed.py`; `tests/test_workspace_auto_fit_migration.py` |
| Shared comparison rows | `fitting.comparison_formatting.build_comparison_table_rows()` turns comparison rows into stable table/CSV-style dictionaries with candidate id, order, status, official metrics, warnings, and errors. It does not compute fit statistics. | `tests/test_fit_model_comparison.py::test_comparison_formatting_builds_shared_rows_from_comparison_result` |

### P2.2B Model Comparison Core Payload Service

P2.2B adds a UI-neutral payload service for selected-fit comparison. It is not
yet wired to Desktop, Web, LaTeX, workspace restore, or plot overlays.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core request normalization | `datalab_core.fitting_comparison.build_fitting_comparison_request()` accepts explicit selected candidates and normalizes shared data, sigma, weights, parameters, and constants through the existing fitting request boundary. | `tests/test_fit_comparison_core_payload.py::test_build_fitting_comparison_request_normalizes_json_safe_payload` |
| Core comparison payload | `datalab_core.fitting_comparison.run_fitting_comparison()` converts normalized candidate payloads into P2.2A candidates, runs the comparison core, and emits JSON-safe rows plus serialized per-candidate `FitResult` payloads. | `tests/test_fit_comparison_core_payload.py::test_run_fitting_comparison_returns_rows_and_serialized_fit_results` |
| Candidate failure rows | Candidate-level fitting, construction, and metadata failures remain row-local and do not abort successful later candidates. Candidate-specific validation is deferred from request construction into the per-candidate runtime loop. | `tests/test_fit_comparison_core_payload.py::test_run_fitting_comparison_keeps_candidate_failures_as_rows`; `tests/test_fit_comparison_core_payload.py::test_run_fitting_comparison_keeps_candidate_construction_failures_as_rows`; `tests/test_fit_comparison_core_payload.py::test_build_request_defers_candidate_metadata_failures_to_result_rows` |
| Stored metric serialization | P2.2B serializes row metrics and per-candidate `FitResult`s from the P2.2A result; it does not recompute official fit statistics. | `tests/test_fit_comparison_core_payload.py::test_run_fitting_comparison_serializes_sentinel_metrics` |
| Auto-fit removal guardrail | The P2.2B payload service does not import or reference `auto_fit_dataset()`, `_sequence_model()`, `AUTO_MODELS`, or winner-selection semantics. | `tests/test_fit_comparison_core_payload.py::test_fitting_comparison_core_does_not_import_auto_fit_selection`; `tests/test_auto_fit_removed.py`; `tests/test_workspace_auto_fit_migration.py` |

### P2.2C Model Comparison Shared CSV/LaTeX Boundary

P2.2C adds a non-UI output formatting boundary for selected-fit comparison
rows. It still does not expose Desktop/Web controls, workspace restore, or plot
overlays.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Shared CSV/table headers | `fitting.comparison_formatting.COMPARISON_TABLE_HEADERS` defines the stable comparison row order for later visible tables and CSV export. | `tests/test_fit_model_comparison.py::test_comparison_formatting_builds_payload_rows_and_headers` |
| Payload row formatting | `fitting.comparison_formatting.build_comparison_table_rows_from_payload()` formats P2.2B JSON-safe payload rows without recomputing metrics. | `tests/test_fit_model_comparison.py::test_comparison_formatting_builds_payload_rows_and_headers` |
| Shared LaTeX comparison block | `datalab_latex.latex_tables_fitting.build_fitting_comparison_latex_block()` consumes the shared comparison rows and emits an evidence-only table with no winner/best language. | `tests/test_fit_model_comparison.py::test_fitting_comparison_latex_block_uses_shared_rows_without_winner_language` |

### P2.2D Model Comparison Semantic Snapshot Boundary

P2.2D adds the non-UI workspace semantic snapshot boundary for selected-fit
comparison. It does not add Desktop/Web controls, comparison plots, public docs,
or automatic model selection. Future adapters can opt in by storing a
`fitting_comparison` payload in the existing result-payload cache.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Semantic snapshot | `datalab_core.fitting_comparison.build_fitting_comparison_result_snapshot()` persists compact comparison rows plus selected serialized entries from the P2.2B payload. It does not recompute official metrics and does not emit winner/best language. | `tests/test_fit_comparison_core_payload.py::test_fitting_comparison_snapshot_round_trips_rows_without_winner_language` |
| Deterministic restore outputs | `datalab_core.fitting_comparison.render_fitting_comparison_snapshot_outputs()` regenerates text and CSV rows from the semantic snapshot through the P2.2C shared row order. Rendered markdown/CSV caches remain non-authoritative. | `tests/test_fit_comparison_core_payload.py::test_fitting_comparison_snapshot_round_trips_rows_without_winner_language` |
| Workspace dispatch | `app_desktop.workspace_controller` captures/restores fitting-comparison semantic snapshots only for `fitting_comparison` payloads or restored snapshots, preserving the existing statistics snapshot path and cache-only LaTeX behavior. | `tests/test_workspace_controller.py::test_workspace_restores_fitting_comparison_rows_from_semantic_snapshot` |

### P2.2E Desktop Fitting-Comparison Result Cache Adapter

P2.2E adds a narrow Desktop adapter for result-cache refresh only. It does not
add selected-fit controls, Web routes, plot overlays, public docs, or automatic
model selection.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Desktop result refresh | `ExtrapolationWindow._refresh_display_format()` handles `fitting_comparison` payloads by building the P2.2D semantic snapshot and reusing `render_fitting_comparison_snapshot_outputs()` for Markdown text and CSV rows. | `tests/test_workspace_controller.py::test_desktop_refresh_display_formats_fitting_comparison_payload` |
| CSV order and filename | Desktop comparison CSV uses `COMPARISON_TABLE_HEADERS` and a fitting-comparison filename suggestion. | `tests/test_workspace_controller.py::test_desktop_refresh_display_formats_fitting_comparison_payload` |

### P2.2F Web Explicit Comparison Payload Adapter

P2.2F adds a narrow Web logic adapter for programmatic selected-fit comparison
posts. It does not add visible template controls, automatic candidate
generation, model-selection recommendations, comparison plots, examples, or
release packaging.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Web explicit comparison route | `app_web.logic.fitting._run_fit()` accepts `fit_mode=comparison` with explicit `fit_comparison_candidates` JSON and routes through `build_fitting_comparison_request()` plus `run_fitting_comparison()`. Missing or malformed candidates fail before ordinary single-fit mode handling. | `tests/test_app_web_fitting_latex.py::test_run_fit_comparison_mode_returns_shared_summary_csv_and_latex`; `tests/test_app_web_fitting_latex.py::test_run_fit_comparison_mode_requires_explicit_candidates` |
| Shared Web outputs | Web comparison summary/CSV are rendered from the P2.2D semantic snapshot renderer and CSV headers; LaTeX uses the P2.2C shared comparison table block. The returned bundle leaves ordinary single-fit params/metrics empty and emits no winner/best-model semantics. | `tests/test_app_web_fitting_latex.py::test_run_fit_comparison_mode_returns_shared_summary_csv_and_latex` |

### P2.2G Web Visible Selected-Fit Comparison Form

P2.2G exposes the existing Web comparison adapter through a visible explicit
form mode. It still does not generate candidates automatically, choose a
winner, add recommendations, expose Desktop controls, or add comparison plots.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Visible Web comparison mode | `app_web/templates/fit.html` exposes `fit_mode=comparison` and an explicit JSON textarea named `fit_comparison_candidates`. Public auto-fit removal guardrails stay green. | `tests/test_auto_fit_removed.py::test_web_fitting_template_exposes_only_explicit_supported_choices` |
| Comparison-specific result table | Web comparison results render `FitResultBundle.comparison_rows` in a comparison table and hide ordinary single-fit parameter/metric cards. | `tests/test_app_web_baseline_contracts.py::test_web_post_fit_route_renders_comparison_table_without_single_fit_cards` |

### P2.2I Desktop Explicit Selected-Fit Comparison Entry

P2.2I exposes selected-fit comparison in Desktop through an explicit JSON
candidate list. It reuses the P2.2B core payload service, P2.2D snapshot
renderer, and P2.2C LaTeX table block; it does not add automatic candidate
generation, recommendations, winner/best labels, or plot overlays.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Visible Desktop comparison mode | `app_desktop.views.fitting.build_fitting_mode_view()` exposes a `comparison` fit model and an explicit candidates JSON editor. Public auto-fit removal guardrails stay green. | `tests/test_auto_fit_removed.py::test_fitting_model_combo_contains_only_supported_explicit_models`; `tests/test_desktop_custom_fit_ui.py::test_desktop_comparison_mode_shows_explicit_candidates_editor` |
| Desktop run and exports | `WindowFittingModelsMixin._run_fitting_mode()` dispatches comparison mode through `build_fitting_comparison_request()` and a comparison worker; `WindowFittingResidualsMixin._on_fitting_comparison_finished()` renders text/CSV through the P2.2D snapshot renderer and LaTeX through `build_fitting_comparison_latex_block()`. | `tests/test_desktop_gui_workflows.py::test_fitting_click_workflow_selected_comparison` |
| Workspace persistence | `app_desktop.workspace_controller` persists and restores Desktop comparison candidate JSON under `config.fitting.comparison_candidates`. | `tests/test_workspace_controller.py::test_workspace_preserves_desktop_fitting_comparison_candidates` |

### P2.2J Desktop Selected-Fit Comparison Documentation

P2.2J documents the existing Desktop selected-fit comparison entry. The guide
uses explicit selected-fit comparison wording, covers the candidate JSON shape,
the supported `polynomial`, `inverse_power`, and `custom` families, comparison
table/CSV/LaTeX outputs, and workspace persistence of
`config.fitting.comparison_candidates`.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Desktop fitting guide | `docs/desktop/fitting.en.md` and `docs/desktop/fitting.zh.md` describe the explicit comparison workflow and avoid automatic-selection, winner, or recommendation language. | `tests/test_auto_fit_removed.py::test_desktop_fitting_docs_describe_explicit_selected_fit_comparison`; `tests/test_auto_fit_removed.py::test_docs_do_not_advertise_automatic_fitting_as_current_feature` |

### P2.3A Shared Root LaTeX Boundary

P2.3A moves root-solving LaTeX document/table generation into a Qt-free shared
module. It does not add root diagnostics, root classification, plot behavior,
workspace snapshots, examples, or Web routing.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Root LaTeX document builder | `datalab_latex.latex_tables_root.build_root_latex_document()` owns the existing root numeric table generation, including dcolumn/siunitx column selection, localized headers, group-size handling, caption escaping, and uncertainty display. | `tests/test_root_latex_writer.py::test_shared_root_latex_builder_matches_desktop_wrapper`; existing root LaTeX formatting tests in `tests/test_root_latex_writer.py` |
| Desktop compatibility adapter | `app_desktop.root_latex_writer.write_root_latex()` still writes files for existing desktop callers and re-exports `build_root_latex_document()` from the shared module. | `tests/test_root_latex_writer.py::test_shared_root_latex_builder_matches_desktop_wrapper` |
| Import boundary | The shared root LaTeX module does not import `app_desktop`, Qt, or PySide. | `tests/test_root_latex_writer.py::test_shared_root_latex_module_is_qt_free` |

### P2.3B Root Semantic Snapshot Boundary

P2.3B stores the serialized `RootBatchResult` payload plus compute/display settings as
the authoritative root result snapshot. Rendered markdown, CSV, plots, and
LaTeX remain cache fields; workspace restore regenerates root text/CSV from the
semantic batch payload when rendered caches are missing.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core root snapshot | `datalab_core.root_solving.build_root_result_snapshot()` stores `family="root_solving"`, schema `datalab.result_snapshot.root_solving`, serialized `batch`, display settings, source counts, warnings, precision, and cache compatibility metadata. Root payload `compute_digits` overrides the current UI precision when present, so build/render both rehydrate the batch under the persisted compute precision before calling `root_solving.formatting.render_root_batch_result()`. | `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_renders_from_semantic_batch_payload`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_deserializes_batch_under_snapshot_precision`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_build_deserializes_metadata_under_snapshot_precision` |
| Desktop worker payload | `_execute_root_solving_job_payload()` includes JSON-safe `batch`, `compute_digits`, `display_digits`, `uncertainty_digits`, and `language` for both core-service and legacy direct root solving paths while preserving existing markdown/CSV/raw rows/log/warnings behavior. Core-service batch deserialization, direct-path semantic batch serialization, Markdown/CSV rendering, and raw-row serialization use `precision_used` / `compute_digits`, not ambient `mp.dps` or a stale job precision. | `tests/test_app_desktop_workers_core.py::test_execute_root_solving_job_payload_uses_core_service_when_request_available`; `tests/test_app_desktop_workers_core.py::test_execute_root_solving_job_payload_core_service_deserializes_under_precision_used`; `tests/test_app_desktop_workers_core.py::test_execute_root_solving_job_payload_formats_under_job_precision`; `tests/test_app_desktop_workers_core.py::test_execute_root_solving_job_payload_returns_markdown_csv_and_log` |
| Workspace restore | `app_desktop.workspace_controller` captures/restores `root_solving` semantic snapshots and regenerates root text/CSV from the semantic batch payload when rendered markdown/CSV caches are blank. Root LaTeX remains cache-only in this slice, and restored high-precision roots keep the payload compute precision even if the UI precision control changed before saving. | `tests/test_workspace_controller.py::test_workspace_restores_root_rows_from_semantic_snapshot`; `tests/test_workspace_controller.py::test_workspace_root_semantic_snapshot_uses_payload_compute_precision_after_ui_precision_change` |

### P2.3C Root Classification Tags

P2.3C attaches per-root classification tags to root results without changing
root values or the `RootValue` dataclass. Tags live in
`RootResult.details["root_classification_tags"]` keyed by root index and render
through the existing root Markdown/CSV formatter.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Solver tag producer | `root_solving.solver` classifies `scan_multiple` roots as `bracketed_sign_change`, `suspected_tangent_or_repeated`, `boundary`, or `unclassified` using the scan residual tolerance, configured scan step, and cluster tolerance. Polynomial non-real complex roots are tagged `complex`; ordinary real polynomial roots are `unclassified`. | `tests/test_root_solving_solver.py::test_scan_multiple_classifies_sign_change_root`; `tests/test_root_solving_solver.py::test_scan_multiple_classifies_even_multiplicity_root_as_suspected_tangent`; `tests/test_root_solving_solver.py::test_scan_multiple_classifies_boundary_root`; `tests/test_root_solving_solver.py::test_scan_multiple_zero_delta_finite_difference_guard_is_not_tangent`; `tests/test_root_solving_solver.py::test_scan_multiple_center_sample_root_merged_with_minimum_is_unclassified`; `tests/test_root_solving_solver.py::test_high_precision_polynomial_complex_roots_remain_finite` |
| Text and CSV rendering | `root_solving.formatting.render_root_result()` and `render_root_batch_result()` include a `classification_tags` column for single and batch rows, keep failure rows, and render tags in stable order: `complex`, `bracketed_sign_change`, `suspected_tangent_or_repeated`, `boundary`, `unclassified`. | `tests/test_root_solving_formatting.py::test_render_complex_polynomial_roots_as_a_plus_b_i_without_uncertainty`; `tests/test_root_solving_formatting.py::test_render_scan_multiple_flattens_roots_to_csv_rows`; `tests/test_root_solving_formatting.py::test_render_row_failure_as_one_csv_row` |
| Semantic snapshot preservation | P2.3B's serialized root batch payload preserves `RootResult.details`, so root classification tags survive snapshot build/render without a new snapshot schema. | `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_deserializes_batch_under_snapshot_precision` |

### P2.3D Root Semantic Diagnostic Rows

P2.3D adds UI-neutral `AnalysisRow` diagnostics for root solving without
changing Markdown/CSV rendering, solver algorithms, LaTeX, plots, or Desktop/Web
surfaces.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core root payload rows | `datalab_core.root_solving.run_root_solving()` includes JSON-safe `payload["analysis_rows"]` derived from `RootBatchResult`, with metric rows for input/root counts and diagnostic rows for requested/resolved mode, backend, residual norm, and available classification tags. | `tests/test_datalab_core_root_solving.py::test_core_root_solving_handler_runs_scalar_batch_request` |
| Root semantic snapshot row groups | `build_root_result_snapshot()` writes top-level `metric_rows`, `diagnostic_rows`, and `row_flags`, accepting only canonical root rows that match the serialized batch and rebuilding from the batch for legacy, invalid, foreign, or malformed root-like payload rows. | `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_renders_from_semantic_batch_payload`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_rebuilds_analysis_rows_from_legacy_batch_payload`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_rebuilds_foreign_valid_analysis_rows`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_rebuilds_malformed_root_like_analysis_rows` |
| Failure, warning, and JSON-safety rows | `root_analysis_rows_from_batch()` emits row-flag rows for failed inputs, batch warnings, row warnings, and result warnings while keeping high-precision numeric diagnostics as strings, stable warning `message_key` values, and rejecting JSON float leakage through the existing `AnalysisRow` contract. | `tests/test_datalab_core_root_solving.py::test_root_analysis_rows_include_failure_and_warning_flags_without_json_floats`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_rebuilds_warning_rows_with_unstable_message_keys` |

### P2.3E Root Solver Quality Diagnostic Details

P2.3E adds success-only solver quality metadata to `RootResult.details` and
maps it to UI-neutral diagnostic `AnalysisRow` records. It does not change root
values, tolerances, fallback behavior, Markdown/CSV rendering, LaTeX, plots,
Desktop/Web UI, examples, packaging, or release artifacts.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Solver quality metadata | `root_solving.solver` records `solver_status="converged"`, string initial/bracket summaries, real SciPy iteration/function-evaluation counts when available, scan bounds/count summaries, and system per-equation residual strings only after successful candidate validation. | `tests/test_root_solving_solver.py::test_scalar_bracketed_scipy_solves_quadratic_root`; `tests/test_root_solving_solver.py::test_square_system_scipy_solve_records_finite_residual_norm`; `tests/test_root_solving_solver.py::test_scan_multiple_finds_scalar_roots_in_range` |
| Core diagnostic rows and snapshots | `datalab_core.root_solving.root_analysis_rows_from_batch()` maps quality metadata into stable diagnostic rows and `build_root_result_snapshot()` keeps P2.3D canonical row rebuild behavior from the serialized batch. | `tests/test_datalab_core_root_solving.py::test_core_root_solving_handler_runs_scalar_batch_request`; `tests/test_datalab_core_root_solving.py::test_core_root_snapshot_renders_from_semantic_batch_payload`; `tests/test_datalab_core_root_solving.py::test_root_analysis_rows_include_quality_diagnostics_without_json_floats`; `tests/test_datalab_core_root_solving.py::test_root_analysis_rows_include_scan_summary_in_payload_and_snapshot_without_json_floats` |

### P2.3F Root System Jacobian Condition Diagnostic

P2.3F adds a best-effort Jacobian condition estimate for successful system
root solves. It uses the existing derivative and result serialization paths,
does not change root values, tolerances, fallback behavior, Markdown/CSV
rendering, LaTeX, plots, Desktop/Web UI, examples, packaging, or release
artifacts.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| System condition producer | `root_solving.solver` builds the square system Jacobian at the accepted solution with `RootExpressionSystem.derivative_unknown()` and records a finite non-negative `RootResult.jacobian_condition` only when `mp.cond()` succeeds. | `tests/test_root_solving_solver.py::test_square_system_scipy_solve_records_finite_residual_norm`; `tests/test_root_solving_solver.py::test_high_precision_system_records_mpmath_jacobian_condition` |
| Core diagnostic rows and snapshots | `datalab_core.root_solving.root_analysis_rows_from_batch()` maps `RootResult.jacobian_condition` into the stable `jacobian_condition.{row}` diagnostic row as a string value, and semantic snapshots rebuild that row from the serialized batch without JSON float leakage. | `tests/test_datalab_core_root_solving.py::test_root_analysis_rows_include_quality_diagnostics_without_json_floats` |

### P2.3G Root Scan Accepted Evidence Diagnostics

P2.3G records evidence for accepted `scan_multiple` roots only. It preserves
scan sampling, refinement, validation, tolerances, root values, ordering,
Markdown/CSV rendering, LaTeX, plots, Desktop/Web UI, examples, packaging, and
release artifacts.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Accepted scan evidence producer | `root_solving.solver` carries accepted root evidence through scan candidate creation, deduplication, boundary tagging, and truncation as `RootResult.details["scan_root_evidence"]`. Sign-change evidence stores bracket endpoints and endpoint values as strings; exact-sample evidence stores the sample as a string; local-minimum evidence stores its enclosing interval as strings; duplicate candidate merges record an integer `merged_candidates` count without changing the representative root value. | `tests/test_root_solving_solver.py::test_scan_multiple_classifies_sign_change_root`; `tests/test_root_solving_solver.py::test_scan_multiple_classifies_even_multiplicity_root_as_suspected_tangent`; `tests/test_root_solving_solver.py::test_scan_multiple_classifies_boundary_root`; `tests/test_root_solving_solver.py::test_scan_multiple_duplicate_candidates_record_merge_count_without_changing_root_count` |
| Core diagnostic rows and snapshots | `datalab_core.root_solving.root_analysis_rows_from_batch()` maps accepted scan evidence into stable `scan_evidence.{row}.{root}.{field}` diagnostic rows while accepting only string evidence values and integer merge counts; semantic snapshots rebuild those rows from the serialized batch without JSON float leakage. | `tests/test_datalab_core_root_solving.py::test_root_analysis_rows_include_scan_evidence_in_payload_and_snapshot_without_json_floats`; `tests/test_datalab_core_root_solving.py::test_scan_evidence_analysis_rows_filter_bool_and_float_values` |

### P2.1A Fitting Diagnostics Core Outputs

P2.1A fitting diagnostics are additive to the consolidated `FitResult` metrics:
they attach chi-square p-value, parameter correlation, standardized residual,
and max-standardized-residual data under `FitResult.details["diagnostics"]`.
Adapters render these attached fields; they do not recompute chi-square, AIC,
BIC, RMSE, R², or reduced chi-square.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core fitting diagnostics | `fitting.diagnostics.attach_fit_diagnostics()` computes chi-square p-value with `Q(dof / 2, chi2 / 2)` under `precision_guard`, bounds covariance-derived correlations in `[-1, 1]`, emits `nan` plus warnings for invalid correlation cells, and chooses sigma, weight, or RMSE residual normalization from request-time source data. `fitting.diagnostic_formatting` owns neutral diagnostic metric/correlation/residual rows plus CSV/LaTeX diagnostic row builders. | `tests/test_fit_diagnostics.py` |
| Desktop display and CSV | `WindowFittingFormattersMixin` renders attached p-value, max residual, correlation rows, standardized residual rows, and diagnostic warnings from `FitResult.details["diagnostics"]`; diagnostic CSV rows come from `fitting.diagnostic_formatting.build_fitting_diagnostic_csv_rows()`. | `tests/test_fitting_markdown_display.py::test_fit_text_and_csv_include_attached_diagnostics` |
| Desktop LaTeX | `app_desktop.fitting_latex_writer.build_fit_latex_block()` renders attached diagnostic metrics/rows via `fitting.diagnostic_formatting.build_fitting_diagnostic_latex_entries()` while leaving official fit metrics sourced from `FitResult` fields. | `tests/test_fitting_latex_writer.py::test_build_fit_latex_block_includes_attached_diagnostics` |
| Web fitting output | Web fitting deserializes the core `FitResult` diagnostics into visible metrics, visible parameter-correlation and standardized-residual tables, server-generated CSV rows, and fitting LaTeX diagnostics through the shared formatting helper. | `tests/test_app_web_fitting_latex.py::test_run_fit_surfaces_attached_diagnostics_in_metrics_csv_and_latex` |

### P2.1B Fitting Diagnostic Plots And Bands

P2.1B fitting plots keep plot semantics shared and fail closed for unsupported
bands. Residual histogram and QQ plots are visual diagnostics only; they do not
emit formal normality verdicts.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Shared fitting plot specs | `shared.plotting.FittingPlotSpec` covers `fitting.overview`, `fitting.residual`, `fitting.residual_histogram`, `fitting.residual_qq`, and `fitting.correlation_heatmap`. | `tests/test_plotting_backend.py::test_fitting_plot_specs_cover_p2_1b_gallery_bands_and_render_png_bytes` |
| Confidence and prediction bands | `shared.plotting.compute_fitting_bands()` computes confidence uncertainty as `J_p(x) C J_p(x)^T`; prediction bands add residual variance only when a finite non-negative residual variance is available. Missing fitted values, Jacobian, covariance, or residual variance suppress unsupported bands with diagnostics. | `tests/test_plotting_backend.py::test_fitting_prediction_band_suppression_keeps_valid_confidence_band`; `tests/test_plotting_backend.py::test_fitting_bands_fail_closed_without_parameter_jacobian`; `tests/test_plotting_backend.py::test_fitting_bands_fail_closed_without_covariance`; `tests/test_plotting_backend.py::test_fitting_bands_fail_closed_without_fitted_values` |
| Desktop and Web plot adapters | Desktop and Web fitting plot generation pass P2.1A diagnostics and covariance into the shared fitting overview boundary; the legacy `±2×RMSE band` remains compatibility visual behavior and is not labeled as a confidence or prediction band. | `tests/test_plotting_backend.py::test_desktop_fit_plot_routes_diagnostics_and_covariance_to_shared_overview`; `tests/test_app_web_fitting_latex.py::test_run_fit_plot_routes_attached_diagnostics_to_shared_overview` |

### P1.2 Weighted Consistency Diagnostics

Weighted mean consistency diagnostics are additive to `weighted_sigma` /
`weighted` mode. For finite positive sigma rows used by the weighted mean, the
core reports `weighted_chi_square = sum(w_i * (x_i - mean)^2)` with
`w_i = 1 / sigma_i^2`, `weighted_consistency_dof = n_used - 1`, optional
`weighted_reduced_chi_square`, and optional `birge_ratio`. This dof is separate
from Kish `effective_n = W^2 / W2` and from the existing weighted sample
variance correction denominator. Zero-sigma anchor mode omits these consistency
metrics and keeps the zero-sigma diagnostic.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core weighted statistics | `datalab_core.statistics_compute.compute_statistics()` owns the weighted mean and consistency formulas while preserving dropped-row, negative-sigma, zero-sigma anchor, and weight-sum fallback semantics. | `tests/test_datalab_core_statistics.py::test_weighted_consistency_diagnostics_reference_values_and_surfaces`; `tests/test_datalab_core_statistics.py::test_weighted_consistency_diagnostics_exclude_missing_sigma_rows`; `tests/test_datalab_core_statistics.py::test_core_statistics_handler_single_weighted_row_warns_for_consistency_dof` |
| Payload, legacy adapter, CSV, desktop, and Web | `run_statistics()`, `statistics_payload_to_compute_result()`, `statistics_analysis_rows_from_payload()`, and `statistics_csv_rows_from_result()` expose the same weighted consistency rows to existing adapters. | `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| Sigma parsing adapters | Web and desktop statistics preserve explicit parenthesized zero uncertainty (`1.25(0)`) as sigma `0`, preserve signed statistics sigma-column values into core validation, and keep fitting's default absolute sigma normalization unchanged. | `tests/test_app_web_precision_concurrency.py::test_web_statistics_embedded_zero_sigma_reaches_zero_anchor`; `tests/test_desktop_statistics_ui.py::test_statistics_table_preserves_explicit_zero_uncertainty`; `tests/test_desktop_statistics_ui.py::test_statistics_direct_sigma_column_rejects_negative_sigma`; `tests/test_fitting_input_normalization.py::test_data_uncertainty_normalization_uses_explicit_sigma_column_first` |
| Web result table/export | `app_web/templates/stats.html` renders conditional P1.2/zero-anchor rows and the browser result CSV download uses the server-generated shared CSV payload. | `tests/test_app_web_precision_concurrency.py::test_web_statistics_weighted_metrics_render_in_html_and_export_csv`; `tests/test_app_web_precision_concurrency.py::test_web_statistics_zero_sigma_anchor_renders_in_html` |
| LaTeX and workspace restore | `build_statistics_latex_summary_rows()` consumes the shared result fields; semantic statistics snapshots regenerate weighted consistency text/CSV rows. | `tests/test_latex_generation_consistency.py::test_statistics_latex_summary_rows_include_weighted_consistency_metrics`; `tests/test_workspace_controller.py::test_workspace_restores_weighted_consistency_rows_from_semantic_snapshot` |

### P1.3 Confidence Intervals

Mean confidence intervals are additive statistics rows. Unweighted modes use a
Student-t interval with `mean_sample_se_for_ci = sample_std / sqrt(n)` and
`dof = n - 1`, including population display mode. Weighted mode uses a
known-sigma normal interval with `weighted_se_known_sigma = sqrt(1 / sum(w_i))`
when finite positive sigma rows exist and no zero-sigma anchor is active.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Distribution quantiles | `shared.precision` provides normal and Student-t inverse/critical values under the active precision guard. | `tests/test_datalab_core_statistics.py::test_confidence_quantile_helpers_reference_rejection_and_monotonic` |
| Core statistics and suppression | `compute_statistics()` owns unweighted sample-SE CI, weighted known-sigma CI, singleton suppression diagnostics, and zero-sigma suppression. | `tests/test_datalab_core_statistics.py::test_unweighted_confidence_interval_uses_sample_se_in_population_mode`; `tests/test_datalab_core_statistics.py::test_confidence_interval_suppresses_unweighted_singleton_with_diagnostic`; `tests/test_datalab_core_statistics.py::test_weighted_known_sigma_confidence_interval_singleton_disabled_variance_and_zero_anchor` |
| Payload, semantic rows, CSV, desktop, and Web | `run_statistics()`, `statistics_payload_to_compute_result()`, `statistics_analysis_rows_from_payload()`, and `statistics_csv_rows_from_result()` expose CI rows to existing adapters. | `tests/test_datalab_core_statistics.py::test_confidence_interval_payload_semantic_csv_and_snapshot_parity`; `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| LaTeX and workspace restore | `build_statistics_latex_summary_rows()` consumes CI fields; semantic statistics snapshots regenerate CI text/CSV rows. | `tests/test_latex_generation_consistency.py::test_statistics_latex_summary_rows_include_confidence_interval_metrics`; `tests/test_workspace_controller.py::test_workspace_restores_confidence_interval_rows_from_semantic_snapshot` |

### P1.4 Outlier Flags

Outlier flags are advisory row-level diagnostics. They do not delete rows,
change the statistics inputs, or alter mean, CI, or weighted-consistency
calculations. Sigma flags use finite positive sigma values; robust flags use
the two-tailed modified z-score `abs(0.6745 * (x - median) / MAD)`, with a
MAD-zero fallback that flags non-median values and emits a diagnostic.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core outlier diagnostics | `datalab_core.statistics.statistics_outlier_diagnostics()` builds sigma, robust modified-z, and MAD-zero advisory flags from parsed values, sigmas, current result statistics, and core `source_row_ids`. | `tests/test_datalab_core_statistics.py::test_statistics_robust_outlier_flags_are_two_tailed`; `tests/test_datalab_core_statistics.py::test_statistics_mad_zero_flags_non_median_values_and_diagnostic`; `tests/test_datalab_core_statistics.py::test_statistics_sigma_outlier_flags_positive_sigma_source_rows`; `tests/test_datalab_core_statistics.py::test_statistics_missing_sigma_does_not_create_sigma_outlier_or_change_weighted_diagnostics` |
| Semantic rows and shared CSV | `statistics_analysis_rows_from_payload()` exposes compact `AnalysisRow(render_group="row_flag")` outlier rows with source row id, value, metric, and reason; `statistics_csv_rows_from_result()` serializes the same row flags. | `tests/test_datalab_core_statistics.py::test_statistics_outlier_flags_roundtrip_csv_latex_and_snapshot`; `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| Desktop and Web output | Desktop statistics text adds compact outlier diagnostics; Web statistics continues using server-generated shared CSV data for exported row flags. | `tests/test_desktop_statistics_ui.py::test_statistics_display_includes_compact_outlier_flags`; `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| LaTeX and workspace restore | `build_statistics_latex_diagnostic_rows()` emits outlier row-flag diagnostics; semantic statistics snapshots restore row flags into regenerated text/CSV rows. | `tests/test_latex_generation_consistency.py::test_statistics_latex_summary_rows_include_outlier_row_flags`; `tests/test_workspace_controller.py::test_workspace_restores_outlier_row_flags_from_semantic_snapshot` |

### P1.5 Trimmed Mean

Trimmed mean is an optional descriptive-statistics row only. Blank, missing, or
`0` trim fraction keeps the default statistics output unchanged. A positive
trim fraction sorts finite values, trims `floor(n * trim_fraction)` values from
each tail, and averages the remaining values. Core validation rejects negative,
non-finite, non-numeric, or too-large fractions before all data can be removed.

| Surface | Shared boundary | Boundary evidence |
| --- | --- | --- |
| Core calculation and validation | `datalab_core.statistics_compute.compute_statistics()` owns trim-fraction parsing, validation, and trimmed-mean arithmetic for descriptive modes. | `tests/test_datalab_core_statistics.py::test_descriptive_trimmed_mean_disabled_keeps_default_output_absent`; `tests/test_datalab_core_statistics.py::test_descriptive_trim_fraction_validation`; `tests/test_datalab_core_statistics.py::test_descriptive_trimmed_mean_reference_fixtures` |
| Payload, semantic rows, CSV, desktop, and Web | `run_statistics()`, `statistics_payload_to_compute_result()`, `statistics_analysis_rows_from_payload()`, and `statistics_csv_rows_from_result()` expose `trimmed_mean` only when positive trimming is enabled. | `tests/test_datalab_core_statistics.py::test_trimmed_mean_payload_semantic_csv_and_snapshot_parity`; `tests/test_app_web_precision_concurrency.py::test_statistics_analysis_row_mode_condition_coverage_invariant` |
| Desktop and Web controls/output | Desktop/Web pass the raw trim fraction option through existing request builders while core validation remains authoritative; result views show the row only when present. | `tests/test_desktop_statistics_ui.py::test_statistics_trim_fraction_control_visible_only_for_descriptive`; `tests/test_desktop_statistics_ui.py::test_statistics_display_includes_trimmed_mean`; `tests/test_app_desktop_workers_core.py::test_statistics_calc_job_descriptive_trimmed_mean_routes_core_option`; `tests/test_app_web_precision_concurrency.py::test_web_statistics_descriptive_trimmed_mean_routes_and_renders` |
| LaTeX and workspace restore | `build_statistics_latex_summary_rows()` consumes `trimmed_mean`; semantic statistics snapshots regenerate trimmed-mean text/CSV rows and preserve the trim-fraction setting. | `tests/test_latex_generation_consistency.py::test_statistics_latex_summary_rows_include_descriptive_metrics`; `tests/test_workspace_controller.py::test_workspace_restores_descriptive_statistics_rows_from_semantic_snapshot` |

### Workspace

- v1 ZIP read/write hardening, attachment path/hash validation, atomic save, and stable archive layout.
- Reader-first v2 dispatch through `read_workspace()` while `write_workspace()` remains v1-only by default.
- `WorkbenchModel` v1 hash parity, formula-preview UI-state hash exclusion, legacy-float restore normalization, and Qt/import purity.
- Legacy workspace contracts: obsolete auto-fit degradation, implicit schema 1/2 migration, root-solving `auto` normalization, result-snapshot overview restore, and example-template save-as behavior.

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
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_visual_screenshots.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

Then, for each page (Extrapolation / Error Propagation / Fitting / Statistics):

- Input mode: file + manual (each alone, and both combined).
- Precision controls: `mp.dps` changes + display digits/scientific toggle; confirm result panel updates without recomputation.
- LaTeX controls: input digits, uncertainty digits, `use_dcolumn`, `latex_group_size`, segmented tables (if enabled).
- Export: CSV/LaTeX/PDF (where supported), and verify preview matches saved files.
- Help: function list/help panel and all “?” tooltips/dialogs in both `zh/en`.
