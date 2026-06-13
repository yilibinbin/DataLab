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
QT_QPA_PLATFORM=offscreen pytest -q tests/test_app_desktop_views_registry.py tests/test_desktop_workbench_specs.py tests/test_desktop_workbench_state_ownership.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_formula_panel.py tests/test_desktop_workbench_variable_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_render_service.py tests/test_expression_engine_formula_rendering_integration.py tests/test_formula_preview_rendering.py tests/test_formula_preview_dialog.py tests/test_formula_tex_render_worker.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_table_segments_and_filtering.py tests/test_fitting_latex_writer.py tests/test_latex_tables_facade_exports.py tests/test_latex_security_include_traversal.py tests/test_expression_engine_latex_manual_formatter.py tests/test_latex_formatting_expand_scientific.py tests/test_latex_formatting_spacing_helpers.py tests/test_latex_tables_unit.py tests/test_latex_tables_common_unit.py tests/test_latex_varwidth_regression.py tests/test_sisetup_block.py tests/test_siunitx_column_spec_regression.py tests/test_r10_c1_latex_content_validation_called.py tests/test_latex_compile_worker.py tests/test_desktop_latex_compile_ui.py tests/test_latex_engine_discovery.py tests/test_latex_engine_install.py tests/test_tinytex_install_script.py tests/test_latex_compile_e2e.py tests/test_theory_docs_compile.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_visual_screenshots.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_desktop_editor_affordances.py tests/test_desktop_shared_ui_specs.py tests/test_workspace_controller.py tests/test_packaging_resources.py tests/test_desktop_docs_resources.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_root_solving_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_statistics_ui.py tests/test_desktop_extrapolation_ui.py tests/test_constants_editor.py tests/test_constants_editor_visibility.py tests/test_constants_text_view.py tests/test_constraints_parameter_state.py tests/test_fitting_parameter_inference.py tests/test_parameter_table.py tests/test_parameter_table_editor.py tests/test_desktop_result_schema_ui.py tests/test_desktop_result_workflows.py tests/test_result_view_schema.py tests/test_desktop_theme_tokens.py tests/test_tutorial_overlay.py tests/test_desktop_section_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_bilingual_errors.py tests/test_clipboard_paste_parser.py tests/test_desktop_about_dialog.py tests/test_desktop_global_options_ui.py tests/test_desktop_gui_screenshot_smoke.py tests/test_desktop_mode_stack.py tests/test_desktop_schema_widgets.py tests/test_desktop_shell_layout.py tests/test_qfiledialog_titles_bilingual.py tests/test_splitter_persistence.py tests/test_table_row_col_buttons.py tests/test_ui_schema.py tests/test_ui_schema_audit.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_benchmark_scaffold.py tests/test_cli_batch.py tests/test_crash_reporter.py tests/test_help_specs_single_source.py tests/test_logging_format.py tests/test_model_id_aliases.py tests/test_model_selector.py tests/test_presets.py tests/test_pyproject_metadata.py tests/test_settings_store.py tests/test_r10_c5_m5_requires_positive_x.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_notebook_export.py tests/test_pdf_preview_controller_integration.py tests/test_pdf_preview_page_cache.py tests/test_pdf_preview_raster_backend.py tests/test_pdf_preview_raster_pdftoppm_multi_page.py tests/test_plotting_backend.py
pytest -q tests/test_datalab_core_dtos.py tests/test_datalab_core_statistics.py tests/test_datalab_core_extrapolation.py tests/test_datalab_core_uncertainty.py tests/test_datalab_core_root_solving.py tests/test_datalab_core_fitting.py tests/test_datalab_core_parallel_options.py tests/test_datalab_core_workbench_model.py tests/test_core_no_qt_imports.py tests/test_phase0_precision_guardrails.py tests/test_phase0_adr_guardrails.py tests/test_release_test_matrix.py tests/test_release_artifact_sizes.py tests/test_update_checker.py tests/test_packaging_qt_excludes.py tests/test_webengine_measurement_evidence.py tests/test_webengine_asset_evidence_tool.py tests/test_webengine_shipping_import_guard.py tests/test_webengine_spike_assets.py tests/test_webengine_spike_contract.py tests/test_webengine_spike_report.py tests/test_webengine_evidence_bundle_tool.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_root_solving_batch.py tests/test_root_solving_expression.py tests/test_root_solving_formatting.py tests/test_root_solving_normalization.py tests/test_root_solving_plotting.py tests/test_root_solving_solver.py tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_latex_writer.py tests/test_r10_c4_findroot_convergence_args.py tests/test_uncertainty_auto_digits.py tests/test_uncertainty_formatter_overflow.py tests/test_shared_uncertainty.py tests/test_error_propagation_latex_display_precision.py tests/test_extrapolation_latex_display_precision.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_error_propagation_higher_order_and_mc.py tests/test_error_propagation_mathematica_reference.py tests/test_error_propagation_method_aliases.py tests/test_error_propagation_symbolic_derivative.py tests/test_extrapolation_accelerators.py tests/test_extrapolation_high_precision_convergence.py tests/test_extrapolation_mathematica_reference.py tests/test_extrapolation_power_law.py tests/test_statistics_mathematica_reference.py tests/test_statistics_modes_and_flags.py tests/test_statistics_weighted.py tests/test_special_functions_mathematica_reference.py tests/test_units_integration.py
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
