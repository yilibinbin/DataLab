# DataLab LaTeX, Input, and Constants Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GUI-generated LaTeX compilation reliable and verifiable, remove redundant constants enable toggles, and unify manual/file data plus constants into the left input rail with adaptive layout and current-language help.

**Architecture:** Keep parsing, validation, and serialization in shared/data-controller layers, not Qt widgets. The left rail owns mode selection first, then data input, then mode-conditional constants input; calculation modules consume a single content-derived input bundle. Workspace migration, constants alias collapse, and GUI visibility changes are one release unit because shipping any subset can corrupt restored constants state.

**Tech Stack:** PySide6 desktop GUI, existing `datalab_latex` writers, `shared.input_normalization`, `app_desktop` workbench panels/controllers, pytest/pytest-qt, real local LaTeX engines (`DATALAB_LATEX_ENGINE`, `xelatex`, `pdflatex`, then `tectonic` if installed).

---

## Current Evidence and Review Status

- Existing focused LaTeX baseline passed on 2026-06-15:
  - `QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_compile_e2e.py tests/test_latex_compile_worker.py tests/test_desktop_latex_compile_ui.py tests/test_latex_tables_unit.py tests/test_latex_generation_consistency.py tests/test_latex_group_size_zero.py tests/test_sisetup_block.py tests/test_siunitx_column_spec_regression.py`
  - Result: `31 passed`.
- Local engine discovery showed `tectonic` is not on PATH, while `/opt/homebrew/bin/pdflatex` and `/opt/homebrew/bin/xelatex` exist. A user-visible GUI compile failure can therefore be an engine-selection/runtime-path bug even when generated `.tex` is valid.
- The user screenshot maps to `app_desktop/panels.py` still constructing `self.manual_table = QTableWidget(6, 3)`. This causes a fixed blank input block. `app_desktop/views/helpers.py::fit_table_height_to_contents()` exists, but it currently keys off `rowCount()`, so an empty six-row table still renders six visible rows.
- The worktree already contains partial, unstaged input/constants changes:
  - `shared/input_normalization.py` already defines `InputSections` and `parse_input_sections()`.
  - `shared.input_normalization.ConstantsState.compute_dict()` is already content-driven and no longer returns `{}` solely because `enabled=False`.
  - `app_desktop/fitting_input_normalization.py` already imports/re-exports some shared constants helpers.
  - `app_desktop/panels.py` already creates `input_constants_editor` and aliases `error_constants_editor`, `custom_constants_editor`, `implicit_constants_editor`, and `root_constants_editor` to it.
  - `app_desktop/window.py::_update_constants_visibility()` already exists, but mutates `input_constants_editor._numeric_mode` privately.
  - `tests/test_shared_input_sections.py` already exists as an untracked test file.
- The partial constants alias collapse is not yet safe to ship. Legacy workspaces can contain different per-mode constants; restoring them into one shared editor without mode-scoped migration creates last-write-wins corruption.
- Antigravity/Gemini review accepted additions:
  - Use silent validation while editing and strict validation only on Run.
  - Add left-rail height budget and scroll safety.
  - Prefer installed local TeX engines before Tectonic when offline or Tectonic is unavailable.
  - Add bilingual warnings for legacy workspaces with disabled-but-nonempty constants drafts.
- Claude review accepted corrections:
  - Treat current unstaged parser/constants work as current state, not future work.
  - Fix actual root LaTeX writer path to `app_desktop/root_latex_writer.py`.
  - Add public `ConstantsEditor.set_numeric_mode()`; do not mutate `_numeric_mode` externally.
  - Prevent section parser regressions for legacy bracket-containing data.
  - Do not ship between constants alias collapse and workspace migration.
  - Compile actual GUI-generated `.tex`, not hand-written fixture documents.

## Final Decisions

