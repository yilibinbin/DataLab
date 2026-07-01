# DataLab High-Fidelity Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the shared high-fidelity DataLab workbench layer so formula preview, variable tables, result overview, and mode layout are unified without duplicating computation or workspace state.

**Architecture:** Build a descriptive `ModeWorkbenchSpec` registry and a set of adapter panels that mount existing widgets (`ParameterTable`, `ConstantsEditor`, formula editors, data editors, result tabs) instead of replacing them. The first slice strengthens invariants and result state, then introduces shared panel wrappers for formulas and variables, and only then applies the shared structure across modes. All user-facing labels/help continue to come from the existing schema/help/i18n pipeline.

**Review policy updated 2026-06-09:** Do not run Claude for per-task or pre-implementation gates. Continue with main-thread Codex review and Gemini/Antigravity review while implementing task-by-task. Run exactly one Claude for Codex large review only after all implementation tasks and the full local quality gate are complete.

**Tech Stack:** Python 3.13, PySide6, pytest/pytest-qt, existing `app_desktop` workbench modules, `shared.ui_specs`, `app_desktop.ui_schema_binder`, `app_desktop.formula_preview`, `app_desktop.parameter_table`, `app_desktop.constants_editor`, `app_desktop.workspace_controller`.

---

## Current Codebase Facts

- `app_desktop/panels.py` already builds a three-zone workbench root, aliases `left_layout`, `left_container`, and `_left_scroll` to the config rail, moves the real `manual_box` and `mode_stack` into `workbench_workspace_layout`, and builds the result rail through `_build_right_panel(self.workbench_result_layout)`.
- `app_desktop/workbench_layout.py` owns the visible shell regions and `reparent_widget()`.
- `app_desktop/workbench_results.py` currently projects `_csv_rows` and `_csv_headers` into a compact table, but it still reports `暂无结果` / `No results` when a successful run has plot-only or text-only output.
- Formula preview already exists in `app_desktop/formula_preview.py` and is called through helpers in `app_desktop/panels.py`; the missing piece is a common workbench surface that uses those helpers consistently.
- `ParameterTable` and `ConstantsEditor` already own parameter/constant normalization, manual add/remove, text view, constraints, headers, and workspace round-trip behavior. The new workbench must mount these widgets, not replace their models.
- `app_desktop/workspace_controller.py` captures state by reading the existing widget attributes. Public widget attributes must remain stable.
- The current splitter minimum-width function in `app_desktop/panels.py` still has a legacy two-pane branch after the new three-pane workbench branch. That branch must be removed or guarded by a test so the layout contract is explicit.

## Non-Goals

- No numerical backend changes.
- No workspace manifest version change.
- No new expression parser or formula renderer.
- No replacement table models for parameters, constants, data, or results.
- No invented progress, invented telemetry, demo rows, or ornamental result state in the running application.
- No separate i18n/help registry.

## File Structure Plan

- Create `app_desktop/workbench_specs.py`: frozen descriptive registry for mode layout, existing widget attributes, existing schema keys, formula mount metadata, and result adapter keys.
- Create `tests/test_desktop_workbench_specs.py`: descriptor invariant tests and attribute/schema coverage tests.
- Create `tests/test_desktop_workbench_state_ownership.py`: structural duplicate-widget tests that detect mirrored editable state by role/schema/type.
- Modify `app_desktop/workbench_results.py`: introduce typed real-result summary state and clearer empty/no-tabular/failed labels.
- Modify `tests/test_desktop_workbench_results.py`: cover tabular, no result, plot-only, text-only, failed, and language refresh behavior.
- Create `app_desktop/workbench_formula_panel.py`: adapter surface for formula editors and preview buttons, reusing `FormulaPreviewLabel`, `update_formula_preview()`, and `open_formula_preview_dialog()`.
- Create `tests/test_desktop_workbench_formula_panel.py`: preview surface, popup, fallback, and language/tooltip behavior.
- Create `app_desktop/workbench_variable_panel.py`: adapter surface for existing `ParameterTable` and `ConstantsEditor` widgets.
- Create `tests/test_desktop_workbench_variable_panel.py`: mounting, row add/remove preservation, constants text view, constraints, and workspace round-trip smoke coverage.
- Modify `app_desktop/panels.py`: apply descriptor-driven mount metadata, remove or guard the two-pane splitter fallback, set structural role properties, and refresh shared panels after mode/language/result changes.
- Modify `app_desktop/window.py` and `app_desktop/window_i18n_mixin.py`: call refresh hooks only; do not move computation logic into panel classes.
- Modify `tools/scan_desktop_gui_schema.py` and `tests/test_desktop_gui_redesign_scan.py`: add structural duplicate-state checks to the scanner gate once role properties exist.
- Update `docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md` and desktop guide docs only after implementation passes focused tests.

---

## Task 1: Add Frozen Mode Workbench Descriptors

**Files:**
- Create: `app_desktop/workbench_specs.py`
- Modify: `app_desktop/panels.py`
- Create: `tests/test_desktop_workbench_specs.py`

- [x] **Step 1: Write the failing descriptor tests**

Create `tests/test_desktop_workbench_specs.py`:

```python
from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from app_desktop.workbench_specs import (
    MODE_WORKBENCH_SPECS,
    FormulaMount,
    ModeWorkbenchSpec,
    WidgetMount,
)


def test_mode_workbench_specs_are_frozen_descriptors_only() -> None:
    assert is_dataclass(ModeWorkbenchSpec)
    spec = MODE_WORKBENCH_SPECS["fitting"]
    with pytest.raises(FrozenInstanceError):
        spec.mode_key = "changed"  # type: ignore[misc]

    forbidden_types = (QWidget, list, dict, set)
    for mode, mode_spec in MODE_WORKBENCH_SPECS.items():
        for field in fields(mode_spec):
            value = getattr(mode_spec, field.name)
            assert not isinstance(value, forbidden_types), (mode, value)
        for formula in mode_spec.formulas:
            assert isinstance(formula, FormulaMount)
            assert not isinstance(formula.editor_attr, QWidget)
        for mount in mode_spec.parameters + mode_spec.constants + mode_spec.tables:
            assert isinstance(mount, WidgetMount)
            assert not isinstance(mount.widget_attr, QWidget)


def test_mode_workbench_specs_reference_existing_window_attributes(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    for mode, spec in MODE_WORKBENCH_SPECS.items():
        assert spec.mode_key == mode
        assert 0 <= spec.mode_stack_index < window.mode_stack.count()
        for attr in spec.required_widget_attrs():
            assert hasattr(window, attr), f"{mode}: {attr}"
    assert sorted(spec.mode_stack_index for spec in MODE_WORKBENCH_SPECS.values()) == list(range(window.mode_stack.count()))


def test_mode_workbench_specs_reuse_bound_schema_keys(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(window, formula.editor_attr)
            button = getattr(window, formula.preview_button_attr)
            assert editor.property("datalab_schema_key") == formula.schema_key
            assert button.property("datalab_schema_key") == formula.schema_key
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(window, mount.widget_attr)
            assert widget.property("datalab_schema_key") == mount.schema_key


def test_variable_mount_state_widgets_are_not_shared_between_mode_pages() -> None:
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    owners: dict[str, str] = {}
    state_roles: dict[str, str] = {}
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        for mount in spec.parameters + spec.constants + spec.tables:
            previous_mode = owners.setdefault(mount.widget_attr, mode)
            assert previous_mode == mode, (
                mount.widget_attr,
                previous_mode,
                mode,
            )
            previous_attr = state_roles.setdefault(mount.state_role, mount.widget_attr)
            assert previous_attr == mount.widget_attr, (
                mount.state_role,
                previous_attr,
                mount.widget_attr,
            )
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py
```

Expected before implementation:

```text
ModuleNotFoundError: No module named 'app_desktop.workbench_specs'
```

- [x] **Step 2: Add the descriptor module**

Create `app_desktop/workbench_specs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModeKey = Literal["extrapolation", "error", "fitting", "root_solving", "statistics"]
ResultAdapterKey = Literal["tabular", "text", "plot", "latex", "pdf", "none"]

@dataclass(frozen=True, slots=True)
class FormulaMount:
    editor_attr: str
    preview_button_attr: str
    schema_key: str
    lhs: str | None = None


@dataclass(frozen=True, slots=True)
class WidgetMount:
    widget_attr: str
    schema_key: str
    role: str
    state_role: str
    companion_attrs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModeWorkbenchSpec:
    mode_key: ModeKey
    mode_stack_index: int
    formulas: tuple[FormulaMount, ...] = ()
    parameters: tuple[WidgetMount, ...] = ()
    constants: tuple[WidgetMount, ...] = ()
    tables: tuple[WidgetMount, ...] = ()
    result_adapter_key: ResultAdapterKey = "tabular"

    def required_widget_attrs(self) -> tuple[str, ...]:
        attrs: list[str] = []
        for formula in self.formulas:
            attrs.extend((formula.editor_attr, formula.preview_button_attr))
        for mount in self.parameters + self.constants + self.tables:
            attrs.append(mount.widget_attr)
            attrs.extend(mount.companion_attrs)
        return tuple(dict.fromkeys(attrs))


```

`mode_stack_index` documents the existing `mode_stack` order only. Do not use it to insert or order new adapter pages; adapter stacks must keep a `mode -> page` dictionary and switch with `setCurrentWidget(page)`.

```python
MODE_WORKBENCH_SPECS: dict[ModeKey, ModeWorkbenchSpec] = {
    "extrapolation": ModeWorkbenchSpec(
        mode_key="extrapolation",
        mode_stack_index=0,
        formulas=(
            FormulaMount(
                "custom_formula_edit",
                "custom_formula_preview_button",
                "extrapolation.custom.formula",
            ),
        ),
        result_adapter_key="tabular",
    ),
    "error": ModeWorkbenchSpec(
        mode_key="error",
        mode_stack_index=1,
        formulas=(FormulaMount("formula_edit", "error_formula_preview_button", "error.formula"),),
        constants=(WidgetMount("error_constants_editor", "error.constants", "constants", "error_constants_owner"),),
        result_adapter_key="tabular",
    ),
    "fitting": ModeWorkbenchSpec(
        mode_key="fitting",
        mode_stack_index=2,
        formulas=(
            FormulaMount(
                "fit_expr_edit",
                "fit_formula_preview_button",
                "fitting.custom.expression",
                lhs="y",
            ),
            FormulaMount(
                "implicit_equation_edit",
                "implicit_equation_preview_button",
                "fitting.implicit.equation",
            ),
            FormulaMount(
                "implicit_output_edit",
                "implicit_output_preview_button",
                "fitting.implicit.output_expression",
                lhs="y",
            ),
        ),
        parameters=(
            WidgetMount(
                "custom_params_table",
                "fitting.custom.parameters",
                "parameters",
                "custom_parameters_owner",
                companion_attrs=("custom_param_header_widget", "custom_constraints_checkbox"),
            ),
            WidgetMount(
                "implicit_params_table",
                "fitting.implicit.parameters",
                "parameters",
                "implicit_parameters_owner",
                companion_attrs=("implicit_param_header_widget", "implicit_constraints_checkbox"),
            ),
        ),
        constants=(
            WidgetMount("custom_constants_editor", "fitting.custom.constants", "constants", "custom_constants_owner"),
            WidgetMount("implicit_constants_editor", "fitting.implicit.constants", "constants", "implicit_constants_owner"),
        ),
        result_adapter_key="tabular",
    ),
    "root_solving": ModeWorkbenchSpec(
        mode_key="root_solving",
        mode_stack_index=3,
        formulas=(FormulaMount("root_equations_edit", "root_formula_preview_button", "root.equations", lhs="F"),),
        tables=(
            WidgetMount(
                "root_unknowns_table",
                "root.unknowns",
                "unknowns",
                "root_unknowns_owner",
                companion_attrs=("root_unknown_header_widget",),
            ),
        ),
        constants=(WidgetMount("root_constants_editor", "root.constants", "constants", "root_constants_owner"),),
        result_adapter_key="tabular",
    ),
    "statistics": ModeWorkbenchSpec(
        mode_key="statistics",
        mode_stack_index=4,
        result_adapter_key="tabular",
    ),
}
```

- [x] **Step 3: Wrap existing table-control headers and bind schema keys from descriptors**

Modify `app_desktop/panels.py` so descriptor companion attributes exist.

If the custom parameter header is currently inserted as a raw layout, wrap it the same way as the implicit and root headers so the descriptor can assert a real public widget attribute:

```python
    custom_param_header_widget = QWidget()
    custom_param_header_widget.setLayout(custom_param_header)
    self.custom_param_header_widget = custom_param_header_widget
    custom_layout.addWidget(custom_param_header_widget)
```

If `custom_constraints_checkbox` or `implicit_constraints_checkbox` are currently local variables only, assign them to `self.custom_constraints_checkbox` and `self.implicit_constraints_checkbox` before adding them to the layout. Do not create duplicate checkboxes; expose the existing checkbox instances.

