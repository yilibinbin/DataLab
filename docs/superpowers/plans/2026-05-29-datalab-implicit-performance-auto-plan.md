# DataLab Implicit Performance Auto Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make self-consistent / implicit fitting automatically choose the fastest correct backend without exposing strategy controls in the GUI.

**Architecture:** Add a planner layer between `ModelProblem` and execution that classifies implicit problems into progressively cheaper computation paths without changing the user's fitted objective. Keep the GUI unchanged: users still enter self-consistent variable, equation, output expression, parameters, constants, precision, and solve options; the backend records the selected strategy in result details for diagnostics. Exact residual-space transforms are allowed only for affine output maps; nonlinear inverse maps are used only as root-solver seed hints and must not replace the original output-space residual.

**Tech Stack:** Python, mpmath, SciPy optional double-precision backend, existing DataLab `safe_eval` expression engine, PySide6 only for integration tests.

---

## 2026-05-30 Review-Reconciled Execution Rules

This section is authoritative when it conflicts with older snippets below. It incorporates the multi-subagent review and Claude adversarial reviews run on 2026-05-30.

### Current Baseline

- Task 1 is partially implemented in the working tree: `shared/symbolic_math.py`, `fitting/implicit_planner.py`, `fitting/implicit_transforms.py`, `tests/test_symbolic_math.py`, and `tests/test_implicit_planner.py` already exist as untracked/modified Task 1 files.
- Do **not** recreate `shared/symbolic_math.py` from the older sketch below. The current API is:

```python
def parse_symbolic_expression(
    expression: str,
    *,
    variables: Sequence[str],
    evaluate: bool = True,
    normalize: bool = True,
) -> tuple[sp.Expr, dict[str, sp.Symbol]]:
```

- All new transform, seed-hint, and derivative code must call it as `parse_symbolic_expression(expr, variables=names)` and must handle `(expr, symbol_map)`.
- `shared.symbolic_math` owns parser security. It must keep AST prevalidation before `parse_expr()`, reject unsafe attribute/subscript/call/literal forms, reject unknown function calls, preserve unknown bare symbols for derivative compatibility, and return all declared symbols in `symbol_map`.
- Domain modules must do their own `expr.free_symbols` validation after parsing. Do not move domain validation into the parser.

### Worktree and Commit Safety

- Before each task commit, run `git status --short` and `git diff --cached --name-only`.
- Stage only the files listed for that task. Abort the commit if any staged path is outside that task allowlist.
- Never stage or modify duplicate local files whose names contain `" 2."`, for example `task_plan 2.md` or `tests/test_update_controller 2.py`.
- `task_plan.md`, `findings.md`, and `progress.md` are local recovery anchors; keep them updated, but do not assume they are tracked.

### Corrected API and Sequencing Constraints

- Task 1 must not import `fitting.implicit_seed_hints` or `fitting.implicit_derivatives` unless no-op stubs are created in Task 1. Preferred implementation: keep Task 1 planner independent, set `seed_hint=None`, and use a future `can_build_implicit_derivative_evaluator()` only after Task 4 introduces it.
- Use one canonical implicit model builder signature from Task 3 onward:

```python
def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    seed_hint: ImplicitSeedHint | None = None,
    use_analytic_derivatives: bool = True,
) -> ModelSpecification:
```

- When runner code needs the number of free parameters, use `len(state.free_params)`, not `state.free_names`.
- If `_preflight_implicit_derivatives` is tested via monkeypatch, define it as a module-level function in `fitting/runner.py`.
- Add `implicit_derivative_strategy = "numeric_finite_difference"` before any runner code reads that attribute, then update it to `"analytic_implicit"` in Task 4.

### Numerical Guardrails Added by Review

- Exact affine fast path must be proven against **non-perfect-fit data** and compared against the general output-space path. Do not rely only on constructed data where `y = a*u + b` fits exactly.
- Remapping an affine fast-path result must not leave output-space statistics mixed with implicit-space covariance/errors. Prefer building a new `FitResult` with `dataclasses.replace()`; recompute or prove covariance and parameter errors are invariant under the affine transform with nonzero-residual parity tests.
- Affine transform detection must reject non-finite, complex, and near-zero slopes/intercepts. Add tests for zero slope, `nan`, `inf`, and complex constants.
- Seed hints must not silently select a different implicit root branch than the configured initial guess/warm start would select. Return candidate seed lists, sort them by distance to configured/warm seeds, and try configured/warm neighborhoods before or alongside inverse candidates. Add a two-branch regression.
- If seed hints are kept as a performance feature, either feed them into numeric finite-difference partial solves too, or clearly document/test that they only seed objective evaluation and do not claim Jacobian-speed improvements.
- SciPy implicit routing must pass `fresh_model_factory` into `_fit_with_scipy_least_squares()` and from there into `_spotcheck_scipy_solution()`. Add a stale-cache regression that fails if the same implicit cache is reused for spot-checking.
- SciPy implicit performance must be benchmarked against analytic mpmath for the low-precision case. If it is not faster on the representative implicit workload, keep the safety fallback but do not present SciPy as the preferred fastest path.

### GUI and Legacy Backend Removal

- The real preference files are `app_desktop/parallel_preferences.py` and `shared/parallel_config.py`, not `shared/parallel_preferences.py`.
- Task 6 must explicitly handle `ParallelConfig.enable_new_implicit_backend` and the legacy branch in `app_desktop/workers_core.py`. Stale persisted settings with `enable_new_implicit_backend=False` must still compute through the new backend.
- Add a regression that loads or constructs stale settings/workspace data with `enable_new_implicit_backend=False` and verifies the new backend is used.

## 2026-05-30 Final Multi-Agent Review Corrections

This section is also authoritative when it conflicts with older task snippets below. It incorporates the 2026-05-30 multi-subagent deep reviews plus Claude adversarial re-review. Do not implement later tasks from the older code sketches unless they also satisfy these corrections.

### Parser and Formula Contract

- `shared.symbolic_math` and every SymPy-based detector must match DataLab's formula contract as enforced by the runtime expression engine. The symbolic parser must not accept aliases that the fit evaluator rejects.
- Add regressions proving affine/seed/derivative detectors reject or normalize consistently with `safe_eval` for lowercase aliases such as `e`, `pi`, and `sin(...)`. A detector must not select a fast path for an expression that the normal model evaluator would reject.
- Keep the single shared parser interface, but treat parser acceptance as syntax-only. Domain modules still own free-symbol, parameter, constant, and runtime-evaluator compatibility validation.

### Task 2 Maintainability Corrections

- Do not keep a separate `_output_space_statistics()` formula copy in `fitting/runner.py`. Before committing Task 2, extract a shared helper, for example `fitting/statistics.py::compute_fit_statistics(targets, residuals, weights, free_param_count)`, and use it from the existing high-precision/general path and the affine remap path. Extend later observed-linear cleanup only if it stays in scope and tests remain focused.
- The affine remap helper must return a new `FitResult` via `dataclasses.replace()`; it must not mutate an existing result in place. Any older snippet below showing a `None` return or in-place mutation is obsolete.
- General-path parity tests must patch the planner-bound symbol, e.g. `monkeypatch.setattr("fitting.implicit_planner.detect_output_transform", ...)`, not only `fitting.implicit_transforms.detect_output_transform`.
- Until analytic/SciPy execution is actually implemented, details must distinguish any planned capability from the strategy that actually executed. Prefer keeping not-yet-executable plan kinds out of `details["implicit_strategy"]`, or add explicit `details["implicit_planned_strategy"]` plus tests.

### Seed Hint Corrections

- Task 3 must modify `fitting/implicit_planner.py` and wire `detect_seed_hint()` into `plan_implicit_fit()`. A seed hint module that is not connected to the planner is incomplete.
- The only allowed branch order is:
  1. configured initial seed,
  2. compatible warm start,
  3. validated hint candidates sorted by distance to the configured/warm anchor.
  Delete or ignore older snippets that put seed hints ahead of configured/warm seeds.
- Inverse-square detection must explicitly recognize `A + B/(x-u)^2` and `A - B/(x-u)^2`. Candidate generation must use `effective_target = target - A`; using raw `target` is incorrect for offset forms.
- Add a two-branch regression proving seed hints do not silently switch to a different root branch than the configured/warm path.
- Seed hints must either be passed into numeric finite-difference partial solves as well as objective evaluation, or the implementation and diagnostics must clearly state that the feature only improves objective root-solve seeding and is not a Jacobian-speed optimization.
- Do not hard-code `evalf(80)` in seed hints. Use the requested precision or the current `mp.workdps(...)` context.

### Analytic Derivative Corrections

- Analytic implicit derivatives must be with respect to the optimizer's free parameters, not blindly every `definition.parameters` entry.
- If dependent parameter expressions are present, the first implementation must disable the analytic path and fall back to numeric finite differences, unless it implements and tests the full chain rule from dependent parameters to free parameters.
- Add a dependent-parameter parity regression before enabling analytic derivatives for those cases.

### SciPy Routing Corrections

- SciPy implicit least-squares is a safety candidate until representative benchmarks prove it is no slower than the analytic mpmath route for low-precision implicit workloads.
- Task 5 must not assert that `precision <= 16` always executes `scipy_implicit_least_squares`. It may assert that SciPy is tried, spot-checked, and either accepted or rejected according to the benchmark/safety gate.
- Move the representative SciPy-vs-mpmath benchmark gate into Task 5 before SciPy is advertised as the preferred backend. If the gate fails, keep SciPy as fallback/candidate only.

### Packaging and Legacy Backend Corrections

- Add SymPy packaging support in all frozen-app build paths before release testing:
  - `DataLab.spec`
  - `build_mac_data_gui.sh`
  - `build_windows_data_gui.ps1`

## 2026-05-30 Task 4/5 Review Hard Corrections

This section is authoritative over the Task 4 and Task 5 snippets below. It incorporates the latest read-only subagent reviews and Claude adversarial reviews. Do not continue implementation from the older snippets unless these corrections are satisfied first.

### Analytic Implicit Jacobian Safety

- Do not run analytic-derivative preflight on the same `ModelSpecification` / implicit cache that will be used for the production fit. Preflight must use a fresh spec/cache, or it must fully restore `_values`, `_warm_starts`, point index, and diagnostics. Preferred implementation: create a fresh analytic spec for preflight and discard it.
- Preflight must not check only finiteness at the initial parameter vector. It must compare analytic partials against the existing numeric finite-difference partials through the same forward model at representative rows, using an explicit relative/absolute tolerance. Finiteness alone is not enough to prove the derivative matches DataLab runtime semantics.
- Analytic derivative evaluation must be gated on root-solve quality. The implicit-function derivative is valid only when the solved implicit variable satisfies the residual tolerance. If the solve uses a fallback branch, exceeds tolerance, or has a non-finite residual, the analytic derivative path must fall back consistently to numeric finite differences.
- Define a numeric `F_u` singularity policy. Exact symbolic `F_u == 0` rejection is insufficient. Runtime `|F_u|` near zero must either disable analytic derivatives for the fit or trigger a deterministic numeric fallback with a diagnostic warning.
- Avoid mixed silent Jacobians. If analytic derivative calls fall back to numeric during optimization or covariance, the result must not continue reporting a clean `"analytic_implicit_output_space"` strategy. Preferred first implementation: if any analytic derivative fallback occurs, rerun the fit with `use_analytic_derivatives=False`; otherwise downgrade the strategy and emit a covariance/diagnostic warning with the fallback count.
- The analytic path remains disabled when dependent parameter expressions are present unless a full chain-rule implementation from optimizer free parameters to dependent parameters is added and tested. Add a dependent-parameter parity regression before enabling those cases.
- Add bounded-parameter/constraint parity tests proving analytic and numeric derivatives agree under the same optimizer free-parameter mapping used by `fit_custom_model()`.
- Add runtime compatibility tests for DataLab formula syntax and allowed functions by comparing analytic partials against numeric partials, not only by checking that SymPy can parse and lambdify the expression.
- Task 4 is incomplete until `tests/test_implicit_derivatives.py` exists and targeted planner/model/seed-hint tests are updated for the new analytic planner behavior.

### SciPy Candidate Routing

- Rewrite Task 5 before implementation. Older snippets that require `precision <= 16` to execute `scipy_implicit_least_squares` are obsolete and conflict with the final design.
- SciPy for implicit models is a candidate path, not a guaranteed backend. It may be tried only behind safety and benchmark gates, and must fall back to analytic mpmath or numeric finite differences when the candidate fails accuracy, conditioning, spot-check, or speed criteria.
- Do not add or depend on a `SCIPY_IMPLICIT` planner kind until an executable, tested routing implementation exists. If a planned-vs-executed diagnostic is useful, add it together with the implementation and tests.
- Any SciPy implicit residual loop must set the implicit point index for each row and must avoid reusing stale implicit caches during spot-check or covariance. Preferred implementation: use a fresh model/spec factory for candidate fit, spot-check, and any accepted result rematerialization.
- Add a representative benchmark gate before advertising SciPy as preferred for low precision. If the benchmark does not prove it is no slower than analytic mpmath on the target implicit workloads, keep SciPy as an optional candidate/fallback only.
- Strategy selection remains fully automatic and must not reintroduce GUI-visible backend toggles.