1. **Constants are content-driven.** Non-empty valid constants are active; empty constants are inactive. The visible `启用常数设置 / Enable constants` checkbox is removed. Legacy `enabled` stays only as migration metadata.
2. **Constants are input data.** Constants move to the left input card. The middle parameter/workbench area must not contain a separate constants editor.
3. **One shared parser.** Sectioned text/file input is parsed by `shared.input_normalization.parse_input_sections()`. Desktop fitting must not keep a divergent constants parser.
4. **Sectioned input v1 grammar.**

```text
# DataLab input v1
[data]
A B C
1.0 2.0 3.0
1.1 2.1 3.1

[constants]
CR = 3.2898419602500(36)[+9]
M  = 7294.29954171(17)
```

5. **Legacy plain data remains accepted.** If no recognized `[data]` or `[constants]` section is present, all text is data. Unknown `[header]` should only become an error after explicit section mode starts or when a recognized DataLab section exists, so old data containing bracketed text does not regress silently.
6. **Mode-specific constants visibility.** Constants panel is visible only for modes/models that consume constants:
   - Error propagation.
   - Root solving.
   - Fitting custom model.
   - Fitting self-consistent/implicit model.
   - Hidden for extrapolation/statistics and built-in fitting models unless a later formula source actually consumes constants.
7. **Shared constants numeric grammar is broad at the editor boundary.** The unified editor accepts both plain numeric values and bracket uncertainty values everywhere. Computation collectors parse the active constants according to their own numerical requirements at Run time and report current-language validation errors there. This prevents a valid error/root constant such as `1.23(4)` from becoming invalid merely because the user switches to a fitting model view.
8. **LaTeX compile reliability is a GUI-boundary requirement.** Low-level table helper tests are insufficient. The release gate must generate `.tex` via desktop code paths and compile option combinations with the first available local engine.
9. **No shippable intermediate state.** Tasks 2, 4, and 5 form a single release unit. Do not release after only hiding/remounting constants editors unless workspace migration and computation collectors are also updated.

## File Map

- Modify `shared/input_normalization.py`: section parser guardrails, content-driven constants tests, shared constants text/row conversion.
- Modify `app_desktop/fitting_input_normalization.py`: re-export shared constants helpers and remove duplicated behavior.
- Modify `app_desktop/constants_editor.py`: remove visible enable checkbox, add public numeric-mode setter, keep compatibility methods.
- Modify `app_desktop/panels.py`: move mode section to top, use one-row adaptive manual table, mount constants under input data, remove fixed blank heights.
- Modify `app_desktop/views/helpers.py`: make table height depend on populated rows plus one draft row, not raw `rowCount()`.
- Modify `app_desktop/window_data_mixin.py`: parse combined data/constants text and files into one input bundle.
- Modify `app_desktop/window.py`, `app_desktop/views/error.py`, `app_desktop/views/fitting.py`, `app_desktop/views/root_solving.py`, `app_desktop/workbench_specs.py`: remove middle constants mounts, update mode-specific visibility, avoid private `_numeric_mode` mutation.
- Modify `app_desktop/workspace_controller.py`: mode-scoped legacy constants restore and new unified constants capture.
- Modify LaTeX writers and compile path as needed, especially `app_desktop/window_latex_pdf_mixin.py`, `app_desktop/root_latex_writer.py`, `app_desktop/fitting_latex_writer.py`, and `datalab_latex/*`.
- Create/update `tools/latex_option_matrix.py` and `tests/test_latex_option_matrix.py`.
- Update docs/examples/tests: `docs/TEST_MATRIX.md`, `docs/desktop/guide.zh.md`, `docs/desktop/guide.en.md`, `examples/README.md`, `tools/generate_example_workspaces.py`, GUI schema/screenshot tests.

---

## Task 1: Reproduce and Gate GUI LaTeX Failures

**Files:**
- Create: `tools/latex_option_matrix.py`
- Create: `tests/test_latex_option_matrix.py`
- Modify: `tests/test_desktop_latex_compile_ui.py`
- Modify: `docs/TEST_MATRIX.md`
- Inspect: `app_desktop/window_latex_pdf_mixin.py`
- Inspect: `app_desktop/root_latex_writer.py`
- Inspect: `app_desktop/fitting_latex_writer.py`
- Inspect: `datalab_latex/`

