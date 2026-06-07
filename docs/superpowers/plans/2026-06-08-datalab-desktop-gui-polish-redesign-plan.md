# DataLab Desktop GUI Polish Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the DataLab desktop GUI into a clearer, more polished scientific workbench while preserving existing computation behavior, workspace compatibility, shared schema/help metadata, and reusable editor contracts.

**Architecture:** Implement this as a phased shell-and-schema migration, not a rewrite. First strengthen shared UI metadata and GUI tests, then reparent existing widgets into a task-oriented shell, replace hide/show ladders with stable stacks, move result-only controls into result areas, and only then polish styling and onboarding.

**Tech Stack:** Python 3, PySide6, pytest/pytest-qt, existing `shared/ui_schema.py`, `shared/ui_specs.py`, `shared/help_specs.json`, `app_desktop` widgets, workspace controller, Matplotlib-backed formula/plot preview, PyInstaller bundle checks.

---

## Current Codebase Facts

- `app_desktop/panels.py` currently constructs most desktop UI inline: menus, splitter, left scroll rail, all mode boxes, options, result tabs, help buttons, and many local `FormFieldSpec` objects.
- `app_desktop/window.py` and mixins assume stable widget attributes such as `manual_box`, `fit_box`, `root_box`, `options_box`, `run_button`, `result_edit`, `latex_edit`, and many specific input widgets.
- `app_desktop/workspace_controller.py` captures/restores workspace state through those direct attributes. Any layout migration must preserve attributes and persisted config keys until an explicit adapter task changes them.
- `ConstantsEditor`, `ParameterTable`, and `DetectedRowsTable` already encode non-visual behavior: draft preservation, table/text conversion, detected/manual row source metadata, orphan rows, and normalization. The redesign must wrap or reparent them, not replace them with plain tables.
- `shared/ui_schema.py` already defines `FormFieldSpec`, `FormSectionSpec`, `ResultViewSpec`, and `PlotSpec`; `shared/ui_specs.py` still mixes older `WidgetSpec`/`ParameterGroupSpec` with newer schema objects.
- `tools/scan_desktop_gui_schema.py` is the strongest current GUI scan, but it covers only a subset of screens and affordances.
- `docs/TEST_MATRIX.md` still says automated tests do not click through desktop GUI; this is stale and too weak for a redesign release gate.

## Non-Goals

- Do not change numerical algorithms, fitting/root-solving backends, precision behavior, worker isolation, or workspace file format semantics except where layout state is explicitly added with backward-compatible defaults.
- Do not create a second expression parser, help registry, constants parser, parameter parser, or result formatter.
- Do not replace `ConstantsEditor`, `ParameterTable`, `DetectedRowsTable`, or formula preview helpers with new equivalents.
- Do not add marketing-style hero pages, decorative cards, or broad color-only restyling. This is a dense scientific desktop application.

## Target User Experience

- A top workbench bar exposes workspace actions, examples, run/stop, update/docs, current mode, dirty/saved status, and current job status.
- The left side becomes a task setup column with predictable sections: Input, Model/Method, Parameters & Constants, Calculation Options, and Output Setup.
- Mode-specific settings are held in a stack instead of many hidden siblings in one rail.
- Output-only controls live with output tabs where possible, especially LaTeX/PDF/image controls.
- Formula inputs use placeholder examples, preview buttons, function-help buttons, and schema-bound tooltips consistently.
- Tables retain compact scientific editing, with add/remove/clear/text-view affordances and bilingual headers.
- Splitter boundaries never hide required controls or create horizontal scrollbars at supported desktop sizes.

## File Structure Plan

- Modify `shared/ui_schema.py` to add small metadata primitives only when the existing dataclasses are insufficient, such as section roles or command metadata. Keep this minimal.
- Modify `shared/ui_specs.py` to migrate the old `WidgetSpec`/`ParameterGroupSpec` definitions to direct `FormFieldSpec`/`FormSectionSpec` definitions, then expose compatibility accessors only where the web API still needs the old JSON shape.
- Modify `app_web/blueprints/api.py` to serialize `FormFieldSpec`-backed specs into the existing `/api/ui-specs` response shape.
- Modify `formula_help.py` so method/function help comes from `shared/help_specs.json` or one shared loader, rather than keeping a second hardcoded bilingual help registry.
- Modify `shared/help_specs.json` only for missing user-facing help text, keeping keys stable and bilingual.
- Create `app_desktop/schema_widgets.py` for reusable schema-bound help buttons, command buttons, section headers, and row action bars.
- Create `app_desktop/section_panel.py` for reusable compact/collapsible section containers with stable size policies and bilingual title binding.
- Create `app_desktop/shell_layout.py` for top workbench bar and left-panel shell construction.
- Modify `app_desktop/panels.py` to delegate shell/result/section construction and keep existing public widget attributes.
- Modify `app_desktop/window.py` only for mode-stack switching, section state refresh, and language/status integration.
- Modify `app_desktop/workspace_controller.py` only after layout stabilizes, adding adapter helpers while preserving manifest keys.
- If a Qt stack is used for mode pages, create a current-page-only size-hint wrapper instead of relying on raw `QStackedWidget`; raw hidden pages can still enlarge minimum width and reintroduce horizontal scrollbars.
- Modify `tools/scan_desktop_gui_schema.py` to scan every mode/submode/tab and return structured layout/help/accessibility issues.
- Create or expand GUI tests under `tests/test_desktop_gui_redesign_scan.py`, `tests/test_desktop_gui_workflows.py`, `tests/test_desktop_bilingual_inventory.py`, `tests/test_desktop_shell_layout.py`, and existing schema/workspace tests.
- Update `docs/TEST_MATRIX.md`, `docs/desktop/*.md`, and bundled examples/catalog references only after implementation is covered by tests.

---

## Task 1: Strengthen GUI Scan Before Moving Layout

