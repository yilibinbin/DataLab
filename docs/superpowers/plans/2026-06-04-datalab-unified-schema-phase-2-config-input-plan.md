# DataLab Unified Schema Phase 2 Configuration Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate DataLab left-side configuration/input controls onto the Phase 1 schema binder while preserving behavior and workspace compatibility.

**Architecture:** Use Phase 1 `FormFieldSpec`, `ChoiceSpec`, and binder APIs to bind existing Qt widgets. Do not replace the left panel; migrate controls in batches and keep explicit workspace capture/restore as the compatibility boundary.

**Tech Stack:** PySide6, Phase 1 schema binder, pytest-qt, workspace controller tests.

---

## Dependencies

Complete `2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md` first.

## Batch A: Fitting Custom, Self-Consistent, And Root

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Test: `tests/test_desktop_implicit_model_ui.py`
- Test: `tests/test_desktop_root_solving_ui.py`
- Test: `tests/test_workspace_controller.py`

- [ ] **Step 1: Write failing placeholder tests**

Assert:

- fresh custom mode has empty `fit_expr_edit` and placeholder example;
- non-custom model preview remains populated and read-only;
- fresh self-consistent mode has empty `implicit_equation_edit` and `implicit_output_edit` with placeholders;
- workspace restore still writes saved custom/implicit expressions.

- [ ] **Step 2: Run failing tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_implicit_model_ui.py tests/test_workspace_controller.py::test_workspace_preserves_custom_fit_parameters_and_constants
```

Expected: fail on current real default expressions.

- [ ] **Step 3: Move fitting/root metadata into schema bindings**

Bind existing widgets. Keep preview writes in `window.py::_on_fit_model_changed()` and `_refresh_mode_expression()`.

- [ ] **Step 4: Run Batch A tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_implicit_model_ui.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app_desktop/panels.py app_desktop/window.py app_desktop/window_i18n_mixin.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
git commit -m "refactor: bind fitting and root inputs to schema"
```

## Batch B: Error Propagation And Constants

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/constants_editor.py`
- Create: `tests/test_desktop_error_propagation_ui.py`
- Test: `tests/test_workspace_controller.py`

- [ ] **Step 1: Add error/constants schema tests**

Assert formula, function help, constants file toggle, constants editor, Taylor/Monte Carlo controls, and seed fields have localized schema metadata and tooltips.

- [ ] **Step 2: Run failing tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_error_propagation_ui.py
```

Expected: fail until metadata is bound.

- [ ] **Step 3: Bind error propagation controls**

Reuse `ConstantsEditor` help button and text/table mode. Do not duplicate constants parsing.

- [ ] **Step 4: Run Batch B tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_error_propagation_ui.py tests/test_workspace_controller.py
```

- [ ] **Step 5: Commit**

```bash
git add app_desktop/panels.py app_desktop/constants_editor.py tests/test_desktop_error_propagation_ui.py tests/test_workspace_controller.py
git commit -m "refactor: bind error propagation inputs to schema"
```

## Batch C: Extrapolation And Statistics

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `shared/ui_specs.py`
- Test: `tests/test_desktop_extrapolation_ui.py`
- Test: `tests/test_desktop_statistics_ui.py`

- [ ] **Step 1: Add schema-binding tests for extrapolation/statistics**

Assert method combo labels, method help, custom formula, power/Richardson/Levin controls, uncertainty reference column, statistics mode, and statistics options have schema metadata and language switching.

- [ ] **Step 2: Run tests and verify failure**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_extrapolation_ui.py tests/test_desktop_statistics_ui.py
```

- [ ] **Step 3: Bind controls**

Reuse existing extrapolation `MethodSpec` content where possible. Extend rather than duplicate `EXTRAPOLATION_METHOD_SPECS`.

- [ ] **Step 4: Run Batch C tests**

Run the same pytest command plus `tests/test_ui_schema.py`.

- [ ] **Step 5: Commit**

```bash
git add app_desktop/panels.py shared/ui_specs.py tests/test_desktop_extrapolation_ui.py tests/test_desktop_statistics_ui.py
git commit -m "refactor: bind extrapolation and statistics inputs to schema"
```

## Batch D: Global Options

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_parallel_preferences.py`
- Test: `tests/test_desktop_global_options_ui.py`

- [ ] **Step 1: Add global option binding tests**

Assert precision, uncertainty digits, resource strategy, max workers, reserve cores, nested strategy, LaTeX path, input digits, grouping, dcolumn, generate LaTeX, generate plots, and PDF controls have schema metadata and localized help.

- [ ] **Step 2: Run failing tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_global_options_ui.py tests/test_parallel_preferences.py
```

- [ ] **Step 3: Bind global options**

Keep existing parallel behavior; only migrate metadata.

- [ ] **Step 4: Run Batch D tests**

Run the same pytest command.

- [ ] **Step 5: Commit**

```bash
git add app_desktop/panels.py tests/test_desktop_global_options_ui.py tests/test_parallel_preferences.py
git commit -m "refactor: bind global options to schema"
```

## Final Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_implicit_model_ui.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_extrapolation_ui.py tests/test_desktop_statistics_ui.py tests/test_desktop_global_options_ui.py tests/test_parallel_preferences.py
ruff check app_desktop shared tests/test_desktop_implicit_model_ui.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
/Users/fanghao/miniconda3/bin/python -m compileall -q app_desktop shared
git diff --check
```

## Self-Review Checklist

- Spec coverage: Phase 2 covers all left-side configuration/input batches.
- No code path removes workspace restore authority.
- Custom/implicit placeholders are empty only for fresh UI, not restored files.
