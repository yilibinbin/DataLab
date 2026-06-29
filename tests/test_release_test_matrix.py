from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "superpowers" / "specs" / "2026-06-10-datalab-gui-rearchitecture-adr.md"
_RELEASE_GATE_HEADING = "Run the full local gate before packaging:"
_PACKAGING_COMMAND_HEADING = "Build release artifacts after the local gate passes:"
_UPDATE_MANIFEST_COMMAND_HEADING = (
    "After release artifacts exist, generate the signed update manifest."
)
_POST_PACKAGING_ARTIFACT_HEADING = "After macOS and Windows packaging complete"
_INSTALLER_UPDATE_GATE_HEADING = "### Installer Update Release Gate"
_P0_1_BASELINE_HEADING = "### P0.1 Baseline Coverage Matrix"
_ERROR_PROPAGATION_HEADING = "### Error Propagation"
_PYTEST_PATH_RE = re.compile(r"(?:tests|app_web)/[A-Za-z0-9_./-]+\.py")
_TOOL_PATH_RE = re.compile(r"tools/[A-Za-z0-9_./-]+\.py")
_REQUIRED_RUFF_TARGETS = {
    "app_desktop",
    "app_web",
    "datalab_core",
    "datalab_latex",
    "fitting",
    "shared",
    "tests",
    "tools",
    "formula_help.py",
    "statistics_utils.py",
    "data_extrapolation_gui.py",
    "data_extrapolation_latex_latest.py",
}
_REQUIRED_EXACT_RELEASE_COMMANDS = {
    "python -m compileall -q .",
    "python tools/release_import_hygiene.py",
    "python tools/scan_desktop_gui_schema.py",
    "QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900",
    "QT_QPA_PLATFORM=offscreen pytest -q",
}
_REQUIRED_POST_PACKAGING_COMMANDS = {
    "python tools/record_release_artifact_sizes.py --out build/release-artifact-sizes.json",
    "python tools/webengine_evidence_bundle.py --artifact-manifest build/release-artifact-sizes.json --out-dir build/webengine-evidence",
}
_REQUIRED_PACKAGING_COMMANDS = {
    "DATALAB_BUILD_PKG=1 ./build_mac_data_gui.sh",
    r"powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows_data_gui.ps1 -BuildInnoInstaller",
}
_REQUIRED_UPDATE_MANIFEST_COMMANDS = {
    'python tools/generate_updates_manifest.py --version "$DATALAB_RELEASE_VERSION" --release-url "https://github.com/yilibinbin/DataLab/releases/tag/v$DATALAB_RELEASE_VERSION" --notes-file "$DATALAB_RELEASE_NOTES" --published-at "$DATALAB_RELEASE_PUBLISHED_AT" --min-client-version "$DATALAB_UPDATE_MIN_CLIENT_VERSION" --macos-pkg "dist/DataLab-$DATALAB_RELEASE_VERSION-macOS.pkg" --windows-exe "dist/DataLab-$DATALAB_RELEASE_VERSION-Windows-x64.exe" --output "dist/updates.json"',
}
_REQUIRED_INSTALLER_UPDATE_GATE_PHRASES = (
    "macOS `.pkg` is signed and notarized before auto-installable release",
    "Windows Inno installer is Authenticode-signed before",
    "`updates.json` contains only metadata, size, and SHA-256 values",
    "installer arguments are constructed by application code",
    "Offline startup performs no network request unless automatic updates",
)
_P0_1_BASELINE_REQUIRED_PHRASES = (
    "P1/P2 statistics metrics stay out of this",
    "core payload still exposes `min` / `max`",
    "legacy compute/display dictionaries still expose `v_min` / `v_max`",
    "condition-specific `effective_n`",
    "condition-specific `zero_sigma_anchor`",
    "`ResultEnvelope.warnings` preservation through `statistics_payload_to_compute_result()`",
    "datalab_core.statistics_compute.compute_statistics()",
    "datalab_core.statistics.run_statistics()",
    "datalab_core.statistics.statistics_payload_to_compute_result()",
    "app_desktop.window_statistics_mixin.WindowStatisticsMixin._format_statistics_display()",
    "app_desktop.workers_core._execute_calc_job()",
    "app_desktop.window_extrapolation_mixin.WindowExtrapolationMixin.run_calculation()",
    "app_web.logic.statistics._run_statistics()",
    "statistics_utils.generate_statistics_latex()",
    "statistics_utils.generate_statistics_latex_batches()",
    "P0.1 self-contained statistics LaTeX evidence uses tracked tests",
    "tests/test_latex_generation_consistency.py::test_statistics_latex",
    "tests/test_latex_compile_e2e.py::test_latex_compile_e2e",
    "pre-existing untracked",
    "they are not the only P0.1 statistics LaTeX evidence",
    "WindowFittingFormattersMixin._build_fit_csv_rows()",
    "WindowFittingFormattersMixin._fit_latex_block()",
    "WindowExtrapolationMixin._write_root_latex_if_requested()",
    "app_desktop.root_latex_writer.write_root_latex()",
    "app_desktop.workers_core._aggregate_error_contributions()",
    "app_desktop.workers_qt.CalcWorker._aggregate_error_contributions()",
    "app_web.logic.fitting._generate_fitting_latex()",
    "app_web.logic.error_propagation._render_error_latex()",
    "Internal-only allowlist for this baseline",
    "No new P1/P2 statistics metrics, public result keys, GUI controls, or",
)
_P0_1_BASELINE_REQUIRED_ROW_LABELS = (
    "Arithmetic mean sample, population, and bare `mean` mode",
    "Weighted normal case",
    "Weighted zero-sigma anchor",
    "Weighted dropped-row case",
    "High-precision guard",
)
_ERROR_PROPAGATION_P2_4_REQUIRED_PHRASES = (
    "P2.4 diagnostics",
    "shared.error_contributions",
    "error semantic snapshot",
    "contribution diagnostics",
    "propagation metadata",
    "cumulative contribution overlay rows",
    "Taylor/Monte Carlo comparison rows",
    "sensitivity rows",
    "Taylor-order comparison rows",
    "JSON-safe distribution summary/spec",
    "visible distribution plot routing via row plot galleries",
    "tests/test_datalab_core_uncertainty.py",
    "tests/test_shared_error_propagation_engine.py",
    "tests/test_app_desktop_workers_core.py",
    "tests/test_app_web_precision_concurrency.py",
    "tests/test_web_plot_generation.py",
    "tests/test_plotting_backend.py",
)
_UNCERTAINTY_DOC_PATHS = (
    ROOT / "docs" / "desktop" / "uncertainty.en.md",
    ROOT / "docs" / "desktop" / "uncertainty.zh.md",
    ROOT / "docs" / "web" / "uncertainty.en.md",
    ROOT / "docs" / "web" / "uncertainty.zh.md",
)


