# DataLab Workbench Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the conservative desktop shell into the professional three-column scientific workbench shown in the approved sketch while preserving existing computation behavior, schema metadata, workspace compatibility, and release gates.

**Architecture:** This is a visual/layout migration, not an algorithm rewrite. Reuse the existing PySide6 widgets, schema bindings, `ConstantsEditor`, `ParameterTable`, `DetectedRowsTable`, formula preview, result tabs, and workspace controller; reparent them into a three-zone workbench with a modern toolbar, central data/formula workspace, and right result rail. Add failing structural and screenshot tests before changing layout, then migrate one region at a time with frequent commits.

**Tech Stack:** Python 3.13, PySide6, pytest/pytest-qt, existing `shared/ui_schema.py`, `shared/ui_specs.py`, `app_desktop` widgets, `tools/scan_desktop_gui_schema.py`, `tools/capture_desktop_gui_screens.py`, PyInstaller resource checks.

---

## Current Codebase Facts

- `app_desktop/shell_layout.py` currently builds a conservative text-button `workbench_bar` with New/Open/Save/Examples/Run/Stop/Docs/Updates and status labels.
- `app_desktop/panels.py` still constructs most visual layout. It creates the left scroll rail, mode boxes, options, run button, and right `QTabWidget` result area.
- `app_desktop/section_panel.py`, `app_desktop/schema_widgets.py`, and `app_desktop/theme.py` already provide reusable section/header/theme primitives; extend these instead of introducing duplicated styling.
- `tools/scan_desktop_gui_schema.py` already scans 270 zh/en/mode/submode/result-tab scenarios, including fitting `custom` and `self_consistent`, and asserts no left horizontal scrollbar.
- `tools/capture_desktop_gui_screens.py` already generates deterministic zh/en screenshots for visual review.
- Current GUI tests verify widget attributes, schema keys, bilingual tooltips, result tabs, workspace restore, and packaging resources. New visual layout tests must preserve those contracts.

## Visual Target

Implement the approved sketch as a desktop scientific workbench:

- Top toolbar: app identity, workspace breadcrumb, icon+label actions, run split button, job/status indicators, docs/help/settings/menu.
- Left configuration rail: compact sections for calculation mode, data source, and output settings. It should not contain the full formula/table workload.
- Center workspace canvas: real data editor on top and the existing mode editor stack below it; mode-specific parameter and constant tables stay inside their current editors so schema binding, workspace restore, and validation remain single-source-of-truth.
- Right result rail: result tabs, deterministic result overview/status, export action, and compact result data table.
- Bottom status strip: ready state plus lightweight resource/job state. Do not invent fake telemetry; show only data the app already has or deterministic placeholders such as idle/ready.

## Non-Goals

- Do not change numerical algorithms, fitting/root-solving backends, precision behavior, worker isolation, updater behavior, or workspace file format semantics.
- Do not replace `ConstantsEditor`, `ParameterTable`, `DetectedRowsTable`, result formatters, expression parser, or formula preview renderer.
- Do not introduce a second schema/help registry or duplicated user-facing text.
- Do not build a marketing/landing page style UI. This remains a dense scientific desktop application.
- Do not expose fake data in the running app. Placeholder/demo content is allowed only in tests or screenshot fixture setup.

## File Structure Plan

- Create `app_desktop/workbench_visual_contract.py`: shared object names, minimum widths, region roles, and screenshot metric helpers used by tests and capture tools.
- Create `app_desktop/workbench_toolbar.py`: modern icon+label toolbar builder that preserves legacy public attributes such as `new_workspace_button` and `workbench_run_button`.
- Create `app_desktop/workbench_layout.py`: three-zone splitter/page shell builder and reparenting helpers.
- Move the existing input section into the center workspace: the real `manual_table`, `manual_data_edit`, file controls, paste handling, row/column actions, and workspace restore remain single-source-of-truth widgets.
- Create `app_desktop/workbench_results.py`: right result rail overview/status/result-table adapters using existing result snapshot and CSV state.
- Modify `app_desktop/theme.py`: add workbench palette, spacing, region widths, toolbar/button/table styles.
- Modify `app_desktop/shell_layout.py`: keep compatibility exports while delegating toolbar construction to `workbench_toolbar.py`.
- Modify `app_desktop/panels.py`: call new workbench builders and preserve existing public widget attributes.
- Modify `app_desktop/window.py` and mixins only for status/preview refresh hooks, never for visual-only fake data.
- Modify `tools/scan_desktop_gui_schema.py` and `tools/capture_desktop_gui_screens.py`: include workbench region metrics and structural visual issues.
- Create/modify tests under `tests/test_desktop_workbench_visual_contract.py`, `tests/test_desktop_workbench_toolbar.py`, `tests/test_desktop_workbench_layout.py`, `tests/test_desktop_workbench_results.py`, and existing GUI scan/screenshot tests.
- Update `docs/desktop/guide.en.md`, `docs/desktop/guide.zh.md`, and `docs/TEST_MATRIX.md` after tests and implementation pass.

---

## Task 1: Add Workbench Visual Contract Tests Before Layout Changes

**Files:**
- Create: `app_desktop/workbench_visual_contract.py`
- Create: `tests/test_desktop_workbench_visual_contract.py`

- [ ] **Step 1: Create the visual contract module**

Create `app_desktop/workbench_visual_contract.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

TOOLBAR_OBJECT = "workbench_toolbar"
CONFIG_RAIL_OBJECT = "workbench_config_rail"
WORKSPACE_CANVAS_OBJECT = "workbench_workspace_canvas"
RESULT_RAIL_OBJECT = "workbench_result_rail"
STATUS_STRIP_OBJECT = "workbench_status_strip"

SUPPORTED_VISUAL_WIDTH = 1440
SUPPORTED_VISUAL_HEIGHT = 900
CONFIG_RAIL_MIN_WIDTH = 320
CONFIG_RAIL_DEFAULT_WIDTH = 320
RESULT_RAIL_MIN_WIDTH = 320
RESULT_RAIL_DEFAULT_WIDTH = 380
WORKSPACE_CANVAS_MIN_WIDTH = 520


@dataclass(frozen=True)
class WorkbenchRegionMetric:
    object_name: str
    x: int
    y: int
    width: int
    height: int
    visible: bool


def widget_metric(root: QWidget, object_name: str) -> WorkbenchRegionMetric:
    widget = root.findChild(QWidget, object_name)
    if widget is None:
        return WorkbenchRegionMetric(object_name, 0, 0, 0, 0, False)
    geometry = widget.geometry()
    top_left = widget.mapTo(root, QPoint(0, 0))
    return WorkbenchRegionMetric(
        object_name=object_name,
        x=int(top_left.x()),
        y=int(top_left.y()),
        width=int(geometry.width()),
        height=int(geometry.height()),
        visible=bool(widget.isVisible()),
    )


def workbench_region_metrics(root: QWidget) -> dict[str, WorkbenchRegionMetric]:
    return {
        name: widget_metric(root, name)
        for name in (
            TOOLBAR_OBJECT,
            CONFIG_RAIL_OBJECT,
            WORKSPACE_CANVAS_OBJECT,
            RESULT_RAIL_OBJECT,
            STATUS_STRIP_OBJECT,
        )
    }


def visual_contract_issues(root: QWidget) -> list[dict[str, object]]:
    metrics = workbench_region_metrics(root)
    issues: list[dict[str, object]] = []
    for name, metric in metrics.items():
        if not metric.visible or metric.width <= 0 or metric.height <= 0:
            issues.append({"kind": "missing_workbench_region", "widget": name})

    config = metrics[CONFIG_RAIL_OBJECT]
    workspace = metrics[WORKSPACE_CANVAS_OBJECT]
    result = metrics[RESULT_RAIL_OBJECT]
    if config.visible and config.width < CONFIG_RAIL_MIN_WIDTH:
        issues.append({"kind": "config_rail_width", "widget": CONFIG_RAIL_OBJECT, "width": config.width})
    if workspace.visible and workspace.width < WORKSPACE_CANVAS_MIN_WIDTH:
        issues.append({"kind": "workspace_canvas_width", "widget": WORKSPACE_CANVAS_OBJECT, "width": workspace.width})
    if result.visible and result.width < RESULT_RAIL_MIN_WIDTH:
        issues.append({"kind": "result_rail_width", "widget": RESULT_RAIL_OBJECT, "width": result.width})
    if config.visible and workspace.visible and result.visible:
        if not (config.x < workspace.x < result.x):
            issues.append(
                {
                    "kind": "region_order",
                    "widget": "workbench",
                    "positions": {"config": config.x, "workspace": workspace.x, "result": result.x},
                }
            )
    return issues
```

