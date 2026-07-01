# DataLab P3/P4 Analysis Roadmap Implementation Plan

Status: approved for Slice P3.3-A execution after clean Codex,
Gemini/Antigravity, and Claude adversarial reviews.

Spec: `docs/superpowers/specs/2026-06-20-datalab-p3-p4-analysis-roadmap-spec.md`

## 1. Goal

Implement the P3 foundation in independently reviewable slices:

- P3.3 workflow history and same-family compare.
- P3.2 schema-neutral report bundle infrastructure and read-only preview.
- P3.1 uncertainty-budget extractor registry and per-family dashboard.

P4 remains a set of separate feature-spec gates. This plan prepares the order and
handoff criteria for P4, but it must not implement a P4 monolith.

## 2. Global Constraints

- Preserve existing calculation results and algorithms.
- Preserve unrelated dirty worktree changes. Each slice owns an explicit file
  allowlist and reports touched files.
- No staging, commit, package, publish, release, broad cleanup, or unrelated
  revert unless the user explicitly changes scope.
- Persisted semantic data must contain no JSON floats.
- Rendered Markdown, CSV, LaTeX, PDFs, images, and GUI caches are not
  authoritative.
- Desktop is the first visible surface. Web surfaces are deferred unless a slice
  explicitly defines a safe route.
- Each implementation slice uses subagent-driven development: implementer,
  spec-compliance review, code-quality review, accepted-finding fixes, and final
  focused validation before the next slice.

## 3. Implementation Order

### Slice P3.3-A: History Core Model, Hashing, And Pruning

Goal: add a UI-neutral bounded history model.

Likely files:

- `datalab_core/history.py` or equivalent shared/core module.
- `shared/workspace_schema.py` only if a small exported hash helper is required.
- `tests/test_history_core.py`.
- Planning files and `docs/TEST_MATRIX.md` only if validation evidence is added.

Implementation:

- Add immutable history entry and history store DTOs.
- Implement canonical history bytes with SHA-256.
- Reuse or extend `compute_workspace_hash()`, `_hash_relevant_config()`, and
  `DISPLAY_ONLY_COMMON_KEYS` for calculation-affecting state classification.
- Exclude volatile UI/rendered-cache fields.
- Enforce defaults: 20 recent entries, 5 pinned entries, 25 MiB total semantic
  payload, 2 MiB per-entry semantic snapshot.
- Drop optional rendered caches before removing semantic history entries.
- Prune unpinned oldest entries before save only after optional caches are gone;
  never silently drop the current result.

Verification:

- JSON no-float tests.
- Hash stability tests across key order and volatile fields.
- Hash difference tests for calculation-affecting data/constants/config changes.
- Dedup collision-safety test: matching hash still compares canonical bytes.
- Pruning tests for recent, pinned, per-entry, and total-size limits.

### Slice P3.3-B: Workspace History Persistence

Goal: persist and restore bounded history without making rendered caches
authoritative.

Likely files:

- `app_desktop/workspace_controller.py`.
- `datalab_core/workbench_model.py` if the model needs a versioned history slot.
- `shared/workspace_schema.py` / `datalab_core/workspace_v2.py` only for schema
  validation and compatibility adapters.
- `tests/test_workspace_controller.py`, `tests/test_workspace_io.py`,
  `tests/test_datalab_core_workbench_model.py`.

Implementation:

- Add versioned history payload under workspace state only when enabled or
  explicitly saving with history.
- Restore history entries from semantic snapshots, not rendered text.
- Preserve current result snapshot behavior when history is absent.
- Fail loudly if current result cannot fit after optional history pruning.

Verification:

- Save/restore with history disabled.
- Save/restore with history enabled.
- Legacy workspace without history still loads.
- Oversized history prunes optional entries and preserves current result.
- Malformed history fails closed without corrupting current workspace data.

### Slice P3.3-C: Desktop History Panel Foundation

Goal: expose bounded current/recent history in the desktop GUI without compare
logic yet.

Likely files:

- New files: `app_desktop/history_panel.py`, `tests/test_desktop_history_panel.py`.
- Existing GUI allowlist before this slice starts: `app_desktop/window.py`,
  `app_desktop/panels.py`, `app_desktop/workspace_controller.py`,
  `tools/scan_desktop_gui_schema.py`, `tests/test_desktop_gui_schema_scan.py`,
  and `tests/test_workspace_controller.py`.

Implementation:

- Add a compact history drawer/panel with current result plus recent entries.
- Support rename, pin/unpin, delete, and restore selected entry.
- Reserve an "export selected to report bundle" command surface. It may remain
  disabled with a clear diagnostic until Slice P3.2-B provides the writer, but
  the history UI must not need another redesign to connect report export.
- Mark workspace dirty when persisted history state changes.
- Keep rendered output refreshed from semantic snapshot restore paths.

Verification:

- Qt offscreen tests for add/current entry, rename, pin, delete, restore.
- GUI schema scan for localized labels/help and no horizontal overflow.
- Workspace dirty tracking tests.

### Slice P3.3-D: Same-Family Compare Core

Goal: compare selected history/current results without parsing rendered text.

Likely files:

- `datalab_core/history_compare.py` or equivalent.
- Family adapters in statistics, fitting comparison, root solving, and
  uncertainty modules only where semantic snapshot helpers already exist.
- `tests/test_history_compare.py`.

Implementation:

- Add comparison request/result DTOs.
- Implement same-family adapters:
  - Statistics metric deltas, CI overlap, weighted consistency, outlier flags.
  - Fitting comparison rows, selected-fit metric deltas, matching parameter
    deltas, covariance/correlation warnings.
  - Root value deltas by index/label, classification changes, residual/Jacobian
    diagnostics.
  - Error propagation result deltas, contribution percent deltas, Taylor/MC
    diagnostics changes.
- Cross-family comparison starts with shared metadata only and performs no
  scientific cross-family deltas until a specific adapter exists.
- Cross-family comparison includes shared metadata immediately and defines the
  extension hook for budget-row comparison. Budget-row comparison becomes active
  when Slice P3.1-B supplies budget rows; before that it emits an explicit
  unavailable diagnostic rather than silently dropping the expected pathway.

Verification:

- Per-family fixtures with matching and mismatched schemas.
- JSON no-float comparison output.
- Unsupported/malformed snapshot diagnostics.
- No rendered text parsing.

### Slice P3.3-E: Desktop Compare Surface

Goal: make same-family compare usable from the history panel.

Likely files:

- New files: `app_desktop/history_compare_panel.py`,
  `tests/test_desktop_history_compare_panel.py`.
- Existing GUI allowlist before this slice starts: `app_desktop/window.py`,
  `app_desktop/panels.py`, `app_desktop/workspace_controller.py`,
  `app_desktop/history_panel.py`, `tools/scan_desktop_gui_schema.py`,
  `tests/test_desktop_gui_schema_scan.py`, and
  `tests/test_desktop_history_panel.py`.
- Shared CSV/LaTeX serializers if compare output gets export buttons.
- GUI tests and schema scan fixtures.

Implementation:

- Add compare-selected command with clear disabled state for invalid selections.
- Render compare rows through shared result table/CSV mechanisms.
- Keep LaTeX export optional in this slice; if added, use `datalab_latex`
  helpers only.

Verification:

- GUI tests for valid/invalid compare selections.
- Result restore and compare refresh tests.
- CSV parity tests if CSV export is visible.

### Slice P3.2-A: Schema-Neutral Archive Validation

Goal: extract reusable archive safety from workspace IO before report bundles.

Likely files:

- `shared/archive_validation.py`.
- `shared/workspace_io.py`.
- `shared/workspace_schema.py` only for constants/import wiring.
- `tests/test_archive_validation.py`, `tests/test_workspace_io.py`.

Implementation:

- Move path normalization, duplicate-entry rejection, symlink/directory
  rejection, total uncompressed byte accounting, per-prefix count limits, and
  per-prefix combined byte limits into a schema-neutral helper.
- Preserve current workspace archive behavior and error semantics where tests
  already cover them.
