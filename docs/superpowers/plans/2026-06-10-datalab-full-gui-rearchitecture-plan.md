# DataLab Full GUI Rearchitecture Plan

## Status

This plan is the current Task 19 planning artifact. It supersedes the first
draft that treated QtWebEngine as the preferred direction before proving it can
ship.

Primary planning source:

- Claude for Codex was rerun with the concrete model requested by the user:
  `--model claude-fable-5 --effort max`.
- The fable 5 smoke test returned `PASS` and identified model
  `claude-fable-5`.
- The full fable 5 planning pass completed and intentionally did not read this
  plan, so its architecture recommendation is independent.

Review state:

- Codex found five accepted blockers in the first draft. They are integrated
  here.
- Gemini 3.1 Pro found three accepted blockers after quota recovery. They are
  integrated here:
  - `ui.formula_preview[*]` persistence had a phase-ordering deadlock;
  - Phase 0 lacked web surface characterization before Phase 2 service
    extraction;
  - Phase 1 did not explicitly route web formula rendering through the shared
    render service.
- Claude fable 5 final synthesis returned accepted medium/low findings, which
  are integrated here. The post-fix Claude follow-up and micro follow-up both
  returned `PASS` with no remaining actionable findings.
- Implementation may proceed only through the phased gates below, starting with
  low-risk Phase 0 characterization and guardrails before service/model/view
  migration.

## Goal

Move DataLab from a Qt Widgets form-heavy desktop application toward a modern,
professional scientific workbench while preserving:

- exact numerical precision behavior;
- existing fitting, root solving, uncertainty, statistics, plotting, LaTeX,
  workspace, updater, packaging, and example behavior;
- one state owner per editable datum;
- current `.datalab` workspace compatibility;
- macOS and Windows release gates.

The goal is not to switch toolkits for its own sake. The first architectural
target is a UI-neutral service/model core that makes the current Qt view
maintainable and later makes a web/QtWebEngine view possible if the packaging
and security spike passes.

## Current Repository Facts

### Desktop UI

- The desktop UI is PySide6 Qt Widgets.
- `app_desktop/window.py` owns `ExtrapolationWindow` and mixes in domain
  behavior from data, extrapolation, fitting, statistics, LaTeX/PDF, images,
  i18n, updater, and workspace helpers.
- `app_desktop/panels.py` still builds most UI imperatively by mutating window
  attributes.
- The current branch has already added shared workbench adapters:
  `workbench_formula_panel.py`, `workbench_variable_panel.py`,
  `workbench_results.py`, and theme/card helpers. These mount existing widgets
  rather than creating new state owners.
- `app_desktop/workbench_specs.py::MODE_WORKBENCH_SPECS` already describes
  formula mounts and state-owner mounts per mode. It is descriptor metadata,
  not a durable state model.
- Runtime GUI gates already enforce many invariants through
  `tools/scan_desktop_gui_schema.py`, screenshot captures, bilingual inventory,
  and workbench tests.

### Web Surface

- `app_web/` already exists as a Flask application with blueprints, templates,
  static JS/CSS, CSRF/security support, SSE, and web-specific computation glue.
- Web logic still mirrors desktop orchestration instead of calling a shared
  service layer.
- Current `app_web/templates/base.html` has web formula-rendering assets and
  static JS paths that must become local/offline resources before any embedded
  web workbench can ship.

### Workers and Precision

- Long-running desktop jobs are typed in `app_desktop/workers_core.py` and
  wrapped by Qt threads in `app_desktop/workers_qt.py`.
- Killable subprocess isolation exists for selected work, including
  self-consistent fitting and root solving paths.
- `shared/parallel_backend.py::KillableProcessTaskRunner` owns the
  terminate/join/kill escalation behavior.
- `multiprocessing.freeze_support()` is already required before Qt imports in
  frozen apps.
- `mpmath.mp.dps` is process-global. New code must use
  `shared.precision.precision_guard()` and must not mutate `mp.dps` directly.
