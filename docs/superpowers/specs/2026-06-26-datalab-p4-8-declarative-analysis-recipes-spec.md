# DataLab P4.8 Declarative Analysis Recipes Spec

Status: finalized after Codex, Antigravity/Gemini, and Antigravity/Claude review
Date: 2026-06-26

## 1. Goal

Add reusable, declarative analysis recipes that configure existing DataLab
workflows without arbitrary code execution. A recipe describes inputs,
constants, parameters, selected built-in calculation family, formula/model text,
validation rules, export surfaces, and example data bindings. Executing a recipe
must produce the same semantic snapshots, history entries, reports, LaTeX, and
plots as if the user configured the workflow manually.

Recipes are for repeatability, teaching, and reusable lab workflows. They are
not a plugin runtime.

## 2. Non-Goals

- No Python execution, shell commands, dynamic imports, JavaScript execution, or
  external process calls.
- No network fetches or remote recipe dependencies in the first release.
- No recipe-defined arbitrary UI widgets. Recipes bind to existing declarative
  form-schema fields and built-in workflow controls.
- No recipe-defined calculation kernels. Recipes select existing DataLab result
  families and safe expression engines only.
- No unsigned third-party recipe installation into trusted app resources.
- No export/reverse-generation of recipes from the current workspace in the
  first release. That requires a later reviewed reverse-mapping slice.

## 3. Relationship To Existing Examples And Workspaces

DataLab already has:

- bundled example workspace templates in `examples/workspaces`;
- `examples/catalog.py` as a discoverable example index;
- workspace template save-as protection in the Desktop app;
- generated example workspace tooling.

P4.8 recipes should complement these, not replace them:

- Example workspaces remain concrete saved states with data/config/results.
- Recipes are reusable parameterized descriptors that can generate or configure
  a workspace state.
- Bundled recipes may be referenced by examples and docs.
- User recipes are loaded as untrusted data and must never gain more authority
  than manual GUI input.

## 4. Recipe Schema

Initial schema: `datalab.recipe.v1`.

```json
{
  "schema": "datalab.recipe.v1",
  "id": "weighted-mean-basic",
  "title": {"en": "Weighted mean", "zh": "加权平均"},
  "description": {"en": "Compute a weighted mean from values and sigma."},
  "family": "statistics",
  "workflow_mode": "statistics.standard",
  "inputs": {
    "data": {
      "required_columns": [
        {"id": "value", "suggested_name": "Value", "role": "value", "type": "number_with_uncertainty"},
        {"id": "sigma", "suggested_name": "Sigma", "role": "sigma", "type": "number"}
      ]
    },
    "constants": []
  },
  "configuration": {
    "statistics": {
      "value_column": "${inputs.data.value}",
      "sigma_column": "${inputs.data.sigma}",
      "mode": "weighted_sigma"
    }
  },
  "exports": {
    "latex": true,
    "plots": true,
    "report_bundle": false
  },
  "examples": [
    {"workspace": "statistics.datalab"}
  ]
}
```

Requirements:

- Recipe IDs are stable ASCII identifiers.
- Localized text fields are data and must be escaped in HTML/LaTeX.
- `family`, `workflow_mode`, and configuration keys must be allowlisted.
  `workflow_mode` is a recipe identifier, not automatically a workspace
  `current_mode`; every workflow must map through an explicit adapter table.
- Configuration may reference recipe input roles using placeholders such as
  `${inputs.data.value}`. Placeholders resolve only through an explicit
  `RecipeApplyRequest` binding map supplied at apply time; they are not string
  interpolation in expressions, paths, labels, or code.
- Numeric defaults use the same safe numeric parser as manual inputs. Recipe JSON
  must reject JSON floats and non-finite constants during parsing; numeric
  values are strings except explicitly bounded integer count fields.
- Expressions use existing safe expression engines and existing formula export
  helpers.
- Recipes must not contain file paths outside their package/workspace context.
- Closed validators reject unknown top-level keys unless a documented
  `extensions` object is introduced later.

### 4.0 Workflow Routing Table

Every recipe workflow is mapped explicitly:

| Recipe `family` | Recipe `workflow_mode` | Workspace `current_mode` | Config section | Job mode | Result family |
|---|---|---|---|---|---|
| `statistics` | `statistics.standard` | `statistics` | `config.statistics` | `JobMode.STATISTICS` | `statistics` |

Later mappers add rows for error propagation, fitting, and root solving. Recipes
must not infer workspace mode keys by string equality.

### 4.1 Apply Request And Binding Map

The recipe file and the apply request are separate. A recipe describes required
roles; a `datalab.recipe.apply.v1` request binds those roles to the current
workspace:

```json
{
  "schema": "datalab.recipe.apply.v1",
  "recipe_id": "weighted-mean-basic",
  "bindings": {
    "inputs": {
      "data": {
        "value": {"kind": "data_column", "column_id": "Temperature"},
        "sigma": {"kind": "data_column", "column_id": "Sigma"}
      },
      "constants": {}
    }
  }
}
```

