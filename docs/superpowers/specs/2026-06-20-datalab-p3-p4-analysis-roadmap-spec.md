# DataLab P3/P4 Analysis Roadmap Spec

Status: design-approved for implementation planning after clean Codex,
Gemini/Antigravity, and Claude adversarial reviews.

## 1. Purpose

P0-P2 established shared semantic rows, family-specific semantic result
snapshots, shared CSV/LaTeX/plot boundaries, richer statistics, fitting
diagnostics, root diagnostics, and error-propagation diagnostics. P3/P4 must
build on those contracts rather than creating parallel result formats or
duplicating module math.

This spec defines:

- P3 features that can be implemented after a dedicated implementation plan:
  workflow history/compare, report bundle, and an uncertainty-budget registry
  plus per-family contribution/diagnostic dashboard.
- P4 feature families that remain valuable roadmap work but require individual
  per-feature specs before production implementation.

## 2. Non-Negotiable Architecture Rules

1. Semantic snapshots are the source of truth.
   Rendered Markdown, CSV, LaTeX, PDFs, and images are caches or exports. P3/P4
   must rebuild displays from semantic snapshots or explicit shared serializers.

2. No JSON floats in persisted semantic data.
   Numeric values in snapshots, budgets, report manifests, and history entries
   must be strings, integers, booleans, nulls, or JSON-safe nested structures.

3. No duplicated calculation formulas in UI layers.
   Desktop/Web adapters may dispatch jobs and render shared outputs, but
   calculations, comparisons, and export formatting live in shared or
   `datalab_core` / `datalab_latex` modules.

4. Bounded storage is mandatory.
   Workflow history and report bundles must enforce item count, attachment
   count, per-attachment size, per-category byte limits, and total size limits.

5. P3 must not silently change existing calculation results.
   P3 adds aggregation, packaging, history, and comparison views. It does not
   alter statistics, fitting, root-solving, extrapolation, or uncertainty
   algorithms.

6. P4 features are not allowed to land as one monolith.
   Each P4 feature must have its own spec, routing table, review loop, and
   focused implementation plan.

## 3. Existing Contracts To Reuse

P3/P4 implementations must reuse these existing boundaries where applicable:

- `datalab_core.results.AnalysisRow` and semantic row groups.
- Family result snapshots for statistics, fitting comparison, root solving, and
  uncertainty/error propagation.
- `app_desktop.workspace_controller` semantic capture/restore dispatch.
- `shared.workspace_io` / `shared.workspace_schema` archive validation patterns.
  Report bundles must not reuse the current workspace-only path whitelist
  directly; implementation must first extract a schema-neutral archive member
  validation primitive.
- `shared.workspace_schema.canonical_json()` and `sha256_bytes()` style hashing.
- `shared.workspace_schema` and `datalab_core.workspace_v2` compatibility
  readers.
- Shared plotting render-from-spec helpers in `shared.plotting`.
- Shared formula rendering/export helpers in `shared.formula_export`,
  `shared.formula_latex_export`, and `datalab_latex.formula_render_service`.
- Shared LaTeX table builders under `datalab_latex`.
- Existing parallel/resource options; new batch/resampling work must honor them
  rather than inventing another worker setting.

## 4. P3.1 Uncertainty Budget Registry And Dashboard

### 4.1 Goal

Provide a registry-driven uncertainty/contribution/diagnostic dashboard across
result families by consuming semantic snapshots and diagnostic rows. The first
release is a per-family budget and diagnostics view. Cross-family totals are
allowed only when the contributing snapshots provide explicit compatible
denominators and covariance/correlation metadata.

### 4.2 Scope

Initial P3.1 supports extraction from:

- Error propagation: contribution variance, contribution percent, cumulative
  percent, absolute/relative sensitivities, Taylor/Monte Carlo comparison
  diagnostics, and Monte Carlo distribution summaries when present.
- Fitting: parameter covariance/correlation diagnostics, confidence/prediction
  band suppression diagnostics, standardized residual diagnostics, and official
  fit statistics as context rows.
- Root solving: root uncertainty fields, residual norm, solver status,
  classification tags, scan evidence, Jacobian condition, and warning/failure
  row flags.