def _command_block_after(matrix: str, heading: str) -> str:
    heading_count = matrix.count(heading)
    assert heading_count == 1, f"Expected one heading {heading!r}, found {heading_count}"

    start = matrix.index(heading)
    fence_start = matrix.find("```bash", start)
    assert fence_start >= 0, f"{heading!r} must be followed by a bash command block"

    block_start = fence_start + len("```bash")
    block_end = matrix.find("```", block_start)
    assert block_end >= 0, f"{heading!r} bash command block must be closed"
    return matrix[block_start:block_end]


def _release_gate_command_block(matrix: str) -> str:
    return _command_block_after(matrix, _RELEASE_GATE_HEADING)


def _git_tracked_paths() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise AssertionError("git executable is required to verify release-gate tracked paths") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise AssertionError(f"failed to read git tracked paths{detail}") from exc

    tracked_paths = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not tracked_paths:
        raise AssertionError("git tracked path list is empty; cannot verify release-gate tracked paths")
    return tracked_paths


def _section_after(matrix: str, heading: str) -> str:
    heading_count = matrix.count(heading)
    assert heading_count == 1, f"Expected one heading {heading!r}, found {heading_count}"

    start = matrix.index(heading)
    next_heading = matrix.find("\n##", start + len(heading))
    if next_heading < 0:
        return matrix[start:]
    return matrix[start:next_heading]


