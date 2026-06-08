# DataLab High-Fidelity Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the shared high-fidelity DataLab workbench layer so formula preview, variable tables, result overview, and mode layout are unified without duplicating computation or workspace state.

**Architecture:** Build a descriptive `ModeWorkbenchSpec` registry and a set of adapter panels that mount existing widgets (`ParameterTable`, `ConstantsEditor`, formula editors, data editors, result tabs) instead of replacing them. The first slice strengthens invariants and result state, then introduces shared panel wrappers for formulas and variables, and only then applies the shared structure across modes. All user-facing labels/help continue to come from the existing schema/help/i18n pipeline.

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

- [ ] **Step 1: Write the failing descriptor tests**

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
        assert 0 <= spec.stack_index < window.mode_stack.count()
        for attr in spec.required_widget_attrs():
            assert hasattr(window, attr), f"{mode}: {attr}"
    assert sorted(spec.stack_index for spec in MODE_WORKBENCH_SPECS.values()) == list(range(window.mode_stack.count()))


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
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py
```

Expected before implementation:

```text
ModuleNotFoundError: No module named 'app_desktop.workbench_specs'
```

- [ ] **Step 2: Add the descriptor module**

Create `app_desktop/workbench_specs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
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
    companion_attrs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModeWorkbenchSpec:
    mode_key: ModeKey
    stack_index: int
    formulas: tuple[FormulaMount, ...] = field(default_factory=tuple)
    parameters: tuple[WidgetMount, ...] = field(default_factory=tuple)
    constants: tuple[WidgetMount, ...] = field(default_factory=tuple)
    tables: tuple[WidgetMount, ...] = field(default_factory=tuple)
    result_adapter_key: ResultAdapterKey = "tabular"

    def required_widget_attrs(self) -> tuple[str, ...]:
        attrs: list[str] = []
        for formula in self.formulas:
            attrs.extend((formula.editor_attr, formula.preview_button_attr))
        for mount in self.parameters + self.constants + self.tables:
            attrs.append(mount.widget_attr)
            attrs.extend(mount.companion_attrs)
        return tuple(dict.fromkeys(attrs))


MODE_WORKBENCH_SPECS: dict[ModeKey, ModeWorkbenchSpec] = {
    "extrapolation": ModeWorkbenchSpec(
        mode_key="extrapolation",
        stack_index=0,
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
        stack_index=1,
        formulas=(FormulaMount("formula_edit", "error_formula_preview_button", "error.formula"),),
        constants=(WidgetMount("error_constants_editor", "error.constants", "constants"),),
        result_adapter_key="tabular",
    ),
    "fitting": ModeWorkbenchSpec(
        mode_key="fitting",
        stack_index=2,
        formulas=(
            FormulaMount("fit_expr_edit", "fit_formula_preview_button", "fitting.custom.expression", lhs="y"),
            FormulaMount("implicit_equation_edit", "implicit_equation_preview_button", "fitting.implicit.equation"),
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
                companion_attrs=("custom_param_header_widget", "custom_constraints_checkbox"),
            ),
            WidgetMount(
                "implicit_params_table",
                "fitting.implicit.parameters",
                "parameters",
                companion_attrs=("implicit_param_header_widget", "implicit_constraints_checkbox"),
            ),
        ),
        constants=(
            WidgetMount("custom_constants_editor", "fitting.custom.constants", "constants"),
            WidgetMount("implicit_constants_editor", "fitting.implicit.constants", "constants"),
        ),
        result_adapter_key="tabular",
    ),
    "root_solving": ModeWorkbenchSpec(
        mode_key="root_solving",
        stack_index=3,
        formulas=(FormulaMount("root_equations_edit", "root_formula_preview_button", "root.equations", lhs="F"),),
        tables=(
            WidgetMount(
                "root_unknowns_table",
                "root.unknowns",
                "unknowns",
                companion_attrs=("root_unknown_header_widget",),
            ),
        ),
        constants=(WidgetMount("root_constants_editor", "root.constants", "constants"),),
        result_adapter_key="tabular",
    ),
    "statistics": ModeWorkbenchSpec(
        mode_key="statistics",
        stack_index=4,
        result_adapter_key="tabular",
    ),
}
```

- [ ] **Step 3: Wrap existing table-control headers and bind root preview schema**

Modify `app_desktop/panels.py` so descriptor companion attributes exist.

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

In `_bind_root_schema_fields()` after `bind_field(field=root_equations_field, ...)`, add:

```python
    self.root_formula_preview_button.setProperty("datalab_schema_key", root_equations_field.key)
    self.root_formula_preview_button.setProperty("datalab_schema_required", root_equations_field.required)
