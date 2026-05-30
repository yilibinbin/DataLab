# DataLab Fit Backend UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove automatic fitting, unify custom and self-consistent fitting behind a maintainable compute boundary, add safe hidden SciPy acceleration, clean formula/parameter/constants UI, and ship verified example workspaces.

**Architecture:** Implement this as vertical slices. First remove the obsolete automatic-fit surface and lock workspace migration behavior. Then introduce explicit compute-boundary objects and route existing behavior through them before adding SciPy and implicit strategy selection. Finally unify the GUI editors and add examples/release verification.

**Tech Stack:** Python 3, PySide6, mpmath, SciPy when available, pytest, pytest-qt, ruff, compileall, existing DataLab workspace and LaTeX infrastructure.

---

## Source Spec

- `docs/superpowers/specs/2026-05-29-datalab-fit-backend-ui-overhaul-design.md`

## File Structure

- Modify `app_desktop/panels.py`: remove automatic-fit controls, update fitting panel labels, replace inline previews with preview buttons/dialogs, wire shared parameter/constants widgets.
- Modify `app_desktop/window.py`: remove automatic-fit worker lifecycle and workspace/menu entry points, add example workspace entry point, keep shutdown behavior for remaining workers.
- Modify `app_desktop/window_fitting_models_mixin.py`: collect custom/implicit configs into compute-boundary payloads, remove visible backend toggles, support orphan parameter filtering.
- Modify `app_desktop/window_fitting_mixin.py`: run fits through the unified runner and surface fallback/status diagnostics.
- Modify `app_desktop/workers_core.py`: remove auto-fit job execution, add `ModelProblem` payload support, preserve killable fit subprocess behavior.
- Modify `app_desktop/workers_qt.py`: remove `AutoFitWorker`, keep `FitWorker` cancellation.
- Modify `app_desktop/formula_preview.py`: add preview dialog API and keep renderer display-only.
- Modify `app_desktop/parameter_table.py`: add add/delete/detect/clear-empty APIs, orphan marking, and compute-row filtering.
- Modify `app_desktop/constants_editor.py`: hide inputs when disabled while preserving draft table/text state.
- Modify `app_desktop/workspace_controller.py`: migrate old automatic-fit state on open and strip it on save; persist parameter/constants draft state.
- Modify `shared/workspace_schema.py` and `shared/workspace_io.py`: accept schema migration metadata and generated example workspaces.
- Create `fitting/problem.py`: `ModelProblem`, `ParameterState` adapter helpers, and validation for compute-boundary payloads.
- Create `fitting/runner.py`: `BackendSelector`, `Solver`, `FitRunner`, safety checks, fallback diagnostics, and standard `FitResult.details`.
- Create `fitting/implicit_classifier.py`: classify observed implicit linear, observed implicit nonlinear, and general implicit cases.
- Modify `fitting/implicit_model.py`: keep low-level implicit evaluation/linear QR helpers and expose them through solver classes.
- Modify `fitting/hp_fitter.py`: preserve high-precision fitting and add small hooks needed by `FitRunner`.
- Modify `fitting/__init__.py`: export the new public fitting boundary.
- Modify `fitting/report.py`, `app_desktop/fitting_latex_writer.py`, and related LaTeX tests: remove automatic-fit report output and include solver diagnostics where useful.
- Create `examples/workspaces/`: generated canonical `.datalab` workspaces for extrapolation, error propagation, statistics, and fitting.
- Create or modify tests listed in each task below.

