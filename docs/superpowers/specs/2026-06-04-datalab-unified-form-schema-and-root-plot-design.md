# DataLab Unified Form Schema And Root Plot Design

Date: 2026-06-04

## Goal

Migrate DataLab toward a unified schema-driven UI system that covers all user-facing configuration, input, model selection, result presentation, and workspace snapshot metadata without a risky one-shot rewrite. The immediate user-visible fixes are:

- Custom fitting and self-consistent/implicit model expressions use placeholder examples, not real default inputs.
- Every user input, model selector, and important result/output control has a clear localized tooltip or visible help affordance.
- Repeated label, placeholder, tooltip, help, language-switching, dirty-tracking, and workspace-capture code is consolidated behind shared schema interfaces.
- Root solving generates function plots when "Generate plots" is enabled.
- Root plot uncertainty bands automatically follow the selected root uncertainty method: Taylor, Monte Carlo, or Off.

## Current Context

DataLab already has partial UI metadata in `shared/ui_specs.py`, plus reusable components such as `ConstantsEditor`, `DetectedRowsTable`, formula-preview dialogs, centralized uncertainty parsing, root-solving normalization, result plot display, LaTeX writers, and workspace snapshot capture/restore. These pieces should be reused and extended rather than replaced.

The current desktop UI is still largely hand-built in `app_desktop/panels.py` and several mixins. Text registration, placeholder updates, help buttons, visibility, dirty tracking, result snapshot metadata, and workspace capture/restore are spread across multiple files. This causes repeated logic and makes it easy for one module to miss language-aware labels or option-controlled output formatting.

## Scope

All modules are in scope eventually:

- Extrapolation
- Error propagation
- Fitting, including custom fitting and self-consistent/implicit fitting
- Root solving
- Statistics
- Global options, including precision, uncertainty digits, parallel resources, LaTeX, PDF, and plotting options
- Result tabs: numeric result, image result, log, LaTeX, and PDF preview
- Workspace save/restore and result snapshots

The work must be split into separate plan files and implementation phases. Each phase must be independently testable and should preserve existing behavior unless the spec explicitly changes it.

## Architecture

### Schema Registry

Extend the existing `shared/ui_specs.py` direction into a broader schema registry. The registry should define stable metadata objects for:

- `FormFieldSpec`: labels, placeholders, tooltips, help text, default value, required/optional status, widget kind, language text, workspace key, dirty key, validation hint, and visibility rules.
- `FormSectionSpec`: section title, contained fields, module/mode id, ordering, visibility rules, and help behavior.
- `ChoiceSpec`: localized labels and stable backend values for combo boxes and segmented choices.
- `ResultViewSpec`: result tab labels, result table columns, CSV/raw keys, display formatting policy, LaTeX/PDF/image attachment metadata, and language behavior.
- `PlotSpec`: plot kind, input data requirements, uncertainty visualization policy, result attachment key, and plot budget limits.

The schema must keep stable backend keys in English while localizing user-facing labels. It should not encode numerical algorithms; it describes UI and result contracts.

Visibility rules must be expressive enough for the current Qt UI. They must support:

- equality checks, such as `method == richardson`;
- set membership, such as `fit_model in {custom, self_consistent}`;
- negation, such as `fit_model != self_consistent`;
- conjunctions of clauses.

Free-form Python callbacks should be avoided in portable shared schemas. If a case cannot be represented by declarative clauses, it stays in the desktop binder until a reviewed schema extension exists.

### Desktop Binder

Introduce a desktop binder layer that applies schema metadata to existing Qt widgets. The first implementation should bind existing widgets instead of regenerating the entire GUI. The binder should:

- Set localized label text, placeholder text, tooltips, help button text/tooltips, and combo item labels.
- Register language refresh hooks centrally.
- Register dirty-tracking keys where existing dirty tracking needs them.
- Provide a consistent way to attach visible `?` help buttons when a field needs more explanation than a tooltip.
- Preserve existing widget object names and attributes so old tests and workspace restore code continue to work.

This is a non-destructive migration path: existing `QLineEdit`, `QPlainTextEdit`, `QComboBox`, `QSpinBox`, tables, and reusable editors stay in place while their metadata moves into schema.

### Workspace And Result Binder

Workspace capture/restore should eventually use schema metadata for fields that have a `workspace_key`, but this must happen gradually. Existing explicit capture/restore helpers remain the compatibility boundary during migration.