### Packaging and Legacy Backend Safety

- Include explicit hidden imports and collection/`--collect-all` handling sufficient for PyInstaller builds that import `sympy` through the new planner/transform/derivative modules.
- Remove or neutralize stale `ParallelConfig.enable_new_implicit_backend=False` as an execution selector. Old preferences or workspace payloads may deserialize the field, but they must still route through the unified new backend.
- Add regressions for all legacy entry points that can carry the stale flag: preferences load/save, serialized job payload deserialize, and `app_desktop/workers_core.py` execution path.

## Design Summary

Current evidence:

- `fitting/implicit_classifier.py` has only `OBSERVED_LINEAR`, `OBSERVED_NONLINEAR`, and `GENERAL`.
- `fitting/runner.py::FitRunner._fit_self_consistent()` only takes a fast path when `output_expression == implicit_variable`.
- `fitting/implicit_model.py::build_implicit_model_specification()` evaluates general implicit output by solving the implicit variable and builds parameter partials with numeric finite differences.
- That means changing output from `delta` to a derived quantity makes the backend solve `u` for every point and every parameter perturbation.

Target automatic strategy order:

1. **Observed implicit linear:** existing `observed_linear` QR path.
2. **Observed implicit nonlinear:** existing direct observed residual path.
3. **Exact constant-affine output transform:** only when `y = a*u + b` with finite real constant `a` and `b` independent of free parameters, transform the target to the observed implicit variable path, then remap the returned `FitResult` back to the user's original output space. This path must be compared against the general output-space path on non-perfect-fit data before it is accepted. Skip this path for unweighted `data_sigmas` because observed-variable linear fitting does not preserve ±sigma systematic-refit semantics.
4. **Nonlinear inverse seed hints:** for expressions such as `A + B/(n-u)^2`, derive branch candidates only to seed/validate root solves; the optimizer still minimizes the original output-space residual. Candidate branches must be tried in a way that respects configured initial guesses and warm starts.
5. **SciPy implicit least_squares:** for precision `<= 16`, use the same output-space model specification through the existing SciPy candidate/safety machinery only if benchmarks show it is no slower than the analytic mpmath route for representative implicit workloads.
6. **Analytic implicit derivative:** for high-precision mpmath paths, solve `u` once per point and use implicit differentiation for the output-space Jacobian instead of solving again for every parameter perturbation.
7. **General mpmath fallback:** current robust path.

No GUI strategy dropdown is added.

## File Structure

- Modify/finish `fitting/implicit_planner.py`
  - Defines `ImplicitPlan`, `ImplicitPlanKind`, and `plan_implicit_fit()`.
  - Owns the automatic strategy order and all feature-detection decisions: observed classification, affine transform, seed-hint eligibility, SciPy eligibility, and analytic-derivative eligibility.
- Modify/keep `shared/symbolic_math.py`
  - Reuse the already-extracted SymPy globals/function registry and AST-safe parser. Do not replace it with the older positional-argument sketch.
  - `datalab_latex.derivatives`, `fitting.implicit_transforms`, `fitting.implicit_seed_hints`, and `fitting.implicit_derivatives` must use this helper instead of carrying separate parser/function maps.
- Modify/finish `fitting/implicit_transforms.py`
  - Detects only exact affine output transforms that preserve least-squares objective semantics.
  - Builds transformed target data, transformed `data_sigmas`, and propagated weights.
- Create `fitting/implicit_seed_hints.py`
  - Detects conservative nonlinear inverse candidates such as inverse-square forms.
  - Provides per-point initial guesses and branch validation for root solving without changing residual space.
- Create `fitting/implicit_derivatives.py`
  - Builds analytic derivatives using implicit differentiation.
  - Falls back when expressions cannot be symbolically differentiated safely.
- Modify `fitting/implicit_model.py`
  - Add a model-specification builder that accepts analytic implicit derivative callables.
  - Keep existing general builder as fallback.
- Modify `fitting/runner.py`
  - Route self-consistent fits through `plan_implicit_fit()`.
  - Keep `details["implicit_strategy"]`, `details["optimizer_backend"]`, and `details["fallback_history"]`.
- Modify packaging files
  - Add explicit SymPy collection/hidden-import handling to `DataLab.spec`, `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1`.
- Test files:
  - Create `tests/test_implicit_planner.py`
  - Create `tests/test_symbolic_math.py`
  - Create `tests/test_implicit_transforms.py`
  - Create `tests/test_implicit_derivatives.py`
  - Extend `tests/test_implicit_d8_runner_regression.py`
  - Extend `tests/test_fitting_runner_scipy_fallback.py`
  - Extend `tests/test_workspace_implicit_round_trip.py` only to prove no new GUI/workspace strategy field is persisted.

## Task 1: Add Planner Types and Automatic Classification Boundary

**Files:**
- Create: `fitting/implicit_planner.py`
- Create: `shared/symbolic_math.py`
- Modify: `datalab_latex/derivatives.py`
- Test: `tests/test_implicit_planner.py`
- Test: `tests/test_symbolic_math.py`
- Modify: `fitting/runner.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests/test_implicit_planner.py`:

```python
from __future__ import annotations

import mpmath as mp


def _definition(output_expression: str):
    from fitting.implicit_model import ImplicitModelDefinition

    return ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        output_expression=output_expression,
        parameters=("d0", "d2", "d4"),
        constants={"R": "3.2898419602500e9"},
    )


def test_planner_keeps_existing_observed_linear_first() -> None:
    from fitting.implicit_planner import ImplicitPlanKind, plan_implicit_fit

    plan = plan_implicit_fit(_definition("delta"), precision=80)

    assert plan.kind is ImplicitPlanKind.OBSERVED_LINEAR
    assert plan.reason == "observed implicit variable with linear parameter equation"


def test_planner_marks_affine_output_transform_before_general() -> None:
    from fitting.implicit_planner import ImplicitPlanKind, plan_implicit_fit

    plan = plan_implicit_fit(_definition("2*delta + 1"), precision=80)

    assert plan.kind is ImplicitPlanKind.EXACT_AFFINE_OUTPUT
    assert plan.transform is not None
    assert "affine output expression" in plan.reason


def test_planner_uses_analytic_high_precision_for_nonlinear_output() -> None:
    from fitting.implicit_planner import ImplicitPlanKind, plan_implicit_fit

    plan = plan_implicit_fit(_definition("R/(n-delta)^2"), precision=80)

    assert plan.kind is ImplicitPlanKind.ANALYTIC_IMPLICIT_JACOBIAN
    assert plan.transform is None
```

Review amendment: keep this analytic-high-precision planner assertion only if Task 1 also creates a no-op derivative-probe stub. Otherwise move this assertion to Task 4 after `fitting.implicit_derivatives` exists. Task 1 must be runnable without importing future Task 3/4 modules.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_implicit_planner.py
```

Expected in a fresh tree: fails with `ModuleNotFoundError: No module named 'fitting.implicit_planner'`. In the current partially implemented working tree, treat this as a baseline check instead: Task 1 may already collect and should fail only for remaining Task 1 assertions.

- [ ] **Step 3: Implement planner skeleton**

Review amendment: `shared/symbolic_math.py` already exists in the current working tree. Do not replace it with the older sketch below. If this task is executed from a clean tree, implement the current AST-safe keyword-only API described in **2026-05-30 Review-Reconciled Execution Rules**, not the obsolete positional `parse_symbolic_expression(expression, names)` sketch.

Before adding transform/derivative modules, use the existing shared symbolic parser registry used by `datalab_latex.derivatives`. Do not introduce a smaller third function map; DataLab formula support must stay consistent across LaTeX derivative rendering, parameter constraints, implicit transforms, seed hints, and analytic derivatives.

Current shared parser contract to preserve:

```python
def parse_symbolic_expression(
    expression: str,
    *,
    variables: Sequence[str],
    evaluate: bool = True,
    normalize: bool = True,
) -> tuple[sp.Expr, dict[str, sp.Symbol]]:
    """AST-validate, parse with DataLab's restricted SymPy registry, and return all declared symbols."""
```

If executing from a clean tree, move `datalab_latex.derivatives._SYMPY_GLOBALS` and `_build_sympy_local_dict()` to the shared helper using the current safe API, then import them back into `datalab_latex.derivatives` so existing derivative tests remain the compatibility guard. In the current working tree this extraction is already done; verify rather than rewrite.

Add or update `tests/test_symbolic_math.py` proving numeric literals, `^`, `Sin[...]`, `Ln`, `Log10`, `Pi`, constants, variables, all-declared-symbol return, unknown bare-symbol preservation, and unsafe expression rejection work with the exact parser config. Unknown function calls must fail; unknown bare symbols may be preserved for derivative compatibility and then rejected by domain-specific callers when needed.

Create `fitting/implicit_planner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
from .implicit_model import ImplicitModelDefinition
from .implicit_transforms import OutputTransform, detect_output_transform


class ImplicitPlanKind(Enum):
    OBSERVED_LINEAR = "observed_linear"
    OBSERVED_NONLINEAR = "observed_nonlinear"
    EXACT_AFFINE_OUTPUT = "exact_affine_output"
    ANALYTIC_IMPLICIT_JACOBIAN = "analytic_implicit_jacobian"
    SCIPY_IMPLICIT = "scipy_implicit"
    GENERAL = "general"


@dataclass(frozen=True)
class ImplicitPlan:
    kind: ImplicitPlanKind
    reason: str
    transform: OutputTransform | None = None
    seed_hint: object | None = None
    use_analytic_derivatives: bool = False
    try_scipy: bool = False


def plan_implicit_fit(definition: ImplicitModelDefinition, *, precision: int) -> ImplicitPlan:
    classification = ImplicitProblemClassifier().classify(definition)
    if classification.strategy is ImplicitStrategy.OBSERVED_LINEAR:
        return ImplicitPlan(
            kind=ImplicitPlanKind.OBSERVED_LINEAR,
            reason="observed implicit variable with linear parameter equation",
        )
    if classification.strategy is ImplicitStrategy.OBSERVED_NONLINEAR:
        return ImplicitPlan(
            kind=ImplicitPlanKind.OBSERVED_NONLINEAR,
            reason="observed implicit variable with nonlinear parameter equation",
        )

    transform = detect_output_transform(definition)
    if transform is not None:
        return ImplicitPlan(
            kind=ImplicitPlanKind.EXACT_AFFINE_OUTPUT,
            reason="affine output expression can be transformed without changing the least-squares objective",
            transform=transform,
        )

    if precision <= 16:
        return ImplicitPlan(
            kind=ImplicitPlanKind.SCIPY_IMPLICIT,
            reason="double precision requested; try SciPy implicit least_squares before mpmath fallback",
            try_scipy=True,
        )

    return ImplicitPlan(
        kind=ImplicitPlanKind.ANALYTIC_IMPLICIT_JACOBIAN,
        reason="high precision implicit output fit; future runner task may use analytic implicit Jacobian before numeric fallback",
        use_analytic_derivatives=True,
    )
```

- [ ] **Step 4: Add transform stub so planner imports**

Create `fitting/implicit_transforms.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from mpmath import mp

from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class OutputTransform:
    transformed_targets: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    transformed_sigmas: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf | None] | None], list[mp.mpf | None] | None]
    transformed_weights: Callable[[dict[str, Sequence[mp.mpf]], list[mp.mpf] | None], list[mp.mpf] | None]
    forward_values: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    expression: str
    reason: str


def detect_output_transform(definition: ImplicitModelDefinition) -> OutputTransform | None:
    text = definition.output_expression.replace(" ", "")
    implicit = definition.implicit_variable
    if text == implicit:
        return None
    if text == f"2*{implicit}+1":
        return _build_affine_transform(definition, slope=mp.mpf("2"), intercept=mp.mpf("1"))
    return None