## Task 1: Remove Automatic Fitting and Add Workspace Degradation

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/workers_core.py`
- Modify: `app_desktop/workers_qt.py`
- Modify: `app_desktop/workspace_controller.py`
- Modify: `fitting/__init__.py`
- Modify: `fitting/report.py`
- Test: `tests/test_auto_fit_removed.py`
- Test: `tests/test_workspace_auto_fit_migration.py`
- Test: update `tests/test_app_desktop_workers_core.py`

- [ ] **Step 1: Write RED GUI/backend removal tests**

Create `tests/test_auto_fit_removed.py`:

```python
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_auto_fit_is_not_in_fitting_model_combo(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    values = [
        win.fit_model_combo.itemData(index)
        for index in range(win.fit_model_combo.count())
    ]
    labels = [
        win.fit_model_combo.itemText(index).lower()
        for index in range(win.fit_model_combo.count())
    ]

    assert "auto" not in values
    assert all("auto" not in label and "自动" not in label for label in labels)


def test_auto_fit_worker_is_not_exported():
    import app_desktop.workers_core as workers_core
    import app_desktop.workers_qt as workers_qt

    assert not hasattr(workers_core, "AutoFitJob")
    assert not hasattr(workers_core, "_execute_auto_fit_job_subprocess")
    assert not hasattr(workers_qt, "AutoFitWorker")


def test_fitting_package_no_longer_exports_auto_fit():
    import fitting

    assert not hasattr(fitting, "auto_fit_dataset")
```

- [ ] **Step 2: Write RED old-workspace migration tests**

Create `tests/test_workspace_auto_fit_migration.py`:

```python
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_opening_old_auto_fit_workspace_ignores_auto_state_once(qtbot):
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import restore_workspace

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    manifest = {
        "schema_version": "1.0",
        "config": {
            "fitting": {
                "model": "auto",
                "auto_fit": {"enabled": True, "candidate_models": ["poly2"]},
                "custom": {"expression": "a*x+b"},
            }
        },
        "data": {"input": {"canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]}}},
    }

    restore_workspace(win, manifest, {})

    assert win.fit_model_combo.currentData() != "auto"
    assert getattr(win, "_workspace_degraded", False) is True
    assert "automatic" in " ".join(getattr(win, "_workspace_migration_warnings", [])).lower()


def test_saving_after_old_auto_fit_migration_strips_obsolete_fields(qtbot):
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    manifest = {
        "schema_version": "1.0",
        "config": {
            "fitting": {
                "model": "auto",
                "auto_fit": {"enabled": True},
            }
        },
        "data": {"input": {"canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]}}},
    }

    restore_workspace(win, manifest, {})
    saved = capture_workspace(win, title="migrated").manifest
    fitting = saved["config"]["fitting"]

    assert fitting.get("model") != "auto"
    assert "auto_fit" not in fitting
```

- [ ] **Step 3: Run RED tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py
```

Expected: failures showing automatic-fit GUI/backend exports and missing migration warnings still exist.

- [ ] **Step 4: Remove automatic fitting from UI and workers**

Make these concrete edits:

```python
# app_desktop/panels.py
# In fit_model_combo setup, keep only explicit models:
fit_model_items = [
    ("多项式", "Polynomial", "polynomial"),
    ("反幂级数", "Inverse-power series", "inverse_power"),
    ("Pade", "Pade", "pade"),
    ("幂律极限", "Power-limit", "power_limit"),
    ("自定义模型", "Custom model", "custom"),
    ("自洽隐式模型", "Self-consistent / implicit", "self_consistent"),
]
```

Remove `AutoFitJob`, `_execute_auto_fit_job_subprocess`, `AutoFitWorker`, auto-fit menu actions, and `auto_fit_dataset` exports. Keep deleted functionality out of docs and reports in later tasks.

- [ ] **Step 5: Implement old-workspace degradation**

In `app_desktop/workspace_controller.py`, normalize fitting config during restore:

```python
def _migrate_removed_auto_fit(window: Any, fitting: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(fitting)
    removed = migrated.pop("auto_fit", None)
    if migrated.get("model") == "auto":
        migrated["model"] = "custom"
        removed = removed or {"model": "auto"}
    if removed is not None:
        warnings = list(getattr(window, "_workspace_migration_warnings", []))
        warnings.append("Automatic fitting was removed and its saved settings were ignored.")
        setattr(window, "_workspace_migration_warnings", warnings)
        setattr(window, "_workspace_degraded", True)
    return migrated
```

Call it before restoring fitting widgets and ensure `capture_workspace()` never emits `auto_fit`.

- [ ] **Step 6: Run Task 1 verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py tests/test_app_desktop_workers_core.py
python -m compileall -q app_desktop fitting shared
ruff check app_desktop/panels.py app_desktop/window.py app_desktop/workers_core.py app_desktop/workers_qt.py app_desktop/workspace_controller.py fitting
```

Expected: all pass.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add app_desktop/panels.py app_desktop/window.py app_desktop/workers_core.py app_desktop/workers_qt.py app_desktop/workspace_controller.py fitting/__init__.py fitting/report.py tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py tests/test_app_desktop_workers_core.py
git commit -m "refactor: remove automatic fitting workflow"
```

## Task 2: Introduce Unified Fitting Boundary Without Changing Results

**Files:**
- Create: `fitting/problem.py`
- Create: `fitting/runner.py`
- Create: `fitting/implicit_classifier.py`
- Modify: `fitting/__init__.py`
- Modify: `app_desktop/workers_core.py`
- Modify: `app_desktop/window_fitting_models_mixin.py`
- Test: `tests/test_fitting_problem_boundary.py`
- Test: `tests/test_fitting_runner_equivalence.py`

- [ ] **Step 1: Write RED boundary tests**

Create `tests/test_fitting_problem_boundary.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_model_problem_filters_disabled_constants_and_orphan_params():
    from fitting.problem import ModelProblem, ParameterDraft, constants_for_compute, parameters_for_compute

    problem = ModelProblem(
        model_type="custom",
        expression="a*x + c0",
        variables=("x",),
        target_name="y",
        constants={"c0": "2", "draft_only": "9"},
        constants_enabled=False,
    )
    drafts = [
        ParameterDraft(name="a", initial="1"),
        ParameterDraft(name="old", initial="5", orphaned=True),
    ]

    assert constants_for_compute(problem) == {}
    assert parameters_for_compute(drafts) == {"a": {"initial": "1"}}


def test_implicit_classifier_records_observed_linear_case():
    from fitting.implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d8/(n-delta)^8",
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d8"),
    )

    classification = ImplicitProblemClassifier().classify(definition)

    assert classification.strategy is ImplicitStrategy.OBSERVED_LINEAR
    assert "observed implicit variable" in classification.reason.lower()
```

- [ ] **Step 2: Write RED equivalence tests**

Create `tests/test_fitting_runner_equivalence.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_runner_matches_existing_custom_fit_for_linear_model():
    from fitting import build_model_specification, build_parameter_state, fit_custom_model
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        target_name="y",
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )
    x = [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]
    y = [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")]

    model = build_model_specification("a*x+b", ["x"], ["a", "b"])
    state = build_parameter_state(["a", "b"], {"a": {"initial": "1"}, "b": {"initial": "0"}})
    old = fit_custom_model(model, state, {"x": x}, y, precision=50)
    new = FitRunner().fit(problem, {"x": x}, y, precision=50)

    assert mp.almosteq(new.params["a"], old.params["a"])
    assert mp.almosteq(new.params["b"], old.params["b"])
    assert new.details["optimizer_backend"] == "mpmath_high_precision"
```

- [ ] **Step 3: Run RED tests**

Run:

```bash
pytest -q tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py
```

Expected: import failures for new modules.

- [ ] **Step 4: Implement `fitting/problem.py`**

Create immutable compute-boundary data classes:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ParameterDraft:
    name: str
    initial: str = ""
    fixed: str = ""
    min: str = ""
    max: str = ""
    expression: str = ""
    orphaned: bool = False


@dataclass(frozen=True)
class ModelProblem:
    model_type: str
    expression: str
    variables: tuple[str, ...]
    target_name: str = "y"
    parameter_config: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    constants: Mapping[str, str] = field(default_factory=dict)
    constants_enabled: bool = True
    implicit_definition: object | None = None


def constants_for_compute(problem: ModelProblem) -> dict[str, str]:
    if not problem.constants_enabled:
        return {}
    return {str(name): str(value) for name, value in problem.constants.items() if str(name).strip()}


def parameters_for_compute(rows: list[ParameterDraft]) -> dict[str, dict[str, str]]:
    config: dict[str, dict[str, str]] = {}
    for row in rows:
        name = row.name.strip()
        if not name or row.orphaned:
            continue
        values = {
            key: value
            for key, value in {
                "initial": row.initial.strip(),
                "fixed": row.fixed.strip(),
                "min": row.min.strip(),
                "max": row.max.strip(),
                "expression": row.expression.strip(),
            }.items()
            if value
        }
        if values:
            config[name] = values
    return config
```

- [ ] **Step 5: Implement classifier and runner shell**

Create `fitting/implicit_classifier.py` with explicit strategies and conservative linear detection. Create `fitting/runner.py` with `FitRunner.fit()` that delegates to existing mpmath custom and implicit paths and writes `FitResult.details["optimizer_backend"]`.

- [ ] **Step 6: Route worker payloads through `FitRunner`**

Update `app_desktop/workers_core.py` so existing custom and self-consistent fit jobs build `ModelProblem` and call `FitRunner().fit(...)`. Preserve existing subprocess/cancellation behavior.

- [ ] **Step 7: Run Task 2 verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py tests/test_desktop_implicit_model_ui.py tests/test_implicit_model.py tests/test_app_desktop_workers_core.py
python -m compileall -q fitting app_desktop/workers_core.py app_desktop/window_fitting_models_mixin.py
ruff check fitting/problem.py fitting/runner.py fitting/implicit_classifier.py fitting/__init__.py app_desktop/workers_core.py app_desktop/window_fitting_models_mixin.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py
```

Expected: all pass and existing numeric results unchanged.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add fitting/problem.py fitting/runner.py fitting/implicit_classifier.py fitting/__init__.py app_desktop/workers_core.py app_desktop/window_fitting_models_mixin.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py
git commit -m "refactor: add unified fitting runner boundary"
```

## Task 3: Add Hidden SciPy Acceleration and Implicit Strategy Solvers

**Files:**
- Modify: `fitting/runner.py`
- Modify: `fitting/implicit_classifier.py`
- Modify: `fitting/implicit_model.py`
- Modify: `fitting/hp_fitter.py`
- Modify: `app_desktop/window_fitting_mixin.py`
- Modify: `app_desktop/workers_core.py`
- Test: `tests/test_fitting_runner_scipy_fallback.py`
- Test: `tests/test_implicit_d8_runner_regression.py`

- [ ] **Step 1: Write RED SciPy acceptance/fallback tests**

Create `tests/test_fitting_runner_scipy_fallback.py`:

```python
from __future__ import annotations

import mpmath as mp


def test_precision_16_uses_scipy_when_safety_checks_pass():
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )
    result = FitRunner().fit(
        problem,
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]},
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        precision=16,
    )

    assert result.details["optimizer_backend"] == "scipy_least_squares"
    assert result.details["scipy_safety_passed"] is True


def test_precision_16_falls_back_when_scipy_safety_fails(monkeypatch):
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={"a": {"initial": "1"}, "b": {"initial": "0"}},
    )

    monkeypatch.setattr("fitting.runner._jacobian_condition_estimate", lambda *_args, **_kwargs: float("inf"))
    result = FitRunner().fit(
        problem,
        {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]},
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        precision=16,
    )

    assert result.details["optimizer_backend"] == "mpmath_high_precision"
    assert result.details["fallback_history"][0]["from"] == "scipy_least_squares"
