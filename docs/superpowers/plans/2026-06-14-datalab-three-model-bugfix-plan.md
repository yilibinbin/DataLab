# DataLab Three-Model Bugfix Plan

## Goal
Fix all valid bugs found by Codex subagents, Antigravity/Gemini, Claude SDK subagents, and main-thread repros, then restore release readiness with clean imports, clean examples, stable GUI behavior, and non-duplicated formula/rendering boundaries.

## Source Reviews
- Codex subagents: GUI/layout, backend/report/formula, example/workflow.
- Antigravity/Gemini: mostly formula-renderer diff-focused; accepted as review-debt signal for renderer/value-gate/test risks.
- Claude SDK subagents: `job-becbfcc1-e9d8-4405-9a99-06aba7264c21`, full result at `build/reviews/claude-sdk-job-becbfcc1-result.json`.
- Main-thread probes: reproduced stale formula action pages, duplicate function buttons, missing implicit LHS, stale workspace table cells, chained power mismatch, and fitting report formula mismatch.

## Accepted Bug Groups

### P0 Release Blockers
1. Tracked code imports untracked source modules:
   - `datalab_latex/formula_render_service.py` -> `shared/formula_mathtext_png.py`
   - `app_desktop/formula_preview.py` -> `app_desktop/formula_renderer.py`
   - tests -> `shared/formula_export.py`, `shared/formula_latex_export.py`, `shared/expression_registry.py`
2. Worktree contains release-hazard artifacts:
   - `.orig`, `.rej`, patch/diff/review dumps, `.codegraph/`, root-level scratch `test_*.py`.
3. Release matrix does not explicitly guard all new formula/export tests and clean-checkout import behavior.

### P1 Workspace/Data/Examples
1. `_set_table_from_canonical()` preserves old row/column counts and stale cells.
2. GUI examples with fewer columns become polluted by padded/stale `Column 2` / `Column 3`.
3. Error propagation example data and generated formula variables do not match.
4. Statistics example references a missing sigma column.
5. Richardson example uses insufficient data columns and returns no useful result.
6. Header-only blank manual tables can be treated as active user data.

### P1 GUI Formula Workbench/Layout
1. Formula action pages leak stale buttons after mode switches.
2. Custom modes expose duplicate function-support controls.
3. Shared implicit preview omits the implicit variable LHS.
4. User-driven splitter extremes are not covered by current scanner/screenshot gates and can still allow clipping in real interaction.
5. The data-input placement should be revisited: move the existing state-owned manual data editor to the first workbench area if it reduces second-panel crowding, without creating duplicate editors.

### P1 Formula Rendering/Reports
1. Preview metadata mis-renders chained powers such as `a**b**c`.
2. Desktop custom fitting report model lines still use older raw-ish formula formatting.
3. Potential stale PDF preview state after failed PDF compile/preview needs targeted confirmation and either fix or rejection.

### P2 Architecture/Test Debt
1. Two live PNG rendering pipelines/caches duplicate `RenderResult` assembly:
   - `datalab_latex.formula_render_service.render_formula()`
   - `app_desktop.formula_renderer.render_desktop_preview()`
2. Dead/vestigial preview-language code remains:
   - `datalab_core/workbench_model.py::_replace_formula_preview_languages`
   - `app_desktop/workspace_controller.py` `_workbench_formula_preview_languages` plumbing.
3. Value-gate test assertion is weak and uses non-shipping DPI.
4. Some tests pin deprecated no-op shim behavior with misleading names.
5. `docs/TEST_MATRIX.md` prose references stale implicit test files.

## Implementation Plan

### Phase 0: Release-Safety Baseline
Status: complete

1. Add a release hygiene test/tool that fails when tracked files import untracked local modules.
2. Stage/commit intended new source modules or explicitly remove/revert their tracked import users.
3. Clean `.orig/.rej`, scratch `test_*.py`, patch/diff/review dumps, and `.codegraph/` from release worktree, preserving only intentional review artifacts under `build/reviews/` if ignored/untracked.
4. Add clean-checkout smoke commands to the release gate:
   - `python -c "import datalab_latex.formula_render_service"`
   - `python -c "import app_desktop.formula_preview"`
   - focused collection/import of formula/export tests.
5. Update `docs/TEST_MATRIX.md` and `tests/test_release_test_matrix.py` to include new formula/export/registry tests and clean import guards.

Validation:
- `git status --short` contains only intentional tracked changes and no release-hazard debris.
- Clean worktree or clean-copy import smoke passes.
- Release matrix tests pass.