def _required_release_tests() -> set[str]:
    return {
        *(f"tests/{path.name}" for path in sorted((ROOT / "tests").glob("test_datalab_core_*.py"))),
        "tests/test_app_desktop_bridge_qt.py",
        "tests/test_app_desktop_workers_core.py",
        "tests/test_app_desktop_views_registry.py",
        "tests/test_desktop_workbench_specs.py",
        "tests/test_desktop_workbench_state_ownership.py",
        "tests/test_desktop_workbench_results.py",
        "tests/test_desktop_workbench_formula_panel.py",
        "tests/test_desktop_workbench_variable_panel.py",
        "tests/test_desktop_workbench_visual_contract.py",
        "tests/test_desktop_workbench_theme.py",
        "tests/test_desktop_workbench_toolbar.py",
        "tests/test_desktop_workbench_layout.py",
        "tests/test_desktop_workbench_data_area.py",
        "tests/test_desktop_workbench_editor_canvas.py",
        "tests/test_desktop_workbench_visual_screenshots.py",
        "tests/test_desktop_gui_workflows.py",
        "tests/test_desktop_gui_schema_scan.py",
        "tests/test_desktop_gui_redesign_scan.py",
        "tests/test_desktop_bilingual_inventory.py",
        "tests/test_desktop_ui_schema_binder.py",
        "tests/test_desktop_ui_schema_runtime.py",
        "tests/test_desktop_editor_affordances.py",
        "tests/test_desktop_shared_ui_specs.py",
        "tests/test_desktop_root_solving_ui.py",
        "tests/test_desktop_error_propagation_ui.py",
        "tests/test_desktop_implicit_model_ui.py",
        "tests/test_desktop_statistics_ui.py",
        "tests/test_desktop_extrapolation_ui.py",
        "tests/test_constants_editor.py",
        "tests/test_constants_editor_visibility.py",
        "tests/test_constants_text_view.py",
        "tests/test_constraints_parameter_state.py",
        "tests/test_fitting_parameter_inference.py",
        "tests/test_parameter_table.py",
        "tests/test_parameter_table_editor.py",
        "tests/test_desktop_result_schema_ui.py",
        "tests/test_desktop_result_workflows.py",
        "tests/test_result_view_schema.py",
        "tests/test_desktop_theme_tokens.py",
        "tests/test_tutorial_overlay.py",
        "tests/test_desktop_section_panel.py",
        "tests/test_bilingual_errors.py",
        "tests/test_clipboard_paste_parser.py",
        "tests/test_desktop_about_dialog.py",
        "tests/test_desktop_global_options_ui.py",
        "tests/test_desktop_gui_screenshot_smoke.py",
        "tests/test_desktop_mode_stack.py",
        "tests/test_desktop_schema_widgets.py",
        "tests/test_desktop_shell_layout.py",
        "tests/test_qfiledialog_titles_bilingual.py",
        "tests/test_splitter_persistence.py",
        "tests/test_table_row_col_buttons.py",
        "tests/test_ui_schema.py",
        "tests/test_ui_schema_audit.py",
        "tests/test_benchmark_scaffold.py",
        "tests/test_cli_batch.py",
        "tests/test_crash_reporter.py",
        "tests/test_help_specs_single_source.py",
        "tests/test_logging_format.py",
        "tests/test_model_id_aliases.py",
        "tests/test_model_selector.py",
        "tests/test_presets.py",
        "tests/test_pyproject_metadata.py",
        "tests/test_settings_store.py",
        "tests/test_r10_c5_m5_requires_positive_x.py",
        "tests/test_notebook_export.py",
        "tests/test_pdf_preview_controller_integration.py",
        "tests/test_pdf_preview_page_cache.py",
        "tests/test_pdf_preview_raster_backend.py",
        "tests/test_pdf_preview_raster_pdftoppm_multi_page.py",
        "tests/test_plotting_backend.py",
        "tests/test_packaging_resources.py",
        "tests/test_desktop_docs_resources.py",
        "tests/test_core_no_qt_imports.py",
        "tests/test_phase0_precision_guardrails.py",
        "tests/test_phase0_adr_guardrails.py",
        "tests/test_phase0_desktop_guardrails.py",
        "tests/test_release_artifact_sizes.py",
        "tests/test_release_import_hygiene.py",
        "tests/test_packaging_qt_excludes.py",
        "tests/test_webengine_measurement_evidence.py",
        "tests/test_webengine_asset_evidence_tool.py",
        "tests/test_webengine_shipping_import_guard.py",
        "tests/test_webengine_spike_assets.py",
        "tests/test_webengine_spike_contract.py",
        "tests/test_webengine_spike_report.py",
        "tests/test_webengine_evidence_bundle_tool.py",
        "tests/test_formula_render_service.py",
        "tests/test_formula_export.py",
        "tests/test_formula_latex_export.py",
        "tests/test_expression_registry.py",
        "tests/test_expression_engine_formula_rendering_integration.py",
        "tests/test_formula_preview_rendering.py",
        "tests/test_formula_preview_dialog.py",
        "tests/test_formula_mathtext_png.py",
        "tests/test_formula_renderer_boundary.py",
        "tests/test_formula_renderer_value_gate.py",
        "tests/test_app_web_extrapolation_latex.py",
        "tests/test_app_web_fitting_latex.py",
        "tests/test_latex_table_segments_and_filtering.py",
        "tests/test_latex_generation_consistency.py",
        "tests/test_latex_group_size_zero.py",
        "tests/test_fitting_latex_writer.py",
        "tests/test_latex_tables_facade_exports.py",
        "tests/test_latex_security_include_traversal.py",
        "tests/test_expression_engine_latex_manual_formatter.py",
        "tests/test_latex_formatting_expand_scientific.py",
        "tests/test_latex_formatting_spacing_helpers.py",
        "tests/test_latex_tables_unit.py",
        "tests/test_latex_tables_common_unit.py",
        "tests/test_latex_varwidth_regression.py",
        "tests/test_sisetup_block.py",
        "tests/test_siunitx_column_spec_regression.py",
        "tests/test_r10_c1_latex_content_validation_called.py",
        "tests/test_latex_compile_worker.py",
        "tests/test_desktop_latex_compile_ui.py",
        "tests/test_latex_engine_discovery.py",
        "tests/test_latex_engine_install.py",
        "tests/test_tinytex_install_script.py",
        "tests/test_latex_compile_e2e.py",
        "tests/test_theory_docs_compile.py",
        "tests/test_root_solving_batch.py",
        "tests/test_root_solving_expression.py",
        "tests/test_root_solving_formatting.py",
        "tests/test_root_solving_normalization.py",
        "tests/test_root_solving_plotting.py",
        "tests/test_root_solving_solver.py",
        "tests/test_root_solving_uncertainty.py",
        "tests/test_root_solving_uncertainty_policy.py",
        "tests/test_root_latex_writer.py",
        "tests/test_r10_c4_findroot_convergence_args.py",
        "tests/test_uncertainty_auto_digits.py",
        "tests/test_uncertainty_formatter_overflow.py",
        "tests/test_shared_uncertainty.py",
        "tests/test_error_propagation_latex_display_precision.py",
        "tests/test_extrapolation_latex_display_precision.py",
        "tests/test_error_propagation_higher_order_and_mc.py",
        "tests/test_error_propagation_mathematica_reference.py",
        "tests/test_error_propagation_method_aliases.py",
        "tests/test_error_propagation_second_order_reference.py",
        "tests/test_error_propagation_symbolic_derivative.py",
        "tests/test_extrapolation_accelerators.py",
        "tests/test_extrapolation_high_precision_convergence.py",
        "tests/test_extrapolation_mathematica_reference.py",
        "tests/test_extrapolation_power_law.py",
        "tests/test_statistics_mathematica_reference.py",
        "tests/test_statistics_modes_and_flags.py",
        "tests/test_statistics_weighted.py",
        "tests/test_special_functions_mathematica_reference.py",
        "tests/test_units_integration.py",
        "tests/test_fit_custom_model_same_as_extrapolation.py",
        "tests/test_fit_statistics.py",
        "tests/test_fitting_input_normalization.py",
        "tests/test_fitting_linear_model_sanity.py",
        "tests/test_fitting_markdown_display.py",
        "tests/test_fitting_problem_boundary.py",
        "tests/test_fitting_runner_equivalence.py",
        "tests/test_fitting_runner_scipy_fallback.py",
        "tests/test_fitting_scipy_reference.py",
        "tests/test_implicit_d8_runner_regression.py",
        "tests/test_implicit_fit_worker_cancellation.py",
        "tests/test_mcmc_fitter.py",
        "tests/test_mcmc_gui_wiring.py",
        "tests/test_mcmc_pre_flight_health.py",
        "tests/test_parallel_backend.py",
        "tests/test_parallel_config.py",
        "tests/test_parallel_preferences.py",
        "tests/test_sampling_cache.py",
        "tests/test_sampling_parallel.py",
        "tests/test_safe_eval_ast_nodes_limit.py",
        "tests/test_safe_eval_security.py",
        "tests/test_symbolic_export.py",
        "tests/test_symbolic_math.py",
        "tests/test_render_fit_cache.py",
        "tests/test_r10_c3_plot_fitting_precision_guard.py",
        "tests/test_auto_fit_cancellation_and_timeout.py",
        "tests/test_auto_fit_removed.py",
        "tests/test_bilingual_errors_extrapolation_methods.py",
        "tests/test_desktop_custom_fit_ui.py",
        "tests/test_workspace_io.py",
        "tests/test_workspace_legacy_fixtures.py",
        "tests/test_workspace_auto_fit_migration.py",
        "tests/test_workspace_implicit_round_trip.py",
        "tests/test_workspace_controller.py",
        "tests/test_desktop_example_workspace_menu.py",
        "tests/test_example_workspaces.py",
        "tests/test_desktop_multiprocessing_entrypoint.py",
        "tests/test_gui_shim_exports.py",
        "tests/test_safe_read_text_encodings.py",
        "tests/test_desktop_workspace_entrypoint.py",
        "tests/test_desktop_workspace_menu.py",
        "tests/test_desktop_examples_entrypoint.py",
        "tests/test_docs_sanity.py",
        "tests/test_desktop_docs_smoke.py",
        "tests/test_doc_slug_validation.py",
        "tests/test_app_icon_asset.py",
        "tests/test_implicit_packaging.py",
        "tests/test_macos_icon_packaging.py",
        "tests/test_macos_icon_preparation.py",
        "tests/test_mcmc_packaging_declarations.py",
        "tests/test_workspace_file_association_packaging.py",
        "tests/test_update_checker.py",
        "tests/test_update_controller.py",
        "tests/test_update_payload.py",
        "tests/test_update_signing.py",
        "tests/test_generate_updates_manifest.py",
        "tests/test_update_installer.py",
        "tests/test_update_packaging_scripts.py",
        "tests/test_update_payload_progress.py",
        "tests/test_update_download_worker.py",
        "tests/test_update_progress_dialog.py",
        "tests/test_update_dialogs.py",
        "tests/test_update_preferences.py",
        "tests/test_desktop_update_menu.py",
        "tests/test_pyinstaller_spec_paths.py",
        "tests/test_r10_c2_secret_key_not_hardcoded.py",
        "tests/test_security_get_config_value_no_app_context.py",
        "tests/test_web_server_startup_smoke.py",
        "app_web/test_security.py",
        "tests/test_collaborate_session.py",
        "tests/test_collab_integration.py",
        "tests/test_app_web_baseline_contracts.py",
        "tests/test_app_web_docs_baseline.py",
        "tests/test_app_web_route_inventory.py",
        "tests/test_app_web_fitting_uncertainty.py",
        "tests/test_app_web_formula_resources_baseline.py",
        "tests/test_app_web_precision_concurrency.py",
        "tests/test_app_web_sse_baseline.py",
        "tests/test_web_sse_streaming.py",
        "tests/test_web_sse_fit_endpoint.py",
        "tests/test_openapi_spec.py",
        "tests/test_web_theme_toggle.py",
        "tests/test_web_plot_generation.py",
        "tests/test_web_api_smoke.py",
        "tests/test_release_test_matrix.py",
    }


