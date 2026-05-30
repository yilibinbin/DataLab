# DataLab Implicit Performance Auto Optimization Plan

> Status: resynchronized on 2026-05-30 after multi-subagent reviews, earlier Claude adversarial reviews, and the user-authorized Codex adversarial replacement gate for Task 4d/4e while the external Claude CLI gate was unavailable.
> This file is now the only executable plan for the implicit-performance work. Older task sketches that contradicted the reviewed design have been removed.

## Goal

Make self-consistent / implicit fitting automatically choose the fastest correct backend when a route can prove correctness and net runtime benefit without exposing backend strategy controls in the GUI.

The fitted objective must remain the user's original output-space residual. Exact residual-space transforms are allowed only for proven constant-affine output maps. Nonlinear inverse forms are seed hints only; they must never replace the original output-space residual.

Correctness is the first gate. A faster route may be selected only when validation cost is included in the current-run decision or amortized by a documented cache/calibration mechanism. A SciPy candidate that already required a full mpmath comparator in the same run must reuse that comparator result or reject the candidate; reporting that route as the fastest executed backend is not allowed.

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
- Low precision (`precision <= 16`) only makes SciPy eligible. It does not force SciPy. SciPy may be accepted only when safety and benchmark/calibration gates prove it is correct and faster after validation cost is counted. Until such a gate exists, the full-comparator route must return or reuse the comparator result instead of accepting SciPy after paying both costs.
- Build/release is not complete until release gates below are satisfied from a clean clone of the release commit. Archive-based releases require a separate reviewed manifest/hash verification procedure first.

## Current Implementation State

Implemented foundation on branch `codex/parallel-backend-implementation`:

- Task 0 plan repair was committed as `186c75e`.
- Task 1 local test diffs were committed as `dab9e68`.
- Task 2 regression-frontier foundation was committed as `a5e438f`.
- Task 3a parameter-table GUI polish was committed as `13fe7fa`.
- Task 2b uncertainty-regression hardening was committed as `6fca8b0`.
- Shared symbolic parser and planner modules exist.
- Exact affine transform support exists behind conservative gates.
- Seed hints are wired as root-solver hints, not objective transforms.
- Analytic implicit derivatives exist behind parity, residual-quality, singularity, dependent-parameter, and mixed-Jacobian safeguards.
- SciPy implicit support is candidate-gated and benchmarked; the current real full-comparator route does not accept SciPy after paying comparator cost for the same run. Task 2c below must either add a real low-net-cost acceptance/calibration mechanism or explicitly keep SciPy as a rejected candidate with evidence.
- Visible GUI backend strategy controls were removed/neutralized.
- SymPy is collected by `DataLab.spec`, `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1`.
- Worker sigma serialization, custom-fit unweighted `data_sigmas`, implicit SciPy net-cost accounting, implicit unweighted sigma fast-path policy, and pasted uncertainty token preservation have been fixed in recent commits.
- Task 3b example-workspace synchronization and formula-preview layout/contrast slices were committed as `220c73b` and `19582f1`.
- Task 2c implicit regression evidence and SciPy selection semantics were committed as `f670ce2`.
- Task 4 fit-worker process-boundary guard/equivalence work is complete through `4414d58`: entry gate `fea5b14`, plan sync `c209f11`, payload/static guards `4050fb8`, serial/process equivalence `7571c65`, and stale auto-fit backend toggle removal `4414d58`.
- User-facing auto-fit has been removed and is guarded by `tests/test_auto_fit_removed.py`; the stale `enable_new_auto_fit_backend` config field was removed in `4414d58`.

Current blockers:

- Worktree still contains untracked duplicate `" 2"` files and local draft source files. Use strict allowlist staging only. Release builds must use a clean clone and must fail on any untracked source artifact, not only duplicate `" 2"` paths.
- Task 2c evidence matrix, behavioral cache-boundary matrix, and SciPy decision have passed review and were committed as `f670ce2`.
- Task 3c shared fitting-input normalization is complete as `9376da5`.
- Task 4 fit-worker backend-boundary and equivalence gates are complete through `4414d58`. This does not close the separate Task 2c direct cache identity/state-restoration release blocker, and it does not claim full-program migration of every existing thread helper to `shared/parallel_backend.py`.
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

Status: foundation complete for the reviewed hardening slices. Foundation committed as `a5e438f`; uncertainty and architecture-regression hardening committed as `6fca8b0`. The full release-blocking evidence matrix remains open and is tracked by Task 2c.

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