- Values crossing future UI/service/model boundaries must remain strings or
  typed high-precision values. JSON floats are not allowed for compute inputs.

### Workspace

- `shared/workspace_schema.py` currently accepts only
  `datalab.workspace.v1` / `schema_version == 1`.
- `app_desktop/workspace_controller.py::capture_workspace()` still writes
  `datalab.workspace.v1`.
- `.datalab` files are hardened ZIP archives with strict manifest and
  attachment validation.
- `compute_workspace_hash()` controls result snapshot freshness and must remain
  stable for v1-equivalent compute state.

### Formula Rendering

- Current inline preview is a Qt adapter over matplotlib mathtext after
  ad-hoc expression conversion.
- The separate plan
  `2026-06-10-datalab-formula-rendering-and-workbench-polish-plan.md` is a
  mandatory prerequisite. It defines one pure formula render service outside
  `app_desktop`, render-only LaTeX support, and an optional async sandboxed TeX
  path.

### Packaging

- `DataLab.spec`, `build_mac_data_gui.sh`, and
  `build_windows_data_gui.ps1` explicitly exclude `PySide6.QtWebEngineCore`,
  `PySide6.QtWebEngineWidgets`, `PySide6.QtWebEngineQuick`,
  `PySide6.QtWebChannel`, `PySide6.QtWebSockets`, `PySide6.QtPdf`, and other
  large Qt modules.
- Any WebEngine direction must remove exclusions in all packaging entry points
  and measure artifact size, signing/notarization impact, helper binaries,
  updater impact, and CI feasibility before it is allowed into a shipping path.

## Architecture Decision

### Recommended Direction

Adopt a headless-core-first architecture:

```text
datalab_core/
  jobs.py              pure job builders and request DTOs
  results.py           canonical result envelopes and adapters
  session.py           cancellation/progress/job orchestration
  workbench_model.py   observable UI-neutral state model
  workspace_v1.py      model <-> current v1 manifest adapter
  workspace_v2.py      future reader-first v2 adapter

datalab_latex/
  formula_render_service.py

app_desktop/
  bridge_qt.py         Qt signal/thread adapter over datalab_core
  views/               later per-mode Qt views bound to WorkbenchModel

app_web/
  later adapters over datalab_core and WorkbenchModel
```

Keep Qt Widgets as the shipping view while the service/model extraction is
underway. Treat QtWebEngine as a measured, reversible spike, not as the default
implementation path.

### Why This Is Safer

- It fixes the real maintainability problem: widget-owned state and duplicated
  orchestration.
- It preserves current release and offscreen GUI test gates.
- It keeps numerical behavior under existing Python backends.
- It makes future web or embedded web views view-layer decisions instead of a
  risky rewrite of compute, workspace, and packaging at the same time.

## Non-Negotiable Constraints

- `datalab_core` must not import PySide6. Add an import-purity test.
- Views must not own durable compute state. They bind to `WorkbenchModel`.
- `MODE_WORKBENCH_SPECS`, `shared/ui_specs.py`, and `shared/help_specs.json`
  remain the schema/help sources of truth.
- Formula syntax selectors are preview-only UI state. They do not rewrite
  compute formulas, config, or workspace hashes.
- All compute-relevant numeric payloads stay as source strings until parsed
  under `precision_guard()`.
- In-process mpmath jobs stay single-flight unless a later design proves
  isolated precision contexts.
- Existing subprocess kill, timeout, progress, and cancellation behavior must
  be preserved.
- Workspace v1 reading and writing remain available during the transition.
- Workspace v1 read compatibility is permanent. The v1 writer/export path
  remains available through the transition and may only be removed or narrowed
  by a future ADR and release-compatibility plan.
- No WebEngine, WebChannel, remote assets, or browser bridge is allowed in a
  shipping app until the explicit spike gates pass.