Replace the direct implicit parameter-header layout insertion:

```python
    implicit_layout.addLayout(implicit_param_header)
```

with:

```python
    implicit_param_header_widget = QWidget()
    implicit_param_header_widget.setLayout(implicit_param_header)
    self.implicit_param_header_widget = implicit_param_header_widget
    implicit_layout.addWidget(implicit_param_header_widget)
```

Replace the direct root unknown-header layout insertion:

```python
    root_layout.addLayout(root_unknown_header)
```

with:

```python
    root_unknown_header_widget = QWidget()
    root_unknown_header_widget.setLayout(root_unknown_header)
    self.root_unknown_header_widget = root_unknown_header_widget
    root_layout.addWidget(root_unknown_header_widget)
```

In `_bind_root_schema_fields()` after `bind_field(field=root_equations_field, ...)`, keep the root-specific binding:

```python
    self.root_formula_preview_button.setProperty("datalab_schema_key", root_equations_field.key)
    self.root_formula_preview_button.setProperty("datalab_schema_required", root_equations_field.required)
```

This binds the preview command to the same schema key without changing its preview-specific text or tooltip.

Then add one descriptor-derived schema-key pass after the existing mode widgets and schema bindings have been created:

```python
def _bind_workbench_spec_schema_keys(self) -> None:
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(self, formula.editor_attr, None)
            if editor is not None:
                editor.setProperty("datalab_schema_key", formula.schema_key)
            button = getattr(self, formula.preview_button_attr, None)
            if button is not None:
                button.setProperty("datalab_schema_key", formula.schema_key)
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(self, mount.widget_attr, None)
            if widget is not None:
                widget.setProperty("datalab_schema_key", mount.schema_key)
```

Call `self._bind_workbench_spec_schema_keys()` once near the end of `build_ui()` after the mode pages have been constructed and any existing `bind_field(...)` calls have run. This helper is an idempotent backstop for formula editors, preview buttons, and state-owner widgets; it keeps descriptor schema strings and runtime widget properties aligned without changing visible text, tooltips, table data, constraints state, or constants contents.

- [x] **Step 4: Run descriptor tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py
```

Expected:

```text
4 passed
```

- [x] **Step 5: Commit Task 1**

Run:

```bash
git add app_desktop/workbench_specs.py app_desktop/panels.py tests/test_desktop_workbench_specs.py
git commit -m "test: add high fidelity workbench descriptors"
```

---

## Task 2: Add Structural Single-State Ownership Gates

**Files:**
- Create: `tests/test_desktop_workbench_state_ownership.py`
- Modify: `app_desktop/panels.py`
- Modify: `tools/scan_desktop_gui_schema.py`
- Modify: `tests/test_desktop_gui_redesign_scan.py`

- [x] **Step 1: Write structural duplicate-state tests**

Create `tests/test_desktop_workbench_state_ownership.py`:

```python
from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPlainTextEdit, QStackedWidget, QTableWidget, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def _widgets_by_role(window: QWidget) -> dict[str, list[QWidget]]:
    roles: dict[str, list[QWidget]] = defaultdict(list)
    for widget in window.findChildren(QWidget):
        role = widget.property("datalab_state_role")
        if isinstance(role, str) and role:
            roles[role].append(widget)
    return roles


def test_workbench_has_one_owner_for_primary_editable_state(qtbot: Any) -> None:
    window = _window(qtbot)
    roles = _widgets_by_role(window)

    expected_singletons = {
        "manual_data_owner": window.manual_box,
        "mode_stack_owner": window.mode_stack,
        "result_tabs_owner": window.tabs,
        "custom_parameters_owner": window.custom_params_table,
        "implicit_parameters_owner": window.implicit_params_table,
        "root_unknowns_owner": window.root_unknowns_table,
        "error_constants_owner": window.error_constants_editor,
        "custom_constants_owner": window.custom_constants_editor,
        "implicit_constants_owner": window.implicit_constants_editor,
        "root_constants_owner": window.root_constants_editor,
    }
    for role, expected in expected_singletons.items():
        assert roles[role] == [expected], (role, [widget.objectName() for widget in roles[role]])


def test_no_mirrored_editable_data_or_result_widgets(qtbot: Any) -> None:
    window = _window(qtbot)

    mirrored_names = {
        "workbench_data_preview_table",
        "workbench_editor_stack",
        "workbench_result_model_table",
    }
    assert {widget.objectName() for widget in window.findChildren(QWidget)}.isdisjoint(mirrored_names)

    manual_tables = [
        widget
        for widget in window.findChildren(QTableWidget)
        if widget.property("datalab_state_role") == "manual_data_owner"
    ]
    assert manual_tables == []
    assert window.manual_box.property("datalab_state_role") == "manual_data_owner"
    assert window.manual_table.property("datalab_state_role") == "manual_table_editor"
    assert window.manual_data_edit.property("datalab_state_role") == "manual_text_editor"
    assert isinstance(window.manual_data_edit, QPlainTextEdit)
    assert isinstance(window.mode_stack, QStackedWidget)


def test_manual_data_has_only_existing_child_editors(qtbot: Any) -> None:
    window = _window(qtbot)

    manual_tables = [
        widget
        for widget in window.findChildren(QTableWidget)
        if widget.property("datalab_state_role") == "manual_table_editor"
    ]
    manual_text_edits = [
        widget
        for widget in window.findChildren(QPlainTextEdit)
        if widget.property("datalab_state_role") == "manual_text_editor"
    ]

    assert manual_tables == [window.manual_table]
    assert manual_text_edits == [window.manual_data_edit]
    assert window.manual_table.parentWidget() is window._data_stack
    assert window.manual_data_edit.parentWidget() is window._data_stack


def test_no_extra_manual_data_table_inside_data_owner(qtbot: Any) -> None:
    from PySide6.QtWidgets import QTableWidget

    window = _window(qtbot)

    manual_tables = [
        widget
        for widget in window.manual_box.findChildren(QTableWidget)
        if widget is not window.manual_table
    ]

    assert manual_tables == []


def test_no_unowned_parameter_or_constant_state_widgets(qtbot: Any) -> None:
    from app_desktop.constants_editor import ConstantsEditor
    from app_desktop.detected_rows_table import DetectedRowsTable
    from app_desktop.parameter_table import ParameterTable

    window = _window(qtbot)
    expected_by_attr = {
        "custom_params_table": "custom_parameters_owner",
        "implicit_params_table": "implicit_parameters_owner",
        "root_unknowns_table": "root_unknowns_owner",
        "error_constants_editor": "error_constants_owner",
        "custom_constants_editor": "custom_constants_owner",
        "implicit_constants_editor": "implicit_constants_owner",
        "root_constants_editor": "root_constants_owner",
    }
    owner_types = (ParameterTable, ConstantsEditor, DetectedRowsTable)
    expected_widgets = {getattr(window, attr) for attr in expected_by_attr}
    owner_widgets = []
    for owner_type in owner_types:
        owner_widgets.extend(window.findChildren(owner_type))
    for widget in owner_widgets:
        assert widget in expected_widgets, (
            "unexpected editable state owner",
            widget.__class__.__name__,
            widget.objectName(),
        )
    for attr, role in expected_by_attr.items():
        assert getattr(window, attr).property("datalab_state_role") == role
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_state_ownership.py
```

Expected before implementation:

```text
FAILED ... manual_data_owner
```

- [x] **Step 2: Mark existing owners with structural roles**

Modify `app_desktop/panels.py` inside `build_ui()` after `_build_left_panel()` and before the final `_on_mode_change()` call:

```python
    self.manual_box.setObjectName("manual_box")
    self.manual_table.setObjectName("manual_table")
    self.manual_data_edit.setObjectName("manual_data_edit")
    self.mode_stack.setObjectName("mode_stack")
    self.tabs.setObjectName("result_tabs")
    self.custom_params_table.setObjectName("custom_params_table")
    self.implicit_params_table.setObjectName("implicit_params_table")
    self.root_unknowns_table.setObjectName("root_unknowns_table")
    self.error_constants_editor.setObjectName("error_constants_editor")
    self.custom_constants_editor.setObjectName("custom_constants_editor")
    self.implicit_constants_editor.setObjectName("implicit_constants_editor")
    self.root_constants_editor.setObjectName("root_constants_editor")

    self.manual_box.setProperty("datalab_state_role", "manual_data_owner")
    self.manual_table.setProperty("datalab_state_role", "manual_table_editor")
    self.manual_data_edit.setProperty("datalab_state_role", "manual_text_editor")
    self.mode_stack.setProperty("datalab_state_role", "mode_stack_owner")
    self.tabs.setProperty("datalab_state_role", "result_tabs_owner")
    self.workbench_result_table.setProperty("datalab_state_role", "result_csv_projection")
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.parameters + spec.constants + spec.tables:
            getattr(self, mount.widget_attr).setProperty("datalab_state_role", mount.state_role)
```

Add `MODE_WORKBENCH_SPECS` to the existing `app_desktop.panels.py` imports where this role assignment lives.
Do not assign `manual_data_owner` to `manual_table` or `manual_data_edit`; they are child editors inside the real `manual_box` owner. Their child-editor roles exist only to prevent duplicate manual data editor clones.
Likewise, do not create replacement `ParameterTable`, `DetectedRowsTable`, or `ConstantsEditor` instances for the new common panels. The roles above must stay on the existing owner widgets.

- [x] **Step 3: Add scanner duplicate-role support**

Modify `tools/scan_desktop_gui_schema.py` by adding this helper near the existing issue helpers:

```python
REQUIRED_BASELINE_STATE_ROLES = {
    # These owners are outside MODE_WORKBENCH_SPECS but are always present in the shell.
    "manual_data_owner": "manual_box",
    "mode_stack_owner": "mode_stack",
    "result_tabs_owner": "result_tabs",
}


def _state_ownership_issues(window, scenario: ScreenScenario) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_owner_roles = dict(REQUIRED_BASELINE_STATE_ROLES)
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.parameters + spec.constants + spec.tables:
            existing_attr = expected_owner_roles.get(mount.state_role)
            if existing_attr is not None and existing_attr != mount.widget_attr:
                issues.append(
                    _issue(
                        "duplicate_state_role_definition",
                        scenario,
                        mount.state_role,
                        "state role is mapped to multiple editable state widgets",
                        first_widget=existing_attr,
                        second_widget=mount.widget_attr,
                    )
                )
                # First mapping wins so all later claimants are reported against the canonical owner.
                continue
            expected_owner_roles[mount.state_role] = mount.widget_attr
    for role, expected_object_name in expected_owner_roles.items():
        widgets = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("datalab_state_role") == role
        ]
        if not widgets:
            issues.append(
                _issue(
                    "missing_state_role_owner",
                    scenario,
                    role,
                    f"expected state owner {expected_object_name} for role {role}, found none",
                    count=0,
                    widgets=[],
                )
            )
        elif len(widgets) > 1 or widgets[0].objectName() != expected_object_name:
            if len(widgets) > 1:
                issues.append(
                    _issue(
                        "duplicate_state_role",
                        scenario,
                        role,
                        f"expected exactly one state owner {expected_object_name} for role {role}, found {len(widgets)}",
                        count=len(widgets),
                        widgets=[widget.objectName() for widget in widgets],
                    )
                )
            else:
                issues.append(
                    _issue(
                        "wrong_state_role_owner",
                        scenario,
                        role,
                        f"expected state owner {expected_object_name} for role {role}, found {widgets[0].objectName()}",
                        expected=expected_object_name,
                        found=widgets[0].objectName(),
                    )
                )
    owner_types = (ParameterTable, ConstantsEditor, DetectedRowsTable)
    expected_objects = {
        mount.widget_attr
        for spec in MODE_WORKBENCH_SPECS.values()
        for mount in spec.parameters + spec.constants + spec.tables
    } | set(REQUIRED_BASELINE_STATE_ROLES.values())
    owner_widgets = []
    for owner_type in owner_types:
        owner_widgets.extend(window.findChildren(owner_type))
    # The scanner is a runtime GUI-tree gate: detached widgets are not visible state owners.
    for widget in owner_widgets:
        widget_role = widget.property("datalab_state_role")
        if widget_role in expected_owner_roles:
            continue
        widget_name = widget.objectName()
        if widget_name in expected_objects and getattr(window, widget_name, None) is widget:
            continue
        issues.append(
            _issue(
                "unexpected_editable_state_owner",
                scenario,
                widget_name or widget.__class__.__name__,
                "unexpected editable state owner widget; common panels must mount existing owners",
                widget_class=widget.__class__.__name__,
                state_role=str(widget_role or ""),
            )
        )
    manual_editor_specs = (
        (QTableWidget, "manual_table_editor", "manual_table"),
        (QPlainTextEdit, "manual_text_editor", "manual_data_edit"),
    )
    for widget_type, role, expected_object_name in manual_editor_specs:
        widgets = [
            widget
            for widget in window.findChildren(widget_type)
            if widget.property("datalab_state_role") == role
        ]
        if not widgets:
            issues.append(
                _issue(
                    "missing_manual_data_editor",
                    scenario,
                    role,
                    f"expected manual data editor {expected_object_name} for role {role}, found none",
                    count=0,
                    widgets=[],
                )
            )
        elif len(widgets) > 1:
            issues.append(
                _issue(
                    "duplicate_manual_data_editor",
                    scenario,
                    role,
                    f"expected exactly one manual data editor {expected_object_name} for role {role}",
                    count=len(widgets),
                    widgets=[widget.objectName() for widget in widgets],
                )
            )
        elif widgets[0].objectName() != expected_object_name:
            issues.append(
                _issue(
                    "wrong_manual_data_editor",
                    scenario,
                    role,
                    f"expected manual data editor {expected_object_name} for role {role}, found {widgets[0].objectName()}",
                    expected=expected_object_name,
                    found=widgets[0].objectName(),
                )
            )
    manual_box = getattr(window, "manual_box", None)
    manual_table = getattr(window, "manual_table", None)
    manual_data_edit = getattr(window, "manual_data_edit", None)
    if manual_box is not None:
        for widget in manual_box.findChildren(QTableWidget):
            if widget is not manual_table:
                issues.append(
                    _issue(
                        "unexpected_manual_data_table",
                        scenario,
                        widget.objectName() or widget.__class__.__name__,
                        "unexpected manual data table inside the manual data owner",
                    )
                )
        for widget in manual_box.findChildren(QPlainTextEdit):
            if widget is not manual_data_edit:
                issues.append(
                    _issue(
                        "unexpected_manual_data_text_editor",
                        scenario,
                        widget.objectName() or widget.__class__.__name__,
                        "unexpected manual data text editor inside the manual data owner",
                    )
                )
    return issues