def _build_affine_transform(
    definition: ImplicitModelDefinition,
    *,
    slope: mp.mpf,
    intercept: mp.mpf,
) -> OutputTransform | None:
    if slope == 0:
        return None

    def _targets(variable_data: dict[str, Sequence[mp.mpf]], targets: Sequence[mp.mpf]) -> list[mp.mpf]:
        return [(mp.mpf(target) - intercept) / slope for target in targets]

    def _sigmas(
        variable_data: dict[str, Sequence[mp.mpf]],
        data_sigmas: Sequence[mp.mpf | None] | None,
    ) -> list[mp.mpf | None] | None:
        if data_sigmas is None:
            return None
        scale = mp.fabs(slope)
        return [None if sigma is None else mp.mpf(sigma) / scale for sigma in data_sigmas]

    def _weights(
        variable_data: dict[str, Sequence[mp.mpf]],
        weights: list[mp.mpf] | None,
    ) -> list[mp.mpf] | None:
        scale = mp.fabs(slope)
        if weights is None:
            row_count = len(next(iter(variable_data.values()))) if variable_data else 0
            return [scale * scale for _ in range(row_count)]
        return [mp.mpf(weight) * scale * scale for weight in weights]

    def _forward(variable_data: dict[str, Sequence[mp.mpf]], implicit_values: Sequence[mp.mpf]) -> list[mp.mpf]:
        return [slope * mp.mpf(value) + intercept for value in implicit_values]

    return OutputTransform(
        transformed_targets=_targets,
        transformed_sigmas=_sigmas,
        transformed_weights=_weights,
        forward_values=_forward,
        expression=definition.output_expression,
        reason="exact affine output transform",
    )
```

This stub intentionally supports one exact affine form so Task 1 can compile. Task 2 replaces it with a SymPy affine detector; nonlinear inverse-square expressions are intentionally not transformed into observed-variable residuals.

- [ ] **Step 5: Run planner tests**

Run:

```bash
pytest -q tests/test_implicit_planner.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add fitting/implicit_planner.py fitting/implicit_transforms.py shared/symbolic_math.py datalab_latex/derivatives.py tests/test_implicit_planner.py tests/test_symbolic_math.py
git commit -m "feat: add implicit fit planner boundary"
```

## Task 2: Implement Exact Affine Output Transform Fast Path

**Files:**
- Modify: `fitting/implicit_transforms.py`
- Modify: `fitting/runner.py`
- Test: `tests/test_implicit_transforms.py`
- Test: `tests/test_implicit_d8_runner_regression.py`

- [ ] **Step 1: Write transform tests for exact affine residuals**

Create `tests/test_implicit_transforms.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_affine_output_transform_maps_target_sigma_and_weights_exactly() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="2*u + 1",
        parameters=("a", "b"),
    )

    transform = detect_output_transform(definition)
    assert transform is not None

    targets = transform.transformed_targets({"x": [mp.mpf("3")]}, [mp.mpf("9")])
    sigmas = transform.transformed_sigmas({"x": [mp.mpf("3")]}, [mp.mpf("0.4")])
    weights = transform.transformed_weights({"x": [mp.mpf("3")]}, [mp.mpf("25")])

    assert targets == [mp.mpf("4")]
    assert sigmas == [mp.mpf("0.2")]
    assert weights == [mp.mpf("100")]


def test_affine_output_transform_detects_generic_constant_affine_expression() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="C*u + B",
        parameters=("a", "b"),
        constants={"C": "3", "B": "-2"},
    )

    transform = detect_output_transform(definition)

    assert transform is not None
    assert transform.transformed_targets({"x": [mp.mpf("0")]}, [mp.mpf("7")]) == [mp.mpf("3")]


def test_affine_output_transform_rejects_x_dependent_slope_for_v1() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="C*x*u + B",
        parameters=("a", "b"),
        constants={"C": "3", "B": "5"},
    )

    assert detect_output_transform(definition) is None


def test_nonlinear_inverse_square_output_is_not_affine_transformed() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2",
        output_expression="R/(n-delta)^2",
        parameters=("d0", "d2"),
        constants={"R": "100"},
    )

    assert detect_output_transform(definition) is None


def test_affine_output_transform_rejects_free_parameter_slope() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="a*u + 1",
        parameters=("a", "b"),
    )

    assert detect_output_transform(definition) is None


def test_affine_output_transform_rejects_nonfinite_complex_or_near_zero_scale() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_transforms import detect_output_transform

    base = dict(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        parameters=("a", "b"),
    )

    assert detect_output_transform(ImplicitModelDefinition(output_expression="0*u + 1", **base)) is None
    assert detect_output_transform(
        ImplicitModelDefinition(output_expression="C*u + 1", constants={"C": "nan"}, **base)
    ) is None
    assert detect_output_transform(
        ImplicitModelDefinition(output_expression="C*u + 1", constants={"C": "inf"}, **base)
    ) is None
    assert detect_output_transform(
        ImplicitModelDefinition(output_expression="Sqrt[-1]*u + 1", **base)
    ) is None
