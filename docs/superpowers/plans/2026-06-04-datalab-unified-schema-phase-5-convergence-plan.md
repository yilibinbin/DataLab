# DataLab Unified Schema Phase 5 Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the unified schema program by removing duplicated migrated UI metadata plumbing, adding deterministic GUI/schema scans, synchronizing plan status, and preparing a clean release handoff without weakening existing GUI behavior.

**Architecture:** Phase 1-4 already introduced schema primitives, Qt binding, migrated controls/results, and root plot integration. Phase 5 must not redesign the GUI; it adds audit coverage, moves repeated schema refresh helpers into a small shared runtime module, removes only duplicate manual text/tooltip wiring that tests prove is schema-owned, and adds final source-mode GUI scans. Release work is a separate handoff after source validation passes.

**Tech Stack:** Python 3, PySide6, pytest/pytest-qt, existing `shared/ui_schema.py`, `app_desktop.ui_schema_binder`, `app_desktop.panels`, root-solving plotting, workspace controller, `ruff`, `compileall`.

---

## Current Evidence To Preserve

- Branch: `codex/fix-left-panel-scrollbar`, currently ahead of `origin/main`.
- Implemented unified schema commits:
  - Phase 1: `88f1e65`, `f69e981`, `3f24b7a`, `f47fe3e`.
  - Phase 2: `4ae66c1`, `1346389`, `bfe6718`, `6e2a2f7`.
  - Phase 3: `147e8b3`, `b60292e`, `7899c75`.
  - Phase 4: `84d7a86`, `3188de0`, `7a8435f`, `0adec93`.
- Dirty local state before Phase 5:
  - Modified: `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md`.
  - Untracked: `.superpowers/`.
- Guardrail: never use `git add .`; never stage `.superpowers/`.

## Files And Responsibilities

- Modify `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md`: synchronize completed checkbox state only; no code behavior.
- Modify `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-2-config-input-plan.md`: synchronize completed checkbox state only.
- Modify `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-3-result-workspace-plan.md`: synchronize completed checkbox state only.
- Modify `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md`: keep completed checkbox state; stage this plan doc only when committing plan-sync docs.
- Update local recovery files `task_plan.md`, `progress.md`, and `findings.md` when useful for session recovery, but do not stage or commit them in this phase because the repository ignores these AI session artifacts.
- Create `app_desktop/ui_schema_runtime.py`: runtime helpers that bridge `FormFieldSpec` to existing Qt widgets and language refresh, replacing duplicated helper logic currently embedded in `app_desktop/panels.py`.
- Modify `app_desktop/panels.py`: import runtime helpers and remove migrated duplicate text/tooltip/placeholder wiring only where tests prove schema-owned behavior.
- Do not modify `app_desktop/window_i18n_mixin.py` in this phase. It is a global language-refresh boundary and needs a separate plan if future evidence proves it must change.
- Create `tools/audit_ui_schema_bindings.py`: deterministic source/runtime audit for migrated schema sections.
- Create `tests/test_ui_schema_audit.py`: tests for audit detection and allowlist behavior.
- Create `tools/scan_desktop_gui_schema.py`: offscreen source-mode GUI scan that reports structured JSON.
- Create `tests/test_desktop_gui_schema_scan.py`: tests for language refresh, no unbound required controls, no left-panel horizontal clipping, preview/help wiring, root plot display, and workspace restore.

## Task 1: Synchronize Completed Phase Plan Status

**Files:**
- Modify: `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md`
- Modify: `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-2-config-input-plan.md`
- Modify: `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-3-result-workspace-plan.md`
- Modify: `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md`
- Local-only update: `progress.md` if the file exists; do not stage or commit it.

- [ ] **Step 1: Verify the completed implementation commits still exist**

Run:

```bash
git log --oneline --decorate -20
git show --quiet --format='%h %s' 88f1e65 f69e981 3f24b7a f47fe3e 4ae66c1 1346389 bfe6718 6e2a2f7 147e8b3 b60292e 7899c75 84d7a86 3188de0 7a8435f 0adec93
```

Expected:

```text
All listed commit hashes resolve locally.
```

- [ ] **Step 2: Mark Phase 1-4 checklist items complete**

Change only checklist markers in the four phase plan documents:

```diff
-- [ ] **Step 1: Write failing schema tests**
+- [x] **Step 1: Write failing schema tests**
```