```

This binds the preview command to the same schema key without changing its preview-specific text or tooltip.

- [ ] **Step 4: Run descriptor tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_specs.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit Task 1**

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

- [ ] **Step 1: Write structural duplicate-state tests**

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
    assert isinstance(window.manual_data_edit, QPlainTextEdit)
    assert isinstance(window.mode_stack, QStackedWidget)
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_state_ownership.py
```

Expected before implementation:

```text
FAILED ... manual_data_owner
```

- [ ] **Step 2: Mark existing owners with structural roles**

Modify `app_desktop/panels.py` inside `build_ui()` after `_build_left_panel()` and before the final `_on_mode_change()` call:

```python
    self.manual_box.setProperty("datalab_state_role", "manual_data_owner")
    self.mode_stack.setProperty("datalab_state_role", "mode_stack_owner")
    self.tabs.setProperty("datalab_state_role", "result_tabs_owner")
    self.workbench_result_table.setProperty("datalab_state_role", "result_csv_projection")
```

Do not assign `manual_data_owner` to `manual_table` or `manual_data_edit`; they are child editors inside the real `manual_box` owner.

- [ ] **Step 3: Add scanner duplicate-role support**

Modify `tools/scan_desktop_gui_schema.py` by adding this helper near the existing issue helpers:

```python
def _duplicate_state_role_issues(window) -> list[dict[str, object]]:
    singleton_roles = {"manual_data_owner", "mode_stack_owner", "result_tabs_owner"}
    issues: list[dict[str, object]] = []
    for role in singleton_roles:
        widgets = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("datalab_state_role") == role
        ]
        if len(widgets) != 1:
            issues.append(
                {
                    "kind": "duplicate_state_role",
                    "role": role,
                    "count": len(widgets),
                    "widgets": [widget.objectName() for widget in widgets],
                }
            )
    return issues
```

Then include it where the scan report aggregates visual/schema issues:

```python
issues.extend(_duplicate_state_role_issues(window))
```

Ensure the module already imports `QWidget`; if it does not, add it to the existing `PySide6.QtWidgets` import list.

- [ ] **Step 4: Cover scanner duplicate-state output**

Modify `tests/test_desktop_gui_redesign_scan.py` by adding:

```python
def test_gui_scan_reports_duplicate_state_roles(qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QLabel
    from tools.scan_desktop_gui_schema import _duplicate_state_role_issues

    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    clone = QLabel("duplicate", window)
    clone.setObjectName("duplicated_manual_owner")
    clone.setProperty("datalab_state_role", "manual_data_owner")

    issues = _duplicate_state_role_issues(window)
    assert any(issue["kind"] == "duplicate_state_role" for issue in issues)
```

- [ ] **Step 5: Run structural gates**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_state_ownership.py tests/test_desktop_gui_redesign_scan.py
python tools/scan_desktop_gui_schema.py
```

Expected:

```text
passed
```

The scan report must still contain 240 scenarios with no issues.

- [ ] **Step 6: Commit Task 2**

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
- Modify: `app_desktop/window_fitting_residuals_mixin.py`
- Modify: `app_desktop/window_i18n_mixin.py`

- [ ] **Step 1: Add failing no-tabular and failed-state tests**

Append to `tests/test_desktop_workbench_results.py`:

```python
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