```

- [ ] **Step 2: Write runner regression for affine target parity**

Extend `tests/test_implicit_d8_runner_regression.py`:

```python
def test_affine_output_uses_exact_observed_fast_path_without_changing_statistics() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    n = [mp.mpf(row[0]) for row in D8_ROWS]
    delta = [mp.mpf(row[1]) for row in D8_ROWS]
    affine_y = [2 * value + 1 for value in delta]
    sigmas_delta = [mp.mpf(row[2]) for row in D8_ROWS]
    sigmas_affine = [2 * sigma for sigma in sigmas_delta]
    delta_weights = [1 / (sigma ** 2) for sigma in sigmas_delta]
    affine_weights = [1 / (sigma ** 2) for sigma in sigmas_affine]
    base_config = {
        "d0": {"initial": "-0.01213"},
        "d2": {"initial": "0.0"},
        "d4": {"initial": "0.0"},
        "d6": {"initial": "0.0"},
        "d8": {"initial": "0.0"},
    }
    delta_definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d6", "d8"),
    )
    direct_problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=delta_definition,
    )
    affine_problem = ModelProblem(
        model_type="self_consistent",
        expression="2*delta + 1",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation=delta_definition.equation,
            output_expression="2*delta + 1",
            parameters=delta_definition.parameters,
        ),
    )

    runner = FitRunner()
    direct = runner.fit(direct_problem, {"n": n}, delta, precision=80, weights=delta_weights, data_sigmas=sigmas_delta)
    affine = runner.fit(affine_problem, {"n": n}, affine_y, precision=80, weights=affine_weights, data_sigmas=sigmas_affine)

    assert affine.details["implicit_strategy"] == "exact_affine_output_observed_linear"
    assert affine.details["optimizer_backend"] == "mpmath_qr"
    assert affine.details["output_space_remapped"] is True
    assert all(mp.almosteq(value, expected, rel_eps=mp.mpf("1e-25")) for value, expected in zip(affine.fitted_curve, [2 * v + 1 for v in direct.fitted_curve]))
    assert all(
        mp.almosteq(value, fit - target, rel_eps=mp.mpf("1e-25"), abs_eps=mp.mpf("1e-30"))
        for value, fit, target in zip(affine.residuals, affine.fitted_curve, affine_y)
    )
    for name, expected in direct.params.items():
        assert mp.almosteq(affine.params[name], expected, rel_eps=mp.mpf("1e-25"), abs_eps=mp.mpf("1e-30"))
        assert mp.almosteq(
            affine.param_errors_total[name],
            direct.param_errors_total[name],
            rel_eps=mp.mpf("1e-20"),
            abs_eps=mp.mpf("1e-30"),
        )
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2"):
        assert mp.almosteq(
            getattr(affine, attr),
            getattr(direct, attr),
            rel_eps=mp.mpf("1e-20"),
            abs_eps=mp.mpf("1e-30"),
        )
    assert mp.almosteq(affine.rmse, 2 * direct.rmse, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-30"))


def test_affine_output_fast_path_matches_general_output_space_on_nonzero_residuals(monkeypatch) -> None:
    """Guard against proving affine parity only on perfectly constructed data."""

    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4"), mp.mpf("5")]
    implicit_targets = [mp.mpf("0.15"), mp.mpf("0.41"), mp.mpf("0.62"), mp.mpf("0.81"), mp.mpf("1.08")]
    output_targets = [2 * value + 1 for value in implicit_targets]
    weights = [mp.mpf("1"), mp.mpf("2"), mp.mpf("1.5"), mp.mpf("3"), mp.mpf("2.5")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    fast = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80, weights=weights)
    monkeypatch.setattr("fitting.implicit_transforms.detect_output_transform", lambda definition: None)
    general = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80, weights=weights)

    assert fast.details["implicit_strategy"] == "exact_affine_output_observed_linear"
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2", "rmse"):
        assert mp.almosteq(getattr(fast, attr), getattr(general, attr), rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
    for name in fast.params:
        assert mp.almosteq(fast.params[name], general.params[name], rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
        assert mp.almosteq(
            fast.param_errors_total[name],
            general.param_errors_total[name],
            rel_eps=mp.mpf("1e-12"),
            abs_eps=mp.mpf("1e-25"),
        )


def test_affine_output_skips_fast_path_for_unweighted_data_sigmas() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    us = [mp.mpf("0.2"), mp.mpf("0.4"), mp.mpf("0.6")]
    ys = [2 * value + 1 for value in us]
    sigmas = [mp.mpf("0.01"), mp.mpf("0.01"), mp.mpf("0.01")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a*x + b",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=80, data_sigmas=sigmas)

    assert result.details["implicit_strategy"] != "exact_affine_output_observed_linear"
    assert any(
        "Exact affine output fast path is disabled for unweighted data_sigmas" in item["reason"]
        for item in result.details.get("fallback_history", [])
    )


def test_affine_output_does_not_use_observed_nonlinear_residual_fast_path() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("1.2"), mp.mpf("1.3"), mp.mpf("1.4"), mp.mpf("1.5")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="Sin[a] + b*x",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=80)

    assert result.details["implicit_strategy"] != "exact_affine_output_observed_nonlinear"
    assert any(item["from"] == "exact_affine_output" for item in result.details.get("fallback_history", []))
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
pytest -q \
  tests/test_implicit_transforms.py \
  tests/test_implicit_d8_runner_regression.py::test_affine_output_uses_exact_observed_fast_path_without_changing_statistics \
  tests/test_implicit_d8_runner_regression.py::test_affine_output_fast_path_matches_general_output_space_on_nonzero_residuals \
  tests/test_implicit_d8_runner_regression.py::test_affine_output_skips_fast_path_for_unweighted_data_sigmas \
  tests/test_implicit_d8_runner_regression.py::test_affine_output_does_not_use_observed_nonlinear_residual_fast_path
```

Expected: fails because the Task 1 stub only supports one hardcoded affine form (`2*u + 1`); it does not detect generic constant-affine expressions such as `C*u + B`, and `FitRunner` does not yet route exact affine output transforms.

- [ ] **Step 4: Replace the transform stub with a conservative affine detector**

Replace `detect_output_transform()` and helpers in `fitting/implicit_transforms.py`. Use `shared.symbolic_math.parse_symbolic_expression()` rather than defining a second SymPy grammar in this file:

```python
import sympy as sp

from shared.symbolic_math import parse_symbolic_expression


def detect_output_transform(definition: ImplicitModelDefinition) -> OutputTransform | None:
    if definition.output_expression.strip() == definition.implicit_variable:
        return None
    names = [*definition.x_variables, definition.implicit_variable, *definition.constants]
    try:
        expr, symbols = parse_symbolic_expression(definition.output_expression, variables=names)
    except Exception:
        return None
    free_names = {str(symbol) for symbol in expr.free_symbols}
    if free_names.intersection(definition.parameters):
        return None
    allowed = {definition.implicit_variable, *definition.x_variables, *definition.constants}
    if free_names.difference(allowed):
        return None

    u_symbol = symbols[definition.implicit_variable]
    slope_expr = sp.simplify(sp.diff(expr, u_symbol))
    intercept_expr = sp.simplify(expr - slope_expr * u_symbol)
    if slope_expr == 0 or slope_expr.has(u_symbol) or intercept_expr.has(u_symbol):
        return None
    constants = _constant_values(definition.constants)
    x_symbols = [symbols[name] for name in definition.x_variables]
    substitutions = {symbols[name]: constants[name] for name in constants}
    slope_eval = sp.simplify(slope_expr.subs(substitutions))
    intercept_eval = sp.simplify(intercept_expr.subs(substitutions))
    if any(slope_eval.has(symbol) or intercept_eval.has(symbol) for symbol in x_symbols):
        return None
    slope_func = sp.lambdify(x_symbols, slope_eval, "mpmath")
    intercept_func = sp.lambdify(x_symbols, intercept_eval, "mpmath")

    def _scope_values(variable_data: dict[str, Sequence[mp.mpf]], row: int) -> list[mp.mpf]:
        return [mp.mpf(variable_data[name][row]) for name in definition.x_variables]

    def _slope(variable_data: dict[str, Sequence[mp.mpf]], row: int) -> mp.mpf:
        value = mp.mpf(slope_func(*_scope_values(variable_data, row)))
        if not mp.isfinite(value) or mp.fabs(value) <= mp.mpf("1e-50"):
            raise ValueError("Affine output transform has non-finite or near-zero slope for at least one data point.")
        return value

    def _intercept(variable_data: dict[str, Sequence[mp.mpf]], row: int) -> mp.mpf:
        value = mp.mpf(intercept_func(*_scope_values(variable_data, row)))
        if not mp.isfinite(value):
            raise ValueError("Affine output transform has non-finite intercept for at least one data point.")
        return value

    def _targets(variable_data: dict[str, Sequence[mp.mpf]], targets: Sequence[mp.mpf]) -> list[mp.mpf]:
        return [(mp.mpf(target) - _intercept(variable_data, idx)) / _slope(variable_data, idx) for idx, target in enumerate(targets)]

    def _sigmas(
        variable_data: dict[str, Sequence[mp.mpf]],
        data_sigmas: Sequence[mp.mpf | None] | None,
    ) -> list[mp.mpf | None] | None:
        if data_sigmas is None:
            return None
        return [
            None if sigma is None else mp.mpf(sigma) / mp.fabs(_slope(variable_data, idx))
            for idx, sigma in enumerate(data_sigmas)
        ]

    def _weights(variable_data: dict[str, Sequence[mp.mpf]], weights: list[mp.mpf] | None) -> list[mp.mpf] | None:
        row_count = len(next(iter(variable_data.values()))) if variable_data else 0
        if weights is None:
            return [_slope(variable_data, idx) ** 2 for idx in range(row_count)]
        return [mp.mpf(weight) * _slope(variable_data, idx) ** 2 for idx, weight in enumerate(weights)]

    def _forward(variable_data: dict[str, Sequence[mp.mpf]], implicit_values: Sequence[mp.mpf]) -> list[mp.mpf]:
        return [
            _slope(variable_data, idx) * mp.mpf(value) + _intercept(variable_data, idx)
            for idx, value in enumerate(implicit_values)
        ]

    return OutputTransform(
        transformed_targets=_targets,
        transformed_sigmas=_sigmas,
        transformed_weights=_weights,
        forward_values=_forward,
        expression=definition.output_expression,
        reason="exact affine output transform",
    )


def _constant_values(constants: dict[str, str]) -> dict[str, mp.mpf]:
    values = {name: mp.mpf(value) for name, value in constants.items()}
    if any(not mp.isfinite(value) for value in values.values()):
        raise ValueError("Affine output constants must be finite real values.")
    return values
```

- [ ] **Step 5: Implement exact affine fast path in `FitRunner`**

Modify `fitting/runner.py` imports:

```python
from .implicit_planner import ImplicitPlanKind, plan_implicit_fit
```

Modify `_fit_self_consistent()` after `state = ...` so `plan_implicit_fit()` is the single classification boundary. Keep a local `fallback_history: list[dict[str, str]] = []`; every failed optimized path appends to it instead of overwriting a single fallback reason. Replace direct `classification = ImplicitProblemClassifier().classify(definition)` use with `plan` and keep the observed nonlinear direct path before any general solver:

```python
        plan = plan_implicit_fit(definition, precision=precision)
        fallback_history: list[dict[str, str]] = []
        if plan.kind is ImplicitPlanKind.OBSERVED_LINEAR:
            try:
                result = fit_observed_implicit_variable_linear_model(
                    definition,
                    state,
                    variable_data,
                    target_data,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
                result.details["implicit_diagnostics"] = {
                    "points_solved": 0,
                    "root_fallbacks": 0,
                    "max_iterations_used": 0,
                    "max_residual": "0",
                }
                result.details["implicit_strategy"] = "observed_linear"
                result.details["optimizer_backend"] = "mpmath_qr"
                return result
            except ValueError as exc:
                fallback_history.append({"from": "observed_linear", "to": "general", "reason": str(exc)})

        if plan.kind is ImplicitPlanKind.EXACT_AFFINE_OUTPUT and plan.transform is not None:
            try:
                if weights is None and data_sigmas is not None and any(sigma is not None for sigma in data_sigmas):
                    raise ValueError("Exact affine output fast path is disabled for unweighted data_sigmas to preserve systematic-refit semantics.")
                transformed_targets = plan.transform.transformed_targets(variable_data, target_data)
                transformed_weights = plan.transform.transformed_weights(variable_data, weights)
                transformed_sigmas = plan.transform.transformed_sigmas(variable_data, data_sigmas)
                observed_definition = ImplicitModelDefinition(
                    x_variables=definition.x_variables,
                    implicit_variable=definition.implicit_variable,
                    equation=definition.equation,
                    output_expression=definition.implicit_variable,
                    parameters=definition.parameters,
                    constants=definition.constants,
                    solve_options=definition.solve_options,
                )
                observed_plan = plan_implicit_fit(observed_definition, precision=precision)
                if observed_plan.kind is ImplicitPlanKind.OBSERVED_LINEAR:
                    result = fit_observed_implicit_variable_linear_model(
                        observed_definition,
                        state,
                        variable_data,
                        transformed_targets,
                        precision=precision,
                        weights=transformed_weights,
                        data_sigmas=transformed_sigmas,
                    )
                else:
                    raise ValueError(
                        "Exact affine output fast path is restricted to observed-linear implicit equations; "
                        "nonlinear observed residuals do not prove output-space objective equivalence."
                    )
                result.details["implicit_diagnostics"] = {
                    "points_solved": 0,
                    "root_fallbacks": 0,
                    "max_iterations_used": 0,
                    "max_residual": "0",
                }
                result.details["implicit_strategy"] = "exact_affine_output_observed_linear"
                result.details["optimizer_backend"] = "mpmath_qr"
                result.details["output_transform"] = plan.transform.reason
                _remap_affine_result_to_output_space(
                    result,
                    plan.transform,
                    variable_data,
                    target_data,
                    weights,
                    free_param_count=len(state.free_params),
                )
                return result
            except ValueError as exc:
                fallback_history.append({"from": "exact_affine_output", "to": "general", "reason": str(exc)})

        if plan.kind is ImplicitPlanKind.OBSERVED_NONLINEAR:
            try:
                observed_variable_data = dict(variable_data)
                observed_variable_data[definition.implicit_variable] = target_data
                spec = build_model_specification(
                    definition.equation,
                    [*definition.x_variables, definition.implicit_variable],
                    definition.parameters,
                    definition.constants,
                )
                result = fit_custom_model(
                    spec,
                    state,
                    observed_variable_data,
                    target_data,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
                result.details["implicit_strategy"] = "observed_nonlinear"
                result.details["optimizer_backend"] = "mpmath_high_precision"
                result.details["implicit_diagnostics"] = {
                    "points_solved": 0,
                    "root_fallbacks": 0,
                    "max_iterations_used": 0,
                    "max_residual": "0",
                    "direct_observed_residual": True,
                }
                return result
            except ValueError as exc:
                fallback_history.append({"from": "observed_nonlinear", "to": "general", "reason": str(exc)})
```

Add helper near `_weighted_residual_norm()`. Prefer returning a new `FitResult` via `dataclasses.replace()` rather than mutating the observed-linear result in place; if implementation mutates in place, tests must still prove output-space statistics, covariance-derived errors, and residuals are mutually consistent on nonzero-residual data.

Reuse the same weighted-statistics formulas as `fitting.hp_fitter` / observed-linear fitting. Import `noise_floor` if it is not already available in `runner.py`.

```python
def _remap_affine_result_to_output_space(
    result: FitResult,
    transform: OutputTransform,
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
    *,
    free_param_count: int,
) -> None:
    fitted = transform.forward_values(variable_data, result.fitted_curve)
    residuals = [mp.mpf(fit) - mp.mpf(target) for fit, target in zip(fitted, target_data)]
    result.fitted_curve = fitted
    result.residuals = residuals
    result.chi2, result.reduced_chi2, result.r2, result.rmse, result.aic, result.bic = _output_space_statistics(
        target_data,
        residuals,
        weights,
        free_param_count=free_param_count,
    )
    result.details["output_space_remapped"] = True


def _output_space_statistics(
    targets: Sequence[mp.mpf],
    residuals: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
    *,
    free_param_count: int,
) -> tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf, mp.mpf, mp.mpf]:
    row_count = len(targets)
    if weights:
        chi2 = mp.fsum(weight * (residual * residual) for weight, residual in zip(weights, residuals))
        total_weight = mp.fsum(weights)
        mean_target = (
            mp.fsum(weight * target for weight, target in zip(weights, targets)) / total_weight
            if total_weight > 0 else mp.fsum(targets) / row_count
        )
        sst = mp.fsum(weight * (target - mean_target) ** 2 for weight, target in zip(weights, targets))
        rmse = mp.sqrt(chi2 / total_weight)
    else:
        chi2 = mp.fsum(residual * residual for residual in residuals)
        mean_target = mp.fsum(targets) / row_count
        sst = mp.fsum((target - mean_target) ** 2 for target in targets)
        rmse = mp.sqrt(chi2 / row_count)
    dof = row_count - free_param_count
    if dof <= 0:
        return chi2, mp.nan, mp.nan, rmse, mp.nan, mp.nan
    reduced = chi2 / dof
    r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
    eps = noise_floor()
    noise = chi2 / row_count if chi2 > eps else eps
    aic = 2 * free_param_count + row_count * mp.log(noise)
    bic = free_param_count * mp.log(row_count) + row_count * mp.log(noise)
    return chi2, reduced, r2, rmse, aic, bic
```

When falling back to general in Task 2, do not pass `target_data` yet; Task 3 introduces that argument for seed hints. Preserve all optimized-path failures in `fallback_history` and set `implicit_strategy` to the strategy that actually ran:

```python
        spec = build_implicit_model_specification(definition)
        result = fit_custom_model(
            spec,
            state,
            variable_data,
            target_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
        diagnostics = getattr(spec, "implicit_diagnostics")
        result.details["implicit_diagnostics"] = {
            "points_solved": int(diagnostics.points_solved),
            "root_fallbacks": int(diagnostics.root_fallbacks),
            "max_iterations_used": int(diagnostics.max_iterations_used),
            "max_residual": str(diagnostics.max_residual),
        }
        result.details["implicit_strategy"] = (
            "analytic_implicit_output_space"
            if getattr(spec, "implicit_derivative_strategy", "") == "analytic_implicit"
            else "general_implicit_numeric_finite_difference"
        )
        result.details["optimizer_backend"] = "mpmath_high_precision"
        if plan.seed_hint is not None:
            result.details["implicit_seed_hint"] = plan.seed_hint.reason
        if fallback_history:
            result.details["fallback_history"] = fallback_history
        return result
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
pytest -q tests/test_implicit_transforms.py tests/test_implicit_d8_runner_regression.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fitting/runner.py fitting/implicit_transforms.py tests/test_implicit_transforms.py tests/test_implicit_d8_runner_regression.py
git commit -m "perf: add exact affine implicit output fast path"
```

## Task 3: Add Nonlinear Inverse Seed Hints Without Changing Residual Space

**Files:**
- Create: `fitting/implicit_seed_hints.py`
- Modify: `fitting/implicit_model.py`
- Test: `tests/test_implicit_seed_hints.py`

- [ ] **Step 1: Write seed-hint tests for inverse-square forms**

Create `tests/test_implicit_seed_hints.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_inverse_square_seed_hint_returns_valid_branch_and_reconstructs_target() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_seed_hints import detect_seed_hint

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="cr*M/(M+1)/(n-delta)^2",
        parameters=("d0",),
        constants={"cr": "3.2898419602500e9", "M": "7294.29954171"},
    )

    hint = detect_seed_hint(definition)
    assert hint is not None

    coeff = mp.mpf("3.2898419602500e9") * mp.mpf("7294.29954171") / (mp.mpf("7294.29954171") + 1)
    target = mp.mpf("100")
    guesses = hint.candidates({"n": mp.mpf("10")}, target)
    guess = guesses[0]

    assert mp.mpf("10") - mp.sqrt(coeff / target) in guesses
    assert mp.mpf("10") + mp.sqrt(coeff / target) in guesses
    assert mp.almosteq(coeff / (mp.mpf("10") - guess) ** 2, target, rel_eps=mp.mpf("1e-30"))


def test_inverse_square_seed_hint_supports_constant_offset_output() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_seed_hints import detect_seed_hint

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="En - R/(n-delta)^2",
        parameters=("d0",),
        constants={"En": "0.5", "R": "100"},
    )

    hint = detect_seed_hint(definition)
    assert hint is not None
    guesses = hint.candidates({"n": mp.mpf("10")}, mp.mpf("0.25"))

    assert len(guesses) == 2
    for guess in guesses:
        assert mp.almosteq(mp.mpf("0.5") - mp.mpf("100") / (mp.mpf("10") - guess) ** 2, mp.mpf("0.25"))


def test_inverse_square_seed_hint_rejects_ambiguous_or_invalid_targets() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.implicit_seed_hints import detect_seed_hint

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="R/(n-delta)^2",
        parameters=("d0",),
        constants={"R": "100"},
    )

    hint = detect_seed_hint(definition)
    assert hint is not None

    assert hint.candidates({"n": mp.mpf("10")}, mp.mpf("0")) == ()
    assert hint.candidates({"n": mp.mpf("10")}, mp.mpf("-1")) == ()


def test_seed_hint_is_used_on_high_precision_fit_path() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("4"), mp.mpf("5"), mp.mpf("6"), mp.mpf("7")]
    deltas = [mp.mpf("-0.01"), mp.mpf("-0.011"), mp.mpf("-0.012"), mp.mpf("-0.0125")]
    ys = [mp.mpf("100") / (x - u) ** 2 for x, u in zip(xs, deltas)]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="R/(n-delta)^2",
        variables=("n",),
        parameter_config={"d0": {"initial": "-0.012"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0",
            output_expression="R/(n-delta)^2",
            parameters=("d0",),
            constants={"R": "100"},
        ),
    )

    result = FitRunner().fit(problem, {"n": xs}, ys, precision=80)

    assert result.details.get("implicit_seed_hint") == "validated inverse-square output seed"
    assert all(mp.isfinite(value) for value in result.fitted_curve)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_implicit_seed_hints.py