Convert every checklist marker in Phase 1-4 plan files from `- [ ]` to `- [x]`. Current evidence shows all Phase 1-4 tasks are implemented and committed; do not require the executor to infer a commit-to-checkbox mapping. Do not rewrite task prose.

- [ ] **Step 3: Record the synchronization in progress**

Append to `progress.md`:

```markdown
## 2026-06-05 Unified Schema Phase 5 Task 1
- Synchronized Phase 1-4 plan checkboxes with committed implementation evidence.
- Verified commits: 88f1e65, f69e981, 3f24b7a, f47fe3e, 4ae66c1, 1346389, bfe6718, 6e2a2f7, 147e8b3, b60292e, 7899c75, 84d7a86, 3188de0, 7a8435f, 0adec93.
- No application code changed.
```

- [ ] **Step 4: Verify docs diff is scoped**

Run:

```bash
git diff -- docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-2-config-input-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-3-result-workspace-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md
git diff --check
```

Expected:

```text
Diff contains checklist/progress synchronization only.
git diff --check exits 0.
```

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-2-config-input-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-3-result-workspace-plan.md docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md
git diff --cached --name-only
git commit -m "docs: synchronize unified schema phase status"
```

Expected staged files are exactly the four phase plans. `progress.md` remains a local ignored recovery file.

## Task 2: Add Deterministic Schema Audit Tool

**Files:**
- Create: `tools/audit_ui_schema_bindings.py`
- Create: `tools/ui_schema_audit_allowlist.txt`
- Create: `tests/test_ui_schema_audit.py`
- Local-only update: `progress.md` if useful; do not stage or commit it.

- [ ] **Step 1: Write failing audit tests**

Create `tests/test_ui_schema_audit.py`:

```python
from __future__ import annotations

from tools.audit_ui_schema_bindings import AuditFinding, audit_source_text, format_findings


def test_audit_reports_manual_tooltip_after_schema_binding() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)
    self.root_equations_edit.setToolTip("manual")
'''

    findings = audit_source_text(source, filename="app_desktop/panels.py")

    assert findings == [
        AuditFinding(
            filename="app_desktop/panels.py",
            line=4,
            code="manual-tooltip-after-schema-bind",
            detail='self.root_equations_edit.setToolTip("manual")',
        )
    ]


def test_audit_allows_schema_refresh_helper() -> None:
    source = '''
def _bind_error_schema_fields(self):
    bind_field(field=formula_field, widget=self.formula_edit, lang=lang)
    register_schema_text_refresh(self, formula_field, widget=self.formula_edit)
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_ignores_manual_tooltips_outside_migrated_schema_blocks() -> None:
    source = '''
def _build_unrelated_panel(self):
    self.dynamic_button.setToolTip("runtime state")
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_resets_after_migrated_schema_block() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)

def _refresh_runtime_help(self):
    self.dynamic_button.setToolTip("runtime state")
'''

    assert audit_source_text(source, filename="app_desktop/panels.py") == []


def test_audit_respects_allowlist_entries() -> None:
    source = '''
def _bind_root_schema_fields(self):
    bind_field(field=root_field, widget=self.root_equations_edit, lang=lang)
    self.root_equations_edit.setToolTip("dynamic runtime tooltip")
'''

    findings = audit_source_text(
        source,
        filename="app_desktop/panels.py",
        allowlist={"app_desktop/panels.py:4:manual-tooltip-after-schema-bind"},
    )

    assert findings == []


def test_format_findings_is_stable() -> None:
    findings = [
        AuditFinding("b.py", 2, "c", "second"),
        AuditFinding("a.py", 1, "b", "first"),
    ]

    assert format_findings(findings) == (
        "a.py:1: b: first\\n"
        "b.py:2: c: second"
    )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema_audit.py
```

Expected:

```text
FAIL because tools.audit_ui_schema_bindings does not exist.
```

- [ ] **Step 3: Implement minimal audit tool**

Create `tools/audit_ui_schema_bindings.py`:

```python
from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


