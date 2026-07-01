# DataLab GUI Rearchitecture ADR

Date: 2026-06-10

## Status

Accepted for phased implementation. The full rearchitecture plan has passed
the recorded Codex, Gemini/Antigravity, and Claude no-actionable-findings
planning gates, and implementation proceeds only through the phase gates below.
This ADR authorizes the guardrailed headless-core-first migration path; it does
not authorize a shipping QtWebEngine path, packaging changes, or release
publication without their separate gates.

## Context

DataLab currently ships as a PySide6 Qt Widgets desktop application with a
Flask web surface. The desktop workbench has been polished with shared formula,
variable, and result panels, but durable state still largely lives in widgets
and window attributes. The project also has strict constraints that are more
important than toolkit choice:

- high-precision numerical behavior;
- workspace compatibility;
- killable/cancellable long-running jobs;
- offline startup and update behavior;
- macOS and Windows PyInstaller packaging;
- bilingual desktop GUI gates;
- one state owner per editable datum.

QtWebEngine and a component web workbench remain possible, but the current
packaging scripts explicitly exclude WebEngine modules. A browser-based view
therefore requires a measured spike before it can become a shipping path.

## Decision

The rearchitecture proceeds headless-core-first:

1. Keep Qt Widgets as the shipping desktop view until parity and packaging gates
   prove a replacement.
2. Introduce `datalab_core` as a PySide-free layer for job builders, canonical
   results, session/job orchestration, `WorkbenchModel`, and workspace adapters.
3. Execute the formula-rendering plan as a prerequisite, with a pure
   `datalab_latex` render service and Qt/web adapters only. Formula preview
   uses one rendered style; legacy `ui.formula_preview` metadata is reader-only compatibility state and is not written by current workspaces.
4. Keep workspace v1 writing as the default. Add v2 reading through
   `shared.workspace_io` version dispatch before any v2 writer is enabled.
5. Treat QtWebEngine as a timeboxed spike with a default NO-GO outcome unless
   packaging, bridge security, offline assets, CI/display, artifact size, and
   CJK/IME gates all pass.

## Invariants

- `datalab_core` must not import PySide6.
- Compute input values cross UI, model, service, and process boundaries as
  source strings or explicitly typed high-precision payloads, not JSON floats.
- All mpmath precision changes go through `shared.precision.precision_guard()`.
- In-process mpmath jobs remain single-flight unless a later design proves
  isolated precision contexts.
- Existing subprocess kill/timeout/cancellation behavior remains intact.
- `MODE_WORKBENCH_SPECS`, `shared/ui_specs.py`, and `shared/help_specs.json`
  remain the schema/help sources of truth.
- Formula preview uses a single rendered style. Legacy `ui.formula_preview`
  metadata is ignored during model/controller restore, is not re-saved, and
  does not rewrite compute formulas, config, or workspace hashes.
- Workspace v1 read compatibility is permanent. The v1 writer/export path
  remains available through the transition and may only be removed or narrowed
  by a future ADR and release-compatibility plan.
- No WebEngine bridge may expose arbitrary file, shell, or network access.
- No startup network access is allowed unless the user enabled update checks.
- `datalab_core` may import only Qt-free, side-effect-safe shared modules.
  Qt-coupled shared helpers such as `shared/settings_store.py`,
  `shared/presets.py`, `shared/ui_keyguards.py`, and `shared/pdf_preview*.py`
  are off-limits to core imports unless their Qt-free portions are extracted
  first. Other impure shared helpers such as `shared/latex_engine.py` are also
  off-limits because they perform network/download and filesystem work that
  conflicts with the offline, deterministic core boundary.

## Required Gates

- The active full rearchitecture plan has reached the required no-actionable-
  findings review state. Broad implementation must still proceed phase by
  phase and keep every gate below green.
- Full current local release gate remains green before and after each phase.
- Phase 0 must characterize the existing web surface before Phase 2 migrates
  `app_web`: current POST route contracts, SSE behavior, precision-lock
  concurrency, and offline/static formula resources.