```

Expected: fails because `fitting.implicit_seed_hints` does not exist.

- [ ] **Step 3: Implement conservative seed hints**

Create `fitting/implicit_seed_hints.py`. It must use `shared.symbolic_math.parse_symbolic_expression()` rather than carrying its own parser or its own regex-based identifier scanner:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import sympy as sp
from mpmath import mp

from shared.symbolic_math import parse_symbolic_expression

if TYPE_CHECKING:
    from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class ImplicitSeedHint:
    reason: str
    candidates: Callable[[dict[str, mp.mpf], mp.mpf], tuple[mp.mpf, ...]]


def detect_seed_hint(definition: "ImplicitModelDefinition") -> ImplicitSeedHint | None:
    if len(definition.x_variables) != 1:
        return None
    x_name = definition.x_variables[0]
    u_name = definition.implicit_variable
    constants = _constant_values(definition.constants)
    try:
        coeff = _inverse_square_coefficient(definition, x_name, u_name, constants)
    except ValueError:
        return None

    def _candidates(variables: dict[str, mp.mpf], target: mp.mpf) -> tuple[mp.mpf, ...]:
        y = mp.mpf(target)
        if y <= 0 or coeff <= 0:
            return ()
        x_value = mp.mpf(variables[x_name])
        root = mp.sqrt(coeff / y)
        accepted: list[mp.mpf] = []
        for candidate in (x_value - root, x_value + root):
            reconstructed = coeff / (x_value - candidate) ** 2
            if mp.almosteq(reconstructed, y, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-30")):
                accepted.append(candidate)
        return tuple(accepted)

    return ImplicitSeedHint(reason="validated inverse-square output seed", candidates=_candidates)


def _constant_values(constants: dict[str, str]) -> dict[str, mp.mpf]:
    values: dict[str, mp.mpf] = {}
    for name, value in constants.items():
        values[name] = mp.mpf(value)
    return values


def _inverse_square_coefficient(
    definition: "ImplicitModelDefinition",
    x_name: str,
    u_name: str,
    constants: dict[str, mp.mpf],
) -> mp.mpf:
    # Review amendment: support both B/(x-u)^2 and A + B/(x-u)^2 when A and B
    # are finite constants independent of free parameters. The candidate solver
    # must use target - A as the effective inverse-square target and reject
    # ambiguous/non-finite domains.
    expr, symbols = parse_symbolic_expression(
        definition.output_expression,
        variables=[x_name, u_name, *definition.parameters, *constants],
    )
    if {str(symbol) for symbol in expr.free_symbols}.intersection(definition.parameters):
        raise ValueError("seed hint output depends on free parameters")
    x = symbols[x_name]
    u = symbols[u_name]
    scaled = sp.simplify(expr * (x - u) ** 2)
    if scaled.has(u):
        raise ValueError("output is not an inverse-square expression in the implicit variable")
    value = scaled.subs({symbols[name]: constants[name] for name in constants})
    return mp.mpf(str(value.evalf(80)))
```

- [ ] **Step 4: Wire hints into implicit solve cache as initial guesses only**

Modify `fitting/implicit_model.py` so `build_implicit_model_specification()` can receive target data for seed hints:

```python
def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    seed_hint: ImplicitSeedHint | None = None,
    use_analytic_derivatives: bool = True,
) -> ModelSpecification:
```

Do not call seed-hint detection from inside `implicit_model.py`; the planner owns that classification. Add an optional `seed_hint` argument to the model builder and pass `plan.seed_hint` from `FitRunner`:

```python
def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    seed_hint: ImplicitSeedHint | None = None,
    use_analytic_derivatives: bool = True,
) -> ModelSpecification:
```

Change `_solve_implicit_value()` signature in `fitting/implicit_model.py`:

```python
def _solve_implicit_value(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    var_tuple: tuple[mp.mpf, ...],
    param_tuple: tuple[mp.mpf, ...],
    *,
    initial_guesses: Sequence[mp.mpf] = (),
) -> mp.mpf:
```

Change both internal `_solve_implicit_value()` callers so existing derivative/output helper calls pass no `initial_guess` except the main model evaluation path:

```python
solved = _solve_implicit_value(definition, cache, var_tuple, param_tuple)
```

Inside `_solve_implicit_value()`, add the seed hint ahead of configured and warm seeds:

```python
    seeds: list[tuple[mp.mpf, bool]] = []
    for value in initial_guesses:
        seeds.append((mp.mpf(value), False))
    seeds.append((configured_seed, False))
```

Do not let seed hints silently override the configured branch. Build the seed list from configured seed, compatible warm start, then validated hint candidates sorted by distance to the configured/warm seed. The fitted residual remains `definition.output_expression - target`; do not replace target data or weights in this task.

In the `_evaluate()` closure, use `cache.current_point_index` to fetch the target for the current row and pass the seed hint candidate into the new argument. `hp_fitter._set_model_point_index()` already sets this index before normal mpmath model evaluation/partials; Task 3 must add an end-to-end regression proving the seed hint is consumed on the high-precision path, not only in the detector unit test.

```python
        seed_candidates = ()
        if seed_hint is not None and target_data is not None and cache.current_point_index is not None:
            variables = {name: value for name, value in zip(definition.x_variables, var_tuple)}
            seed_candidates = seed_hint.candidates(variables, mp.mpf(target_data[cache.current_point_index]))
        solved = _solve_implicit_value(
            definition,
            cache,
            var_tuple,
            param_tuple,
            initial_guesses=seed_candidates,
        )
```

Update the final general path in `FitRunner` after Task 3 so the model builder receives the planner-owned seed hint:

```python
        spec = build_implicit_model_specification(
            definition,
            target_data=target_data,
            seed_hint=plan.seed_hint,
            use_analytic_derivatives=plan.use_analytic_derivatives,
        )
```

- [ ] **Step 5: Run seed-hint and implicit regression tests**

Run:

```bash
pytest -q tests/test_implicit_seed_hints.py tests/test_implicit_model.py tests/test_implicit_d8_runner_regression.py
```

Expected: all pass; D8 derived-output tests still report output-space fitting, not observed-variable transform fitting.

- [ ] **Step 6: Commit**

```bash
git add fitting/implicit_seed_hints.py fitting/implicit_model.py tests/test_implicit_seed_hints.py
git commit -m "perf: add implicit output seed hints"
```

## Task 4: Add Analytic Implicit Jacobian for General Path

**Files:**
- Create: `fitting/implicit_derivatives.py`
- Modify: `fitting/implicit_model.py`
- Test: `tests/test_implicit_derivatives.py`
- Test: `tests/test_implicit_model.py`

- [ ] **Step 1: Write analytic derivative tests**

Create `tests/test_implicit_derivatives.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_implicit_derivative_matches_finite_difference_for_simple_model() -> None:
    from fitting.implicit_derivatives import build_implicit_derivative_evaluator
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x + c*u",
        output_expression="u*u + q",
        parameters=("a", "b", "c", "q"),
    )
    evaluator = build_implicit_derivative_evaluator(definition)
    assert evaluator is not None

    x = {"x": mp.mpf("2")}
    params = {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.3"), "q": mp.mpf("1.5")}
    u = (params["a"] + params["b"] * x["x"]) / (1 - params["c"])

    derivative_a = evaluator.partial("a", x, params, {}, u)
    expected_du_da = 1 / (1 - params["c"])
    expected = 2 * u * expected_du_da

    assert mp.almosteq(derivative_a, expected, rel_eps=mp.mpf("1e-30"))


def test_implicit_derivative_parses_datalab_function_syntax() -> None:
    from fitting.implicit_derivatives import build_implicit_derivative_evaluator
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="Sin[u] + c",
        parameters=("a", "b", "c"),
    )

    evaluator = build_implicit_derivative_evaluator(definition)

    assert evaluator is not None
    value = evaluator.partial(
        "c",
        {"x": mp.mpf("2")},
        {"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.3")},
        {},
        mp.mpf("0.5"),
    )
    assert value == mp.mpf("1")


def test_implicit_derivative_accepts_constants_in_output_expression() -> None:
    from fitting.implicit_derivatives import build_implicit_derivative_evaluator
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="u",
        equation="d0 + d2/(n-u)^2",
        output_expression="R/(n-u)^2",
        parameters=("d0", "d2"),
        constants={"R": "100"},
    )

    evaluator = build_implicit_derivative_evaluator(definition)

    assert evaluator is not None
    value = evaluator.partial(
        "d0",
        {"n": mp.mpf("10")},
        {"d0": mp.mpf("-0.01"), "d2": mp.mpf("0.2")},
        {"R": mp.mpf("100")},
        mp.mpf("-0.01"),
    )
    assert mp.isfinite(value)
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
pytest -q tests/test_implicit_derivatives.py
```

Expected: fails because module does not exist.

- [ ] **Step 3: Implement derivative evaluator**

Create `fitting/implicit_derivatives.py`. It must use `shared.symbolic_math.parse_symbolic_expression()` and must pass constants into every generated callable:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import sympy as sp
from mpmath import mp

from shared.symbolic_math import parse_symbolic_expression

if TYPE_CHECKING:
    from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class ImplicitDerivativeEvaluator:
    implicit_variable: str
    ordered_names: tuple[str, ...]
    constant_names: tuple[str, ...]
    partial_functions: dict[str, object]

    def partial(
        self,
        parameter: str,
        variables: dict[str, mp.mpf],
        params: dict[str, mp.mpf],
        constants: dict[str, mp.mpf],
        implicit_value: mp.mpf,
    ) -> mp.mpf:
        fn = self.partial_functions[parameter]
        ordered = _ordered_scope_values(
            self.ordered_names,
            variables,
            params,
            constants,
            self.implicit_variable,
            implicit_value,
        )
        value = mp.mpf(fn(*ordered))
        if not mp.isfinite(value):
            raise ValueError(f"Analytic implicit derivative for {parameter!r} is not finite.")
        return value


def build_implicit_derivative_evaluator(
    definition: "ImplicitModelDefinition",
) -> ImplicitDerivativeEvaluator | None:
    names = [*definition.x_variables, definition.implicit_variable, *definition.parameters, *definition.constants]
    try:
        equation, symbols = parse_symbolic_expression(definition.equation, variables=names)
        output, _ = parse_symbolic_expression(definition.output_expression, variables=names)
    except Exception:
        return None

    u = symbols[definition.implicit_variable]
    # F = u - g(x,u,p) = 0
    implicit_residual = u - equation
    f_u = sp.diff(implicit_residual, u)
    if f_u == 0:
        return None
    ordered_names = tuple(names)
    partial_functions: dict[str, object] = {}
    for parameter in definition.parameters:
        p = symbols[parameter]
        f_p = sp.diff(implicit_residual, p)
        du_dp = -f_p / f_u
        dy_dp = sp.diff(output, p) + sp.diff(output, u) * du_dp
        try:
            partial_functions[parameter] = sp.lambdify(
                [symbols[name] for name in ordered_names],
                dy_dp,
                "mpmath",
            )
        except Exception:
            return None

    return ImplicitDerivativeEvaluator(
        implicit_variable=definition.implicit_variable,
        ordered_names=ordered_names,
        constant_names=tuple(definition.constants),
        partial_functions=partial_functions,
    )