def test_release_gate_lists_core_phase0_and_web_boundary_tests() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    required_tests = _required_release_tests()

    missing = sorted(test_file for test_file in required_tests if test_file not in release_gate_commands)

    assert not missing, "docs/TEST_MATRIX.md release gate is missing: " + ", ".join(missing)


def test_release_gate_required_set_covers_every_pytest_path() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    release_gate_tests = set(_PYTEST_PATH_RE.findall(release_gate_commands))
    required_tests = _required_release_tests()

    unguarded = sorted(release_gate_tests - required_tests)

    assert not unguarded, "release gate pytest paths are not in required set: " + ", ".join(unguarded)


def test_release_gate_includes_phase0_adr_evidence_tests() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    adr_text = ADR_PATH.read_text(encoding="utf-8")
    adr_evidence_tests = sorted(set(_PYTEST_PATH_RE.findall(adr_text)))

    assert adr_evidence_tests, "Phase 0 ADR should list guardrail tests in its evidence map"

    missing = sorted(test_path for test_path in adr_evidence_tests if test_path not in release_gate_commands)

    assert not missing, "docs/TEST_MATRIX.md release gate is missing ADR evidence tests: " + ", ".join(missing)


def test_release_gate_test_paths_exist() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    test_paths = sorted(set(_PYTEST_PATH_RE.findall(release_gate_commands)))
    tracked_paths = _git_tracked_paths()

    assert test_paths, "docs/TEST_MATRIX.md release gate should list pytest test files"

    missing = [test_path for test_path in test_paths if not (ROOT / test_path).is_file()]
    untracked = [test_path for test_path in test_paths if test_path not in tracked_paths]

    assert not missing, "docs/TEST_MATRIX.md release gate references missing test files: " + ", ".join(missing)
    assert not untracked, "docs/TEST_MATRIX.md release gate references untracked test files: " + ", ".join(untracked)