```

- [ ] **Step 2: Write RED d8 regression test**

Create `tests/test_implicit_d8_runner_regression.py` with the supplied weighted data and constants:

```python
from __future__ import annotations

import time

import mpmath as mp


D8_ROWS = [
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


def test_observed_implicit_d8_weighted_fit_finishes_quickly():
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config={
            "d0": {"initial": "-0.01213"},
            "d2": {"initial": "0.0"},
            "d4": {"initial": "0.0"},
            "d6": {"initial": "0.0"},
            "d8": {"initial": "0.0"},
        },
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
            output_expression="delta",
            parameters=("d0", "d2", "d4", "d6", "d8"),
        ),
    )
    n = [mp.mpf(row[0]) for row in D8_ROWS]
    delta = [mp.mpf(row[1]) for row in D8_ROWS]
    weights = [1 / (mp.mpf(row[2]) ** 2) for row in D8_ROWS]

    start = time.perf_counter()
    result = FitRunner().fit(problem, {"n": n}, delta, precision=80, weights=weights)

    assert time.perf_counter() - start < 1.0
    assert result.details["implicit_strategy"] == "observed_linear"
    assert result.details["optimizer_backend"] in {"mpmath_qr", "scipy_least_squares"}
    assert set(result.params) == {"d0", "d2", "d4", "d6", "d8"}