def _ordered_scope_values(
    ordered_names: tuple[str, ...],
    variables: dict[str, mp.mpf],
    params: dict[str, mp.mpf],
    constants: dict[str, mp.mpf],
    implicit_variable: str,
    implicit_value: mp.mpf,
) -> list[mp.mpf]:
    values: list[mp.mpf] = []
    for name in ordered_names:
        if name in variables:
            values.append(mp.mpf(variables[name]))
        elif name in params:
            values.append(mp.mpf(params[name]))
        elif name in constants:
            values.append(mp.mpf(constants[name]))
        elif name == implicit_variable:
            values.append(mp.mpf(implicit_value))
        else:
            raise KeyError(f"No numeric value is available for symbol {name!r}.")
    return values
```

- [ ] **Step 4: Wire analytic derivatives into implicit model builder**

Modify `fitting/implicit_model.py`:

```python
from fitting.implicit_derivatives import build_implicit_derivative_evaluator
```

Change `build_implicit_model_specification()` so tests can compare analytic and numeric derivative paths without adding any GUI/workspace option:

```python
def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    seed_hint: ImplicitSeedHint | None = None,
    use_analytic_derivatives: bool = True,
) -> ModelSpecification:
```

After `cache = ImplicitEvaluationCache()`:

```python
    derivative_evaluator = build_implicit_derivative_evaluator(definition) if use_analytic_derivatives else None
```

Because `build_implicit_model_specification()` does not receive observations or initial parameters, add a runner-side preflight before calling `fit_custom_model()` for analytic implicit specs. Use the first, middle, and last observations with `state.compose(state.initial_vector())`; if any analytic partial is nonfinite or raises `ZeroDivisionError`/`ValueError`, rebuild the spec with `use_analytic_derivatives=False`. This keeps singular analytic derivatives from corrupting covariance while avoiding parameter-by-parameter fallback inside hot loops.

Replace gradient loop:

```python
    for parameter_index, parameter_name in enumerate(param_names):
        if derivative_evaluator is not None:
            gradient_funcs[parameter_name] = _build_analytic_partial(
                definition,
                cache,
                derivative_evaluator,
                parameter_name=parameter_name,
            )
        else:
            gradient_funcs[parameter_name] = _build_numeric_partial(
                definition,
                cache,
                parameter_index=parameter_index,
            )
```

Add helper:

```python
def _build_analytic_partial(
    definition: ImplicitModelDefinition,
    cache: ImplicitEvaluationCache,
    derivative_evaluator: object,
    *,
    parameter_name: str,
) -> MpfCallable:
    def _call(
        var_tuple: tuple[mp.mpf, ...],
        param_tuple: tuple[mp.mpf, ...],
    ) -> mp.mpf:
        solved = _solve_implicit_value(definition, cache, var_tuple, param_tuple)
        variables = {name: value for name, value in zip(definition.x_variables, var_tuple)}
        params = {name: value for name, value in zip(definition.parameters, param_tuple)}
        constants = {name: mp.mpf(value) for name, value in definition.constants.items()}
        try:
            return mp.mpf(derivative_evaluator.partial(parameter_name, variables, params, constants, solved))
        except (ZeroDivisionError, ValueError):
            cache.analytic_derivative_fallbacks += 1
            return _build_numeric_partial(
                definition,
                cache,
                parameter_index=definition.parameters.index(parameter_name),
            )(var_tuple, param_tuple)

    return _call
```

Add `analytic_derivative_fallbacks` to `ImplicitDiagnostics` and expose it in `result.details["implicit_diagnostics"]`. Add `_preflight_implicit_derivatives(spec, state, variable_data) -> bool` in `fitting/runner.py`. It must set the implicit point index before each sampled evaluation, solve `u` once, evaluate every analytic partial, and record a fallback-history item when analytic derivatives are disabled. Runtime singularities after preflight fall back per-call through the numeric partial wrapper above and increment the diagnostic counter instead of crashing the fit.

Call-site sequencing in `_fit_self_consistent()`:

```python
        spec = build_implicit_model_specification(
            definition,
            target_data=target_data,
            seed_hint=plan.seed_hint,
            use_analytic_derivatives=plan.use_analytic_derivatives,
        )
        if getattr(spec, "implicit_derivative_strategy", "") == "analytic_implicit":
            ok, reason = _preflight_implicit_derivatives(spec, state, variable_data)
            if not ok:
                fallback_history.append({
                    "from": "analytic_implicit_jacobian",
                    "to": "numeric_finite_difference",
                    "reason": reason,
                })
                spec = build_implicit_model_specification(
                    definition,
                    target_data=target_data,
                    seed_hint=plan.seed_hint,
                    use_analytic_derivatives=False,
                )
```

- [ ] **Step 5: Add diagnostic test that numeric solve count drops**

Append to `tests/test_implicit_model.py`:

```python
def test_general_implicit_uses_analytic_partials_when_available() -> None:
    from fitting.implicit_model import ImplicitModelDefinition, build_implicit_model_specification

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x + c*u",
        output_expression="u*u + q",
        parameters=("a", "b", "c", "q"),
    )
    spec = build_implicit_model_specification(definition)

    assert getattr(spec, "implicit_derivative_strategy") == "analytic_implicit"


def test_analytic_implicit_partials_reduce_solve_count_against_numeric_path() -> None:
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import fit_custom_model
    from fitting.implicit_model import ImplicitModelDefinition, build_implicit_model_specification

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("0.35"), mp.mpf("0.55"), mp.mpf("0.75"), mp.mpf("0.95")]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x + c*u",
        output_expression="u*u + q",
        parameters=("a", "b", "c", "q"),
    )
    state = build_parameter_state(
        {"a": {"initial": "0.1"}, "b": {"initial": "0.2"}, "c": {"initial": "0.1"}, "q": {"initial": "0.1"}},
        list(definition.parameters),
    )
    analytic_spec = build_implicit_model_specification(definition, use_analytic_derivatives=True)
    numeric_spec = build_implicit_model_specification(definition, use_analytic_derivatives=False)

    fit_custom_model(analytic_spec, state, {"x": xs}, ys, precision=50)
    fit_custom_model(numeric_spec, state, {"x": xs}, ys, precision=50)

    assert analytic_spec.implicit_diagnostics.points_solved < numeric_spec.implicit_diagnostics.points_solved


def test_analytic_and_numeric_implicit_fits_match_parameters_and_errors() -> None:
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import fit_custom_model
    from fitting.implicit_model import ImplicitModelDefinition, build_implicit_model_specification

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("0.35"), mp.mpf("0.55"), mp.mpf("0.75"), mp.mpf("0.95")]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u*u + c",
        parameters=("a", "b", "c"),
    )
    config = {
        "a": {"initial": "0.1"},
        "b": {"initial": "0.2"},
        "c": {"initial": "0.1"},
    }
    state = build_parameter_state(config, list(definition.parameters))

    analytic = fit_custom_model(
        build_implicit_model_specification(definition, use_analytic_derivatives=True),
        state,
        {"x": xs},
        ys,
        precision=50,
    )
    numeric = fit_custom_model(
        build_implicit_model_specification(definition, use_analytic_derivatives=False),
        state,
        {"x": xs},
        ys,
        precision=50,
    )

    for name, expected in numeric.params.items():
        assert mp.almosteq(analytic.params[name], expected, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-25"))
        assert mp.almosteq(
            analytic.param_errors_total[name],
            numeric.param_errors_total[name],
            rel_eps=mp.mpf("1e-12"),
            abs_eps=mp.mpf("1e-20"),
        )


def test_analytic_preflight_failure_reports_numeric_fallback_strategy(monkeypatch) -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("0.3"), mp.mpf("0.4"), mp.mpf("0.5"), mp.mpf("0.6")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u",
            parameters=("a", "b"),
        ),
    )
    monkeypatch.setattr("fitting.runner._preflight_implicit_derivatives", lambda *args, **kwargs: (False, "forced preflight failure"))

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=80)

    assert result.details["implicit_strategy"] == "general_implicit_numeric_finite_difference"
    assert any("forced preflight failure" in item["reason"] for item in result.details.get("fallback_history", []))
```

Set that attribute in `build_implicit_model_specification()`:

```python
    setattr(
        spec,
        "implicit_derivative_strategy",
        "analytic_implicit" if derivative_evaluator is not None else "numeric_finite_difference",
    )
```

- [ ] **Step 6: Run derivative tests**

Run:

```bash
pytest -q tests/test_implicit_derivatives.py tests/test_implicit_model.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fitting/implicit_derivatives.py fitting/implicit_model.py tests/test_implicit_derivatives.py tests/test_implicit_model.py
git commit -m "perf: use analytic implicit derivatives when available"
```

## Task 5: Add SciPy Implicit Backend for Double Precision

**Files:**
- Modify: `fitting/runner.py`
- Create: `tests/test_implicit_scipy_backend.py`
- Extend: `tests/test_fitting_runner_scipy_fallback.py`

- [ ] **Step 1: Write SciPy implicit backend tests**

Create `tests/test_implicit_scipy_backend.py`:

```python
from __future__ import annotations

import mpmath as mp
import pytest

pytest.importorskip("scipy.optimize")


def test_precision_16_general_implicit_tries_scipy_backend() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf(i) for i in range(1, 8)]
    implicit_values = [mp.mpf("0.2") + mp.mpf("0.5") * x for x in xs]
    ys = [value * value for value in implicit_values]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.4"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u + 0*x",
            parameters=("a", "b"),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    assert result.details["scipy_safety_passed"] is True


def test_scipy_implicit_spotcheck_uses_fresh_implicit_cache(monkeypatch) -> None:
    """Fails if `_spotcheck_scipy_solution` reuses the optimization spec/cache."""

    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    # Use any small general implicit problem that reaches the SciPy route.
    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("0.04"), mp.mpf("0.09"), mp.mpf("0.16"), mp.mpf("0.25")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u*u",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="u*u",
            parameters=("a", "b"),
        ),
    )

    seen_fresh_factory = {"called": False}
    original_spotcheck = __import__("fitting.runner", fromlist=["_spotcheck_scipy_solution"])._spotcheck_scipy_solution

    def _wrapped(*args, fresh_model_factory=None, **kwargs):
        assert fresh_model_factory is not None
        fresh_model_factory()
        seen_fresh_factory["called"] = True
        return original_spotcheck(*args, fresh_model_factory=fresh_model_factory, **kwargs)

    monkeypatch.setattr("fitting.runner._spotcheck_scipy_solution", _wrapped)

    FitRunner().fit(problem, {"x": xs}, ys, precision=16)

    assert seen_fresh_factory["called"] is True
```

- [ ] **Step 2: Run test and confirm current fallback**

Run:

```bash
pytest -q tests/test_implicit_scipy_backend.py
```

Expected: fails because precision-16 general implicit fitting still reports the mpmath fallback backend instead of `scipy_implicit_least_squares`.

- [ ] **Step 3: Reuse the existing SciPy candidate helper for implicit models**

Do not create a second copy of the SciPy least-squares implementation. Modify `_fit_with_scipy_least_squares()` in `fitting/runner.py` so it accepts `fresh_model_factory: Callable[[], ModelSpecification] | None = None` and sets an implicit row index when the model exposes `set_implicit_point_index`:

```python
    point_index_setter = getattr(model, "set_implicit_point_index", None)

    def _residual_vector(values) -> np.ndarray:
        params = parameter_state.compose(tuple(mp.mpf(str(float(value))) for value in values))
        residuals = []
        for idx, (obs, target) in enumerate(zip(observations, targets)):
            if point_index_setter is not None:
                point_index_setter(idx)
            residual = float(model.evaluate(obs, params) - target)
            if sqrt_weights is not None:
                residual *= float(sqrt_weights[idx])
            residuals.append(residual)
        return np.asarray(residuals, dtype=float)
```

The rest of `_fit_with_scipy_least_squares()` stays shared for custom and implicit models: bounds, weights, covariance, systematic errors, condition estimate, and mpmath spot-check continue to use the same code path.

Also update `_weighted_residual_norm()` and `_spotcheck_scipy_solution()` so implicit models get their row index before evaluation. For implicit models, the spot-check must use a fresh model specification/cache, not the same spec that SciPy just evaluated:

```python
def _weighted_residual_norm(
    model: ModelSpecification,
    params: dict[str, mp.mpf],
    variable_data: dict[str, Sequence[mp.mpf]],
    target_data: Sequence[mp.mpf],
    weights: list[mp.mpf] | None,
) -> float:
    observations, targets = _prepare_points(variable_data, target_data)
    point_index_setter = getattr(model, "set_implicit_point_index", None)
    total = mp.mpf("0")
    for idx, (obs, target) in enumerate(zip(observations, targets)):
        if point_index_setter is not None:
            point_index_setter(idx)
        residual = model.evaluate(obs, params) - target
        weight = mp.mpf(weights[idx]) if weights else mp.mpf("1")
        total += weight * residual * residual
    return float(total)


