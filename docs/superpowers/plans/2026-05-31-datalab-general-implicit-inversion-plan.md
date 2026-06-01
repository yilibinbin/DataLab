# DataLab General Implicit Inversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace narrow implicit-fit optimization shortcuts with one maintainable, automatic, target-aware inversion initializer for general self-consistent models, while keeping final accepted results in the user's original output-space objective.

**Architecture:** Keep `observed_linear` as the only true fast objective path, because it is correct when the observed target column is the implicit variable itself. For all other implicit-output models, build a generic `OutputInversion` layer that tries to solve `y = f(x, u, constants)` for candidate implicit values, validates branches against the original output expression, uses those values to seed parameter estimates and per-row root solves, then runs the original output-space implicit fitter. Delete the current non-general strategy surface: `exact_affine_output`, inverse-square-only seed hints, `observed_nonlinear`, and the implicit SciPy full-comparator gate.

**Tech Stack:** Python 3.11+, mpmath, SymPy through `shared.symbolic_math`, existing DataLab `safe_eval`, PySide6 worker boundary, pytest.

---

## Current Facts From `v2.5.2`

- Fact source: clean `v2.5.2` release checkout at `f2e46e8316f630720bebd6254211430122d5c687`.
- `fitting/implicit_planner.py` currently exposes `OBSERVED_LINEAR`, `OBSERVED_NONLINEAR`, `EXACT_AFFINE_OUTPUT`, `ANALYTIC_IMPLICIT_JACOBIAN`, and `GENERAL`.
- `fitting/implicit_classifier.py` also exposes `OBSERVED_NONLINEAR`; removing the runner/planner route is not enough unless the classifier strategy and tests are migrated too.
- `fitting/implicit_transforms.py` supports only constant-affine output transforms; tests explicitly reject `R/(n-delta)^2` as transformable.
- `fitting/implicit_seed_hints.py` is inverse-square-specific and is currently only a root-solver seed source. It also bypasses `parse_numeric_value()` for constants in one SymPy substitution path.
- `fitting/runner.py` pays an expensive implicit SciPy candidate/comparator cost for eligible precision, then returns the mpmath comparator in the real path.
- `quantum-defect-odd.datalab` shows the gap: direct observed `delta` fitting completes quickly, while energy-output fitting falls into repeated per-point root solving.

## Non-Negotiable Rules

- Do not add a GUI backend strategy selector.
- Do not add quantum-defect-specific logic, names, constants, or branches to fitting core.
- Do not accept nonlinear transformed u-space residuals as final fit statistics.
- Final `fitted_curve`, `residuals`, chi-square, AIC/BIC, covariance/error reporting, and workspace result snapshots must be computed in the original output space.
- Output inversion may seed the solver; only truly observed implicit-variable data may use `observed_linear` as the final objective route.
- Version 1 output inversion is restricted to `u = h(x, y, constants)` where the output expression does not depend on fitted parameters. Parameter-dependent output expressions such as `En - C/(n-u)^2` remain supported by the general output-space route but do not receive this initializer until a separately reviewed current-parameter inversion design exists.
- Temporary u-space seed fits are best-effort only. They must never receive output-space sigmas as if they were u-space sigmas, and failure must not fail the final output-space fit.
- Mutable implicit caches and warm starts must be branch-aware when target-derived implicit seeds are active. Include a stable candidate/selected-seed signature in both value-cache and warm-start keys for that route; do not use noisy output residual validation or bare row index as the primary cache-reuse gate.
- Inversion output must preserve row alignment and non-injective output maps. Dataset inversion returns all valid candidates per row as `list[tuple[mp.mpf, ...]]`, or returns `None` for the whole dataset when any row cannot be inverted within bounds. Do not mix targeted seeded rows with blind unseeded rows for a nonlinear/non-injective output initializer.
- Symbolic solving and numeric inversion must have strict runtime and candidate-count bounds. If bounds are exceeded, inversion is unavailable and the original general route runs.
- If inversion cannot be proven for the whole dataset, fall back to the original general output-space route.
- All symbolic parsing goes through `shared.symbolic_math`.
- All numeric constants, including compact uncertainty notation such as `3.2898419602500(36)[+9]`, go through `shared.uncertainty.parse_numeric_value()`.
- Remove or explicitly deprecate non-general optimization routes instead of layering new exceptions on top.
- Keep worker process isolation/cancellation behavior intact.

## File Structure

- Create `fitting/output_inversion.py`
  - Generic inversion detection, symbolic candidates, bounded numeric fallback, branch validation, derivative diagnostics, and dataset inverse values.
- Modify `fitting/implicit_planner.py`
  - Reduce planning to `OBSERVED_LINEAR`, `INVERTIBLE_OUTPUT_INITIALIZER`, and `GENERAL`.