def test_result_rail_distinguishes_failed_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._mark_workbench_result_failed()

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py
```

Expected before implementation:

```text
FAILED ... 'No results'
```

- [ ] **Step 2: Add typed summary state**

Modify `app_desktop/workbench_results.py`:

```python
from dataclasses import dataclass
from typing import Literal

ResultOverviewKind = Literal["none", "running", "tabular", "plot", "text", "failed"]


@dataclass(frozen=True, slots=True)
class ResultOverviewState:
    kind: ResultOverviewKind
    rows: tuple[dict[str, object], ...] = ()
    headers: tuple[str, ...] = ()


def _overview_state(owner: Any) -> ResultOverviewState:
    rows = tuple(dict(row) for row in (getattr(owner, "_csv_rows", []) or []) if isinstance(row, dict))
    headers = tuple(str(header) for header in (getattr(owner, "_csv_headers", []) or []))
    if getattr(owner, "_workbench_result_state", "") == "failed":
        return ResultOverviewState("failed")
    if getattr(owner, "_workbench_result_state", "") == "running":
        return ResultOverviewState("running")
    if rows:
        return ResultOverviewState("tabular", rows=rows, headers=headers)
    if getattr(owner, "_result_plot_base_pixmap", None) is not None or getattr(owner, "result_plot_bytes", None):
        return ResultOverviewState("plot")
    rendered_text = str(getattr(owner, "_last_result_rendered_text", "") or "").strip()
    if rendered_text:
        return ResultOverviewState("text")
    return ResultOverviewState("none")
```

Then update `refresh_result_overview()` so it uses `_overview_state(owner)` and sets labels:

```python
    state = _overview_state(owner)
    rows = list(state.rows)
    headers = list(state.headers)
    ...
    if state.kind == "tabular":
        ...
    elif state.kind == "plot":
        owner.workbench_result_overview.setText(owner._tr("结果已生成；无表格数据", "Result ready; no tabular data"))
    elif state.kind == "text":
        owner.workbench_result_overview.setText(owner._tr("文本结果已生成；无表格数据", "Text result ready; no tabular data"))
    elif state.kind == "failed":
        owner.workbench_result_overview.setText(owner._tr("计算失败", "Calculation failed"))
    elif state.kind == "running":
        owner.workbench_result_overview.setText(owner._tr("计算中", "Running"))
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
```

Keep `workbench_result_table` as a projection table only. Do not add a second result model.

- [ ] **Step 3: Wire result state to real calculation paths**

Modify `app_desktop/window.py` near `_reset_csv_data()` and `_set_csv_data()`:

```python
    def _mark_workbench_result_running(self) -> None:
        self._workbench_result_state = "running"
        self._last_result_rendered_text = ""
        self.result_plot_bytes = None
        self._result_plot_base_pixmap = None
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()

    def _mark_workbench_result_failed(self) -> None:
        self._workbench_result_state = "failed"
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()

    def _clear_workbench_result_state(self) -> None:
        self._workbench_result_state = "none"
```

Inside `_reset_csv_data()` add before the result rail refresh:

```python
        if getattr(self, "_workbench_result_state", "none") != "running":
            self._clear_workbench_result_state()
```

Inside `_set_csv_data()` add before the result rail refresh:

```python
        self._clear_workbench_result_state()
```

Modify `app_desktop/window_extrapolation_mixin.py`:

```python
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

The existing bodies must remain intact after the new first line. Do not set the failed state in validation branches that never start a worker unless those branches also call the same failure callback.

- [ ] **Step 4: Refresh result overview after plot/image updates and workspace restore**

Modify `app_desktop/window_images_mixin.py` in `_update_result_plot()` after `_update_image_status()` in both success and empty-image branches:

```python
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
```

Modify `_set_image_list()` after the final `_update_image_status()` or `_show_image_at(...)` path completes:

```python
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

- [ ] **Step 5: Mark new runs as running before clearing old outputs**

Modify `app_desktop/window_extrapolation_mixin.py` in `run_calculation()` by replacing:

```python
        self._reset_csv_data()
```

with:

```python
        self._mark_workbench_result_running()
        self._reset_csv_data()
```

This prevents the overview from showing stale plot/text output from the previous run while the new run is preparing.

- [ ] **Step 6: Preserve language refresh**

Check `app_desktop/window_i18n_mixin.py`; it already calls `refresh_workbench_result_rail()` after language changes. Keep that call. Add no new localized strings outside `workbench_results.py`.

- [ ] **Step 7: Run result tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py tests/test_desktop_result_workflows.py tests/test_workspace_controller.py tests/test_desktop_gui_workflows.py
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add app_desktop/workbench_results.py tests/test_desktop_workbench_results.py tests/test_workspace_controller.py app_desktop/window.py app_desktop/window_extrapolation_mixin.py app_desktop/window_fitting_residuals_mixin.py app_desktop/window_images_mixin.py app_desktop/workspace_controller.py app_desktop/window_i18n_mixin.py
git commit -m "feat: distinguish workbench result overview states"
```

---

## Task 4: Remove Or Explicitly Guard Legacy Two-Pane Splitter Logic

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_desktop_workbench_layout.py`
- Modify: `tests/test_splitter_persistence.py`

- [ ] **Step 1: Add a regression test proving the three-pane contract**

Append to `tests/test_desktop_workbench_layout.py`:

```python
def test_splitter_refresh_requires_three_pane_workbench(qtbot: Any) -> None:
    window = _offscreen_window(qtbot)

    assert window._main_splitter.count() == 3
    window._refresh_main_splitter_left_min_width()

    assert window._main_splitter.count() == 3
    assert window._main_splitter_left_min_width >= window.workbench_config_rail.minimumWidth()
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py
```

Expected:

```text
passed
```

- [ ] **Step 2: Remove the legacy two-pane fallback**

Modify `app_desktop/panels.py` in `_refresh_main_splitter_left_min_width()` by deleting the branch that begins after the three-pane `return`:

```python
    left_container = getattr(self, "left_container", None)
    left_scroll = getattr(self, "_left_scroll", None)
    ...
    splitter.setSizes([left_min_width, right_width])
```

Replace it with a guarded early return:

```python
    return
```

This keeps `left_layout`, `left_container`, and `_left_scroll` as compatibility aliases while making the three-pane workbench the only active geometry contract.

- [ ] **Step 3: Run splitter persistence tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py tests/test_splitter_persistence.py
```

Expected:

```text
passed
```

- [ ] **Step 4: Commit Task 4**

Run:

```bash
git add app_desktop/panels.py tests/test_desktop_workbench_layout.py tests/test_splitter_persistence.py
git commit -m "refactor: enforce three-pane workbench splitter contract"
```

---

## Task 5: Add Shared Formula Workbench Panel Adapter

**Files:**
- Create: `app_desktop/workbench_formula_panel.py`
- Create: `tests/test_desktop_workbench_formula_panel.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/theme.py`

- [ ] **Step 1: Write failing formula panel tests**

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


