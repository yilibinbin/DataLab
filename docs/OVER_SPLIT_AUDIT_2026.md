# Over-Split Audit — DataLab

## 1. Executive summary

**The codebase is healthy. It is not over-split.** Across 15 candidate splits that survived initial triage, adversarial verification confirmed exactly **one** genuine over-split worth consolidating — a 12-line pure re-export module (`shared/expression_names.py`). Every other small module examined turned out to be a legitimate layering boundary, a single-source-of-truth for drifting constants, a localization facade, or a compatibility contract with tests pinning it in place.

This is the profile of a codebase that splits deliberately, not reflexively. The maintainer's principle — "split for value/maintainability, not for the sake of splitting" — is broadly being honored. The one MERGE below is a rare miss (a light wrapper stacked on an already-light module), not a systemic pattern. **Recommendation: merge the single item, leave everything else.**

One item in the KEEP list (`latex_escape` wrapper) is flagged as a *soft* consolidation opportunity — real but lower-value indirection inside otherwise-legitimate files. It is not a file-level over-split, so it is noted, not ranked as a MERGE.

---

## 2. Consolidate these (ranked)

### #1 — `shared/expression_names.py` → fold into `shared/expression_registry.py`  ·  effort: **S**

| | |
|---|---|
| **Files** | `shared/expression_names.py` (delete) |
| **Merge target** | `shared/expression_registry.py` (already contains both functions, lines 60–67) |
| **Callers to repoint** | `shared/computation_inputs.py`, `shared/input_normalization.py` (one import line each) |
| **Test to update** | `tests/test_expression_registry.py` (one import line) |

**What to merge.** `expression_names.py` re-exports `reserved_expression_names()` and `is_reserved_expression_name()` from `expression_registry.py`. The re-export is behavior-free: `reserved_expression_names()` just forwards, and `is_reserved_expression_name()` is byte-identical to the registry's own implementation. Both functions **already live** in `expression_registry.py`, so merging grows the target by **zero lines** — callers simply repoint imports.

**Why it adds value.** This is pure indirection with no compensating benefit:
- **Not a layer boundary** — both files sit in `shared/` at the same layer.
- **Not an import firewall** — the usual defense for a thin shim. It fails here: `expression_registry.py` is *itself* import-light (only `re` + `typing`), and the existing `test_..._import_stay_lightweight` guard already protects it against PySide6/mpmath/sympy/etc. Callers importing directly from the registry get the identical lightness guarantee. The wrapper shields against nothing.
- **Not a compatibility contract** — the sole test consumer asserts the two sources return *identical* values, i.e. it exists to confirm redundancy, not to pin an external API. A full grep found no other importers, no `__init__` re-export, no dynamic/`importlib` references.

The one nuance flagged during verification: design docs name this file as an intended future "unit-validation facade." That is forward-looking intent, not present value — today the module has zero behavior and zero external contract. If a real validation seam is needed later, it should be a *new* module with actual logic, not a behavior-free re-export kept alive on spec.

Both independent verifiers returned **CONFIRMED / MERGE**. Safe, mechanical, strictly removes one import hop.

---

## 3. These splits are GOOD — do not touch

Each of these looked small enough to question but earned its place. Leave them.

| Module | Why it's legitimate |
|---|---|
| `app_desktop/bridge_qt.py` | **Bridge pattern.** Adapts `datalab_core` `SessionCallbacks` to Qt signals so the core never takes a PySide6 dependency. Small size = focused responsibility; dedicated test suite confirms the boundary. |
| `app_desktop/result_csv_spec.py` | **Single source of truth.** Keeps CSV headers/filenames from drifting across first-render mixins vs. `_refresh_display_format`. A test asserts both paths read the same spec — removing it re-invites hardcoding drift. Data-heavy, not fragmented. |
| `app_desktop/result_view_titles.py` | **Localization facade.** Maps view keys → bilingual strings, deferring to shared UI specs on miss. Small because the concept is small. |
| `app_desktop/workbench_model_bindings.py` | **State-path registry.** Centralizes `STATE_ROLE_MODEL_PATHS` + path construction; inlining pushes these strings back into the already-large `panels.py`. Declarative, cohesive. |
| `app_desktop/ui_schema_runtime.py` | **Mid-level binding layer.** Adds i18n lifecycle (`owner._register_text`) on top of `bind_field`; 8 view/widget builders depend on it, avoiding duplicated language-routing logic. |
| `app_desktop/widget_hints.py` | **Borderline but keep.** A one-liner wrapping `setAccessibleDescription` with a `getattr` guard, shared by 4 callers across modules. Marginal value, but consolidating buys almost nothing and risks scattering the guard pattern. Not worth the churn. |
| `datalab_latex/latex_tables_*` (fitting / statistics_grouped / statistics_matrix / budget) | **Files are correctly split by table domain — keep the files.** *However*, the `latex_escape()` **wrapper** inside `latex_tables_fitting.py` (lines 70–73) is a thin delegator to `shared.latex_escaping`, and three sibling modules import it from there instead of from `shared`. This is a soft, in-file cleanup (repoint 4 imports to `shared.latex_escaping`, drop the wrapper) — **not** a file-level over-split. Optional, low priority. |

---

## 4. Left as-is (harmless — not worth the churn)

Three trivially-small modules were examined and deliberately **left alone**: `app_desktop/current_page_stack.py` (a `QStackedWidget` subclass overriding two layout-hint methods), `app_desktop/root_latex_writer.py` (path/file-I/O wrapper around the LaTeX doc builder), and `app_desktop/shell_layout.py` (status-bar update helpers over `workbench_toolbar`). Each is small because its job is small; consolidating them would add no clarity and only generate diff noise.

---

**Bottom line:** 1 merge (S effort, mechanical), 1 optional in-file import cleanup, everything else stays. The codebase splits for value, not for the sake of it.