- Modify `fitting/runner.py`
  - Remove `EXACT_AFFINE_OUTPUT`, `OBSERVED_NONLINEAR`, and implicit SciPy comparator execution.
  - Add output-inversion initializer flow before the general output-space route.
- Modify `fitting/implicit_model.py`
  - Replace inverse-square `seed_hint` plumbing with generic per-row target implicit seeds.
- Delete or reduce `fitting/implicit_transforms.py` and `fitting/implicit_seed_hints.py`
  - These should no longer be strategy-level modules.
- Modify `fitting/__init__.py`
  - Export the new inversion API only if needed by tests or worker boundaries.
- Modify tests:
  - Add `tests/test_output_inversion.py`.
  - Update planner, performance, D8, worker, and symbolic-architecture tests.
- Modify project planning files:
  - Mark the older implicit-performance plan as superseded for this topic.

---

### Task 1: RED Tests for Generic Output Inversion

**Files:**
- Create: `tests/test_output_inversion.py`
- Create: `fitting/output_inversion.py`

- [x] **Step 1: Add failing inversion detection tests**

Add:

```python
from __future__ import annotations

from mpmath import mp

from fitting.implicit_model import ImplicitModelDefinition
from fitting.output_inversion import detect_output_inversion


def _definition(output: str, constants: dict[str, str] | None = None) -> ImplicitModelDefinition:
    return ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="u",
        equation="d0 + d2/(n-u)^2",
        output_expression=output,
        parameters=("d0", "d2"),
        constants=constants or {},
    )


def test_detects_affine_output_as_generic_inversion() -> None:
    inversion = detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("4")}, mp.mpf("7")) == (mp.mpf("3"),)
        assert inversion.forward_row({"n": mp.mpf("4")}, mp.mpf("3")) == mp.mpf("7")


def test_detects_inverse_square_output_with_uncertain_constants() -> None:
    definition = _definition(
        "CR*M/(M+1)/(n-u)^2",
        {"CR": "3.2898419602500(36)[+9]", "M": "7294.29954171(17)"},
    )

    inversion = detect_output_inversion(definition, precision=50)

    assert inversion is not None
    with mp.workdps(50):
        target = mp.mpf("204397210.721")
        candidates = inversion.candidates_row({"n": mp.mpf("4")}, target)
        assert candidates
        assert any(candidate < 0 for candidate in candidates)
        assert all(mp.almosteq(inversion.forward_row({"n": mp.mpf("4")}, candidate), target, rel_eps=mp.mpf("1e-30")) for candidate in candidates)


def test_rejects_output_that_depends_on_fit_parameter() -> None:
    assert detect_output_inversion(_definition("d0/(n-u)^2"), precision=50) is None
```

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_output_inversion.py
```

Expected: import failure or missing implementation failure.

- [x] **Step 3: Add skeleton**

Create:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mpmath import mp


@dataclass(frozen=True)
class OutputInversion:
    expression: str
    reason: str
    candidates_row: Callable[[Mapping[str, mp.mpf], mp.mpf], tuple[mp.mpf, ...]]
    forward_row: Callable[[Mapping[str, mp.mpf], mp.mpf], mp.mpf]

    def inverse_candidates(
        self,
        variable_data: dict[str, Sequence[mp.mpf]],
        targets: Sequence[mp.mpf],
    ) -> list[tuple[mp.mpf, ...]] | None:
        return None


def detect_output_inversion(definition, *, precision: int | None = None) -> OutputInversion | None:
    return None
```

- [x] **Step 4: Verify meaningful failures**

Run the same pytest command. Expected: detection assertions fail.

### Task 2: Implement Symbolic and Numeric Inversion Candidates

**Files:**
- Modify: `fitting/output_inversion.py`
- Test: `tests/test_output_inversion.py`

- [x] **Step 1: Implement parser and symbolic candidate creation**

Implementation requirements:

- Parse output expression through `parse_symbolic_expression()`.
- Reject expressions whose free symbols include fitted parameters or undeclared names. This is an intentional v1 scope limit for the generic `u = h(x, y, constants)` initializer, not a rejection of fitting those models: parameter-dependent outputs still run through the existing general output-space implicit route.
- Substitute constants with `parse_numeric_value()`.
- Introduce an internal target symbol created after parsing. Do not pass a double-underscore name through `shared.symbolic_math`; use an internal `sympy.Symbol("_datalab_target_y")` or equivalent.
- Try `sympy.solve(Eq(output, target), implicit_variable)` inside a strict timeout. If the solve times out, raises, returns too many candidates, or returns unsupported conditional/set objects, fail closed to no inversion.
- The symbolic timeout must be implemented behind a killable boundary. Do not use a plain Python thread timeout for SymPy. Use a short-lived subprocess/process-pool worker that receives only primitive expression metadata, returns serialized candidate expressions, and is hard-terminated on timeout; if process creation is unavailable, skip symbolic solving and use the bounded numeric dataset path.
- Timeout accounting must separate worker startup from solve execution. The 250 ms symbolic-solve budget applies after a worker is ready; worker startup has its own configurable wall-clock cap. If startup exceeds its cap or process-pool warmup is unavailable, skip symbolic solving and rely on bounded numeric dataset inversion instead of freezing the GUI.
- Compile each candidate with `lambdify(..., "mpmath")`, then apply the same `__builtins__`-stripping hardening used by existing implicit derivative lambdify callables. Extract that hardening to a shared helper if needed; add a test proving compiled inversion callables do not retain ambient builtins.
- For each row, evaluate bounded candidates, keep all finite real values, and forward-evaluate the original output expression with a compiled hardened mpmath evaluator. Parser/runtime semantic mismatches must be caught by shared parser contract tests, not by per-row `safe_eval()` spot checks in the hot path.
- `candidates_row()` returns a tuple of every valid symbolic/closed-form candidate for that row, or an empty tuple when no symbolic candidate reconstructs the target within a scale-aware tolerance. It must not silently choose a branch.
- Numeric fallback is dataset-owned. Do not let production callers loop over `candidates_row()` to bypass global budget accounting. Numeric row attempts require an internal `InversionBudget` owned by `inverse_candidates()`.

- [x] **Step 2: Add numeric fallback tests**

Add tests for a monotonic output that SymPy may not solve robustly:

```python
def test_dataset_numeric_inversion_handles_exp_output() -> None:
    inversion = detect_output_inversion(_definition("Exp[u]"), precision=50)
    assert inversion is not None
    with mp.workdps(50):
        candidates = inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.e ** 2])
        assert candidates is not None
        solved = candidates[0][0]
        assert mp.almosteq(solved, mp.mpf("2"), rel_eps=mp.mpf("1e-30"))
```

Numeric fallback must use bounded attempts and fail closed:

- maximum 250 ms symbolic solve time per expression enforced after a killable worker is ready, a separate bounded worker-startup cap, and a 500 ms global numeric inversion budget per dataset owned by `inverse_candidates()`, with implementation constants centralized and overridable in tests,
- tight per-row iteration cap even within the global budget,
- maximum 16 scalar solve attempts per row,
- no more than 8 symbolic candidates plus 8 numeric candidates,
- no complex, non-finite, or non-real accepted values,
- scale-aware forward residual tolerance `max(1e-30, mp.eps**0.5 * max(1, abs(target), abs(reconstructed)))`,
- reject negative or domain-invalid targets for functions such as `Exp[u]`,
- reject singular points where `dy/du` is zero or non-finite,
- reject rows that require unbounded search outside a finite seed/bracket set.

Add negative tests for negative `Exp[u]` target, singular inverse-square target, non-finite candidate, and a no-real-root expression.
Add a timeout test that monkeypatches the solve worker to exceed the time budget and asserts `detect_output_inversion()` returns `None`.
Add a startup-overhead test that monkeypatches the symbolic worker startup path to exceed its startup cap and asserts detection fails closed.

- [x] **Step 3: Run tests**

```bash
PYTHONPATH=. pytest -q tests/test_output_inversion.py
```

Expected: pass.

### Task 3: Add Target-Aware Branch Candidates and Dataset Inversion

**Files:**
- Modify: `fitting/output_inversion.py`
- Test: `tests/test_output_inversion.py`

- [x] **Step 1: Extend API**

Add the branch-preserving dataset API:

```python
def inverse_candidates(
    self,
    variable_data: dict[str, Sequence[mp.mpf]],
    targets: Sequence[mp.mpf],
) -> list[tuple[mp.mpf, ...]] | None: ...

def derivative_values(
    self,
    variable_data: dict[str, Sequence[mp.mpf]],
    selected_values: Sequence[mp.mpf],
) -> list[mp.mpf | None]: ...

def forward_values(
    self,
    variable_data: dict[str, Sequence[mp.mpf]],
    selected_values: Sequence[mp.mpf],
) -> list[mp.mpf | None]: ...
```

`inverse_candidates()` must preserve `len(targets)` exactly when it succeeds, and each row tuple must contain every finite real candidate that reconstructs the observed output within tolerance. If any row has no valid candidate, if symbolic/numeric budgets are exhausted, or if candidate enumeration becomes ambiguous beyond the configured candidate cap, return `None` for the whole dataset and skip the inversion initializer. Do not return `[candidate, None, candidate]` for nonlinear output initializers.