def test_formula_workspace_preview_uses_current_editor_text(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_expr_edit.setPlainText("A*x+B")
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_preview_tracks_last_edited_implicit_formula(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    window.refresh_workbench_formula_panel()

    assert window.workbench_formula_preview_label._preview_expression == "u + x"
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_formula_panel.py
```

Expected before implementation:

```text
FAILED ... workbench_formula_panel
```

- [ ] **Step 2: Add the adapter module**

Create `app_desktop/workbench_formula_panel.py`:

```python
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app_desktop.formula_preview import FormulaPreviewLabel, update_formula_preview
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, FormulaMount


def build_formula_workspace_panel(owner: Any) -> QWidget:
    panel = QWidget()
    panel.setObjectName("workbench_formula_panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    owner.workbench_formula_panel_title = QLabel(owner._tr("公式预览", "Formula preview"))
    owner.workbench_formula_panel_title.setObjectName("workbench_formula_panel_title")
    layout.addWidget(owner.workbench_formula_panel_title)

    owner.workbench_formula_preview_label = FormulaPreviewLabel()
    owner.workbench_formula_preview_label.setObjectName("workbench_formula_preview_label")
    layout.addWidget(owner.workbench_formula_preview_label)

    owner._workbench_formula_refresh_timer = QTimer(owner)
    owner._workbench_formula_refresh_timer.setSingleShot(True)
    owner._workbench_formula_refresh_timer.setInterval(120)
    owner._workbench_formula_refresh_timer.timeout.connect(owner.refresh_workbench_formula_panel)
    return panel


def current_formula_mount(owner: Any) -> FormulaMount | None:
    mode = str(owner.mode_combo.currentData() or "fitting")
    spec = MODE_WORKBENCH_SPECS.get(mode)
    if spec is None:
        return None
    active_attr = getattr(owner, "_workbench_active_formula_attr", "")
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if mount.editor_attr == active_attr and editor is not None and editor.isVisible():
            return mount
    visible_mounts: list[FormulaMount] = []
    for mount in spec.formulas:
        editor = getattr(owner, mount.editor_attr, None)
        if editor is not None and editor.isVisible():
            visible_mounts.append(mount)
    if len(visible_mounts) == 1:
        return visible_mounts[0]
    return None


def refresh_formula_workspace_panel(owner: Any) -> None:
    label = getattr(owner, "workbench_formula_preview_label", None)
    if label is None:
        return
    title = getattr(owner, "workbench_formula_panel_title", None)
    if title is not None:
        title.setText(owner._tr("公式预览", "Formula preview"))
    mount = current_formula_mount(owner)
    if mount is None:
        label.clear()
        label.setText(owner._tr("当前模式没有公式输入。", "Current mode has no formula input."))
        return
    editor = getattr(owner, mount.editor_attr)
    text = editor.toPlainText().strip() if hasattr(editor, "toPlainText") else editor.text().strip()
    update_formula_preview(label, text, lhs=mount.lhs)


def schedule_formula_workspace_refresh(owner: Any, editor_attr: str | None = None) -> None:
    if editor_attr:
        owner._workbench_active_formula_attr = editor_attr
    timer = getattr(owner, "_workbench_formula_refresh_timer", None)
    if timer is not None:
        timer.start()
```

- [ ] **Step 3: Wire the panel into `panels.build_ui()`**

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
    for formula_attr in (
        "custom_formula_edit",
        "formula_edit",
        "fit_expr_edit",
        "implicit_equation_edit",
        "implicit_output_edit",
        "root_equations_edit",
    ):
        editor = getattr(self, formula_attr, None)
        if editor is not None and hasattr(editor, "textChanged"):
            editor.textChanged.connect(lambda _attr=formula_attr: schedule_formula_workspace_refresh(self, _attr))
```

Call `self.refresh_workbench_formula_panel()` after `_on_mode_change()` completes.

- [ ] **Step 4: Run formula tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py tests/test_formula_preview_rendering.py tests/test_desktop_workbench_editor_canvas.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add app_desktop/workbench_formula_panel.py app_desktop/panels.py app_desktop/theme.py tests/test_desktop_workbench_formula_panel.py
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

- [ ] **Step 1: Write failing variable panel tests**

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
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_variable_panel.py
```

Expected before implementation:

```text
FAILED ... workbench_variable_panel
```

- [ ] **Step 2: Add the variable adapter**

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
    pages = getattr(owner, "_workbench_variable_pages", {})
    for mode, spec in sorted(MODE_WORKBENCH_SPECS.items(), key=lambda item: item[1].stack_index):
        page = QWidget()
        page.setObjectName(f"workbench_variable_page_{mode}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for mount in spec.parameters + spec.tables + spec.constants:
            for attr in mount.companion_attrs + (mount.widget_attr,):
                widget = getattr(owner, attr, None)
                if widget is not None:
                    widget.setProperty("datalab_state_role", f"{mode}_{attr}_{mount.role}_owner")
                    reparent_widget(layout, widget)
        layout.addStretch(1)
        stack.insertWidget(spec.stack_index, page)
        pages[mode] = page


def refresh_variable_workspace_panel(owner: Any) -> None:
    stack = getattr(owner, "workbench_variable_stack", None)
    if stack is None:
        return
    title = getattr(owner, "workbench_variable_title", None)
    if title is not None:
        title.setText(owner._tr("参数与常数", "Parameters and constants"))
    mode = str(owner.mode_combo.currentData() or "fitting")
    pages = getattr(owner, "_workbench_variable_pages", {})
    page = pages.get(mode)
    if page is not None:
        stack.setCurrentWidget(page)
```

This task deliberately moves the existing parameter/constant widgets into the shared variable panel. Do not create a wrapper that leaves a second editable parameter or constants table in the original mode page. The source of truth remains the existing widget object, addressed by the same public attribute.

- [ ] **Step 3: Keep fitting submode visibility correct after reparenting**

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

Keep the existing custom visibility loop, and ensure it still includes `custom_param_header_widget`, `custom_params_table`, and `custom_constraints_checkbox`. Leave `custom_constants_editor.setVisible(mode == "custom")` in place.

- [ ] **Step 4: Wire and refresh the variable panel**

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

- [ ] **Step 5: Add a workspace round-trip smoke test**

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

- [ ] **Step 6: Run variable/workspace tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_variable_panel.py tests/test_parameter_table.py tests/test_constants_editor.py tests/test_workspace_controller.py
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit Task 6**

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
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_desktop_workbench_editor_canvas.py`
- Modify: `tests/test_desktop_gui_schema_scan.py`
- Modify: `tests/test_desktop_bilingual_inventory.py`

- [ ] **Step 1: Add a failing mode-refresh test**

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
```

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py
```

Expected before implementation if Task 6 has not wired `_on_mode_change()` fully:

```text
FAILED ... workbench_variable_page_root_solving
```

- [ ] **Step 2: Refresh common panels from mode changes**

Modify `app_desktop/window.py` in `_on_mode_change()` after the existing `mode_stack.setCurrentIndex(...)` block:

```python
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
```

- [ ] **Step 3: Refresh common panels from language changes**

Modify `app_desktop/window_i18n_mixin.py` after the existing result rail refresh:

```python
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
```

- [ ] **Step 4: Run bilingual and schema gates**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_bilingual_inventory.py
python tools/scan_desktop_gui_schema.py
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit Task 7**

Run:

```bash
git add app_desktop/window.py app_desktop/window_i18n_mixin.py app_desktop/panels.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_bilingual_inventory.py
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

- [ ] **Step 1: Update screenshot assertions for new common panels**

Modify `tests/test_desktop_workbench_visual_screenshots.py` to assert the screenshot manifest includes visible formula and variable panels:

```python
def test_screenshot_manifest_includes_common_workbench_panels(tmp_path) -> None:
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    manifest = capture_desktop_gui_screens(out=tmp_path, width=1440, height=900)

    assert manifest["screenshots"]
    for screenshot in manifest["screenshots"]:
        regions = screenshot["regions"]
        assert regions["workbench_formula_panel"]["visible"] is True
        assert regions["workbench_variable_panel"]["visible"] is True
```

If `capture_desktop_gui_screens()` currently records only the five shell regions, update `tools/capture_desktop_gui_screens.py` to include:

```python
from app_desktop.workbench_visual_contract import widget_metric
from dataclasses import asdict

for object_name in ("workbench_formula_panel", "workbench_variable_panel", "workbench_result_overview_panel"):
    regions[object_name] = asdict(widget_metric(window, object_name))
```

- [ ] **Step 2: Update user docs**

Update `docs/desktop/guide.en.md` and `docs/desktop/guide.zh.md` with concise sections that describe:

```markdown
### Shared workbench

The center workspace keeps the active data editor, formula preview, parameter table, and constants table together. Formula previews are display-only; calculation still uses the source expression in the editor.

### Result overview

The right rail summarizes the real result state. If a calculation produces plots or text without tabular rows, the overview reports that no tabular data is available instead of treating the run as missing.
```

Use Chinese text in `guide.zh.md` with the same meaning.

- [ ] **Step 3: Document the quality gate**

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

- [ ] **Step 4: Run the full quality gate**

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
scan report has 240 scenarios and 0 issues
screenshot capture writes 16 screenshots and 0 issues
full pytest passes with only existing documented skips/warnings
```

- [ ] **Step 5: Run external read-only reviews**

Run Claude:

```bash
CODEX_PLUGIN_ROOT=/Users/fanghao/.codex/plugins/cache/external-models-for-codex/claude-for-codex/0.14.2 \
node /Users/fanghao/.codex/plugins/cache/external-models-for-codex/claude-for-codex/0.14.2/scripts/claude-companion.mjs adversarial-review \
  --scope working-tree \
  --path app_desktop \
  --path tests \
  "Review the completed high-fidelity workbench implementation for duplicated GUI state, broken workspace restore, schema/i18n drift, and result overview correctness. Return PASS, CONTESTED, or REJECT."
```

Run Gemini through Antigravity:

```bash
CODEX_PLUGIN_ROOT=/Users/fanghao/.codex/plugins/cache/external-models-for-codex/antigravity-for-codex/0.1.0 \
ANTIGRAVITY_FOR_CODEX_MODEL="gemini-3.1-pro" \
node /Users/fanghao/.codex/plugins/cache/external-models-for-codex/antigravity-for-codex/0.1.0/scripts/antigravity-companion.mjs adversarial-review \
  --scope working-tree \
  "Review the completed DataLab high-fidelity workbench implementation against docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md and find GUI state duplication, brittle adapters, stale result states, and maintainability problems."
```

If a tool times out, returns empty output, or emits malformed output, record that in `progress.md` and continue only with the successful review evidence plus main-thread judgment.

- [ ] **Step 6: Commit Task 8**

Run:

```bash
git add docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md docs/desktop/guide.en.md docs/desktop/guide.zh.md docs/TEST_MATRIX.md tests/test_desktop_workbench_visual_screenshots.py tools/capture_desktop_gui_screens.py
git commit -m "docs: document high fidelity workbench quality gate"
```

---

## Final Verification Checklist

- [ ] `ModeWorkbenchSpec` exists, is frozen, and contains no `QWidget` or runtime values.
- [ ] Common panels mount existing widgets only.
- [ ] `manual_box`, `mode_stack`, `tabs`, `ParameterTable`, and `ConstantsEditor` remain the only state owners for their domains.
- [ ] Structural duplicate-state scan passes.
- [ ] Result overview distinguishes no result, tabular result, plot-only result, text-only result, and failed result.
- [ ] Formula preview uses the shared renderer and remains non-blocking.
- [ ] Workspace round-trip tests pass for moved or wrapped widgets.
- [ ] Bilingual/schema/help gates pass.
- [ ] Screenshot capture includes visible common formula and variable panels.
- [ ] Full pytest passes before any packaging or release task starts.

## Self-Review Notes

- Spec coverage: every acceptance criterion in `docs/superpowers/specs/2026-06-08-datalab-high-fidelity-workbench-design.md` maps to at least one task above.
- Placeholder scan: this plan avoids undefined implementation slots and gives concrete paths, snippets, commands, and expected outputs.
- Type consistency: descriptor names use string widget attributes only; panel adapters accept the existing `ExtrapolationWindow` object and do not introduce new persisted state.
