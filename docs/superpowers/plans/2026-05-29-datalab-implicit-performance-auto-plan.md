# DataLab Implicit Performance Auto Optimization Plan

> Status: resynchronized on 2026-05-30 after the second multi-subagent review and Claude adversarial review.
> This file is now the only executable plan for the implicit-performance work. Older task sketches that contradicted the reviewed design have been removed.

## Goal

Make self-consistent / implicit fitting automatically choose the fastest correct backend without exposing backend strategy controls in the GUI.

The fitted objective must remain the user's original output-space residual. Exact residual-space transforms are allowed only for proven constant-affine output maps. Nonlinear inverse forms are seed hints only; they must never replace the original output-space residual.

## Non-Negotiable Rules

- Strategy selection is fully automatic. The GUI exposes resource controls and model settings, not implicit backend strategy choices.
- `implicit_planner` performs side-effect-free classification only: observed-variable eligibility, exact affine transform eligibility, seed-hint eligibility, analytic-derivative eligibility, and SciPy candidate eligibility.
- `FitRunner` owns all side-effecting execution: candidate fit, benchmark, spot-check, rematerialization, fallback metadata, covariance construction, and result diagnostics.
- `details["implicit_strategy"]` reports the route that actually executed. Planned-but-not-executed capabilities must not be reported as executed strategy.
- Strategy, fallback, seed-source, and benchmark diagnostics are advanced/debug metadata. Normal users should not see strategy popups/toasts unless the calculation fails and the message is framed around result correctness.
- `shared.symbolic_math` is the single SymPy parsing boundary for implicit transform, seed-hint, and derivative detectors. Domain modules still validate symbols and runtime compatibility.
- Symbolic detectors must not accept formula syntax that the runtime expression evaluator rejects. Registry drift between symbolic parsing and runtime `safe_eval` must be tested.
- `ImplicitEvaluationCache` belongs to one `ModelSpecification` and one route. Preflight, production, SciPy candidate, spot-check, and rematerialization must use fresh specs/caches or prove complete state restoration.
- Row evaluation must contain or restore point-index state. Warm starts, seed diagnostics, and route diagnostics must not leak across independent specs/routes.
- Constant-affine fast paths must reject non-finite, complex, parameter-dependent, x-dependent, or near-zero slopes.
- Observed-variable and affine fast paths must skip or exactly preserve unweighted `data_sigmas` semantics. If +/- sigma systematic refits are required, use the general mpmath route.
- Low precision (`precision <= 16`) only makes SciPy eligible. It does not force SciPy. SciPy may be accepted only when safety and full-route benchmark gates prove it is correct and not slower for the current route.
- Build/release is not complete until release gates below are satisfied from a clean tracked archive or clean clone.

## Current Implementation State

Implemented foundation on branch `codex/parallel-backend-implementation`:

- Task 0 plan repair was committed as `186c75e`.
- Task 1 local test diffs were committed as `dab9e68`.
- Task 2 regression-frontier foundation was committed as `a5e438f`.
- Task 3a parameter-table GUI polish is staged but not yet committed.
- Shared symbolic parser and planner modules exist.
- Exact affine transform support exists behind conservative gates.
- Seed hints are wired as root-solver hints, not objective transforms.
- Analytic implicit derivatives exist behind parity, residual-quality, singularity, dependent-parameter, and mixed-Jacobian safeguards.
- SciPy implicit support is candidate-gated and benchmarked; the real full-comparator route does not accept SciPy after paying comparator cost for the same run.
- Visible GUI backend strategy controls were removed/neutralized.
- SymPy is collected by `DataLab.spec`, `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1`.
- Worker sigma serialization, custom-fit unweighted `data_sigmas`, implicit SciPy net-cost accounting, implicit unweighted sigma fast-path policy, and pasted uncertainty token preservation have been fixed in recent commits.

Current blockers:

- Worktree still contains staged Task 3a GUI files plus untracked duplicate `" 2"` files. Use strict allowlist staging only.
- The implementation state above is not a correctness claim for merge or release; Task 2b still needs harder regression gates for covariance, parameter errors, weighted/unweighted uncertainty, SciPy selection metadata, and ionization-energy output-space fitting.
- Task 3a must be committed only as a narrow parameter/constant GUI slice, or extended to cover all Task 3 workspace/example gates before claiming Task 3 complete.
- The release gate still needs concrete frozen-bundle smoke and signing/trust evidence.