Progress:
- Release import-hygiene tool/test is implemented and indexed.
- Clean import smoke for formula render/preview/export/registry modules is in the release matrix.
- The scanner now handles package facade exports and package-`__init__.py` relative imports without false positives.
- The intended formula renderer/export/registry modules and obsolete TeX-worker deletions are staged in the Git index, making `python tools/release_import_hygiene.py` pass.
- Release-hazard debris cleanup is complete for this phase: tracked root-level `test_*.py` validation scripts were migrated into `tests/` and added to the release matrix; `.orig`, `.rej`, `.codegraph`, patch/diff/review-dump scan found no unignored hazards; the only diff match is ignored `build/reviews/phase0a-staged-review-scope.diff`.
- Remaining untracked files are known prior work (`docs/superpowers/plans/2026-06-13-datalab-reduce3j-formula-rendering-plan.md`, `docs/superpowers/plans/2026-06-14-datalab-formula-renderer-boundary-completion-plan.md`, `tests/test_app_web_extrapolation_latex.py`, `tests/test_app_web_fitting_latex.py`) and were intentionally preserved.

### Phase 1: Workspace Restore and Example Workspaces
Status: complete

1. Add RED tests for `_set_table_from_canonical()` shrinking/clearing row and column counts, headers, stale cells, and constants/manual data sections.
2. Fix `_set_table_from_canonical()` so canonical data is authoritative:
   - clear contents before restore,
   - set row/column counts from canonical rows/headers plus minimum UI defaults,
   - clear trailing items and stale headers,
   - keep one empty row/column only when canonical data is empty.
3. Fix `_active_data_source()` / manual table detection so header-only blank tables are not treated as active manual data.
4. Repair example workspace generation/data:
   - error propagation formula variables match columns,
   - statistics sigma config matches data or example includes sigma,
   - Richardson example has enough columns/data or uses the correct method,
   - fewer-column examples do not acquire stale/padded columns.
5. Regenerate bundled example workspaces and add end-to-end tests that open every example and run its default calculation.

Validation:
- Focused workspace/example tests.
- GUI example open-and-calculate workflow tests.
- Workspace save/open/recalculate with smaller table over larger table.

Progress:
- `_set_table_from_canonical()` now treats canonical workspace data as authoritative: it clears stale table contents/headers, shrinks rows and columns to canonical size, and uses the shared synthetic-header logic for blank/padded headers.
- `_active_data_source()` now ignores header-only blank manual tables in table view, so empty UI defaults no longer masquerade as user input.
- Example workspace generation was repaired so error propagation uses `V1 * V2` with the actual example columns, and statistics uses the `Value` column's parsed bracket uncertainties instead of a missing `Sigma` column.
- Root/fewer-column example restore is covered by a GUI regression that opens a 3-column example first and then a 1-column root example.
- Every bundled example workspace opens as a live template and can run its default calculation from the GUI with LaTeX/plots disabled for test speed.

### Phase 2: GUI Formula Workbench and Splitter Bounds
Status: complete

1. Add RED GUI tests for:
   - switching from self-consistent fitting to custom extrapolation hides implicit output action buttons,
   - custom fitting/extrapolation expose exactly one function-support action,
   - implicit preview displays `u = ...` / `delta = ...` through shared preview metadata,
   - splitter drag/setSizes extremes do not create horizontal scrollbars or clipped required controls.
2. Fix formula action stack ownership:
   - clear/hide inactive action pages on mode/mount switch,
   - ensure action pages are bound to current mounted editor only,
   - remove or hide legacy per-view function buttons when shared workbench controls are mounted.
3. Pass implicit variable LHS into the shared workbench preview metadata for implicit equation mounts.
4. Strengthen splitter clamps:
   - enforce dynamic minimum widths based on required controls,
   - test pathological user-set splitter sizes, not only default scanner sizes,
   - keep left panel usable without horizontal scrollbar.
5. Evaluate moving the existing manual data editor to the first workbench area:
   - relocate, do not duplicate state,
   - preserve `datalab_state_role` ownership,
   - keep save/restore and calculation inputs unchanged.

Validation:
- `tests/test_desktop_workbench_formula_panel.py`
- `tests/test_desktop_gui_workflows.py`
- `tests/test_splitter_persistence.py`
- schema scan plus new user-driven splitter stress tool.
- screenshot capture at desktop and narrow widths.

Progress:
- Existing formula workbench tests cover action-page ownership, one shared function-help button, English self-consistent action overlap, hidden implicit preview controls after mode switches, and formula panel visibility.
- Splitter/layout tests and schema scan cover user-forced minimum splitter sizes and no horizontal scrollbar in the config rail across modes and supported widths.
- Workbench data-area/state-ownership tests cover the relocated manual data editor and prevent duplicate manual data editors.
- No Phase 2 code change was required in this pass because the current implementation already satisfies the accepted plan items.

### Phase 3: Formula Export, Reports, and PDF Failure State
Status: complete