- No network access on startup unless the user enabled update checking.
- `datalab_core` may import only Qt-free, side-effect-safe `shared/` modules.
  Qt-coupled shared modules, including `shared/settings_store.py`,
  `shared/presets.py`, `shared/ui_keyguards.py`, and
  `shared/pdf_preview*.py`, are off-limits to core imports unless a future ADR
  first extracts their Qt-free portions. Other impure shared modules such as
  `shared/latex_engine.py` are also off-limits because they perform
  network/download and filesystem work that conflicts with the offline,
  deterministic core boundary.

## Phased Plan

### Phase 0: Baseline Freeze and Release Characterization

Goal: establish a measurable green baseline before architecture work starts.

Tasks:

1. Finish or explicitly shelve the current GUI workbench polish branch.
2. Run the current release gate and record:
   - `python -m compileall -q .`
   - `python -m ruff check ...`
   - `QT_QPA_PLATFORM=offscreen pytest -q`
   - `QT_QPA_PLATFORM=offscreen python tools/scan_desktop_gui_schema.py`
   - `QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900`
3. Record current macOS and Windows artifact sizes.
4. Add an ADR documenting invariants:
   - no duplicate state owners;
   - `precision_guard()` only;
   - v1 workspace writability;
   - string-only compute payloads;
   - offline startup;
   - packaging/resource budget;
   - one i18n/help/schema source.
5. Add characterization tests for current job construction, result snapshots,
   single-flight execution, and workspace hash stability if missing.
6. Add web baseline characterization before any `app_web` service migration:
   - Flask route contract tests for the current POST surfaces;
   - SSE endpoint smoke and error-path tests for current `/api/fit/stream`
     behavior;
   - web precision-lock regression tests proving current POST and SSE routes
     restore `mp.dps` and do not cross-contaminate concurrent requests;
   - static resource/offline checks for existing web formula-rendering assets
     so later service migration has a measured baseline.

Gate G0:

- Current branch is green under the existing gate.
- Artifact sizes are recorded.
- Invariants are documented and testable.
- Web POST/SSE/resource characterization is green and recorded before Phase 2
  touches `app_web/logic/*` or routes.

### Phase 1: Formula Render Service Prerequisite

Goal: complete the approved formula-rendering plan before broad UI rewrites.

Tasks:

1. Keep formula preview as a single rendered style:
   - legacy `ui.formula_preview` metadata remains reader-only compatibility
     input;
   - current v1 workspace adapters must not persist preview-language state;
   - Formula UI code may not invent workspace paths for preview-language state.
2. Create `datalab_latex/formula_render_service.py`.
3. Make `app_desktop/formula_preview.py` a Qt adapter over PNG bytes/metadata.
4. Delegate `datalab_latex/expression_engine.py::format_latex_formula()` to
   the same render service or shared helper.
5. Make the web surface consume the same render service or deliberately remove
   its duplicate formula-rendering path:
   - existing web JS may remain only as a thin view adapter or fallback around
     service output;
   - any separate parser/converter logic in web assets must be deleted,
     replaced, or documented as a temporary compatibility exception with a
     removal gate;
   - add tests proving desktop and web render the same sanitized expression
     metadata for representative DataLab/Python/LaTeX inputs.
6. Keep LaTeX render-only.
7. Add optional high-fidelity TeX preview only as an async sandboxed path:
   no network, no auto-install, isolated temp cwd, no user filenames,
   process-group kill, timeout, cache, raster fallback.

Gate G1:

- Formula service tests pass.
- Inline preview never shells out to TeX.
- High-fidelity backend is mocked/deterministic in CI.
- Changing preview syntax does not alter compute text, config, or hash.
- Web formula preview no longer owns a divergent parser/render pipeline, or the
  remaining compatibility exception is explicitly timeboxed and tested.

### Phase 2: Service Layer Extraction

Goal: remove duplicated desktop/web orchestration while keeping the Qt UI
behavior unchanged.

Tasks:

1. Create canonical request/result dataclasses:
   - `datalab_core/jobs.py`
   - `datalab_core/results.py`