**Files:**
- Modify: `tools/scan_desktop_gui_schema.py`
- Create: `tests/test_desktop_gui_redesign_scan.py`
- Modify: `tests/test_desktop_gui_schema_scan.py`

- [ ] **Step 1: Add screen scenario descriptors to the scan tool**

Add a `ScreenScenario` dataclass near the top of `tools/scan_desktop_gui_schema.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ScreenScenario:
    key: str
    language: str
    mode: str
    root_mode: str = ""
    result_tab: str = ""
    width: int = 1400
    height: int = 900
```

Use scenarios for all main modes, root submodes, result tabs, and at least widths `1280`, `1440`, and `1680`.

- [ ] **Step 2: Return structured layout issues**

Change issue entries from strings to dictionaries:

```python
{
    "kind": "horizontal_scrollbar",
    "scenario": scenario.key,
    "language": scenario.language,
    "widget": "_left_scroll",
    "details": {"maximum": int(bar.maximum()), "visible": bool(bar.isVisible())},
}
```

Keep a compatibility helper that prints human-readable messages for existing tests.

- [ ] **Step 3: Scan all visible labels, buttons, actions, tabs, tooltips, and placeholders**

Add helper functions:

```python
def _visible_text_inventory(window: Any) -> list[dict[str, str]]:
    ...

def _missing_help_affordances(window: Any, scenario: ScreenScenario) -> list[dict[str, Any]]:
    ...
```

The scan must fail for visible user-input controls without tooltip/accessible description or adjacent schema help button, except read-only result display widgets.

- [ ] **Step 4: Add failing tests for the stricter scan**

In `tests/test_desktop_gui_redesign_scan.py`, add:

```python
def test_redesign_scan_covers_all_modes_and_languages(qapp):
    from app_desktop.window import ExtrapolationWindow
    from tools.scan_desktop_gui_schema import scan_window

    window = ExtrapolationWindow()
    try:
        report = scan_window(window, refresh_language=True, strict=True)
        assert report["checks"]["scenario_count"] >= 30
        assert report["issues"] == []
    finally:
        window.deleteLater()
```

Expected before implementation: FAIL with missing strict scan support or existing issues. Expected after Task 1 and later layout tasks: PASS.

- [ ] **Step 5: Run focused tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py
```

Expected after Task 1: existing scan tests still pass; new strict test may remain marked as expected-failing only if the scan infrastructure is present and documents current issues. Do not proceed to layout tasks until the strict scan can report actionable structured issues.

- [ ] **Step 6: Commit**

```bash
git add tools/scan_desktop_gui_schema.py tests/test_desktop_gui_schema_scan.py tests/test_desktop_gui_redesign_scan.py
git commit -m "test: strengthen desktop gui schema scan"
```

---

## Task 2: Replace Legacy UI Specs With Direct Shared Schema Specs

**Files:**
- Modify: `shared/ui_schema.py`
- Modify: `shared/ui_specs.py`
- Modify: `app_web/blueprints/api.py`
- Modify: `app_desktop/ui_schema_binder.py`
- Modify: `app_desktop/ui_schema_runtime.py`
- Create: `tests/test_desktop_shared_ui_specs.py`
- Modify: `tests/test_web_api_smoke.py`

- [ ] **Step 1: Replace legacy widget classes with direct schema factories**

In `shared/ui_specs.py`, remove the old `WidgetSpec`, `TextWidgetSpec`, `NumberWidgetSpec`, `SelectWidgetSpec`, `TextAreaWidgetSpec`, and `ParameterGroupSpec` hierarchy after replacing each use with direct schema factories:

```python
def text_field(
    key: str,
    zh: str,
    en: str,
    *,
    placeholder_zh: str = "",
    placeholder_en: str = "",
    tooltip_zh: str = "",
    tooltip_en: str = "",
    required: bool = True,
    default_value: str = "",
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="text",
        label=LocalizedText(zh, en),
        placeholder=LocalizedText(placeholder_zh, placeholder_en),
        tooltip=LocalizedText(tooltip_zh, tooltip_en),
        required=required,
        default_value=default_value,
    )


def select_field(
    key: str,
    zh: str,
    en: str,
    *,
    choices: tuple[ChoiceSpec, ...],
    tooltip_zh: str = "",
    tooltip_en: str = "",
    default_value: object = None,
) -> FormFieldSpec:
    return FormFieldSpec(
        key=key,
        widget_kind="select",
        label=LocalizedText(zh, en),
        tooltip=LocalizedText(tooltip_zh, tooltip_en),
        choices=choices,
        default_value=default_value,
    )
```

Define similar small factories for number, checkbox, and textarea fields only if they avoid repeated literals.

- [ ] **Step 1b: Define the ownership boundary for shared vs desktop metadata**

Add this module-level comment above the new registries in `shared/ui_specs.py`:

```python
# Shared specs may describe user-visible labels, help, field keys,
# choices, placeholders, visibility rules, result attachment keys, and
# plot budgets. Desktop-only modules may describe Qt layout containers,
# stretch factors, icons, and platform-specific action placement. Do not
# put duplicate user-visible strings in app_desktop unless a Qt widget
# requires a transient state label that is not part of the shared UI.
```

This prevents `shared/ui_specs.py` from becoming a second desktop layout file while still removing duplicated labels/tooltips from `panels.py`.

- [ ] **Step 2: Define shared section registries**

Add `DESKTOP_FORM_SECTIONS`, `DESKTOP_RESULT_VIEWS`, and `DESKTOP_PLOT_SPECS` in `shared/ui_specs.py`. Use existing keys already bound in `panels.py`, including:

```python
"input"
"extrapolation"
"error"
"fitting"
"root_solving"
"statistics"
"options"
"result.numeric"
"result.image"
"result.log"
"result.latex"
"result.pdf"
```

Each section must be built from `FormSectionSpec` and existing `FormFieldSpec` values, not duplicate freeform label strings in the desktop layer.

- [ ] **Step 3: Preserve the web API response shape without legacy classes**

In `app_web/blueprints/api.py`, update `/api/ui-specs` serialization to consume `FormFieldSpec` and `FormSectionSpec` directly. Add a helper:

```python
def form_field_to_api_payload(field: FormFieldSpec, *, lang: str = "zh") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": field.key,
        "label": field.label.for_lang(lang),
        "widget_type": field.widget_kind,
        "default_value": field.default_value,
        "tooltip": field.tooltip.for_lang(lang),
        "optional": not field.required,
    }
    if field.placeholder.zh or field.placeholder.en:
        payload["placeholder"] = field.placeholder.for_lang(lang)
    if field.choices:
        payload["options"] = [
            {"label": choice.label.for_lang(lang), "value": choice.value}
            for choice in field.choices
        ]
    return payload