```

- [ ] **Step 3: Run RED tests**

Run:

```bash
pytest -q tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py
```

Expected: SciPy backend and runner strategy assertions fail until implemented.

- [ ] **Step 4: Implement backend selector and safety checks**

In `fitting/runner.py`, add:

```python
def _can_try_scipy(problem: ModelProblem, precision: int) -> bool:
    return precision <= 16 and problem.model_type in {"custom", "self_consistent"}


def _accept_scipy_result(candidate: FitResult, start_norm: float, condition: float, spotcheck_ok: bool) -> tuple[bool, str]:
    if not candidate.details.get("scipy_success"):
        return False, "scipy did not report convergence"
    if not all(mp.isfinite(value) for value in candidate.fitted_curve + candidate.residuals):
        return False, "non-finite residuals or fitted values"
    if not mp.isfinite(candidate.chi2) or float(candidate.chi2) > start_norm:
        return False, "weighted residual norm is not improved"
    if not condition < float("inf") or condition > 1e12:
        return False, "jacobian condition estimate exceeds 1e12"
    if not spotcheck_ok:
        return False, "mpmath spot-check disagrees with SciPy model values"
    return True, "accepted"
```

Record rejected attempts in `FitResult.details["fallback_history"]`.

- [ ] **Step 5: Implement implicit strategy dispatch**

Dispatch:

- `OBSERVED_LINEAR`: call the existing weighted QR helper and mark `implicit_strategy=observed_linear`.
- `OBSERVED_NONLINEAR`: minimize `equation(x, u_observed, params) - u_observed` directly.
- `GENERAL`: call existing per-point implicit solver with cache/warm starts and fatal failure diagnostics.

Per-point failure messages must include point index, variable values, parameter values, solver method, residual, and iteration count.

- [ ] **Step 6: Surface backend diagnostics in GUI**

Update `app_desktop/window_fitting_mixin.py` result rendering to show a non-blocking status message when `fallback_history` is non-empty:

```python
if result.details.get("fallback_history"):
    self.statusBar().showMessage(self._tr("已回退到高精度求解器。", "Fell back to high-precision solver."), 8000)