- [ ] **Step 2: Write the failing visual contract test**

Create `tests/test_desktop_workbench_visual_contract.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_OBJECT,
    STATUS_STRIP_OBJECT,
    TOOLBAR_OBJECT,
    WORKSPACE_CANVAS_OBJECT,
    SUPPORTED_VISUAL_HEIGHT,
    SUPPORTED_VISUAL_WIDTH,
    visual_contract_issues,
    workbench_region_metrics,
)


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(SUPPORTED_VISUAL_WIDTH, SUPPORTED_VISUAL_HEIGHT)
    window.show()
    QApplication.processEvents()
    return window


def test_workbench_exposes_three_column_visual_regions(qtbot: Any) -> None:
    window = _window(qtbot)

    metrics = workbench_region_metrics(window)

    for name in (
        TOOLBAR_OBJECT,
        CONFIG_RAIL_OBJECT,
        WORKSPACE_CANVAS_OBJECT,
        RESULT_RAIL_OBJECT,
        STATUS_STRIP_OBJECT,
    ):
        assert metrics[name].visible is True, name
    assert visual_contract_issues(window) == []


def test_workbench_keeps_legacy_public_widget_attributes(qtbot: Any) -> None:
    window = _window(qtbot)

    for name in (
        "manual_table",
        "mode_combo",
        "fit_expr_edit",
        "custom_params_table",
        "custom_constants_editor",
        "root_equations_edit",
        "result_tabs",
        "result_edit",
        "latex_edit",
        "run_button",
        "workbench_run_button",
    ):
        assert getattr(window, name, None) is not None, name
```

- [ ] **Step 3: Run the test and verify it fails before implementation**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py
```

Expected before implementation:

```text
FAILED ... AssertionError: workbench_toolbar
```

- [ ] **Step 4: Commit the failing visual contract gate**

Run:

```bash
git add app_desktop/workbench_visual_contract.py tests/test_desktop_workbench_visual_contract.py
git commit -m "test: add desktop workbench visual contract"
```

---

## Task 2: Add Workbench Theme Tokens and Region Styles

**Files:**
- Modify: `app_desktop/theme.py`
- Create: `tests/test_desktop_workbench_theme.py`

- [ ] **Step 1: Write theme token tests**

Create `tests/test_desktop_workbench_theme.py`:

```python
from __future__ import annotations


def test_workbench_region_width_tokens_match_visual_contract() -> None:
    from app_desktop.theme import (
        CONFIG_RAIL_WIDTH,
        RESULT_RAIL_WIDTH,
        STATUS_STRIP_HEIGHT,
        TOOLBAR_HEIGHT,
        WORKSPACE_GUTTER,
    )

    assert 260 <= CONFIG_RAIL_WIDTH <= 340
    assert 320 <= RESULT_RAIL_WIDTH <= 440
    assert 44 <= TOOLBAR_HEIGHT <= 64
    assert 22 <= STATUS_STRIP_HEIGHT <= 32
    assert 8 <= WORKSPACE_GUTTER <= 16


def test_workbench_styles_expose_named_regions() -> None:
    from app_desktop.theme import workbench_region_style, workbench_toolbar_style

    toolbar = workbench_toolbar_style(dark=False)
    region = workbench_region_style(dark=False)

    assert "QFrame#workbench_toolbar" in toolbar
    assert "QScrollArea#workbench_config_rail" in region
    assert "QScrollArea#workbench_workspace_canvas" in region
    assert "QFrame#workbench_result_rail" in region
```

- [ ] **Step 2: Run the failing theme tests**

Run:

```bash
pytest -q tests/test_desktop_workbench_theme.py
```

Expected before implementation:

```text
ImportError: cannot import name 'CONFIG_RAIL_WIDTH'
```

- [ ] **Step 3: Add theme constants and styles**

Modify `app_desktop/theme.py` by adding these constants after the existing width constants:

```python
TOOLBAR_HEIGHT = 54
STATUS_STRIP_HEIGHT = 26
CONFIG_RAIL_WIDTH = 320
RESULT_RAIL_WIDTH = 380
WORKSPACE_GUTTER = 12
REGION_RADIUS = 8
```

Add these functions:

```python
def workbench_toolbar_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    border = "rgba(255, 255, 255, 0.10)" if dark else "rgba(31, 35, 40, 0.12)"
    bg = "#20242b" if dark else "#f8fafc"
    fg = "#e5e7eb" if dark else "#1f2328"
    hover = "#2b313a" if dark else "#eef2f7"
    active = "#2563eb" if dark else "#2563eb"
    return f"""
QFrame#workbench_toolbar {{
    background: {bg};
    border-bottom: 1px solid {border};
}}
QFrame#workbench_toolbar QLabel {{
    color: {fg};
}}
QFrame#workbench_toolbar QToolButton,
QFrame#workbench_toolbar QPushButton {{
    min-height: 34px;
    padding: 4px 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {fg};
}}
QFrame#workbench_toolbar QToolButton:hover,
QFrame#workbench_toolbar QPushButton:hover {{
    background: {hover};
    border-color: {border};
}}
QFrame#workbench_toolbar QToolButton#workbench_run_button {{
    color: #ffffff;
    background: {active};
    border-color: {active};
}}
"""


def workbench_region_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    app_bg = "#181a1f" if dark else "#f3f5f7"
    panel_bg = "#20242b" if dark else "#ffffff"
    border = "rgba(255, 255, 255, 0.10)" if dark else "#d8dee8"
    fg = "#e5e7eb" if dark else "#1f2328"
    return f"""
QWidget#workbench_root {{
    background: {app_bg};
}}
QScrollArea#workbench_config_rail,
QScrollArea#workbench_workspace_canvas,
QFrame#workbench_result_rail {{
    background: {panel_bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QFrame#workbench_status_strip {{
    background: {app_bg};
    color: {fg};
    border-top: 1px solid {border};
}}
"""
```

- [ ] **Step 4: Run theme tests**

Run:

```bash
pytest -q tests/test_desktop_workbench_theme.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add app_desktop/theme.py tests/test_desktop_workbench_theme.py
git commit -m "style: add workbench visual theme tokens"
```

---

## Task 3: Replace Text Workbench Bar With Modern Icon Toolbar

**Files:**
- Create: `app_desktop/workbench_toolbar.py`
- Modify: `app_desktop/shell_layout.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_desktop_workbench_toolbar.py`

- [ ] **Step 1: Write toolbar tests**

Create `tests/test_desktop_workbench_toolbar.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QToolButton


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_toolbar_uses_icon_actions_and_preserves_public_attributes(qtbot: Any) -> None:
    window = _window(qtbot)

    toolbar = window.findChild(QFrame, "workbench_toolbar")
    assert toolbar is not None
    assert toolbar.height() >= 44

    for name in (
        "new_workspace_button",
        "open_workspace_button",
        "save_workspace_button",
        "open_examples_button",
        "workbench_run_button",
        "workbench_stop_button",
        "docs_button",
        "check_updates_button",
    ):
        button = getattr(window, name, None)
        assert isinstance(button, QToolButton), name
        assert not button.icon().isNull(), name
        assert button.toolTip(), name
        assert button.accessibleDescription(), name


def test_toolbar_language_switch_keeps_actions(qtbot: Any) -> None:
    window = _window(qtbot)

    window._apply_language("en")
    assert window.new_workspace_button.text() == "New"
    assert window.workbench_run_button.text() == "Run"

    window._apply_language("zh")
    assert window.new_workspace_button.text() == "新建"
    assert window.workbench_run_button.text() == "运行"
```

- [ ] **Step 2: Run toolbar tests and verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_toolbar.py
```

Expected before implementation:

```text
AssertionError: expected QToolButton
```

- [ ] **Step 3: Create the toolbar builder and move shared action helpers**