MIGRATED_BIND_MARKERS = (
    "bind_field(",
    "bind_choices(",
    "register_schema_text_refresh(",
    "_register_schema_text_refresh(",
    "bind_schema_command_button(",
    "_bind_schema_command_button(",
)
MANUAL_TEXT_MARKERS = (
    ".setToolTip(",
    ".setPlaceholderText(",
    "._register_text(",
    "self._register_text(",
)
ALLOWLIST_SNIPPETS = (
    "register_schema_text_refresh(",
    "_register_schema_text_refresh(",
    "bind_schema_command_button(",
    "_bind_schema_command_button(",
    "setAccessibleName",
    "setAccessibleDescription",
)


@dataclass(frozen=True, order=True)
class AuditFinding:
    filename: str
    line: int
    code: str
    detail: str


def _finding_key(finding: AuditFinding) -> str:
    return f"{finding.filename}:{finding.line}:{finding.code}"


def audit_source_text(
    source: str,
    *,
    filename: str,
    allowlist: set[str] | None = None,
) -> list[AuditFinding]:
    allowlist = allowlist or set()
    findings: list[AuditFinding] = []
    in_migrated_binding_block = False
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("def _bind_") and "schema" in stripped:
            in_migrated_binding_block = True
        elif stripped.startswith("def ") and not stripped.startswith("def _bind_"):
            in_migrated_binding_block = False

        if any(marker in stripped for marker in MIGRATED_BIND_MARKERS):
            in_migrated_binding_block = True

        if not in_migrated_binding_block:
            continue
        if any(snippet in stripped for snippet in ALLOWLIST_SNIPPETS):
            continue
        if any(marker in stripped for marker in MANUAL_TEXT_MARKERS):
            detail = stripped
            finding = AuditFinding(
                filename=filename,
                line=line_number,
                code="manual-tooltip-after-schema-bind",
                detail=detail,
            )
            if _finding_key(finding) not in allowlist:
                findings.append(finding)
    return sorted(findings)


def read_allowlist(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def audit_paths(paths: Iterable[Path], *, allowlist: set[str] | None = None) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for path in paths:
        findings.extend(
            audit_source_text(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                allowlist=allowlist,
            )
        )
    return sorted(findings)


def format_findings(findings: Iterable[AuditFinding]) -> str:
    return "\\n".join(
        f"{finding.filename}:{finding.line}: {finding.code}: {finding.detail}"
        for finding in sorted(findings)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrated-only", action="store_true")
    parser.add_argument("--allowlist", type=Path, default=Path("tools/ui_schema_audit_allowlist.txt"))
    parser.add_argument("paths", nargs="*", default=["app_desktop/panels.py"])
    args = parser.parse_args()

    findings = audit_paths(Path(path) for path in args.paths, allowlist=read_allowlist(args.allowlist))
    if findings:
        print(format_findings(findings))
        return 1
    print("No schema audit findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests and audit**

Run:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema_audit.py
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/audit_ui_schema_bindings.py --migrated-only
ruff check tools/audit_ui_schema_bindings.py tests/test_ui_schema_audit.py
git diff --check
```

Expected:

```text
tests/test_ui_schema_audit.py passes.
Audit may fail before Task 4 if real duplicate wiring exists; record every finding in findings.md before changing app code. If a finding is a dynamic runtime tooltip that must stay outside schema ownership, add the exact key `filename:line:code` to `tools/ui_schema_audit_allowlist.txt` and document the reason in findings.md.
ruff and git diff --check pass for touched files.
```

- [ ] **Step 5: Record audit findings**

If the audit reports findings, append the literal current finding list to `findings.md` before any app-code refactor. These line numbers are only a baseline inventory; Task 4 must re-run the audit after Task 3 because the `panels.py` helper extraction changes line numbers.

Append each accepted finding to `findings.md`:

```markdown
## 2026-06-05 Unified Schema Phase 5 Audit
| Finding | Evidence | Disposition |
|---|---|---|
| Manual tooltip after schema binding in app_desktop/panels.py:LINE | tools/audit_ui_schema_bindings.py --migrated-only | Accepted for Task 4 if covered by migrated UI tests. |
```

If the audit reports no findings, append:

```markdown
## 2026-06-05 Unified Schema Phase 5 Audit
No duplicate migrated schema text/tooltip wiring findings from tools/audit_ui_schema_bindings.py --migrated-only.
```

- [ ] **Step 6: Commit**

Run:

```bash
git add tools/audit_ui_schema_bindings.py tools/ui_schema_audit_allowlist.txt tests/test_ui_schema_audit.py
git diff --cached --name-only
git commit -m "test: audit migrated ui schema bindings"
```

Expected staged files are the audit tool, audit allowlist, and audit test only. `findings.md` and `progress.md` remain local ignored recovery files.

## Task 3: Move Schema Runtime Helpers Out Of panels.py

**Files:**
- Create: `app_desktop/ui_schema_runtime.py`
- Modify: `app_desktop/panels.py`
- Create: `tests/test_desktop_ui_schema_runtime.py`
- Local-only update: `progress.md` if useful; do not stage or commit it.

- [ ] **Step 1: Write failing runtime helper tests**

Create `tests/test_desktop_ui_schema_runtime.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from app_desktop.ui_schema_runtime import bind_schema_command_button, register_schema_text_refresh
from shared.ui_schema import FormFieldSpec, LocalizedText


class DummyWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, str, str, str]] = []

    def _register_text(self, widget: Any, zh: str, en: str, attr: str = "setText") -> None:
        self.calls.append((widget, zh, en, attr))


def _app() -> QApplication:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])


