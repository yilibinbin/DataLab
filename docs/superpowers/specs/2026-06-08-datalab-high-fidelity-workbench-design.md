# DataLab High-Fidelity Workbench Design

## Purpose

DataLab should move from a technically functional three-pane shell to a high-fidelity scientific workbench that matches the approved sketch more closely. The first implementation slice covers the common workbench shared by all computation modes. Mode-specific polish comes after the shared shell and component contracts are stable.

This design is visual and structural. It must not rewrite numerical backends, workspace semantics, schema/help ownership, parameter parsing, constants parsing, result export, or update behavior.

## Review Status

The architecture direction was reviewed through:

- Main-thread Codex review against the current codebase.
- Codex top-model subagent review with `gpt-5.5` and `xhigh`, which returned `CONTESTED` with accepted constraints.
- Claude for Codex adversarial review, which returned `PASS` with accepted forward-risk findings.
- Antigravity Gemini review. Gemini default provider returned `PASS`; Gemini 3.1 Pro timed out twice and did not produce a usable verdict.
- Antigravity Claude provider returned empty output and did not produce a usable verdict.

The final decision is: proceed with high-fidelity common workbench implementation only under the constraints in this document.

## Goals

- Make the first screen feel like the approved professional scientific workbench: top toolbar, left configuration rail, center data/formula workspace, right result rail, and bottom status strip.
- Cover all computation modes with one shared workbench shell before mode-specific refinements.
- Add visible, consistent formula preview, parameter/constant editing, and result overview surfaces.
- Preserve existing computation behavior and workspace compatibility.
- Improve maintainability by creating shared workbench adapters instead of duplicating mode-specific GUI code.

## Non-Goals

- No algorithm changes.
- No new data model for formulas, parameters, constants, input data, or results.
- No fake progress, fake CPU/memory telemetry, fake result status, or decorative placeholder data in the app.
- No separate schema/help/i18n registry.
- No full rewrite of every mode UI in the first slice.
- No release packaging in this design step.

## Core Architecture

The workbench is a shared shell plus adapter panels. Adapter panels mount existing widgets and project existing state. They do not own independent computation state.

### Workbench Shell

`WorkbenchShell` is the visual owner of the shared layout:

- Top toolbar: workspace identity, file actions, run/stop, docs/help/update/settings affordances.
- Left configuration rail: mode selection, data source, output settings, and compact mode-level controls.
- Center workspace: data preview/editor, formula/model editor, parameter table, constants table.
- Right result rail: result tabs, result overview, progress/status summary, export affordances, compact result table.
- Bottom status strip: real readiness/job/workspace state only.

The existing `build_workbench_main_splitter()`, `workbench_layout.py`, `panels.py`, and `workbench_visual_contract.py` remain the starting point. The work should refine these boundaries rather than replace them wholesale.

### ModeWorkbenchSpec

`ModeWorkbenchSpec` is a frozen descriptor registry keyed by computation mode. It describes layout and binding, not values.

Allowed descriptor content:

- Mode key and display grouping.
- Existing widget attribute names to mount.
- Existing schema keys or shared result specs to use for labels/help.
- Formula block metadata, such as title, placeholder example, and preview target.
- Parameter/constant table placement and section titles.
- Result summary adapter key.

Forbidden descriptor content:

- `QWidget` instances.
- Mutable runtime state.
- Saved parameter values, constants, input data, formula text, result rows, result summaries, or plot data.
- New localized strings that duplicate `shared/ui_specs.py` or existing help specs.

The descriptor layer must first describe existing mode blocks. It must not regenerate every mode UI in the first implementation slice.

## Common Panels

### DataPreviewPanel

The data preview/editor area uses the existing input widgets as the single source of truth.

- The real manual data editor remains the editable data owner.
- File data controls and paste/import behavior remain existing behavior.
- Any styled preview is a projection of current input state, not a second editable data store.
- Tests must prove there is not a mirrored editable data table.

### FormulaWorkspacePanel

The formula workspace standardizes formula entry and preview across modes that use expressions.

- Reuse existing expression text widgets.
- Reuse `render_formula_pixmap()`, `FormulaPreviewDialog`, formula help, and schema/help bindings.
- Add a consistent visual pattern: formula editor on one side and rendered preview surface or preview button on the other.
- Refresh previews with debounce so typing does not block the GUI.
- If rendering fails, show a clear source-text fallback and non-blocking error message.
- Do not introduce a new expression parser.

### VariableTablesPanel

The parameter and constants area wraps existing table components.