Create `app_desktop/workbench_toolbar.py`. Move the existing `_OwnerProtocol`, `_translate`, `_call_owner`, and `_dynamic_owner` helper logic from `app_desktop/shell_layout.py` into this module so the helper logic has one owner:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QStyle, QToolButton, QWidget

from app_desktop.theme import TOOLBAR_HEIGHT, workbench_toolbar_style
from app_desktop.workbench_visual_contract import TOOLBAR_OBJECT


class _OwnerProtocol(Protocol):
    def _register_text(self, widget: object, zh: str, en: str, attr: str = "setText") -> None: ...

    def _tr(self, zh: str, en: str) -> str: ...

    def style(self) -> QStyle: ...


def _translate(owner: object, zh: str, en: str) -> str:
    translate = getattr(owner, "_tr", None)
    if callable(translate):
        return cast(_OwnerProtocol, owner)._tr(zh, en)
    return zh


def _dynamic_owner(owner: object) -> Any:
    return cast(Any, owner)


def _call_owner(owner: object, *method_names: str) -> Callable[[bool], None]:
    def _slot(_checked: bool = False) -> None:
        for method_name in method_names:
            method = getattr(owner, method_name, None)
            if callable(method):
                try:
                    method(_checked)
                except TypeError:
                    method()
                return

    return _slot


def _icon(owner: object, standard_pixmap: QStyle.StandardPixmap):
    return cast(_OwnerProtocol, owner).style().standardIcon(standard_pixmap)


def make_toolbar_button(
    owner: object,
    *,
    object_name: str,
    text_zh: str,
    text_en: str,
    tooltip_zh: str,
    tooltip_en: str,
    icon: QStyle.StandardPixmap,
    methods: tuple[str, ...],
) -> QToolButton:
    button = QToolButton()
    button.setObjectName(object_name)
    button.setText(_translate(owner, text_zh, text_en))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setIcon(_icon(owner, icon))
    button.setIconSize(QSize(20, 20))
    button.setAutoRaise(True)
    button.setToolTip(_translate(owner, tooltip_zh, tooltip_en))
    button.setAccessibleName(_translate(owner, text_zh, text_en))
    button.setAccessibleDescription(_translate(owner, tooltip_zh, tooltip_en))
    button.clicked.connect(_call_owner(owner, *methods))

    register = getattr(owner, "_register_text", None)
    if callable(register):
        typed = cast(_OwnerProtocol, owner)
        typed._register_text(button, text_zh, text_en)
        typed._register_text(button, text_zh, text_en, "setAccessibleName")
        typed._register_text(button, tooltip_zh, tooltip_en, "setToolTip")
        typed._register_text(button, tooltip_zh, tooltip_en, "setAccessibleDescription")
    return button


def build_workbench_toolbar(owner: object) -> QWidget:
    dynamic_owner = cast(Any, owner)
    toolbar = QFrame()
    toolbar.setObjectName(TOOLBAR_OBJECT)
    toolbar.setMinimumHeight(TOOLBAR_HEIGHT)
    toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    toolbar.setStyleSheet(workbench_toolbar_style())

    layout = QHBoxLayout(toolbar)
    layout.setContentsMargins(12, 6, 12, 6)
    layout.setSpacing(10)

    dynamic_owner.app_identity_label = QLabel("DataLab")
    dynamic_owner.app_identity_label.setObjectName("app_identity_label")
    layout.addWidget(dynamic_owner.app_identity_label)
    layout.addSpacing(16)

    specs = [
        ("new_workspace_button", "新建", "New", "新建空白工作区。", "Create a blank workspace.", QStyle.StandardPixmap.SP_FileIcon, ("new_workspace",)),
        ("open_workspace_button", "打开", "Open", "打开已有 .datalab 工作区。", "Open an existing .datalab workspace.", QStyle.StandardPixmap.SP_DirOpenIcon, ("open_workspace",)),
        ("save_workspace_button", "保存", "Save", "保存当前工作区；示例模板会要求另存为。", "Save the current workspace; example templates require Save As.", QStyle.StandardPixmap.SP_DialogSaveButton, ("save_workspace",)),
        ("open_examples_button", "示例", "Examples", "打开内置示例工作区作为只读模板。", "Open a bundled example workspace as a read-only template.", QStyle.StandardPixmap.SP_FileDialogListView, ("open_example_workspace",)),
        ("workbench_run_button", "运行", "Run", "运行当前配置的计算。", "Run the calculation with the current configuration.", QStyle.StandardPixmap.SP_MediaPlay, ("run_extrapolation", "run_calculation")),
        ("workbench_stop_button", "停止", "Stop", "停止正在运行的计算。", "Stop the running calculation.", QStyle.StandardPixmap.SP_MediaStop, ("stop_calculation", "_stop_current_worker")),
    ]
    for object_name, zh, en, tooltip_zh, tooltip_en, icon, methods in specs:
        button = make_toolbar_button(
            owner,
            object_name=object_name,
            text_zh=zh,
            text_en=en,
            tooltip_zh=tooltip_zh,
            tooltip_en=tooltip_en,
            icon=icon,
            methods=methods,
        )
        setattr(dynamic_owner, object_name, button)
        layout.addWidget(button)

    layout.addStretch(1)
    dynamic_owner.job_status_label = QLabel()
    dynamic_owner.job_status_label.setObjectName("job_status_label")
    dynamic_owner.workspace_status_label = QLabel()
    dynamic_owner.workspace_status_label.setObjectName("workspace_status_label")
    layout.addWidget(dynamic_owner.job_status_label)
    layout.addWidget(dynamic_owner.workspace_status_label)

    for object_name, zh, en, tooltip_zh, tooltip_en, icon, methods in (
        ("docs_button", "文档", "Docs", "打开离线桌面帮助文档。", "Open the offline desktop documentation.", QStyle.StandardPixmap.SP_MessageBoxQuestion, ("_open_docs", "_show_docs")),
        ("check_updates_button", "更新", "Updates", "检查 GitHub 发布页上的新版本。", "Check GitHub releases for a newer version.", QStyle.StandardPixmap.SP_BrowserReload, ("check_for_updates", "_check_for_updates")),
    ):
        button = make_toolbar_button(
            owner,
            object_name=object_name,
            text_zh=zh,
            text_en=en,
            tooltip_zh=tooltip_zh,
            tooltip_en=tooltip_en,
            icon=icon,
            methods=methods,
        )
        setattr(dynamic_owner, object_name, button)
        layout.addWidget(button)

    return toolbar
```

- [ ] **Step 4: Delegate shell layout to the toolbar builder**

Modify `app_desktop/shell_layout.py`:

```python
from app_desktop.workbench_toolbar import _dynamic_owner, _translate, build_workbench_toolbar


def build_workbench_bar(owner: object) -> QWidget:
    bar = build_workbench_toolbar(owner)
    dynamic_owner = _dynamic_owner(owner)
    dynamic_owner.workbench_bar = bar
    update_workbench_status(owner)
    return bar
```

Remove the old local copies of `_OwnerProtocol`, `_translate`, `_call_owner`, and `_button` from `shell_layout.py`; `_translate` is imported from `workbench_toolbar.py` for the retained status functions. Keep `update_workbench_status()` and `set_workbench_job_status()` in `shell_layout.py` so existing window calls keep working.

- [ ] **Step 5: Apply toolbar style during theme refresh**

Modify `app_desktop/window.py::_apply_desktop_theme()` so toolbar styling refreshes with palette changes. Add this block after the existing application stylesheet refresh:

```python
if hasattr(self, "workbench_bar"):
    self.workbench_bar.setStyleSheet(workbench_toolbar_style())
```

and import:

```python
from app_desktop.theme import workbench_toolbar_style
```

- [ ] **Step 6: Run toolbar and existing shell tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_toolbar.py tests/test_desktop_shell_layout.py tests/test_desktop_examples_entrypoint.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app_desktop/workbench_toolbar.py app_desktop/shell_layout.py app_desktop/window.py tests/test_desktop_workbench_toolbar.py
git commit -m "style: modernize desktop workbench toolbar"
```

---

## Task 4: Build the Three-Zone Workbench Shell

**Files:**
- Create: `app_desktop/workbench_layout.py`
- Modify: `app_desktop/panels.py`
- Create: `tests/test_desktop_workbench_layout.py`
- Modify: `tests/test_splitter_persistence.py`
- Modify: `tests/test_desktop_root_solving_ui.py`
- Modify: `tests/test_desktop_mode_stack.py`
- Modify: `tests/test_parallel_preferences.py`
- Modify: `tests/test_formula_preview_dialog.py`