```

The JSON keys returned by `/api/ui-specs` must remain compatible with existing web tests.

- [ ] **Step 4: Add binder helpers for help and action buttons**

In `app_desktop/ui_schema_runtime.py`, add:

```python
def bind_schema_help_button(owner: Any, button: QWidget, *, field: FormFieldSpec, lang: str) -> None:
    bind_field(field=field, help_button=button, lang=lang)
    register_schema_text_refresh(owner, field, help_button=button)
```

In `app_desktop/ui_schema_binder.py`, keep `bind_field()` as the single property setter for labels/widgets/buttons.

- [ ] **Step 5: Test direct schema registry completeness**

Create `tests/test_desktop_shared_ui_specs.py`:

```python
def test_error_formula_spec_is_direct_form_field():
    from shared.ui_schema import FormFieldSpec
    from shared.ui_specs import ERROR_FORMULA_FIELD

    field = ERROR_FORMULA_FIELD
    assert isinstance(field, FormFieldSpec)
    assert field.key == "error.formula"
    assert field.label.zh == "公式："
    assert field.label.en == "Formula:"
    assert field.placeholder.zh
    assert field.tooltip.en

def test_desktop_section_registry_has_core_sections():
    from shared.ui_specs import DESKTOP_FORM_SECTIONS, DESKTOP_RESULT_VIEWS
    assert {"input", "fitting", "root_solving", "options"} <= set(DESKTOP_FORM_SECTIONS)
    assert {"numeric", "image", "latex", "pdf"} <= set(DESKTOP_RESULT_VIEWS)
```

- [ ] **Step 6: Run focused tests**

```bash
pytest -q tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_desktop_shared_ui_specs.py tests/test_web_api_smoke.py
```

- [ ] **Step 7: Commit**

```bash
git add shared/ui_schema.py shared/ui_specs.py app_web/blueprints/api.py app_desktop/ui_schema_binder.py app_desktop/ui_schema_runtime.py tests/test_desktop_shared_ui_specs.py tests/test_web_api_smoke.py
git commit -m "refactor: centralize desktop ui metadata specs"
```

---

## Task 2b: Make Help Specs the Single Source of Truth

**Files:**
- Modify: `formula_help.py`
- Modify: `shared/help_specs.json`
- Modify: `shared/ui_specs.py`
- Create: `tests/test_help_specs_single_source.py`
- Modify: `tests/test_web_api_smoke.py`

- [ ] **Step 1: Add a shared help loader**

In `formula_help.py`, replace hardcoded method/function text dictionaries with a loader that reads `shared/help_specs.json` through the existing resource resolver when bundled, falling back to the repository path in source mode. Preserve public functions:

```python
def get_method_name(method_key: str, lang: str = "zh") -> str: ...
def get_method_description(method_key: str, lang: str = "zh") -> str: ...
def get_function_help(lang: str = "zh") -> str: ...
def get_function_tooltip(lang: str = "zh") -> str: ...
```

These functions must return exactly the same type and broadly the same content as before so desktop and web callers do not change.

- [ ] **Step 2: Remove duplicated method/help literals from Python**

Keep Python-side default fallback strings only for missing file/load failure messages. Method names, method descriptions, function help text, and tooltip text must live in `shared/help_specs.json`.

- [ ] **Step 3: Test public API compatibility**

Create `tests/test_help_specs_single_source.py`:

```python
def test_formula_help_public_api_reads_shared_help_specs():
    from formula_help import get_function_help, get_method_description, get_method_name

    assert get_method_name("power_law", "zh")
    assert get_method_name("power_law", "en")
    assert get_method_description("power_law", "zh")
    assert "sin" in get_function_help("en").lower() or "Sin" in get_function_help("en")
```

- [ ] **Step 4: Run focused tests**

```bash
pytest -q tests/test_help_specs_single_source.py tests/test_web_api_smoke.py
```

- [ ] **Step 5: Commit**

```bash
git add formula_help.py shared/help_specs.json shared/ui_specs.py tests/test_help_specs_single_source.py tests/test_web_api_smoke.py
git commit -m "refactor: load formula help from shared specs"
```

---

## Task 3: Add Reusable Schema-Bound Desktop Widgets

**Files:**
- Create: `app_desktop/schema_widgets.py`
- Create: `app_desktop/section_panel.py`
- Create: `tests/test_desktop_schema_widgets.py`
- Create: `tests/test_desktop_section_panel.py`

- [ ] **Step 1: Create schema-bound help and command factories**

Implement `make_schema_help_button()`, `make_schema_command_button()`, and `make_icon_text_button()` in `app_desktop/schema_widgets.py`. They must:

- Set stable `objectName` when passed.
- Bind text/tooltip/accessibility via `bind_field()` or `bind_schema_command_button()`.
- Use the existing owner language registration methods.
- Use text labels first; icon support can be added only if the project already has a safe icon provider.

- [ ] **Step 2: Create a compact section panel**

Implement `SectionPanel(QWidget)` in `app_desktop/section_panel.py` with:

- Header label.
- Optional help button.
- Optional collapse toggle.
- A body layout returned by `body_layout()`.
- `set_collapsed(bool)`, `is_collapsed()`, `set_title(str)`, and `set_help_text(str)`.
- Stable margins and no horizontal scrollbar policy.

- [ ] **Step 3: Test widget contracts**

Add tests proving:

```python
def test_schema_help_button_has_tooltip_accessibility(qtbot):
    ...