```

- [ ] **Step 7: Run Task 3 verification**

Run:

```bash
pytest -q tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py tests/test_fitting_runner_equivalence.py tests/test_implicit_model.py tests/test_fitting_scipy_reference.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_app_desktop_workers_core.py tests/test_implicit_fit_worker_cancellation.py
python -m compileall -q fitting app_desktop/workers_core.py app_desktop/window_fitting_mixin.py
ruff check fitting app_desktop/workers_core.py app_desktop/window_fitting_mixin.py tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py
```

Expected: all pass; d8 regression completes under the local budget.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add fitting/runner.py fitting/implicit_classifier.py fitting/implicit_model.py fitting/hp_fitter.py app_desktop/window_fitting_mixin.py app_desktop/workers_core.py tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py
git commit -m "feat: add safe fitting backend selection"
```

## Task 4: Unify Formula Preview, Parameter Table, and Constants Editor UI

**Files:**
- Modify: `app_desktop/formula_preview.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/parameter_table.py`
- Modify: `app_desktop/constants_editor.py`
- Modify: `app_desktop/window_fitting_models_mixin.py`
- Modify: `app_desktop/workspace_controller.py`
- Test: `tests/test_formula_preview_dialog.py`
- Test: `tests/test_parameter_table_editor.py`
- Test: `tests/test_constants_editor_visibility.py`
- Test: update `tests/test_desktop_implicit_model_ui.py`

- [ ] **Step 1: Write RED formula dialog tests**

Create `tests/test_formula_preview_dialog.py`:

```python
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_formula_preview_dialog_has_high_contrast_surface(qtbot):
    from app_desktop.formula_preview import FormulaPreviewDialog

    dialog = FormulaPreviewDialog(expression="a*x+b", lhs="y")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle()
    assert "a*x+b" in dialog.expression_text.toPlainText()
    assert "#ffffff" in dialog.formula_surface.styleSheet().lower() or "background" in dialog.formula_surface.styleSheet().lower()


def test_implicit_panel_uses_preview_buttons_not_inline_labels(window):
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))

    assert hasattr(window, "implicit_equation_preview_button")
    assert hasattr(window, "implicit_output_preview_button")
    assert not hasattr(window, "implicit_equation_preview") or not window.implicit_equation_preview.isVisible()
```

