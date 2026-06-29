# DataLab P4.8 Declarative Analysis Recipes Implementation Plan

Status: finalized after Codex, Antigravity/Gemini, and Antigravity/Claude review
Date: 2026-06-26

Spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-8-declarative-analysis-recipes-spec.md`

## 1. Preconditions

- Claude CLI / claude-for-codex review is disabled. If a Claude-family review is
  needed, use an Antigravity/agy Claude model only.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse existing example workspace, workspace schema, safe expression, family
  validator, semantic snapshot, and report-bundle boundaries.
- Do not implement arbitrary plugin execution or remote recipe loading.
- Do not implement recipe export/reverse-generation from a current workspace in
  the first release.

## 2. Key Design Decisions

1. Recipes are untrusted declarative data, not code.
2. Recipes configure existing DataLab workflows and then use normal job paths.
3. Recipe output is ordinary family semantic snapshots plus recipe provenance.
4. First implementation maps one family before broad coverage.
5. Bundled examples and recipe-generated workspaces keep existing template
   save-as behavior.
6. Recipe provenance lives in versioned workspace provenance metadata and in a
   versioned top-level history-entry provenance field. It is not embedded in the
   closed history semantic snapshot.
7. Recipe `workflow_mode` is mapped through explicit adapters to real
   `current_mode`, config section, job mode, and result family; string equality
   is never assumed.

## 3. Slice P4.8-A: Recipe Schema And Validator

Goal: define the safe portable recipe contract.

Likely files:

- new `datalab_core/recipes.py` or `shared/recipes.py`
- `shared/workspace_schema.py` if schema helpers are reused
- `tests/test_recipes_schema.py`

Implementation:

- Add `datalab.recipe.v1` normalizer/validator.
- Add `datalab.recipe.apply.v1` binding-map normalizer separate from recipe
  files.
- Validate:
  - stable recipe ID;
  - localized title/description maps;
  - allowlisted family/workflow/configuration keys;
  - required columns/constants declarations;
  - role placeholder syntax and binding references;
  - export surface flags;
  - example references.
- Add a workflow routing table. Initial row:
  `statistics` + `statistics.standard` -> `current_mode="statistics"`,
  `config.statistics`, `JobMode.STATISTICS`, result family `statistics`.
- Enforce whole-field placeholder grammar only:
  `${inputs.<namespace>.<role>}` where namespace is one of `data`, `constants`,
  `parameters`, `unknowns`, or `variables`, and where the family adapter
  allowlists that namespace. Reject substring interpolation, nested/object-path
  placeholders, undeclared roles, duplicate bindings, and placeholders in
  expressions/paths/localized text unless a later family-specific resolver
  explicitly supports that field.
- Require declared role IDs in required columns/constants/parameters/unknowns to
  match the same identifier grammar and be unique per namespace before apply.
- Enforce resource limits: 512 KiB max recipe bytes, max nesting depth 16, max
  256 object keys/array items per level, max 64 input roles, max 128
  placeholders, max 4096 Unicode scalar values per localized text field, and
  duplicate JSON key rejection.
- Parse JSON with duplicate-key rejection plus `parse_float` and
  `parse_constant` rejection. Numeric values are strings except explicitly
  bounded integer count fields.
- Reject:
  - unknown top-level keys;
  - URLs;
  - absolute paths;
  - path traversal;
  - dynamic-code fields;
  - binary payloads;
  - unsafe expression fields not accepted by existing expression validators.
- Defer YAML support in the first release; reject YAML inputs so alias expansion
  and duplicate-key policy cannot drift.

Verification:

- Valid minimal recipe passes.
- Each forbidden capability fails closed.
- Localized text is treated as data and escaped by renderers.
- Placeholders are parsed as recipe binding references only; they cannot execute
  code or reference arbitrary object paths.
- Placeholder denial tests cover undeclared placeholders, nested/object paths,
  substring interpolation, duplicate bindings, excessive placeholders, and
  mutation-before-validation.
- Oversized JSON, duplicate keys, excessive nesting/role counts, and YAML inputs
  fail closed.
- JSON floats/non-finite constants and duplicate declared role IDs fail closed.
- Validator does not mutate workspace state.

## 4. Slice P4.8-B: Recipe Mapper For Statistics

Goal: prove recipes configure one family through existing controls.

Likely files:

- `datalab_core/recipes.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/views/statistics.py` only if metadata hooks are needed
- `tests/test_recipes_statistics_mapper.py`

Implementation:

- Map a statistics recipe to existing statistics workspace/config fields.
- Use the workflow routing table to derive `current_mode`, config section, job
  mode, and result family.
- Resolve recipe input roles to current input headers through an explicit
  binding map. Auto-bind by exact suggested name where possible; otherwise
  return unresolved-binding diagnostics for the Desktop apply flow.
- Resolve placeholders through typed adapters before workspace mutation; never
  interpolate strings directly inside formulas, paths, labels, or config
  fragments.
- Run bound-family validation through the existing statistics request builder
  and symbol/control validators before mutation.
- Build the same `ComputeJobRequest` or workspace config that manual statistics
  setup would build.
- Keep all calculation and render paths unchanged.

Adapter table for current and future slices:

| Family | Adapter boundary | Extraction needed | Reject/clamp policy |
|---|---|---|---|
| statistics | `datalab_core.statistics.build_multi_column_statistics_requests` plus the existing statistics config adapter used by Desktop/Web job submission | none expected for first mapper | reject unsupported controls before mutation |
| error propagation | `datalab_core.uncertainty.build_uncertainty_request`, `shared.computation_inputs.classify_expression_symbols`, and `shared.computation_inputs.validate_symbol_classification` where expression roles are needed | extract any Desktop-only normalization needed into core/shared before recipe use | reject unsupported controls; do not clamp numeric scientific options silently |
| fitting | `datalab_core.fitting.build_fitting_request`, `fitting.model_parser.infer_parameter_names`, `fitting.model_parser.build_model_specification`, and `app_desktop.fitting_input_normalization.normalize_fitting_input` until its reusable parts are extracted into core/shared | extraction required before visible fitting recipes | reject unsupported optimizer/resource controls unless existing manual UI also clamps them |
| root solving | `root_solving.normalization.normalize_root_problem`, `root_solving.normalization.normalize_root_problem_from_context`, `shared.computation_inputs.classify_expression_symbols`, and `shared.computation_inputs.validate_symbol_classification` | none expected if existing core request covers equations/unknowns/constants | reject unsupported controls before mutation |

Verification:

- Recipe-generated statistics request equals manual configuration.
- Workflow-routing tests prove `statistics.standard` maps to real DataLab
  `current_mode`, config, job mode, and result family.
- Missing required bindings produce diagnostics or prompt data and leave
  workspace state unchanged until resolved.
- A user can bind columns with different names, such as `Temperature` and
  `Error`, to recipe roles without renaming the data table.
- Unknown configuration keys are rejected before mutation.
- Reserved names, invalid identifiers, constants-vs-data ambiguity, symbol
  collisions, missing symbols, and unsafe expression syntax are rejected by
  existing family validators when applicable.

## 5. Slice P4.8-C: Desktop Preview And Apply Flow

Goal: expose recipes without adding a new calculation panel.

Likely files:

- `app_desktop/window.py`
- existing workbench toolbar/menu modules
- optional new `app_desktop/recipe_preview.py`
- `tests/test_desktop_recipes.py`
- GUI schema scan tests

Implementation:

- Add Recipes entry near Examples.
- Show preview: title, description, family, required inputs, exports, and
  diagnostics.
- Show role-binding controls when current data does not exactly match suggested
  recipe column names.
- Add explicit Apply action.
- Apply only after validation and required role binding succeed.
- After applying, show ordinary DataLab controls for the selected workflow.
- Define two save-path flows:
  - apply-to-current-workspace preserves the current save path/template state;
  - create/open-from-bundled-example uses
    `_open_workspace_from_path(..., as_template=True)` or an equivalent
    template-origin field, so direct Save requires Save As.

Verification:

- Preview renders bilingual text safely.
- Apply succeeds for bundled statistics recipe.
- Apply fails without mutating state when headers are missing.
- Apply succeeds after manual role binding to differently named columns.
- Apply-to-current-workspace does not force Save As for ordinary user data.
- Recipe-generated bundled example workspaces require Save As on direct Save.
- GUI schema scan remains clean.

## 6. Slice P4.8-D: Workspace, History, Report Provenance

Goal: make recipe use auditable without creating a new result family.

Likely files:

- `shared/workspace_io.py`
- `shared/workspace_schema.py`
- `datalab_core/workbench_model.py`
- `datalab_core/history.py`
- `datalab_core/report_bundle.py`
- `app_desktop/workspace_controller.py`
- `tests/test_workspace_io.py`
- `tests/test_datalab_core_workbench_model.py`
- `tests/test_workspace_controller.py`
- `tests/test_report_bundle.py`

Implementation:

- Store a bounded `RecipeProvenanceV1` in
  `workspace["provenance"]["recipe"]`:
  - ID;
  - schema version;
  - source kind;
  - safe source label/hash;
  - normalized binding summary or binding hash;
  - generated config hash, not a duplicate config copy;
  - applied timestamp if existing workspace metadata supports it;
  - user-modified flag.
- Enforce `MAX_RECIPE_PROVENANCE_BYTES = 16 KiB`, text-field caps of 512 Unicode
  scalar values, and binding-summary caps of 8 KiB in workspace, history, and
  report paths.
- Extend `WorkbenchModel`, workspace v1/v2 conversion, and workspace validators
  so this provenance field round-trips. Because it is outside `config`, it is
  excluded from computation hashes.
- Keep history semantic snapshots unchanged/manual-equivalent. Add a versioned
  top-level `HistoryEntry.provenance["recipe"]` field outside
  `semantic_snapshot` and `rendered_cache`; restoring/exporting a history entry
  uses that entry provenance rather than the current workspace root provenance.
  Report manifests read recipe provenance from the current workspace for current
  exports or the selected history entry for historical exports.
- Include normalized top-level provenance in history dedup identity while
  keeping `semantic_hash` unchanged.
- Count provenance bytes in history per-entry and total prune budgets, and
  reject oversized provenance before save/export.
- Define report-bundle location as `metadata.recipe_provenance` in
  `datalab.report_bundle.v1`, with JSON/no-float and byte-limit validation in
  writer, reader, preview, and history-export paths.
- Wire Desktop capture/restore and dirty tracking so applying a recipe sets
  provenance, later manual edits to generated controls set `user_modified=true`,
  and unknown provenance is not dropped.
- Do not store rendered recipe preview as authoritative data.

Verification:

- Workspace round-trip preserves recipe metadata.
- Manual edits after apply mark generated configuration as modified.
- Recipe provenance changes do not affect workspace computation hash or history
  semantic hash; generated ordinary config changes still do.
- Oversized provenance is rejected consistently by workspace/history/report
  validators.
- History navigation tests prove restoring an older entry restores or exports
  that entry's recipe provenance instead of retaining the newest workspace root
  provenance.
- Same-semantic/different-provenance history entries remain distinct in
  dedup/prune behavior.
- Report bundle includes recipe provenance and ordinary snapshots.
- History entry/schema tests prove recipe provenance is accepted only in the
  top-level provenance field and is not added as an unknown semantic field.
- Report-bundle reader/writer/preview/history-export tests cover
  `metadata.recipe_provenance` limits and no-float validation.

## 7. Slice P4.8-E: Bundled Recipes, Docs, Examples

Goal: ship useful recipe examples and documentation.

Likely files:

- new `examples/recipes/*.json`
- `examples/catalog.py`
- `examples/README.md`
- `tools/generate_example_workspaces.py`
- docs under `docs/desktop` / `docs/web` as appropriate
- resource inclusion tests

Implementation:

- Add bundled recipes only for mapper-complete families in this slice. Initial
  Slice E ships statistics recipes such as weighted statistics.
- Link recipes to existing example workspaces where useful.
- Update docs and example catalog.
- Ensure packaged app resource lookup includes recipes.

Verification:

- Bundled statistics recipes validate, apply, calculate, and produce the same
  request/config as manual setup.
- Linked example workspaces still open as templates and calculate.
- Packaged-resource tests include recipe files.

## 8. Slice P4.8-F: Broader Family Mapper Coverage

Goal: extend recipe mapping beyond statistics after the foundation is stable.

Likely files:

- `datalab_core/recipes.py`
- family-specific request builders or workspace config adapters
- focused family tests

Implementation:

- Add mappers for error propagation, fitting, and root solving.
- Reuse each family validator/request builder.
- Keep unsupported controls rejected rather than silently ignored.
- Add bundled recipes for error propagation, fitting, and root solving only
  after their mapper coverage is implemented.

Verification:

- Recipe-generated requests match manual configuration for each family.
- Unsafe expressions remain rejected through existing safe engines.
- Existing unitless/manual workflows remain unchanged.
- Every bundled recipe validates, applies, calculates, and preserves ordinary
  semantic/report/history outputs before it is shipped.

## 9. Release Gate For P4.8

No user-visible P4.8 release should ship until:

- schema/security validator is closed;
- at least one family mapper is fully tested;
- Desktop preview/apply flow validates before mutation;
- workspace/history/report provenance works;
- every bundled recipe for mapper-complete families validates, applies,
  calculates, matches manual setup, and linked examples open as templates;
- no arbitrary code, shell, import, URL, absolute path, or path traversal is
  accepted by recipe validation.