def test_section_panel_preserves_body_widget_when_collapsed(qtbot):
    ...
```

The section test must add a child `QLineEdit`, collapse/expand, and verify the widget object is the same instance.

- [ ] **Step 4: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_schema_widgets.py tests/test_desktop_section_panel.py
```

- [ ] **Step 5: Commit**

```bash
git add app_desktop/schema_widgets.py app_desktop/section_panel.py tests/test_desktop_schema_widgets.py tests/test_desktop_section_panel.py
git commit -m "feat: add reusable desktop schema widgets"
```

---

## Task 4: Introduce the Workbench Shell Without Replacing Widgets

**Files:**
- Create: `app_desktop/shell_layout.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_desktop_shell_layout.py`

- [ ] **Step 1: Build top workbench bar using existing actions**

Create `build_workbench_bar(owner)` in `app_desktop/shell_layout.py`. It should expose:

- New workspace.
- Open workspace.
- Save.
- Open examples.
- Run.
- Stop.
- Docs.
- Check updates.
- Dirty/saved status label.
- Job status label.

Use existing window methods: `new_workspace`, `open_workspace`, `save_workspace`, `open_example_workspace`, `run_extrapolation`, `stop_calculation`, `_open_docs`, and `check_for_updates`.

- [ ] **Step 2: Reparent existing widgets into section containers**

Before moving any widget, add a baseline test that verifies the exact existing public attributes used by behavior and workspace code:

```python
def test_shell_preserves_current_public_widget_attributes(qtbot):
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    for name in (
        "manual_box",
        "extrap_box",
        "error_box",
        "fit_box",
        "root_box",
        "stats_box",
        "options_box",
        "run_button",
    ):
        assert getattr(window, name, None) is not None, name
```

Then in `build_left_panel()` in `app_desktop/panels.py`, create sections:

- `self.input_section`
- `self.mode_section`
- `self.parameters_section`
- `self.output_setup_section`
- `self.run_section`

Reparent existing `manual_box`, mode boxes, `options_box`, and `run_button` into those containers. Do not rename or recreate those widgets.

- [ ] **Step 3: Keep public attributes stable after reparenting**

Keep and extend the baseline test in `tests/test_desktop_shell_layout.py`:

```python
def test_shell_preserves_legacy_widget_attributes(qtbot):
    from app_desktop.window import ExtrapolationWindow
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    for name in ("manual_box", "extrap_box", "error_box", "fit_box", "root_box", "stats_box", "options_box", "run_button"):
        assert getattr(window, name, None) is not None
```

Also assert `window.run_button.clicked` still reaches `run_calculation` by monkeypatching `window.run_calculation` before clicking.

- [ ] **Step 4: Test section order and current-page baseline width**

Add:

```python
def test_shell_sections_are_visible_in_expected_order(qtbot):
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    names = [
        window.input_section.objectName(),
        window.mode_section.objectName(),
        window.output_setup_section.objectName(),
        window.run_section.objectName(),
    ]
    assert names == ["input_section", "mode_section", "output_setup_section", "run_section"]
```

Do not assert all-mode horizontal scrollbar behavior in Task 4. That assertion belongs in Task 5 after `CurrentPageStack` prevents hidden wide pages from driving the splitter minimum width.

- [ ] **Step 5: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_shell_layout.py tests/test_desktop_gui_redesign_scan.py
```

- [ ] **Step 6: Commit**

```bash
git add app_desktop/shell_layout.py app_desktop/panels.py app_desktop/window.py tests/test_desktop_shell_layout.py
git commit -m "feat: add desktop workbench shell"
```

---

## Task 5: Replace Mode Hide/Show Ladders With a Stable Mode Stack

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Create: `app_desktop/current_page_stack.py`
- Modify: `app_desktop/workspace_controller.py` only if mode stack state needs persistence
- Create: `tests/test_desktop_mode_stack.py`

- [ ] **Step 1: Create a current-page-only stack wrapper**

Do not use raw `QStackedWidget` directly for the left settings stack. Create `app_desktop/current_page_stack.py`:

```python
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QStackedWidget, QWidget


class CurrentPageStack(QStackedWidget):
    """A stack whose size hints come only from the current page.

    Qt's QStackedWidget can size itself from all pages, including hidden
    pages. In DataLab's narrow left panel that reintroduces horizontal
    scrollbars when one mode contains a wide table. This wrapper keeps
    hidden modes stateful but prevents hidden pages from driving splitter
    minimum width.
    """

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        widget = self.currentWidget()
        return widget.sizeHint() if isinstance(widget, QWidget) else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        widget = self.currentWidget()
        return widget.minimumSizeHint() if isinstance(widget, QWidget) else super().minimumSizeHint()