2. Move job-building logic out of desktop mixins into pure builders:
   - extrapolation;
   - uncertainty propagation;
   - statistics;
   - fitting, including custom and self-consistent fitting;
   - root solving.
3. Add `datalab_core/session.py::SessionService`:
   - `submit()`, `cancel()`, status, log, progress, result, failure callbacks;
   - preserve current worker/subprocess semantics;
   - enforce single-flight in-process execution;
   - keep process-boundary paths killable.
4. Add `app_desktop/bridge_qt.py` to deliver core callbacks as Qt signals on
   the GUI thread.
5. Keep `app_desktop/workers_qt.py` as a compatibility shim while migration is
   incremental.
6. Adapt one mode at a time behind focused tests.
7. Later adapt `app_web/logic/*` and API routes to the same services.
8. Define a shared precision/concurrency contract for desktop and web before
   either surface is adapted:
   - desktop keeps one in-process compute flight at a time unless a future
     isolated precision design is proven;
   - web preserves its current synchronized mpmath behavior for POST and SSE
     routes;
   - input strings are materialized into `mp.mpf` or typed values only inside
     `precision_guard()`;
   - JSON floats are not allowed for compute inputs;
   - concurrent desktop/web tests must prove `mp.dps` is restored and requests
     cannot cross-contaminate precision.

Gate G2:

- Service outputs match current worker outputs through golden tests.
- Cancellation and timeout parity tests pass.
- `mp.dps` does not leak or change on the submitting GUI thread.
- Concurrent web POST/SSE requests preserve precision and source-string inputs
  under the same service-level contract.
- No `float()` conversion exists at service/model input boundaries except for
  display/plotting code explicitly marked as lossy output adaptation.
- `datalab_core` imports without PySide6.

### Phase 3: WorkbenchModel With v1-Compatible Persistence

Goal: stop using live widgets as the durable state model without breaking
existing workspaces.

Tasks:

1. Create `datalab_core/workbench_model.py`.
2. Store compute-relevant values as strings and structured DTOs.
3. Separate:
   - `compute.formulas[*].raw_text`;
   - `compute.parameters`;
   - `compute.constants`;
   - `compute.options`;
  - legacy `ui.formula_preview` metadata as read-compatible UI-only input;
   - panel/tab/splitter/zoom UI state;
   - result snapshot state.
4. Adopt and expand the Phase 1 formula preview compatibility contract:
   - the model ignores legacy `ui.formula_preview` metadata for current UI;
   - workspace adapters keep v1 read compatibility but do not re-save those fields;
   - formula UI adapters expose one rendered preview style;
   - if Phase 1 intentionally kept syntax selection session-only, Phase 3 is
     the first phase allowed to turn on persistence;
   - any change to these paths requires main-thread interface review.
5. Add a binder from current Qt widgets to model paths using existing schema
   keys and `datalab_state_role` metadata.
6. Extend scanner gates to detect:
   - missing model bindings;
   - duplicate model-path bindings;
   - cloned editable state widgets.
7. Route `capture_workspace()` and `restore_workspace()` through the model
   while still writing `datalab.workspace.v1`.
8. Add v1 parity tests:
   - canonical JSON parity where possible;
   - `compute_workspace_hash()` parity excluding UI-only fields;
   - example workspace open/save behavior unchanged.
9. Add permanent legacy workspace fixtures before the model becomes
   authoritative:
   - obsolete auto-fit migration/degradation;
   - implicit fitting schema 1 and schema 2;
   - root-solving `auto` mode migration/normalization;
   - snapshot-only result workspaces and template unlock behavior;
   - durable overview states for tabular, plot, text, plot+text,
     empty-success, failed, and stale snapshots;
   - bundled example-template save-as behavior.

Gate G3:

- v1 workspaces round-trip through the model.
- v1 writer remains default.
- Examples open as live templates.
- UI-only formula preview settings never affect compute hash.
- Existing workspace tests remain green.

### Phase 4: Reader-First Workspace v2