- [ ] **Step 2: Write RED parameter/constants editor tests**

Create `tests/test_parameter_table_editor.py`:

```python
from __future__ import annotations


def test_parameter_table_add_delete_clear_and_orphan_filter(qtbot):
    from app_desktop.parameter_table import ParameterTable

    table = ParameterTable()
    qtbot.addWidget(table)

    table.add_parameter_row({"name": "a", "initial": "1"})
    table.add_parameter_row({"name": "old", "initial": "2"})
    table.mark_orphans({"a"})
    assert table.compute_rows() == [{"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""}]
    assert table.orphan_names() == {"old"}

    table.clear_empty_rows()
    table.delete_rows([1])
    assert table.orphan_names() == set()
```

Create `tests/test_constants_editor_visibility.py`:

```python
from __future__ import annotations


def test_constants_editor_hides_inputs_when_disabled_and_preserves_draft(qtbot):
    from app_desktop.constants_editor import ConstantsEditor

    editor = ConstantsEditor(checked=True)
    qtbot.addWidget(editor)
    editor.set_rows([{"name": "CR", "value": "3.2898419602500(36)[+9]"}])

    editor.setChecked(False)
    assert not editor.controls_widget.isVisible()
    assert not editor.stack.isVisible()
    assert editor.constants_dict(validate=False) == {"CR": "3.2898419602500(36)[+9]"}

    editor.setChecked(True)
    assert editor.controls_widget.isVisible()
    assert editor.stack.isVisible()
```

- [ ] **Step 3: Run RED tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py tests/test_desktop_implicit_model_ui.py
```

Expected: preview dialog/buttons and parameter table APIs fail until implemented.

- [ ] **Step 4: Add preview dialog API**

In `app_desktop/formula_preview.py`, add `FormulaPreviewDialog` and `open_formula_preview_dialog(parent, expression, lhs)`. The dialog must contain a rendered image/label surface, original expression text, copy button, and error label. Use a light/high-contrast surface independent of theme.

- [ ] **Step 5: Replace inline previews with buttons**

In `app_desktop/panels.py`, replace `FormulaPreviewLabel` widgets below formula editors with title rows:

```python
row = QHBoxLayout()
row.addWidget(QLabel("自洽方程："))
row.addStretch()
self.implicit_equation_preview_button = QPushButton("预览")
self.implicit_equation_preview_button.clicked.connect(
    lambda: open_formula_preview_dialog(self, self.implicit_equation_edit.toPlainText(), self.implicit_variable_edit.text())
)
row.addWidget(self.implicit_equation_preview_button)
implicit_layout.addLayout(row)
```

Apply the same pattern to custom formula, implicit output, extrapolation custom formula, and error propagation formula editors where inline preview currently exists.

- [ ] **Step 6: Implement parameter table row controls**

Add `add_parameter_row()`, `delete_rows()`, `clear_empty_rows()`, `mark_orphans()`, `orphan_names()`, and `compute_rows()` to `app_desktop/parameter_table.py`. `compute_rows()` must exclude orphaned rows and keep drafts in `rows()`.

- [ ] **Step 7: Fix constants editor disabled visibility**

Change `_on_checked_changed()` in `app_desktop/constants_editor.py` to call `set_inputs_visible(checked)` instead of only disabling controls:

```python
def _on_checked_changed(self, checked: bool) -> None:
    self.set_inputs_visible(bool(checked))
    self._emit_changed()
```

Ensure `constants_dict(validate=False)` still returns draft rows even while hidden.

- [ ] **Step 8: Persist editor draft state**

Update `app_desktop/workspace_controller.py` so custom and implicit parameter rows persist orphan state, constants enabled state, active view, rows, and raw text. Compute payload builders must use `compute_rows()` and must not include disabled constants.

- [ ] **Step 9: Run Task 4 verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py tests/test_formula_preview_rendering.py tests/test_desktop_implicit_model_ui.py tests/test_workspace_implicit_round_trip.py
python -m compileall -q app_desktop/formula_preview.py app_desktop/panels.py app_desktop/parameter_table.py app_desktop/constants_editor.py app_desktop/workspace_controller.py
ruff check app_desktop/formula_preview.py app_desktop/panels.py app_desktop/parameter_table.py app_desktop/constants_editor.py app_desktop/workspace_controller.py tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py
```

