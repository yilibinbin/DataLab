from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = ROOT / "docs" / "superpowers" / "specs" / "2026-06-10-datalab-gui-rearchitecture-adr.md"
PLAN_PATH = ROOT / "docs" / "superpowers" / "plans" / "2026-06-10-datalab-full-gui-rearchitecture-plan.md"
TEST_PATH_RE = re.compile(r"`((?:tests|app_web)/[A-Za-z0-9_./-]+\.py)`")


REQUIRED_INVARIANT_SNIPPETS = (
    "datalab_core` must not import PySide6",
    "source strings or explicitly typed high-precision payloads",
    "not JSON floats",
    "shared.precision.precision_guard()",
    "In-process mpmath jobs remain single-flight",
    "Existing subprocess kill/timeout/cancellation behavior remains intact",
    "MODE_WORKBENCH_SPECS",
    "shared/ui_specs.py",
    "shared/help_specs.json",
    "legacy `ui.formula_preview` metadata is reader-only compatibility state",
    "is not re-saved",
    "does not rewrite compute formulas, config, or workspace hashes",
    "Workspace v1 read compatibility is permanent",
    "v1 writer/export path",
    "No WebEngine bridge may expose arbitrary file, shell, or network access",
    "No startup network access is allowed unless the user enabled update checks",
    "Qt-free, side-effect-safe shared modules",
    "shared/settings_store.py",
    "shared/presets.py",
    "shared/ui_keyguards.py",
    "shared/pdf_preview",
    "shared/latex_engine.py",
)


REQUIRED_EVIDENCE_TESTS = (
    "tests/test_core_no_qt_imports.py",
    "tests/test_phase0_precision_guardrails.py",
    "tests/test_phase0_desktop_guardrails.py",
    "tests/test_datalab_core_parallel_options.py",
    "tests/test_datalab_core_workbench_model.py",
    "tests/test_workspace_legacy_fixtures.py",
    "tests/test_workspace_io.py",
    "tests/test_app_web_baseline_contracts.py",
    "tests/test_app_web_docs_baseline.py",
    "tests/test_app_web_route_inventory.py",
    "tests/test_app_web_fitting_uncertainty.py",
    "tests/test_app_web_precision_concurrency.py",
    "tests/test_app_web_sse_baseline.py",
    "tests/test_web_sse_streaming.py",
    "tests/test_web_sse_fit_endpoint.py",
    "tests/test_app_web_formula_resources_baseline.py",
    "tests/test_openapi_spec.py",
    "tests/test_web_theme_toggle.py",
    "tests/test_web_plot_generation.py",
    "tests/test_web_api_smoke.py",
    "tests/test_packaging_qt_excludes.py",
    "tests/test_release_artifact_sizes.py",
    "tests/test_webengine_shipping_import_guard.py",
    "tests/test_webengine_measurement_evidence.py",
    "tests/test_webengine_asset_evidence_tool.py",
    "tests/test_webengine_spike_assets.py",
    "tests/test_webengine_spike_contract.py",
    "tests/test_webengine_spike_report.py",
    "tests/test_webengine_evidence_bundle_tool.py",
    "tests/test_update_checker.py",
    "tests/test_update_controller.py",
    "tests/test_r10_c2_secret_key_not_hardcoded.py",
    "tests/test_security_get_config_value_no_app_context.py",
    "tests/test_web_server_startup_smoke.py",
    "app_web/test_security.py",
    "tests/test_collaborate_session.py",
    "tests/test_collab_integration.py",
    "tests/test_release_test_matrix.py",
)


def _adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def test_phase0_adr_preserves_required_invariants() -> None:
    text = _adr_text()

    missing = [snippet for snippet in REQUIRED_INVARIANT_SNIPPETS if snippet not in text]

    assert not missing, "Phase 0 ADR is missing required invariant snippets: " + ", ".join(missing)


def test_phase0_adr_evidence_map_references_existing_guardrail_tests() -> None:
    text = _adr_text()

    assert "## Evidence Map" in text, "Phase 0 ADR must map invariants to guardrail tests"

    referenced_tests = set(TEST_PATH_RE.findall(text))
    missing_from_adr = sorted(test_path for test_path in REQUIRED_EVIDENCE_TESTS if test_path not in referenced_tests)
    missing_on_disk = sorted(test_path for test_path in referenced_tests if not (ROOT / test_path).is_file())

    assert not missing_from_adr, "Phase 0 ADR evidence map is missing tests: " + ", ".join(missing_from_adr)
    assert not missing_on_disk, "Phase 0 ADR references missing test files: " + ", ".join(missing_on_disk)


def test_full_gui_rearchitecture_plan_testing_matrix_references_existing_tests() -> None:
    text = PLAN_PATH.read_text(encoding="utf-8")

    assert "## Testing Matrix" in text, "Full GUI rearchitecture plan must keep a Testing Matrix section"

    referenced_tests = sorted(set(TEST_PATH_RE.findall(text)))
    missing_on_disk = sorted(test_path for test_path in referenced_tests if not (ROOT / test_path).is_file())

    assert referenced_tests, "Full GUI rearchitecture plan should name concrete test files"
    assert not missing_on_disk, "Full GUI rearchitecture plan references missing test files: " + ", ".join(
        missing_on_disk
    )