- [ ] **Step 1: Write layout tests**

Create `tests/test_desktop_workbench_layout.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QSplitter, QWidget

from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_OBJECT,
    RESULT_RAIL_OBJECT,
    WORKSPACE_CANVAS_OBJECT,
    visual_contract_issues,
)


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_main_area_uses_config_workspace_result_regions(qtbot: Any) -> None:
    window = _window(qtbot)

    splitter = window.findChild(QSplitter, "workbench_main_splitter")
    assert splitter is not None
    assert splitter.count() == 3
    assert isinstance(window.findChild(QScrollArea, CONFIG_RAIL_OBJECT), QScrollArea)
    assert isinstance(window.findChild(QScrollArea, WORKSPACE_CANVAS_OBJECT), QScrollArea)
    assert isinstance(window.findChild(QFrame, RESULT_RAIL_OBJECT), QFrame)
    assert visual_contract_issues(window) == []


def test_splitter_cannot_hide_config_or_result_regions(qtbot: Any) -> None:
    window = _window(qtbot)
    splitter = window.findChild(QSplitter, "workbench_main_splitter")
    assert splitter is not None

    splitter.setSizes([1, 1438, 1])
    QApplication.processEvents()

    sizes = splitter.sizes()
    assert sizes[0] >= 260
    assert sizes[1] >= 520
    assert sizes[2] >= 320


def test_status_strip_owns_workspace_and_job_status(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.workspace_status_label.parentWidget() is window.workbench_status_strip
    assert window.job_status_label.parentWidget() is window.workbench_status_strip
    assert window.workspace_status_label.text() in {"已保存", "未保存", "Saved", "Unsaved"}
    assert window.job_status_label.text() in {"就绪", "运行中", "Ready", "Running"}


def test_status_strip_tracks_dirty_and_running_state(qtbot: Any) -> None:
    window = _window(qtbot)

    window._mark_workspace_dirty()
    assert window.workspace_status_label.text() in {"未保存", "Unsaved"}
    window._set_button_to_stop_mode()
    assert window.job_status_label.text() in {"运行中", "Running"}
    window._set_button_to_run_mode()
    assert window.job_status_label.text() in {"就绪", "Ready"}
```

- [ ] **Step 2: Run layout tests and verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py
```

Expected before implementation:

```text
AssertionError: splitter is None
```

- [ ] **Step 3: Create three-zone layout helpers**

Create `app_desktop/workbench_layout.py`:

```python
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QScrollArea, QSplitter, QVBoxLayout, QWidget

from app_desktop.theme import (
    CONFIG_RAIL_WIDTH,
    RESULT_RAIL_WIDTH,
    STATUS_STRIP_HEIGHT,
    WORKSPACE_GUTTER,
    workbench_region_style,
)
from app_desktop.workbench_visual_contract import (
    CONFIG_RAIL_OBJECT,
    CONFIG_RAIL_MIN_WIDTH,
    RESULT_RAIL_OBJECT,
    RESULT_RAIL_MIN_WIDTH,
    STATUS_STRIP_OBJECT,
    WORKSPACE_CANVAS_MIN_WIDTH,
    WORKSPACE_CANVAS_OBJECT,
)


def _frame(object_name: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setStyleSheet(workbench_region_style())
    return frame


def _scroll_wrapper(
    object_name: str,
    content: QWidget,
    horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    content.setObjectName(f"{object_name}_content")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(horizontal_policy)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(content)
    return scroll


def scroll_viewport_overhead(scroll: QScrollArea) -> int:
    return (
        scroll.frameWidth() * 2
        + scroll.verticalScrollBar().sizeHint().width()
    )


def make_config_rail() -> tuple[QFrame, QVBoxLayout, QScrollArea]:
    frame = _frame(CONFIG_RAIL_OBJECT)
    frame.setMinimumWidth(CONFIG_RAIL_MIN_WIDTH)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll = _scroll_wrapper(CONFIG_RAIL_OBJECT, frame)
    scroll.setMinimumWidth(CONFIG_RAIL_MIN_WIDTH + scroll_viewport_overhead(scroll))
    return frame, layout, scroll


def make_workspace_canvas() -> tuple[QFrame, QVBoxLayout, QScrollArea]:
    frame = _frame(WORKSPACE_CANVAS_OBJECT)
    frame.setMinimumWidth(WORKSPACE_CANVAS_MIN_WIDTH)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER, WORKSPACE_GUTTER)
    layout.setSpacing(WORKSPACE_GUTTER)
    scroll = _scroll_wrapper(
        WORKSPACE_CANVAS_OBJECT,
        frame,
        horizontal_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    )
    scroll.setMinimumWidth(WORKSPACE_CANVAS_MIN_WIDTH)
    return frame, layout, scroll


def make_result_rail() -> tuple[QFrame, QVBoxLayout]:
    frame = _frame(RESULT_RAIL_OBJECT)
    frame.setMinimumWidth(RESULT_RAIL_MIN_WIDTH)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)
    return frame, layout


def make_status_strip(owner: Any) -> tuple[QFrame, QHBoxLayout]:
    frame = _frame(STATUS_STRIP_OBJECT)
    frame.setMinimumHeight(STATUS_STRIP_HEIGHT)
    frame.setMaximumHeight(STATUS_STRIP_HEIGHT)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 2, 10, 2)
    layout.setSpacing(12)
    owner.job_status_label.setParent(None)
    owner.workspace_status_label.setParent(None)
    layout.addWidget(owner.job_status_label)
    layout.addStretch(1)
    layout.addWidget(owner.workspace_status_label)
    return frame, layout


def build_workbench_main_splitter(owner: Any) -> QSplitter:
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setObjectName("workbench_main_splitter")
    splitter.setChildrenCollapsible(False)

    owner.workbench_config_content, owner.workbench_config_layout, owner.workbench_config_rail = make_config_rail()
    owner.workbench_workspace_content, owner.workbench_workspace_layout, owner.workbench_workspace_canvas = make_workspace_canvas()
    owner.workbench_result_rail, owner.workbench_result_layout = make_result_rail()

    splitter.addWidget(owner.workbench_config_rail)
    splitter.addWidget(owner.workbench_workspace_canvas)
    splitter.addWidget(owner.workbench_result_rail)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setStretchFactor(2, 0)
    available = max(
        int(getattr(owner, "width", lambda: 0)()),
        CONFIG_RAIL_WIDTH + WORKSPACE_CANVAS_MIN_WIDTH + RESULT_RAIL_WIDTH,
    )
    splitter.setSizes([CONFIG_RAIL_WIDTH, available - CONFIG_RAIL_WIDTH - RESULT_RAIL_WIDTH, RESULT_RAIL_WIDTH])
    return splitter


def reparent_widget(layout: QVBoxLayout, widget: QWidget, stretch: int = 0) -> None:
    widget.setParent(None)
    layout.addWidget(widget, stretch)
```

- [ ] **Step 4: Wire the new shell in `panels.py`**

Modify `build_ui()` in `app_desktop/panels.py`. Replace the block that starts with `self.workbench_bar = build_workbench_bar(self)` and ends immediately before `self._build_left_panel()` with:

```python
from app_desktop.workbench_layout import build_workbench_main_splitter, make_status_strip
from app_desktop.shell_layout import update_workbench_status