- [x] **Step 1: Add GUI-generated LaTeX option matrix tests**

Add cases that generate `.tex` through the same desktop writer paths used by the GUI. Cover at minimum:
- Error propagation with uncertainty constants.
- Statistics with bracket uncertainty values.
- Fitting custom model with formula summary and parameter table.
- Root solving with root uncertainty output.
- Extrapolation segmented table.

Use this test shape:

```python
@pytest.mark.parametrize("use_dcolumn", [False, True])
@pytest.mark.parametrize("group_size", [0, 3, 4])
@pytest.mark.parametrize("caption", ["", "中文标题", "English caption"])
def test_gui_generated_latex_options_compile(tmp_path, use_dcolumn, group_size, caption):
    tex_path = build_desktop_generated_tex(
        tmp_path,
        module="root_solving",
        use_dcolumn=use_dcolumn,
        group_size=group_size,
        caption=caption,
    )
    result = compile_latex_with_available_engine(tex_path)
    assert result.ok or result.skipped_missing_engine
```

- [x] **Step 2: Implement `tools/latex_option_matrix.py`**

The tool must:
- Generate GUI-style `.tex` into `build/latex-option-matrix/`.
- Discover engines in order: `DATALAB_LATEX_ENGINE`, `xelatex`, `pdflatex`, `tectonic`.
- Write `manifest.json` with `module`, `use_dcolumn`, `group_size`, `caption_kind`, `engine`, `engine_path`, `returncode`, `tex_path`, `pdf_path`, `status`, and first error excerpt.
- Treat missing engines as explicit `skipped_missing_engine`, not as a pass.
- Compile actual generated `.tex`; do not compile hand-written fixtures.

- [x] **Step 3: Run matrix before code fixes**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_option_matrix.py -vv
python tools/latex_option_matrix.py --out build/latex-option-matrix --json
```

Expected:
- If `.tex` is invalid, preserve the engine log in `build/latex-option-matrix/manifest.json`.
- If all generated `.tex` compiles locally, continue because the user-visible bug may be GUI engine selection or packaged runtime discovery.

- [x] **Step 4: Harden GUI compile path tests**

Extend `tests/test_desktop_latex_compile_ui.py` to assert:
- Compile starts a worker and returns control to the GUI quickly.
- If `tectonic` is missing but `xelatex` or `pdflatex` exists, the GUI does not stop at a vague `tectonic` failure.
- The status/log reports selected engine, fallback engine, and engine path.
- `use_dcolumn`, `group_size`, caption text, and current language affect generated `.tex` before compilation.

- [x] **Step 5: Update release matrix**

Add:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_option_matrix.py tests/test_desktop_latex_compile_ui.py
python tools/latex_option_matrix.py --out build/latex-option-matrix --json
```

## Task 2: Finalize Shared Sectioned Input and Constants Semantics

**Files:**
- Modify: `shared/input_normalization.py`
- Modify: `app_desktop/fitting_input_normalization.py`
- Modify: `tests/test_shared_input_sections.py`
- Modify: `tests/test_fitting_input_normalization.py`

- [x] **Step 1: Lock parser behavior with tests**

Add/adjust tests for:
- Legacy plain table remains data-only.
- `[data]` plus `[constants]` parses both sections.
- `[DATA]` and `[Constants]` are accepted.
- Duplicate `[data]` or duplicate `[constants]` fails with line number and bilingual text.
- Unknown headers fail only in explicit DataLab section mode.
- Legacy data containing bracketed uncertainty/exponent strings remains accepted.
- Constants accept `name value` and `name = value`.

- [x] **Step 2: Harden `parse_input_sections()`**

Update `shared.input_normalization.parse_input_sections(text)` so it returns:

```python
@dataclass(frozen=True)
class InputSections:
    data_text: str
    constants_text: str
    explicit_sections: bool
```