Rules:

- Placeholders are whole-field tokens only, matching
  `^\$\{inputs\.(data|constants|parameters|unknowns|variables)\.[A-Za-z_][A-Za-z0-9_]*\}$`.
  Each family adapter declares which of these namespaces it accepts.
- Declared role IDs in `required_columns`, constants, parameters, unknowns, or
  other role collections must match the same identifier grammar and be unique
  per namespace before any apply request is accepted.
- Substring interpolation such as `"prefix-${inputs.data.value}"` is rejected.
- Nested/object-path placeholders beyond declared role IDs are rejected.
- Duplicate bindings for one role are rejected.
- Bindings are resolved by typed family adapters before any workspace mutation.
- Placeholders are forbidden in expressions, paths, and localized text unless a
  later family-specific resolver explicitly supports that field and has tests.

### 4.2 Family Role Contracts

Recipe validation has two stages:

1. Recipe-file validation checks only schema, limits, placeholders, source
   policy, and allowlisted family/workflow/control keys.
2. Bound-family validation resolves roles and then calls existing family request
   builders, symbol classifiers, and expression validators before workspace
   mutation.

Each family adapter must declare accepted role kinds:

- statistics: data column, optional sigma/weight/group/time column, method
  controls;
- error propagation: expression symbols, input variables, constants, output
  target;
- fitting: x/y/sigma data columns, parameters, constants, model expression,
  target/output;
- root solving: equations, unknowns, constants, batch data roles, target
  variables.

Adapters must reject reserved names, invalid identifiers, duplicate symbols,
constants-vs-data ambiguity, parameter/constant collisions, missing required
symbols, and unsupported expression syntax by reusing the same validators that
manual setup uses. Recipes must not evaluate expressions during validation.

## 5. Execution Semantics

Recipe execution has two phases:

1. Configuration phase:
   - validate recipe schema;
   - validate requested family/workflow/control keys against an allowlist;
   - bind recipe inputs to the current data table, file input, or bundled example
     data through an explicit binding map;
   - produce an ordinary DataLab workspace/config state.

2. Calculation phase:
   - execute the selected built-in workflow through the normal job path;
   - produce normal semantic result snapshots and history entries;
   - route text/CSV/LaTeX/plot/report generation through existing family
     renderers.

If required columns/constants cannot be resolved by exact suggested name or a
stored binding, the Desktop apply flow prompts the user to bind current columns
or constants to recipe roles. Recipes do not bypass family validators. A recipe
that configures an invalid workflow fails with the same diagnostics as manual
input plus recipe context.

## 6. Security Model

Recipes are untrusted data.

Allowed:

- JSON parsed with duplicate-key rejection and bounded resource limits;
- built-in family/workflow selectors;
- existing safe expression text;
- bundled example data references;
- relative recipe-package resource references checked against an allowlist.

Forbidden:

- Python code;
- shell commands;
- environment variable access;
- dynamic imports;
- network URLs;
- absolute paths;
- `..` path traversal;
- binary embedded payloads unless a later reviewed package format allows them.

Validation must occur before any workspace state is mutated.

First release defers YAML support to avoid alias-expansion and duplicate-key
ambiguity. If YAML is added later, aliases must be disabled or bounded by a
reviewed parser policy.

Resource limits:

- maximum recipe file size: 512 KiB before parsing;
- maximum nesting depth: 16;
- maximum object keys or array items at any one level: 256;
- maximum declared input roles: 64;
- maximum placeholders: 128;
- maximum localized text field length: 4096 Unicode scalar values;
- duplicate JSON keys reject before normalization.
- JSON parsing uses duplicate-key rejection plus `parse_float` and
  `parse_constant` rejection so binary floats, `NaN`, and infinities never enter
  the recipe payload.

## 7. Recipe Package And Source Policy

First release supports:

- bundled recipes shipped with the app;
- user-opened local recipe files treated as untrusted and not installed
  automatically.

No background recipe marketplace or auto-update channel is included.

If recipe packages later include data files, package members must use the same
archive path validation primitives as workspace/report bundles and must keep
bounded size limits.

## 8. GUI Semantics

Desktop UI should provide:

- a Recipes entry near examples/templates;
- recipe preview showing title, description, family, required columns, and
  outputs;
- binding UI for unresolved input roles, using current workspace columns and
  constants;
- explicit Apply button that maps the recipe to the current workspace;
- diagnostics before mutation when required roles remain unbound or constants
  are missing;
- Save As behavior for recipe-generated workspaces when a bundled example
  workspace is opened/created as part of the recipe flow.

Recipes should not add another dense configuration panel. After applying a
recipe, users see and can edit the ordinary DataLab controls.

## 9. Workspace, History, Report, Docs