## Task 2c: Close Implicit Regression Evidence and SciPy Selection Semantics

Status: complete for the reviewed Task 2c slice. Release and new parallel-backend expansion remain blocked by the direct cache identity/state-restoration gate below.

Purpose:

Turn the Task 2 regression frontier into an auditable evidence matrix and close the gap between "correctness-first candidate rejection" and the stated "fastest correct backend" goal.

Required work:

- [x] Add an evidence matrix in this plan or a tracked companion artifact that maps every Task 2 required regression to:
  - test file and test name,
  - verification command,
  - last observed result,
  - commit or current diff that provides the evidence,
  - whether it blocks release.
  - Existing committed regressions should be cataloged rather than duplicated. New implementation in Task 2c is required only for missing oracle/cache rows and the SciPy acceptance/calibration decision.
- [x] Add a quantum-defect numerical oracle row to the matrix:
  - direct `delta` and ionization-energy output-space scenarios,
  - reference or synthetic known-parameter recovery tolerances,
  - residual sign and unit assertion: residuals are fitted output minus observed target in the target's output space,
  - weighted, unweighted `data_sigmas`, and no-sigma behavior,
  - executed `details["implicit_strategy"]` and fallback metadata.
- [x] Add or update the cache-lifecycle evidence matrix so each boundary is explicit:
  - preflight vs production,
  - production vs SciPy candidate,
  - SciPy candidate vs spot-check,
  - spot-check vs rematerialization,
  - route/backend/precision/parameter/constant/data-row/seed-source invalidation.
- [ ] Add direct object-identity/state-leak tests for preflight, production, SciPy candidate, spot-check, and rematerialization before release or before expanding new parallel-backend call sites. Current Task 2c evidence covers behavior and fresh factory threading; it does not claim exhaustive identity proof for every mutable cache instance.
- [x] Decide and implement the SciPy acceptance path:
  - either add a real low-net-cost calibration gate, such as cached comparator reuse or sampled calibration whose validation cost is included in the decision,
  - or explicitly keep SciPy as a rejected candidate for current full-comparator runs and update user/debug metadata so the plan no longer claims current-run fastest-route selection where it is not true.
- [x] Preserve output-space residuals, covariance, parameter errors, chi-square/AIC/BIC, fallback metadata, and unweighted `data_sigmas` behavior in covered routes. The non-perfect ionization-energy regression compares analytic output-space fit statistics, fitted curve, and residuals against a forced numeric output-space route.
- [x] Add tests proving any accepted SciPy route is faster after validation cost is counted, or proving the current route rejects SciPy and reuses/returns the comparator instead.

Expected verification:

- Focused implicit tests covering the evidence matrix rows.
- `pytest -q tests/test_implicit_scipy_backend.py tests/test_implicit_performance_regression.py tests/test_implicit_d8_runner_regression.py tests/test_fitting_runner_scipy_fallback.py`
- `ruff check fitting tests/test_implicit_scipy_backend.py tests/test_implicit_performance_regression.py`
- scoped `mypy` on changed modules/tests where configured.
- `python -m compileall -q fitting shared tests`

Review gate:

- deep numerical/spec review,
- code-quality review,
- Claude adversarial review.

## Task 3a: Parameter and Constants GUI Slice

Status: complete. Committed as `13fe7fa`.

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

Status: complete. Example-workspace synchronization and formula-preview layout/contrast slices were committed as `220c73b` and `19582f1`.

Completed slice:

- Example-workspace synchronization and read-only template Save As behavior are implemented and reviewed.
- `quantum-defect-implicit.datalab` is generated, checked in, listed in the desktop examples menu, and tested byte-for-byte against the generator.
- The quantum-defect example uses inline ionization-energy data and exercises the `analytic_implicit_output_space` route; that route is the self-consistent `delta` ionization-energy output-space fit, not the easy observed-`delta` target.
- Checked-in/generated/Save As workspaces are tested not to persist GUI backend strategy selectors.
- Opening a checked-in example through the examples menu, ordinary Open, or file-association-style `open_workspace_path()` treats it as a template; Save routes through Save As and saving to the bundled example path is refused.
- Formula-preview layout and contrast regressions are covered: implicit previews are button/dialog-only, long formulas do not expand the left splitter, dark palettes keep a high-contrast preview surface, and non-self-consistent/MCMC UI states do not expose implicit preview controls.