Goal: introduce a future model-native workspace format without stranding old
installs.

Tasks:

1. Add a v2 reader that maps a model-native manifest into `WorkbenchModel`.
2. Add a manifest-version dispatch point in `shared.workspace_io` after shared
   ZIP member, path, symlink, size, and archive-size checks but before the
   current v1-only manifest validation chain. The dispatch must fork the whole
   post-ZIP validation path for each schema version: manifest validation,
   attachment path collection, and attachment hash verification. A standalone
   v2 reader under `datalab_core` is not enough because ordinary "Open
   Workspace" flows through `shared.workspace_io.read_workspace()`.
3. Keep hostile archive checks shared across v1 and v2.
4. Add a v2 `.datalab` fixture read through the real public IO path.
5. Keep the writer on v1 for at least one transition release.
6. Add v2 fixtures and migration tests.
7. Keep permanent v1 fixtures.
8. Add a v2 writer only behind an explicit feature flag after v2-capable
   readers have shipped.
9. Keep `shared.workspace_io.write_workspace()` v1-only unless the explicit v2
   writer flag is active.
10. Never silently rewrite a v1 file to v2 on ordinary save.

Gate G4:

- v1 and v2 readers work.
- v1 writer still works.
- v2 writer is disabled by default.
- Hash and result snapshot semantics are documented and tested.

### Phase 5: Qt View Modernization Through the Model

Goal: reduce `panels.py` and mode-specific imperative UI while keeping the
shipping app in Qt Widgets.

Tasks:

1. Create `app_desktop/views/` per-mode views.
2. Generate or bind forms from `shared/ui_specs.py` and
   `MODE_WORKBENCH_SPECS`.
3. Migrate modes in lowest-risk order:
   - statistics;
   - uncertainty/error propagation;
   - extrapolation;
   - root solving;
   - fitting;
   - self-consistent/implicit fitting.
4. Delete old mode pages only after each new mode passes all gates.
5. Keep current user-facing workflows, examples, docs, and screenshots current.
6. Move remaining inline styles into `app_desktop/theme.py`.
7. Add modern workbench affordances only when model-backed:
   - better formula preview;
   - constants/parameters summaries;
   - result overview driven by real run state;
   - command palette or action search if justified;
   - run history only if backed by real `SessionService` events.

Gate G5:

- Per-mode scanner and screenshot gates pass.
- No duplicate state-owner issues.
- Bilingual inventory passes.
- Workspace round-trip passes for each migrated mode.
- Old mode code is deleted as each mode is replaced.

### Phase 6: QtWebEngine / Component Workbench Spike

Goal: decide whether an embedded web workbench is shippable. The default
decision is **default NO-GO** unless every measurement and security gate passes.

Tasks:

1. Prototype a `QWebEngineView` host in an isolated branch.
2. Use only local vendored assets. No CDN. No runtime network requirement.
3. Prefer a custom URL scheme over `file://` or local HTTP.
4. If using `QWebChannel`, expose only a whitelisted bridge:
   - workspace open/save;
   - job submit/cancel/status;
   - examples/docs;
   - update check where already allowed;
   - export actions.
5. Add bridge security tests:
   - remote URL denial;
   - CSP;
   - no file URL access;
   - method allowlist;
   - input validation;
   - no arbitrary shell/file bridge.
6. Vendor MathLive/KaTeX/MathJax or chosen assets locally.
7. Remove QtWebEngine exclusions in `DataLab.spec`,
   `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1` only inside the
   spike branch.
8. Measure:
   - macOS artifact size delta;
   - Windows artifact size delta;
   - cold start time;
   - memory usage;
   - macOS signing/notarization helper behavior;
   - Windows signing/helper behavior;
   - updater artifact size and install behavior;
   - CI/display requirements;
   - CJK/IME input quality.

Gate G6:

- GO only if:
  - size delta is within an agreed budget;
  - offline/no-network test passes;
  - bridge security tests pass;
  - CI can exercise the view;
  - macOS and Windows packaging smoke passes;
  - IME/CJK input is acceptable.