## Task 0: Worktree Hygiene and Plan Repair

Status: complete. Committed as `186c75e`.

Files:

- `docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md`
- `task_plan.md`
- `findings.md`
- `progress.md`

Steps:

- [x] Run multi-subagent plan review and Claude adversarial review.
- [x] Remove obsolete, copyable Task 1-6 code sketches from this executable plan.
- [x] Record the reviewed current state and non-negotiable rules.
- [x] Review this plan repair with:
  - deep/spec review,
  - code-quality/process review,
  - external Claude adversarial review.
- [x] If reviews pass, commit only this plan repair with explicit path staging.

Verification:

- `git diff -- docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md task_plan.md findings.md progress.md`
- `git diff --cached --name-only` before commit.

## Task 1: Resolve Local Test Diffs

Status: complete. Committed as `dab9e68`.

Purpose:

The current tree has tracked diffs in:

- `tests/test_app_desktop_workers_core.py`
- `tests/test_formula_preview_rendering.py`

Steps:

- [x] Inspect both diffs and decide whether each is aligned with the current objective.
- [x] Treat the `tests/test_app_desktop_workers_core.py` diff as behavior-coupled because it changes existing mocking around observed-implicit fast-path behavior, not just additive coverage.
- [x] Keep aligned test diffs, run focused tests, and review as a small test-only task.
- [x] Do not stage any untracked duplicate `" 2"` files.

Expected verification if kept:

- `pytest -q tests/test_app_desktop_workers_core.py tests/test_formula_preview_rendering.py`
- `ruff check tests/test_app_desktop_workers_core.py tests/test_formula_preview_rendering.py`
- `python -m compileall -q tests/test_app_desktop_workers_core.py tests/test_formula_preview_rendering.py`

Review gate:

- deep/spec review,
- code-quality review,
- Claude adversarial review.

## Task 2: Complete Implicit Regression Frontier

Status: partly complete. Foundation committed as `a5e438f`; Task 2b hardening remains pending after the 2026-05-30 re-review.

Purpose:

Prove the current automatic implicit routes solve the real performance/correctness frontier without changing the fitted objective.

Required regressions:

- Direct `delta` quantum-defect fitting:
  - expected observed-variable or affine route,
  - output-space residuals,
  - weighted, unweighted `data_sigmas`, and no-sigma uncertainty behavior,
  - covariance, `param_errors`, and `param_errors_sys` behavior against the general route where applicable,
  - bounded implicit solve count where the route should avoid per-row root solves.
- Ionization-energy fitting:
  - output expression like `En + R/(n-delta)^2` or equivalent constants,
  - output-space residuals against the energy target, not transformed `delta`,
  - weighted, unweighted `data_sigmas`, and no-sigma uncertainty behavior,
  - covariance, `param_errors`, and `param_errors_sys` behavior,
  - seed hints only affect root-solver initialization,
  - configured seed and warm start beat hints when they converge,
  - hint success after configured/warm failure is explicitly reported.
- SciPy/mpmath automatic selection:
  - `precision <= 16` only makes SciPy eligible and never forces SciPy,
  - unweighted `data_sigmas` skip SciPy when systematic refits are required,
  - after a full mpmath comparator has already been paid for the current run, the run must either reuse the comparator result or reject the SciPy candidate with diagnostics,
  - accepted SciPy candidates must rematerialize fitted curve, output-space residuals, covariance, parameter errors, and fit statistics within explicit tolerances against the guarded mpmath route,
  - fallback metadata must record safety failures, benchmark rejection, sigma-policy skips, and selected comparator fallback.
- Affine transform parity on non-perfect-fit data:
  - compare against general output-space path,
  - verify fitted curve, residuals, chi-square, AIC/BIC, covariance, and parameter errors.
- Formula contract parity:
  - symbolic detector acceptance/rejection matches the runtime `safe_eval` registry as the source of truth for relevant constants and functions,
  - cover `Pi/E/Sin` and lowercase `pi/e/sin` according to the runtime contract.
  - add an architecture guard proving implicit detector modules do not bypass `shared.symbolic_math` with direct SymPy parsing or duplicate formula registries.