- Statistics: confidence intervals, weighted consistency diagnostics,
  outlier flags, trimmed mean metadata, and plot diagnostics as context rows.

P3.1 does not infer unavailable physical correlations automatically. Correlated
inputs are represented only when a snapshot explicitly supplies correlation or
covariance metadata.

### 4.3 Extractor Interface

Avoid a single coupling hub that reads arbitrary snapshot internals. Add a
stable per-family extractor interface in a shared/core module, for example:

```python
@dataclass(frozen=True)
class BudgetExtractionResult:
    rows: tuple[UncertaintyBudgetRow, ...]
    diagnostics: tuple[AnalysisRow, ...]


class BudgetExtractor(Protocol):
    family: str
    supported_snapshot_schemas: tuple[str, ...]

    def extract(self, snapshot: Mapping[str, object]) -> BudgetExtractionResult:
        ...
```

Rules:

- Each family owns its extractor and its supported snapshot-schema list.
- Extractors fail closed: unsupported or malformed snapshots emit diagnostics and
  no forged contribution rows.
- Extractors may use `AnalysisRow` keys and source identifiers, but they must not
  embed normalized `AnalysisRow` JSON inside budget rows.
- Adding a new result family requires registering an extractor, not modifying a
  central snapshot parser.

### 4.4 Budget Row Model

Add a UI-neutral budget row type in a shared/core module, for example:

```python
@dataclass(frozen=True)
class UncertaintyBudgetRow:
    family: str
    result_id: str
    source_snapshot_id: str
    source_row_id: str | None
    source_key: str | None
    category: str
    label_key: str
    value: str | int | None
    uncertainty: str | None
    percent: str | None
    cumulative_percent: str | None
    method: str | None
    severity: str
    notes: tuple[str, ...]
```

Rules:

- The row model is derived from semantic snapshots and family extractors.
- Percent values are family-local unless an explicit total budget denominator is
  defined.
- For fitting/root/statistics rows that are diagnostics rather than variance
  contributions, `percent` remains null and `category` explains the diagnostic
  type.

### 4.5 Correlation And Total-Budget Policy

Initial P3.1:

- Accepts explicit covariance/correlation matrices only from family snapshots or
  future P4 matrix features.
- Emits a diagnostic when users request a total budget across potentially
  correlated sources but no covariance metadata exists.
- Does not assume independence unless the source family marks a row as
  independent or the user explicitly chooses an independence assumption.
- Treats P4.2 covariance/correlation metadata as one possible source of explicit
  correlation data, not as a sufficient condition for every total-budget mode.
- Requires total-budget rows to pass a commensurability gate before aggregation:
  matching denominator semantics, matching quantity space, compatible unit or
  unitless interpretation, and an explicitly named aggregation model. If any
  check is missing, rows remain side-by-side diagnostics rather than a total.

### 4.6 Output Surfaces

- Core: extractor registry, budget builder, and JSON-safe serializer.
- Desktop: a result subview/table and CSV export using shared serializers.
- Web: deferred unless the implementation plan includes a safe visible route.
- LaTeX: shared budget table block through `datalab_latex`, with dcolumn/siunitx
  compatibility where numeric columns apply.
- Plot: optional Pareto/cumulative contribution plot only for rows with a
  meaningful denominator.
- Workspace: budget outputs are generated from snapshots and may be cached, but
  semantic family snapshots stay authoritative.

### 4.7 Verification

- Per-family extractor fixtures for statistics, fitting, root, and uncertainty.
- JSON no-float tests.
- Fail-closed malformed snapshot tests per extractor.
- Correlation policy tests: explicit covariance accepted; missing covariance
  emits diagnostic; independence assumption recorded when used.
- CSV/LaTeX parity and compile tests.
- Plot spec tests for contribution-only budgets.

## 5. P3.2 Report Bundle

### 5.1 Goal

Export a self-contained report bundle that captures selected semantic results,
shared CSV tables, LaTeX source, optional PDF, plots, report metadata, and
provenance in a portable archive.

### 5.2 Bundle Structure

Use a ZIP-based structure similar to workspace archives but with a distinct
schema and distinct allowed prefixes:

```text
manifest.json
snapshots/{id}.json
tables/{id}.csv
latex/report.tex
latex/sections/{id}.tex
pdf/report.pdf
plots/{id}.png
sources/{id}
```