def _spotcheck_scipy_solution(
    model: ModelSpecification,
    observations: Sequence[dict[str, mp.mpf]],
    params: dict[str, mp.mpf],
    fitted_curve: Sequence[mp.mpf],
    *,
    fresh_model_factory: Callable[[], ModelSpecification] | None = None,
) -> bool:
    if not observations:
        return False
    if fresh_model_factory is not None:
        model = fresh_model_factory()
    point_index_setter = getattr(model, "set_implicit_point_index", None)
    indices = sorted({0, len(observations) // 2, len(observations) - 1})
    for index in indices:
        if point_index_setter is not None:
            point_index_setter(index)
        expected = mp.mpf(fitted_curve[index])
        actual = model.evaluate(observations[index], params)
        scale = max(mp.mpf("1"), mp.fabs(expected), mp.fabs(actual))
        if mp.fabs(actual - expected) > max(mp.mpf("1e-10"), mp.mpf("1e-8") * scale):
            return False
    return True
```

When calling this from the SciPy implicit route, pass `fresh_model_factory=lambda: build_implicit_model_specification(definition, target_data=target_data, seed_hint=plan.seed_hint, use_analytic_derivatives=False)`. Add a regression that would fail if an implicit cache returns a stale previous point during spot-check.

- [ ] **Step 4: Route SciPy implicit plan in `_fit_self_consistent()`**

Before the final general path:

```python
        if plan.kind is ImplicitPlanKind.SCIPY_IMPLICIT and not state.dependent_defs:
            try:
                spec = build_implicit_model_specification(
                    definition,
                    target_data=target_data,
                    seed_hint=plan.seed_hint,
                    use_analytic_derivatives=False,
                )
                candidate = _fit_with_scipy_least_squares(
                    spec,
                    state,
                    variable_data,
                    target_data,
                    weights=weights,
                    data_sigmas=data_sigmas,
                    fresh_model_factory=lambda: build_implicit_model_specification(
                        definition,
                        target_data=target_data,
                        seed_hint=plan.seed_hint,
                        use_analytic_derivatives=False,
                    ),
                )
                start_norm = _weighted_residual_norm(
                    spec,
                    state.compose(state.initial_vector()),
                    variable_data,
                    target_data,
                    weights,
                )
                accepted, reason = _accept_scipy_result(
                    candidate.result,
                    start_norm,
                    candidate.condition,
                    candidate.spotcheck_ok,
                )
                if accepted:
                    candidate.result.details["implicit_strategy"] = "scipy_general_implicit"
                    candidate.result.details["optimizer_backend"] = "scipy_implicit_least_squares"
                    candidate.result.details["scipy_safety_passed"] = True
                    diagnostics = getattr(spec, "implicit_diagnostics", None)
                    if diagnostics is not None:
                        candidate.result.details["implicit_diagnostics"] = {
                            "points_solved": int(diagnostics.points_solved),
                            "root_fallbacks": int(diagnostics.root_fallbacks),
                            "max_iterations_used": int(diagnostics.max_iterations_used),
                            "max_residual": str(diagnostics.max_residual),
                        }
                    return candidate.result
                scipy_fallback_reason = reason
            except Exception as exc:
                scipy_fallback_reason = f"scipy implicit unavailable or failed: {exc}"
        else:
            scipy_fallback_reason = ""
```

After final general result:

```python
        if scipy_fallback_reason:
            fallback_history.append(
                {
                    "from": "scipy_implicit_least_squares",
                    "to": "mpmath_high_precision",
                    "reason": scipy_fallback_reason,
                }
            )
        if fallback_history:
            result.details["fallback_history"] = fallback_history
            result.details["scipy_safety_passed"] = False
```

- [ ] **Step 5: Tighten SciPy test expected result**

Update `tests/test_implicit_scipy_backend.py`:

```python
    assert result.details["optimizer_backend"] == "scipy_implicit_least_squares"
    assert result.details["scipy_safety_passed"] is True
```

- [ ] **Step 6: Run SciPy/fallback tests**

Run:

```bash
pytest -q tests/test_implicit_scipy_backend.py tests/test_fitting_runner_scipy_fallback.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fitting/runner.py tests/test_implicit_scipy_backend.py tests/test_fitting_runner_scipy_fallback.py
git commit -m "perf: add automatic scipy implicit backend"
```

## Task 5b: Add SymPy Frozen-App Packaging Support

**Files:**
- Modify: `DataLab.spec`
- Modify: `build_mac_data_gui.sh`
- Modify: `build_windows_data_gui.ps1`
- Test: `tests/test_implicit_packaging.py`

- [ ] **Step 1: Add packaging regression**

Create `tests/test_implicit_packaging.py`:

```python
from pathlib import Path


def test_pyinstaller_packaging_collects_sympy() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = (root / "DataLab.spec").read_text(encoding="utf-8")
    mac = (root / "build_mac_data_gui.sh").read_text(encoding="utf-8")
    win = (root / "build_windows_data_gui.ps1").read_text(encoding="utf-8")

    assert "sympy" in spec.lower()
    assert "collect_all(\"sympy\")" in spec or "collect_all('sympy')" in spec
    assert "--collect-all \"sympy\"" in mac or "--collect-all sympy" in mac
    assert '"--collect-all", "sympy"' in win or "'--collect-all', 'sympy'" in win
```

- [ ] **Step 2: Add explicit SymPy collection**

Update:

- `DataLab.spec`: include `"sympy"` in the `collect_all` package loop and hidden imports.
- `build_mac_data_gui.sh`: add `--hidden-import "sympy"` and `--collect-all "sympy"`.
- `build_windows_data_gui.ps1`: add `--hidden-import`, `"sympy"`, and `--collect-all`, `"sympy"`.

- [ ] **Step 3: Run packaging tests and source smoke**

```bash
pytest -q tests/test_implicit_packaging.py
python - <<'PY'
from fitting.implicit_derivatives import build_implicit_derivative_evaluator
from fitting.implicit_model import ImplicitModelDefinition

definition = ImplicitModelDefinition(
    x_variables=("x",),
    implicit_variable="u",
    equation="a + b*x",
    output_expression="Sin[u] + c",
    parameters=("a", "b", "c"),
)
assert build_implicit_derivative_evaluator(definition) is not None
PY
```

- [ ] **Step 3b: Run frozen-app smoke when environment allows**

On macOS, run the existing mac packaging script after focused tests pass, launch the built app or perform the repository's established bundled-app smoke import, and record the result in `progress.md`. If signing/notarization or PyInstaller cache state makes a frozen build unavailable in the current environment, record an explicit environment skip; do not treat the string-only packaging test as sufficient release evidence.

- [ ] **Step 4: Commit**

```bash
git add DataLab.spec build_mac_data_gui.sh build_windows_data_gui.ps1 tests/test_implicit_packaging.py
git commit -m "build: package sympy for implicit fitting"
```

## Task 6: Keep GUI Automatic and Workspace-Compatible

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/parallel_preferences.py`
- Modify: `shared/parallel_config.py`
- Modify: `app_desktop/workers_core.py`
- Test: `tests/test_parallel_preferences.py`
- Test: `tests/test_app_desktop_workers_core.py`
- Test: `tests/test_desktop_implicit_model_ui.py`
- Test: `tests/test_workspace_implicit_round_trip.py`

- [ ] **Step 1: Add no-strategy-control GUI regression**

Append to `tests/test_desktop_implicit_model_ui.py`:

```python
def test_implicit_ui_does_not_expose_backend_strategy_choice(window) -> None:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QComboBox, QCheckBox, QWidget

    _select_model(window, "self_consistent")

    forbidden = []
    for attr in dir(window):
        lower = attr.lower()
        if "strategy" in lower and "implicit" in lower:
            forbidden.append(attr)
        if "backend" in lower and "implicit" in lower:
            forbidden.append(attr)

    inspected_text = []
    for child in window.findChildren(QWidget):
        inspected_text.append(child.objectName())
        if isinstance(child, QCheckBox):
            inspected_text.append(child.text())
        if isinstance(child, QComboBox):
            inspected_text.append(child.currentText())
            inspected_text.extend(child.itemText(index) for index in range(child.count()))
    for action in window.findChildren(QAction):
        inspected_text.append(action.objectName())
        inspected_text.append(action.text())
    lower_text = "\n".join(text.lower() for text in inspected_text if text)
    forbidden_terms = ["implicit backend", "implicit strategy", "隐式后端", "隐式策略", "new implicit backend", "新隐式拟合后端"]

    assert forbidden == []
    assert all(term not in lower_text for term in forbidden_terms)
```

- [ ] **Step 2: Add workspace non-persistence regression**

Append to `tests/test_workspace_implicit_round_trip.py`:

```python
def test_workspace_does_not_persist_implicit_backend_strategy(qtbot, tmp_path: Path) -> None:
    from app_desktop.window import ExtrapolationWindow

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.fit_model_combo, "self_consistent")

    path = tmp_path / "implicit-no-strategy.datalab"
    assert source._save_workspace_to_path(path)

    from shared.workspace_io import read_workspace

    loaded = read_workspace(path)
    fitting = loaded.manifest["workspace"]["config"]["fitting"]
    implicit = fitting["implicit"]

    assert "strategy" not in implicit
    assert "backend" not in implicit
    assert "optimizer" not in implicit
```

- [ ] **Step 3: Run GUI/workspace tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_implicit_model_ui.py tests/test_workspace_implicit_round_trip.py
```

Expected: fail before Step 3b because the current Options panel still exposes `parallel_implicit_backend_checkbox`.

- [ ] **Step 3b: Remove the existing implicit backend checkbox**

Current code has `parallel_implicit_backend_checkbox` / “Enable new implicit backend” in the Options panel. Remove this visible control and force the new implicit backend internally. If older settings contain an `enable_new_implicit_backend` value, ignore it during load and do not re-save it. Keep max-worker/reserve-core/nested-policy controls.

Also remove or neutralize the legacy compute branch in `app_desktop/workers_core.py` so stale persisted `enable_new_implicit_backend=False` cannot route a fit to `_execute_fit_job_payload_subprocess_legacy(...)`. Add a regression that constructs stale preferences/config with that field set to `False` and verifies the new backend path is still used.

Expected behavior:

- no checkbox/action/widget text contains “implicit backend”, “new implicit backend”, “隐式后端”, or “新隐式拟合后端”;
- no workspace or settings write path persists an implicit backend strategy flag;
- compute path always uses the new backend.

- [ ] **Step 4: Commit**

```bash
git add app_desktop/panels.py app_desktop/parallel_preferences.py shared/parallel_config.py app_desktop/workers_core.py tests/test_parallel_preferences.py tests/test_app_desktop_workers_core.py tests/test_desktop_implicit_model_ui.py tests/test_workspace_implicit_round_trip.py
git commit -m "test: keep implicit backend selection automatic"
```

## Task 7: Add Performance Benchmarks as Regression Tests

**Files:**
- Create: `tests/test_implicit_performance_regression.py`
- Modify: `docs/TEST_MATRIX.md`

- [ ] **Step 1: Create performance regression tests**

Create `tests/test_implicit_performance_regression.py`:

```python
from __future__ import annotations

import mpmath as mp


def _d8_rows() -> list[tuple[mp.mpf, mp.mpf, mp.mpf]]:
    raw = [
        ("4", "-0.01161947382", "0.00000000002"),
        ("5", "-0.01182004861", "0.00000000004"),
        ("6", "-0.01192302789", "0.00000000003"),
        ("7", "-0.01198312684", "0.00000000003"),
        ("8", "-0.01202134197", "0.00000000004"),
        ("9", "-0.01204718702", "0.00000000006"),
        ("10", "-0.01206549920", "0.00000000006"),
        ("11", "-0.01207895610", "0.00000000008"),
        ("12", "-0.0120891399", "0.0000000001"),
        ("13", "-0.0120970357", "0.0000000001"),
        ("14", "-0.0121032829", "0.0000000002"),
        ("15", "-0.0121083122", "0.0000000002"),
        ("16", "-0.0121124215", "0.0000000003"),
        ("17", "-0.0121158233", "0.0000000003"),
        ("18", "-0.0121186716", "0.0000000004"),
        ("19", "-0.0121210809", "0.0000000004"),
        ("20", "-0.0121231371", "0.0000000005"),
        ("21", "-0.0121249065", "0.0000000006"),
        ("22", "-0.0121264402", "0.0000000006"),
        ("23", "-0.0121277787", "0.0000000007"),
        ("24", "-0.0121289539", "0.0000000008"),
        ("25", "-0.012129992", "0.000000001"),
        ("26", "-0.012130913", "0.000000001"),
        ("27", "-0.012131734", "0.000000001"),
        ("28", "-0.012132469", "0.000000001"),
        ("29", "-0.012133131", "0.000000001"),
        ("30", "-0.012133729", "0.000000002"),
        ("31", "-0.012134269", "0.000000002"),
        ("32", "-0.012134761", "0.000000002"),
        ("33", "-0.012135210", "0.000000003"),
        ("34", "-0.012135623", "0.000000006"),
        ("35", "-0.01213599", "0.00000001"),
        ("36", "-0.01213634", "0.00000006"),
        ("37", "-0.0121366", "0.0000008"),
        ("38", "-0.01215", "0.00005"),
    ]
    return [(mp.mpf(n), mp.mpf(delta), mp.mpf(sigma)) for n, delta, sigma in raw]


def test_nonlinear_output_uses_output_space_backend_without_transforming_objective() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    rows = _d8_rows()
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    r_const = mp.mpf("100")
    energy = [r_const / (x - u) ** 2 for x, u in zip(n, delta)]
    sigma_energy = [mp.fabs(2 * r_const / (x - u) ** 3) * s for x, u, s in rows]
    base_config = {
        "d0": {"initial": "-0.01213"},
        "d2": {"initial": "0"},
        "d4": {"initial": "0"},
        "d6": {"initial": "0"},
        "d8": {"initial": "0"},
    }
    energy_problem = ModelProblem(
        model_type="self_consistent",
        expression="R/(n-delta)^2",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
            output_expression="R/(n-delta)^2",
            parameters=("d0", "d2", "d4", "d6", "d8"),
            constants={"R": str(r_const)},
        ),
    )

    energy_result = FitRunner().fit(
        energy_problem,
        {"n": n},
        energy,
        precision=80,
        weights=[1 / s**2 for s in sigma_energy],
        data_sigmas=sigma_energy,
    )

    assert energy_result.details["implicit_strategy"] == "analytic_implicit_output_space"
    assert energy_result.details.get("output_transform") is None
    assert all(
        mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-30"))
        for residual, fit, target in zip(energy_result.residuals, energy_result.fitted_curve, energy)
    )
    assert all(mp.isfinite(value) for value in energy_result.params.values())
    diagnostics = energy_result.details.get("implicit_diagnostics", {})
    assert int(diagnostics.get("points_solved", 10**9)) < len(n) * (len(base_config) + 2)


def test_nonlinear_output_analytic_strategy_matches_forced_numeric_errors() -> None:
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import fit_custom_model
    from fitting.implicit_model import ImplicitModelDefinition, build_implicit_model_specification

    rows = _d8_rows()[:12]
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    r_const = mp.mpf("100")
    energy = [r_const / (x - u) ** 2 for x, u in zip(n, delta)]
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        output_expression="R/(n-delta)^2",
        parameters=("d0", "d2", "d4"),
        constants={"R": str(r_const)},
    )
    state = build_parameter_state(
        {"d0": {"initial": "-0.01213"}, "d2": {"initial": "0"}, "d4": {"initial": "0"}},
        list(definition.parameters),
    )
    analytic = fit_custom_model(
        build_implicit_model_specification(definition, target_data=energy, use_analytic_derivatives=True),
        state,
        {"n": n},
        energy,
        precision=50,
    )
    numeric = fit_custom_model(
        build_implicit_model_specification(definition, target_data=energy, use_analytic_derivatives=False),
        state,
        {"n": n},
        energy,
        precision=50,
    )

    for name in definition.parameters:
        assert mp.almosteq(analytic.params[name], numeric.params[name], rel_eps=mp.mpf("1e-16"), abs_eps=mp.mpf("1e-24"))
        assert mp.almosteq(
            analytic.param_errors_total[name],
            numeric.param_errors_total[name],
            rel_eps=mp.mpf("1e-10"),
            abs_eps=mp.mpf("1e-20"),
        )
