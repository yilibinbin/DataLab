# DataLab Root-Solving Follow-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the post-v2.7.0 root-solving work by cleaning the development baseline, making root uncertainty behavior explicit, adding selectable linear / Monte Carlo / scalar second-order propagation, preserving the shared uncertainty-input architecture, and carrying the result through review, validation, PR, and release readiness.

**Architecture:** Keep the existing `root_solving` package as the only root-solving backend and keep `shared.uncertainty`, `shared.input_normalization`, and `shared.computation_inputs` as the only numeric/uncertainty input grammar. Add a root-specific uncertainty policy layer that dispatches between existing first-order implicit propagation, new Monte Carlo propagation, and scalar second-order propagation without duplicating expression parsing or constants normalization. The desktop UI stores only primitive config values in workspaces and worker payloads; the worker reconstructs typed options before computation.

**Tech Stack:** Python 3, PySide6, mpmath, SciPy, SymPy where already used, pytest, ruff, mypy, PyInstaller packaging scripts, GitHub CLI.

---

## Original Goal Check

The original root-solving goal was to add a maintainable root-solving module with constants substitution, compact uncertainty notation, uncertainty propagation, precision-digit based SciPy/mpmath routing, desktop GUI mode, workspace persistence, and examples. v2.7.0 completed the first-version backend, batch workflow, GUI mode, workspace persistence, examples, PR #53, and release.

This follow-up does not change that goal. It closes the user-visible gap discovered after testing: root solving currently propagates uncertainty automatically but does not show a clear uncertainty section or provide the optional methods discussed earlier. The plan preserves the original maintainability constraint: no new uncertainty grammar, no separate precision selector, no duplicate constants parser, and no module-specific backend selector.

## Current Baseline

- Current repository: `/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab-review`.
- PR #53 is merged into `main`.
- Release `v2.7.0` is published at `https://github.com/yilibinbin/DataLab/releases/tag/v2.7.0`.
- Local checkout is still on `codex/root-solving-module`, not current `main`.
- Local worktree contains unrelated dirty tracked files and many untracked duplicate `" 2"` files. Do not stage them.
- Current root uncertainty implementation:
  - `root_solving/uncertainty.py` implements first-order linear implicit propagation.
  - `root_solving/solver.py` calls `attach_linear_uncertainty_with_system(...)` when `uncertain_inputs` exists.
  - `root_solving/batch.py` gets uncertainties through `shared.computation_inputs.extract_uncertainties(...)`.
  - `app_desktop/panels.py` exposes constants in `numeric_mode="uncertainty"` but has no root-specific uncertainty method UI.

## File Structure

### New Files

- `root_solving/uncertainty_policy.py`
  - Owns `RootUncertaintyOptions`, method resolution, warning text, and dispatch to linear / Monte Carlo / scalar second-order propagation.
  - Does not parse equations or constants. It receives `RootExpressionSystem`, `RootProblem`, `RootResult`, and `Mapping[str, UncertainValue]`.
  - Monte Carlo and scalar second-order reuse the already-built expression system by replacing nominal input values; they must not call the top-level parser for every sample.

- `tests/test_root_solving_uncertainty_policy.py`
  - Focused tests for method resolution, off mode, Monte Carlo deterministic seed behavior, scalar second-order behavior, and fallback/warning semantics.

### Modified Files

- `root_solving/models.py`
  - Add `RootUncertaintyMethod` and `RootUncertaintyOptions`.
  - Add `uncertainty_options: RootUncertaintyOptions` to `RootProblem`.

- `root_solving/normalization.py`
  - Normalize primitive uncertainty config dictionaries into `RootUncertaintyOptions`.
  - Keep old workspaces compatible by defaulting to `method="auto"`.

- `root_solving/solver.py`
  - Replace direct `attach_linear_uncertainty_with_system(...)` call with `attach_root_uncertainty(...)`.
  - Add an internal system-aware nominal solve path for Monte Carlo and second-order resampling. It must reuse the parsed `RootExpressionSystem` with shifted `nominal_inputs` to avoid reparsing expressions per sample.

- `root_solving/batch.py`
  - Pass uncertainty options through `normalize_root_problem_from_context(...)`.
  - Keep uncertainty extraction through `extract_uncertainties(...)`.
  - Add an end-to-end batch test proving UI/worker-selected methods affect row solves, including uncertain data columns carried through `row_values`.

- `root_solving/formatting.py`
  - Include method metadata in Markdown/log details without changing CSV schema unless contribution rows are explicitly added.

- `app_desktop/workers_core.py`
  - Extend `RootSolvingJob` and payload serialization with primitive `uncertainty_options`.
  - Preserve backward compatibility when the field is absent.

- `app_desktop/window.py`
  - Capture root uncertainty controls in `_build_root_solving_job(...)`.

- `app_desktop/panels.py`
  - Add a compact root uncertainty section below constants:
    - method combo: automatic, off, linear implicit, Monte Carlo, scalar second-order;
    - Monte Carlo sample count and seed controls visible only for Monte Carlo;
    - static method description label that is language-aware.

- `app_desktop/workspace_controller.py`
  - Persist and restore `config["root_solving"]["uncertainty_options"]`.
  - Old workspaces without this key open as `method="auto"`.

- `tests/test_desktop_root_solving_ui.py`
  - UI widget existence, visibility, dirty tracking, workspace round trip, and worker job payload tests.

- `tests/test_workspace_controller.py`
  - Workspace compatibility and new config persistence tests.

- `task_plan.md`, `findings.md`, `progress.md`
  - Track this follow-up and review results.

## Non-Goals

- Do not add another parser for `1.23(4)` or magnitude notation.
- Do not add root-specific precision controls.
- Do not add a manual SciPy/mpmath selector.
- Do not change fitting, implicit fitting, statistics, or extrapolation behavior except where shared tests prove no regression.
- Do not submit unrelated local `" 2"` files or `.superpowers/` generated content.
- Do not claim OS-level installer trust without Developer ID notarization or Authenticode.
- Do not support unbounded interactive Monte Carlo jobs. This follow-up caps the root Monte Carlo sample count at 50,000 and skips jobs whose `samples * roots` budget exceeds 50,000, preserving the existing 300-second root worker timeout behavior.

## Task 0: Clean Execution Baseline

**Files:**
- No source edits.
- Read: `/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab-review/task_plan.md`
- Read: `/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab-review/findings.md`
- Read: `/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab-review/progress.md`

- [ ] **Step 1: Record current git state**

Run:

