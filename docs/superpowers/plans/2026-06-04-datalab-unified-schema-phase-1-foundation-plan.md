# DataLab Unified Schema Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the schema foundation and non-destructive Qt binder required by later DataLab UI migrations.

**Architecture:** Extend the existing `shared/ui_specs.py` direction with focused schema primitives and create a desktop binder that applies metadata to existing widgets. Do not rewrite `build_left_panel`; bind a small set of existing controls to prove the interface.

**Tech Stack:** Python dataclasses, PySide6 widgets, pytest/pytest-qt, existing `WindowI18nMixin`.

---

## File Structure

- Create: `shared/ui_schema.py`
  - Owns `LocalizedText`, `ChoiceSpec`, `VisibilityRule`, `FormFieldSpec`, `FormSectionSpec`, `ResultViewSpec`, and `PlotSpec`.
- Create: `app_desktop/ui_schema_binder.py`
  - Applies schema metadata to existing Qt widgets and stores binding markers.
- Create: `tests/test_ui_schema.py`
  - Unit tests for localization, visibility rules, and plot budget defaults.
- Create: `tests/test_desktop_ui_schema_binder.py`
  - Offscreen Qt tests for binder behavior and dynamic scan boundaries.
- Modify: `shared/ui_specs.py`
  - Re-export new schema primitives for compatibility with the current shared UI module.

## Task 1: Schema Primitives

**Files:**
- Create: `shared/ui_schema.py`
- Test: `tests/test_ui_schema.py`

- [x] **Step 1: Write failing schema tests**

Add tests:

```python
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText, VisibilityRule


def test_localized_text_uses_chinese_by_default_and_english_when_requested():
    text = LocalizedText(zh="公式：", en="Formula:")
    assert text.for_lang("zh") == "公式："
    assert text.for_lang("en") == "Formula:"
    assert text.for_lang("auto") == "公式："


def test_visibility_rule_supports_equals_in_not_equals_and_and():
    rule = VisibilityRule.all(
        VisibilityRule.equals("method", "levin_u"),
        VisibilityRule.in_set("fit_model", {"custom", "self_consistent"}),
        VisibilityRule.not_equals("fit_model", "builtin"),
    )
    assert rule.evaluate({"method": "levin_u", "fit_model": "custom"}) is True
    assert rule.evaluate({"method": "richardson", "fit_model": "custom"}) is False


def test_form_field_spec_exposes_placeholder_tooltip_and_required_marker():
    spec = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        placeholder=LocalizedText("例如 A*x + B", "e.g. A*x + B"),
        tooltip=LocalizedText("输入 y=f(x,p) 形式", "Enter y=f(x,p) form"),
        required=True,
    )
    assert spec.label.for_lang("en") == "Model expression:"
    assert spec.placeholder.for_lang("zh") == "例如 A*x + B"
    assert spec.required is True


def test_choice_spec_keeps_backend_value_stable():
    choice = ChoiceSpec(value="scalar", label=LocalizedText("标量", "Scalar"))
    assert choice.value == "scalar"
    assert choice.label.for_lang("en") == "Scalar"
```

- [x] **Step 2: Run failing test**

Run:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py
```

Expected: fail with `ModuleNotFoundError: No module named 'shared.ui_schema'`.

- [x] **Step 3: Implement schema primitives**

Create `shared/ui_schema.py` with frozen dataclasses and pure-Python visibility evaluation. Keep it independent of PySide6.

- [x] **Step 4: Run schema tests**

Run the same pytest command.

Expected: `4 passed`.

- [x] **Step 5: Commit**

```bash
git add shared/ui_schema.py tests/test_ui_schema.py
git commit -m "feat: add shared ui schema primitives"
```

## Task 2: Qt Binder

**Files:**
- Create: `app_desktop/ui_schema_binder.py`
- Test: `tests/test_desktop_ui_schema_binder.py`

- [x] **Step 1: Write failing binder tests**

Add tests that instantiate `QLabel`, `QPlainTextEdit`, `QPushButton`, and `QComboBox`, bind a `FormFieldSpec`, then assert:

- label text follows language;
- placeholder follows language;
- tooltip follows language;
- help button tooltip follows language;
- combo item text follows `ChoiceSpec`;
- bound widgets have property `datalab_schema_key`;
- in-scope scan only flags widgets with property `datalab_schema_required=True`.

- [x] **Step 2: Run failing binder tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_ui_schema_binder.py
```