self.workbench_root = QWidget()
self.workbench_root.setObjectName("workbench_root")
root_layout = QVBoxLayout(self.workbench_root)
root_layout.setContentsMargins(0, 0, 0, 0)
root_layout.setSpacing(0)
layout.setContentsMargins(0, 0, 0, 0)
self.workbench_bar = build_workbench_bar(self)
root_layout.addWidget(self.workbench_bar)
self._main_splitter = build_workbench_main_splitter(self)
root_layout.addWidget(self._main_splitter, 1)
self.workbench_status_strip, self.workbench_status_layout = make_status_strip(self)
update_workbench_status(self)
root_layout.addWidget(self.workbench_status_strip)
layout.addWidget(self.workbench_root)
```

Then route existing section construction:

```python
self.left_layout = self.workbench_config_layout
self.left_container = self.workbench_config_content
```

Keep `self._left_scroll` as a compatibility alias to the real config scroll area because `window.closeEvent()` and older tests still probe legacy left-panel state:

```python
self._left_scroll = self.workbench_config_rail
```

Replace the surviving right-panel call:

```python
self._build_right_panel(right_layout)
```

with:

```python
self._build_right_panel(self.workbench_result_layout)
```

Update the QSettings splitter-restore block later in `build_ui()` so it uses `self._main_splitter` instead of the removed local `splitter`, and so it accepts three-pane splitter blobs:

```python
splitter = self._main_splitter
pre_restore_sizes = splitter.sizes()
pre_restore_count = splitter.count()
expected_count = pre_restore_count
blob_count = extract_splitter_pane_count(bytes(blob))
if blob_count is not None and blob_count != expected_count:
    settings.save_bytes(KEY_MAIN_SPLITTER_STATE, None)
else:
    restored_ok = splitter.restoreState(blob)
    sizes_after = splitter.sizes()
    if (
        restored_ok
        and len(sizes_after) == splitter.count()
        and all(s >= 0 for s in sizes_after)
        and sum(sizes_after) > 0
    ):
        self._refresh_main_splitter_left_min_width()
    else:
        splitter.setSizes(pre_restore_sizes)
        settings.save_bytes(KEY_MAIN_SPLITTER_STATE, None)
```

Add a focused assertion to `tests/test_splitter_persistence.py` that a saved three-pane splitter state restores without being discarded:

```python
def test_workbench_three_pane_splitter_state_restores(qtbot, tmp_path, monkeypatch):
    from app_desktop.window import ExtrapolationWindow
    from shared.settings_store import KEY_MAIN_SPLITTER_STATE, SettingsStore

    store = SettingsStore(app_name="DataLabTest", organization="DataLabTest")
    monkeypatch.setattr("shared.settings_store.SettingsStore", lambda *args, **kwargs: store)
    first = ExtrapolationWindow()
    qtbot.addWidget(first)
    first.resize(1440, 900)
    first._main_splitter.setSizes([330, 730, 380])
    store.save_bytes(KEY_MAIN_SPLITTER_STATE, bytes(first._main_splitter.saveState()))

    second = ExtrapolationWindow()
    qtbot.addWidget(second)
    assert len(second._main_splitter.sizes()) == 3
    assert store.load_bytes(KEY_MAIN_SPLITTER_STATE) is not None
```

Update existing tests that force the old two-pane splitter. Replace calls like:

```python
window._main_splitter.setSizes([1, max(1, window.width() - 1)])
```

with the three-pane equivalent:

```python
window._main_splitter.setSizes([1, max(1, window.width() - 321), 320])
```

Apply this migration in:

```text
tests/test_desktop_mode_stack.py
tests/test_desktop_root_solving_ui.py
tests/test_parallel_preferences.py
tests/test_formula_preview_dialog.py
```

In `tests/test_desktop_root_solving_ui.py`, keep the existing exact expected formula aligned with the production formula:

```python
expected = (
    max(320, window.left_container.minimumSizeHint().width())
    + window._left_scroll.frameWidth() * 2
    + window._left_scroll.verticalScrollBar().sizeHint().width()
)
assert window._main_splitter_left_min_width == expected
assert window._left_scroll.minimumWidth() == expected
```

Update `_refresh_main_splitter_left_min_width()` in `app_desktop/panels.py` so it uses `workbench_config_rail` when present and falls back to `_left_scroll` only for older layouts:

```python
from app_desktop.workbench_visual_contract import CONFIG_RAIL_MIN_WIDTH


def _refresh_main_splitter_left_min_width(self) -> None:
    config_rail = getattr(self, "workbench_config_content", None)
    config_scroll = getattr(self, "workbench_config_rail", None)
    if config_rail is not None:
        _activate_widget_layouts(config_rail)
        workspace_canvas = getattr(self, "workbench_workspace_canvas", None)
        if workspace_canvas is not None:
            _activate_widget_layouts(workspace_canvas)
            _refresh_visible_table_min_widths(workspace_canvas)
        _refresh_visible_table_min_widths(config_rail)
        content_min_width = max(CONFIG_RAIL_MIN_WIDTH, config_rail.minimumSizeHint().width())
        config_rail.setMinimumWidth(content_min_width)
        viewport_overhead = (
            config_scroll.frameWidth() * 2
            + config_scroll.verticalScrollBar().sizeHint().width()
            if config_scroll is not None
            else 0
        )
        left_min = content_min_width + viewport_overhead
        self._main_splitter_left_min_width = left_min
        if config_scroll is not None:
            config_scroll.setMinimumWidth(left_min)
        splitter = getattr(self, "_main_splitter", None)
        if splitter is not None and splitter.count() >= 3:
            sizes = splitter.sizes()
            center_min = getattr(self, "workbench_workspace_canvas", config_rail).minimumWidth()
            right_min = getattr(self, "workbench_result_rail", config_rail).minimumWidth()
            if sizes and len(sizes) >= 3 and sizes[0] >= left_min and sizes[1] >= center_min and sizes[2] >= right_min:
                return
            total = max(sum(sizes), 1)
            current_left = sizes[0] if len(sizes) >= 3 else left_min
            current_right = sizes[2] if len(sizes) >= 3 else right_min
            new_left = max(current_left, left_min)
            new_right = max(current_right, right_min)
            new_center = total - new_left - new_right
            if new_center < center_min:
                deficit = center_min - new_center
                shrink_left = min(max(0, new_left - left_min), deficit)
                new_left -= shrink_left
                deficit -= shrink_left
                shrink_right = min(max(0, new_right - right_min), deficit)
                new_right -= shrink_right
                deficit -= shrink_right
                new_center = max(1, total - new_left - new_right)
            splitter.setSizes(
                [
                    new_left,
                    new_center,
                    new_right,
                ]
            )
        return

    left_container = getattr(self, "left_container", None)
    left_scroll = getattr(self, "_left_scroll", None)
    if left_container is None or left_scroll is None:
        return
    _activate_widget_layouts(left_container)
    _refresh_visible_table_min_widths(left_container)
    _activate_widget_layouts(left_container)
    viewport_overhead = (
        left_scroll.frameWidth() * 2
        + left_scroll.verticalScrollBar().sizeHint().width()
    )
    content_min_width = max(
        left_container.minimumSizeHint().width(),
        _visible_left_content_min_width(left_container),
    )
    left_min_width = max(MIN_LEFT_PANEL_WIDTH, content_min_width) + viewport_overhead
    self._main_splitter_left_min_width = left_min_width
    left_scroll.setMinimumWidth(left_min_width)
    splitter = getattr(self, "_main_splitter", None)
    if splitter is None or splitter.count() < 2:
        return
    sizes = splitter.sizes()
    if not sizes or sizes[0] >= left_min_width:
        return
    total = max(sum(sizes), left_min_width + 1)
    right_width = max(1, total - left_min_width)
    splitter.setSizes([left_min_width, right_width])