- Workspace wrapping must leave per-prefix combined byte limits unset or equal to
  the existing total cap so workspace validation behavior does not silently
  tighten. Report bundles use the new per-prefix combined limits.
- Add report-friendly prefix configuration but no report writer yet.

Verification:

- Existing workspace IO tests remain green.
- New helper rejects traversal, absolute paths, duplicates, symlinks,
  directories, unsupported prefixes, per-file overages, per-prefix combined
  overages, and total overages.

### Slice P3.2-B: Report Bundle Writer

Goal: export selected current/history semantic snapshots into a validated report
bundle archive.

Likely files:

- New files: `shared/report_bundle.py` or `datalab_core/report_bundle.py`,
  `tests/test_report_bundle.py`.
- New `datalab_latex` report assembly helper only if no existing builder can
  compose the selected sections.
- Existing GUI allowlist before visible export wiring starts:
  `app_desktop/window.py`, `app_desktop/panels.py`,
  `app_desktop/history_panel.py`, `app_desktop/window_latex_pdf_mixin.py`,
  `tests/test_desktop_history_panel.py`, and
  `tests/test_desktop_latex_compile_ui.py`.

Implementation:

- Define `datalab.report_bundle.v1` manifest.
- Write selected snapshots, CSV tables, LaTeX report/sections, optional plots,
  optional source attachments, optional PDF.
- Wire the history panel's selected entries to report bundle export once the
  writer exists.
- Enforce limits from the approved spec.
- Store SHA-256 hashes and sizes for every attachment.
- Use existing asynchronous LaTeX compile path for optional PDF; on compile
  failure, bundle `.tex` and failure details.

Verification:

- Round-trip writer/reader tests with and without PDF.
- Path/hash/size/count rejection tests for every report prefix.
- LaTeX representative compile tests for statistics/fitting/root/error sections.
- GUI responsiveness test if desktop export is visible.

### Slice P3.2-C: Report Bundle Read-Only Preview

Goal: open report bundles safely as read-only reports, not editable workspaces.

Likely files:

- New files: `app_desktop/report_bundle_preview.py`,
  `tests/test_report_bundle_preview.py`.
- Existing GUI allowlist before this slice starts: `app_desktop/window.py`,
  `app_desktop/panels.py`, `app_desktop/window_latex_pdf_mixin.py`,
  `tools/scan_desktop_gui_schema.py`, `tests/test_desktop_gui_schema_scan.py`,
  and `tests/test_desktop_latex_compile_ui.py`.
- Report bundle reader module.
- Tests for read-only behavior.

Implementation:

- Validate bundle and manifest before displaying anything.
- Show metadata, LaTeX, PDF/plots, and CSV tables when present.
- Never compile bundle-provided `.tex` during import/preview. Imported LaTeX is
  displayed as source only; PDF display uses pre-built bundle PDF. Any future
  explicit compile action must route through the hardened no-shell-escape path
  and content pre-filter.
- Offer "Open source workspace" only if an attached workspace is present and
  passes workspace validation.
- Never write report bundle contents back into the active workspace implicitly.

Verification:

- Valid bundle preview test.
- Malformed bundle rejection tests.
- Attached workspace validation tests.
- Read-only/no-dirty-state tests.

### Slice P3.1-A: Budget Extractor Registry

Goal: add the per-family budget extraction foundation.

Likely files:

- `datalab_core/uncertainty_budget.py` or shared/core equivalent.
- Family extractor modules or adapter functions in statistics/fitting/root/error
  core modules.
- `tests/test_uncertainty_budget.py`.

Implementation:

- Add `UncertaintyBudgetRow`, `BudgetExtractionResult`, and extractor protocol.
- Register initial extractors for statistics, fitting, root, and uncertainty
  snapshots.
- Extract rows only from semantic snapshots and `AnalysisRow` references.
- Fail closed on malformed or unsupported snapshots.
- Do not compute cross-family totals in this slice.

Verification:

- Per-family extractor fixtures.
- JSON no-float output.
- Malformed snapshot fail-closed tests.
- No embedded normalized `AnalysisRow` JSON in budget rows.

### Slice P3.1-B: Desktop Budget Dashboard And Exports

Goal: expose per-family budget/diagnostic rows for selected current/history
results.

Likely files:

- New files: `app_desktop/budget_panel.py`,
  `tests/test_desktop_budget_panel.py`.
- Existing GUI allowlist before this slice starts: `app_desktop/window.py`,
  `app_desktop/panels.py`, `app_desktop/workspace_controller.py`,
  `app_desktop/history_panel.py`, `app_desktop/history_compare_panel.py`,
  `tools/scan_desktop_gui_schema.py`, `tests/test_desktop_gui_schema_scan.py`,
  and `tests/test_workspace_controller.py`.
- Shared CSV and LaTeX budget table helpers.
- Plotting helper only for meaningful denominator rows.
- GUI and LaTeX tests.

Implementation:

- Add dashboard table for selected snapshots.
- Add CSV export through shared serializers.
- Add LaTeX budget block through `datalab_latex`, preserving dcolumn/siunitx
  compatibility where numeric columns apply.
- Add optional Pareto/cumulative plot only when denominator rows are present.
- Add diagnostics when total aggregation is unavailable.
- Activate the history compare budget-row extension hook for cross-family budget
  row comparisons where budget rows are available.

Verification:

- GUI table tests and schema scan.
- CSV/LaTeX parity and compile tests.
- Plot spec tests for contribution-only rows.
- Correlation/commensurability diagnostics tests.

## 4. P4 Handoff Plan

Each P4 item requires a separate spec and implementation plan before code:

1. P4.1 multi-column descriptive statistics.
2. P4.2 covariance/correlation matrix.
3. P4.3 grouped statistics.
4. P4.4 bootstrap confidence intervals.
5. P4.5 hypothesis tests.
6. P4.6 time-series smoothing and rolling statistics.
7. P4.7 unit-aware calculations.
8. P4.8 plugin-like declarative recipes.

Deferred dependency:

- P3.1-C cross-family total-budget aggregation is not part of the initial P3
  execution. It may start only after P4.2 or an equivalent separately reviewed
  feature provides explicit compatible covariance/correlation metadata. The
  future P3.1-C plan must implement the denominator, quantity-space,
  unit/unitless, aggregation-model, and covariance/correlation checks from the
  approved spec before allowing any total aggregation.

For each P4 spec:

- Define math semantics, invalid-input diagnostics, precision policy,
  workspace/schema impact, GUI surface, Web deferral or inclusion, CSV/LaTeX/plot
  outputs, examples, and tests.
- Run Codex, Gemini/Antigravity, and Claude adversarial review to no accepted
  findings before implementation.
- Use subagent-driven development per implementation slice.

## 5. Review Gates

Before implementation starts:

- This implementation plan must pass Codex, Gemini/Antigravity, and Claude
  adversarial review with no accepted findings.
- `git diff --check` must pass for the spec, plan, and planning files.

Per implementation slice:

- Implementer completes focused tests and reports touched files.
- Spec-compliance reviewer checks the slice against this plan and the approved
  spec.
- Code-quality reviewer checks maintainability, security, precision, and
  integration risk.
- Main thread reruns focused pytest, Ruff, compileall, feasible mypy, and scoped
  diff-check for touched files.
- Accepted findings are fixed and re-reviewed before moving on.

## 6. Rollback And Failure Policy

- If a slice fails repeatedly, stop at that slice and record the blocker in
  `task_plan.md`, `findings.md`, and `progress.md`.
- Do not keep partial GUI routes visible without working core behavior.
- If a new P4 idea proves larger than its spec, split it into another spec rather
  than expanding the current implementation slice.
- If archive validation or history persistence discovers workspace compatibility
  risk, prefer no-op/disabled visible UI over shipping unsafe persistence.

## 7. Initial Execution Target After Approval

Start with Slice P3.3-A. It is the lowest-risk foundation and unblocks later
history selection, report bundle selection, compare views, and budget dashboards.