```

- [ ] **Step 2: Create `self.mode_stack` with `CurrentPageStack`**

In `build_left_panel()`, add `CurrentPageStack` and insert existing boxes:

```python
self.mode_stack = CurrentPageStack()
self.mode_stack.addWidget(self.extrap_box)
self.mode_stack.addWidget(self.error_box)
self.mode_stack.addWidget(self.fit_box)
self.mode_stack.addWidget(self.root_box)
self.mode_stack.addWidget(self.stats_box)
```

Keep each original `self.<mode>_box` attribute.

- [ ] **Step 3: Replace mode visibility updates**

In `window.py` mode-change logic, replace manual sibling show/hide for mode boxes with:

```python
mode_to_index = {
    "extrapolation": 0,
    "error": 1,
    "fitting": 2,
    "root_solving": 3,
    "statistics": 4,
}
self.mode_stack.setCurrentIndex(mode_to_index.get(mode, 0))
self._refresh_main_splitter_left_min_width()
```

Retain existing mode-specific refresh calls for options, placeholders, and result actions.

- [ ] **Step 4: Convert extrapolation sub-method settings to `CurrentPageStack`**

Inside `extrap_box`, replace sibling hide/show switching for `power_box`, `levin_box`, `richardson_box`, and `custom_formula_widget` with:

```python
self.extrap_method_stack = CurrentPageStack()
self.extrap_method_stack.addWidget(self.power_box)
self.extrap_method_stack.addWidget(self.levin_box)
self.extrap_method_stack.addWidget(self.richardson_box)
self.extrap_method_stack.addWidget(self.custom_formula_widget)
```

Update `_update_method_state` in `app_desktop/window.py` so method changes set the current page instead of manually hiding all siblings. Keep existing enable/disable and validation logic.

- [ ] **Step 5: Test hidden pages do not control left width**

Add a test that makes a hidden page artificially wide and verifies the left panel width calculation follows the current page:

```python
def test_mode_stack_uses_current_page_minimum_width(qtbot):
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    set_mode(window, "extrapolation")
    window.root_unknowns_table.setMinimumWidth(900)
    window._refresh_main_splitter_left_min_width()
    extrap_width = window._main_splitter_left_min_width
    set_mode(window, "root_solving")
    window._refresh_main_splitter_left_min_width()
    root_width = window._main_splitter_left_min_width
    assert extrap_width < root_width
```

- [ ] **Step 6: Test sub-method hidden pages do not control width**

Add a similar test for `extrap_method_stack`: make `custom_formula_widget` or `levin_box` artificially wide while another method is active, refresh splitter width, then switch to that method and assert the width grows only when the wide page becomes current.

- [ ] **Step 7: Test no clipping at supported widths**

Resize to `1280x800`, `1440x900`, and `1680x1050`; switch all top-level modes and extrapolation sub-methods; assert left horizontal scrollbar maximum is zero.

- [ ] **Step 8: Test draft preservation across mode switches**

`tests/test_desktop_mode_stack.py`:

```python
def test_mode_stack_preserves_hidden_mode_drafts(qtbot):
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.fit_expr_edit.setPlainText("a*x+b")
    window.root_equations_edit.setPlainText("x^2-A")
    set_mode(window, "root_solving")
    set_mode(window, "fitting")
    assert window.fit_expr_edit.toPlainText() == "a*x+b"
    assert window.root_equations_edit.toPlainText() == "x^2-A"
```

- [ ] **Step 9: Test workspace round trip with hidden drafts**

Capture a workspace after editing two different hidden mode drafts, restore into a fresh window, and assert both drafts survive.

- [ ] **Step 10: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_mode_stack.py tests/test_workspace_controller.py
```

- [ ] **Step 11: Commit**

```bash
git add app_desktop/current_page_stack.py app_desktop/panels.py app_desktop/window.py app_desktop/workspace_controller.py tests/test_desktop_mode_stack.py
git commit -m "refactor: use stacked desktop mode settings"
```

---

## Task 6: Standardize Formula, Parameter, Constants, and Detected-Row Editors

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/schema_widgets.py`
- Modify: `app_desktop/constants_editor.py`
- Modify: `app_desktop/parameter_table.py`
- Modify: `app_desktop/detected_rows_table.py`
- Modify: `app_desktop/formula_preview.py`
- Create: `tests/test_desktop_editor_affordances.py`

- [ ] **Step 1: Keep valid startup formulas while improving placeholders**

For custom extrapolation, error propagation, fitting custom model, implicit model, and root solving:

- Retain valid existing default mathematical expressions where they enable immediate smoke-test calculation, such as custom extrapolation's `(C - B)^2/(B - A) + C`.
- Use schema-bound placeholders for empty/new fields and for fields where no universal default is mathematically valid.
- Keep preview buttons and function-help buttons visible and tooltip-bound.
- Preserve workspace restore behavior: if an old workspace has expression text, restore it as real text, not placeholder.

- [ ] **Step 2: Add reusable editor header factory**

In `schema_widgets.py`, add `make_editor_header(owner, field, *, preview_button=None, function_button=None, help_button=None)`. Use it in `panels.py` to reduce repeated title/help/preview rows.

- [ ] **Step 3: Localize table headers through reusable APIs**

Use existing:

- `ConstantsEditor.set_table_headers(name, value)`
- `DetectedRowsTable.set_headers(headers)`

Add `ParameterTable.set_headers(headers)` if missing, and bind zh/en headers from shared specs.

- [ ] **Step 4: Verify editor APIs are unchanged**

Add tests:

```python
def test_redesigned_parameter_table_keeps_rows_api(qtbot):
    table = ParameterTable()
    table.add_parameter_row({"name": "a", "initial": "1"})
    assert table.rows()[0]["name"] == "a"
    table.set_detected_names(["b"], keep_orphans=False)
    assert [row["name"] for row in table.rows() if row["name"]] == ["b"]
```

Also test constants table/text draft preservation and detected/manual source behavior.

- [ ] **Step 5: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_constants_editor.py tests/test_desktop_editor_affordances.py tests/test_desktop_implicit_model_ui.py tests/test_desktop_root_solving_ui.py
```

- [ ] **Step 6: Commit**

```bash
git add app_desktop/panels.py app_desktop/schema_widgets.py app_desktop/constants_editor.py app_desktop/parameter_table.py app_desktop/detected_rows_table.py app_desktop/formula_preview.py tests/test_desktop_editor_affordances.py
git commit -m "refactor: standardize desktop input editor affordances"
```