```

Update the Qt imports in `tools/scan_desktop_gui_schema.py` to include `QScrollArea`, then update `_horizontal_scrollbar_issues()` so it checks the real 3-pane config rail scroll area before the legacy fallback:

```python
def _horizontal_scrollbar_issues(window: Any, scenarios: list[ScreenScenario]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for scenario in scenarios:
        _apply_screen_scenario(window, scenario)
        QApplication.processEvents()
        _force_smallest_left_splitter(window)
        config_scroll = window.findChild(QScrollArea, "workbench_config_rail")
        if config_scroll is not None:
            bar = config_scroll.horizontalScrollBar()
            if bar.maximum() != 0 or bar.isVisible():
                issues.append(
                    _issue(
                        "workbench_config_horizontal_scrollbar",
                        scenario,
                        "workbench_config_rail",
                        "configuration rail exposes a horizontal scrollbar after splitter clamp",
                        maximum=int(bar.maximum()),
                        visible=bool(bar.isVisible()),
                    )
                )
            continue

        bar = window._left_scroll.horizontalScrollBar()
        if bar.maximum() != 0 or bar.isVisible():
            issues.append(
                _issue(
                    "horizontal_scrollbar",
                    scenario,
                    "_left_scroll",
                    "left panel horizontal scrollbar is visible after splitter clamp",
                    maximum=int(bar.maximum()),
                    visible=bool(bar.isVisible()),
                )
            )
    return issues
```

Update `_force_smallest_left_splitter()` in `tools/scan_desktop_gui_schema.py` so it clamps all three panes when the new workbench splitter is present:

```python
def _force_smallest_left_splitter(window: Any) -> None:
    window._refresh_main_splitter_left_min_width()
    splitter = window._main_splitter
    if splitter.count() >= 3:
        splitter.setSizes([1, max(1, window.width() - 321), 320])
    else:
        splitter.setSizes([1, max(1, window.width() - 1)])
    QApplication.processEvents()
    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
```

Modify `tests/test_desktop_gui_redesign_scan.py` with a regression proving the new gate is live:

```python
def test_workbench_config_horizontal_scroll_gate_detects_overflow(qtbot):
    from PySide6.QtWidgets import QLabel
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import ScreenScenario, _horizontal_scrollbar_issues

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    huge = QLabel("X" * 500)
    window.workbench_config_layout.addWidget(huge)
    issues = _horizontal_scrollbar_issues(window, [ScreenScenario(key="zh:fitting", language="zh", mode="fitting")])
    assert any(issue["kind"] == "workbench_config_horizontal_scrollbar" for issue in issues)
```

After the new regions exist, extend `tools/scan_desktop_gui_schema.py` near the imports:

```python
from app_desktop.workbench_visual_contract import visual_contract_issues  # noqa: E402
```

Inside `scan_window()` after existing layout issues are collected, add:

```python
    for issue in visual_contract_issues(window):
        structured_issues.append(
            _issue(
                str(issue.get("kind", "workbench_visual")),
                None,
                str(issue.get("widget", "workbench")),
                "workbench visual contract issue",
                **{k: v for k, v in issue.items() if k not in {"kind", "widget"}},
            )
        )
```

- [ ] **Step 5: Run layout and existing GUI scan tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_visual_contract.py tests/test_desktop_shell_layout.py tests/test_desktop_gui_redesign_scan.py tests/test_splitter_persistence.py tests/test_desktop_root_solving_ui.py tests/test_desktop_mode_stack.py tests/test_parallel_preferences.py tests/test_formula_preview_dialog.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add app_desktop/workbench_layout.py app_desktop/panels.py tools/scan_desktop_gui_schema.py tests/test_desktop_workbench_layout.py tests/test_splitter_persistence.py tests/test_desktop_root_solving_ui.py tests/test_desktop_mode_stack.py tests/test_parallel_preferences.py tests/test_formula_preview_dialog.py
git commit -m "refactor: introduce three-column desktop workbench"
```

---

## Task 5: Move the Real Data Input Area Into the Center Workspace

**Files:**
- Modify: `app_desktop/panels.py`
- Create: `tests/test_desktop_workbench_data_area.py`

- [ ] **Step 1: Write data-area ownership tests**

Create `tests/test_desktop_workbench_data_area.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_actual_data_editor_lives_in_center_workspace(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.input_section.parentWidget() is window.workbench_config_content
    assert window.manual_box.parentWidget() is window.workbench_workspace_content
    assert window.manual_table.parentWidget() is window._data_stack
    assert window.manual_data_edit.parentWidget() is window._data_stack
    assert window.file_box.parentWidget() is window.input_section


def test_data_input_state_is_not_duplicated_or_mirrored(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.findChild(type(window.manual_table), "workbench_data_preview_table") is None
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_data_edit
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_table
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_data_area.py
```

Expected before implementation:

```text
AssertionError: manual_box parent is not workbench_workspace_canvas
```

- [ ] **Step 3: Reparent only the data editor after construction**

Modify `app_desktop/panels.py::build_ui()` after `self._build_left_panel()` and before `self._build_right_panel(self.workbench_result_layout)`:

```python
from app_desktop.workbench_layout import reparent_widget

reparent_widget(self.workbench_workspace_layout, self.manual_box, stretch=2)
```

- [ ] **Step 4: Keep source controls in the left configuration rail**

Do not move `self.mode_section`, `self.output_setup_section`, or `self.run_section`; these stay in `self.workbench_config_layout`. Add this assertion to `tests/test_desktop_workbench_data_area.py`:

```python
def test_configuration_sections_stay_in_left_rail(qtbot: Any) -> None:
    window = _window(qtbot)
    assert window.mode_section.parentWidget() is window.workbench_config_content
    assert window.input_section.parentWidget() is window.workbench_config_content
    assert window.output_setup_section.parentWidget() is window.workbench_config_content
    assert window.run_section.parentWidget() is window.workbench_config_content
```

- [ ] **Step 5: Run data-area and input workflow tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_data_area.py tests/test_desktop_gui_workflows.py tests/test_workspace_controller.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add app_desktop/panels.py tests/test_desktop_workbench_data_area.py
git commit -m "refactor: move data input into center workbench"
```

---

## Task 6: Move Mode Editors Into the Center Workspace Canvas

**Files:**
- Modify: `app_desktop/workbench_layout.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_desktop_workbench_editor_canvas.py`
- Modify: `tests/test_desktop_shell_layout.py`

- [ ] **Step 1: Write editor canvas tests**

Create `tests/test_desktop_workbench_editor_canvas.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStackedWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_mode_editors_reuse_existing_mode_stack_in_center_canvas(qtbot: Any) -> None:
    window = _window(qtbot)

    stack = window.mode_stack
    assert isinstance(stack, QStackedWidget)
    assert stack.parentWidget() is window.workbench_workspace_content
    assert stack.count() >= 5
    for widget in (window.extrap_box, window.error_box, window.fit_box, window.root_box, window.stats_box):
        assert stack.indexOf(widget) >= 0


def test_mode_switch_updates_center_editor_without_losing_drafts(qtbot: Any) -> None:
    window = _window(qtbot)
    stack = window.mode_stack

    window.fit_expr_edit.setPlainText("A*x+B")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.root_box

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.fit_box
    assert window.fit_expr_edit.toPlainText() == "A*x+B"
```

- [ ] **Step 2: Run editor canvas tests and verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py
```

Expected before implementation:

```text
AssertionError: stack is None
```

- [ ] **Step 3: Reuse the existing reparent helper**

Use the `reparent_widget()` helper created in Task 4. Do not add another helper for the same `setParent(None)` plus `layout.addWidget(...)` operation.

- [ ] **Step 4: Reparent the existing mode stack after it is constructed**

Modify `app_desktop/panels.py` after all mode boxes are created. Move the existing `mode_stack`; do not create a second stack:

```python
from app_desktop.workbench_layout import reparent_widget

reparent_widget(self.workbench_workspace_layout, self.mode_stack, stretch=1)
if hasattr(self, "parameters_section"):
    self.parameters_section.setParent(None)
    self.parameters_section.deleteLater()
```

Keep the left rail `mode_section` limited to `mode_combo` and mode-level hints. Do not add `extrap_box`, `error_box`, `fit_box`, `root_box`, or `stats_box` directly to `left_layout`; they remain owned by the single existing `mode_stack`.

Update `tests/test_desktop_shell_layout.py::test_shell_sections_are_visible_in_expected_order` so the expected left-rail order matches the post-migration layout:

```python
assert layout_names[:4] == [
    "input_section",
    "mode_section",
    "output_setup_section",
    "run_section",
]
```

Add an assertion proving parameter/model controls moved to the center instead of being destroyed:

```python
assert window.mode_stack.parentWidget() is window.workbench_workspace_content
assert window.custom_params_table is not None
assert window.custom_constants_editor is not None
```

- [ ] **Step 5: Keep `_on_mode_change()` on the existing stack**

Do not add a new stack driver to `app_desktop/window.py`. Verify `_on_mode_change()` continues to call `self.mode_stack.setCurrentIndex(...)`. Add this assertion to `tests/test_desktop_workbench_editor_canvas.py`:

```python
def test_no_second_editor_stack_is_created(qtbot: Any) -> None:
    window = _window(qtbot)
    assert window.findChild(QStackedWidget, "workbench_editor_stack") is None
```

- [ ] **Step 6: Run editor and legacy mode tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_mode_stack.py tests/test_workspace_controller.py tests/test_desktop_shell_layout.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app_desktop/workbench_layout.py app_desktop/panels.py app_desktop/window.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_shell_layout.py
git commit -m "refactor: move mode editors into workbench canvas"
```

---

## Task 7: Add Right Result Rail Overview and Compact Result Table

**Files:**
- Create: `app_desktop/workbench_results.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_desktop_workbench_results.py`

- [ ] **Step 1: Write result rail tests**

Create `tests/test_desktop_workbench_results.py`:

```python
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTableWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_result_rail_has_overview_and_data_table(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.workbench_result_overview is not None
    assert isinstance(window.workbench_result_table, QTableWidget)
    assert window.tabs.parentWidget() is window.workbench_result_rail
    assert window.result_tabs.parentWidget() is window.tabs.widget(window.result_tab_index)


def test_result_rail_mirrors_csv_rows(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window.refresh_workbench_result_rail()

    assert window.workbench_result_table.rowCount() == 1
    assert window.workbench_result_table.columnCount() == 2
    assert window.workbench_result_table.item(0, 0).text() == "2.47e-3"
    assert "1" in window.workbench_result_overview.text()


def test_result_rail_clears_when_csv_data_resets(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")
    window._reset_csv_data()

    assert window.workbench_result_table.rowCount() == 0
    assert window.workbench_result_overview.text() in {"暂无结果", "No results"}


def test_result_rail_summary_relocalizes_on_language_switch(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")

    window._apply_language("en")
    assert "Result data: 1 rows" in window.workbench_result_overview.text()
    window._apply_language("zh")
    assert "结果数据：1 行" in window.workbench_result_overview.text()
```

- [ ] **Step 2: Run result tests and verify failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py
```

Expected before implementation:

```text
AttributeError: 'ExtrapolationWindow' object has no attribute 'workbench_result_overview'
```

- [ ] **Step 3: Create result rail adapter**

Create `app_desktop/workbench_results.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import table_style


def build_result_overview(owner) -> QWidget:
    widget = QWidget()
    widget.setObjectName("workbench_result_overview_panel")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    owner.workbench_result_overview = QLabel(owner._tr("暂无结果", "No results"))
    layout.addWidget(owner.workbench_result_overview)

    table = QTableWidget()
    table.setObjectName("workbench_result_table")
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(table_style())
    owner.workbench_result_table = table
    layout.addWidget(table)
    return widget


def refresh_result_overview(owner) -> None:
    rows = list(getattr(owner, "_csv_rows", []) or [])
    headers = list(getattr(owner, "_csv_headers", []) or [])
    table = owner.workbench_result_table
    table.clear()
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels([str(header) for header in headers])
    for row_index, row in enumerate(rows):
        for col_index, header in enumerate(headers):
            table.setItem(row_index, col_index, QTableWidgetItem(str(row.get(header, ""))))
    if rows:
        owner.workbench_result_overview.setText(
            owner._tr(
                f"结果数据：{len(rows)} 行，{len(headers)} 列",
                f"Result data: {len(rows)} rows, {len(headers)} columns",
            )
        )
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
    table.resizeColumnsToContents()
```

- [ ] **Step 4: Add overview to result rail without breaking outer result tabs**

Modify `app_desktop/panels.py` after `build_right_panel()` creates `self.result_tabs`:

```python
from app_desktop.workbench_results import build_result_overview

self.workbench_result_overview_panel = build_result_overview(self)
self.workbench_result_layout.insertWidget(0, self.workbench_result_overview_panel)
```

Do not reparent `self.result_tabs`. The outer `self.tabs` must remain the right-rail child because `tools/scan_desktop_gui_schema.py`, `window_latex_pdf_mixin.py`, workspace restore, and result-tab tests drive `window.tabs`.

- [ ] **Step 5: Add refresh hook**

Modify `app_desktop/window.py`:

```python
def refresh_workbench_result_rail(self) -> None:
    from app_desktop.workbench_results import refresh_result_overview

    if hasattr(self, "workbench_result_table"):
        refresh_result_overview(self)
```

At the end of `_set_csv_data()`, add:

```python
if hasattr(self, "refresh_workbench_result_rail"):
    self.refresh_workbench_result_rail()
```

At the end of `_reset_csv_data()`, add the same refresh call:

```python
if hasattr(self, "refresh_workbench_result_rail"):
    self.refresh_workbench_result_rail()
```

Modify `WindowI18nMixin._apply_language()` or the owning language-refresh method so dynamic result counts re-render after static text refresh:

```python
if hasattr(self, "refresh_workbench_result_rail"):
    self.refresh_workbench_result_rail()
```

- [ ] **Step 6: Run result rail tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_results.py tests/test_desktop_result_workflows.py tests/test_workspace_controller.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add app_desktop/workbench_results.py app_desktop/panels.py app_desktop/window.py tests/test_desktop_workbench_results.py
git commit -m "feat: add workbench result overview rail"
```

---

## Task 8: Apply Dense Scientific Workbench Styling Without Breaking Scroll Boundaries

**Files:**
- Modify: `app_desktop/theme.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/section_panel.py`
- Modify: `tools/scan_desktop_gui_schema.py`
- Modify: `tests/test_desktop_gui_redesign_scan.py`
- Create: `tests/test_desktop_workbench_visual_screenshots.py`

- [ ] **Step 1: Write screenshot metric tests**

Create `tests/test_desktop_workbench_visual_screenshots.py`:

```python
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


def test_workbench_screenshot_manifest_contains_region_metrics(tmp_path) -> None:
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    report = capture_desktop_gui_screens(out=tmp_path / "screens", width=1440, height=900)

    assert report["count"] >= 16
    for item in report["screenshots"]:
        assert item["issue_count"] == 0
        regions = item["regions"]
        assert regions["workbench_config_rail"]["width"] >= 260
        assert regions["workbench_workspace_canvas"]["width"] >= 520
        assert regions["workbench_result_rail"]["width"] >= 320

    manifest = json.loads((tmp_path / "screens" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["screenshots"][0]["regions"]["workbench_toolbar"]["height"] >= 44
```

- [ ] **Step 2: Add screenshot region metrics to the capture tool**

Modify `tools/capture_desktop_gui_screens.py` imports:

```python
from app_desktop.workbench_visual_contract import workbench_region_metrics, visual_contract_issues
```

Inside the screenshot loop, before appending each screenshot entry, add:

```python
            metrics = workbench_region_metrics(window)
            screenshots.append(
                {
                    "path": str(target),
                    "width": int(image.width()),
                    "height": int(image.height()),
                    "mode": scenario.mode,
                    "root_mode": scenario.root_mode,
                    "language": scenario.language,
                    "issue_count": _scenario_issue_count(window) + len(visual_contract_issues(window)),
                    "regions": {
                        key: metric.__dict__
                        for key, metric in metrics.items()
                    },
                }
            )
```

Remove the old append block for that screenshot entry so each screenshot appears once.

- [ ] **Step 3: Run visual screenshot metric test**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_screenshots.py
```

Expected before Tasks 4-7 are complete: fail with missing `regions`.

- [ ] **Step 4: Tighten region styles**

Modify `app_desktop/theme.py` so `workbench_region_style()` includes:

```python
QFrame#workbench_workspace_canvas_content QGroupBox,
QFrame#workbench_result_rail QWidget#workbench_result_overview_panel {{
    border: 1px solid {border};
    border-radius: 8px;
    background: {panel_bg};
}}
QFrame#workbench_workspace_canvas_content QLabel,
QFrame#workbench_config_rail_content QLabel,
QFrame#workbench_result_rail QLabel {{
    color: {fg};
}}
```

Do not style page sections as floating marketing cards. These are compact tool surfaces.

- [ ] **Step 5: Ensure theme refresh applies all new styles**

Modify `ExtrapolationWindow._apply_desktop_theme()` in `app_desktop/window.py`:

```python
for widget_name in (
    "workbench_root",
    "workbench_bar",
    "workbench_config_rail",
    "workbench_workspace_canvas",
    "workbench_result_rail",
    "workbench_status_strip",
):
    widget = getattr(self, widget_name, None)
    if widget is not None:
        widget.setStyleSheet(workbench_toolbar_style() if widget_name == "workbench_bar" else workbench_region_style())
```

- [ ] **Step 5: Run GUI scan and screenshot tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_screenshots.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_theme_tokens.py tests/test_desktop_workbench_theme.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

Expected: tests pass, scan reports no issues, screenshot manifest has `issue_count: 0`.

- [ ] **Step 6: Commit**

Run:

```bash
git add app_desktop/theme.py app_desktop/panels.py app_desktop/section_panel.py app_desktop/window.py tools/scan_desktop_gui_schema.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_workbench_visual_screenshots.py
git commit -m "style: polish desktop scientific workbench layout"
```

---

## Task 9: Update Docs and Release Gate for the Visual Workbench

**Files:**
- Modify: `docs/desktop/guide.en.md`
- Modify: `docs/desktop/guide.zh.md`
- Modify: `docs/TEST_MATRIX.md`
- Modify: `tools/capture_desktop_gui_screens.py`

- [ ] **Step 1: Update desktop docs**

Add this section to `docs/desktop/guide.en.md`:

```markdown
## Workbench Layout

The desktop window uses a three-zone scientific workbench:

- Left configuration rail: calculation mode, data source, and output settings.
- Center workspace: data editor, formula/model editor, parameters, and constants.
- Right result rail: result summary/status, result data, image, LaTeX, log, and PDF preview tabs.

The splitter keeps required controls visible at supported desktop sizes. Formula preview buttons open a rendered preview dialog without changing the formula text.
```

Add this section to `docs/desktop/guide.zh.md`:

```markdown
## 工作台布局

桌面窗口采用三栏科学工作台：

- 左侧配置栏：计算模式、数据来源和输出设置。
- 中央工作区：数据编辑、公式/模型编辑、参数和常数。
- 右侧结果栏：结果摘要、进度、结果数据、图片、LaTeX、日志和 PDF 预览标签。

在支持的桌面尺寸下，分隔条不会遮挡必要控件。公式预览按钮会打开渲染预览窗口，不会修改公式文本。
```

- [ ] **Step 2: Update release gate**

Modify `docs/TEST_MATRIX.md` release gate to include:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_visual_screenshots.py
```

- [ ] **Step 3: Run docs/resource tests**

Run:

```bash
pytest -q tests/test_desktop_docs_resources.py tests/test_packaging_resources.py
```

Expected: pass.

- [ ] **Step 4: Verify screenshot manifest still carries visual metrics**

Run:

```bash
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
python - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path("build/gui-screenshots/manifest.json").read_text())
assert manifest["screenshots"], "expected screenshot entries"
for entry in manifest["screenshots"]:
    assert "regions" in entry, entry["path"]
    assert entry["issue_count"] == 0, entry
PY
```

Expected: command exits with status 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add docs/desktop/guide.en.md docs/desktop/guide.zh.md docs/TEST_MATRIX.md tools/capture_desktop_gui_screens.py
git commit -m "docs: document desktop visual workbench"
```

---

## Task 10: Final Visual Release Gate

**Files:**
- Modify: `docs/TEST_MATRIX.md`

- [ ] **Step 1: Run focused visual gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_visual_contract.py tests/test_desktop_workbench_theme.py tests/test_desktop_workbench_toolbar.py tests/test_desktop_workbench_layout.py tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_editor_canvas.py tests/test_desktop_workbench_results.py tests/test_desktop_workbench_visual_screenshots.py
```

Expected: all pass.

- [ ] **Step 2: Run existing GUI compatibility gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py tests/test_desktop_theme_tokens.py tests/test_desktop_shell_layout.py tests/test_desktop_examples_entrypoint.py tests/test_desktop_docs_resources.py tests/test_packaging_resources.py tests/test_desktop_example_workspace_menu.py tests/test_desktop_gui_screenshot_smoke.py
```

Expected: all pass.

- [ ] **Step 3: Run workspace/result compatibility gate**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_controller.py tests/test_workspace_io.py tests/test_workspace_auto_fit_migration.py tests/test_desktop_result_workflows.py
```

Expected: all pass.

- [ ] **Step 4: Run screenshot and scan commands**

Run:

```bash
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

Expected:

```text
"issues": []
"count": 16
```

Every screenshot entry must have `issue_count: 0`.

- [ ] **Step 5: Run full local gate**

Run:

```bash
python -m compileall -q .
QT_QPA_PLATFORM=offscreen pytest -q
```

Expected: full suite passes. Existing skip count is acceptable if skip reasons are unchanged and not related to the visual workbench.

- [ ] **Step 6: Commit final gate docs if changed**

If `docs/TEST_MATRIX.md` changed, run:

```bash
git add docs/TEST_MATRIX.md
git commit -m "test: finalize desktop visual workbench gate"
```

If no files changed, do not create an empty commit.

---

## Three-Model Review Gate

This plan must be reviewed and revised until no accepted findings remain.

### Codex Review

Use a read-only Codex subagent/code reviewer or main-thread review with this prompt:

```text
Review docs/superpowers/plans/2026-06-08-datalab-workbench-visual-redesign-plan.md against the current DataLab source. Focus on feasibility, maintainability, GUI/widget ownership, reparenting risks, schema/help reuse, workspace compatibility, screenshot/scan coverage, and whether the plan actually reaches the approved three-column workbench sketch. Return PASS/CONTESTED/REJECT and concrete findings only.
```

Acceptance rule:

- Accept findings that identify a real implementation hazard, duplicated logic, broken current tests, missing state preservation, or inadequate visual acceptance.
- Reject findings only with a written reason in `findings.md`.

### Gemini / Antigravity Gemini Pro Review

Run from the repository root. The Gemini plugin must use the configured Antigravity Gemini Pro backend.

```bash
GEMINI_FOR_CODEX_BACKEND=antigravity node ${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/gemini-for-codex/0.11.0/scripts/gemini-companion.mjs adversarial-review --scope working-tree --path docs/superpowers/plans/2026-06-08-datalab-workbench-visual-redesign-plan.md --path app_desktop/panels.py --path app_desktop/shell_layout.py --path app_desktop/theme.py --path tools/scan_desktop_gui_schema.py --json "Challenge whether this plan can actually deliver the approved DataLab three-column scientific workbench without breaking existing GUI behavior, workspace compatibility, schema reuse, tests, or maintainability."
```

If the local Antigravity configuration requires an explicit Gemini model, set it in the environment before the command:

```bash
export GEMINI_FOR_CODEX_ANTIGRAVITY_MODEL="Gemini 3.1 Pro (High)"
```

### Claude Review

Run from the repository root:

```bash
node ${CODEX_PLUGIN_CACHE:-~/.codex/plugins/cache}/external-models-for-codex/claude-for-codex/0.14.1/scripts/claude-companion.mjs adversarial-review --scope working-tree --path docs/superpowers/plans/2026-06-08-datalab-workbench-visual-redesign-plan.md --path app_desktop/panels.py --path app_desktop/shell_layout.py --path app_desktop/theme.py --path tools/scan_desktop_gui_schema.py --json "Challenge whether this plan can actually deliver the approved DataLab three-column scientific workbench without breaking existing GUI behavior, workspace compatibility, schema reuse, tests, or maintainability."
```

### Revision Loop

For every finding:

1. Classify it in `findings.md` as accepted or rejected.
2. For accepted findings, patch this plan before implementation.
3. Re-run the relevant model review command.
4. Stop only when Codex, Gemini, and Claude each return `PASS` or no accepted findings remain.

---

## Self-Review

### Spec Coverage

- User asked why the current version does not match the sketch: this plan explicitly targets the sketch with toolbar, left rail, center workspace, right rail, and bottom status strip.
- User asked for implementation design details: each task lists files, tests, code snippets, commands, and commit points.
- User required three-model adversarial review: the plan includes Codex, Gemini/Antigravity Gemini Pro, and Claude review gates plus a revision loop.
- User required maintainability: the plan reuses existing widgets, schema metadata, parsers, result formatters, and tests; new files are focused by responsibility.

### Placeholder Scan

No task uses TBD/TODO/fill-in placeholders. Every code-changing step includes concrete code snippets and exact commands.

### Type and Contract Consistency

- Object names are centralized in `app_desktop/workbench_visual_contract.py`.
- New tests use the same object names as the layout helpers.
- Existing public widget attributes remain preserved and are explicitly tested.
- Screenshot and scan tools use the same visual contract helper, avoiding duplicated geometry rules.