def test_release_gate_tool_paths_exist() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    tool_paths = sorted(set(_TOOL_PATH_RE.findall(release_gate_commands)))
    tracked_paths = _git_tracked_paths()

    assert tool_paths, "docs/TEST_MATRIX.md release gate should list helper tool scripts"

    missing = [tool_path for tool_path in tool_paths if not (ROOT / tool_path).is_file()]
    untracked = [tool_path for tool_path in tool_paths if tool_path not in tracked_paths]

    assert not missing, "docs/TEST_MATRIX.md release gate references missing tool scripts: " + ", ".join(missing)
    assert not untracked, "docs/TEST_MATRIX.md release gate references untracked tool scripts: " + ", ".join(untracked)


def test_release_gate_includes_release_relevant_ruff_targets() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    expected = "python -m ruff check "

    ruff_lines = [
        line.strip()
        for line in release_gate_commands.splitlines()
        if line.strip().startswith(expected)
    ]

    assert len(ruff_lines) == 1, "Release gate must include exactly one release-relevant ruff check"
    assert ruff_lines[0] != "python -m ruff check .", "Release gate ruff must exclude root scratch files"
    targets = set(ruff_lines[0][len(expected) :].split())
    missing = sorted(_REQUIRED_RUFF_TARGETS - targets)

    assert not missing, "release gate ruff command is missing targets: " + ", ".join(missing)