Expected: fail with `ModuleNotFoundError: No module named 'app_desktop.ui_schema_binder'`.

- [x] **Step 3: Implement binder**

Implement these public functions:

```python
def bind_field(*, field: FormFieldSpec, label=None, widget=None, help_button=None, lang: str = "zh") -> None: ...
def bind_choices(combo, choices: list[ChoiceSpec], *, lang: str = "zh") -> None: ...
def find_unbound_required_widgets(root) -> list[object]: ...
```

Use Qt dynamic properties:

- `datalab_schema_key`: schema key applied by binder.
- `datalab_schema_required`: opt-in marker for migrated-section scan.

- [x] **Step 4: Run binder tests**

Run the same pytest command.

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add app_desktop/ui_schema_binder.py tests/test_desktop_ui_schema_binder.py
git commit -m "feat: bind schema metadata to qt widgets"
```

## Task 3: Compatibility Re-Exports

**Files:**
- Modify: `shared/ui_specs.py`
- Test: `tests/test_ui_schema.py`

- [x] **Step 1: Add failing import test**

Add:

```python
def test_ui_specs_reexports_new_schema_types():
    from shared.ui_specs import FormFieldSpec, LocalizedText, VisibilityRule

    assert FormFieldSpec.__name__ == "FormFieldSpec"
    assert LocalizedText("中", "En").for_lang("en") == "En"
    assert VisibilityRule.equals("mode", "root").evaluate({"mode": "root"}) is True
```

- [x] **Step 2: Run test and verify failure**

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py::test_ui_specs_reexports_new_schema_types
```

Expected: import failure.

- [x] **Step 3: Re-export schema primitives**

Modify `shared/ui_specs.py` to import and expose the new types without changing existing names.

- [x] **Step 4: Run focused tests**

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py
ruff check shared/ui_schema.py shared/ui_specs.py app_desktop/ui_schema_binder.py tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py
```

Expected: pass.

- [x] **Step 5: Commit**

```bash
git add shared/ui_specs.py tests/test_ui_schema.py
git commit -m "refactor: expose unified schema primitives"
```

## Task 4: Smoke Bind Existing Root Fields

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Test: `tests/test_desktop_root_solving_ui.py`

- [x] **Step 1: Write failing root binder test**

Add a test that opens root mode and asserts `root_equations_edit`, `root_mode_combo`, `root_unknowns_table`, and `root_constants_editor` have schema key metadata or are explicitly excluded reusable editors.

- [x] **Step 2: Run failing test**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_root_solving_ui.py::test_root_controls_have_schema_bindings
```

Expected: fail because no schema keys are applied yet.

- [x] **Step 3: Bind root fields non-destructively**

Add a small root-specific binding call after root widgets are created. Do not change root behavior, just move text metadata into schema objects and binder calls.

- [x] **Step 4: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_desktop_root_solving_ui.py tests/test_desktop_ui_schema_binder.py tests/test_ui_schema.py
```

Expected: pass.

- [x] **Step 5: Commit**

```bash
git add app_desktop/panels.py app_desktop/window_i18n_mixin.py tests/test_desktop_root_solving_ui.py
git commit -m "refactor: bind root ui metadata through schema"
```

## Final Verification

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
ruff check shared/ui_schema.py shared/ui_specs.py app_desktop/ui_schema_binder.py app_desktop/panels.py app_desktop/window_i18n_mixin.py tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_root_solving_ui.py
/Users/fanghao/miniconda3/bin/python -m compileall -q shared app_desktop tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py
git diff --check
```

Expected: all pass.

## Self-Review Checklist

- Spec coverage: Phase 1 covers schema primitives, declarative visibility, dynamic scan property, non-destructive binder, and a first migrated root binding.
- Placeholder scan: no incomplete placeholder steps remain.
- Type consistency: all public names are defined before later tasks use them.