---

## Task 7: Move Result-Only Controls Into Result Views

**Files:**
- Modify: `shared/ui_specs.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window_latex_pdf_mixin.py`
- Modify: `app_desktop/window_images_mixin.py`
- Create: `tests/test_desktop_result_workflows.py`

- [ ] **Step 1: Bind result tabs from shared result specs**

Use `DESKTOP_RESULT_VIEWS` to set tab titles, tooltips, attachment keys, and controls for:

- Numeric result.
- Image result.
- Log.
- LaTeX source.
- PDF preview.

- [ ] **Step 2: Move LaTeX/PDF/image controls closer to tabs**

Keep existing attributes:

- `latex_compile_button`
- `latex_save_button`
- `latex_open_button`
- `pdf_zoom_spin`
- `result_plot_zoom_spin`
- `result_plot_page_spin`

Reparent these controls into their corresponding result tab headers. Do not change method names or signal connections.

- [ ] **Step 3: Keep output setup fields that affect calculation in left panel**

Keep calculation-time fields such as `generate_latex_checkbox`, output path, and plot generation checkbox in Output Setup. Move only display/export controls that operate on generated outputs.

- [ ] **Step 4: Add GUI command workflow tests**

In `tests/test_desktop_result_workflows.py`, use fake workers or direct result payload injection to verify:

- CSV export button is enabled after result data exists.
- LaTeX save writes expected source to a temp path.
- PDF preview accepts a small fake/fixture PDF or mocked renderer.
- Image zoom/page buttons change view state without losing `result_plot_bytes`.

- [ ] **Step 5: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_result_workflows.py tests/test_desktop_result_schema_ui.py tests/test_workspace_controller.py
```

- [ ] **Step 6: Commit**

```bash
git add shared/ui_specs.py app_desktop/panels.py app_desktop/window_latex_pdf_mixin.py app_desktop/window_images_mixin.py tests/test_desktop_result_workflows.py
git commit -m "refactor: bind desktop result views from shared specs"
```

---

## Task 8: Add Realistic GUI Click Workflows

**Files:**
- Create: `tests/test_desktop_gui_workflows.py`
- Modify: `docs/TEST_MATRIX.md`

- [ ] **Step 1: Add one minimal user workflow per mode**

Use pytest-qt to simulate user actions, not only private method calls:

- Extrapolation: paste small table, select a method, click Run, verify result text.
- Error propagation: paste data, fill formula, click Run, verify result and LaTeX text.
- Fitting: paste data, fill custom model, detect parameters, click Run with fake worker or tiny real data, verify parameter output.
- Root solving: fill `x^2-A`, unknown `x`, constant/input `A`, click Run, verify root result and optional plot bytes.
- Statistics: paste values, click Run, verify mean/std output.

Every workflow that clicks Run must wait for completion before asserting output. Use one of these patterns:

```python
qtbot.waitUntil(lambda: not window._is_any_worker_running(), timeout=10_000)
assert "expected text" in window.result_edit.toPlainText()
```

or connect to the relevant worker `finished_ok` signal with `qtbot.waitSignal(...)` when the test constructs the worker directly. Immediate assertions after a Run click are not allowed.

- [ ] **Step 2: Add export and workspace round trip in workflows**

At least one workflow must:

- Save workspace to a temporary `.datalab`.
- Reopen it.
- Verify input, config, result text, CSV data, LaTeX text, image bytes, and selected result tab restore.

- [ ] **Step 3: Add bilingual workflow pass**

Run one representative workflow after `_apply_language("en")` and one after `_apply_language("zh")`; assert visible result/log messages use the active language where localized code paths exist.

- [ ] **Step 4: Update test matrix**

Replace the stale sentence “Automated tests do not click through the desktop GUI” with the new release gate:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_gui_redesign_scan.py tests/test_desktop_bilingual_inventory.py
python tools/scan_desktop_gui_schema.py
```

- [ ] **Step 5: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_desktop_gui_workflows.py docs/TEST_MATRIX.md
git commit -m "test: add desktop gui click workflows"
```

---

## Task 9: Add Bilingual Runtime Inventory and Accessibility Gate

**Files:**
- Create: `tests/test_desktop_bilingual_inventory.py`
- Modify: `tools/scan_desktop_gui_schema.py`
- Modify: `shared/help_specs.json` only for missing texts
- Modify: `shared/ui_specs.py` only for missing specs

- [ ] **Step 1: Enumerate visible text after language switches**

The test must visit every mode/submode/result tab and enumerate:

- `QLabel`
- `QPushButton`
- `QCheckBox`
- `QAction`
- `QTabBar` tab titles/tooltips
- `QLineEdit` placeholders/tooltips
- `QPlainTextEdit` placeholders/tooltips
- `QComboBox` item texts/tooltips
- `QTableWidget` headers

- [ ] **Step 2: Fail on missing required affordances**

For visible user-input controls, fail if both are missing:

- A direct tooltip/accessibility description.
- A nearby schema help button bound to the same schema key.

- [ ] **Step 3: Add allowlist only for deliberate technical labels**

Allowlist values such as `A`, `B`, `x`, `y`, `PDF`, `CSV`, `LaTeX`, and icon-only buttons with accessible names. Store allowlist in the test file, not scattered in application code.

- [ ] **Step 4: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_bilingual_inventory.py
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_desktop_bilingual_inventory.py tools/scan_desktop_gui_schema.py shared/help_specs.json shared/ui_specs.py
git commit -m "test: add desktop bilingual ui inventory gate"
```

---

## Task 10: Visual Polish With Centralized Theme Tokens

**Files:**
- Create: `app_desktop/theme.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/section_panel.py`
- Modify: `app_desktop/schema_widgets.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_desktop_theme_tokens.py`