Manifest requirements:

- `schema = "datalab.report_bundle.v1"`
- DataLab version, created timestamp, language, precision/display settings.
- Selected snapshot IDs and snapshot family/kind.
- Attachment paths, sizes, SHA-256 hashes, and purpose.
- Export options: include PDF, include plots, include source data, include
  rendered caches, LaTeX engine used, compile status.

### 5.3 Shared Archive Validation Primitive

Report bundle implementation must first extract the reusable archive-safety
rules from `shared.workspace_io` into a schema-neutral helper, for example
`shared.archive_validation`.

The shared primitive owns:

- Path normalization and rejection of absolute paths, drive-letter paths,
  parent traversal, empty path components, duplicate entries, directories, and
  symlinks.
- Total uncompressed byte accounting.
- Per-prefix count and byte limits.
- Hash verification hooks.

Workspace archives keep their current schema and limits by wrapping this helper
with workspace-specific prefixes (`attachments/plots/`, `attachments/sources/`).
Report bundles wrap the same helper with report-specific prefixes.

### 5.4 Size And Security Limits

Initial report bundle defaults:

- `manifest.json`: max 2 MiB.
- Snapshots: max 100 files, max 2 MiB each, max 50 MiB combined.
- CSV tables: max 100 files, max 10 MiB each, max 50 MiB combined.
- LaTeX: `latex/report.tex` max 10 MiB; max 100 section files, max 2 MiB each,
  max 20 MiB combined.
- Plots: max 64 PNG files, max 20 MiB each, max 128 MiB combined.
- PDF: max 1 file, max 100 MiB.
- Sources: max 8 files, max 25 MiB each, max 100 MiB combined.
- Total uncompressed archive size: max 256 MiB.

Any implementation may choose stricter limits, but it must not choose looser
limits without a new spec review.

### 5.5 LaTeX/PDF Strategy

- Generate LaTeX through shared `datalab_latex` builders only.
- Compile asynchronously through the existing LaTeX worker/engine discovery
  path, never on the GUI thread.
- If no engine is available, bundle the `.tex` and manifest compile failure
  details instead of blocking export.
- PDF is optional and cache-like; `.tex` and semantic snapshots remain the
  durable source.

### 5.6 Restore Behavior

Initial P3.2 does not make report bundles editable workspaces. Import/open
behavior is read-only preview:

- Validate bundle.
- Show metadata, LaTeX, PDF/plots if present, and tables.
- Never compile bundle-provided `.tex` during read-only import/preview. Display
  the source as text and show only pre-built PDF/plots from the bundle. Any
  future explicit compile action for imported bundle LaTeX must go through the
  hardened no-shell-escape compile path and content pre-filter.
- Offer "Open source workspace" only if a workspace attachment is explicitly
  included and passes workspace validation.

### 5.7 Verification

- Archive path/hash/size/count rejection tests for every allowed prefix.
- Report bundle round-trip tests with and without PDF.
- Compile failure preserved in manifest without crashing.
- LaTeX compile tests for representative statistics/fitting/root/error sections.
- GUI responsiveness tests for asynchronous compile/export.

## 6. P3.3 Workflow History And Compare

### 6.1 Goal

Maintain a bounded local history of calculation results and allow users to
compare selected results without relying on rendered text parsing.

### 6.2 History Entry Model

Each history item stores:

- Stable ID, timestamp, title, mode/family/kind, language.
- Semantic result snapshot.
- Compact input signature: data hash, formula/model summary, constants hash,
  relevant options.
- Optional rendered-cache references, bounded by size and excluded by default.
- Status: success, warning, failed, stale, restored.

### 6.3 Storage Policy

Defaults:

- Keep current result plus 20 recent history entries.
- Keep at most 5 pinned history entries in addition to the recent limit.
- History semantic payload total max: 25 MiB.
- Per-entry semantic snapshot max: 2 MiB.
- Rendered caches, plots, and PDFs are excluded from history by default; history
  may reference current workspace/report attachments only when explicitly saved.