1. Add parity tests proving preview metadata and shared AST export agree for precedence/associativity cases, especially chained powers.
2. Route formula render metadata conversion through shared canonical export consistently, keeping deliberate fallback paths explicit and tested.
3. Update desktop fitting report formula lines to use shared formula export/fallback helpers rather than raw `**` replacement.
4. Decide renderer pipeline consolidation:
   - preferred: factor one shared `metadata -> RenderResult` helper and one cache policy, then make both compatibility APIs call it;
   - acceptable fallback: keep both APIs but add parity tests and document compatibility reason.
5. Align value-gate rendering parameters with shipping `RenderRequest` defaults.
6. Add targeted failed-PDF-compile tests; clear stale PDF preview/path state on failure if confirmed.

Validation:
- Formula export/render service tests.
- Fitting LaTeX writer tests and LaTeX compile smoke.
- Value-gate tests.
- PDF preview failure regression if confirmed.

Progress:
- Web extrapolation LaTeX now threads only custom method formulas into a shared compile-safe formula summary line before the table.
- Web fitting LaTeX now threads the raw core result expression into the report formula summary while keeping CSV stringification separate.
- Both Web report paths reuse `shared.formula_export.inline_formula_summary_or_none()` so empty/legacy `"None"` values are skipped and unsupported expressions use the shared literal fallback.
- The formula renderer value-gate now renders representative evidence with the shipping `RenderRequest` DPI/color defaults and records those values in the JSON report.
- Focused formula/report/PDF validation passed for Web tests, shared formula exporter/rendering tests, LaTeX table/compile tests, and desktop PDF preview/compile UI tests.

### Phase 4: Vestigial Code and Test Cleanup
Status: complete

1. Remove `_replace_formula_preview_languages` if no production caller exists.
2. Remove or reduce `_workbench_formula_preview_languages` controller plumbing; keep only model-layer legacy input tolerance if needed.
3. Rename/update tests that assert deprecated no-op preview-language shims so they describe compatibility tolerance rather than active behavior.
4. Remove stale docs prose and stale references in `docs/TEST_MATRIX.md`.

Validation:
- Workbench model tests.
- Workspace controller tests.
- Docs/release-matrix tests.
- Ruff/compileall for touched files.

Progress:
- Removed the private `_replace_formula_preview_languages()` model helper and dead controller capture/restore sanitizer paths.
- Workspace restore now deletes any stale `_workbench_formula_preview_languages` attribute instead of preserving an empty legacy state container.
- Updated WorkbenchModel/workspace-controller/workspace-IO tests to assert legacy `formula_preview` metadata is read-compatible input only and is not re-saved.
- Updated the Phase 0 ADR guardrail and full GUI plan references to the current single-rendered-preview design and replaced the deleted TeX worker test reference with renderer boundary/value-gate tests.
- Focused workbench model, workspace controller, workspace IO, formula preview, ADR, and release-matrix tests passed.

### Phase 5: Final Quality Gate
Status: complete

1. Run focused suites for all changed areas.
2. Run GUI schema scan and screenshot scan.
3. Run clean import/release hygiene guard.
4. Run `python -m compileall -q` on touched packages.
5. Run `pytest -q` when environment permits; otherwise run documented TEST_MATRIX partitions and record any skipped/impossible parts.
6. Re-run Claude/Gemini/Codex review only on the final diff if the user asks for implementation after this plan.

Progress:
- Full compile, full Ruff, release import hygiene, unstaged diff check, and staged diff check all passed.
- Focused formula/report/Web tests passed: 302 tests.
- Focused LaTeX/PDF tests passed: 69 tests.
- Focused GUI/workspace/schema/model tests passed: 268 tests with one expected duplicate-manifest warning from the duplicate-manifest rejection test.
- GUI schema scan passed for 270 scenarios with `left_panel_no_horizontal_scrollbar=true`, no missing help affordances, and no structured issues.
- GUI screenshot capture produced 18 screenshots at 1440x900, all with `issue_count=0`.
- Full `QT_QPA_PLATFORM=offscreen pytest -q` passed before the final Claude low-finding follow-up: 2577 passed, 9 skipped, 1 expected duplicate-manifest warning.
- After the final Claude low-finding follow-up, the focused value-gate/release-hygiene suite passed: 157 tests, plus scoped Ruff, compileall, release import hygiene, and diff whitespace checks.

## Execution Order
1. Phase 0 first, because release blockers can invalidate every later package/test result.
2. Phase 1 next, because stale table restore contaminates examples and other GUI workflows.
3. Phase 2 next, because it addresses the user-visible GUI defects.
4. Phase 3 next, because formula preview/report consistency depends on the renderer/export boundary.
5. Phase 4 cleanup after behavior is stable.
6. Phase 5 gates before PR/release.

## Non-Goals
- Do not reintroduce LaTeX as calculation input.
- Do not ship WebEngine/MathJax until a separate value-gate proves packaging/runtime benefits.
- Do not create a second manual data editor; relocate the existing state-owned editor only if implementing the layout change.
- Do not treat `.orig/.rej` contents as live code.