```bash
git status --short --branch
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git rev-parse origin/main
/opt/homebrew/bin/gh pr view 53 --json state,url,statusCheckRollup
/opt/homebrew/bin/gh release view v2.7.0 --json tagName,url,targetCommitish,publishedAt
```

Expected:

```text
PR #53 state is MERGED.
Release v2.7.0 exists and targets origin/main commit f50c7d2...
The local checkout is not a clean main baseline.
```

- [ ] **Step 2: Create a clean implementation worktree**

Run:

```bash
git fetch origin
rm -rf /private/tmp/datalab-root-followup
git worktree add /private/tmp/datalab-root-followup origin/main
cd /private/tmp/datalab-root-followup
git switch -c codex/root-uncertainty-methods
```

Expected:

```text
New branch codex/root-uncertainty-methods starts from origin/main.
Main noisy checkout is untouched.
```

- [ ] **Step 3: Verify clean baseline**

Run:

```bash
git status --short --branch
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_root_solving_solver.py tests/test_root_solving_uncertainty.py tests/test_root_solving_batch.py tests/test_desktop_root_solving_ui.py
```

Expected:

```text
No local source changes.
Focused root-solving tests pass.
```

- [ ] **Step 4: Commit**

No commit is required for Task 0.

## Task 1: Root Uncertainty Options Data Model

**Files:**
- Modify: `root_solving/models.py`
- Modify: `root_solving/normalization.py`
- Test: `tests/test_root_solving_normalization.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests:

```python
def test_root_problem_defaults_uncertainty_options_to_auto() -> None:
    problem, _ = normalize_root_problem(
        equations=("x^2 - C",),
        unknown_rows=[{"name": "x", "initial": "2"}],
        known_rows=[],
        constants_enabled=True,
        constants_rows=[{"name": "C", "value": "4.0"}],
        mode="scalar",
        precision=80,
    )

    assert problem.uncertainty_options.method == "auto"
    assert problem.uncertainty_options.monte_carlo_samples == 2000
    assert problem.uncertainty_options.monte_carlo_seed == ""


def test_root_problem_normalizes_uncertainty_options_dict() -> None:
    problem, _ = normalize_root_problem(
        equations=("x^2 - C",),
        unknown_rows=[{"name": "x", "initial": "2"}],
        known_rows=[],
        constants_enabled=True,
        constants_rows=[{"name": "C", "value": "4.0"}],
        mode="scalar",
        precision=80,
        uncertainty_options={
            "method": "monte_carlo",
            "monte_carlo_samples": "250",
            "monte_carlo_seed": "123",
        },
    )

    assert problem.uncertainty_options.method == "monte_carlo"
    assert problem.uncertainty_options.monte_carlo_samples == 250
    assert problem.uncertainty_options.monte_carlo_seed == "123"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_root_solving_normalization.py::test_root_problem_defaults_uncertainty_options_to_auto tests/test_root_solving_normalization.py::test_root_problem_normalizes_uncertainty_options_dict
```

Expected: fails because `RootProblem` has no `uncertainty_options`.

- [ ] **Step 3: Add the model types**

In `root_solving/models.py`, add:

```python
RootUncertaintyMethod = Literal["auto", "off", "linear", "monte_carlo", "second_order"]


@dataclass(frozen=True)
class RootUncertaintyOptions:
    method: RootUncertaintyMethod = "auto"
    monte_carlo_samples: int = 2000
    monte_carlo_seed: str = ""
```

Update `RootProblem`:

```python
uncertainty_options: RootUncertaintyOptions = field(default_factory=RootUncertaintyOptions)
```

- [ ] **Step 4: Normalize primitive option dictionaries**

In `root_solving/normalization.py`, add:

```python
_ROOT_UNCERTAINTY_METHODS = {"auto", "off", "linear", "monte_carlo", "second_order"}


def normalize_root_uncertainty_options(raw: object | None) -> RootUncertaintyOptions:
    if raw is None:
        return RootUncertaintyOptions()
    if isinstance(raw, RootUncertaintyOptions):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("Root uncertainty options must be a mapping.")

    method = str(raw.get("method") or "auto").strip()
    if method not in _ROOT_UNCERTAINTY_METHODS:
        raise ValueError(f"Unknown root uncertainty propagation method: {method}")

    sample_raw = raw.get("monte_carlo_samples", 2000)
    try:
        samples = int(str(sample_raw).strip())
    except Exception as exc:
        raise ValueError("Monte Carlo sample count must be an integer.") from exc
    if samples < 2 or samples > 50000:
        raise ValueError("Monte Carlo sample count must be between 2 and 50000.")

    seed = str(raw.get("monte_carlo_seed") or "").strip()
    return RootUncertaintyOptions(
        method=cast(RootUncertaintyMethod, method),
        monte_carlo_samples=samples,
        monte_carlo_seed=seed,
    )
```

Add `uncertainty_options: object | None = None` to `normalize_root_problem(...)` and `normalize_root_problem_from_context(...)`, then pass `normalize_root_uncertainty_options(uncertainty_options)` into `RootProblem`.

Also add `uncertainty_options: object | None = None` to `solve_root_batch(...)` in `root_solving/batch.py` and pass it into both calls to `normalize_root_problem_from_context(...)`:

```python
normalize_root_problem_from_context(
    equations=clean_equations,
    unknown_rows=unknown_rows,
    row_values={header: "0" for header in clean_headers},
    constants_state=constants_state,
    mode=mode,
    precision=precision,
    scan_config=scan_config,
    uncertainty_options=uncertainty_options,
)
```

and:

```python
problem = normalize_root_problem_from_context(
    equations=clean_equations,
    unknown_rows=unknown_rows,
    row_values=source_values,
    constants_state=constants_state,
    mode=mode,
    precision=precision,
    scan_config=scan_config,
    uncertainty_options=uncertainty_options,
)
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_root_solving_normalization.py
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_root_solving_batch.py
PATH=/Users/fanghao/miniconda3/bin:$PATH ruff check root_solving/models.py root_solving/normalization.py tests/test_root_solving_normalization.py
PATH=/Users/fanghao/miniconda3/bin:$PATH python3 -m mypy --follow-imports=skip root_solving/models.py root_solving/normalization.py tests/test_root_solving_normalization.py
python3 -m compileall -q root_solving/models.py root_solving/normalization.py tests/test_root_solving_normalization.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add root_solving/models.py root_solving/normalization.py root_solving/batch.py tests/test_root_solving_normalization.py tests/test_root_solving_batch.py
git diff --cached --name-only
git commit -m "feat: add root uncertainty options"
```

Expected staged files are exactly the five files in the `git add` command.

## Task 2: Policy Dispatcher For Linear, Off, Monte Carlo, And Scalar Second-Order

**Files:**
- Create: `root_solving/uncertainty_policy.py`
- Modify: `root_solving/solver.py`
- Modify: `root_solving/__init__.py`
- Test: `tests/test_root_solving_uncertainty_policy.py`
- Test: `tests/test_root_solving_uncertainty.py`

- [x] **Step 1: Write RED tests for off and auto-linear behavior**

Create `tests/test_root_solving_uncertainty_policy.py` with:

```python
from __future__ import annotations