Purpose:

Make the automatic backend usable without exposing implementation strategy controls.

Required work:

- Formula preview becomes an explicit preview action for self-consistent equation and output expression.
- Formula preview must not force the left configuration pane width or make splitters unusable.
- Preview contrast must work on light and dark app palettes.
- MCMC or unrelated sections must not show stray implicit formula previews.
- Parameter table behavior from Task 3a remains accepted and covered while completing the broader workspace polish.
- Constants editor behavior from Task 3a remains accepted and covered while completing the broader workspace polish.
- Add or update a built-in quantum-defect implicit example workspace.
  - Generator, checked-in `.datalab` archive, desktop example list, and tests must stay synchronized.
  - The example must store data inline with no private/local file paths.
  - The primary example must cover ionization-energy output-space fitting using the self-consistent `delta` equation and constants such as `CR` and `M`; a direct `delta` observed-variable example may exist only as an additional clearly named variant.
  - Example metadata variants must use documented tokens and tests must assert the expected variants.
- Example workspaces are read-only templates: modifying them requires Save As / custom path and must not mutate the bundled template or silently save to an ephemeral temp copy.
  - Opening an example must mark the workspace as template-derived.
  - Plain Save on a template-derived workspace must route to Save As.
  - Save As to a user path must clear the template-derived state; later Save may write that user path.
  - Tests must prove the bundled example hash/mtime does not change and, if a temp copy is used internally, plain Save does not write that temp copy.
- Workspaces must not persist any implicit backend strategy selector.
  - Saved and checked-in workspaces must not contain `implicit_strategy`, backend selector fields, or user-visible `enable_new_implicit_backend` controls.
- Formula preview must be explicit and bounded:
  - self-consistent equation and output expression expose preview buttons/dialogs only; inline rendered pixmap/label previews must not remain in the left configuration pane,
  - long formulas must not increase the left pane minimum width or make the main splitter unusable,
  - light and dark palettes must keep rendered formulas, fallback text, and error messages readable,
  - switching to MCMC or any non-self-consistent model must not show or route implicit preview controls.

Expected verification:

- GUI/unit tests for formula preview sizing, preview dialog/action, splitter width, dark/light contrast, constants visibility, parameter add/remove, workspace round trip, and example-template read-only behavior.
- Negative workspace tests proving no implicit backend strategy selector is persisted in generated manifests, checked-in archives, and Save As output.
- Checked-in quantum-defect implicit example workspace opens as a read-only template, requires Save As after modification, and round-trips without local paths.
- Fitting smoke proving the example configuration runs the intended ionization-energy output-space implicit route with weighted uncertainties.
- Manual GUI smoke after tests pass.

Review gate:

- deep product/spec review,
- code-quality review,
- Claude adversarial review.

## Task 3c: Shared Fitting-Input Normalization

Status: complete. Committed as `9376da5`.

Purpose:

Replace duplicated custom-fit and self-consistent-fit input parsing with one named shared normalization boundary. This is a maintainability and correctness task; it must remove drift rather than adding another copy.

Owner module:

- `app_desktop/fitting_input_normalization.py` is the committed production normalization boundary from `9376da5`; future changes must keep it wired rather than reintroducing parallel parsing paths.

Required API contract:

- Provide one public entry point for full fitting-input preparation, for example `normalize_fitting_input(...) -> NormalizedFittingInput`. Parameter-only or constants-only helpers may exist only as internals or widget adapters; they are not sufficient to complete this task.
- Define immutable DTOs for:
  - model type,
  - expression / implicit equation / output expression,
  - variable mapping and target-column identity,
  - parameter rows and compute config,
  - constants rows/text state and compute dict,
  - implicit definition draft state,
  - uncertainty policy with `data_sigmas`, `weights`, and weighted/unweighted/no-sigma semantics,
  - validation diagnostics and localized error text,
  - workspace-serializable persisted state,
  - worker-payload-safe serialized state where needed.
- The API must distinguish persisted/draft state from compute state:
  - manual empty rows and unnamed draft rows are preserved for the GUI/workspace,
  - orphan rows do not enter compute config,
  - disabled constants preserve draft rows/text but produce an empty compute dict,
  - disabled parameter constraints ignore fixed/min/max for compute without deleting drafts.