Result presentation should be described by `ResultViewSpec` and `PlotSpec`, but existing renderers remain responsible for producing Markdown, CSV rows, LaTeX source, PDF preview content, and image bytes.

## Phased Plan Boundaries

### Phase 1: Schema Foundation And Non-Destructive Binding

Create or extend schema objects for fields, sections, choices, result views, and plots. Add a Qt binder that can apply metadata to existing widgets.

Acceptance criteria:

- No broad UI rewrite.
- Existing modes still open.
- Existing language switching still works.
- Tests prove schema metadata can set labels, placeholders, tooltips, combo labels, and help button tooltips.
- Dynamic Qt object-tree tests detect visible user-facing input widgets in migrated areas that lack schema binding metadata.
- The dynamic scan only treats a widget as in scope when it is either registered by the schema binder or carries the Qt dynamic property `datalab_schema_required=True` inside a migrated section. Nested implementation widgets owned by reusable editors such as `ConstantsEditor` and `DetectedRowsTable` are excluded unless the reusable editor itself is the schema-bound field. Phase 1 tests must assert this property convention directly.
- Visibility-rule tests cover at least Levin beta visibility and custom-vs-self-consistent fitting control sets before Batch A migration.

### Phase 2: Configuration/Input Migration

Migrate all left-side configuration/input areas into the schema layer in batches:

- Batch A: custom fitting, self-consistent/implicit fitting, and root solving.
- Batch B: error propagation and constants.
- Batch C: extrapolation and statistics.
- Batch D: global options, including precision, uncertainty digits, parallel resources, LaTeX, PDF, and plotting.

Explicit behavior changes:

- In custom fitting mode, `fit_expr_edit` must start empty and show the current custom model example as placeholder text.
- In non-custom fitting modes, `fit_expr_edit` remains a read-only model preview and may be populated by mode-switch preview code.
- Workspace restore remains authoritative: if a saved workspace contains a custom expression, restore writes that expression into `fit_expr_edit` even though the default fresh UI is empty.
- `implicit_equation_edit` must start empty and show a self-consistent equation example as placeholder text, unless restoring a saved workspace expression.
- `implicit_output_edit` must start empty and show an output expression example as placeholder text, unless restoring a saved workspace expression.
- Root equations keep the current empty-by-default behavior with placeholder examples.

Acceptance criteria:

- Every migrated user input and model selector has localized label text and tooltip/help metadata.
- User-facing table headers follow the UI language where applicable.
- Existing workspace files still restore.
- Tests assert that non-custom model previews stay populated/read-only, custom mode starts empty with placeholder examples, and restored custom/implicit expressions are not discarded.
- Existing parameter detection, constants parsing, formula preview, and uncertainty parsing are reused.

### Phase 3: Result Area And Workspace Snapshot Migration

Bring numeric results, image results, logs, LaTeX, PDF preview, and workspace result snapshots under result schema metadata.

Acceptance criteria:

- Result tabs and result controls have localized schema metadata.
- Result snapshot save/restore preserves table display format, Markdown, logs, LaTeX, PDF state, and image attachments as before.
- Schema metadata documents which outputs are user-facing display values and which are raw machine-readable fields.
- No duplicate result-column localization logic remains in newly migrated result paths.
- A committed pre-migration workspace fixture loads and round-trips through the schema path without dropping table display format, Markdown, logs, LaTeX, PDF state, or image attachments when result-schema metadata is absent.

### Phase 4: Root Plot Generation

When root solving is run with "Generate plots" enabled, generate plots through the existing result image area and workspace plot attachment mechanism.

Root mode must explicitly honor the existing `generate_plots_checkbox`. Plot zoom/export controls apply through the existing image result area. Existing fitting-only log-scale controls remain fitting-only until a reviewed root log-scale design exists.

Root plot content:

- Function curve for scalar root problems.
- Zero line `y = 0`.
- Root markers with labels.
- Bracket/scan interval markers when the mode provides interval information.
- Per-row batch plots when batch data is used, subject to the plot budget below.

Uncertainty band policy:

- If root uncertainty method is Off, draw only the nominal function curve and root markers.
- If Taylor is selected, draw Taylor-style visualization using the same uncertain inputs but not by reusing the scalar root uncertainty as a function band. The plot shows:
  - a horizontal root-x uncertainty interval when a root uncertainty exists;
  - a function-value band computed over the plotted x-grid by first-order finite differences of the function value with respect to active uncertain inputs.