- If any requirement fails, keep Qt Widgets as the shipping view and retain
  only the measured spike report.

### Phase 7: Optional Web Workbench Port

Goal: if G6 passes, build a component web workbench as a second view over
`WorkbenchModel` and `SessionService`.

Tasks:

1. Build first in `app_web` with local assets and service APIs.
2. Add Playwright E2E and visual snapshot gates.
3. Add DOM duplicate-owner checks analogous to the Qt scanner.
4. Embed in desktop only after web and packaging gates pass.
5. Keep Qt Widgets fallback for one release cycle.
6. Flip default only after parity.

Gate G7:

- Full module parity with Qt view.
- Workspace v1/v2 compatibility.
- Full release gate green on macOS and Windows.
- Documented rollback path.

### Phase 8: Legacy Retirement

Goal: remove maintenance burden only after replacement views are shipped and
stable.

Tasks:

1. Retire old `panels.py` sections gradually.
2. Keep native shell, updater, file associations, release flow, and workspace
   readers.
3. Remove old scanner paths only when replacement gates prove equal or better
   coverage.
4. Keep v1 reader permanently.

## Testing Matrix

Required tests and current coverage files:

- `tests/test_core_no_qt_imports.py` as a transitive purity check: import
  `datalab_core` in a clean interpreter, assert `PySide6` is absent from
  `sys.modules`, and assert the named off-limits shared modules are absent
  from `sys.modules`;
- core DTO, job-builder, result-envelope, and precision-boundary coverage:
  - `tests/test_datalab_core_dtos.py`
  - `tests/test_datalab_core_statistics.py`
  - `tests/test_datalab_core_extrapolation.py`
  - `tests/test_datalab_core_uncertainty.py`
  - `tests/test_datalab_core_root_solving.py`
  - `tests/test_datalab_core_fitting.py`
  - `tests/test_datalab_core_parallel_options.py`
  - `tests/test_phase0_precision_guardrails.py`
- desktop service/session bridge coverage:
  - `tests/test_app_desktop_bridge_qt.py`
  - `tests/test_app_desktop_workers_core.py`
  - `tests/test_phase0_desktop_guardrails.py`
- `tests/test_app_web_baseline_contracts.py`
- `tests/test_app_web_sse_baseline.py`
- `tests/test_app_web_precision_concurrency.py`
- `tests/test_app_web_formula_resources_baseline.py`
- workspace model, workspace parity, and v2 reader compatibility coverage:
  - `tests/test_datalab_core_workbench_model.py`
  - `tests/test_workspace_io.py`
  - `tests/test_workspace_controller.py`
  - `tests/test_workspace_auto_fit_migration.py`
  - `tests/test_workspace_implicit_round_trip.py`
  - `tests/test_workspace_legacy_fixtures.py`
- formula-render tests from the formula plan:
  - `tests/test_formula_render_service.py`
  - `tests/test_expression_engine_formula_rendering_integration.py`
  - `tests/test_formula_preview_rendering.py`
  - `tests/test_formula_preview_dialog.py`
  - `tests/test_formula_renderer_boundary.py`
  - `tests/test_formula_renderer_value_gate.py`
- scanner binding-completeness and shared schema/help tests:
  - `tests/test_desktop_gui_schema_scan.py`
  - `tests/test_desktop_gui_redesign_scan.py`
  - `tests/test_desktop_bilingual_inventory.py`
  - `tests/test_desktop_ui_schema_binder.py`
  - `tests/test_desktop_ui_schema_runtime.py`
  - `tests/test_desktop_editor_affordances.py`
  - `tests/test_desktop_shared_ui_specs.py`
- packaging exclude-list parser/sync tests that normalize and compare the Qt
  exclusions in `DataLab.spec`, `build_mac_data_gui.sh`, and
  `build_windows_data_gui.ps1`:
  - `tests/test_packaging_qt_excludes.py`