- Constants syntax must match the same uncertainty-aware grammar used by error propagation without making the normalization core depend on LaTeX/reporting modules. This was resolved in `9376da5` by moving the shared grammar behind `shared/uncertainty.py`.
- Ordering requirement for future rewrites: keep the uncertainty grammar in `shared/` or an equivalent non-reporting boundary before wiring desktop, web, workspace, or worker consumers to it.
- Validation errors must preserve the current bilingual behavior. Shared normalization may accept a message provider or return structured error codes, but it must not regress existing Chinese/English `_dual_msg()` cases to English-only messages.
- Workspace migration and restore must be lossless for supported schemas. Malformed legacy rows must fail loudly or surface explicit migration diagnostics; the normalizer must not silently drop non-dict rows, falsy numeric values, constants text, disabled-state drafts, or constraint drafts.
- Uncertainty handling has a single boundary, for example `normalize_data_uncertainty(headers, rows, sigma_rows, target_column, explicit_sigma_column, weighted)`.
  - This boundary is the only code that interprets embedded uncertainty tokens, explicit sigma/err columns, weighted mode, unweighted `data_sigmas`, and no-sigma behavior.
  - Worker serialization may preserve and round-trip normalized sigma values, but must not reinterpret token syntax or create a second uncertainty grammar.

Replacement map:

- `app_desktop/parameter_table.py`
  - `parameter_config()` delegates to the shared API.
  - UI-only row ownership, selection, and display behavior remain in `ParameterTable`.
- `app_desktop/constants_editor.py`
  - table/text parsing, `constants_dict()`, disabled state, and reserved-name validation delegate to the shared API.
  - editor widgets remain responsible only for presentation and state capture.
- `app_desktop/window_data_mixin.py`
  - `_resolve_uncertainties()` and `_build_weight_vector()` either delegate to the shared uncertainty boundary or are reduced to UI/dataframe adapters that call it.
- `app_web/logic/fitting.py`
  - must use the same shared uncertainty grammar or be explicitly documented as out of scope with a tracked rationale before Task 3c can complete.
  - direct parsing imports from report/LaTeX modules are not allowed after the shared grammar boundary exists.
- `app_desktop/window.py` and `app_desktop/window_fitting_models_mixin.py`
  - custom fitting and self-consistent fitting compute paths call the full fitting-input normalizer before building `ModelProblem`, `FitJob`, or worker payloads.
  - `_collect_custom_parameter_config()`, `_collect_implicit_parameter_config()`, `_collect_custom_constants()`, and `_collect_implicit_constants()` may remain only as adapter methods that delegate to the normalized DTO.
- Workspace capture/restore paths
  - custom fitting and self-consistent fitting both serialize through the same persisted DTOs,
  - stale workspaces migrate without losing draft rows/text or constraints-disabled state,
  - round trips do not introduce backend strategy fields.
- Fit job construction and worker payloads
  - compute config, constants, `data_sigmas`, `weights`, and serialized uncertainty values are produced through the shared API,
  - worker deserialization must not reimplement incompatible parsing.

Required tests:

- Failing-first unit tests for the shared API must be added before production wiring.
- Unit tests for the shared API:
  - constraints enabled/disabled,
  - manual empty rows and unnamed drafts,
  - orphan filtering,
  - duplicate/invalid/reserved names,
  - constants table/text views,
  - disabled constants preserving drafts but computing `{}`,
  - uncertainty tokens, explicit sigma columns, weighted/unweighted/no-sigma cases.
- Tests for localized errors:
  - missing uncertainty for weighted fitting,
  - zero/negative uncertainty,
  - no uncertainty data,
  - invalid parameter/constant value,
  - each case must preserve both language halves or structured message codes that the UI renders bilingually.
- Integration tests proving both custom fitting and self-consistent fitting use the same normalized output for equivalent inputs.
- Workspace tests for capture, restore, migration, Save As, and round trip.
- Worker payload round-trip tests for uncertainty tokens and sigma values.
- Architecture guard proving:
  - the shared normalizer has production imports before it is committed,
  - `ParameterTable.parameter_config()`, `ConstantsEditor.constants_dict()`, workspace coercion/config helpers, and data-uncertainty helpers are removed or reduced to delegation,
  - custom and self-consistent fitting compute paths cannot bypass the shared normalizer.

Expected verification:

- `pytest -q tests/test_fitting_input_normalization.py tests/test_parameter_table.py tests/test_constants_editor.py tests/test_constants_text_view.py tests/test_workspace_implicit_round_trip.py tests/test_app_desktop_workers_core.py`
- `QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_implicit_model_ui.py tests/test_workspace_controller.py tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py`
- Web/logic tests covering `app_web/logic/fitting.py` if it remains a consumer of uncertainty-token parsing.
- GUI tests touched by custom/self-consistent fitting collection.
- `ruff check app_desktop/fitting_input_normalization.py app_desktop/parameter_table.py app_desktop/constants_editor.py app_desktop/window.py app_desktop/window_fitting_models_mixin.py app_desktop/window_data_mixin.py app_web/logic/fitting.py`
- scoped `mypy` on changed modules where configured.
- `python -m compileall -q shared app_web/logic/fitting.py app_desktop/fitting_input_normalization.py app_desktop/parameter_table.py app_desktop/constants_editor.py app_desktop/workspace_controller.py app_desktop/workers_core.py`

Review gate:

- deep architecture/spec review,
- code-quality review,
- Claude adversarial review.

## Task 4: Parallel Backend Continuation

Status: complete through `4414d58` for the scoped fit-worker process boundary. Entry gate, backend-boundary tests, raw worker payload tests, serial/process equivalence tests, and stale auto-fit backend toggle removal are committed. PR, merge, and release remain blocked by Task 5, including the still-open Task 2c direct cache identity/state-restoration proof.

Purpose:

Continue the broader backend parallelization plan only after implicit fitting is stable and reviewed.

Required work:

- [x] Entry gate: delete `_execute_fit_job_payload_subprocess_legacy()` and remove `ParallelConfig.enable_new_implicit_backend`, or add a tracked ADR explaining the external compatibility requirement and a regression proving stale `enable_new_implicit_backend=False` inputs still route through the unified backend. This gate must be complete before adding new parallel call sites.
- [x] Delete the legacy self-consistent hook branch (`_fit_self_consistent_with_legacy_hooks` / `_self_consistent_hooks_replaced`) so self-consistent fits always route through the unified `FitRunner` path.
- [x] Preserve stale-input compatibility by ignoring old serialized/settings `enable_new_implicit_backend=False` fields and proving no public `ParallelConfig` attribute remains.
- Treat untracked `docs/superpowers/plans/2026-05-28-datalab-parallel-backend-implementation-plan.md` as historical reference only, not as executable input. Any still-valid requirement must be folded into this tracked plan through a reviewed docs task before implementation.
- Keep resource controls centralized and reusable across modules.
- Avoid new per-module duplicate process/thread pool management. The Task 4 static guard covers process pools, executor pools, and fit-worker process primitives; it does not yet migrate every pre-existing helper such as direct `threading.Thread` usage in unrelated model-selection code.
- Do not reintroduce GUI backend strategy toggles.
- `shared/parallel_backend.py` is the only production module permitted to create process/thread pools. New execution code must route through `KillableProcessTaskRunner` or `ParallelMapExecutor` and shared config, not ad hoc primitives.
- Worker payloads, preferences, and stale workspace inputs must route through the unified backend even if they contain old `enable_new_implicit_backend=False` data.
- Parallel worker payloads must be raw, serializable input payloads only. They must not pickle, pass, cache, or reuse:
  - `ModelSpecification`,
  - implicit evaluator closures,
  - `ImplicitEvaluationCache`,
  - route diagnostics,
  - mutable warm-start or point-index state.
- Each worker execution must rebuild `ModelSpecification` and implicit caches inside the worker from normalized input payloads.
- Complete the direct cache identity/state-restoration gate from Task 2c before adding any new parallel call site. The already-committed legacy deletion is the only Task 4 work exempt from this ordering rule.
- Serial and process backends must produce equivalent results for direct custom fits and self-consistent fits across:
  - precision `<= 16` and high precision,
  - constants,
  - configured seed, warm start, and hint-source cases,
  - SciPy candidate/fallback and mpmath routes,
  - cancellation followed by retry,
  - repeated runs proving no cache or diagnostics leakage.

Task 4 slices:

- [x] Task 4a: synchronize this tracked plan with `f670ce2` and `fea5b14`; remove phantom test references and untracked-plan dependencies. Committed as `c209f11`.
- [x] Task 4b: add a committed static guard test, for example `test_no_ad_hoc_parallel_primitives_outside_shared_backend`, scanning tracked production fit-worker/process-pool surfaces and allowing new process/executor pool primitives only through `shared/parallel_backend.py`. Committed as part of `4050fb8`. Pre-existing unrelated helpers such as direct `threading.Thread` usage in model-selection code are out of this Task 4 scope unless they are promoted into a future full-program parallel-governance cleanup.
- [x] Task 4c: add worker payload contract tests, for example `test_fit_job_payload_contains_only_raw_serializable_inputs`, recursively asserting `_serialize_fit_job()` contains only raw `None/bool/int/float/str/list/tuple/dict` values and no `ModelSpecification`, `ImplicitEvaluationCache`, callables, Qt objects, `mp.mpf`, diagnostics objects, or mutable warm-start/point-index state. Committed as part of `4050fb8`.
- [x] Task 4d: add serial-vs-process equivalence tests. Committed as `7571c65` after the user-authorized Codex adversarial replacement gate because the external Claude CLI gate was unavailable:
  - `test_custom_fit_serialized_payload_is_equivalent_low_precision_with_constants`,
  - `test_custom_fit_serialized_payload_is_equivalent_high_precision_with_constants`,
  - `test_self_consistent_serial_and_process_are_equivalent_low_precision_scipy_candidate_fallback`,
  - `test_self_consistent_serial_and_process_are_equivalent_high_precision_mpmath`,
  - `test_self_consistent_process_cancel_then_retry_matches_clean_serial_baseline`,
  - `test_self_consistent_repeated_process_runs_do_not_leak_cache_or_diagnostics`,
  - `test_self_consistent_worker_rebuilds_model_spec_and_cache_inside_child`,
  - a worker DTO consistency test proving `variable_map`, `variable_data`, `target_series`, and single-variable `x_series/y_series/sigma_series` do not drift.
- [x] Task 4e: remove `enable_new_auto_fit_backend` if auto-fit remains deleted, or add a tracked ADR and stale-settings routing tests explaining why the hidden compatibility field remains. Removed and committed as `4414d58`.

Required equivalence assertions:

- Compare `params`, `param_errors`, `param_errors_sys`, covariance where available, `fitted_curve`, residuals, chi-square, reduced chi-square, AIC, BIC, RMSE, R2, `details["implicit_strategy"]`, optimizer backend, fallback metadata, and residual sign/space.
- Low precision (`precision <= 16`) must remain SciPy-eligible only, not SciPy-forced. Subprocess and serial paths must both return/reuse the comparator or mpmath fallback for current full-comparator runs.
- Unweighted `data_sigmas` must skip SciPy where systematic refits are required and preserve nonzero systematic parameter-error behavior.
- Cancellation followed by retry must prove worker budget/depth is released and `mp.dps`, route diagnostics, warm-start state, cache state, seed source, and point index do not leak into the retry.
- Repeated process runs must prove diagnostics do not accumulate and results match a fresh serial baseline.

Expected verification:

- `pytest -q tests/test_parallel_backend.py tests/test_app_desktop_workers_core.py tests/test_implicit_fit_worker_cancellation.py tests/test_auto_fit_removed.py tests/test_parallel_preferences.py` passed after Task 4e with 94 tests.
- `pytest -q tests/test_implicit_scipy_backend.py tests/test_implicit_performance_regression.py tests/test_implicit_d8_runner_regression.py tests/test_fitting_runner_scipy_fallback.py` passed after Task 4e with 30 tests.
- The committed static guard test replaces the previous manual grep-only guard.
- `ruff check` and `python -m compileall -q` passed on the changed Task 4 backend/worker/test modules.

Review gate:

- deep architecture/spec review: passed for Task 4 slices.
- code-quality review: passed for Task 4 slices.
- adversarial review: passed for Task 4d/4e through the user-authorized Codex replacement gate because the external Claude CLI gate was unavailable. This substitution is task-local and does not imply external Claude passed.

## Task 5: Release Gate

Status: pending and blocking public release.

Release builds must be produced from a clean clone of the release commit. Release prep fails if any untracked source artifact or duplicate `" 2"` file is present in the build source. A `git archive` export may be used only after a separate manifest/hash verification procedure is written and reviewed; until then, use clean clones only.

Release-only checks may be skipped only by marking the release blocked. An environment skip for macOS smoke, Windows smoke, signing, notarization, Authenticode verification, manifest signing, or pinned-download verification is not a pass and must not produce public release assets.

Source hygiene gate before any release build:

```bash
git status --porcelain=v1 --untracked-files=all
git ls-files --others --exclude-standard
git diff --cached --name-only
```