- [ ] **Step 1: Centralize spacing and style constants**

Create `app_desktop/theme.py` with:

```python
PANEL_MARGIN = 10
SECTION_SPACING = 8
CONTROL_SPACING = 6
MIN_LEFT_PANEL_WIDTH = 420
SUPPORTED_MIN_WINDOW_WIDTH = 1280
```

Add helper functions for stylesheets already repeated in `panels.py`, including scrollbars and compact buttons.

- [ ] **Step 2: Use restrained scientific workbench styling**

Apply:

- Clear section headers.
- Stable compact action rows.
- No nested card styling.
- Neutral background with subtle separators.
- Sufficient contrast for light/dark system themes.
- Stable table widths and no content-overflow horizontal scrollbar.

- [ ] **Step 3: Reapply theme on runtime palette changes**

In `app_desktop/window.py`, handle Qt palette changes:

```python
def changeEvent(self, event):  # noqa: N802 - Qt API
    super().changeEvent(event)
    if event.type() == QEvent.Type.PaletteChange:
        self._apply_desktop_theme()
```

Add `_apply_desktop_theme()` in the desktop shell/theme integration layer and call it during UI construction and on palette change. The method must update centralized styles only; it must not reset user data, current mode, splitter sizes, or result state.

- [ ] **Step 4: Test theme constants and supported sizes**

Add `tests/test_desktop_theme_tokens.py`:

```python
def test_supported_left_panel_width_is_not_smaller_than_known_minimum():
    from app_desktop.theme import MIN_LEFT_PANEL_WIDTH
    assert MIN_LEFT_PANEL_WIDTH >= 420
```

Also assert the scan tool uses the same constants instead of hardcoded conflicting widths.

- [ ] **Step 5: Test palette change does not reset state**

Add a test that fills a formula field, switches mode, calls `_apply_desktop_theme()` or sends a `QEvent.PaletteChange`, and asserts the field text/current mode remain unchanged.