```

- [ ] **Step 2: Run performance regression**

Run:

```bash
pytest -q tests/test_implicit_performance_regression.py
```

Expected: pass with deterministic output-space strategy, residual-quality, and diagnostic assertions. Do not make this test depend on a hard wall-clock threshold; if wall-clock timing is useful locally, print or log it as non-gating diagnostic output.

- [ ] **Step 3: Document in test matrix**

Append to `docs/TEST_MATRIX.md`:

```markdown
- Implicit fitting performance: `tests/test_implicit_performance_regression.py` verifies that nonlinear-output implicit models stay on the output-space objective while using automatic SciPy or analytic-implicit acceleration.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_implicit_performance_regression.py docs/TEST_MATRIX.md
git commit -m "test: pin implicit fitting performance strategies"
```

## Task 8: Full Verification and Review Prep

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest -q \
  tests/test_implicit_planner.py \
  tests/test_symbolic_math.py \
  tests/test_implicit_transforms.py \
  tests/test_implicit_seed_hints.py \
  tests/test_implicit_derivatives.py \
  tests/test_implicit_model.py \
  tests/test_implicit_d8_runner_regression.py \
  tests/test_implicit_performance_regression.py \
  tests/test_fitting_runner_scipy_fallback.py \
  tests/test_implicit_scipy_backend.py \
  tests/test_implicit_packaging.py
```

Expected: all pass.

- [ ] **Step 2: Run GUI/workspace no-strategy tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q \
  tests/test_desktop_implicit_model_ui.py \
  tests/test_workspace_implicit_round_trip.py
```

Expected: all pass.

- [ ] **Step 3: Run static checks**

Run:

```bash
python -m compileall -q fitting app_desktop shared datalab_latex tests/test_symbolic_math.py tests/test_implicit_planner.py tests/test_implicit_transforms.py tests/test_implicit_seed_hints.py tests/test_implicit_derivatives.py tests/test_implicit_scipy_backend.py tests/test_implicit_performance_regression.py tests/test_implicit_packaging.py
ruff check fitting app_desktop shared/symbolic_math.py datalab_latex/derivatives.py tests/test_symbolic_math.py tests/test_implicit_planner.py tests/test_implicit_transforms.py tests/test_implicit_seed_hints.py tests/test_implicit_derivatives.py tests/test_implicit_scipy_backend.py tests/test_implicit_performance_regression.py tests/test_implicit_packaging.py
pytest -q tests/test_mypy_strict_clean_modules.py
```

Expected: all pass.

- [ ] **Step 3b: Re-run SymPy packaging/source smoke**

Task 5b makes SymPy packaging explicit. Re-run the packaging regression and source smoke as part of final verification:

```bash
pytest -q tests/test_implicit_packaging.py
python - <<'PY'
from fitting.implicit_derivatives import build_implicit_derivative_evaluator
from fitting.implicit_model import ImplicitModelDefinition

definition = ImplicitModelDefinition(
    x_variables=("x",),
    implicit_variable="u",
    equation="a + b*x",
    output_expression="Sin[u] + c",
    parameters=("a", "b", "c"),
)
assert build_implicit_derivative_evaluator(definition) is not None
PY
```

Expected: source smoke passes, and packaging files explicitly collect SymPy for frozen builds.

- [ ] **Step 4: Run full tests**

Run:

```bash
pytest -q
```

Expected: pass or only documented environment skips. Any failure in fitting/implicit/workspace tests must be fixed before review.

- [ ] **Step 5: Update planning files**

Append to `progress.md`:

```markdown
## Implicit Performance Auto Optimization
- Implemented automatic implicit fit planner, exact affine output fast path, nonlinear output seed hints, analytic implicit derivatives, and SciPy implicit double-precision fallback.
- GUI remains automatic; no strategy selector added.
- Verification:
  - focused implicit backend tests: PASS
  - GUI/workspace tests: PASS
  - compileall/ruff/mypy: PASS
  - full pytest: PASS or documented skips only
```

Append to `findings.md`:

```markdown
## Implicit Performance Optimization Findings
- The previous performance cliff happened because non-`delta` output expressions skipped observed-variable residual construction and fell directly to per-point implicit solve plus finite-difference parameter derivatives.
- Nonlinear inverse output transforms are not used to replace the fitted residual because that can change the least-squares objective and covariance semantics. Only exact affine output maps can be transformed to observed implicit-variable residuals.
- Nonlinear inverse-square forms may provide root-solver seed hints, but the residual and statistics remain in the user's original output space.
- The backend remains fully automatic; selected strategy is diagnostic metadata only.
```

- [ ] **Step 6: Commit final verification notes**

```bash
git add progress.md findings.md
git commit -m "docs: record implicit performance verification"
```

## Risks and Guardrails

- **Risk:** A nonlinear inverse transform can silently change the objective even when no free parameter appears in the inverse.
  - Guard: do not transform nonlinear output residuals. Use nonlinear inverses only as root-solver seed hints and verify they reconstruct the target before use.
- **Risk:** Transforming weights or `data_sigmas` incorrectly can bias weighted fits and total parameter errors.
  - Guard: only exact affine transforms with observed-linear inner equations propagate `target`, `weights`, and `data_sigmas`; parity tests compare params, total errors, residuals, `chi2`, reduced `chi2`, AIC/BIC, `r2`, and output-space `rmse`.
- **Risk:** A transformed `FitResult` can mix implicit-variable-space and output-space statistics.
  - Guard: remap by constructing output-space fitted values/residuals and recomputing weighted output-space statistics with the same formulas as the core fitter.
- **Risk:** SymPy solving can over-accept ambiguous branches.
  - Guard: branch-solving output is never used as a residual-space transform; seed hints require target reconstruction and reject invalid targets.
- **Risk:** Analytic derivative mistakes can produce wrong covariance/error estimates.
  - Guard: compare analytic partials against finite differences in tests; compare complete fit params and total errors against a forced numeric-derivative path; preflight analytic derivatives and fall back per-call to numeric partials on runtime singular/nonfinite derivatives.
- **Risk:** SciPy double precision can produce plausible but wrong results for high precision or ill-conditioned data.
  - Guard: only try SciPy for `precision <= 16`; require convergence, condition, residual improvement, and mpmath spot-check against a fresh implicit spec/cache.
- **Risk:** New SymPy use can diverge from existing formula support or fail in frozen builds.
  - Guard: extract existing symbolic registry into `shared.symbolic_math`, preserve existing function coverage, and explicitly collect SymPy in macOS/Windows PyInstaller packaging.
- **Risk:** Users may think strategy is manual.
  - Guard: no GUI/workspace field; record strategy only in result details.

## Self-Review

Spec coverage:

- No GUI strategy exposure: Task 6.
- Generic algorithm optimization, not quantum-defect special case: Tasks 1-5 build planner, transforms, seed hints, implicit derivatives, and SciPy backend for general implicit models.
- Automatically choose fastest correct computation: Tasks 1, 2, 4, 5.
- Preserve correctness and fallback behavior: every optimized path has safety/fallback tests.
- Performance case proving energy-like output does not stay on the slow general path: Task 7.

Placeholder scan:

- No unresolved vague terms or unspecified test instructions remain.

Type consistency:

- `ImplicitPlanKind`, `ImplicitPlan`, `OutputTransform`, and `ImplicitDerivativeEvaluator` are introduced before use.
- `FitRunner` integration references planner/transform fields defined in earlier tasks.

Claude review note:

- External Claude adversarial review was rerun with `PATH="/Users/fanghao/.local/bin:$PATH"` and Claude Code `2.1.156`; the previous plan was `REJECT`.
- New multi-agent review results: Python subagent `REJECT`, architecture subagent `CONTESTED`, sequencing subagent `CONTESTED`; Claude multi-review roles `skeptic`, `architect`, and `tests` completed with no failed roles and produced high/medium findings.
- Accepted findings applied in this revision: nonlinear inverse transforms no longer replace residual space; exact affine fast path is observed-linear-only; `data_sigmas` and output-space statistics are preserved for exact affine transforms; inverse-square branch solving is seed-only with target reconstruction and seed precedence over warm starts; the planner owns strategy feature detection; SciPy implicit routing reuses `_fit_with_scipy_least_squares()` and spot-checks against a fresh implicit spec; analytic derivative tests include full-fit parameter/error parity plus fallback metadata; GUI backend selector removal and SymPy packaging are explicit tasks.
- 2026-05-30 follow-up multi-agent/Claude review results: subagents returned `REJECT`/`CONTESTED` and Claude returned `REJECT`/`CONTESTED`. Accepted findings are now incorporated in the authoritative 2026-05-30 rules: current working-tree baseline is explicit; obsolete parser sketch is marked non-copyable; all real parser calls use keyword-only `variables=...`; Task 1 no longer depends on future seed/derivative modules; canonical implicit builder signature is preserved; `state.free_params` replaces `state.free_names`; Task 5b and Task 6 are split; GUI legacy backend removal includes `app_desktop/parallel_preferences.py`, `shared/parallel_config.py`, and `app_desktop/workers_core.py`; SciPy spot-check factory is wired into the helper call; affine fast-path tests include nonzero-residual general-path parity and nonfinite-scale rejection; seed hints return branch candidates and include constant-offset inverse-square coverage.