def test_release_gate_includes_required_non_pytest_commands() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    release_gate_commands = _release_gate_command_block(matrix)
    command_lines = {
        line.strip()
        for line in release_gate_commands.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(_REQUIRED_EXACT_RELEASE_COMMANDS - command_lines)

    assert not missing, "release gate is missing required non-pytest commands: " + ", ".join(missing)


def test_post_packaging_artifact_evidence_commands_are_guarded() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    post_packaging_commands = _command_block_after(matrix, _POST_PACKAGING_ARTIFACT_HEADING)
    command_lines = {
        line.strip()
        for line in post_packaging_commands.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(_REQUIRED_POST_PACKAGING_COMMANDS - command_lines)

    assert not missing, "post-packaging artifact evidence commands are missing: " + ", ".join(missing)
    artifact_line = " ".join(
        line for line in command_lines if "tools/record_release_artifact_sizes.py" in line
    )
    assert "--allow-empty" not in artifact_line, "release artifact evidence must not use --allow-empty"


def test_release_artifact_packaging_commands_are_documented() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    packaging_commands = _command_block_after(matrix, _PACKAGING_COMMAND_HEADING)
    command_lines = {
        line.strip()
        for line in packaging_commands.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(_REQUIRED_PACKAGING_COMMANDS - command_lines)

    assert not missing, "release artifact packaging commands are missing: " + ", ".join(missing)


def test_signed_update_manifest_command_is_documented() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    update_manifest_section = _section_after(matrix, _UPDATE_MANIFEST_COMMAND_HEADING)
    update_manifest_commands = _command_block_after(matrix, _UPDATE_MANIFEST_COMMAND_HEADING)
    command_lines = {
        line.strip()
        for line in update_manifest_commands.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = sorted(_REQUIRED_UPDATE_MANIFEST_COMMANDS - command_lines)

    assert not missing, "signed update manifest command is missing: " + ", ".join(missing)
    assert "DATALAB_UPDATE_SIGNING_PRIVATE_KEY_B64" in update_manifest_section
    assert "--allow-unsigned-assets" not in update_manifest_commands


def test_installer_update_release_gate_policy_is_documented() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    section = _section_after(matrix, _INSTALLER_UPDATE_GATE_HEADING)
    missing = [
        phrase
        for phrase in _REQUIRED_INSTALLER_UPDATE_GATE_PHRASES
        if phrase not in section
    ]

    assert not missing, "installer update release gate is missing policy text: " + ", ".join(missing)


def test_p0_1_baseline_matrix_documents_schema_mapping_and_internal_allowlist() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    section = _section_after(matrix, _P0_1_BASELINE_HEADING)
    row_labels: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| ") or " | " not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"Current row", "---"}:
            continue
        row_labels.add(cells[0])
    missing_rows = [
        label
        for label in _P0_1_BASELINE_REQUIRED_ROW_LABELS
        if label not in row_labels
    ]
    missing = [
        phrase
        for phrase in _P0_1_BASELINE_REQUIRED_PHRASES
        if phrase not in section
    ]

    assert not missing_rows, "P0.1 baseline matrix is missing rows: " + ", ".join(missing_rows)
    assert not missing, "P0.1 baseline matrix is missing coverage text: " + ", ".join(missing)


def test_error_propagation_p2_4_docs_and_matrix_cover_distribution_plots() -> None:
    matrix = (ROOT / "docs" / "TEST_MATRIX.md").read_text(encoding="utf-8")
    section = _section_after(matrix, _ERROR_PROPAGATION_HEADING)
    missing = [
        phrase
        for phrase in _ERROR_PROPAGATION_P2_4_REQUIRED_PHRASES
        if phrase not in section
    ]

    assert not missing, "Error Propagation matrix is missing P2.4 evidence: " + ", ".join(missing)

    for doc_path in _UNCERTAINTY_DOC_PATHS:
        doc = doc_path.read_text(encoding="utf-8")
        assert "Monte Carlo" in doc
        assert "per-variable contribution" in doc or "逐变量贡献" in doc
        assert "percentile" in doc or "百分位" in doc
        assert "distribution histogram" in doc or "分布直方图" in doc
        assert "Taylor" in doc
        assert "cumulative contribution" in doc or "累计贡献" in doc