- WebEngine spike bridge/security/offline tests, only if spike proceeds:
  - `tests/test_webengine_shipping_import_guard.py`
  - `tests/test_webengine_spike_assets.py`
  - `tests/test_webengine_spike_contract.py`
  - `tests/test_webengine_spike_report.py`
  - `tests/test_webengine_asset_evidence_tool.py`
  - `tests/test_webengine_measurement_evidence.py`
  - `tests/test_webengine_evidence_bundle_tool.py`

Existing gates to retain:

- full `pytest -q`;
- compileall;
- ruff;
- GUI schema scan;
- screenshot matrix;
- bilingual inventory;
- docs/resource packaging tests;
- workspace tests;
- numerical reference tests;
- macOS and Windows frozen smoke before release.

## Subagent Ownership After Approval

Only after Codex, Gemini, and Claude are clean:

- Core agent: `datalab_core/jobs.py`, `results.py`, `session.py`; no PySide6.
- Workspace agent: `workbench_model.py`, `workspace_v1.py`,
  `workspace_v2.py`, and workspace controller adapters.
- Formula agent: execute the formula-rendering plan in `datalab_latex` plus Qt
  and web adapter updates. It may not invent workspace/model paths for preview
  syntax; legacy `ui.formula_preview` metadata is reader-only compatibility
  input and must not be re-saved by current workspace adapters.
- Web agent: owns Phase 0 web baseline tests for Flask POST route contracts,
  SSE behavior, precision-lock concurrency, and offline/static formula
  resources; owns Phase 2 `app_web/logic/*` and route adaptation to
  `SessionService`. It must coordinate with the Formula agent for formula
  preview adapters and with the Gate agent for Playwright/visual checks.
- Qt views agent: `app_desktop/views`, binder integration, theme migration.
- Packaging agent: PyInstaller spec, macOS/Windows build scripts, updater
  smoke, exclude-list sync, resource bundling.
- Gate agent: scanner, screenshot, bilingual inventory, Playwright if needed,
  TEST_MATRIX updates.

Interface changes must land through the plan/ADR first. Downstream agents may
not edit upstream contracts without main-thread reconciliation.

## Risks

- QtWebEngine may be too large or too hard to sign/notarize reliably.
- WebEngine may require CI/display infrastructure not currently available.
- A browser bridge can accidentally become a privileged file/shell API if not
  whitelisted and tested.
- Workspace v2 writer can break older installs if enabled too early.
- Moving job builders can accidentally introduce float conversion or precision
  leakage.
- Allowing concurrent in-process jobs can corrupt mpmath precision.
- Deleting `panels.py` sections can break hidden `getattr(self, attr)`
  dependencies.
- Maintaining Qt and web views simultaneously can duplicate logic unless the
  model/service boundary is complete first.

## Deferred

- LaTeX as a computable model language.
- Bundling or auto-downloading TeX for formula preview by default.
- Tauri/Electron/native web rewrite.
- Default WebEngine UI before the spike passes.
- Workspace v2 writer as default.
- Removing Qt Widgets before parity and rollback gates pass.

## Review Checklist

Codex, Gemini, and Claude should challenge this plan against:

1. Is QtWebEngine correctly downgraded from preferred direction to measured
   spike?
2. Does service/model extraction preserve worker cancellation, subprocess kill,
   timeout, progress, and `mp.dps` behavior?
3. Are all UI/service/model numeric boundaries string-safe?
4. Does workspace v2 sequencing avoid breaking existing users?
5. Is formula rendering integrated as one pure service, not duplicated in
   desktop/web paths?
6. Are compute formula text and preview syntax state separated?
7. Are no-duplicate-state-owner guarantees mechanically tested?
8. Are packaging excludes/resources tracked in all macOS/Windows build files?
9. Are release gates explicit enough to catch GUI, packaging, precision,
   workspace, and updater regressions?
10. Is subagent ownership concrete enough to prevent overlapping edits?