`inverse_candidates()` is the only production API allowed to use numeric fallback. It owns a single dataset-level budget object and passes it through row attempts. Direct `candidates_row()` calls are limited to symbolic candidates and focused unit tests.

`derivative_values()` is diagnostic and seed-quality information only. It must not be used to report final nonlinear transformed uncertainties as if they were exact output-space uncertainties.

- [x] **Step 2: Add multi-branch tests**

Add:

```python
def test_multibranch_inverse_selects_output_valid_branch() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)
    assert inversion is not None
    with mp.workdps(50):
        candidates = inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("4"))
        assert set(candidates) == {mp.mpf("-2"), mp.mpf("2")}
        assert all(inversion.forward_row({"n": mp.mpf("0")}, candidate) == mp.mpf("4") for candidate in candidates)
```

- [x] **Step 3: Add singular derivative rejection test**

Add a row where the selected branch has zero or non-finite `dy/du`; it must either reject inversion or mark it unusable for solver seeding.
Add a row-alignment test where every row is invertible and assert `inverse_candidates()` returns one tuple per target, including multi-branch tuples such as `(-2, 2)` for `u^2`.
Add a whole-dataset-fallback test where one middle row is not invertible and assert `inverse_candidates()` returns `None`, so the runner never mixes seeded and unseeded rows for that dataset.
Add inverse-square branch tests proving both algebraic candidates are preserved until the implicit equation selects the branch.
Add a large synthetic dataset test proving branch selection performs bounded work: patch candidate evaluation counters and assert numeric inversion stops when the global dataset budget or row iteration cap is reached and returns `None` for the whole dataset.
Add a test proving repeated production calls do not call numeric fallback row-by-row through `candidates_row()` and cannot exceed the global dataset budget.
Add duplicate-row tests proving identical `(x, target, candidate tuple)` inputs still deduplicate, while duplicate `x` with different candidate/selected-seed signatures cannot bleed branches.
Add a parameter-dependent output test such as `En - C/(n-u)^2` proving `detect_output_inversion()` returns `None` and `plan_implicit_fit()` returns plain `GENERAL` with a reason such as `"parameter-dependent output inversion unavailable"`, without any quantum-defect-specific branch. Do not require inversion fallback history in the runner for this case because the inversion initializer route is never entered.
Add a runner test proving multi-branch `inverse_candidates()` skips the temporary u-space parameter seed fit and still passes candidate tuples into the final output-space solver.

### Task 4: Simplify Planner

**Files:**
- Modify: `fitting/implicit_planner.py`
- Modify: `tests/test_implicit_planner.py`

- [x] **Step 1: Replace enum**

Use:

```python
class ImplicitPlanKind(Enum):
    OBSERVED_LINEAR = "observed_linear"
    INVERTIBLE_OUTPUT_INITIALIZER = "invertible_output_initializer"
    GENERAL = "general"
```

- [x] **Step 2: Replace plan fields**

`ImplicitPlan` fields:

```python
kind: ImplicitPlanKind
reason: str
output_inversion: OutputInversion | None = None
use_analytic_derivatives: bool = False
```

- [x] **Step 3: Replace decision order**

Define the parameter-dependent-output guard and use it in the decision order. The helper must parse through `shared.symbolic_math`, compare free symbols with `definition.parameters`, and return `False` on parser failure so normal validation/error handling remains responsible for malformed expressions.

```python
def output_expression_uses_fit_parameters(definition: ImplicitModelDefinition) -> bool:
    parsed = try_parse_output_expression(definition.output_expression)
    if parsed is None:
        return False
    return bool(parsed.free_symbol_names & set(definition.parameters))
```

Then use:

```python
classification = ImplicitProblemClassifier().classify(definition)
if classification.strategy is ImplicitStrategy.OBSERVED_LINEAR:
    return ImplicitPlan(kind=ImplicitPlanKind.OBSERVED_LINEAR, reason="observed implicit variable with linear parameter equation")
inversion = detect_output_inversion(definition, precision=precision)
if inversion is not None:
    return ImplicitPlan(kind=ImplicitPlanKind.INVERTIBLE_OUTPUT_INITIALIZER, reason=inversion.reason, output_inversion=inversion, use_analytic_derivatives=True)
if output_expression_uses_fit_parameters(definition):
    return ImplicitPlan(kind=ImplicitPlanKind.GENERAL, reason="parameter-dependent output inversion unavailable", use_analytic_derivatives=True)
return ImplicitPlan(kind=ImplicitPlanKind.GENERAL, reason="general implicit output fit", use_analytic_derivatives=True)
```

- [x] **Step 4: Update tests**