Expected: all pass and the left configuration pane remains splitter-resizable.

- [ ] **Step 10: Commit Task 4**

Run:

```bash
git add app_desktop/formula_preview.py app_desktop/panels.py app_desktop/parameter_table.py app_desktop/constants_editor.py app_desktop/window_fitting_models_mixin.py app_desktop/workspace_controller.py tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py tests/test_desktop_implicit_model_ui.py tests/test_workspace_implicit_round_trip.py
git commit -m "feat: unify formula and fitting editors"
```

## Task 5: Add Example Workspaces and Release-Level Verification

**Files:**
- Create: `examples/workspaces/extrapolation.datalab`
- Create: `examples/workspaces/error-propagation.datalab`
- Create: `examples/workspaces/statistics.datalab`
- Create: `examples/workspaces/fitting.datalab`
- Create: `tools/generate_example_workspaces.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: packaging scripts/spec files that already collect app assets
- Modify: `app_desktop/fitting_latex_writer.py`
- Test: `tests/test_example_workspaces.py`
- Test: `tests/test_desktop_example_workspace_menu.py`
- Test: update `tests/test_fitting_latex_writer.py`

- [ ] **Step 1: Write RED example workspace tests**

Create `tests/test_example_workspaces.py`:

```python
from __future__ import annotations

from pathlib import Path


EXAMPLE_NAMES = {
    "extrapolation.datalab",
    "error-propagation.datalab",
    "statistics.datalab",
    "fitting.datalab",
}


def test_canonical_example_workspaces_exist_and_open():
    from shared.workspace_io import read_workspace

    root = Path("examples/workspaces")
    found = {path.name for path in root.glob("*.datalab")}
    assert found == EXAMPLE_NAMES

    for name in EXAMPLE_NAMES:
        loaded = read_workspace(root / name)
        assert loaded.manifest["schema_version"]
        assert loaded.manifest["config"]
        assert loaded.manifest["data"]