- Use existing `ParameterTable` instances.
- Use existing `ConstantsEditor` instances.
- Keep automatic detection, manual row add/remove, constraints, constants text view, uncertainty parsing, and workspace restore behavior.
- The panel may improve visual grouping, headers, toolbar buttons, and layout density.
- It must not replace the underlying table widgets or row normalization logic.

### ResultOverviewPanel

The result overview expands the current CSV-backed rail into a more useful real-result summary.

- It may show status, duration, data row count, output file path, parameter count, constant count, warning count, and compact result rows.
- Every field must come from real run state, `_csv_rows`, `_csv_headers`, result snapshots, or saved workspace state.
- For plot-only or text-only successful runs, the empty tabular state must not say "No results." It should say "No tabular data" or show a broader non-tabular result status.
- The compact table is allowed because it is a projection of `_csv_rows`, not a second result model.

## State And Data Flow

The redesigned workbench keeps current ownership boundaries:

- Workspace capture and restore continue to read real widgets and result snapshots.
- Mode mixins continue to own computation-specific behavior.
- Existing public widget attributes remain available for tests, mixins, and workspace code.
- Common panels receive widgets through explicit mount points.
- Common panels emit UI-only signals or call existing methods; they do not compute or persist model values.

## Error Handling

- Formula preview errors must not block editing or running.
- Missing optional render dependencies fall back to source text.
- Result overview missing table data must distinguish no result, no tabular result, and failed result.
- Splitter and geometry persistence remain best-effort; invalid saved geometry should be clamped or discarded without blocking startup.

## Test Strategy

The implementation plan must add tests before each risky migration.

Required tests:

- Descriptor tests proving `ModeWorkbenchSpec` is frozen/descriptive and contains no `QWidget` or mutable runtime state.
- Tests proving each mode descriptor references existing widget attributes and schema keys.
- Structural duplicate-widget tests that detect mirrored data, mode editor, parameter, constants, or result state by role/schema binding, not only by object name.
- Per-mode workspace round-trip tests after moving or wrapping visible panels.
- Formula preview tests for live preview, popup preview, render fallback, and language refresh.
- Result overview tests for tabular, plot-only, text-only, failed, and restored workspace states.
- Existing visual gates: workbench visual contract, GUI schema scan, screenshot capture, bilingual inventory, workspace controller, and full pytest.

## Phased Delivery

### Phase 1: Descriptor And Guard Rails

- Add `ModeWorkbenchSpec` and mode registry as descriptive metadata only.
- Add descriptor invariants and duplicate-widget structural tests.
- Remove or explicitly guard/test the legacy two-pane splitter fallback.
- Adjust result overview empty wording for non-tabular states.

### Phase 2: Common High-Fidelity Panels

- Introduce shared panel adapters for data, formula, variables, and result overview.
- Mount existing widgets through explicit mount points.
- Preserve public attributes and workspace behavior.
- Update scanner and screenshot gates for the refined layout.

### Phase 3: Mode-by-Mode Polish

- Improve custom fitting, implicit fitting, root solving, error propagation, extrapolation, and statistics using the common panels.
- Each mode may refine formula examples, table grouping, and result summary adapters.
- Each mode must keep its current computation backend and saved workspace semantics.

### Phase 4: Full Quality Gate

- Run focused GUI suites.
- Run schema scan and screenshot capture.
- Run workspace round-trip suites.
- Run full pytest.
- Run Claude, Gemini, and Codex review where available. Tool failures must be recorded, not treated as passes.

## Acceptance Criteria

- The main window visually matches the approved workbench structure: compact left rail, central data/formula/parameter/constants workspace, and useful right result overview.
- All modes run through the common shell.
- No duplicated editable data table, mode stack, parameter state, constants state, or result state exists.
- Workspace files saved before and after the change still open correctly.
- Formula preview is visible and consistent where formulas are used.
- Result overview distinguishes real no-result, no-tabular-data, failed, and successful states.
- Bilingual labels and help affordances remain governed by shared specs.
- Full local quality gate passes before release work starts.

## Rejected Approaches

- Building a pixel-only clone with independent demo tables or decorative state.
- Replacing `ParameterTable` or `ConstantsEditor` with new table widgets.
- Moving computation logic into GUI panel classes.
- Creating a second i18n/help registry for the redesigned workbench.
- Regenerating every mode UI before descriptor tests and shared panel contracts exist.

## Spec Self-Review

- Placeholder scan: no TODO/TBD placeholders remain.
- Consistency check: the design prioritizes high-fidelity visuals while preserving single-source widget/state ownership.
- Scope check: the work is split into common shell first, then mode-by-mode polish.
- Ambiguity check: adapter panels, descriptor ownership, and forbidden duplicated state are explicit.