Remove expectations for `EXACT_AFFINE_OUTPUT`, `OBSERVED_NONLINEAR`, and seed hints. Add inverse-square and affine outputs as `INVERTIBLE_OUTPUT_INITIALIZER`.
Delete or merge `ImplicitStrategy.OBSERVED_NONLINEAR` in `fitting/implicit_classifier.py`; do not leave a dangling classifier strategy with no planner/runner route. Update classifier tests so nonlinear observed-implicit equations classify into the general implicit route unless a separate reviewed route is introduced.

### Task 5: Replace Runner Routes With Output-Space Fit From Inversion Seeds

**Files:**
- Modify: `fitting/runner.py`
- Modify: `fitting/implicit_model.py`
- Test: `tests/test_implicit_performance_regression.py`
- Test: `tests/test_implicit_d8_runner_regression.py`

- [x] **Step 1: Remove non-general routes**

Delete self-consistent runner branches for:

- `EXACT_AFFINE_OUTPUT`
- `OBSERVED_NONLINEAR`
- implicit SciPy benchmark gate

Keep explicit custom-model SciPy routing unless its own tests fail.

- [x] **Step 2: Add generic inversion initializer**

For `INVERTIBLE_OUTPUT_INITIALIZER`:

- Compute `implicit_candidate_values = inversion.inverse_candidates(variable_data, target_data)`.
- If `implicit_candidate_values is None`, record `{"from": "output_inversion", "to": "general_output_space", "reason": "dataset_inversion_unavailable"}` and run the original general output-space route without target-derived seeds.
- If candidates are available, let the implicit evaluator select the best per-row branch by evaluating candidates against the current parameter-dependent implicit equation and continuity/warm-start preference. Do not select a global branch by output residual alone; all candidates already reconstruct the same observed output.
- Build a temporary observed-variable definition with `output_expression=implicit_variable`.
- If the temporary definition is `OBSERVED_LINEAR` and every row's `inverse_candidates()` tuple has exactly one candidate, call `fit_observed_implicit_variable_linear_model()` only to derive parameter initial values. Pass no output-space `data_sigmas` into this seed fit unless a future reviewed derivation proves exact u-space sigma semantics.
- If any row has multiple candidates, skip the temporary u-space parameter seed fit. Record `{"from": "output_inversion_parameter_seed", "to": "original_parameter_initials", "reason": "multi_branch_candidates"}` and use the full candidate tuples only as root-solve seeds in the final output-space route.
- If the temporary observed-variable definition is not `OBSERVED_LINEAR`, do not run a u-space parameter fit. Record `{"from": "output_inversion_parameter_seed", "to": "original_parameter_initials", "reason": "observed equation is not linear in free parameters"}` and continue with original parameter initial values plus `target_implicit_candidates`.
- Seed fit is best-effort. Bounded parameters, dependent expressions, singular data, multi-branch ambiguity, missing dataset inversion, or seed-fit failure must record fallback metadata and continue the final output-space fit using original parameter initial values and candidate-guided root solving where available.
- Preserve fixed values, bounds, and dependent parameter expressions when copying seed values back to the original parameter config. Only free parameter `initial` values may be overwritten by seed-fit results.
- Pass `target_implicit_candidates=implicit_candidate_values` into the original output-space implicit model so per-row root solves prefer a candidate that also satisfies the current parameter-dependent implicit equation.
- Candidate computation must be tied to the current target vector. For unweighted `data_sigmas` systematic refits, `target + sigma` and `target - sigma` runs must rebuild candidates from those perturbed output-space targets. Do not store original-target candidates on a long-lived spec and reuse them for perturbed-target refits.
- Implement this with an explicit current-target model/spec factory, not by passing a one-time candidate list into a single long-lived `ModelSpecification`. Extend the mpmath fitting path so `fit_custom_model()` or a new implicit-output-space wrapper can request a fresh `ModelSpecification` for each `current_targets` vector used by `_estimate_systematic_uncertainty()`. The factory must recompute `inversion.inverse_candidates(variable_data, current_targets)` before building the spec for original, `target + sigma`, and `target - sigma` runs.
- In `fitting/hp_fitter.py`, the rebuild point is the solver callable passed into `_estimate_systematic_uncertainty()`: the current `_run_once(current_targets, seed_override)` closure captures one fixed `model` specification. The implementation must move model/spec construction inside that current-target solver callable or replace the closure with a factory-backed solver, so each systematic refit target vector receives freshly recomputed inversion candidates and a fresh `ModelSpecification`.
- Run `_fit_mpmath_implicit_route()` on the original output expression and original target data.
- Set details:
  - `implicit_strategy="general_output_space_with_inversion_seed"`
  - `output_inversion=<reason>`
  - fallback history from inversion to output-space route.