def test_register_schema_text_refresh_registers_tooltip_and_placeholder() -> None:
    _app()
    win = DummyWindow()
    edit = QLineEdit()
    field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        placeholder=LocalizedText("示例", "Example"),
        tooltip=LocalizedText("提示", "Hint"),
    )

    register_schema_text_refresh(win, field, widget=edit)

    assert (edit, "提示", "Hint", "setToolTip") in win.calls
    assert (edit, "示例", "Example", "setPlaceholderText") in win.calls


def test_bind_schema_command_button_sets_accessible_names_and_schema_key() -> None:
    _app()
    win = DummyWindow()
    button = QPushButton()
    field = FormFieldSpec(
        key="results.export.csv",
        widget_kind="button",
        label=LocalizedText("导出 CSV", "Export CSV"),
        tooltip=LocalizedText("导出当前结果", "Export current results"),
    )

    bind_schema_command_button(
        win,
        button,
        field=field,
        accessible_name=LocalizedText("导出 CSV", "Export CSV"),
        lang="en",
    )

    assert button.property("datalab_schema_key") == "results.export.csv"
    assert button.accessibleName() == "Export CSV"
    assert button.accessibleDescription() == "Export current results"
    assert (button, "导出 CSV", "Export CSV", "setAccessibleName") in win.calls
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_ui_schema_runtime.py
```

Expected:

```text
FAIL because app_desktop.ui_schema_runtime does not exist.
```

- [ ] **Step 3: Implement runtime helper module**

Create `app_desktop/ui_schema_runtime.py`:

```python
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from app_desktop.ui_schema_binder import bind_field
from shared.ui_schema import FormFieldSpec, LocalizedText


def register_schema_text_refresh(
    owner: Any,
    field: FormFieldSpec,
    *,
    widget: QWidget | None = None,
    help_button: QWidget | None = None,
) -> None:
    if widget is not None:
        if field.tooltip.zh or field.tooltip.en:
            owner._register_text(widget, field.tooltip.zh, field.tooltip.en, "setToolTip")
        if field.placeholder.zh or field.placeholder.en:
            owner._register_text(widget, field.placeholder.zh, field.placeholder.en, "setPlaceholderText")
    if help_button is not None and (field.tooltip.zh or field.tooltip.en):
        owner._register_text(help_button, field.tooltip.zh, field.tooltip.en, "setToolTip")


def bind_schema_command_button(
    owner: Any,
    button: QWidget,
    *,
    field: FormFieldSpec,
    accessible_name: LocalizedText,
    lang: str,
) -> None:
    bind_field(field=field, widget=button, lang=lang)
    register_schema_text_refresh(owner, field, widget=button)
    button.setAccessibleName(accessible_name.for_lang(lang))
    if field.tooltip.zh or field.tooltip.en:
        button.setAccessibleDescription(field.tooltip.for_lang(lang))
        owner._register_text(button, field.tooltip.zh, field.tooltip.en, "setAccessibleDescription")
    owner._register_text(button, accessible_name.zh, accessible_name.en, "setAccessibleName")
```

- [ ] **Step 4: Replace local helper definitions in panels.py**

In `app_desktop/panels.py`, add imports:

```python
from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    register_schema_text_refresh,
)
```

Then replace helper calls:

```diff
-    _register_schema_text_refresh(self, method_field, widget=self.method_combo)
+    register_schema_text_refresh(self, method_field, widget=self.method_combo)