When a recipe is applied, the workspace stores a bounded
`RecipeProvenanceV1` payload at `workspace["provenance"]["recipe"]`. The
canonical JSON size of this object must not exceed
`MAX_RECIPE_PROVENANCE_BYTES = 16 KiB`, with individual text fields capped at
512 Unicode scalar values and binding summaries capped at 8 KiB:

- recipe ID/version/source metadata;
- source kind and source hash/path label when safe to store;
- normalized binding summary or binding hash;
- generated config hash, not a duplicate copy of generated config;
- whether the user has modified the generated configuration;
- applied time if the existing workspace metadata clock/source supports it.

Recipe provenance must not duplicate generated configuration or semantic result
snapshots. Authoritative configuration remains only in `workspace.config`, and
authoritative results remain only in `result_snapshot`/history entries.

This requires extending `WorkbenchModel` and v1 workspace round-trip handling so
the `provenance` object is preserved. Recipe provenance is explicitly excluded
from computation hashes; the generated ordinary `config` still participates in
workspace staleness and history input signatures.

History semantic snapshots remain manual-equivalent and keep their existing
closed semantic payload. To avoid provenance/result mismatches during history
navigation, P4.8 adds a versioned top-level history-entry provenance field, for
example `HistoryEntry.provenance["recipe"]`, outside `semantic_snapshot` and
outside `rendered_cache`. Restoring or exporting a history entry must use the
entry's own recipe provenance, not whichever recipe is currently present on the
workspace root. Recipe provenance remains excluded from semantic hashes and
computation hashes. History deduplication identity must include normalized
top-level provenance in addition to semantic payload so identical results
produced by different recipes do not collapse into one entry.
History pruning and per-entry size checks must count provenance bytes toward the
entry budget, and oversized provenance is rejected before save/export.

Report bundles include recipe provenance from the current workspace provenance
for current-workspace exports, or from the selected history entry provenance for
history/report exports, not from rendered caches and not as a separate result
family. In `datalab.report_bundle.v1`, recipe provenance lives in a validated
optional manifest field, for example `metadata.recipe_provenance`, with the same
JSON/no-float and byte-limit checks as workspace/history provenance.

Docs and examples should show recipes as a learning path, especially for
statistics, fitting, root solving, and error propagation examples.

## 10. Validation

Required tests:

- Valid recipe configures a built-in workflow and produces the same request as
  manual configuration.
- Workflow-routing tests prove recipe `workflow_mode` maps to the intended
  workspace `current_mode`, config section, job mode, and result family; string
  equality is not assumed.
- Role placeholders resolve through explicit bindings and never through code or
  unrestricted string interpolation.
- Placeholder tests cover undeclared roles, nested/object-path placeholders,
  substring interpolation, duplicate bindings, and mutation-before-validation.
- Bound-family validation tests cover reserved names, invalid identifiers,
  symbol collisions, missing symbols, constants-vs-data ambiguity, and existing
  expression validation without arbitrary evaluation.
- Recipe apply prompts or reports unresolved bindings instead of requiring users
  to rename their data columns.
- Unknown family/workflow/control keys are rejected.
- Unknown top-level keys are rejected.
- Unsafe paths, URLs, dynamic-code fields, and path traversal are rejected.
- Oversized recipes, excessive nesting, excessive role/placeholder counts,
  duplicate JSON keys, and YAML inputs are rejected.
- JSON float and non-finite constant inputs reject at parse time; numeric
  defaults are strings except bounded integer count fields.
- Duplicate declared role IDs reject before apply-request binding.
- Safe expressions are accepted only through existing expression validators.
- Recipe application does not mutate workspace state until validation passes.
- Apply-to-current-workspace preserves the current save path and template state.
- Create/open-from-bundled-example recipe flows reuse
  `_open_workspace_from_path(..., as_template=True)` or an equivalent
  template-origin field, so direct Save requires Save As.
- Workspace save/restore preserves recipe provenance and user-modified state,
  and provenance changes do not alter computation hashes.
- History semantic snapshots remain unchanged/manual-equivalent; top-level
  history-entry provenance restores with the entry and report bundles use that
  entry provenance when exporting historical results.
- History dedup tests prove same-semantic/different-provenance entries remain
  distinct, while `semantic_hash` remains unchanged.
- Report-bundle tests prove `metadata.recipe_provenance` is bounded,
  JSON-safe/no-float, visible in preview, and validated on read/write/history
  export.
- Bilingual title/description render safely in Desktop and docs.

## 11. Delivery Slices

1. Recipe DTO/schema/validator and security tests.
2. Recipe-to-workspace configuration mapper for one family, likely statistics.
3. Desktop recipe preview/apply flow.
4. Workspace/history/report provenance integration.
5. Bundled statistics recipe, docs, and example-workspace links.
6. Extend mapper coverage to fitting, root solving, and error propagation, then
   add their bundled recipes only after the corresponding mapper and end-to-end
   tests pass.