- [x] **Step 3: Add explicit seed-config merge helper**

Add `_parameter_config_with_inversion_seed(original_config, parameter_state, seed_result)` in `fitting/runner.py` or a small helper module. It must:

- return a deep copy of the original parameter config,
- update only free parameter `"initial"` fields from finite seed-fit params,
- leave `"fixed"`, `"min"`, `"max"`, and `"expr"` unchanged,
- return the original config unchanged when seed fit is unavailable,
- have tests for fixed, bounded, and dependent parameters.
Add a nonlinear observed-equation test proving the helper does not attempt linear seed derivation and the final output-space route still runs.

- [x] **Step 4: Add target implicit seeds to `implicit_model.py`**

Change `build_implicit_model_specification()` signature:

```python
def build_implicit_model_specification(
    definition: ImplicitModelDefinition,
    target_data: Sequence[mp.mpf] | None = None,
    *,
    target_implicit_candidates: Sequence[tuple[mp.mpf, ...]] | None = None,
    use_analytic_derivatives: bool = False,
) -> ModelSpecification:
```

Replace `seed_hint` plumbing with `target_implicit_candidates`. Seed order and cache behavior must be branch-aware:

1. target implicit candidate selected by smallest parameter-dependent implicit-equation residual, then continuity/warm-start tie-breakers,
2. configured seed,
3. warm start.

Do not stop at a root solely because it converged if it violates the target output branch.
Use branch-signature cache and warm-start keys as the primary fix: include the target/candidate tuple or selected-seed signature in both the implicit value cache key and the warm-start key when `target_implicit_candidates` are present. Add a RED regression with duplicate `x`, identical parameters, and different output targets/branches proving the second row reuses the wrong cached root before the fix and passes after the key change. Add a second RED regression with duplicate identical rows proving the branch-signature key still allows cache hits when `(x, target, candidates)` are truly identical. Do not use noisy output residual validation as the primary cache reuse decision. The regression must drive evaluation through the normal row loop where the point context is set, not by calling the evaluate function without setting context.

The stable branch signature must be computed before the first cache lookup in the implicit solver. Pass it into `ImplicitEvaluationCache.get()/set()/status()` and warm-start get/set when target-derived candidates are active; computing the selected branch only after a cached root has already been returned is a bug.

Every implicit spec rebuild/probe path must receive the same current-target candidate context:

- `_fit_mpmath_implicit_route(..., target_implicit_candidates=...)`
- a current-target spec factory used by `fit_custom_model()` / `_estimate_systematic_uncertainty()`
- `_preflight_implicit_derivatives(..., target_implicit_candidates=...)`
- `_probe_implicit_derivative_parity(..., target_implicit_candidates=...)`
- every analytic-to-numeric fallback rerun and final parity rerun that calls `build_implicit_model_specification()`

Add regressions proving derivative preflight, runtime derivative fallback, and analytic-vs-numeric parity probes do not drop candidate context or switch root branches.

- [x] **Step 5: Add regression for the odd quantum-defect workspace shape**

Use the `quantum-defect-odd.datalab` data shape in a test fixture or inline data. Assert:

```python
assert result.details["implicit_strategy"] == "general_output_space_with_inversion_seed"
assert result.details["output_inversion"] == "validated symbolic output inversion"
assert elapsed_seconds < 2.0
assert all(mp.almosteq(r, f - y, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-8")) for r, f, y in zip(result.residuals, result.fitted_curve, energy))
assert result.chi2 == pytest.approx(sum(float(w * r * r) for w, r in zip(weights, result.residuals, strict=True)), rel=1e-10)
```

The tolerance must reflect energy scale, not delta scale.
Also assert RMSE/AIC/BIC are computed from output residuals; `fitted_curve` equals the original output expression evaluated at final parameters; covariance/errors are not copied from the temporary u-space seed fit; weighted and unweighted `data_sigmas` systematic refits still perturb original target data in output space.
Add an unweighted `data_sigmas` regression where `target + sigma` and `target - sigma` change inversion candidates; assert systematic refits recompute candidates from each perturbed output target and do not reuse original-target candidate tuples.
Add a regression around `fitting/hp_fitter.py::_estimate_systematic_uncertainty()` proving the `_run_once` solver callable, or its replacement, calls the current-target spec factory for the original target, the plus-sigma target, and the minus-sigma target. The test must fail if `_run_once` closes over one prebuilt spec/candidate list and reuses it for all three runs.
Add a regression asserting `result.details["implicit_strategy"]` remains `general_output_space_with_inversion_seed` after `_fit_mpmath_implicit_route()` returns; the generic route must not overwrite the caller's accepted strategy label.