import mpmath as mp

from root_solving.batch import solve_root_batch
from root_solving.models import RootProblem, RootUncertaintyOptions, RootUnknown
from root_solving.solver import solve_root_problem
from shared.input_normalization import ConstantsState
from shared.uncertainty import UncertainValue


def _quadratic_problem(options: RootUncertaintyOptions) -> RootProblem:
    return RootProblem(
        equations=("x^2 - C",),
        unknowns=(RootUnknown("x", initial="2"),),
        constants={"C": "4.0"},
        mode="scalar",
        precision=80,
        uncertainty_options=options,
    )


def test_uncertainty_method_off_suppresses_uncertainty() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="off")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.roots[0].uncertainty is None
    assert result.roots[0].contributions == {}
    assert result.details["uncertainty_method"] == "off"


def test_uncertainty_method_auto_uses_linear_for_real_roots() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="auto")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert mp.almosteq(result.roots[0].uncertainty, mp.mpf("0.05"), rel_eps=mp.mpf("1e-50"))
    assert result.details["uncertainty_method"] == "linear"


def test_uncertainty_method_reports_skipped_when_linear_cannot_attach() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="0"),),
            constants={"C": "0.0"},
            mode="scalar",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(method="linear"),
        ),
        uncertain_inputs={"C": UncertainValue("0.0", "0.1")},
    )

    assert result.roots[0].uncertainty is None
    assert result.details["uncertainty_method"] == "skipped"


def test_uncertainty_inactive_inputs_leave_details_unchanged() -> None:
    for method in ("linear", "off"):
        result = solve_root_problem(
            RootProblem(
                equations=("x^2 - C",),
                unknowns=(RootUnknown("x", initial="2"),),
                constants={"C": "4.0", "unused": "1.0"},
                mode="scalar",
                precision=80,
                uncertainty_options=RootUncertaintyOptions(method=method),
            ),
            uncertain_inputs={"unused": UncertainValue("1.0", "0.1")},
        )

        assert result.roots[0].uncertainty is None
        assert "uncertainty_method" not in result.details


def test_uncertainty_complex_roots_preserve_real_root_warning() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 + C",),
            unknowns=(RootUnknown("x", initial="1"),),
            constants={"C": "1.0"},
            mode="polynomial",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(method="linear"),
        ),
        uncertain_inputs={"C": UncertainValue("1.0", "0.1")},
    )

    assert all(root.uncertainty is None for root in result.roots)
    assert result.details["uncertainty_method"] == "skipped"
    assert any("real-valued roots" in warning for warning in result.warnings)
```

- [x] **Step 2: Write RED Monte Carlo and scalar second-order tests**

Add:

```python
def test_uncertainty_method_monte_carlo_is_deterministic_with_seed() -> None:
    options = RootUncertaintyOptions(method="monte_carlo", monte_carlo_samples=400, monte_carlo_seed="42")
    first = solve_root_problem(
        _quadratic_problem(options),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )
    second = solve_root_problem(
        _quadratic_problem(options),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert first.details["uncertainty_method"] == "monte_carlo"
    assert first.roots[0].uncertainty is not None
    assert first.roots[0].uncertainty == second.roots[0].uncertainty
    assert mp.mpf("0.035") < first.roots[0].uncertainty < mp.mpf("0.07")


def test_batch_monte_carlo_uses_uncertain_data_columns() -> None:
    constants_state = ConstantsState(enabled=False, rows=(), text="", view="table", numeric_mode="uncertainty")
    batch = solve_root_batch(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2"),),
        data_headers=("A",),
        data_rows=((UncertainValue("4.0", "0.2"),),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        data_text_rows=(("4.0(2)",),),
        uncertainty_options={
            "method": "monte_carlo",
            "monte_carlo_samples": 200,
            "monte_carlo_seed": "9",
        },
    )

    root = batch.rows[0].result.roots[0]
    assert batch.rows[0].result.details["uncertainty_method"] == "monte_carlo"
    assert root.uncertainty is not None
    assert root.uncertainty > 0


def test_monte_carlo_rejects_scan_multiple_without_root_matching() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="0", lower="-3", upper="3"),),
            constants={"C": "4.0"},
            mode="scan_multiple",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(method="monte_carlo", monte_carlo_samples=20, monte_carlo_seed="1"),
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.details["uncertainty_method"] == "none"
    assert any("Monte Carlo" in warning and "scalar and system" in warning for warning in result.warnings)


def test_second_order_ignores_unused_uncertain_batch_columns() -> None:
    constants_state = ConstantsState(enabled=False, rows=(), text="", view="table", numeric_mode="uncertainty")
    batch = solve_root_batch(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2"),),
        data_headers=("A", "unused"),
        data_rows=((UncertainValue("4.0", "0.2"), UncertainValue("10.0", "1.0")),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        data_text_rows=(("4.0(2)", "10.0(1.0)"),),
        uncertainty_options={"method": "second_order"},
    )

    assert batch.rows[0].failure is None
    root = batch.rows[0].result.roots[0]
    assert root.uncertainty is not None
    assert batch.rows[0].result.details["uncertainty_method"] == "second_order"


def test_uncertainty_method_second_order_scalar_reports_bias_and_uncertainty() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="second_order")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.details["uncertainty_method"] == "second_order"
    assert result.roots[0].uncertainty is not None
    assert mp.mpf("0.049") < result.roots[0].uncertainty < mp.mpf("0.052")
    assert "uncertainty_bias" in result.details
```

- [x] **Step 3: Run tests to verify RED**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_root_solving_uncertainty_policy.py
```

Expected: fails because `root_solving/uncertainty_policy.py` and solver dispatch do not exist.

- [x] **Step 4: Implement policy dispatcher**