Acceptance: the release build source is a clean clone with no untracked files. If using the development worktree for preflight only, any untracked source draft or path containing `" 2"` blocks release and must not be copied into the build source.

Untracked-source guard for release sources:

```bash
test -z "$(git ls-files --others --exclude-standard)"
```

Acceptance: the command exits successfully in the release source. Development-worktree preflight may additionally grep for duplicate `" 2"` paths for convenience, but release acceptance is the stronger rule: no untracked source files at all.

Release order is mandatory:

1. Commit reviewed changes with explicit allowlist staging.
2. Before any push or PR, run the staged/branch pre-push source audit below. In the dirty development worktree, untracked artifacts are a staging risk to inspect and must not be staged. A hard untracked-file gate applies only in a clean review worktree/clean clone and in release sources.
3. Push branch and create/review PR only after the audit passes.
4. Merge to `main`.
5. Tag or otherwise identify the release commit on `main`.
6. Build macOS and Windows assets from a clean clone of that release commit.
7. Sign, notarize, staple, and verify macOS assets.
8. Authenticode-sign and verify Windows assets.
9. Upload signed assets to a draft release.
10. Download the uploaded assets back from GitHub and verify size, hash, signature, notarization/staple status, and Authenticode signature.
11. Generate update metadata only from the downloaded-back, verified assets.
12. Sign or otherwise verify the update manifest, upload it, then download it back and verify hash/signature.
13. Publish release notes without local paths, private hosts, or local-server descriptions.

Pre-push source audit:

- `git diff --cached --name-only` must exactly match the task-specific allowlist before commit.
- `git diff --name-only origin/main...HEAD` and the PR file list must contain only reviewed task files.
- `git diff --cached --name-only` and the PR file list must contain no duplicate `" 2"` paths, `.superpowers/`, `dist/`, `build/`, `__pycache__/`, local full-review scratch lists, or unrelated update/packaging drafts.
- Scan the staged diff and branch diff for local filesystem paths, private hosts, localhost release descriptions, secrets/tokens, internal AI/process artifacts, and temporary build machine paths. Any match blocks push until reviewed or removed.
- Scan untracked artifacts in the development worktree before staging and record known unrelated hits in `progress.md`; these hits block staging/release-source copying, not necessarily branch push from this dirty development checkout.
- For PR/release hard proof, repeat the branch audit in a clean review worktree or clean clone where `git ls-files --others --exclude-standard` must be empty.

Per-task exact allowlist template:

```bash
test -s "$TASK_ALLOWLIST" || { echo "TASK_ALLOWLIST must point to the reviewed current-task file list" >&2; exit 2; }
tmp_allowed="$(mktemp)"
cp "$TASK_ALLOWLIST" "$tmp_allowed"
tmp_staged="$(mktemp)"
tmp_diff="$(mktemp)"
git diff --cached --name-only | sort > "$tmp_staged"
sort "$tmp_allowed" > "$tmp_allowed.sorted"
comm -3 "$tmp_allowed.sorted" "$tmp_staged" > "$tmp_diff"
test ! -s "$tmp_diff"
```

Local planning files `findings.md`, `progress.md`, and `task_plan.md` are intentionally ignored by `.gitignore`; update them for recovery, but do not include them in public commit allowlists unless the user explicitly asks to publish process notes.

Pre-push staged and branch artifact scan:

```bash
artifact_name_pattern='(^|/)(\.superpowers|dist|build|__pycache__)(/|$)| 2(\.|$)|FULL_FILE_REVIEW_FILELIST|update_.* 2| 2\.md$'
git diff --cached --name-only | rg "$artifact_name_pattern" && exit 1 || true
git diff --name-only origin/main...HEAD | rg "$artifact_name_pattern" && exit 1 || true

content_pattern='(/Users/|/var/folders/|localhost|127\.0\.0\.1|apm8517|backup-windows|OPENAI_API_KEY|GITHUB_TOKEN|ghp_|private host|temporary local server)'
git diff --cached -- . \
  ':(exclude)docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md' \
  | rg -n "$content_pattern" && exit 1 || true
git diff origin/main...HEAD -- . \
  ':(exclude)docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md' \
  | rg -n "$content_pattern" && exit 1 || true
```

Development-worktree untracked artifact inspection:

```bash
artifact_name_pattern='(^|/)(\.superpowers|dist|build|__pycache__)(/|$)| 2(\.|$)|FULL_FILE_REVIEW_FILELIST|update_.* 2| 2\.md$'
git ls-files --others --exclude-standard | rg "$artifact_name_pattern" || true
```

Record any expected unrelated hits in `progress.md`. Do not stage them. In a clean review worktree, clean clone, or release source, this same command must produce no output.

If a scan hit is intentionally confined to local planning files such as `progress.md` or `findings.md`, record the exception in `progress.md`; public docs, release notes, manifests, examples, and archives get no exception without removing or rewriting the content.

Before PR, create or update a branch-wide reviewed-file manifest in the local planning files and compare it with `git diff --name-only origin/main...HEAD`. Per-commit allowlists are not enough for final PR/release readiness.

Required release evidence:

- Legacy backend cleanup:
  - Task 4 entry gate evidence showing legacy backend compatibility surfaces were deleted, or a tracked ADR plus stale-input routing regression explains why they remain.
- Source verification:
  - clean clone checkout of the release commit,
  - `git status --porcelain=v1 --untracked-files=all` returns empty output in the build source,
  - full or agreed broad test suite,
  - `ruff check`,
  - scoped/broad `mypy` where configured,
  - `python -m compileall -q`.
- macOS frozen smoke:
  - build `.app`/DMG from clean source,
  - launch app,
  - open an implicit example workspace,
  - run direct `delta` and ionization-energy implicit fits,
  - paste or open uncertainty-token data such as `1.23(4)` and `±` forms and verify parsing in the frozen app,
  - run a low-precision SciPy-eligible case and verify the app either selects a validated faster route or records a comparator fallback with correct metadata,
  - run an unweighted-sigma case and verify mpmath systematic refits are preserved,
  - verify frozen runtime actually imports and uses `scipy`, `mpmath`, and `sympy`,
  - verify no extra GUI process opens during fitting,
  - verify formula preview and workspace Save As behavior.
  - command evidence must include `codesign --verify --deep --strict --verbose=2 <app>`, `spctl --assess --type execute --verbose <app>`, notarization submit/result, and `xcrun stapler validate <app-or-dmg>` where applicable.
- Windows frozen smoke:
  - build remotely on Windows from clean source,
  - launch `.exe`/installer result,
  - run the same implicit example, uncertainty-token, SciPy-eligible, and unweighted-sigma smokes,
  - verify no extra GUI process opens during fitting.
  - command evidence must include `signtool verify /pa /v <exe-or-installer>` and a clean remote `git status --porcelain=v1 --untracked-files=all` before build.
- Signing/trust:
  - macOS Developer ID signing and notarization evidence, including `spctl` and package/app verification where applicable,
  - Windows Authenticode signing evidence, including `signtool verify`,
  - update manifest signing verification, or omit auto-installable assets from `updates.json`.
  - unsigned `updates.json` may link to the release page or manually downloaded signed assets, but must not drive silent or automatic installation.
- Build-time downloads:
  - release builds must use pre-provisioned dependencies or pinned hash/signature verification for every external download.
  - release prep must record dependency provenance for standalone Python, wheel caches or lockfiles, and any build-time downloads; missing provenance blocks public release.
- Final artifact audit:
  - scan release notes, `updates.json`, public docs, bundled example workspaces, and uploaded archives for local filesystem paths, private hosts, temporary localhost descriptions, secrets, duplicate `" 2"` artifacts, and internal AI/process artifacts,
  - record the audit command/output before publishing.
  - generate `updates.json` only after final signed assets are uploaded, downloaded back, and size/hash-verified.
  - unsigned or unverifiable platforms may be listed only as manual release-page links, not silent/automatic install targets.

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
  - compare staged names against the exact task allowlist,
  - verify no `" 2"` duplicate file, `.superpowers/`, `dist/`, `build/`, `__pycache__/`, scratch review list, or unrelated draft file is staged,
  - scan staged content for local paths, private hosts, localhost release notes, secrets/tokens, and internal AI/process artifacts.

## Completion Definition

This objective is complete only when:

- all pending tasks above are implemented or intentionally split into a separate accepted plan,
- each task has deep/spec review, code-quality review, and Claude adversarial review,
- review findings are fixed or explicitly rejected with technical evidence,
- verification commands pass with current output,
- worktree is clean except ignored/local artifacts explicitly excluded from release,
- branch is merged/pushed as requested,
- macOS and Windows release assets pass the release gate if a public release is requested.