- Workspace v1 parity tests cover legacy auto-fit, implicit schemas, root
  migration, result snapshot state, failed/empty-success overviews, and example
  template behavior.
- Web precision/concurrency tests cover POST and SSE paths under the same
  service-level precision contract as desktop.
- Formula-rendering gates cover both desktop and web adapters, so web formula
  preview cannot keep an independent parser/render pipeline without an
  explicit temporary compatibility exception and removal gate.
- Packaging tests normalize and compare Qt exclude lists across `DataLab.spec`,
  `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1`.
- A WebEngine spike must measure artifact size, signing/notarization impact,
  helper binaries, updater impact, offline behavior, CJK/IME input, and CI
  coverage before any shipping decision.

## Evidence Map

The Phase 0 invariants above are backed by guardrail tests. This map is not a
complete test inventory; it pins the minimum evidence that must stay connected
to the ADR before later service/model/view migration proceeds.

- Core purity and Qt-free shared boundaries:
  `tests/test_core_no_qt_imports.py`
- Precision-guard-only mpmath mutations:
  `tests/test_phase0_precision_guardrails.py`
- Desktop single-flight run/cancel and worker request construction:
  `tests/test_phase0_desktop_guardrails.py`
- String-only/high-precision request payload boundaries:
  `tests/test_datalab_core_parallel_options.py`
- Workbench model hash and UI-only formula-preview state boundaries:
  `tests/test_datalab_core_workbench_model.py`
- Workspace v1 compatibility, legacy fixtures, and snapshot restore:
  `tests/test_workspace_legacy_fixtures.py`, `tests/test_workspace_io.py`
- Web POST/SSE/docs/schema/resource baseline characterization:
  `tests/test_app_web_baseline_contracts.py`,
  `tests/test_app_web_docs_baseline.py`,
  `tests/test_app_web_route_inventory.py`,
  `tests/test_app_web_fitting_uncertainty.py`,
  `tests/test_app_web_precision_concurrency.py`,
  `tests/test_app_web_sse_baseline.py`,
  `tests/test_web_sse_streaming.py`,
  `tests/test_web_sse_fit_endpoint.py`,
  `tests/test_app_web_formula_resources_baseline.py`,
  `tests/test_openapi_spec.py`,
  `tests/test_web_theme_toggle.py`,
  `tests/test_web_plot_generation.py`,
  `tests/test_web_api_smoke.py`
- Web startup and security hardening:
  `tests/test_web_server_startup_smoke.py`,
  `tests/test_r10_c2_secret_key_not_hardcoded.py`,
  `tests/test_security_get_config_value_no_app_context.py`,
  `app_web/test_security.py`
- Optional Web collaboration surface:
  `tests/test_collaborate_session.py`,
  `tests/test_collab_integration.py`
- Packaging/WebEngine NO-GO and artifact-size evidence:
  `tests/test_packaging_qt_excludes.py`,
  `tests/test_release_artifact_sizes.py`,
  `tests/test_webengine_shipping_import_guard.py`,
  `tests/test_webengine_measurement_evidence.py`,
  `tests/test_webengine_asset_evidence_tool.py`,
  `tests/test_webengine_spike_assets.py`,
  `tests/test_webengine_spike_contract.py`,
  `tests/test_webengine_spike_report.py`,
  `tests/test_webengine_evidence_bundle_tool.py`
- Offline-friendly updater behavior:
  `tests/test_update_checker.py`, `tests/test_update_controller.py`
- Release-gate drift prevention:
  `tests/test_release_test_matrix.py`,
  `tests/test_phase0_adr_guardrails.py`

## Consequences

- A toolkit swap is intentionally delayed. The first value delivery is lower
  duplication, safer precision boundaries, and testable workspace behavior.
- The web surface can later reuse the same services instead of mirroring
  desktop orchestration.
- The current Qt GUI remains releasable throughout the migration.
- The WebEngine decision becomes reversible and evidence-based rather than a
  hidden packaging surprise.

## Deferred

- LaTeX as a computable model language.
- WebEngine as the default desktop UI.
- Workspace v2 writer as the default.
- Removing Qt Widgets before parity and rollback gates pass.