Create `root_solving/uncertainty_policy.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import random

from mpmath import mp

from root_solving.expression import RootExpressionSystem
from root_solving.models import RootProblem, RootResult, RootUncertaintyOptions
from root_solving.uncertainty import attach_linear_uncertainty_with_system
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

SampleSolver = Callable[[Mapping[str, mp.mpf]], RootResult]

_SECOND_ORDER_SYSTEM_WARNING = "Second-order root uncertainty is currently supported for scalar real roots only; use Monte Carlo for systems."


def attach_root_uncertainty(
    *,
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
) -> RootResult:
    if not uncertain_inputs:
        return result
    options = problem.uncertainty_options
    active_uncertain_inputs = _active_uncertain_inputs(system, uncertain_inputs)
    if not active_uncertain_inputs:
        return result
    if options.method == "off":
        return _with_method(result, "off")
    if any(not _is_real_number(root.value) for root in result.roots):
        return replace(
            result,
            details={**result.details, "uncertainty_method": "skipped"},
            warnings=(*result.warnings, "Linear uncertainty propagation is only supported for real-valued roots."),
        )
    if options.method in {"auto", "linear"}:
        return _with_linear_method(
            attach_linear_uncertainty_with_system(system, result, active_uncertain_inputs, precision=problem.precision)
        )
    if options.method == "monte_carlo":
        return _attach_monte_carlo(problem, system, result, active_uncertain_inputs, solve_nominal, options)
    if options.method == "second_order":
        return _attach_scalar_second_order(problem, system, result, active_uncertain_inputs, solve_nominal)
    return result
```

Then add the helper implementations in the same file:

```python
def _with_method(result: RootResult, method: str) -> RootResult:
    return replace(result, details={**result.details, "uncertainty_method": method})


def _with_linear_method(result: RootResult) -> RootResult:
    method = "linear" if any(root.uncertainty is not None for root in result.roots) else "skipped"
    return replace(result, details={**result.details, "uncertainty_method": method})


def _attach_monte_carlo(
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
    options: RootUncertaintyOptions,
) -> RootResult:
    if result.mode not in {"scalar", "system"}:
        return replace(
            result,
            details={
                **result.details,
                "uncertainty_method": "none",
                "uncertainty_requested_method": "monte_carlo",
            },
            warnings=(*result.warnings, "Monte Carlo root uncertainty is supported for scalar and system roots only."),
        )
    if options.monte_carlo_samples * max(1, len(result.roots)) > 50000:
        return replace(
            result,
            details={
                **result.details,
                "uncertainty_method": "none",
                "uncertainty_requested_method": "monte_carlo",
            },
            warnings=(*result.warnings, "Monte Carlo root uncertainty skipped: sample budget exceeds the interactive worker limit."),
        )
    rng = random.Random(_monte_carlo_seed(options.monte_carlo_seed))
    names = tuple(uncertain_inputs)
    values_by_root: list[list[mp.mpf]] = [[] for _ in result.roots]
    failures = 0
    with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        for _ in range(options.monte_carlo_samples):
            nominal_inputs = dict(system.nominal_inputs)
            for name in names:
                uncertain = uncertain_inputs[name]
                sampled = mp.mpf(uncertain.value) + mp.mpf(uncertain.uncertainty) * mp.mpf(rng.gauss(0.0, 1.0))
                if name in nominal_inputs:
                    nominal_inputs[name] = sampled
            try:
                sample_result = solve_nominal(nominal_inputs)
            except Exception:
                failures += 1
                continue
            if len(sample_result.roots) != len(result.roots):
                failures += 1
                continue
            for index, root in enumerate(sample_result.roots):
                if _is_real_number(root.value):
                    values_by_root[index].append(mp.mpf(root.value))
                else:
                    failures += 1
    warnings = tuple(result.warnings)
    if any(len(values) < 2 for values in values_by_root):
        warnings = (*warnings, "Monte Carlo root uncertainty skipped: fewer than two valid samples.")
    roots = tuple(
        replace(root, uncertainty=_sample_std(values) if len(values) >= 2 else None)
        for root, values in zip(result.roots, values_by_root, strict=True)
    )
    return replace(
        result,
        roots=roots,
        warnings=warnings,
        details={
            **result.details,
            "uncertainty_method": "monte_carlo",
            "monte_carlo_samples": options.monte_carlo_samples,
            "monte_carlo_failures": failures,
            "monte_carlo_valid_samples": min((len(values) for values in values_by_root), default=0),
        },
    )
```

Scalar second-order should use finite differences over solved roots instead of adding a second parser or new expression-system derivative API:

```python
def _attach_scalar_second_order(
    problem: RootProblem,
    system: RootExpressionSystem,
    result: RootResult,
    uncertain_inputs: Mapping[str, UncertainValue],
    solve_nominal: SampleSolver,
) -> RootResult:
    if result.mode != "scalar" or len(result.roots) != 1:
        linear = attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
        return replace(
            linear,
            details={**linear.details, "uncertainty_method": "linear", "uncertainty_requested_method": "second_order"},
            warnings=(*linear.warnings, _SECOND_ORDER_SYSTEM_WARNING),
        )
    linear = attach_linear_uncertainty_with_system(system, result, uncertain_inputs, precision=problem.precision)
    root = linear.roots[0]
    if root.uncertainty is None:
        return _with_linear_method(linear)
    bias = mp.mpf("0")
    variance = mp.mpf("0")
    with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        for input_name in uncertain_inputs:
            uncertain = uncertain_inputs[input_name]
            if input_name not in system.nominal_inputs:
                continue
            sigma = mp.mpf(uncertain.uncertainty)
            if sigma == 0:
                continue
            try:
                plus_root = _solve_scalar_with_shift(problem, system, input_name, sigma, solve_nominal)
                minus_root = _solve_scalar_with_shift(problem, system, input_name, -sigma, solve_nominal)
            except Exception:
                return replace(
                    _with_linear_method(linear),
                    details={
                        **linear.details,
                        "uncertainty_method": "linear",
                        "uncertainty_requested_method": "second_order",
                    },
                    warnings=(*linear.warnings, "Second-order root uncertainty fell back to linear propagation."),
                )
            center = mp.mpf(root.value)
            symmetric_delta = (plus_root - minus_root) / 2
            curvature_delta = plus_root - 2 * center + minus_root
            bias += mp.mpf("0.5") * curvature_delta
            variance += symmetric_delta**2 + mp.mpf("0.5") * curvature_delta**2
    return replace(
        linear,
        roots=(replace(root, value=mp.mpf(root.value) + bias, uncertainty=mp.sqrt(variance)),),
        details={**linear.details, "uncertainty_method": "second_order", "uncertainty_bias": mp.nstr(bias, 20)},
    )
```

Add `_solve_scalar_with_shift(...)` in `root_solving/uncertainty_policy.py`:

```python
def _solve_scalar_with_shift(
    problem: RootProblem,
    system: RootExpressionSystem,
    input_name: str,
    shift: mp.mpf,
    solve_nominal: SampleSolver,
) -> mp.mpf:
    nominal_inputs = dict(system.nominal_inputs)
    if input_name not in nominal_inputs:
        raise ValueError(f"Unknown uncertain input for second-order propagation: {input_name}")
    nominal_inputs[input_name] = mp.mpf(nominal_inputs[input_name]) + shift
    shifted = solve_nominal(nominal_inputs)
    if len(shifted.roots) != 1 or not _is_real_number(shifted.roots[0].value):
        raise ValueError("Second-order scalar propagation requires one real shifted root.")
    return mp.mpf(shifted.roots[0].value)
```

This intentionally reuses the already-built expression system. It samples constants, old known values, and batch `row_values` uniformly because all of them are represented in `system.nominal_inputs`.

Also define the helper semantics explicitly:

```python
def _is_real_number(value: object) -> bool:
    if isinstance(value, complex):
        return value.imag == 0
    if isinstance(value, mp.mpc):
        return bool(mp.im(value) == 0)
    return True


def _sample_std(values: Sequence[mp.mpf]) -> mp.mpf:
    if len(values) < 2:
        raise ValueError("At least two Monte Carlo samples are required.")
    mean = mp.fsum(values) / len(values)
    variance = mp.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mp.sqrt(variance)


def _active_uncertain_inputs(
    system: RootExpressionSystem,
    uncertain_inputs: Mapping[str, UncertainValue],
) -> dict[str, UncertainValue]:
    active_symbols = set().union(*(expression.free_symbols for expression in system.symbolic_expressions))
    return {
        name: value
        for name, value in uncertain_inputs.items()
        if name in system.symbol_map and system.symbol_map[name] in active_symbols
    }


def _monte_carlo_seed(seed: str) -> int | str | None:
    clean = str(seed).strip()
    if not clean:
        return None
    if clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit()):
        return int(clean)
    return clean
```

Monte Carlo is intentionally limited to `scalar` and square `system` modes in this follow-up. `polynomial` and `scan_multiple` can change root count or root ordering across samples; supporting those modes requires a separate reviewed root-matching algorithm.

- [x] **Step 5: Integrate solver dispatch without recursion**

In `root_solving/solver.py`, split the current top-level solve into a system-aware internal helper:

```python
from dataclasses import replace

from root_solving.models import RootUncertaintyOptions, immutable_mapping


def solve_root_problem(problem: RootProblem, *, uncertain_inputs: Mapping[str, UncertainValue] | None = None) -> RootResult:
    system = build_root_expression_system(problem)
    return _solve_root_problem_with_system(problem, system, uncertain_inputs)


def _solve_root_problem_with_system(
    problem: RootProblem,
    system: RootExpressionSystem,
    uncertain_inputs: Mapping[str, UncertainValue] | None = None,
) -> RootResult:
    ...
```

Then pass a system-preserving sample solver into `attach_root_uncertainty(...)`:

```python
def solve_with_nominal_inputs(nominal_inputs: Mapping[str, mp.mpf]) -> RootResult:
    sampled_system = replace(system, nominal_inputs=immutable_mapping(nominal_inputs))
    sampled_problem = replace(problem, uncertainty_options=RootUncertaintyOptions(method="off"))
    return _solve_root_problem_with_system(sampled_problem, sampled_system, uncertain_inputs=None)

propagated = attach_root_uncertainty(
    problem=problem,
    system=system,
    result=result,
    uncertain_inputs=uncertain_inputs,
    solve_nominal=solve_with_nominal_inputs,
)
```

The sample solver must pass `uncertain_inputs=None` because Monte Carlo and second-order have already changed the nominal input values. It must also use `replace(system, nominal_inputs=...)`, not `build_root_expression_system(...)`, so samples do not reparse equations.

- [x] **Step 6: Verify GREEN**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_solving_solver.py
PATH=/Users/fanghao/miniconda3/bin:$PATH ruff check root_solving tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_solving_solver.py
PATH=/Users/fanghao/miniconda3/bin:$PATH python3 -m mypy --follow-imports=skip root_solving tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_solving_solver.py
python3 -m compileall -q root_solving tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_solving_solver.py
```

Expected: all pass.

- [x] **Step 7: Commit**

Run:

```bash
git add root_solving/models.py root_solving/normalization.py root_solving/solver.py root_solving/uncertainty_policy.py root_solving/__init__.py tests/test_root_solving_uncertainty.py tests/test_root_solving_uncertainty_policy.py tests/test_root_solving_solver.py tests/test_root_solving_expression.py
git diff --cached --name-only
git commit -m "feat: add selectable root uncertainty propagation"
```

Expected: staged files are only root-solving backend/tests.

## Task 3: Worker Payload, Workspace Persistence, And Result Metadata

**Files:**
- Modify: `app_desktop/workers_core.py`
- Modify: `app_desktop/workspace_controller.py`
- Modify: `root_solving/formatting.py`
- Test: `tests/test_app_desktop_workers_core.py`
- Test: `tests/test_workspace_controller.py`
- Test: `tests/test_root_solving_formatting.py`

- [x] **Step 1: Write RED worker and workspace tests**

Add:

```python
def test_root_worker_payload_preserves_uncertainty_options() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        uncertainty_options={"method": "monte_carlo", "monte_carlo_samples": 25, "monte_carlo_seed": "7"},
        precision=80,
        display_digits=20,
    )

    payload = _serialize_root_solving_job(job)
    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options == {
        "method": "monte_carlo",
        "monte_carlo_samples": 25,
        "monte_carlo_seed": "7",
    }
```

Add workspace test:

```python
def test_workspace_preserves_root_uncertainty_options(window: Any, tmp_path: Path) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("monte_carlo"))
    window.root_monte_carlo_samples_spin.setValue(321)
    window.root_monte_carlo_seed_edit.setText("11")

    path = tmp_path / "root-options.datalab"
    save_workspace(window, path)
    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("auto"))
    window.root_monte_carlo_samples_spin.setValue(2000)
    window.root_monte_carlo_seed_edit.clear()

    load_workspace(window, path)

    assert window.root_uncertainty_method_combo.currentData() == "monte_carlo"
    assert window.root_monte_carlo_samples_spin.value() == 321
    assert window.root_monte_carlo_seed_edit.text() == "11"
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_app_desktop_workers_core.py::test_root_worker_payload_preserves_uncertainty_options tests/test_workspace_controller.py::test_workspace_preserves_root_uncertainty_options
```

Expected: fails because UI/payload/workspace fields do not exist.

- [x] **Step 3: Implement primitive worker payload**

Extend `RootSolvingJob` in `app_desktop/workers_core.py`. Append the new defaulted field after the existing `display_digits` field so dataclass non-default field ordering stays valid:

```python
uncertainty_options: dict[str, object] = field(default_factory=lambda: {"method": "auto"})
```

Extend `_serialize_root_solving_job(...)`:

```python
"uncertainty_options": {
    "method": str(job.uncertainty_options.get("method") or "auto"),
    "monte_carlo_samples": int(job.uncertainty_options.get("monte_carlo_samples") or 2000),
    "monte_carlo_seed": str(job.uncertainty_options.get("monte_carlo_seed") or ""),
},
```

Extend `_deserialize_root_solving_job(...)`:

```python
raw_uncertainty_options = payload.get("uncertainty_options", {})
if not isinstance(raw_uncertainty_options, Mapping):
    raw_uncertainty_options = {}