Rules:
- If no recognized section header appears, all text is data.
- Recognized section headers are case-insensitive `[data]` and `[constants]`.
- Duplicate recognized headers error.
- Unknown bracketed headers error only when explicit section parsing has begun or another recognized section exists.

- [x] **Step 3: Preserve content-driven constants**

Keep `ConstantsState.compute_dict(validate=True)` content-driven:
- Empty rows/text return `{}`.
- Non-empty complete rows return a dict even if legacy `enabled=False`.
- Draft/incomplete rows are ignored only when `validate=False`.
- Draft/incomplete rows fail on Run when `validate=True`.

- [x] **Step 4: Remove duplicated desktop constants behavior**

Ensure `app_desktop/fitting_input_normalization.py` imports/re-exports shared helpers:

```python
from shared.input_normalization import (
    ConstantsState,
    constants_rows_to_text,
    normalize_constants_state,
    parse_constants_text,
)
```

Keep fitting parameter-row logic local unless sharing it reduces code.

## Task 3: Rebuild Left Rail Order and Adaptive Data Table

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/views/helpers.py`
- Modify: `tests/test_desktop_workbench_data_area.py`
- Modify: `tests/test_desktop_gui_schema_scan.py`
- Modify: `tools/scan_desktop_gui_schema.py`
- Modify: `tools/capture_desktop_gui_screens.py`

- [x] **Step 1: Add layout regression tests**

Tests must assert:
- Calculation mode section is first in the left rail.
- Empty manual table starts with one visible editable row, not six blank rows.
- Empty table/card height is near one-row height.
- Adding populated rows grows height up to max; clearing rows shrinks height.
- No horizontal scrollbar appears in left rail at 1280, 1440, and 1680 width captures.

- [x] **Step 2: Change table construction**

In `app_desktop/panels.py`, change:

```python
self.manual_table = QTableWidget(6, 3)
```

to:

```python
self.manual_table = QTableWidget(1, 3)
```

Do not compensate with a larger `setMinimumHeight()`.

- [x] **Step 3: Fix adaptive table height helper**

Implement `fit_table_height_to_contents(table, min_rows=1, max_rows=8)` using populated rows plus one draft row:

```python
def _populated_row_count(table: QTableWidget) -> int:
    count = 0
    for row in range(table.rowCount()):
        if any(
            table.item(row, col) is not None and table.item(row, col).text().strip()
            for col in range(table.columnCount())
        ):
            count = row + 1
    return count

visible_rows = max(min_rows, min(_populated_row_count(table) + 1, max_rows))
```

Clamp by max rows and set both minimum and maximum height to the computed value.

- [x] **Step 4: Wire adaptive updates**

Call the helper after:
- Table construction.
- Add/remove row.
- Add/remove column.
- Clear.
- Paste.
- Workspace restore.
- Mode column sync.
- Text/table view switch.

- [x] **Step 5: Reorder left rail**

In `build_left_panel()`, order sections:
1. `mode_section`
2. `input_section`
3. `output_setup_section`
4. `run_section`

## Task 4: Move Constants Into the Input Card Safely

**Files:**
- Modify: `app_desktop/constants_editor.py`
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/views/error.py`
- Modify: `app_desktop/views/fitting.py`
- Modify: `app_desktop/views/root_solving.py`
- Modify: `app_desktop/workbench_specs.py`
- Modify: `tests/test_constants_editor.py`
- Modify: `tests/test_desktop_workbench_variable_panel.py`

- [x] **Step 1: Remove visible enable checkbox**

Keep compatibility methods but remove the visible switch:
- `isChecked()` returns whether `constants_dict(validate=False)` is non-empty.
- `setChecked(False)` must not clear constants.
- `self.checkbox` is hidden or removed from layout.

- [x] **Step 2: Add public numeric mode setter**

Add:

```python
def set_numeric_mode(self, mode: str) -> None:
    if mode not in {"uncertainty", "mpmath"}:
        raise ValueError(f"Unsupported constants numeric mode: {mode}")
    if self._numeric_mode != mode:
        self._numeric_mode = mode
        self._emit_changed()
```