-    _bind_schema_command_button(
+    bind_schema_command_button(
         self,
         self.output_browse_button,
```

Remove only the old local definitions:

```python
def _register_schema_text_refresh(...):
    ...

def _bind_schema_command_button(...):
    ...
```

Keep `_mark_schema_choices()` in `panels.py` unless a test proves it can also move safely.

- [ ] **Step 5: Verify every old helper reference was renamed**

Run:

```bash
rg -n "_register_schema_text_refresh|_bind_schema_command_button" app_desktop/panels.py
```

Expected:

```text
No matches in app_desktop/panels.py.
```

If matches remain, replace them with `register_schema_text_refresh` or `bind_schema_command_button` and rerun the command.

- [ ] **Step 6: Run focused verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_ui_schema_runtime.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_root_solving_ui.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_extrapolation_ui.py tests/test_desktop_statistics_ui.py tests/test_desktop_global_options_ui.py tests/test_desktop_result_schema_ui.py
ruff check app_desktop/ui_schema_runtime.py app_desktop/panels.py tests/test_desktop_ui_schema_runtime.py
/Users/fanghao/miniconda3/bin/python -m compileall -q app_desktop/ui_schema_runtime.py app_desktop/panels.py
git diff --check
```

Expected:

```text
Focused tests pass.
ruff passes for touched files.
compileall exits 0.
```

- [ ] **Step 7: Commit**

Run:

```bash
git add app_desktop/ui_schema_runtime.py app_desktop/panels.py tests/test_desktop_ui_schema_runtime.py
git diff --cached --name-only
git commit -m "refactor: share schema runtime text helpers"
```

Expected staged files are exactly the runtime helper, panels migration, and runtime tests.

## Task 4: Remove Covered Duplicate Metadata Wiring

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_desktop_error_propagation_ui.py`
- Modify: `tests/test_desktop_root_solving_ui.py`
- Modify: `tests/test_desktop_global_options_ui.py`
- Modify: `tests/test_desktop_result_schema_ui.py`
- Local-only update: `findings.md`/`progress.md` for audit rationale and progress; do not stage or commit them.

- [ ] **Step 1: Re-run the audit after Task 3 and record accepted duplicate lines**

Run:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/audit_ui_schema_bindings.py --migrated-only
```

Expected:

```text
Either "No schema audit findings." or a deterministic list of file:line findings.
```

Use only this post-Task-3 audit output for deletion and allowlist decisions. Do not use Task 2 baseline line numbers after `app_desktop/panels.py` has been edited.

For every finding, classify it in `findings.md`:

```markdown
| Manual tooltip after schema binding | app_desktop/panels.py:LINE | Accepted: covered by tests/test_desktop_root_solving_ui.py::test_root_solving_page_has_required_widgets |
```

Reject a finding if the line belongs to a dynamic tooltip whose text depends on runtime state rather than static schema metadata.
For each rejected finding, add an exact key to `tools/ui_schema_audit_allowlist.txt`:

```text
# Dynamic runtime tooltip; schema provides baseline text but mode-specific details are composed at runtime.
app_desktop/panels.py:LINE:manual-tooltip-after-schema-bind
```

- [ ] **Step 2: Add regression assertions before deleting wiring**

For root constants/help wiring, extend `tests/test_desktop_root_solving_ui.py`:

```python
def test_root_schema_tooltips_survive_language_switch(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window._apply_language("en")
    assert "Constants" in window.root_constants_editor.toolTip()
    assert "unknown" in window.root_unknowns_table.toolTip().lower()

    window._apply_language("zh")
    assert "常数" in window.root_constants_editor.toolTip()
    assert "未知量" in window.root_unknowns_table.toolTip()
```

For result buttons, extend `tests/test_desktop_result_schema_ui.py`:

```python
def test_result_command_buttons_keep_accessible_names_after_language_switch(window: Any) -> None:
    window._apply_language("en")
    assert window.export_csv_btn.accessibleName() == "Export CSV"
    assert window.result_export_btn.accessibleName() == "Export image"

    window._apply_language("zh")
    assert window.export_csv_btn.accessibleName() == "导出 CSV"
    assert window.result_export_btn.accessibleName() == "导出图片"
```

- [ ] **Step 3: Run regression tests before code deletion**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_root_solving_ui.py tests/test_desktop_result_schema_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_global_options_ui.py
```

Expected:

```text
Tests pass before deletion; this proves the assertions are observing current behavior.
```

- [ ] **Step 4: Remove only covered duplicate lines**

Delete manual text wiring only where the runtime helper or binder already owns the exact same widget and the tests from Step 2 cover language refresh. Example pattern:

```diff
-    self.root_mode_combo.setToolTip(getattr(self, "root_mode_help_button", self.root_mode_combo).toolTip())
```

Do not remove dynamic methods that compute table headers, mode-dependent visibility, or runtime validation messages.

- [ ] **Step 5: Re-run audit and focused tests**

Run:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/audit_ui_schema_bindings.py --migrated-only
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_ui_schema_runtime.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_root_solving_ui.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_extrapolation_ui.py tests/test_desktop_statistics_ui.py tests/test_desktop_global_options_ui.py tests/test_desktop_result_schema_ui.py
ruff check app_desktop/panels.py tests/test_desktop_root_solving_ui.py tests/test_desktop_result_schema_ui.py
git diff --check
```

Expected:

```text
Audit exits 0 after covered duplicates are removed and any justified dynamic runtime exceptions are documented in `tools/ui_schema_audit_allowlist.txt`.
Focused migrated UI tests pass.
```

- [ ] **Step 6: Commit**

Run:

```bash
git add app_desktop/panels.py tools/ui_schema_audit_allowlist.txt tests/test_desktop_root_solving_ui.py tests/test_desktop_result_schema_ui.py tests/test_desktop_error_propagation_ui.py tests/test_desktop_global_options_ui.py
git diff --cached --name-only
git commit -m "refactor: remove covered duplicate ui metadata wiring"
```

If any listed test file was not changed, omit it from `git add`.

## Task 5: Add Final GUI Schema Scan

**Files:**
- Create: `tools/scan_desktop_gui_schema.py`
- Create: `tests/test_desktop_gui_schema_scan.py`
- Local-only update: `progress.md` if useful; do not stage or commit it.

- [ ] **Step 1: Write failing scan tests**

Create `tests/test_desktop_gui_schema_scan.py`:

```python
from __future__ import annotations

import base64
import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tools.scan_desktop_gui_schema import scan_window


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.resize(1400, 900)
    win.show()
    QApplication.processEvents()
    return win


def test_gui_schema_scan_reports_no_issues(window: Any) -> None:
    report = scan_window(window)

    assert report["issues"] == []
    assert report["checks"]["languages"] == ["zh", "en"]
    assert report["checks"]["root_plot_display"] is True
    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True
    assert report["checks"]["workspace_result_restore"] is True


def test_gui_schema_scan_uses_real_workspace_restore(window: Any) -> None:
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    window.result_edit.setPlainText("before")
    window.result_plot_bytes = png_1x1

    report = scan_window(window)

    assert report["checks"]["workspace_result_restore"] is True


def test_gui_schema_scan_reports_missing_help_as_issue(window: Any) -> None:
    window.root_equations_help_button.setToolTip("")

    report = scan_window(window, refresh_language=False)

    assert any("root equations help tooltip missing" in issue for issue in report["issues"])
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_gui_schema_scan.py
```

Expected:

```text
FAIL because tools.scan_desktop_gui_schema does not exist.
```

- [ ] **Step 3: Implement scan tool**

Create `tools/scan_desktop_gui_schema.py`:

```python
from __future__ import annotations

import base64
import json
import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_desktop.ui_schema_binder import find_unbound_required_widgets
from app_desktop.workspace_controller import capture_workspace, restore_workspace


MODES = ("extrapolation", "error", "fitting", "root_solving", "statistics")
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _combo_index_for_data(combo: Any, data: object) -> int:
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"missing combo data {data!r}")
    return index


def _has_no_horizontal_scrollbar(window: Any) -> bool:
    for mode in MODES:
        window.mode_combo.setCurrentIndex(_combo_index_for_data(window.mode_combo, mode))
        QApplication.processEvents()
        window._refresh_main_splitter_left_min_width()
        window._main_splitter.setSizes([1, max(1, window.width() - 1)])
        QApplication.processEvents()
        bar = window._left_scroll.horizontalScrollBar()
        if bar.maximum() != 0 or bar.isVisible():
            return False
    return True


def _workspace_result_round_trip_ok(window: Any) -> bool:
    window.result_edit.setPlainText("| root | value |\n|---|---|\n| x | 1.414 |")
    window.log_edit.setPlainText("scan restore check")
    window.latex_edit.setPlainText("\\begin{table}\\end{table}")
    window._set_csv_data([{"root": "x", "value": "1.414"}], ["root", "value"], "root.csv")
    window.result_plot_bytes = PNG_1X1
    bundle = capture_workspace(window, title="gui schema scan")

    from app_desktop.window import ExtrapolationWindow

    restored = ExtrapolationWindow()
    try:
        restore_workspace(restored, bundle.manifest, bundle.attachments)
        QApplication.processEvents()
        return (
            "1.414" in restored.result_edit.toPlainText()
            and restored.log_edit.toPlainText() == "scan restore check"
            and restored.result_plot_bytes == PNG_1X1
            and window.result_plot_bytes == PNG_1X1
        )
    finally:
        restored.deleteLater()


def scan_window(window: Any, *, refresh_language: bool = True) -> dict[str, Any]:
    issues: list[str] = []
    languages = ("zh", "en") if refresh_language else ("current",)
    for lang in languages:
        if refresh_language:
            window._apply_language(lang)
            QApplication.processEvents()
        if not window.root_equations_help_button.toolTip():
            issues.append(f"{lang}: root equations help tooltip missing")
        if not window.root_formula_preview_button.toolTip():
            issues.append(f"{lang}: root formula preview tooltip missing")
        if find_unbound_required_widgets(window.root_box):
            issues.append(f"{lang}: root box has unbound required schema widgets")
        if find_unbound_required_widgets(window.options_box):
            issues.append(f"{lang}: options box has unbound required schema widgets")

    left_ok = _has_no_horizontal_scrollbar(window)
    if not left_ok:
        issues.append("left panel horizontal scrollbar is visible after splitter clamp")

    root_plot_display = bool(getattr(window, "result_plot_label", None) is not None)
    workspace_result_restore = _workspace_result_round_trip_ok(window)
    if not workspace_result_restore:
        issues.append("workspace result snapshot failed capture/restore round trip")

    return {
        "issues": issues,
        "checks": {
            "languages": ["zh", "en"],
            "left_panel_no_horizontal_scrollbar": left_ok,
            "root_plot_display": root_plot_display,
            "workspace_result_restore": workspace_result_restore,
        },
    }


def main() -> int:
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    window = ExtrapolationWindow()
    window.resize(1400, 900)
    window.show()
    QApplication.processEvents()
    report = scan_window(window)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run scan tests and tool**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_gui_schema_scan.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/scan_desktop_gui_schema.py
ruff check tools/scan_desktop_gui_schema.py tests/test_desktop_gui_schema_scan.py
/Users/fanghao/miniconda3/bin/python -m compileall -q tools/scan_desktop_gui_schema.py
git diff --check
```

Expected:

```text
pytest passes.
scan JSON has "issues": [].
ruff and compileall pass.
```

- [ ] **Step 5: Commit**

Run:

```bash
git add tools/scan_desktop_gui_schema.py tests/test_desktop_gui_schema_scan.py
git diff --cached --name-only
git commit -m "test: add unified schema gui scan"
```

Expected staged files are exactly the scan tool and scan test.

## Task 6: Final Source Verification And Release Handoff

**Files:**
- Local-only update: `task_plan.md`, `progress.md`, and `findings.md`; do not stage or commit them.

- [ ] **Step 1: Run the final Phase 5 source gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_ui_schema_audit.py tests/test_desktop_gui_schema_scan.py tests/test_workspace_controller.py tests/test_root_solving_plotting.py tests/test_root_solving_uncertainty.py tests/test_app_desktop_workers_core.py tests/test_desktop_root_solving_ui.py tests/test_desktop_result_schema_ui.py tests/test_desktop_global_options_ui.py
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/audit_ui_schema_bindings.py --migrated-only
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python tools/scan_desktop_gui_schema.py
ruff check shared/ui_schema.py app_desktop/ui_schema_binder.py app_desktop/ui_schema_runtime.py app_desktop/panels.py root_solving tools tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_ui_schema_audit.py tests/test_desktop_gui_schema_scan.py
/Users/fanghao/miniconda3/bin/python -m compileall -q shared app_desktop root_solving tools
git diff --check
```

Expected:

```text
Focused pytest passes.
Audit reports no accepted findings.
GUI scan JSON has "issues": [].
ruff, compileall, and git diff --check pass.
```

- [ ] **Step 2: Update planning files with final verdict**

In `task_plan.md`, add a new phase entry:

```markdown
49. [complete] Complete unified schema Phase 5 convergence: synchronized Phase 1-4 plan status, added deterministic schema audit, moved reusable schema runtime helpers out of panels.py, removed covered duplicate metadata wiring, added final GUI schema scan, and passed the final source verification gate.
```

In `progress.md`, append:

```markdown
## 2026-06-05 Unified Schema Phase 5 Final Gate
- Final focused pytest passed: COMMAND_OUTPUT_SUMMARY.
- Schema audit passed with no accepted findings.
- GUI scan passed with issues: [].
- ruff, compileall, and git diff --check passed.
- Remaining release work: push branch, PR/review gate, merge to main, clean worktree verification, macOS/Windows packaging, update manifest, GitHub Release.
```

In `findings.md`, append:

```markdown
## 2026-06-05 Unified Schema Phase 5 Final Findings
No unresolved Phase 5 source-code findings remain after focused source verification. Release packaging remains a separate workflow and is not claimed complete by this Phase 5 gate.
```

- [ ] **Step 3: Leave local planning files unstaged**

Run:

```bash
git status --short --ignored task_plan.md progress.md findings.md
git diff --cached --name-only
```

Expected: `task_plan.md`, `progress.md`, and `findings.md` are not staged. They may appear as ignored local recovery files.

- [ ] **Step 4: Report release handoff status without publishing**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected:

```text
Working tree has no source-code dirt except explicitly ignored local artifacts.
Branch still needs push/PR/merge/release unless the user explicitly asks to continue the release workflow.
```

## Final Verification Checklist

- [ ] Phase 1-4 plan status matches committed evidence.
- [ ] Phase 5 audit tool exists and is deterministic.
- [ ] Reusable schema runtime helpers are not duplicated in `app_desktop/panels.py`.
- [ ] No schema-owned migrated control has untested manual tooltip/placeholder/text wiring.
- [ ] Chinese and English language refresh are covered by GUI tests.
- [ ] Left-panel splitter clamp is covered by the final GUI scan.
- [ ] Root plot display and workspace result restore are covered by the final GUI scan.
- [ ] `task_plan.md` clearly distinguishes source implementation completion from PR/merge/package/release completion.
- [ ] `.superpowers/` remains unstaged.

## External Review Reconciliation

- Claude plan review finding accepted and fixed: the GUI scan must use the real workspace APIs, `capture_workspace()` and `restore_workspace()`, rather than a non-existent `_restore_workspace_snapshot` attribute.
- Claude plan review finding accepted and fixed: the audit RED test expected detail text must match the audit implementation output; the test now expects the raw source line.
- Claude/Gemini risk accepted and mitigated: the static audit is intentionally conservative and may report legitimate dynamic runtime tooltips. The plan now creates `tools/ui_schema_audit_allowlist.txt`; every allowlisted finding must have an exact `filename:line:code` key and a reason recorded in `findings.md`.
- Gemini plan review risk accepted and fixed: `app_desktop/window_i18n_mixin.py` is a global language-refresh boundary and is out of scope for this Phase 5 convergence pass.
- Claude re-review robustness gaps accepted and fixed: Task 1 now mechanically marks all Phase 1-4 checkboxes complete, Task 2 adds false-positive boundary tests, Task 3 greps for stale helper names and runs the expanded migrated UI suite, Task 4 explicitly re-runs audit after Task 3 line-number drift, and Task 5 tears down the fresh workspace-restore window.

## Self-Review

- Spec coverage: The plan covers the remaining Phase 5 index item plus the pending distinction between implementation and release workflow.
- Placeholder scan: No `TBD`, `TODO`, or vague "add tests" steps remain; every task includes exact files, test snippets, commands, and expected results.
- Type consistency: Runtime helper names are `register_schema_text_refresh` and `bind_schema_command_button`; tests, imports, and replacement snippets use the same names.