uncertainty_options = {
    "method": str(raw_uncertainty_options.get("method") or "auto"),
    "monte_carlo_samples": int(raw_uncertainty_options.get("monte_carlo_samples") or 2000),
    "monte_carlo_seed": str(raw_uncertainty_options.get("monte_carlo_seed") or ""),
}
```

and pass `uncertainty_options=uncertainty_options` into the restored `RootSolvingJob`.

In `_execute_root_solving_job_payload(...)`, pass:

```python
uncertainty_options=job.uncertainty_options,
```

to `solve_root_batch(...)`.

- [x] **Step 4: Persist workspace config**

In `app_desktop/workspace_controller.py`, modify `_capture_root_config(window)` so the returned root-solving config dictionary includes:

```python
"uncertainty_options": {
    "method": _combo_data(getattr(window, "root_uncertainty_method_combo", None), "auto"),
    "monte_carlo_samples": _value(getattr(window, "root_monte_carlo_samples_spin", None), 2000),
    "monte_carlo_seed": _text(getattr(window, "root_monte_carlo_seed_edit", None), ""),
},
```

In `_restore_root_config(window, config)`, add restore with default after mode restore and before returning from the valid-config path:

```python
options = dict(config.get("uncertainty_options") or {})
_set_combo_data(getattr(window, "root_uncertainty_method_combo", None), str(options.get("method") or "auto"))
samples_widget = getattr(window, "root_monte_carlo_samples_spin", None)
if samples_widget is not None:
    samples_widget.setValue(int(options.get("monte_carlo_samples") or 2000))
_set_text(getattr(window, "root_monte_carlo_seed_edit", None), str(options.get("monte_carlo_seed") or ""))
```

- [x] **Step 5: Format method metadata**

In `root_solving/formatting.py`, ensure Markdown details include:

```text
uncertainty method: linear
monte carlo samples: 2000
monte carlo failures: 0
```

when those fields exist in `RootResult.details`.

- [x] **Step 6: Verify GREEN**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_app_desktop_workers_core.py tests/test_workspace_controller.py tests/test_root_solving_formatting.py
PATH=/Users/fanghao/miniconda3/bin:$PATH ruff check app_desktop/workers_core.py app_desktop/workspace_controller.py root_solving/formatting.py tests/test_app_desktop_workers_core.py tests/test_workspace_controller.py tests/test_root_solving_formatting.py
python3 -m compileall -q app_desktop/workers_core.py app_desktop/workspace_controller.py root_solving/formatting.py tests/test_app_desktop_workers_core.py tests/test_workspace_controller.py tests/test_root_solving_formatting.py
```

Expected: all pass.

- [x] **Step 7: Commit**

Run:

```bash
git add app_desktop/workers_core.py app_desktop/workspace_controller.py root_solving/formatting.py tests/test_app_desktop_workers_core.py tests/test_workspace_controller.py tests/test_root_solving_formatting.py
git diff --cached --name-only
git commit -m "feat: persist root uncertainty options"
```

## Task 4: Desktop Root Uncertainty UI

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Test: `tests/test_desktop_root_solving_ui.py`

- [x] **Step 1: Write RED UI tests**

Add:

```python
def test_root_solving_page_has_uncertainty_controls(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))

    assert _combo_data(window.root_uncertainty_method_combo) == [
        "auto",
        "off",
        "linear",
        "monte_carlo",
        "second_order",
    ]
    assert window.root_monte_carlo_samples_spin.minimum() == 2
    assert window.root_monte_carlo_samples_spin.maximum() == 50000
    assert window.root_monte_carlo_samples_spin.value() == 2000
    assert window.root_uncertainty_method_help_label.text()


def test_root_monte_carlo_controls_visible_only_for_monte_carlo(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))

    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("auto"))
    assert not window.root_monte_carlo_samples_spin.isVisible()
    assert not window.root_monte_carlo_seed_edit.isVisible()

    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("monte_carlo"))
    assert window.root_monte_carlo_samples_spin.isVisible()
    assert window.root_monte_carlo_seed_edit.isVisible()
```

Add worker-build test:

```python
def test_root_job_collects_uncertainty_options(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x^2 - C")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "2", "lower": "", "upper": ""}])
    window.root_constants_editor.set_rows([{"name": "C", "value": "4.0(2)"}])
    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("monte_carlo"))
    window.root_monte_carlo_samples_spin.setValue(123)
    window.root_monte_carlo_seed_edit.setText("5")

    job = window._build_root_solving_job(data_path=None, manual_content="")

    assert job.uncertainty_options == {
        "method": "monte_carlo",
        "monte_carlo_samples": 123,
        "monte_carlo_seed": "5",
    }
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_root_solving_ui.py::test_root_solving_page_has_uncertainty_controls tests/test_desktop_root_solving_ui.py::test_root_monte_carlo_controls_visible_only_for_monte_carlo tests/test_desktop_root_solving_ui.py::test_root_job_collects_uncertainty_options
```

Expected: fails because controls do not exist.

- [x] **Step 3: Add UI controls below root constants**

In `app_desktop/panels.py`, after `root_constants_editor`, create:

```python
self.root_uncertainty_group = QGroupBox()
self._register_text(self.root_uncertainty_group, "根的不确定度传播", "Root uncertainty propagation")
root_uncertainty_layout = QFormLayout(self.root_uncertainty_group)

self.root_uncertainty_method_combo = QComboBox()
self.root_uncertainty_method_combo.addItem(self._tr("自动", "Automatic"), "auto")
self.root_uncertainty_method_combo.addItem(self._tr("关闭", "Off"), "off")
self.root_uncertainty_method_combo.addItem(self._tr("线性隐函数", "Linear implicit"), "linear")
self.root_uncertainty_method_combo.addItem(self._tr("蒙特卡洛", "Monte Carlo"), "monte_carlo")
self.root_uncertainty_method_combo.addItem(self._tr("标量二阶", "Scalar second-order"), "second_order")
root_uncertainty_layout.addRow(self._tr("方法", "Method"), self.root_uncertainty_method_combo)

self.root_monte_carlo_samples_spin = QSpinBox()
self.root_monte_carlo_samples_spin.setRange(2, 50000)
self.root_monte_carlo_samples_spin.setValue(2000)
root_uncertainty_layout.addRow(self._tr("样本数", "Samples"), self.root_monte_carlo_samples_spin)

self.root_monte_carlo_seed_edit = QLineEdit()
root_uncertainty_layout.addRow(self._tr("随机种子", "Seed"), self.root_monte_carlo_seed_edit)

self.root_uncertainty_method_help_label = QLabel()
self.root_uncertainty_method_help_label.setWordWrap(True)
root_uncertainty_layout.addRow(self.root_uncertainty_method_help_label)
root_layout.addWidget(self.root_uncertainty_group)
```

Add `_on_root_uncertainty_method_changed()` to show/hide Monte Carlo controls and update help text. Do not use in-app prose explaining general software behavior; the label should only state the selected calculation method and trigger condition.

- [x] **Step 4: Connect dirty tracking and job build**

In `app_desktop/window.py`, include:

```python
"method": str(self.root_uncertainty_method_combo.currentData() or "auto"),
"monte_carlo_samples": int(self.root_monte_carlo_samples_spin.value()),
"monte_carlo_seed": self.root_monte_carlo_seed_edit.text().strip(),
```

in `RootSolvingJob`.

Connect changed signals to `_mark_workspace_dirty`.