```

Then include it where the scan report aggregates visual/schema issues:

```python
if not scenarios:
    raise ValueError("duplicate-state scan requires at least one representative scenario")
structured_issues.extend(_state_ownership_issues(window, scenarios[0]))
```

Ensure the module imports `Any` from `typing`, `QPlainTextEdit`, `QTableWidget`, and `QWidget` from `PySide6.QtWidgets`, `MODE_WORKBENCH_SPECS` from `app_desktop.workbench_specs`, and `ConstantsEditor`, `DetectedRowsTable`, and `ParameterTable` from their existing `app_desktop` modules.
Place the `scenarios` guard immediately after `scenarios = _screen_scenarios(...)` in `scan_window()` and before any scenario-consuming helper runs. These structural duplicate-state checks are scenario-independent; emit them once against a representative `ScreenScenario` so a single duplicate does not create repeated report rows across the full scenario matrix. The `REQUIRED_BASELINE_STATE_ROLES` constant is intentionally separate from spec-derived roles because manual data, mode stack, and result tabs are required shell-level owners rather than mode-local mounts. Keep `duplicate_manual_data_editor` as its own issue kind so cloned manual table/text editors remain easy to identify. Expected editable owner detection must trust `datalab_state_role` first and object names second, so a correctly tagged owner with a missing object name reports `wrong_state_role_owner` without also creating a noisy `unexpected_editable_state_owner`. If a clone uses a reserved object name without being the actual `getattr(window, objectName)` owner, it must still be reported as `unexpected_editable_state_owner`; object-name equality alone is not a valid pass.

- [x] **Step 4: Cover scanner duplicate-state output**

Modify `tests/test_desktop_gui_redesign_scan.py` by adding:

```python
def test_gui_scan_reports_duplicate_state_roles(qtbot) -> None:
    from PySide6.QtWidgets import QLabel
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    clone = QLabel("duplicate", window)
    clone.setObjectName("duplicated_manual_owner")
    clone.setProperty("datalab_state_role", "manual_data_owner")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)
    issue = next(issue for issue in issues if issue["kind"] == "duplicate_state_role")
    assert issue["message"]
    # Role-ownership issues use the role identifier in the shared "widget" field.
    assert issue["widget"] == "manual_data_owner"
    assert issue["details"]["count"] == 2
    assert "duplicated_manual_owner" in issue["details"]["widgets"]


def test_gui_scan_reports_missing_state_role_owner(qtbot) -> None:
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_box.setProperty("datalab_state_role", "")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "missing_state_role_owner" for issue in issues)


def test_gui_scan_reports_wrong_state_role_owner(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_box.setProperty("datalab_state_role", "")
    wrong = QLabel("wrong", window)
    wrong.setObjectName("wrong_manual_owner")
    wrong.setProperty("datalab_state_role", "manual_data_owner")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "wrong_state_role_owner" for issue in issues)


def test_gui_scan_reports_missing_manual_data_editor(qtbot) -> None:
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_table.setProperty("datalab_state_role", "")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "missing_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_duplicate_manual_data_editor(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    duplicate = QTableWidget(window)
    duplicate.setObjectName("duplicate_manual_table_editor")
    duplicate.setProperty("datalab_state_role", "manual_table_editor")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "duplicate_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_wrong_manual_data_editor(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.manual_table.setProperty("datalab_state_role", "")
    wrong = QTableWidget(window)
    wrong.setObjectName("wrong_manual_table_editor")
    wrong.setProperty("datalab_state_role", "manual_table_editor")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "wrong_manual_data_editor" and issue["widget"] == "manual_table_editor"
        for issue in issues
    )


def test_gui_scan_reports_untagged_manual_data_table_clone(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    clone = QTableWidget(window.manual_box)
    clone.setObjectName("untagged_manual_table_clone")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "unexpected_manual_data_table" for issue in issues)


def test_gui_scan_reports_duplicate_state_role_definitions(qtbot, monkeypatch) -> None:
    from dataclasses import replace

    from tools import scan_desktop_gui_schema as scan
    from tools.scan_desktop_gui_schema import ScreenScenario

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    specs = dict(MODE_WORKBENCH_SPECS)
    fitting = specs["fitting"]
    root = specs["root_solving"]
    conflicting_mount = replace(root.tables[0], state_role=fitting.parameters[0].state_role)
    specs["root_solving"] = replace(root, tables=(conflicting_mount,))
    monkeypatch.setattr(scan, "MODE_WORKBENCH_SPECS", specs)

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    scenario = ScreenScenario(key="test", language="en", mode="fitting")

    issues = scan._state_ownership_issues(window, scenario)

    assert any(issue["kind"] == "duplicate_state_role_definition" for issue in issues)


def test_gui_scan_reports_spec_collision_with_baseline_state_role(qtbot, monkeypatch) -> None:
    from dataclasses import replace

    from tools import scan_desktop_gui_schema as scan
    from tools.scan_desktop_gui_schema import ScreenScenario

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    specs = dict(MODE_WORKBENCH_SPECS)
    root = specs["root_solving"]
    conflicting_mount = replace(root.tables[0], state_role="manual_data_owner")
    specs["root_solving"] = replace(root, tables=(conflicting_mount,))
    monkeypatch.setattr(scan, "MODE_WORKBENCH_SPECS", specs)

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    scenario = ScreenScenario(key="test", language="en", mode="root_solving")

    issues = scan._state_ownership_issues(window, scenario)
    issue = next(issue for issue in issues if issue["kind"] == "duplicate_state_role_definition")

    assert issue["details"]["first_widget"] == "manual_box"
    assert issue["details"]["second_widget"] == root.tables[0].widget_attr


def test_gui_scan_reports_wrong_owner_without_unexpected_owner_when_object_name_missing(qtbot) -> None:
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    mount = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    widget = getattr(window, mount.widget_attr)
    widget.setObjectName("")

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "wrong_state_role_owner" and issue["widget"] == mount.state_role
        for issue in issues
    )
    assert not any(issue["kind"] == "unexpected_editable_state_owner" for issue in issues)


def test_gui_scan_reports_named_parameter_table_clone_without_state_role(qtbot) -> None:
    from app_desktop.parameter_table import ParameterTable
    from tools.scan_desktop_gui_schema import ScreenScenario
    from tools.scan_desktop_gui_schema import _state_ownership_issues

    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    mount = MODE_WORKBENCH_SPECS["fitting"].parameters[0]
    clone = ParameterTable(window)
    clone.setObjectName(mount.widget_attr)

    scenario = ScreenScenario(key="test", language="en", mode="fitting")
    issues = _state_ownership_issues(window, scenario)

    assert any(
        issue["kind"] == "unexpected_editable_state_owner" and issue["widget"] == mount.widget_attr
        for issue in issues
    )


def test_gui_scan_rejects_empty_scenario_list(qtbot, monkeypatch) -> None:
    import pytest

    from tools import scan_desktop_gui_schema as scan

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(scan, "_screen_scenarios", lambda *, refresh_language: [])

    with pytest.raises(ValueError, match="duplicate-state scan requires"):
        scan.scan_window(window)
```

- [x] **Step 5: Run structural gates**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_state_ownership.py tests/test_desktop_gui_redesign_scan.py
python tools/scan_desktop_gui_schema.py
```

Expected:

```text
passed
```

The scan report must still contain 270 scenarios with no issues, including both custom fitting and self-consistent fitting submodes.

- [x] **Step 6: Commit Task 2**

Run:

```bash
git add app_desktop/panels.py tools/scan_desktop_gui_schema.py tests/test_desktop_workbench_state_ownership.py tests/test_desktop_gui_redesign_scan.py
git commit -m "test: guard workbench state ownership"
```

---

## Task 3: Make Result Overview State Real And Typed