def test_fitting_example_contains_required_variants():
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/fitting.datalab"))
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert {"custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"} <= set(variants)
```

Create `tests/test_desktop_example_workspace_menu.py`:

```python
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_example_workspace_menu_action_exists(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    actions = [action.text() for action in win.menuBar().actions()]
    menu_text = " ".join(actions).lower()
    assert "example" in menu_text or "示例" in menu_text
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py
```

Expected: missing examples/menu failures.

- [ ] **Step 3: Generate canonical example workspaces**

Create `tools/generate_example_workspaces.py` using existing `shared.workspace_io.write_workspace()` and checked-in small datasets. The script must write exactly four `.datalab` files under `examples/workspaces/` and include result snapshots.

Run:

```bash
python tools/generate_example_workspaces.py
```

Expected: four workspaces are created or refreshed.

- [ ] **Step 4: Add app menu entry**

Add "Open Example Workspace" / "打开示例工作区" to the File menu in `app_desktop/panels.py`. Implement `open_example_workspace()` in `app_desktop/window.py` so it copies the selected installed example into a user-writable temporary or chosen location before opening it.

- [ ] **Step 5: Remove automatic-fit LaTeX/report output**

Update `app_desktop/fitting_latex_writer.py`, `fitting/report.py`, and tests so generated fitting reports describe explicit model, parameters, uncertainty treatment, statistics, residuals, and solver details, but never automatic-fit rankings.

- [ ] **Step 6: Run release-level verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py tests/test_fitting_latex_writer.py tests/test_latex_compile_e2e.py tests/test_workspace_io.py tests/test_workspace_controller.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py
python -m compileall -q app_desktop fitting shared tools
ruff check app_desktop fitting shared tools tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py
```

Expected: all pass.

- [ ] **Step 7: Run broad verification if the environment supports it**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Expected: pass. If failures are unrelated pre-existing environment problems, record exact failures in `progress.md` and keep all targeted tests green.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add examples/workspaces tools/generate_example_workspaces.py app_desktop/panels.py app_desktop/window.py app_desktop/fitting_latex_writer.py fitting/report.py tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py tests/test_fitting_latex_writer.py
git commit -m "feat: add example workspaces and fitting verification"
```

## Final Review and Packaging Gate

- [ ] **Step 1: Check public diff for private paths and obsolete auto-fit references**

Run:

```bash
home_path_pattern='/''Users/'
temp_path_pattern='/''var/folders/'
local_host_pattern='local''host|127''\.0\.0\.1'
secret_pattern='OPENAI''_API_KEY|GITHUB''_TOKEN|ghp''_'
private_host_pattern='private ''host'
local_server_pattern='temporary local ''server'
private_host_marker_pattern='apm''8517|backup-''windows'
private_content_pattern="($home_path_pattern|$temp_path_pattern|$local_host_pattern|$private_host_pattern|$local_server_pattern|$private_host_marker_pattern|$secret_pattern)"
audit_paths=(app_desktop fitting shared docs examples tests tools)
audit_excludes=(':(exclude)docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md' ':(exclude)docs/superpowers/plans/2026-05-29-datalab-fit-backend-ui-overhaul-implementation-plan.md')
if git diff -- "${audit_paths[@]}" "${audit_excludes[@]}" | rg -n "$private_content_pattern"; then
  echo "Working-tree private-content audit failed." >&2
  exit 1
fi
if git diff --cached -- "${audit_paths[@]}" "${audit_excludes[@]}" | rg -n "$private_content_pattern"; then
  echo "Staged private-content audit failed." >&2
  exit 1
fi
if git diff origin/main...HEAD -- "${audit_paths[@]}" "${audit_excludes[@]}" | rg -n "$private_content_pattern"; then
  echo "Branch private-content audit failed." >&2
  exit 1
fi
git diff origin/main...HEAD -- "${audit_paths[@]}" \
  ':(exclude)docs/superpowers/plans/2026-05-29-datalab-implicit-performance-auto-plan.md' \
  | rg -n "auto.?fit|AutoFit|automatic fitting" || true
```

Expected: no private path/server hits in working-tree, staged, or branch diffs. Remaining automatic-fitting hits, if any, are only in migration tests or release notes that explicitly document removal.

- [ ] **Step 2: Run focused full gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_auto_fit_removed.py tests/test_workspace_auto_fit_migration.py tests/test_fitting_problem_boundary.py tests/test_fitting_runner_equivalence.py tests/test_fitting_runner_scipy_fallback.py tests/test_implicit_d8_runner_regression.py tests/test_formula_preview_dialog.py tests/test_parameter_table_editor.py tests/test_constants_editor_visibility.py tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py
python -m compileall -q app_desktop fitting shared tools
ruff check app_desktop fitting shared tools tests
```

Expected: all pass.

- [ ] **Step 3: Perform code review**

Use `superpowers:requesting-code-review` with this focus:

- automatic-fit deletion completeness;
- workspace migration behavior;
- hidden backend selection and SciPy safety predicates;
- implicit strategy classification and d8 fast path;
- GUI editor state versus compute payload filtering;
- example workspace packaging and LaTeX coverage.

- [ ] **Step 4: Address review findings and commit fixes**

For each accepted finding, add or update a regression test first, then patch. Commit with:

```bash
git add <review-fix-files>
git commit -m "fix: address fit overhaul review findings"
```

## Self-Review

- Spec coverage: covered automatic-fit removal, unified boundary, hidden SciPy selection, implicit strategies, formula preview dialogs, parameter/constants editor behavior, example workspaces, LaTeX/report cleanup, and verification.
- Placeholder scan: no unresolved placeholder tokens or unbounded catch-all steps are intentionally present.
- Type consistency: plan consistently uses `ModelProblem`, `ParameterDraft`, `ImplicitProblemClassifier`, `FitRunner`, `FitResult.details`, `optimizer_backend`, `implicit_strategy`, and `fallback_history`.
- Scope check: the work is large but split into five independently testable vertical commits. Each task has its own RED tests, implementation boundary, verification commands, and commit.