- [x] **Step 5: Verify GREEN**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py::test_workspace_preserves_root_uncertainty_options
PATH=/Users/fanghao/miniconda3/bin:$PATH ruff check app_desktop/panels.py app_desktop/window.py tests/test_desktop_root_solving_ui.py
python3 -m compileall -q app_desktop/panels.py app_desktop/window.py tests/test_desktop_root_solving_ui.py
```

Expected: all pass.

- [x] **Step 6: Commit**

Run:

```bash
git add app_desktop/panels.py app_desktop/window.py tests/test_desktop_root_solving_ui.py
git diff --cached --name-only
git commit -m "feat: expose root uncertainty controls"
```

## Task 5: Examples And Documentation

**Files:**
- Create or modify: `examples/workspaces/root-scalar-with-uncertainty.datalab`
- Create: `examples/workspaces/root-monte-carlo-uncertainty.datalab`
- Create: `examples/workspaces/root-batch-quadratic.datalab`
- Modify: `docs/METHODS_THEORY.en.tex`
- Modify: `docs/METHODS_THEORY.zh.tex` if present
- Test: `tests/test_example_workspaces.py`

- [ ] **Step 1: Write RED example tests**

Add:

```python
def test_root_uncertainty_example_workspaces_load() -> None:
    names = {
        "root-scalar-with-uncertainty.datalab",
        "root-monte-carlo-uncertainty.datalab",
        "root-batch-quadratic.datalab",
    }
    for name in names:
        loaded = read_workspace(Path("examples/workspaces") / name)
        workspace = loaded.manifest["workspace"]
        assert workspace["current_mode"] == "root_solving"
        assert "root_solving" in workspace["config"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_example_workspaces.py::test_root_uncertainty_example_workspaces_load
```

Expected: fails until the missing examples exist.

- [ ] **Step 3: Add examples**

Create examples with these behaviors:

- `root-scalar-with-uncertainty.datalab`: equation `x^2 - C`, constant `C=4.0(2)`, scalar mode, uncertainty method `linear`.
- `root-monte-carlo-uncertainty.datalab`: same equation and constant, method `monte_carlo`, samples `2000`, seed `42`.
- `root-batch-quadratic.datalab`: equation `x^2 - A`, data column `A` with rows `1.0(1)`, `4.0(2)`, `9.0(3)`, scalar mode, unknown `x` initial value `1`.

Use the existing workspace writer helper instead of hand-writing zip archives.

- [ ] **Step 4: Document method limits**

In methods docs, add concise statements:

```tex
For implicit root solving, DataLab supports independent-input first-order propagation through the implicit function theorem. Monte Carlo propagation samples uncertain constants and data inputs, solves each sampled problem, and reports sample standard deviation. Scalar second-order propagation is local and intended for smooth scalar roots; for systems or branch-sensitive problems, Monte Carlo is preferred.
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH PYTHONPATH=. pytest -q tests/test_example_workspaces.py tests/test_workspace_io.py
python3 -m compileall -q tests/test_example_workspaces.py
git diff --check
```

Expected: all pass or only the known duplicate-manifest warning appears in pytest.

- [ ] **Step 6: Commit**

Run:

```bash
git add examples/workspaces/root-scalar-with-uncertainty.datalab examples/workspaces/root-monte-carlo-uncertainty.datalab examples/workspaces/root-batch-quadratic.datalab docs/METHODS_THEORY.en.tex docs/METHODS_THEORY.zh.tex tests/test_example_workspaces.py
git diff --cached --name-only
git commit -m "docs: add root uncertainty examples"
```

If `docs/METHODS_THEORY.zh.tex` does not exist, omit it from `git add`.

## Task 6: Final Verification And Reviews

**Files:**
- No source edits unless reviews find accepted blockers.
- Update: `task_plan.md`
- Update: `findings.md`
- Update: `progress.md`

- [ ] **Step 1: Run focused verification**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q \
  tests/test_root_solving_solver.py \
  tests/test_root_solving_uncertainty.py \
  tests/test_root_solving_uncertainty_policy.py \
  tests/test_root_solving_batch.py \
  tests/test_root_solving_formatting.py \
  tests/test_app_desktop_workers_core.py \
  tests/test_desktop_root_solving_ui.py \
  tests/test_workspace_controller.py \
  tests/test_example_workspaces.py
```

Expected: pass.

- [ ] **Step 2: Run static checks**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH ruff check root_solving app_desktop/workers_core.py app_desktop/workspace_controller.py app_desktop/panels.py app_desktop/window.py tests/test_root_solving_uncertainty_policy.py tests/test_desktop_root_solving_ui.py
PATH=/Users/fanghao/miniconda3/bin:$PATH python3 -m mypy --follow-imports=skip root_solving tests/test_root_solving_uncertainty_policy.py
python3 -m compileall -q root_solving app_desktop tests
git diff --check
```

Expected: pass. If broad compileall finds unrelated pre-existing duplicate files, rerun compileall over touched files and record the blocker in `progress.md`.

- [ ] **Step 3: Run full tracked tests**

Run:

```bash
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q -x $(git ls-files 'tests/*.py')
```

Expected: pass with only known unrelated warnings.

- [ ] **Step 4: Run model reviews**

Run Codex local review with a subagent:

```text
Review the root uncertainty follow-up implementation against the plan. Focus on parser reuse, recursion safety in Monte Carlo, scalar second-order correctness, workspace compatibility, UI clarity, and test coverage. Return PASS/CONTESTED/REJECT with findings.
```

Run Claude:

```bash
CODEX_PLUGIN_ROOT=/Users/fanghao/.codex/plugins/cache/external-models-for-codex-local/claude-for-codex/0.5.0 \
node /Users/fanghao/.codex/plugins/cache/external-models-for-codex-local/claude-for-codex/0.5.0/scripts/claude-companion.mjs adversarial-review \
  --scope branch \
  --base origin/main \
  --path root_solving \
  --path app_desktop/workers_core.py \
  --path app_desktop/workspace_controller.py \
  --path app_desktop/panels.py \
  --path app_desktop/window.py \
  --path tests \
  --adversarial-lenses skeptic,architect,minimalist \
  --json \
  "Review the root-solving uncertainty follow-up for correctness, maintainability, and drift from the original DataLab root-solving goal."
```

Run Gemini:

```bash
CODEX_PLUGIN_ROOT=/Users/fanghao/.codex/plugins/cache/external-models-for-codex-local/gemini-for-codex/0.1.1 \
node /Users/fanghao/.codex/plugins/cache/external-models-for-codex-local/gemini-for-codex/0.1.1/scripts/gemini-companion.mjs adversarial-review \
  --scope branch \
  --base origin/main \
  --path root_solving \
  --path app_desktop/workers_core.py \
  --path app_desktop/workspace_controller.py \
  --path app_desktop/panels.py \
  --path app_desktop/window.py \
  --path tests \
  --adversarial-lenses skeptic,architect,minimalist \
  --json \
  "Review the root-solving uncertainty follow-up for correctness, maintainability, and drift from the original DataLab root-solving goal."
```

Expected: all three return PASS or low-only findings accepted as non-blocking. Any high/medium finding must be fixed and re-reviewed before PR.

- [ ] **Step 5: Commit review-plan evidence**

Run:

```bash
git add task_plan.md findings.md progress.md
git diff --cached --name-only
git commit -m "docs: record root uncertainty review evidence"
```

## Task 7: PR, Merge, Packaging, And Release Readiness

**Files:**
- Modify: version files used by the current release script if a release is requested after validation.
- Build outputs must not be committed.

- [ ] **Step 1: Push branch and open PR**

Run:

```bash
git push -u origin codex/root-uncertainty-methods
/opt/homebrew/bin/gh pr create --base main --head codex/root-uncertainty-methods --title "Add selectable root uncertainty propagation" --body-file /tmp/datalab-root-uncertainty-pr.md
```

Expected: PR URL created.

- [ ] **Step 2: Wait for checks and reviews**

Run:

```bash
/opt/homebrew/bin/gh pr view --json state,mergeable,reviewDecision,statusCheckRollup,url
```

Expected: checks pass and review blockers are closed.

- [ ] **Step 3: Merge PR**

Run:

```bash
/opt/homebrew/bin/gh pr merge --squash --delete-branch
git fetch origin
git switch main
git pull --ff-only origin main
```

Expected: `main` includes the follow-up.

- [ ] **Step 4: Clean release verification**

Run from a fresh clone or worktree:

```bash
rm -rf /private/tmp/datalab-root-uncertainty-release
git clone https://github.com/yilibinbin/DataLab.git /private/tmp/datalab-root-uncertainty-release
cd /private/tmp/datalab-root-uncertainty-release
PATH=/Users/fanghao/miniconda3/bin:$PATH QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q -x
python3 -m compileall -q data_extrapolation_gui.py app_desktop shared root_solving fitting tests
git diff --check
```

Expected: pass.

- [ ] **Step 5: Build macOS and Windows artifacts only after release decision**

Use the existing release scripts and the established remote Windows builder. The Windows build must happen on `apm8517` or the currently confirmed Windows builder, not on macOS.

Expected:

```text
macOS installer built and smoke-checked.
Windows installer built remotely and copied back.
Signed updates.json generated with generic public release notes.
Download-back hashes match uploaded assets.
```

- [ ] **Step 6: Publish release**

Publish the next version only after the user confirms release timing or explicitly asks to publish. Release notes must be generic:

```text
This release improves the root-solving module with explicit uncertainty propagation controls, Monte Carlo uncertainty propagation, scalar second-order propagation, workspace persistence for root uncertainty settings, and updated examples.
```

## Final Acceptance Criteria

- Clean implementation branch starts from `origin/main`, not the noisy local feature branch.
- No `" 2"` duplicate files are staged or committed.
- Root solving displays an explicit uncertainty propagation section.
- Root uncertainty options persist in `.datalab` workspaces.
- Root worker payloads contain only primitive, spawn-safe values.
- Linear propagation remains the automatic default and produces the same result as v2.7.0.
- Off mode suppresses uncertainty output without changing nominal roots.
- Monte Carlo mode is deterministic when a seed is supplied.
- Monte Carlo mode is limited to scalar/system roots in this follow-up and reports no uncertainty for polynomial/scan-multiple roots until a root-matching algorithm is separately planned.
- Monte Carlo sample count is capped at 50,000, and interactive row/root sample budget checks prevent predictable worker timeout traps.
- Scalar second-order mode is documented as scalar-local and warns/falls back for systems.
- All uncertainty input parsing still routes through shared modules.
- Codex, Claude, and Gemini reviews have no unresolved high/medium findings.
- Focused tests, static checks, full tracked pytest, and clean release verification pass.
- PR is merged only after review/check gates.
- Release is published only after package smoke checks and user release confirmation.

## Self-Review

- Spec coverage: The plan covers baseline recovery, UI clarity, selectable uncertainty methods, parser reuse, workspace persistence, examples, tests, reviews, PR, and release readiness.
- Placeholder scan: No `TBD`, `TODO`, or unspecified "add tests" steps are present.
- Type consistency: `RootUncertaintyOptions`, `RootUncertaintyMethod`, `uncertainty_options`, and method string values are used consistently across model, normalization, worker, workspace, and UI tasks.
- Original-goal alignment: The plan extends the existing root-solving module without changing the original precision routing, expression parser, constants parser, or workspace architecture.