- [ ] **Step 6: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_theme_tokens.py tests/test_desktop_shell_layout.py tests/test_desktop_gui_redesign_scan.py
```

- [ ] **Step 7: Commit**

```bash
git add app_desktop/theme.py app_desktop/panels.py app_desktop/section_panel.py app_desktop/schema_widgets.py app_desktop/window.py tests/test_desktop_theme_tokens.py
git commit -m "style: centralize desktop workbench theme"
```

---

## Task 11: Examples and Documentation Entry Points

**Files:**
- Modify: `examples/catalog.py` if present, otherwise create a small catalog adapter matching existing example-loading code.
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `docs/desktop/*.md`
- Modify: `docs/web/*.md` only where shared user-facing concepts change
- Create: `tests/test_desktop_examples_entrypoint.py`

- [ ] **Step 1: Expose example workspaces in the workbench bar**

Use the existing `open_example_workspace` flow. Add a compact Example button/dropdown to the top workbench bar. Do not allow saving back into bundled examples; preserve the existing save-as behavior for example templates.

- [ ] **Step 2: Add contextual help entry points**

Add Docs and Function Help actions in locations that match user workflow:

- Formula editors: function help.
- Mode sections: mode help.
- Result tabs: export/LaTeX/PDF help.

All help strings must come from `shared/help_specs.json` or `shared/ui_specs.py`. `formula_help.py` may remain as a compatibility facade, but after Task 2b it must read the same shared help specs instead of owning separate dictionaries.

- [ ] **Step 3: Update desktop docs for the new shell**

Update desktop docs to describe:

- Workbench bar.
- Sectioned input flow.
- Formula preview.
- Parameters/constants tables.
- Result tabs and exports.
- Example workspace behavior.

- [ ] **Step 4: Test bundled resource discoverability**

Add test that imports the docs/example loader and asserts all referenced docs and example workspaces resolve under PyInstaller-style resource lookup.

- [ ] **Step 5: Run focused tests**

```bash
pytest -q tests/test_desktop_examples_entrypoint.py tests/test_desktop_docs_resources.py tests/test_packaging_resources.py
```

If one of these test files does not exist, create the missing test in the same task and include it in this command.

- [ ] **Step 6: Commit**

```bash
git add examples app_desktop/panels.py app_desktop/window.py docs/desktop docs/web tests/test_desktop_examples_entrypoint.py tests/test_desktop_docs_resources.py tests/test_packaging_resources.py
git commit -m "docs: document redesigned desktop workbench"
```

---

## Task 12: Workspace State Hardening

**Files:**
- Modify: `app_desktop/workspace_controller.py`
- Modify: `tests/test_workspace_controller.py`

- [ ] **Step 1: Reuse existing workspace widget helpers**

Do not create `app_desktop/workspace_ui_adapters.py`. Reuse and, if necessary, minimally extend existing helpers in `workspace_controller.py`: `_text`, `_set_text`, `_checked`, `_value`, `_combo_data`, and `_set_combo_data`. This task is about preserving state after reparenting, not adding a new abstraction layer.

- [ ] **Step 2: Preserve legacy manifest compatibility**

Keep existing manifest keys, attachment paths, and config field names. Add tests using existing workspace fixtures and one new fixture saved from the redesigned shell.

- [ ] **Step 3: Test moved widgets restore correctly**

Test restoring after widgets are reparented into shell sections and result tab headers. Verify:

- Current mode.
- Hidden mode drafts.
- Constants/parameters table contents.
- Result text/log/LaTeX/CSV/image bytes.
- Selected result tab and zoom/page state where already persisted.

- [ ] **Step 4: Restore persisted tab indices**

`_capture_ui` already records `main_tab` and `result_subtab`. Update `restore_workspace` to restore active tab indices only after the corresponding tab widgets have been constructed and result attachments have been restored:

```python
ui_state = manifest.get("ui", {}) if isinstance(manifest.get("ui"), dict) else {}
main_tab = int(ui_state.get("main_tab", 0) or 0)
result_subtab = int(ui_state.get("result_subtab", 0) or 0)
if hasattr(window, "tabs") and 0 <= main_tab < window.tabs.count():
    window.tabs.setCurrentIndex(main_tab)
if hasattr(window, "result_tabs") and 0 <= result_subtab < window.result_tabs.count():
    window.result_tabs.setCurrentIndex(result_subtab)
```

Clamp invalid indices instead of raising, so old/corrupt workspaces still open.

- [ ] **Step 5: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_controller.py tests/test_workspace_io.py tests/test_workspace_auto_fit_migration.py
```

- [ ] **Step 6: Commit**

```bash
git add app_desktop/workspace_controller.py tests/test_workspace_controller.py
git commit -m "refactor: harden desktop workspace ui adapters"
```

---

## Task 13: Screenshot and Geometry Artifacts for Review

**Files:**
- Create: `tools/capture_desktop_gui_screens.py`
- Create: `tests/test_desktop_gui_screenshot_smoke.py`
- Modify: `docs/TEST_MATRIX.md`

- [ ] **Step 1: Add deterministic screenshot capture tool**

The tool must:

- Set `QT_QPA_PLATFORM=offscreen` when not already set.
- Open `ExtrapolationWindow`.
- Capture images for zh/en and each main mode.
- Save artifacts under a caller-provided directory, defaulting to `build/gui-screenshots`.
- Emit JSON with paths, window size, mode, language, and issue count.

- [ ] **Step 2: Add smoke test for screenshot generation**

Test that screenshot files are non-empty and dimensions match the requested size. Avoid brittle pixel goldens in the first pass.

- [ ] **Step 3: Add manual visual review command to test matrix**

Document:

```bash
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

- [ ] **Step 4: Run focused tests**

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_screenshot_smoke.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

- [ ] **Step 5: Commit**

```bash
git add tools/capture_desktop_gui_screens.py tests/test_desktop_gui_screenshot_smoke.py docs/TEST_MATRIX.md
git commit -m "test: add desktop gui screenshot smoke artifacts"
```

---

## Task 14: Final Quality Gate and Packaging Resource Check

**Files:**
- Modify: `docs/TEST_MATRIX.md`
- Modify: `.github/workflows/*.yml` if workflows exist or are introduced by the project owner
- Modify: `DataLab.spec` only if docs/examples/help resources are missing from bundles

- [ ] **Step 1: Run full local gate**

```bash
python -m compileall -q .
QT_QPA_PLATFORM=offscreen pytest -q
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
```

- [ ] **Step 2: Run packaging resource check**

Build not required in this plan unless execution owner chooses release work, but resource lookup must be tested:

```bash
pytest -q tests/test_packaging_resources.py tests/test_desktop_docs_resources.py
```

If these tests reveal missing bundled docs/examples/help, update `DataLab.spec` with explicit data entries and rerun the tests.

- [ ] **Step 3: Manual source-mode GUI smoke**

Run:

```bash
python data_extrapolation_gui.py
```

Manually verify:

- Workbench bar actions are visible.
- Splitter cannot hide the left controls.
- No horizontal scrollbar appears in the left panel.
- Formula preview dialogs are readable.
- Constants/parameters tables can add/remove rows.
- Run/Stop buttons reflect worker state.
- Result, Log, LaTeX, PDF Preview, and Image tabs are reachable.
- Language switch refreshes visible text/tooltips.

- [ ] **Step 4: Update test matrix with final gate**

`docs/TEST_MATRIX.md` must list the exact command block above and state that a release cannot proceed while the scan reports issues or screenshot capture fails.

- [ ] **Step 5: Commit**

```bash
git add docs/TEST_MATRIX.md DataLab.spec .github/workflows
git commit -m "test: document desktop gui redesign release gate"
```

If `.github/workflows` is unchanged or absent, omit it from `git add`.

---

## External Review Requirements

Before execution, this plan must pass:

- Codex self-review against `docs/ARCHITECTURE.md`, current source files, and the three subagent findings.
- Gemini Pro / Antigravity-style read-only adversarial review of this plan and relevant files.
- Claude read-only adversarial review of this plan and relevant files.

Accepted findings must be patched into this plan. Rejected findings must be documented in `findings.md` with the reason. Execution should not begin until there are no accepted unresolved high/medium findings.

Current review status for this revision:

- Codex/subagent review: complete; findings incorporated.
- Claude read-only adversarial review: complete; findings incorporated.
- AGY/Gemini Pro adversarial review: first pass rejected with nine actionable findings; all were incorporated. Second pass returned `PASS` with no findings.

## Final Verification Matrix

Run after all implementation tasks:

```bash
python -m compileall -q .
QT_QPA_PLATFORM=offscreen pytest -q tests/test_ui_schema.py tests/test_desktop_ui_schema_binder.py tests/test_desktop_ui_schema_runtime.py tests/test_desktop_shared_ui_specs.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_redesign_scan.py tests/test_desktop_shell_layout.py tests/test_desktop_mode_stack.py tests/test_desktop_editor_affordances.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_gui_workflows.py tests/test_desktop_bilingual_inventory.py tests/test_desktop_result_workflows.py tests/test_desktop_gui_screenshot_smoke.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_controller.py tests/test_workspace_io.py tests/test_workspace_auto_fit_migration.py
pytest -q tests/test_packaging_resources.py tests/test_desktop_docs_resources.py tests/test_desktop_examples_entrypoint.py
python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
QT_QPA_PLATFORM=offscreen pytest -q
```

Manual smoke before release:

```bash
python data_extrapolation_gui.py
```

Manual smoke must cover all modes, both languages, splitter drag boundaries, formula previews, add/remove table rows, constants text/table view, LaTeX save/compile path, PDF preview, image preview, workspace save/open, and example workspace save-as behavior.