### Task 6: Remove Obsolete Strategy Modules and Update Worker Boundaries

**Files:**
- Delete or reduce: `fitting/implicit_transforms.py`
- Delete or reduce: `fitting/implicit_seed_hints.py`
- Modify: `fitting/__init__.py`
- Modify: `tests/test_symbolic_math.py`
- Modify: `tests/test_app_desktop_workers_core.py`
- Modify: `app_desktop/workers_core.py`

- [x] **Step 1: Remove exports/imports**

Remove strategy-level exports for `OutputTransform`, `detect_output_transform`, `ImplicitSeedHint`, and `detect_seed_hint`.
Update `tests/test_implicit_scipy_backend.py` by deleting or replacing self-consistent implicit comparator tests that directly assert `_implicit_scipy_benchmark_gate`, `scipy_safety_passed`, `scipy_implicit_least_squares`, or comparator fallback metadata. Preserve custom-model SciPy tests that are outside self-consistent implicit routing.

- [x] **Step 2: Update static architecture guard**

`tests/test_symbolic_math.py::test_implicit_detectors_use_shared_symbolic_parser_boundary` should include `fitting/output_inversion.py` and `fitting/implicit_derivatives.py`. Remove only files that are actually deleted. If `fitting/implicit_transforms.py` or `fitting/implicit_seed_hints.py` survives as a reduced compatibility module and still calls SymPy, keep it in the guard list.

- [x] **Step 3: Tighten worker validation**

Validate at the deserialization boundary, not only before constructing `ModelProblem` or `ModelSpecification`:

- reject non-string `equation`, `output_expression`, `implicit_variable`, method, initial, and tolerance,
- reject non-string x-variable and parameter lists,
- reject non-dict constants and solve options,
- whitelist `process_start_method` to the supported values from `shared.parallel_backend` and reject malformed values,
- do not coerce malformed payloads through `str(...)`.

Add focused serial and process-boundary tests that send malformed serialized implicit definitions and assert clean validation errors.

- [x] **Step 4: Preserve constants numeric mode in workspaces**

Persist and restore the constants editor `numeric_mode` for custom and self-consistent/implicit constants. Add a workspace round-trip test with compact uncertainty notation such as `3.2898419602500(36)[+9]` proving the restored editor uses the same numeric mode and that compute normalization still routes through `parse_numeric_value()`.

### Task 7: Verification

**Files:**
- Test-only task

- [x] **Step 1: Focused tests**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_output_inversion.py tests/test_implicit_d8_runner_regression.py tests/test_app_desktop_workers_core.py tests/test_implicit_model.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_scipy_fallback.py tests/test_fitting_scipy_reference.py tests/test_fitting_runner_equivalence.py
```

- [x] **Step 2: Full source gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q -x $(git ls-files 'tests/*.py')
ruff check fitting shared app_desktop tests
python -m compileall -q data_extrapolation_gui.py app_desktop shared tools fitting cli tests
git diff --check
```

Add a release/build side-effect audit before packaging any implementation of this plan: build from a clean clone or isolated output directory, fail if `DataLab.spec` or source files drift unexpectedly after packaging, fail if duplicate local files such as `* 2*` would enter the source/archive/package boundary, and scan bundled metadata/docs/example workspaces for stale backend fields, private paths, and local-only artifacts.

- [x] **Step 3: GUI smoke**

Open the app, load a local quantum-defect example workspace, run fitting, and verify:

- no second app window,
- result completes within interactive time budget,
- final residuals are output-space energy residuals,
- result table saves/restores through workspace round trip.

Status: passed on 2026-06-01 with an offscreen GUI smoke that created and opened a local quantum-defect energy workspace, ran the self-consistent fit through the GUI worker/process boundary, verified no second visible `QMainWindow`, verified `general_output_space_with_inversion_seed`/validated symbolic inversion through the live result payload, checked output-space residuals (`fitted - target`), and restored the result snapshot through `capture_workspace()`/`restore_workspace()`. Runtime was 1.882s.

### Task 8: Multi-Model Review Gate

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [x] **Step 1: Codex multi-agent review**

Run read-only subagents for architecture, Python correctness/performance, GUI/workspace, and release/package risk. Main thread must accept/reject each finding and update the plan or code.

- [x] **Step 2: Claude and Gemini adversarial loop**

Run both:

```bash
<claude-for-codex-plugin>/scripts/claude-companion.mjs adversarial-review --json --scope working-tree --adversarial-lenses skeptic,architect,minimalist "Review DataLab general implicit output inversion implementation for correctness, performance, and maintainability."
<gemini-for-codex-plugin>/scripts/gemini-companion.mjs adversarial-review --json --scope working-tree --adversarial-lenses skeptic,architect,minimalist "Review DataLab general implicit output inversion implementation for correctness, performance, and maintainability."
```