- Cache lifecycle:
  - fresh spec/cache for preflight, production, SciPy candidate, spot-check, and rematerialization,
  - no point-index or warm-start leakage across routes.
  - tests must fail if preflight, production, SciPy candidate, spot-check, or rematerialization reuse the same mutable implicit cache unexpectedly.
  - cache invalidation boundaries include data rows, parameters, constants, precision, route, seed source, and SciPy/mpmath backend.

Expected verification:

- Focused implicit tests covering planner, transform, seed hints, derivatives, SciPy candidate, and D8/quantum-defect regressions.
- `ruff check` and scoped `mypy` on changed modules/tests.
- `python -m compileall -q fitting shared app_desktop datalab_latex tests`.

Review gate:

- deep numerical/spec review,
- code-quality review,
- Claude adversarial review.

## Task 3a: Parameter and Constants GUI Slice

Status: in progress. Current staged files:

- `app_desktop/panels.py`
- `app_desktop/parameter_table.py`
- `tests/test_desktop_implicit_model_ui.py`
- `tests/test_parameter_table.py`

Purpose:

Land the narrow GUI improvement that adds manual parameter-row controls and fixes constants-editor visibility, without claiming full Task 3 completion.

Required work:

- Parameter tables for custom and self-consistent fitting expose manual add/remove row controls.
- Auto-detect preserves intentionally added empty rows without polluting `rows()`, `compute_rows()`, orphan state, or parameter config.
- Constants editors for custom and self-consistent fitting hide and restore inputs consistently when disabled/enabled.
- Row-delete semantics are explicit and tested:
  - no selection deletes only an empty trailing row,
  - selected rows may be deleted as an explicit user action,
  - populated rows are never deleted by an accidental no-selection click.
- Empty-row detection is owned by `ParameterTable`; panels must not duplicate cell-scanning logic.
- Multiple empty manual rows either have a documented behavior with tests or are collapsed to one trailing empty row by design.

Expected verification:

- `QT_QPA_PLATFORM=offscreen pytest -q tests/test_parameter_table.py tests/test_desktop_implicit_model_ui.py tests/test_formula_preview_dialog.py`
- `ruff check app_desktop/panels.py app_desktop/parameter_table.py tests/test_desktop_implicit_model_ui.py tests/test_parameter_table.py`
- `mypy app_desktop/parameter_table.py`
- `python -m compileall -q app_desktop/panels.py app_desktop/parameter_table.py tests/test_desktop_implicit_model_ui.py tests/test_parameter_table.py`

Review gate:

- deep product/spec review,
- code-quality review,
- Claude adversarial review.

## Task 3b: GUI and Workspace Polish

Status: pending.

Purpose:

Make the automatic backend usable without exposing implementation strategy controls.

Required work:

- Formula preview becomes an explicit preview action for self-consistent equation and output expression.
- Formula preview must not force the left configuration pane width or make splitters unusable.
- Preview contrast must work on light and dark app palettes.
- MCMC or unrelated sections must not show stray implicit formula previews.
- Parameter table behavior from Task 3a remains accepted and covered while completing the broader workspace polish.
- Constants editor behavior from Task 3a remains accepted and covered while completing the broader workspace polish.
- Custom fitting and self-consistent fitting must use a named shared parameter/constant normalization API. The shared path must cover table view, text view, disabled constants, reserved-name validation, workspace restore, and compute-path serialization.
- Add or update a built-in quantum-defect implicit example workspace.
- Example workspaces are read-only templates: modifying them requires Save As / custom path and must not mutate the bundled template.
- Workspaces must not persist any implicit backend strategy selector.
  - Saved and checked-in workspaces must not contain `implicit_strategy`, backend selector fields, or user-visible `enable_new_implicit_backend` controls.

Expected verification:

- GUI/unit tests for formula preview sizing, preview dialog/action, constants visibility, parameter add/remove, workspace round trip, and example-template read-only behavior.
- Negative workspace tests proving no implicit backend strategy selector is persisted.
- Checked-in quantum-defect implicit example workspace opens as a read-only template and requires Save As after modification.
- Manual GUI smoke after tests pass.

Review gate:

- deep product/spec review,
- code-quality review,
- Claude adversarial review.

## Task 4: Parallel Backend Continuation

Status: pending.

Purpose:

Continue the broader backend parallelization plan only after implicit fitting is stable and reviewed.

Required work:

- If `docs/superpowers/plans/2026-05-28-datalab-parallel-backend-implementation-plan.md` is committed by then, re-read it and reconcile it with current implicit backend changes.
- If that parallel-backend plan is still untracked, either commit it through its own reviewed docs task or reconstruct the parallel-backend continuation requirements from tracked code, `task_plan.md`, `findings.md`, `progress.md`, and current git history before implementation.
- Keep resource controls centralized and reusable across modules.
- Avoid per-module duplicate process/thread management.
- Do not reintroduce GUI backend strategy toggles.
- Name and enforce the shared backend boundary before adding new parallel call sites. New code must not create ad hoc process/thread pools or bypass the shared runner/config path.
- Worker payloads, preferences, and stale workspace inputs must route through the unified backend even if they contain old `enable_new_implicit_backend=False` data.

Review gate:

- deep architecture/spec review,
- code-quality review,
- Claude adversarial review.

## Task 5: Release Gate

Status: pending and blocking public release.

Release builds must be produced from a clean tracked archive or clean clone. Release prep fails if duplicate `" 2"` files are present in the build source.

Release-only checks may be skipped only by marking the release blocked. An environment skip for macOS smoke, Windows smoke, signing, notarization, Authenticode verification, manifest signing, or pinned-download verification is not a pass and must not produce public release assets.

Release order is mandatory:

1. Commit reviewed changes with explicit allowlist staging.
2. Push branch and create/review PR.
3. Merge to `main`.
4. Tag or otherwise identify the release commit on `main`.
5. Build macOS and Windows assets from a clean clone or clean tracked archive of that release commit.
6. Sign, notarize, staple, and verify macOS assets.
7. Authenticode-sign and verify Windows assets.
8. Generate update metadata from final uploaded assets only.
9. Verify uploaded asset size/hash by downloading from GitHub.
10. Publish release notes without local paths, private hosts, or local-server descriptions.

Required release evidence:

- Legacy backend cleanup:
  - delete `_execute_fit_job_payload_subprocess_legacy()` and remove `ParallelConfig.enable_new_implicit_backend`, or add a short tracked ADR explaining why each compatibility surface must remain and how it is tested,
  - an ADR instead of deletion must be gated by an existing or new regression proving stale `enable_new_implicit_backend=False` inputs route through the unified backend,
  - stale workspaces/preferences/payloads with `enable_new_implicit_backend=False` must still route through the unified backend until the compatibility field is removed.
- Source verification:
  - full or agreed broad test suite,
  - `ruff check`,
  - scoped/broad `mypy` where configured,
  - `python -m compileall -q`.
- macOS frozen smoke:
  - build `.app`/DMG from clean source,
  - launch app,
  - open an implicit example workspace,
  - run direct `delta` and ionization-energy implicit fits,
  - verify no extra GUI process opens during fitting,
  - verify formula preview and workspace Save As behavior.
- Windows frozen smoke:
  - build remotely on Windows from clean source,
  - launch `.exe`/installer result,
  - run the same implicit example smoke,
  - verify no extra GUI process opens during fitting.
- Signing/trust:
  - macOS Developer ID signing and notarization evidence, including `spctl` and package/app verification where applicable,
  - Windows Authenticode signing evidence, including `signtool verify`,
  - update manifest signing verification, or omit auto-installable assets from `updates.json`.
  - unsigned `updates.json` may link to the release page or manually downloaded signed assets, but must not drive silent or automatic installation.
- Build-time downloads:
  - release builds must use pre-provisioned dependencies or pinned hash/signature verification for every external download.
  - release prep must record dependency provenance for standalone Python, wheel caches or lockfiles, and any build-time downloads; missing provenance blocks public release.

Review gate:

- release/process review,
- code-quality review of packaging/updater changes,
- Claude adversarial release review.

## Staging Rules

- Never use `git add .`.
- Stage only explicit paths for the current task.
- Before every commit:
  - `git status --short`,
  - `git diff --cached --name-only`,
  - verify no `" 2"` duplicate file is staged.

## Completion Definition

This objective is complete only when:

- all pending tasks above are implemented or intentionally split into a separate accepted plan,
- each task has deep/spec review, code-quality review, and Claude adversarial review,
- review findings are fixed or explicitly rejected with technical evidence,
- verification commands pass with current output,
- worktree is clean except ignored/local artifacts explicitly excluded from release,
- branch is merged/pushed as requested,
- macOS and Windows release assets pass the release gate if a public release is requested.