**Files:**
- Modify: `app_desktop/workbench_results.py`
- Modify: `tests/test_desktop_workbench_results.py`
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/window_extrapolation_mixin.py`
- Modify: `app_desktop/window_fitting_models_mixin.py`
- Modify: `app_desktop/window_fitting_residuals_mixin.py`
- Modify: `app_desktop/window_images_mixin.py`
- Modify: `app_desktop/window_statistics_mixin.py`
- Modify: `app_desktop/workspace_controller.py`
- Modify: `tests/test_workspace_controller.py`

- [x] **Step 1: Add failing no-tabular and failed-state tests**

Append to `tests/test_desktop_workbench_results.py`:

```python
def _tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfeA\xe2\xa1\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_result_rail_distinguishes_plot_only_result(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = ""
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_distinguishes_text_only_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "x = 1.0"

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_result_rail_distinguishes_plot_and_text_without_tabular_data(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "diagnostic text"
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"


def test_result_rail_distinguishes_failed_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._mark_workbench_result_failed()

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_failed_result_survives_ordinary_csv_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_hard_reset_clears_failed_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_result_rail_shows_running_while_worker_is_in_flight(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data(clear_non_tabular_result=True)
    window._mark_workbench_result_running()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Running"


def test_result_rail_plot_only_success_does_not_stay_running(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._mark_workbench_result_running()
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_plot_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._update_result_plot(_tiny_png_bytes(), final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_text_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("text-only result", final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_result_rail_tabular_result_mentions_available_plot(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": "1", "y": "2"}], ["x", "y"])
    window.result_plot_bytes = b"plot-bytes"
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result data: 1 row, 2 columns; plot also available"


def test_result_rail_empty_tabular_schema_is_still_tabular(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([], ["x", "y"])
    window._apply_language("en")

    assert window.workbench_result_table.columnCount() == 2
    assert window.workbench_result_overview.text() == "Result data: 0 rows, 2 columns"


def test_result_overview_copies_only_preview_rows(qtbot: Any) -> None:
    from app_desktop.workbench_results import _overview_state

    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])

    state = _overview_state(window)

    assert state.total_rows == 500
    assert len(state.preview_rows) == 100


def test_result_overview_summary_reports_displayed_row_count(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])
    window._apply_language("en")

    assert "Result data: 500 rows, 1 column" in window.workbench_result_overview.text()
    assert "showing first 50 rows" in window.workbench_result_overview.text()
    assert window.workbench_result_table.rowCount() == 50


def test_result_rail_intermediate_text_does_not_clear_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("intermediate progress")
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_result_rail_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._mark_workbench_result_complete()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_reset_csv_preserves_empty_success_unless_hard_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"

    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_root_solving_empty_success_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_root_solving_finished({"markdown": "", "csv_rows": [], "csv_headers": []})
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_image_list_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_image_list("fit", [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_fit_batches_tabular_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_substituted_expression", lambda *args, **kwargs: "A*x")
    monkeypatch.setattr(window, "_format_fit_result_text", lambda *args, **kwargs: "fit summary")
    monkeypatch.setattr(window, "_render_fit_plot_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_build_fit_csv_rows",
        lambda *args, **kwargs: [{"section": "parameters", "name": "A", "value": "1"}],
    )
    payload = SimpleNamespace(
        job=SimpleNamespace(
            model_expr="A*x",
            headers=["x", "y"],
            data_rows=[],
            sigma_rows=[],
            render_plots=False,
        ),
        expression="A*x",
        fit_result=SimpleNamespace(params={"A": "1"}),
    )

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="fit", fit_payload=payload, error=None, captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result data: 1 row, 8 columns"


def test_fit_batches_text_only_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="error", fit_payload=None, error="bad input", captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_reset_csv_rejects_conflicting_hard_reset_and_preserve_running(qtbot: Any) -> None:
    import pytest

    window = _window(qtbot)
    window._set_csv_data([{"x": "1"}], ["x"])
    window._mark_workbench_result_running()
    window._apply_language("en")

    with pytest.raises(ValueError, match="preserve_workbench_running"):
        window._reset_csv_data(preserve_workbench_running=True, clear_non_tabular_result=True)

    assert window._csv_rows == [{"x": "1"}]
    assert window._csv_headers == ["x"]
    assert window.workbench_result_overview.text() == "Running"


def test_set_csv_empty_payload_preserves_empty_success(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()

    window._set_csv_data([], [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_csv_intermediate_rows_can_preserve_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._set_csv_data([{"x": "1"}], ["x"], final_result=False)
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_worker_start_failure_does_not_leave_running_overview(qtbot: Any) -> None:
    import pytest

    class BrokenWorker:
        def start(self) -> None:
            raise RuntimeError("boom")

    window = _window(qtbot)
    window._apply_language("en")

    with pytest.raises(RuntimeError):
        window._start_worker_with_workbench_result_state(BrokenWorker())

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_worker_start_refreshes_result_rail_once(qtbot: Any, monkeypatch) -> None:
    class Worker:
        def start(self) -> None:
            pass

    window = _window(qtbot)
    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_result_rail", refresh)
    window._start_worker_with_workbench_result_state(Worker())

    assert calls == 1


def test_calc_success_handler_exception_marks_result_failed(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_show_extrapolation_results", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render boom")))
    window._mark_workbench_result_running()

    window._on_calc_finished(
        SimpleNamespace(
            mode="extrapolation",
            logs=[],
            latex_path=None,
            warnings=[],
            payload={"headers": [], "data_rows": [], "results": []},
        )
    )
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_statistics_empty_batches_use_empty_success_overview(qtbot: Any) -> None:
    window = _window(qtbot)

    window._display_statistics_batches([], "value")
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_empty_result_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(window, "_format_statistics_display", lambda **kwargs: ("", []))

    window._display_statistics_result({}, "value", 0, render_plots=False)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_nonempty_batch_without_csv_reports_text_result(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._apply_language("en")
    captured_text: dict[str, str] = {}
    original_set_result_text = window._set_result_text

    def capture_result_text(text: str, *args: Any, **kwargs: Any) -> None:
        captured_text["text"] = text
        original_set_result_text(text, *args, **kwargs)

    monkeypatch.setattr(window, "_set_result_text", capture_result_text)
    monkeypatch.setattr(window, "_render_statistics_text", lambda *args, **kwargs: "")
    monkeypatch.setattr(window, "_build_stats_csv_rows", lambda *args, **kwargs: [])

    window._display_statistics_batches([{"index": 1, "result": {}, "rows": []}], "value", render_plots=False)
    window._apply_language("en")

    assert captured_text["text"].strip()
    assert "Batch" in captured_text["text"]
    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"

```

The non-empty batch test expects a text result, not `empty_success`, because `_display_statistics_batches()` intentionally emits a non-empty per-batch header even when the mocked body and CSV rows are empty. Only genuinely empty text payloads, such as `[]` batches or a single-result formatter returning `("", [])`, should route to `empty_success`. Keep the captured-text assertions with the overview assertions so a future header-format change fails at the statistics batch boundary instead of silently changing result-overview semantics.

```python


def test_run_validation_error_does_not_leave_result_overview_running(qtbot: Any, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window._apply_language("en")

    window.run_calculation()

    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_does_not_reset_results_before_worker(qtbot: Any, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    reset_called = False

    def reset_csv_data(*args: object, **kwargs: object) -> None:
        nonlocal reset_called
        reset_called = True

    monkeypatch.setattr(window, "_reset_csv_data", reset_csv_data)

    window.run_calculation()

    assert reset_called is False


def test_worker_cancellation_clears_running_result_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_worker_cancellation_after_old_plot_does_not_restore_stale_plot(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._workbench_result_state = "running"

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_preserves_previous_valid_result_overview(qtbot: Any, monkeypatch) -> None:
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._last_result_rendered_text = "old text result"
    window.refresh_workbench_result_rail()
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.generate_latex_checkbox.setChecked(True)
    window.output_file_edit.setText("")
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window.run_calculation()

    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py
```

Expected before implementation:

```text
FAILED ... previous valid result overview was cleared
```

- [x] **Step 2: Add typed summary state**

Modify `app_desktop/workbench_results.py`:

```python
from dataclasses import dataclass
from typing import Literal

ResultOverviewKind = Literal["none", "running", "tabular", "plot", "text", "plot_text", "empty_success", "failed"]


@dataclass(frozen=True, slots=True)
class ResultOverviewState:
    kind: ResultOverviewKind
    preview_rows: tuple[dict[str, object], ...] = ()
    total_rows: int = 0
    headers: tuple[str, ...] = ()
    has_plot: bool = False
    has_text: bool = False


def _format_tabular_summary(owner: Any, row_count: int, column_count: int, visible_count: int) -> str:
    extra_zh = f"（显示前 {visible_count} 行）" if visible_count < row_count else ""
    row_word = "row" if row_count == 1 else "rows"
    column_word = "column" if column_count == 1 else "columns"
    extra_en = f" (showing first {visible_count} {row_word})" if visible_count < row_count else ""
    return owner._tr(
        f"结果数据：{row_count} 行，{column_count} 列{extra_zh}",
        f"Result data: {row_count} {row_word}, {column_count} {column_word}{extra_en}",
    )


def _overview_state(owner: Any) -> ResultOverviewState:
    raw_rows = getattr(owner, "_csv_rows", []) or []
    total_rows = len(raw_rows)
    preview_rows = tuple(dict(row) for row in raw_rows[:100] if isinstance(row, dict))
    headers = tuple(str(header) for header in (getattr(owner, "_csv_headers", []) or []))
    if getattr(owner, "_workbench_result_state", "") == "failed":
        return ResultOverviewState("failed")
    if getattr(owner, "_workbench_result_state", "") == "running":
        return ResultOverviewState("running")
    has_plot = getattr(owner, "_result_plot_base_pixmap", None) is not None or bool(getattr(owner, "result_plot_bytes", None))
    rendered_text = str(getattr(owner, "_last_result_rendered_text", "") or "").strip()
    has_text = bool(rendered_text)
    if total_rows or headers:
        return ResultOverviewState(
            "tabular",
            preview_rows=preview_rows,
            total_rows=total_rows,
            headers=headers,
            has_plot=has_plot,
            has_text=has_text,
        )
    if has_plot and has_text:
        return ResultOverviewState("plot_text", has_plot=True, has_text=True)
    if has_plot:
        return ResultOverviewState("plot", has_plot=True)
    if has_text:
        return ResultOverviewState("text", has_text=True)
    if getattr(owner, "_workbench_result_state", "") == "complete":
        return ResultOverviewState("empty_success")
    return ResultOverviewState("none")
```

Then update `refresh_result_overview()` so it uses `_overview_state(owner)` and sets labels:

```python
    state = _overview_state(owner)
    rows = list(state.preview_rows)
    headers = list(state.headers)
    ...
    if state.kind == "tabular":
        ...
        visible_rows = rows[:MAX_RESULT_OVERVIEW_ROWS]
        summary = _format_tabular_summary(owner, state.total_rows, len(headers), len(visible_rows))
        if state.has_plot and state.has_text:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有图片和文本", "; plot and text also available"))
        elif state.has_plot:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有图片", "; plot also available"))
        elif state.has_text:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有文本", "; text also available"))
        else:
            owner.workbench_result_overview.setText(summary)
    elif state.kind == "plot_text":
        owner.workbench_result_overview.setText(
            owner._tr("结果已生成；有图片和文本；无表格数据", "Result ready; plot and text available; no tabular data")
        )
    elif state.kind == "plot":
        owner.workbench_result_overview.setText(owner._tr("结果已生成；无表格数据", "Result ready; no tabular data"))
    elif state.kind == "text":
        owner.workbench_result_overview.setText(owner._tr("文本结果已生成；无表格数据", "Text result ready; no tabular data"))
    elif state.kind == "failed":
        owner.workbench_result_overview.setText(owner._tr("计算失败", "Calculation failed"))
    elif state.kind == "running":
        owner.workbench_result_overview.setText(owner._tr("计算中", "Running"))
    elif state.kind == "empty_success":
        owner.workbench_result_overview.setText(owner._tr("计算完成；无可显示结果", "Calculation complete; no displayable result"))
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
```

Keep `workbench_result_table` as a projection table only. Do not add a second result model.

- [x] **Step 3: Wire result state to real calculation paths**

Modify `app_desktop/window.py` near `_reset_csv_data()` and `_set_csv_data()`:

```python
    def _mark_workbench_result_running(self) -> None:
        self._workbench_result_state = "running"
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()

    def _mark_workbench_result_failed(self) -> None:
        self._workbench_result_state = "failed"
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()

    def _mark_workbench_result_complete(self) -> None:
        self._workbench_result_state = "complete"

    def _clear_workbench_result_state(self) -> None:
        self._workbench_result_state = "none"
```

`_mark_workbench_result_complete()` intentionally mirrors `_clear_workbench_result_state()` and does not refresh by itself. Callers that know a final result payload has been applied must trigger exactly one trailing `refresh_workbench_result_rail()` after all payload/state mutations.

Change `_reset_csv_data()` to accept keyword-only flags. It must clear `running` by default, preserve `failed` through ordinary CSV projection resets, and clear stale text/plot payloads only for hard resets such as worker start or cancellation after a worker exists. Keep `preserve_workbench_running` as an explicit escape hatch for any existing internal caller that must reset CSV projection without ending an already-marked running state; do not use it in the normal worker-start path. If `preserve_workbench_running` and `clear_non_tabular_result` are both true, raise `ValueError` before mutating CSV, text, plot, or overview state:

```python
    def _reset_csv_data(
        self,
        *,
        preserve_workbench_running: bool = False,
        clear_non_tabular_result: bool = False,
        refresh_result_rail: bool = True,
    ):
        if preserve_workbench_running and clear_non_tabular_result:
            raise ValueError("preserve_workbench_running cannot be combined with clear_non_tabular_result")
        ...
        if clear_non_tabular_result:
            self._last_result_text = ""
            self._last_result_text_format = "plain"
            self._last_result_rendered_text = ""
            self.result_plot_bytes = None
            self._result_plot_base_pixmap = None
            if hasattr(self, "result_edit"):
                self.result_edit.clear()
            if hasattr(self, "result_plot_label"):
                self.result_plot_label.clear()
                self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            # A hard reset starts a fresh run/cancel state and intentionally clears failed too.
            self._clear_workbench_result_state()
        elif not preserve_workbench_running:
            current_state = getattr(self, "_workbench_result_state", "none")
            if current_state == "running":
                self._clear_workbench_result_state()
        if refresh_result_rail and hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
```

Move the existing `refresh_workbench_result_rail()` call in `_reset_csv_data()` to the end of the method after the `clear_non_tabular_result` and `_clear_workbench_result_state()` mutations above. There must be at most one result-rail refresh in `_reset_csv_data()`, gated by `refresh_result_rail`, and it must observe the final payload/state values. Do not leave the old refresh before these new mutations.

Do not set `clear_non_tabular_result=True` in successful no-tabular result callbacks; those callbacks intentionally set text/plot payloads first and then call `_reset_csv_data()` to clear only CSV data.

Change `_set_csv_data()` to accept `final_result: bool = True`. After `_csv_rows` and `_csv_headers` have been finalized, and before the result rail refresh, clear the workbench result state only when this call represents a final tabular projection:

```python
        has_tabular_projection = bool(self._csv_rows or self._csv_headers)
        if final_result and has_tabular_projection:
            self._clear_workbench_result_state()
```

This deliberately preserves `empty_success` for final callbacks that have already marked a successful no-display result and then call `_set_csv_data([], [])`. It also gives any future intermediate tabular streaming path a safe escape hatch: such paths must call `_set_csv_data(..., final_result=False)` so the overview remains `Running` until the worker actually finishes. Existing definitive tabular success call sites keep the default `final_result=True`.

Validation failures should not call `_mark_workbench_result_failed()` and should not show `Running`; they are pre-run input errors shown by the existing modal dialogs. This is enforced by marking `running` only after validation has completed and a worker is about to start.

Modify the existing `app_desktop/window_extrapolation_mixin.py::_on_worker_cancelled()` method by adding one workbench-result reset line after the existing `_append_log(...)` call. Do not add a second `_on_worker_cancelled()` definition.

```python
    def _on_worker_cancelled(self):
        self._append_log(self._tr("任务已取消", "Task cancelled"))
        self._reset_csv_data(clear_non_tabular_result=True)

    def _on_calc_failed(self, message: str):
        self._mark_workbench_result_failed()
        ...

    def _on_root_solving_failed(self, message: str):
        self._mark_workbench_result_failed()
        ...
```

Modify `app_desktop/window_fitting_residuals_mixin.py`:

```python
    def _on_fit_failed(self, message: str):
        self._mark_workbench_result_failed()
        ...
```

The existing failure callback bodies must remain intact after the new first line. Cancellation clears `running` back to `none`; it is not a failed result. Do not set the failed state in validation branches that never start a worker unless those branches also call the same failure callback.

Also update success-handler `except` blocks that catch display/rendering exceptions after the worker has already reported success. In `_on_calc_finished()`, call `_mark_workbench_result_failed()` before showing the existing critical dialog. If `_on_root_solving_finished()`, `_on_fit_finished()`, or `_on_fit_batches_finished()` add or already contain local `except` blocks around final display/rendering work, those exception paths must also call `_mark_workbench_result_failed()` before logging/dialog output. This prevents a completed worker's UI rendering exception from leaving the overview stuck at `Running`.

Statistics mode uses `CalcWorker` and connects `worker.failed` to the existing `_on_calc_failed()` path; there is no separate `_on_statistics_failed()` callback to edit. Keep this route covered by the `_on_calc_failed()` failed-state tests instead of adding a duplicate statistics-specific failure handler.

- [x] **Step 4: Refresh result overview after plot/image updates and workspace restore**

Modify `app_desktop/window_images_mixin.py::_update_result_plot()` to accept `final_result: bool = False`. After `_update_image_status()` in both success and empty-image branches, clear/complete only for final payloads:

```python
        if final_result:
            if image_data:
                self._clear_workbench_result_state()
            else:
                self._mark_workbench_result_complete()
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
```

Modify `app_desktop/window.py::_set_result_text()` to accept `final_result: bool = False`. After `_last_result_rendered_text` is updated:

```python
        if final_result:
            if self._last_result_rendered_text.strip():
                self._clear_workbench_result_state()
            else:
                self._mark_workbench_result_complete()
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
```

Modify final worker-success callbacks that produce definitive plot/text-only outputs to pass `final_result=True` to `_update_result_plot(...)` and `_set_result_text(...)`. Do not pass `final_result=True` for progress/intermediate payload updates while a worker is still running. The live production call sites to pin are:

- `app_desktop/window_extrapolation_mixin.py::_on_root_solving_finished()`: change `_update_result_plot(plot_bytes)` to `_update_result_plot(plot_bytes, final_result=True)` and `_set_result_text(markdown)` to `_set_result_text(markdown, final_result=True)`.
- `app_desktop/window_extrapolation_mixin.py::_show_extrapolation_results()`: change the definitive `_set_result_text(text)` call to `_set_result_text(text, final_result=True)`.
- `app_desktop/window_extrapolation_mixin.py::_show_error_results()`: change the definitive `_set_result_text(text)` call to `_set_result_text(text, final_result=True)`.
- `app_desktop/window_fitting_residuals_mixin.py::_on_fit_finished()`: change `_set_result_text(summary)` to `_set_result_text(summary, final_result=True)` and `_update_result_plot(plot_bytes)` to `_update_result_plot(plot_bytes, final_result=True)`.
- `app_desktop/window_fitting_residuals_mixin.py::_on_fit_batches_finished()`: change the definitive `_set_result_text(combined)` call to `_set_result_text(combined, final_result=True)`. Keep `_set_csv_data(...)` as the tabular success clearing path when `csv_rows` exists, and keep the ordinary `_reset_csv_data()` path for text-only/error batch output so the final text result remains visible. The two focused fit-batch tests above must cover both tabular and text-only output shapes.
- `app_desktop/window_statistics_mixin.py::_display_statistics_result()`: change the definitive `_set_result_text(text)` call to `_set_result_text(text, final_result=True)`. If `csv_rows` is empty, the following ordinary `_reset_csv_data()` must preserve the `complete` state so the overview shows empty success rather than `No results`.
- `app_desktop/window_statistics_mixin.py::_display_statistics_batches()`: change both definitive text paths to final results: the empty `if not batches:` branch uses `_set_result_text("", final_result=True)`, and the non-empty branch changes `_set_result_text("\n\n".join(block_texts))` to `_set_result_text("\n\n".join(block_texts), final_result=True)`.
- Defensive legacy parity: `app_desktop/window_fitting_models_mixin.py::_execute_custom_fit()`, `_run_linear_definition_fit()`, and `_execute_template_custom_fit()` currently appear to be synchronous/legacy paths rather than the live async fit path. If they remain in the codebase, change their definitive summary/plot display calls to pass `final_result=True` as well.

Modify `app_desktop/window_statistics_mixin.py::_display_statistics_batches()` in the empty `if not batches:` branch so it routes through the same empty-success state:

```python
            self._set_result_text("", final_result=True)
            ...
            self._reset_csv_data()
```

The ordinary `_reset_csv_data()` call must preserve the `complete` and `failed` states, so the overview shows `Calculation complete; no displayable result` or `Calculation failed` instead of `No results`.

Modify `_set_image_list()` after the final `_update_image_status()` or `_show_image_at(...)` path completes:

```python
        if figures:
            self._clear_workbench_result_state()
        else:
            self._mark_workbench_result_complete()
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
```

Modify `app_desktop/workspace_controller.py` at the end of `restore_workspace()` before setting `_workspace_dirty = False`:

```python
    if hasattr(window, "refresh_workbench_result_rail"):
        window.refresh_workbench_result_rail()
```

Add a regression test to `tests/test_workspace_controller.py`:

```python
def test_workspace_restore_refreshes_plot_only_result_overview(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._reset_csv_data()
    source._last_result_rendered_text = ""
    source._update_result_plot(_tiny_png_bytes())
    path = tmp_path / "plot-only.datalab"
    bundle = capture_workspace(source, title="plot only")
    write_workspace(path, bundle.manifest, bundle.attachments)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    loaded = read_workspace(path)
    restore_workspace(target, loaded.manifest, loaded.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Result ready; no tabular data"
```

If `_tiny_png_bytes()` is not available in `tests/test_workspace_controller.py`, add this local helper near the other test helpers:

```python
def _tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfeA\xe2\xa1\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )
```

- [x] **Step 5: Mark new runs as running only after validation and job construction**

Do not mark the overview `running` and do not hard-reset result payloads at the top of `run_calculation()`. Input validation must complete first. If validation fails, keep the previous valid result overview visible and show the existing validation dialog.

Modify `app_desktop/window_extrapolation_mixin.py::run_calculation()` by deleting any existing top-of-method result reset before validation, including either of these forms if present:

```python
        self._reset_csv_data()
        self._reset_csv_data(clear_non_tabular_result=True)
```

There must be no `_reset_csv_data(...)` call before validation has selected and constructed a worker.

Add a small helper on `ExtrapolationWindow` and call it in each branch that actually constructs a worker. The following applies to the ordinary `CalcWorker`, statistics `CalcWorker`, root-solving `RootSolvingWorker`, and fitting workers in `app_desktop/window_fitting_models_mixin.py`:

```python
    def _start_worker_with_workbench_result_state(self, worker) -> None:
        try:
            self._reset_csv_data(clear_non_tabular_result=True, refresh_result_rail=False)
            self._mark_workbench_result_running()
            self._set_button_to_stop_mode()
            worker.start()
        except Exception:
            self._mark_workbench_result_failed()
            self._set_button_to_run_mode()
            raise
```

Then replace direct worker starts:

```python
        self._start_worker_with_workbench_result_state(worker)
```

At each worker construction site, keep the existing worker handle assignment (`self._calc_worker = worker`, `self._fit_worker = worker`, or `self._root_worker = worker`) before calling `_start_worker_with_workbench_result_state(worker)`. Replace only the final `_set_button_to_stop_mode(); worker.start()` sequence with the helper call; if a call site already invokes `_set_button_to_stop_mode()` immediately before `worker.start()`, remove that preceding call so the helper is the only place that switches the run button to stop mode.

Do not call `_reset_csv_data()` outside `_start_worker_with_workbench_result_state()` for the same branch. The helper's hard reset clears stale CSV/text/plot payloads and visible result widgets only after validation and worker construction have succeeded; `_mark_workbench_result_running()` then changes only the overview state and refreshes it. This prevents the overview from showing stale plot/text output after a real worker starts, while preserving previous valid results for validation errors that return before any worker exists.
If a synchronous `worker.start()` failure occurs, the `except` path must clear `Running` through `_mark_workbench_result_failed()` before restoring the run button and re-raising so existing error handling/tests can still observe the original failure.

- [x] **Step 6: Preserve language refresh**

Check `app_desktop/window_i18n_mixin.py`; it already calls `refresh_workbench_result_rail()` after language changes. Keep that call. Add no new localized strings outside `workbench_results.py`.

- [x] **Step 7: Run result tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py tests/test_desktop_result_workflows.py tests/test_workspace_controller.py tests/test_desktop_gui_workflows.py
```

Expected:

```text
passed
```

- [x] **Step 8: Commit Task 3**

Run:

```bash
git add app_desktop/workbench_results.py tests/test_desktop_workbench_results.py tests/test_workspace_controller.py app_desktop/window.py app_desktop/window_extrapolation_mixin.py app_desktop/window_fitting_models_mixin.py app_desktop/window_fitting_residuals_mixin.py app_desktop/window_images_mixin.py app_desktop/window_statistics_mixin.py app_desktop/workspace_controller.py
git commit -m "feat: distinguish workbench result overview states"
```

---

## Task 4: Remove Or Explicitly Guard Legacy Two-Pane Splitter Logic

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_desktop_workbench_layout.py`
- Run-only regression gate: `tests/test_splitter_persistence.py`

- [x] **Step 1: Add a regression test proving the three-pane contract**

Append to `tests/test_desktop_workbench_layout.py`:

```python
def test_splitter_refresh_requires_three_pane_workbench(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    assert window._main_splitter.count() == 3
    window._refresh_main_splitter_left_min_width()

    assert window._main_splitter.count() == 3
    assert window._main_splitter_left_min_width >= window.workbench_config_rail.minimumWidth()


def test_splitter_clamp_preserves_side_rail_proportions_for_subminimum_center() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 260]
    clamped = _clamp_workbench_splitter_sizes([600, 120, 700], minimums, total=1420)

    assert sum(clamped) == 1420
    assert clamped[0] >= minimums[0]
    assert clamped[1] >= minimums[1]
    assert clamped[2] >= minimums[2]
    assert clamped[0] > minimums[0]
    assert clamped[2] > minimums[2]
    assert abs((clamped[0] / clamped[2]) - (600 / 700)) < 0.35


def test_splitter_clamp_returns_minimums_when_total_cannot_satisfy_contract() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 260]

    assert _clamp_workbench_splitter_sizes([200, 200, 200], minimums, total=600) == minimums


def test_splitter_clamp_preserves_sum_with_small_remainder() -> None:
    from app_desktop.panels import _clamp_workbench_splitter_sizes

    minimums = [320, 520, 260]
    clamped = _clamp_workbench_splitter_sizes([321, 519, 263], minimums, total=1103)

    assert sum(clamped) == 1103
    assert all(size >= minimum for size, minimum in zip(clamped, minimums, strict=True))


def test_splitter_refresh_uses_three_pane_clamp(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    splitter = window._main_splitter
    splitter.setSizes([600, 120, 700])
    QApplication.processEvents()

    window._refresh_main_splitter_left_min_width()
    sizes = splitter.sizes()

    assert sizes[1] >= window.workbench_workspace_canvas.minimumWidth()
    assert sizes[0] > window.workbench_config_rail.minimumWidth()
    assert sizes[2] > window.workbench_result_rail.minimumWidth()
    assert sum(sizes) > 0
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py
```

Expected:

```text
FAILED ... _clamp_workbench_splitter_sizes
```

This is the intended RED boundary for Task 4: the pure clamp helper and the active three-pane clamp are created in Step 2.

- [x] **Step 2: Replace legacy fallback with ratio-preserving three-pane clamp**

Modify `app_desktop/panels.py` in `_refresh_main_splitter_left_min_width()` by deleting the branch that begins after the three-pane `return`:

```python
    left_container = getattr(self, "left_container", None)
    left_scroll = getattr(self, "_left_scroll", None)
    ...
    splitter.setSizes([left_min_width, right_width])
```

Add a small pure helper near `_refresh_main_splitter_left_min_width()` so the clamp math can be tested without relying on `QSplitter.setSizes()` pre-clamping sub-minimum panes:

```python
def _clamp_workbench_splitter_sizes(sizes: list[int], minimums: list[int], total: int) -> list[int]:
    if total <= sum(minimums):
        return list(minimums)
    clamped = [max(size, minimum) for size, minimum in zip(sizes, minimums, strict=True)]
    overflow = sum(clamped) - total
    while overflow > 0:
        surplus = [size - minimum for size, minimum in zip(clamped, minimums, strict=True)]
        candidates = [(available, index) for index, available in enumerate(surplus) if available > 0]
        if not candidates:
            break
        total_surplus = sum(available for available, _ in candidates)
        reductions: list[tuple[int, int]] = []
        for available, index in candidates:
            proportional = int(overflow * (available / total_surplus))
            reductions.append((index, min(available, proportional)))
        if not any(reduction for _, reduction in reductions):
            _, index = max(candidates)
            reductions = [(index, 1)]
        for index, reduction in reductions:
            if overflow <= 0:
                break
            reduction = min(reduction, clamped[index] - minimums[index], overflow)
            if reduction <= 0:
                continue
            clamped[index] -= reduction
            overflow -= reduction
    return clamped
```

Then replace the active three-pane branch with a call to that helper. The clamp must preserve user/restored side-rail proportions as much as possible. Do not reset left and right rails to their absolute minimums just because the center pane is below minimum.

```python
    sizes = splitter.sizes()
    handle_total = splitter.handleWidth() * max(0, splitter.count() - 1)
    total = sum(sizes) or max(0, splitter.width() - handle_total)
    minimums = [
        self.workbench_config_rail.minimumWidth(),
        self.workbench_workspace_canvas.minimumWidth(),
        self.workbench_result_rail.minimumWidth(),
    ]
    if total <= sum(minimums):
        splitter.setSizes(minimums)
        return
    clamped = _clamp_workbench_splitter_sizes(sizes, minimums, total)
    if clamped != sizes:
        splitter.setSizes(clamped)
    return
```

This keeps `left_layout`, `left_container`, and `_left_scroll` as compatibility aliases while making the three-pane workbench the only active geometry contract.

- [x] **Step 3: Run splitter persistence tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py tests/test_splitter_persistence.py
```

Expected:

```text
passed
```

`tests/test_splitter_persistence.py` is a run-only regression gate here. If implementing the new clamp exposes a real persistence-test change, add that file to the Task 4 file list and the commit command in the same patch; otherwise do not stage it.

- [x] **Step 4: Commit Task 4**

Run:

```bash
git add app_desktop/panels.py tests/test_desktop_workbench_layout.py
git commit -m "refactor: enforce three-pane workbench splitter contract"
```

---

## Task 5: Add Shared Formula Workbench Panel Adapter

**Files:**
- Create: `app_desktop/workbench_formula_panel.py`
- Create: `tests/test_desktop_workbench_formula_panel.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/ui_schema_binder.py`
- Modify: `app_desktop/window.py`

- [x] **Step 1: Write failing formula panel tests**

Create `tests/test_desktop_workbench_formula_panel.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_formula_workspace_panel_mounts_existing_editors(qtbot: Any) -> None:
    window = _window(qtbot)
    panel = window.findChild(QWidget, "workbench_formula_panel")

    assert panel is not None
    assert window.workbench_formula_preview_label.parentWidget() is panel
    assert window.fit_expr_edit.parentWidget() is window.fit_box
    assert window.fit_formula_preview_button.parentWidget() is not None


def test_formula_workspace_has_single_persistent_preview_label(qtbot: Any) -> None:
    from app_desktop.formula_preview import FormulaPreviewLabel

    window = _window(qtbot)

    assert window.findChildren(FormulaPreviewLabel) == [window.workbench_formula_preview_label]


def test_formula_workspace_preview_uses_current_editor_text(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_expr_edit.setPlainText("A*x+B")
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_preview_tracks_last_edited_implicit_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    assert window._workbench_active_formula_attr == "implicit_output_edit"
    window.refresh_workbench_formula_panel()

    assert current_formula_mount(window).editor_attr == "implicit_output_edit"


def test_formula_workspace_preview_prefers_focused_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_equation_edit.setPlainText("u - x")
    window.implicit_equation_edit.setFocus()
    QApplication.processEvents()

    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_focus_filter_updates_active_formula(qtbot: Any) -> None:
    from PySide6.QtCore import QEvent
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    handled = window._workbench_formula_focus_filter.eventFilter(
        window.implicit_equation_edit,
        QEvent(QEvent.Type.FocusIn),
    )

    assert handled is False
    assert window._workbench_active_formula_attr == "implicit_equation_edit"
    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_installs_editor_local_focus_filter(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window._workbench_formula_focus_filter is not None
    assert not hasattr(window, "_workbench_formula_focus_disconnect")


def test_formula_workspace_title_describes_multi_formula_card(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    assert window.workbench_formula_panel_title.text() == "Model formulas"
    assert window._workbench_formula_mount_labels["implicit_output_edit"].text() == "Output expression:"


def test_formula_workspace_mode_switch_uses_bound_schema_title_without_manual_refresh(qtbot: Any) -> None:
    window = _window(qtbot)
    window._apply_language("en")
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert window.workbench_formula_panel_title.text() == "Formula preview"


def test_formula_workspace_title_does_not_expose_raw_schema_key_when_label_missing(qtbot: Any) -> None:
    from app_desktop.ui_schema_binder import SCHEMA_LABEL_EN_PROPERTY, SCHEMA_LABEL_ZH_PROPERTY

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_ZH_PROPERTY, "")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_EN_PROPERTY, "")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    title = window.workbench_formula_panel_title.text()
    output_label = window._workbench_formula_mount_labels["implicit_output_edit"].text()
    assert "fitting.implicit.output_expression" not in title
    assert "fitting.implicit.output_expression" not in output_label
    assert title == "Model formulas"
    assert output_label == "Output Expression:"


def test_formula_panel_hidden_when_mode_has_no_formulas(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()


def test_formula_panel_hidden_when_fitting_submode_has_no_visible_formula(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    assert window.workbench_formula_panel.isVisible()

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("polynomial"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()


def test_formula_workspace_refreshes_on_fitting_submode_visibility_change(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_formula_panel", refresh)

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()

    assert calls >= 1
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_formula_panel.py
```

Expected before implementation:

```text
FAILED ... workbench_formula_panel
```

- [x] **Step 2: Expose existing schema labels to bound widgets**

Modify `app_desktop/ui_schema_binder.py` so widgets bound through `bind_field()` carry localized label metadata from the existing `FormFieldSpec`. Do not add a second label registry and do not duplicate user-facing formula titles in `workbench_specs.py`:

```python
SCHEMA_LABEL_ZH_PROPERTY = "datalab_schema_label_zh"
SCHEMA_LABEL_EN_PROPERTY = "datalab_schema_label_en"


def _set_localized_label(obj: Any, zh: str, en: str) -> None:
    _set_property(obj, SCHEMA_LABEL_ZH_PROPERTY, zh)
    _set_property(obj, SCHEMA_LABEL_EN_PROPERTY, en)
```

In `bind_field()`, call `_set_localized_label(..., field.label.zh, field.label.en)` for `label`, `widget`, and `help_button` when those objects are present. Reuse the existing `_set_property()` helper already present in `app_desktop/ui_schema_binder.py`; do not replace it with a second property helper. Existing language refresh remains owned by the current `_register_schema_label_refresh()` / `bind_field()` paths; this metadata is read-only context for shared workbench panels.
The localized label properties must be written even when both labels are empty, so re-binding a widget cannot leave stale label metadata behind.

- [x] **Step 3: Add the adapter module**

Create `app_desktop/workbench_formula_panel.py`:

```python
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from app_desktop.formula_preview import FormulaPreviewLabel, update_formula_preview
from app_desktop.ui_schema_binder import SCHEMA_LABEL_EN_PROPERTY, SCHEMA_LABEL_ZH_PROPERTY
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, FormulaMount


def build_formula_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_formula_panel")
    panel.setMinimumHeight(72)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    owner.workbench_formula_panel_title = QLabel(owner._tr("公式预览", "Formula preview"))
    owner.workbench_formula_panel_title.setObjectName("workbench_formula_panel_title")
    layout.addWidget(owner.workbench_formula_panel_title)

    owner.workbench_formula_preview_label = FormulaPreviewLabel()
    owner.workbench_formula_preview_label.setObjectName("workbench_formula_preview_label")
    owner.workbench_formula_preview_label.setMinimumHeight(44)
    layout.addWidget(owner.workbench_formula_preview_label)

    owner._workbench_formula_refresh_timer = QTimer(owner)
    owner._workbench_formula_refresh_timer.setSingleShot(True)
    owner._workbench_formula_refresh_timer.setInterval(120)
    owner._workbench_formula_refresh_timer.timeout.connect(owner.refresh_workbench_formula_panel)
    owner._workbench_formula_focus_filter = _FormulaFocusFilter(owner)
    _install_formula_focus_filters(owner)
    return panel


class _FormulaFocusFilter(QObject):
    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn:
            owner = self._owner
            mode = str(owner.mode_combo.currentData() or "")
            spec = MODE_WORKBENCH_SPECS.get(mode)
            if spec is None:
                return False
            for mount in spec.formulas:
                editor = getattr(owner, mount.editor_attr, None)
                if editor is None:
                    continue
                if not editor.isVisibleTo(owner):
                    continue
                viewport = editor.viewport() if hasattr(editor, "viewport") else None
                is_child_widget = isinstance(watched, QWidget) and editor.isAncestorOf(watched)
                if watched is editor or watched is viewport or is_child_widget:
                    owner._workbench_active_formula_attr = mount.editor_attr
                    schedule_formula_workspace_refresh(owner, mount.editor_attr)
                    return False
        return False


def _install_formula_focus_filters(owner: Any) -> None:
    focus_filter = owner._workbench_formula_focus_filter
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.formulas:
            editor = getattr(owner, mount.editor_attr, None)
            if editor is None:
                continue
            editor.installEventFilter(focus_filter)
            if hasattr(editor, "viewport"):
                editor.viewport().installEventFilter(focus_filter)


def _widget_or_child_has_focus(widget: QWidget) -> bool:
    focused = QApplication.focusWidget()
    while focused is not None:
        if focused is widget:
            return True
        focused = focused.parentWidget()
    return False


def current_formula_mount(owner: Any) -> FormulaMount | None:
    mode = str(owner.mode_combo.currentData() or "")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return None
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if editor is not None and editor.isVisibleTo(owner) and _widget_or_child_has_focus(editor):
            return mount
    active_attr = getattr(owner, "_workbench_active_formula_attr", "")
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if mount.editor_attr == active_attr and editor is not None and editor.isVisibleTo(owner):
            return mount
    visible_mounts: list[FormulaMount] = []
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if editor is not None and editor.isVisibleTo(owner):
            visible_mounts.append(mount)
    if len(visible_mounts) >= 1:
        return visible_mounts[0]
    return None


def refresh_formula_workspace_panel(owner: Any) -> None:
    panel = getattr(owner, "workbench_formula_panel", None)
    label = getattr(owner, "workbench_formula_preview_label", None)
    if label is None:
        return
    title = getattr(owner, "workbench_formula_panel_title", None)
    mode = str(owner.mode_combo.currentData() or "")
    mount = current_formula_mount(owner)
    if mount is None:
        if title is not None:
            title.setText(owner._tr("公式预览", "Formula preview"))
        if panel is not None:
            panel.setVisible(False)
        label.clear()
        return
    if panel is not None:
        panel.setVisible(True)
    editor = getattr(owner, mount.editor_attr)
    if title is not None:
        title.setText(_formula_panel_title(owner, mode))
    text = editor.toPlainText().strip() if hasattr(editor, "toPlainText") else editor.text().strip()
    update_formula_preview(label, text, lhs=mount.lhs)


def _formula_mount_title(owner: Any, editor: QWidget, mount: FormulaMount) -> str:
    zh = str(editor.property(SCHEMA_LABEL_ZH_PROPERTY) or "")
    en = str(editor.property(SCHEMA_LABEL_EN_PROPERTY) or "")
    fallback = _schema_key_fallback(mount.schema_key)
    zh_title = _with_label_suffix(zh or fallback, "：")
    en_title = _with_label_suffix(en or fallback, ":")
    return owner._tr(zh_title, en_title)


def _formula_panel_title(owner: Any, mode: str) -> str:
    visible_count = len(_visible_formula_mounts(owner, mode))
    if visible_count > 1:
        return owner._tr("模型公式", "Model formulas")
    return owner._tr("公式预览", "Formula preview")


def _schema_key_fallback(schema_key: str) -> str:
    tail = schema_key.rsplit(".", 1)[-1]
    words = tail.replace("_", " ").replace("-", " ").strip()
    return words.title() if words else "Formula"


def _with_label_suffix(text: str, suffix: str) -> str:
    stripped = text.rstrip()
    if stripped.endswith((":", "：")):
        return stripped
    return f"{stripped}{suffix}"


def schedule_formula_workspace_refresh(owner: Any, editor_attr: str | None = None) -> None:
    if editor_attr:
        owner._workbench_active_formula_attr = editor_attr
    timer = getattr(owner, "_workbench_formula_refresh_timer", None)
    if timer is not None:
        timer.start()
```

- [x] **Step 4: Wire the panel into `panels.build_ui()`**

Modify `app_desktop/panels.py` imports:

```python
from app_desktop.workbench_formula_panel import (
    build_formula_workspace_panel,
    refresh_formula_workspace_panel,
    schedule_formula_workspace_refresh,
)
```

After `reparent_widget(self.workbench_workspace_layout, self.manual_box, stretch=2)` and before reparenting `mode_stack`, add:

```python
    self.workbench_formula_panel = build_formula_workspace_panel(self)
    self.workbench_workspace_layout.addWidget(self.workbench_formula_panel)
```

Expose methods near the panel helpers:

```python
def refresh_workbench_formula_panel(self) -> None:
    refresh_formula_workspace_panel(self)
```

Connect editor changes after mode widgets are created:

```python
    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(self, formula.editor_attr, None)
            if editor is not None and hasattr(editor, "textChanged"):
                editor.textChanged.connect(
                    lambda *args, _attr=formula.editor_attr: schedule_formula_workspace_refresh(self, _attr)
                )
```

The `textChanged` wiring must be derived from `MODE_WORKBENCH_SPECS`, not from a hardcoded formula-attribute list, so future schema/editor additions cannot silently miss live preview refresh. The `_FormulaFocusFilter` is only for selecting the active formula editor on focus changes. Typing updates must always flow through these `textChanged` connections and the debounced timer; do not rely on focus events to refresh formula content while the user is editing. The focus filter is installed on the editor and viewport for the existing plain-text editor surfaces; if a future complex custom formula editor introduces additional focusable child widgets, that editor must either install the same filter on its focusable children or expose one focus proxy covered by this adapter.

Call `self.refresh_workbench_formula_panel()` after `_on_mode_change()` completes. The initial `build_ui()` refresh must run after `self._bind_workbench_spec_schema_keys()` has completed, so `_formula_mount_title()` sees schema-label metadata on the first visible paint rather than briefly falling back to the humanized schema tail.
The common `workbench_formula_preview_label` is the only persistent formula preview surface. Keep existing preview buttons as popup/dialog entry points, but do not create or leave additional persistent `FormulaPreviewLabel` widgets inside mode pages. Existing tests that assert implicit model pages contain no `FormulaPreviewLabel` must continue to pass.

Implementation note from execution: the final wiring stores formula `textChanged` callbacks on the window and has those callbacks hold only a weak reference to the window. This keeps PySide signal callbacks alive without creating a window reference cycle. `schedule_formula_workspace_refresh()` also ignores hidden or read-only editors so programmatic updates to inactive formula fields cannot steal the active formula selection.

- [x] **Step 5: Run formula tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py tests/test_formula_preview_rendering.py tests/test_desktop_workbench_editor_canvas.py
```

Expected:

```text
passed
```

- [x] **Step 6: Commit Task 5**

Run:

```bash
git add app_desktop/workbench_formula_panel.py app_desktop/panels.py app_desktop/ui_schema_binder.py app_desktop/window.py tests/test_desktop_workbench_formula_panel.py tests/test_desktop_ui_schema_binder.py
git commit -m "feat: add shared formula workbench panel"
```

---

## Task 6: Add Shared Variable Tables Panel Adapter

**Files:**
- Create: `app_desktop/workbench_variable_panel.py`
- Create: `tests/test_desktop_workbench_variable_panel.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `tests/test_workspace_controller.py`

- [x] **Step 1: Write failing variable panel tests**

Create `tests/test_desktop_workbench_variable_panel.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_variable_panel_mounts_existing_parameter_and_constant_widgets(qtbot: Any) -> None:
    window = _window(qtbot)
    panel = window.findChild(QWidget, "workbench_variable_panel")

    assert panel is not None
    assert window.custom_params_table in panel.findChildren(type(window.custom_params_table))
    assert window.custom_constants_editor in panel.findChildren(type(window.custom_constants_editor))
    assert window.custom_params_table.property("datalab_state_role") == "custom_parameters_owner"
    assert window.custom_constants_editor.property("datalab_state_role") == "custom_constants_owner"


def test_variable_panel_preserves_parameter_table_behavior(qtbot: Any) -> None:
    window = _window(qtbot)
    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    window.custom_params_table.add_parameter_row({"name": "B", "initial": "2"})

    rows = window.custom_params_table.rows()

    assert [row["name"] for row in rows if row["name"]] == ["A", "B"]


def test_variable_panel_preserves_constants_text_view(qtbot: Any) -> None:
    window = _window(qtbot)
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.use_text_view(True)
    window.custom_constants_editor.set_text("CR 3.2898419602500(36)[+9]")

    assert window.custom_constants_editor.constants_dict(validate=True)["CR"].startswith("3.289")


def test_variable_panel_tracks_fitting_submode_visibility(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()
    assert window.custom_params_table.isVisible()
    assert window.custom_constants_editor.isVisible()
    assert not window.implicit_params_table.isVisible()
    assert not window.implicit_constants_editor.isVisible()

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()
    assert not window.custom_params_table.isVisible()
    assert not window.custom_constants_editor.isVisible()
    assert window.implicit_params_table.isVisible()
    assert window.implicit_constants_editor.isVisible()

    built_in_index = next(
        (
            index
            for index in range(window.fit_model_combo.count())
            if window.fit_model_combo.itemData(index) not in {"custom", "self_consistent"}
        ),
        None,
    )
    assert built_in_index is not None
    window.fit_model_combo.setCurrentIndex(built_in_index)
    QApplication.processEvents()

    assert not window.custom_params_table.isVisible()
    assert not window.custom_constants_editor.isVisible()
    assert not window.implicit_params_table.isVisible()
    assert not window.implicit_constants_editor.isVisible()
    assert not window.workbench_variable_panel.isVisible()


def test_root_variable_panel_orders_unknowns_before_constants(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    page = window.workbench_variable_stack.currentWidget()
    widgets = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if page.layout().itemAt(index).widget() is not None
    ]

    assert widgets.index(window.root_unknowns_table) < widgets.index(window.root_constants_editor)


def test_fitting_variable_panel_orders_constraints_after_parameter_table(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    page = window.workbench_variable_stack.currentWidget()
    widgets = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if page.layout().itemAt(index).widget() is not None
    ]

    assert widgets.index(window.custom_param_header_widget) < widgets.index(window.custom_params_table)
    assert widgets.index(window.custom_params_table) < widgets.index(window.custom_constraints_checkbox)
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_variable_panel.py
```

Expected before implementation:

```text
FAILED ... workbench_variable_panel
```

- [x] **Step 2: Add the variable adapter**

Create `app_desktop/workbench_variable_panel.py`:

```python
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
from app_desktop.workbench_layout import reparent_widget


def build_variable_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_variable_panel")
    panel.setMinimumHeight(96)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    owner.workbench_variable_title = QLabel(owner._tr("参数与常数", "Parameters and constants"))
    owner.workbench_variable_title.setObjectName("workbench_variable_title")
    layout.addWidget(owner.workbench_variable_title)

    owner.workbench_variable_stack = QStackedWidget()
    owner.workbench_variable_stack.setObjectName("workbench_variable_stack")
    layout.addWidget(owner.workbench_variable_stack)
    owner._workbench_variable_pages = {}
    return panel


def populate_variable_workspace_panel(owner: Any) -> None:
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None or stack.count() > 0:
        return
    pages = owner._workbench_variable_pages
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        page = QWidget()
        page.setObjectName(f"workbench_variable_page_{mode}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for mount in spec.parameters + spec.tables + spec.constants:
            for attr in _mount_attrs_in_visual_order(mount):
                widget = getattr(owner, attr, None)
                if widget is not None:
                    reparent_widget(layout, widget)
        layout.addStretch(1)
        stack.addWidget(page)
        pages[mode] = page


def _mount_attrs_in_visual_order(mount: Any) -> tuple[str, ...]:
    pre_attrs = tuple(attr for attr in mount.companion_attrs if "header" in attr)
    post_attrs = tuple(attr for attr in mount.companion_attrs if attr not in pre_attrs)
    return pre_attrs + (mount.widget_attr,) + post_attrs


def refresh_variable_workspace_panel(owner: Any) -> None:
    panel = getattr(owner, "workbench_variable_panel", None)
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None:
        return
    title = getattr(owner, "workbench_variable_title", None)
    if title is not None:
        title.setText(owner._tr("参数与常数", "Parameters and constants"))
    mode = str(owner.mode_combo.currentData() or "")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    has_variables = bool(spec and (spec.parameters or spec.tables or spec.constants))
    if not has_variables:
        if panel is not None:
            panel.setVisible(False)
        return
    pages = getattr(owner, "_workbench_variable_pages", {})
    page = pages.get(mode)
    if page is not None:
        stack.setCurrentWidget(page)
    page_has_visible_variables = False
    if page is not None and page.layout() is not None:
        for index in range(page.layout().count()):
            item = page.layout().itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.isVisibleTo(page):
                page_has_visible_variables = True
                break
    if panel is not None:
        panel.setVisible(page_has_visible_variables)
```

This task deliberately moves the existing parameter/constant widgets into the shared variable panel. Do not create a wrapper that leaves a second editable parameter or constants table in the original mode page. The source of truth remains the existing widget object, addressed by the same public attribute.
For the fitting mode, custom and self-consistent parameter/constant widgets intentionally remain in the same fitting page during this common-shell phase. Their mutually exclusive visibility stays owned by the existing `_update_model_controls()` logic and is locked by `test_variable_panel_tracks_fitting_submode_visibility`; do not create duplicate submode widgets to make the adapter look more isolated.

- [x] **Step 3: Keep fitting submode visibility correct after reparenting**

Modify `app_desktop/window.py` in `_update_model_controls()` after `self.implicit_model_widget.setVisible(mode == "self_consistent")`:

```python
        show_implicit = mode == "self_consistent"
        for name in (
            "implicit_param_header_widget",
            "implicit_params_table",
            "implicit_constraints_checkbox",
            "implicit_constants_editor",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(show_implicit)
```

Do not set or overwrite `datalab_state_role` inside `populate_variable_workspace_panel()`. Task 2 owns those structural roles; this adapter only reparents existing widgets into visible mode pages. Companion widgets such as add/remove buttons and headers may remain untagged because they are not state owners.

Keep the existing custom visibility loop, and ensure it still includes `custom_param_header_widget`, `custom_params_table`, and `custom_constraints_checkbox`. Leave `custom_constants_editor.setVisible(mode == "custom")` in place.

At the end of `_update_model_controls()`, after custom and self-consistent widget visibility has been updated, refresh both shared workbench panels. The formula panel refresh prevents stale previews/titles when a fitting submode hides one formula editor and reveals another; the variable panel refresh hides the panel when a built-in model has no visible parameter/constant controls:

```python
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
```

- [x] **Step 4: Wire and refresh the variable panel**

Modify `app_desktop/panels.py` imports:

```python
from app_desktop.workbench_variable_panel import (
    build_variable_workspace_panel,
    populate_variable_workspace_panel,
    refresh_variable_workspace_panel,
)
```

After `self.workbench_formula_panel` is added, add:

```python
    self.workbench_variable_panel = build_variable_workspace_panel(self)
    self.workbench_workspace_layout.addWidget(self.workbench_variable_panel)
```

After the existing mode stack is fully built, add:

```python
    populate_variable_workspace_panel(self)
```

Expose:

```python
def refresh_workbench_variable_panel(self) -> None:
    refresh_variable_workspace_panel(self)
```

Call it from `_on_mode_change()` after `mode_stack.setCurrentIndex(...)`.

- [x] **Step 5: Add a workspace round-trip smoke test**

Append to `tests/test_workspace_controller.py`:

```python
def test_workspace_round_trip_preserves_workbench_variable_panel_state(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.custom_params_table.set_rows([{"name": "A", "initial": "1.25"}])
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "CR", "value": "3.2898419602500(36)[+9]"}])
    path = tmp_path / "variables.datalab"

    bundle = capture_workspace(window, title="variables")
    write_workspace(path, bundle.manifest, bundle.attachments)
    loaded = read_workspace(path)
    restored = ExtrapolationWindow()
    qtbot.addWidget(restored)
    restore_workspace(restored, loaded.manifest, loaded.attachments)

    assert restored.custom_params_table.rows()[0]["name"] == "A"
    assert restored.custom_constants_editor.rows()[0]["name"] == "CR"
```

- [x] **Step 6: Run variable/workspace tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_variable_panel.py tests/test_parameter_table.py tests/test_constants_editor.py tests/test_workspace_controller.py
```

Expected:

```text
passed
```

- [x] **Step 7: Commit Task 6**

Run:

```bash
git add app_desktop/workbench_variable_panel.py app_desktop/panels.py app_desktop/window.py tests/test_desktop_workbench_variable_panel.py tests/test_workspace_controller.py
git commit -m "feat: add shared variable workbench panel"
```

---

## Task 7: Apply Descriptor Refresh Hooks Across Modes

**Files:**
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Modify: `tests/test_desktop_workbench_editor_canvas.py`

- [x] **Step 1: Add panel mode-refresh and language-title tests**

Append to `tests/test_desktop_workbench_editor_canvas.py`:

```python
def test_common_workbench_panels_track_mode_changes(qtbot: Any) -> None:
    window = _window(qtbot)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.mode_stack.currentWidget() is window.root_box
    assert window.workbench_variable_stack.currentWidget().objectName() == "workbench_variable_page_root_solving"
    assert "root" in window.workbench_variable_stack.currentWidget().objectName()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert window.mode_stack.currentWidget() is window.fit_box
    assert window.workbench_variable_stack.currentWidget().objectName() == "workbench_variable_page_fitting"


def test_common_workbench_panel_titles_refresh_on_language_change(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))

    window._apply_language("en")
    assert window.workbench_formula_panel_title.text() == "Formula preview"
    assert window.workbench_variable_title.text() == "Parameters and constants"

    window._apply_language("zh")
    assert window.workbench_formula_panel_title.text() == "公式预览"
    assert window.workbench_variable_title.text() == "参数与常数"
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py
```

Expected before Task 7 language-refresh implementation:

```text
FAILED ... workbench_formula_panel_title
```

The mode-tracking assertion may already be GREEN after Task 6 because Task 6 wires the variable stack from `_on_mode_change()` to support fitting submode visibility. Keep the mode-tracking assertion as a regression guard, but use the language-title assertion as this task's RED evidence.

- [x] **Step 2: Refresh common panels from mode changes**

Modify `app_desktop/window.py` in `_on_mode_change()` after the existing `mode_stack.setCurrentIndex(...)` block. Task 6 already adds the variable-panel refresh needed for mode and fitting-submode visibility. Add the formula refresh and keep exactly one guarded variable refresh inside `_on_mode_change()`:

```python
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
```

`_update_model_controls()` also refreshes the variable panel for fitting submode changes after it toggles the custom/self-consistent/built-in controls. That cross-method refresh is intentional and may run during fitting mode switches; do not remove it unless a replacement test still proves built-in fitting models hide an empty variable panel.

- [x] **Step 3: Refresh common panels from language changes**

Modify `app_desktop/window_i18n_mixin.py` after the existing result rail refresh:

```python
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
```

- [x] **Step 4: Run bilingual and schema gates**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_bilingual_inventory.py
python tools/scan_desktop_gui_schema.py
```

Expected:

```text
passed
```

- [x] **Step 5: Commit Task 7**

Run:

```bash
git add app_desktop/window.py app_desktop/window_i18n_mixin.py tests/test_desktop_workbench_editor_canvas.py
git commit -m "feat: synchronize shared workbench panels across modes"
```

---

## Task 8: Documentation, Screenshots, And Full Quality Gate

**Files:**
- Modify: `docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md`
- Modify: `docs/desktop/guide.en.md`
- Modify: `docs/desktop/guide.zh.md`
- Modify: `docs/TEST_MATRIX.md`
- Modify: `tests/test_desktop_workbench_visual_screenshots.py`
- Modify: `tools/capture_desktop_gui_screens.py`

- [x] **Step 1: Update screenshot assertions for new common panels**

Modify `tests/test_desktop_workbench_visual_screenshots.py` to assert the screenshot manifest includes formula, variable, and result overview panel metrics. Formula and variable panels are visible only when the active `MODE_WORKBENCH_SPECS` entry has corresponding content; do not force empty statistics-mode panels to remain visible just to satisfy screenshots. For fitting screenshots, make the capture tool select a variable-bearing fitting submode such as `custom` before the metrics are recorded, so the screenshot gate is deterministic and does not depend on the default built-in model selection:

```python
def test_screenshot_manifest_includes_common_workbench_panels(tmp_path) -> None:
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    manifest = capture_desktop_gui_screens(out=tmp_path, width=1440, height=900)

    assert manifest["screenshots"]
    for screenshot in manifest["screenshots"]:
        regions = screenshot["regions"]
        spec = MODE_WORKBENCH_SPECS[screenshot["mode"]]

        result_metric = regions["workbench_result_overview_panel"]
        assert result_metric["visible"] is True
        assert result_metric["width"] >= 160
        assert result_metric["height"] >= 48

        formula_metric = regions["workbench_formula_panel"]
        assert formula_metric["visible"] is bool(spec.formulas)
        if spec.formulas:
            assert formula_metric["width"] >= 160
            assert formula_metric["height"] >= 48

        variable_metric = regions["workbench_variable_panel"]
        has_variables = bool(spec.parameters or spec.tables or spec.constants)
        assert variable_metric["visible"] is has_variables
        if has_variables:
            assert variable_metric["width"] >= 160
            assert variable_metric["height"] >= 48
```

The result overview metrics target the existing container returned by `app_desktop/workbench_results.py::build_result_overview()`, whose object name is `workbench_result_overview_panel`. Preserve that object name; do not collect metrics from the child label `workbench_result_overview`, because the screenshot gate needs the full panel geometry.

If `capture_desktop_gui_screens()` currently records only the five shell regions, update `tools/capture_desktop_gui_screens.py` in two insertion points.

First, apply the fitting submode override before `image = window.grab()` and before shell `metrics` are computed. This keeps the saved PNG, shell-region metrics, and common-panel metrics in the same visible state:

```python
if scenario.mode == "fitting" and hasattr(window, "fit_model_combo"):
    custom_index = window.fit_model_combo.findData("custom")
    if custom_index >= 0:
        window.fit_model_combo.setCurrentIndex(custom_index)
        QApplication.processEvents()
```

Second, after shell `metrics` has been computed and before `screenshots.append(...)`, extract the current inline `regions` manifest value to a local variable and append the common panel metrics:

```python
from app_desktop.workbench_visual_contract import widget_metric
from dataclasses import asdict

regions = {key: asdict(metric) for key, metric in metrics.items()}
for object_name in ("workbench_formula_panel", "workbench_variable_panel", "workbench_result_overview_panel"):
    regions[object_name] = asdict(widget_metric(window, object_name))
```

Then change the screenshot manifest entry from the current inline value:

```python
"regions": {key: asdict(metric) for key, metric in metrics.items()},
```

to:

```python
"regions": regions,
```

- [x] **Step 2: Update user docs**

Update `docs/desktop/guide.en.md` and `docs/desktop/guide.zh.md` with concise sections that describe:

```markdown
### Shared workbench

The center workspace keeps the active data editor together with the formula preview, parameter table, and constants table when the active mode provides those inputs. Formula previews are display-only; calculation still uses the source expression in the editor.

### Result overview

The right rail summarizes the real result state. If a calculation produces plots or text without tabular rows, the overview reports that no tabular data is available instead of treating the run as missing.
```

Use Chinese text in `guide.zh.md` with the same meaning.

- [x] **Step 3: Document the quality gate**

Update `docs/TEST_MATRIX.md` with this command block:

```bash
python -m compileall -q .
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py tests/test_desktop_workbench_state_ownership.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_formula_panel.py tests/test_desktop_workbench_variable_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_visual_screenshots.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py tests/test_workspace_controller.py tests/test_packaging_resources.py tests/test_desktop_docs_resources.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
QT_QPA_PLATFORM=offscreen pytest -q
```

- [x] **Step 4: Run the full quality gate**

Run exactly:

```bash
python -m compileall -q .
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py tests/test_desktop_workbench_state_ownership.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_formula_panel.py tests/test_desktop_workbench_variable_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_visual_screenshots.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py tests/test_workspace_controller.py tests/test_packaging_resources.py tests/test_desktop_docs_resources.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
QT_QPA_PLATFORM=offscreen pytest -q
```

Expected:

```text
compileall passes
focused pytest commands pass
scan report has 270 scenarios and 0 issues
screenshot capture writes 22 screenshots and 0 issues
full pytest passes with only existing documented skips/warnings
```

- [x] **Step 5: Run final post-implementation read-only reviews**

This is the only Claude review in the updated workflow. Run it only after Tasks 1-8 are implemented and Step 4's full local quality gate passes. Do not use Claude to gate individual tasks or plan chunks.

Run the final Claude for Codex large review:

```bash
CODEX_PLUGIN_ROOT=${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/claude-for-codex/0.15.0 \
node ${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/claude-for-codex/0.15.0/scripts/claude-companion.mjs adversarial-review \
  --quality strong \
  --scope working-tree \
  --path app_desktop \
  --path tests \
  "Review the completed high-fidelity workbench implementation for duplicated GUI state, broken workspace restore, schema/i18n drift, and result overview correctness. Return PASS, CONTESTED, or REJECT."
```

Run Gemini through Antigravity:

```bash
CODEX_PLUGIN_ROOT=${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/antigravity-for-codex/0.5.4 \
ANTIGRAVITY_FOR_CODEX_MODEL="Gemini 3.1 Pro (High)" \
node ${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/antigravity-for-codex/0.5.4/scripts/antigravity-companion.mjs adversarial-review \
  --scope working-tree \
  "Review the completed DataLab high-fidelity workbench implementation against docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md and find GUI state duplication, brittle adapters, stale result states, and maintainability problems."
```

If Gemini times out, returns empty output, or emits malformed output, record that in `progress.md` and use main-thread judgment to decide whether a narrower Gemini follow-up is needed. If the final Claude review fails due to quota/tooling, record the exact blocker in `progress.md`; do not reintroduce per-task Claude gates.

Status update 2026-06-13: the final Claude job `job-mqbxmyd3-fb7387` was run as a tracked background job and allowed to complete naturally. It returned `PASS` with three accepted findings: section-card runtime theme refresh, statistics card height cap, and formula action stack monotonic width. All three findings were fixed and validated with focused tests, ruff, compileall, GUI schema scan, screenshot capture, and `git diff --check`.

Gemini/Antigravity was also run through tracked background jobs. The first full workbench review job `agy-mqbyf3zf-18276c46d264` completed successfully; accepted findings around formula action width calculation, result-details empty-state ownership, and English singular/plural text were fixed and validated. Follow-up job `agy-mqbz7ha1-a3e8bf819327` completed successfully and found additional Qt layout edge cases; accepted findings around `QStackedWidget.minimumSizeHint()`, inherited layout spacing, nested layouts, empty-label i18n registration, section-card repeated stylesheet application, and the statistics uncapped-height test were fixed. The final narrowed confirmation job `agy-mqbzqz7q-f5b04242bf41` completed successfully; main-thread triage accepted the nested-layout/type-hardening and stylesheet no-op findings and rejected non-actionable or current-code-inaccurate claims about action-button shrinkability and future empty-state granularity. Local validation after the accepted fixes: focused regression tests passed, the related GUI partition passed, ruff passed, compileall passed, GUI schema scan reported 270 scenarios with no issues and `left_panel_no_horizontal_scrollbar=true`, screenshot capture reported 22 screenshots with no issues, and `git diff --check` passed.

- [x] **Step 6: Commit Task 8**

Run:

```bash
git add docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md docs/desktop/guide.en.md docs/desktop/guide.zh.md docs/TEST_MATRIX.md tests/test_desktop_workbench_visual_screenshots.py tools/capture_desktop_gui_screens.py
git commit -m "docs: document high fidelity workbench quality gate"
```

---

## Final Verification Checklist

- [x] `ModeWorkbenchSpec` exists, is frozen, and contains no `QWidget` or runtime values.
- [x] Common panels mount existing widgets only.
- [x] `manual_box`, `mode_stack`, `tabs`, `ParameterTable`, and `ConstantsEditor` remain the only state owners for their domains.
- [x] Structural duplicate-state scan passes.
- [x] Result overview distinguishes no result, tabular result, plot-only result, text-only result, and failed result.
- [x] Formula preview uses the shared renderer, remains non-blocking, and hides the common formula panel in modes without formula inputs.
- [x] Workspace round-trip tests pass for moved or wrapped widgets.
- [x] Bilingual/schema/help gates pass.
- [x] Screenshot capture includes formula and variable panel metrics, with visibility asserted only when the active mode spec has corresponding content.
- [x] Full pytest passes before any packaging or release task starts.

## Self-Review Notes

- Spec coverage: every acceptance criterion in `docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md` maps to at least one task above.
- Placeholder scan: this plan avoids undefined implementation slots and gives concrete paths, snippets, commands, and expected outputs.
- Type consistency: descriptor names use string widget attributes only; panel adapters accept the existing `ExtrapolationWindow` object and do not introduce new persisted state.