If either returns `CONTESTED` or `REJECT`, reconcile findings in `findings.md`, revise the plan/code, and rerun until there are no accepted findings.

Status: accepted Gemini findings were fixed; the final Gemini follow-up timed out and is recorded as unavailable/hung, not as a PASS. Claude became available after quota reset; accepted findings were fixed; the final Claude follow-up returned malformed/non-JSON output with a clear textual PASS and no remaining high/medium blockers.

## Initial Accepted Review Findings

- High: nonlinear output inversion must not become final u-space objective. It is an initializer; final statistics remain output-space.
- High: inverse-square seed hints are domain-specific and must be replaced by generic output inversion.
- High: current implicit SciPy gate pays extra cost and should be removed from this path.
- High: configured/warm roots can lock in wrong branches; new seed order must be target-aware.
- High: `OBSERVED_NONLINEAR` conflicts with the “only observed_linear fast path” rule and should be removed unless a separate reviewed reason keeps it.
- Medium: worker typing/validation around fitting payloads is loose and should be tightened while touching the route boundary.
- High: target-aware seeds require branch-aware cache semantics; cached roots must include the target/candidate or selected-seed signature when target-derived candidates are active.
- High: parameter seed derivation must be a best-effort helper with explicit merge semantics for fixed, bounded, and dependent parameters.
- High: worker deserialization must reject malformed implicit definitions before `str(...)` coercion.
- Medium: test migration must include `tests/test_implicit_scipy_backend.py` and worker tests that currently assert implicit SciPy fallback metadata.
- Medium: numeric inversion fallback needs concrete candidate caps, residual tolerance, domain rejection, and negative tests.
- Medium: the private target symbol for symbolic solve must not use a parser-rejected double-underscore name.
- High: inversion rows must preserve dataset index alignment when the dataset succeeds; rejected rows make the dataset-level initializer unavailable instead of being dropped or represented as partial `None` seeds.
- High: nonlinear observed equations need explicit seed-fit fallback behavior.
- Medium: symbolic solve and numeric inversion need strict timeout/candidate caps.
- Medium: branch validation must use compiled hardened hot-path evaluators and avoid row-by-row `safe_eval()` bottlenecks.
- Medium: route metadata must not be overwritten by the general output-space helper after an inversion-seeded route is accepted.
- Medium: inversion lambdify callables must reuse the existing builtins-stripping hardening boundary.
- Low: parser-boundary guards must include any surviving reduced detector module that still calls SymPy.
- Low: branch-signature cache keys are the primary cache fix; validation-before-reuse is not sufficient under noisy residuals.
- High: cache isolation must use target/candidate or selected-seed signatures; output-residual validation and bare row index are not acceptable as the primary cache gate.
- Medium: warm-start reuse must also be branch-aware when target-derived candidates are active; param-only warm starts can otherwise reintroduce branch bleed.
- High: non-injective output inversion must preserve all valid candidates per row. A scalar `inverse_targets` API is insufficient because `u^2` and inverse-square expressions have multiple legitimate roots.
- High: global dataset inversion budget exhaustion or any non-invertible row must disable the inversion initializer for the whole dataset. Mixing seeded and blind rows is not acceptable for nonlinear/non-injective outputs.
- High: v1 output inversion only covers `u = h(x, y, constants)`. Parameter-dependent outputs remain valid fits but must not be silently accelerated by a parameter-blind inverse.
- Medium: temporary u-space parameter seed fitting is allowed only for singleton candidate rows; multi-branch inversions must not invent an early branch selector outside the final output-space solver.
- High: target-derived inversion candidates must be recomputed for every current target vector, including `target +/- sigma` systematic refits, or candidates will become stale and branch selection can be wrong.
- High: branch signatures must be available before implicit cache lookup; cache APIs and warm starts need the signature as an input, not a post-solve annotation.
- Medium: all implicit spec rebuild/probe paths must thread candidate context so derivative fallback and parity checks do not silently evaluate a different root-selection path.
- High: worker process payloads must validate `process_start_method` against supported values instead of accepting arbitrary stale/malformed settings.
- Medium: workspace persistence must preserve constants editor `numeric_mode`, otherwise compact uncertainty constants can be restored under a different parsing contract.
- Medium: production numeric inversion must be dataset-budget-owned; a public row API must not let callers bypass global budget accounting.
- Medium: SymPy timeout must use a killable process boundary, not an unsafe thread timeout.
- Medium: numeric inversion uses a global dataset budget, not a per-row timeout that scales linearly into UI freezes.
- Low: remove `safe_eval()` from the inversion hot path; parser/runtime parity belongs in shared parser contract tests.
