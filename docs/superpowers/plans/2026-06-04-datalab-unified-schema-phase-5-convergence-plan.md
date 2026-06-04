# DataLab Unified Schema Phase 5 Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate UI metadata plumbing after prior phases have migrated the application onto the unified schema and binder.

**Architecture:** Replace ad hoc text registration, placeholder refresh, tooltip wiring, and result/workspace metadata duplication only in areas already covered by schema tests. Keep compatibility shims until tests prove no old path depends on them.

**Tech Stack:** PySide6, schema binder, pytest/pytest-qt, ruff, GUI scan scripts.

---

## Task 1: Duplicate Metadata Inventory

**Files:**
- Create: `tools/audit_ui_schema_bindings.py`
- Test: `tests/test_ui_schema_audit.py`

- [ ] Add tests for detecting duplicate `_register_text`/manual tooltip calls in migrated sections.
- [ ] Implement an audit tool that reports migrated-section widgets without schema keys and manual text wiring that should be schema-owned.
- [ ] Run and commit:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema_audit.py
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/audit_ui_schema_bindings.py --migrated-only
git add tools/audit_ui_schema_bindings.py tests/test_ui_schema_audit.py
git commit -m "test: audit migrated ui schema bindings"
```

## Task 2: Remove Redundant Text/Placeholder Wiring

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Test: migrated desktop UI tests from Phases 1-3

- [ ] Use the audit tool to list redundant wiring.
- [ ] Remove only wiring covered by schema tests.
- [ ] Run migrated UI tests and commit:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_ui_schema_binder.py tests/test_desktop_root_solving_ui.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_result_schema_ui.py
git add app_desktop/panels.py app_desktop/window_i18n_mixin.py
git commit -m "refactor: remove duplicated migrated ui metadata wiring"
```

## Task 3: Final GUI Scan

**Files:**
- Create or modify: `tools/scan_desktop_gui_schema.py`
- Test: `tests/test_desktop_gui_schema_scan.py`

- [ ] Add scan tests for Chinese/English language switching, no unbound required controls, no clipped left panel, working formula preview buttons, visible help buttons, root plot image display, and workspace result restore.
- [ ] Implement the scan using offscreen Qt and existing widget attributes.
- [ ] Run scan and commit:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_gui_schema_scan.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/scan_desktop_gui_schema.py
git add tools/scan_desktop_gui_schema.py tests/test_desktop_gui_schema_scan.py
git commit -m "test: add unified schema gui scan"
```

## Final Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_gui_schema_scan.py tests/test_workspace_controller.py tests/test_root_solving_plotting.py
ruff check shared app_desktop root_solving tools tests
/Users/fanghao/miniconda3/bin/python -m compileall -q shared app_desktop root_solving tools
git diff --check
```

## Self-Review Checklist

- No cleanup removes behavior that is not covered by schema tests.
- Audit reports are deterministic.
- Broad GUI scan covers the user-reported classes of regressions: missing help, stale labels, clipped controls, root plot missing, and workspace display loss.