Update callers to use this method. No external code may mutate `_numeric_mode`.

- [x] **Step 3: Implement and test broad constants grammar**

The constants editor accepts both plain numeric values and bracket uncertainties in all modes. Computation collectors parse the values according to their own needs at Run time and surface current-language validation errors there.

Tests must cover switching from error/root mode to fitting custom mode with an existing `1.23(4)` value.

- [x] **Step 4: Mount constants under input data**

Use one widget:

```python
self.input_constants_editor = ConstantsEditor(min_rows=1, checked=False, numeric_mode="uncertainty")
self.input_section_layout.addWidget(self.input_constants_editor)
self.error_constants_editor = self.input_constants_editor
self.custom_constants_editor = self.input_constants_editor
self.implicit_constants_editor = self.input_constants_editor
self.root_constants_editor = self.input_constants_editor
```

The editor is visually part of the input card, below manual/file data.

- [x] **Step 5: Remove middle-panel constants mounts**

Update `MODE_WORKBENCH_SPECS` and view builders so constants no longer render in the middle configuration panel. Parameter tables, unknown variables, bounds, and formulas remain in the middle panel.

- [x] **Step 6: Mode/model-specific visibility**

Use a single function:

```python
def _mode_uses_constants(owner) -> bool:
    mode = owner.mode_combo.currentData()
    if mode in {"error", "root_solving"}:
        return True
    if mode == "fitting":
        return owner.fit_model_combo.currentData() in {"custom", "self_consistent"}
    return False
```

Call it from mode changes and fitting-model changes. Hidden constants remain preserved but inactive only if empty; non-empty constants still serialize.

## Task 5: Unified File/Text Input Bundle and Workspace Migration

**Files:**
- Modify: `app_desktop/window_data_mixin.py`
- Modify: `app_desktop/window.py`
- Modify: `app_desktop/window_error_mixin.py` if present
- Modify: `app_desktop/window_fitting_models_mixin.py`
- Modify: `app_desktop/window_root_solving_mixin.py` if present
- Modify: `app_desktop/workspace_controller.py`
- Modify: `tests/test_workspace_controller.py`
- Modify: `tests/test_workspace_io.py`

- [x] **Step 1: Add active input bundle**

Create:

```python
@dataclass(frozen=True)
class InputBundle:
    data_path: str
    data_text: str
    constants_text: str
    constants_rows: tuple[dict[str, str], ...]
    source_kind: str
    explicit_sections: bool
```

Add `_active_input_bundle(self) -> InputBundle` in `window_data_mixin.py`.

- [x] **Step 2: Route data and constants collection through the bundle**

Keep `_active_data_source()` as a compatibility wrapper returning only data. Update these consumers to use the bundle:
- Error propagation constants collection.
- Custom fitting constants collection.
- Implicit fitting constants collection.
- Root solving constants payload.

- [x] **Step 3: Parse sectioned data files/text**

When the active data source is text or a file:
- Run `parse_input_sections()`.
- Put `[data]` content into the data parser.
- Put `[constants]` content into the shared constants state unless the left constants table has explicit user-entered content.
- Define and test precedence: left constants table/text overrides file constants when both are non-empty.

- [x] **Step 4: Workspace capture remains v1-compatible**

Do not add a duplicate `workspace["input"]` object in this release. The current workspace schema and `WorkbenchModel.to_v1_workspace()` persist canonical v1 top-level `data` and `constants`; adding a parallel `input` object would create two write sources before the v2 reader/writer boundary is ready.

The unified runtime semantics are therefore mirrored into existing top-level `workspace["data"]` and `workspace["constants"]`. Existing v2-ish manifests with `manifest["data"]["input"]` and `manifest["data"]["constants"]` continue to be accepted by the reader compatibility path and normalized to v1 fields.

- [x] **Step 5: Workspace restore without last-write-wins corruption**

Restore order:
1. If new unified `input.constants` exists, restore it.
2. Else restore only the legacy constants block for the current saved mode/model.
3. Do not merge all legacy per-mode constants into the shared editor.
4. If legacy constants have `enabled=false` and non-empty content, show one current-language warning that constants are now content-driven.

