# DataLab Unified Schema Phase 3 Result And Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring result tabs, result controls, and workspace result snapshots under schema metadata while preserving legacy workspace compatibility.

**Architecture:** Add result schema metadata and bind existing result widgets. Keep existing renderers and workspace attachments; schema documents and binds metadata rather than replacing output generation.

**Tech Stack:** PySide6, workspace controller, `shared.workspace_schema`, pytest.

---

## Tasks

### Task 1: Result Schema Metadata

**Files:**
- Modify: `shared/ui_schema.py`
- Create: `tests/test_result_view_schema.py`

- [x] Write tests for `ResultViewSpec` display/raw columns and localized tab/control labels.
- [x] Run `PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_result_view_schema.py` and verify failure.
- [x] Implement result metadata additions without touching renderers.
- [x] Run tests and commit:

```bash
git add shared/ui_schema.py tests/test_result_view_schema.py
git commit -m "feat: add result view schema metadata"
```

### Task 2: Bind Result Area Controls

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Test: `tests/test_desktop_result_schema_ui.py`

- [x] Add tests asserting numeric result, image result, log, LaTeX, PDF tabs, zoom/export controls, and CSV export controls have localized schema metadata.
- [x] Run the test and verify failure.
- [x] Bind existing widgets with result schema metadata.
- [x] Run focused result UI tests and commit:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_result_schema_ui.py
git add app_desktop/panels.py app_desktop/window_i18n_mixin.py tests/test_desktop_result_schema_ui.py
git commit -m "refactor: bind result area controls to schema"
```

### Task 3: Legacy Workspace Fixture

**Files:**
- Create: `tests/fixtures/workspaces/pre_schema_result_snapshot.datalab`
- Modify: `tests/test_workspace_controller.py`

- [x] Add or regenerate a small pre-schema workspace fixture containing table display, Markdown result, log, LaTeX source, PDF state if available, and one PNG attachment.
- [x] Add a test that opens the fixture, saves it to a temp path, reopens it, and asserts display/result fields are preserved.
- [x] Run fixture test and verify it fails if schema restore drops absent metadata.
- [x] Fix only the compatibility boundary needed in `app_desktop/workspace_controller.py`.
- [x] Run workspace tests and commit:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_workspace_controller.py
git add app_desktop/workspace_controller.py tests/test_workspace_controller.py tests/fixtures/workspaces/pre_schema_result_snapshot.datalab
git commit -m "test: preserve legacy result snapshots through schema"
```

## Final Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_result_view_schema.py tests/test_desktop_result_schema_ui.py tests/test_workspace_controller.py
ruff check shared app_desktop tests/test_result_view_schema.py tests/test_desktop_result_schema_ui.py tests/test_workspace_controller.py
/Users/fanghao/miniconda3/bin/python -m compileall -q shared app_desktop
git diff --check
```

## Self-Review Checklist

- Result schema does not replace renderers.
- Workspace restore remains tolerant of metadata missing from old files.
- Image attachments still use existing workspace attachment storage.