- If Taylor order 2 is selected for root uncertainty, the initial plot still uses the first-order function-value band and must label it as a first-order plot band. The root result may still use the order-2 root uncertainty path.
- If the root uncertainty policy resolves to skipped, unsupported, or fallback with no attached uncertainty, the plot draws no uncertainty band and emits a localized note.
- If Monte Carlo is selected, draw:
  - sampled root markers or a compact root distribution on the x-axis;
  - a function-value envelope from a deterministic downsample of sampled input sets.
- Monte Carlo plot envelopes are not allowed to evaluate every root-uncertainty sample across every grid point.

Root plotting must reuse:

- Existing expression parsing/evaluation safety.
- Existing uncertainty input extraction.
- Existing precision policy.
- Existing result image display/export and workspace attachment storage.
- Existing parallel resource settings where safe.

Plot budget:

- Maximum plotted x-grid points per curve: 300.
- Maximum Monte Carlo sampled curves per plot: 100, selected deterministically from the configured sample stream.
- Maximum batch rows plotted by default: 25. If a batch contains more rows, select rows in stable input-row order, not worker completion order, and plot the first 25 successful scalar/scan rows in that order. Emit a localized truncation note.
- Maximum generated images per run: 25 unless the existing image-result paging design is explicitly extended in a later reviewed plan.
- The per-run image cap is the hard ceiling. If a row would generate more than one image, batch plotting stops when the per-run cap is reached, and result details must state whether truncation was caused by row count, image count, or both.
- Budget decisions must be present in result details so users can see when a plot is downsampled or truncated.

Initial limits:

- Scalar and scan-multiple root plots are in scope first.
- Polynomial roots may plot the polynomial on a chosen interval if an interval can be inferred or configured.
- System roots are not plotted initially unless a clear one-dimensional projection exists; they should emit a localized warning instead of a misleading plot.

### Phase 5: Full Convergence And Cleanup

After the earlier phases are stable, remove duplicate UI text registration, duplicated placeholder refresh code, duplicated tooltip wiring, and duplicated workspace/result metadata for migrated areas.

Acceptance criteria:

- New user-facing controls in migrated areas require schema entries.
- Focused tests detect missing localized labels, placeholders, tooltips/help, and workspace keys where required.
- Broad GUI scan verifies no clipped controls, no stale English-only labels in Chinese mode, and no nonfunctional help/preview buttons.

## Error Handling

- Missing schema metadata in a migrated area should fail tests, not silently produce unlabeled controls.
- Invalid or unsupported plot cases should produce localized warnings and no image, not a crash.
- Monte Carlo plot bands must respect existing sample limits and cancellation boundaries.
- Plot generation must respect the plot budget even when computation results contain more rows, roots, or Monte Carlo samples.
- Workspace restore must continue to tolerate legacy files and malformed optional fields according to existing validation rules.

## Testing Strategy

Each phase gets focused tests before broad GUI scans:

- Schema unit tests for localization, defaults, placeholder, tooltip, and choice labels.
- Qt binder tests that instantiate controls offscreen and verify text/tooltips/help buttons.
- Workspace round-trip tests for migrated config and result metadata.
- Root plotting backend tests for nominal curve, root markers, Taylor band, Monte Carlo band, and unsupported system warning.
- Root plotting budget tests for deterministic Monte Carlo downsampling, stable input-row-order batch truncation, maximum generated image count, and image-cap precedence when a row can emit multiple images.
- GUI scan tests for layout, language switching, visible help affordances, formula preview buttons, root plot generation, and result image display.
- Regression tests for custom/implicit expression editors being empty with placeholder examples.

## Non-Goals

- Do not replace the entire Qt UI in one change.
- Do not introduce a separate expression engine, constants parser, uncertainty parser, precision option, or plotting display surface.
- Do not remove existing workspace compatibility.
- Do not implement system-root visualization until a reviewed projection design exists.

## Implementation Notes

- `shared/ui_specs.py` may be expanded or split into a small package if it becomes too large. The important constraint is one schema source of truth, not one physical file.
- The first implementation should prefer binding existing widgets over code-generating new widgets.
- The schema should remain backend-agnostic. Numerical behavior stays in fitting/root/error modules.