- Drop rendered caches first when size limits are exceeded.
- Prune unpinned oldest entries before workspace write.
- Never drop the current result silently.
- The existing workspace total-size cap remains the hard outer limit. If history
  cannot fit after pruning optional entries, save fails loudly instead of
  corrupting the workspace.
- Workspace save includes history only when enabled or when the user explicitly
  chooses "save with history".

### 6.4 Canonical Hashing And Deduplication

History deduplication and input signatures use canonical bytes. The
calculation-affecting portion must reuse or extend the existing workspace
staleness classifier (`compute_workspace_hash()`, `_hash_relevant_config()`, and
`DISPLAY_ONLY_COMMON_KEYS`) instead of defining an independent list of
calculation-vs-display options.

- JSON serialization uses UTF-8, `sort_keys=True`, and compact separators.
- Exclude volatile fields such as timestamp, UI transient state, selected tabs,
  rendered caches, and preview/PDF cache metadata.
- Include schema, snapshot version, family, kind, calculation inputs, constants,
  and calculation-affecting options.
- Numeric values remain the already-normalized string/int representation; no
  float coercion occurs during hashing.
- Hash algorithm: SHA-256 over canonical bytes.
- If hashes match, compare canonical bytes before deduplicating so collisions or
  canonicalization bugs fail closed.

### 6.5 Comparison Rules

Initial comparisons:

- Same-family comparison first.
- Statistics: metric deltas, CI overlap diagnostics, weighted consistency
  changes, outlier flag differences.
- Fitting: selected-fit comparison rows, metric deltas, parameter deltas when
  names match, covariance/correlation comparison warnings.
- Root: root value deltas by matching index/label, classification changes,
  residual/Jacobian diagnostics.
- Error propagation: result deltas, contribution percent deltas, Taylor/MC
  diagnostics changes.

Cross-family comparison is limited to shared metadata and budget rows until a
specific adapter exists.

### 6.6 UI Surfaces

- Desktop: history drawer/panel with pin/delete/rename, compare selected, export
  selected to report bundle.
- Web: deferred unless a server-side session history policy is defined.
- Workspace: history stored under bounded, versioned schema.

### 6.7 Verification

- Bounded storage pruning tests.
- Snapshot hash/dedup tests including canonicalization and collision-safety
  byte-compare tests.
- Same-family comparison fixtures.
- Workspace save/restore with history disabled/enabled.
- GUI tests for pin/delete/compare and no stale rendered-cache authority.

## 7. P4 Feature Specs

P4 features are valuable, but each needs its own spec and review loop. The order
below is recommended by reuse value and scientific utility.

### P4.1 Multi-Column Descriptive Statistics

Goal: compute descriptive/statistics rows for multiple selected columns in one
run.

Must reuse:

- Existing `compute_statistics()` / `run_statistics()` per column.
- Semantic rows, shared CSV/LaTeX, statistics plot specs.

Initial scope:

- Numeric columns only.
- One result group per column.
- Optional shared confidence level and trim fraction.
- No cross-column covariance until P4.2.

### P4.2 Covariance And Correlation Matrix

Goal: compute covariance/correlation matrices across selected columns and expose
explicit metadata that can feed future budget features only when the downstream
budget adapter also proves denominator, quantity-space, unit, and aggregation
compatibility.

Decisions required:

- Pairwise vs listwise missing-data policy.
- Sample vs population denominator.
- Weighted covariance support or explicit deferral.
- Matrix semantic row/LaTeX representation.

Initial outputs:

- Matrix table, CSV, LaTeX, heatmap plot.
- Optional link into P3.1 as explicit correlation metadata for total-budget mode.

### P4.3 Grouped Statistics

Goal: compute statistics per group/category and optionally compare groups.

Decisions required:

- Group key parsing and sorting.
- Minimum group size diagnostics.
- Whether group comparisons include hypothesis tests or only descriptive deltas.

Must reuse:

- Existing statistics core per group.
- P3.3 comparison row patterns when available.

### P4.4 Bootstrap Confidence Intervals

Goal: add bootstrap confidence intervals for selected statistics.

Decisions required:

- Percentile vs BCa first release.
- Seed/reproducibility policy.
- Resampling count defaults and parallel/resource control.
- Result distribution summary and plot reuse.

Must reuse:

- Existing parallel config.
- Monte Carlo distribution summary/plot pattern from error propagation.

### P4.5 Hypothesis Tests

Goal: add explicit hypothesis-test module or statistics submodes.

Candidates:

- One-sample and two-sample t-tests.
- Paired t-test.
- Nonparametric sign/Wilcoxon tests if dependency-free or well-scoped.
- Chi-square goodness-of-fit/independence.

Rules:

- Every test must surface assumptions and invalid-input diagnostics.
- P-values must be computed under `precision_guard` or through a documented
  SciPy/double-precision fast path controlled by numeric precision settings.

### P4.6 Time-Series Smoothing And Rolling Statistics

Goal: support rolling mean/median/std, EWMA, and optional Savitzky-Golay.

Decisions required:

- Time/index column semantics.
- Window alignment.
- Boundary policy.
- Uncertainty propagation for rolling summaries.

Must reuse:

- Existing statistics calculations where applicable.
- Shared plotting for series/residual visualizations.

### P4.7 Unit-Aware Calculations

Goal: optional unit annotations and unit conversion/dimensional checks.

This is high risk and must not be implicit. Initial spec must decide:

- Whether to depend on a mature unit library or implement a small safe subset.
- How units interact with uncertainty strings and constants.
- How to serialize units in workspaces and report bundles.
- How formulas validate dimensional compatibility.

Initial release should prefer opt-in unit metadata, not automatic reinterpretation
of existing numeric input.

### P4.8 Plugin-Like Analysis Recipes

Goal: allow reusable analysis recipes without arbitrary code execution.

Rules:

- Recipes are declarative JSON/YAML using existing safe expression engines,
  built-in modules, and fixed workflow steps.
- No Python execution, shell commands, or dynamic imports.
- Recipes declare inputs, constants, parameters, result family, and export
  surfaces.
- Recipe execution must produce normal semantic snapshots and history entries.

## 8. Recommended Delivery Order

1. P3.3 history foundation without comparison UI.
2. P3.3 same-family compare for current/recent results.
3. P3.2 schema-neutral archive validator and report bundle writer.
4. P3.2 report bundle read-only preview/import.
5. P3.1 budget extractor registry and per-family budget dashboard.
6. P4.1 multi-column descriptive statistics.
7. P4.2 covariance/correlation matrix.
8. P3.1 cross-family total-budget mode, only if explicit covariance/correlation
   metadata exists and the commensurability gate passes.
9. P4.3 grouped statistics.
10. P4.4 bootstrap confidence intervals.
11. P4.5 hypothesis tests.
12. P4.6 time-series smoothing.
13. P4.7 unit-aware calculations.
14. P4.8 plugin-like recipes.

Rationale:

- History/compare gives P3.2 report bundles and P3.1 budget a stable selection
  mechanism.
- Report bundles become more useful when they can export multiple selected
  history items.
- The initial budget dashboard can use existing P2 diagnostics without claiming
  unavailable cross-family covariance.
- P4.2 supplies the explicit covariance/correlation metadata required for any
  later total-budget mode.
- Units and recipes are most powerful but most likely to create security,
  compatibility, and scope risks, so they come last.

## 9. Review Questions For Three-Model Gate

Reviewers must challenge:

- Whether any P3 feature duplicates an existing workspace/report/history path.
- Whether P3.1 still overclaims uncertainty aggregation when correlations are
  unknown.
- Whether the per-family extractor interface avoids a central coupling hub.
- Whether report bundle size/security limits are concrete and sufficient.
- Whether the archive validator extraction is schema-neutral rather than
  workspace-path-specific.
- Whether history storage can corrupt or bloat workspaces.
- Whether canonical hashing excludes volatile fields without dropping
  calculation-affecting state.
- Whether P4 ordering is scientifically and architecturally defensible.
- Whether any P4 feature should be split further before implementation.
- Whether any UI/Web surface should be deferred to protect maintainability.

## 10. Acceptance Criteria For This Spec

- Codex, Gemini/Antigravity, and Claude adversarial reviews return no accepted
  findings.
- All accepted review findings are reconciled in this document before the
  implementation plan is written.
- The implementation plan that follows this spec must break P3/P4 work into
  independently reviewed slices and must not start with P4 monolith work.