Tests must create a workspace with different legacy constants in error/custom/root fields and prove only the saved active mode's constants restore into `input_constants_editor`.

## Task 6: Help Text, Labels, and Documentation

**Files:**
- Modify: `shared/ui_specs.py`
- Modify: `app_desktop/views/helpers.py`
- Modify: `docs/desktop/guide.zh.md`
- Modify: `docs/desktop/guide.en.md`
- Modify: `examples/README.md`
- Modify: `tools/generate_example_workspaces.py`

- [x] **Step 1: Update input help**

Every input-facing `?` tooltip must explain in the current UI language:
- Plain table input.
- Sectioned `[data]` and `[constants]` input.
- Constants are active when filled.
- Empty constants are ignored.
- Bracket uncertainty syntax is accepted where the mode supports it.

- [x] **Step 2: Update mode-specific help**

For modes without constants, do not mention constants. For modes with constants, help must say constants are entered in the left input card, not in the middle configuration panel.

- [x] **Step 3: Update labels**

All visible constants/input table headers must be localized through the existing language registry. No raw English-only `name`, `value`, `constant`, or `data` headers in the GUI.

- [x] **Step 4: Regenerate examples**

Add sectioned input examples for:
- Error propagation with constants.
- Root solving with constants.
- Custom fitting with constants.
- Implicit fitting with constants.

Each bundled example must open as a template and run its default calculation in GUI tests.

## Task 7: End-to-End Validation and Release Gates

**Files:**
- Modify: `docs/TEST_MATRIX.md`
- Modify: tests touched by Tasks 1-6.

- [x] **Step 1: Focused tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_latex_option_matrix.py tests/test_desktop_latex_compile_ui.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_constants_editor.py tests/test_shared_input_sections.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_data_area.py tests/test_desktop_workbench_variable_panel.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_workspace_controller.py tests/test_workspace_io.py
```

- [x] **Step 2: GUI schema and screenshot scans**

Run:

```bash
QT_QPA_PLATFORM=offscreen python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots-input-unification --width 1440 --height 900
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots-input-unification-1280 --width 1280 --height 800
```

Acceptance:
- No horizontal scrollbar in the left rail.
- Mode selector appears above input.
- Empty data table has no fixed six-row blank block.
- Constants panel appears only where usable.
- All visible input fields have current-language labels and help.

- [x] **Step 3: LaTeX option matrix**

Run:

```bash
python tools/latex_option_matrix.py --out build/latex-option-matrix --json
```

Acceptance:
- Every generated `.tex` compiles with an available engine or records a precise missing-engine skip.
- dcolumn on/off, group size 0/3/4, and CJK captions are covered.
- The manifest path and summary are logged to `progress.md`.

- [x] **Step 4: Static/release gates**

Run:

```bash
python -m ruff check app_desktop app_web datalab_core datalab_latex fitting shared tests tools
python -m compileall -q app_desktop app_web datalab_core datalab_latex fitting shared tests tools
git diff --check
```

## Review Completion Criteria

- Codex main-thread review confirms every user requirement maps to a task.
- Antigravity/Gemini review findings are either fixed in this plan or explicitly rejected with evidence.
- Claude review findings are either fixed in this plan or explicitly rejected with evidence.
- Implementation can start only after no accepted plan-level findings remain.

## Self-Review Against User Requirements

- LaTeX compile failure and option testing: Tasks 1 and 7.
- Adaptive table/input blank-space behavior: Task 3.
- Remove `启用常数设置`: Task 4.
- Treat constants as input data: Tasks 4 and 5.
- Single-file text format for data/constants: Tasks 2 and 5.
- Manual table constants section in left input column: Task 4.
- Calculation mode moved to top: Task 3.
- Mode-specific constants visibility: Task 4.
- Updated `?` help content: Task 6.
- Codex/Gemini/Claude review loop: Review Completion Criteria.
