# DataLab Desktop — On-Demand LaTeX Generation (result-panel model)

**Date:** 2026-07-05  **Status:** draft (pending dual-model + user review)
**Supersedes Module 4 of:** `2026-07-05-latex-pdf-window-cleanup-design.md`
**Builds on landed modules:** 2 (tectonic-only), 3 (options→dialogs), 1a (temp-path), 1b
(LaTeX preview dialog).

## Goal (user, 2026-07-05)

Change LaTeX from "pre-check 生成 LaTeX + configure in a toolbar dialog, tex built during
the compute run" to an **on-demand, result-panel model**:

1. **No 生成 LaTeX checkbox.** The user never pre-decides whether to generate tex.
2. **No LaTeX toolbar options button/dialog.** LaTeX options (dcolumn / 分组位数 / caption /
   输入列位数) move to a **separate "LaTeX 选项" entry in the RESULT area**. KEEP the 计算
   toolbar button (precision/parallel/plots/verbose stay there).
3. **On-demand:** click **生成 TeX** (result panel) → tex is built ON DEMAND from the current
   result (NOT during the run) → the LaTeX preview window opens showing the source. Click
   **预览 PDF** → auto-compiles via tectonic (no compile checkbox, no engine picker, no
   visible compile step).

The user chose this over the cheaper "run always writes tex to a temp file" alternative so
that changing a LaTeX option regenerates the tex WITHOUT re-running the compute.

## Verified feasibility (5-mode parallel recon, 2026-07-05)

The tex builders need compute-derived data (`headers`, `data_rows`, `results`,
`table_segments`, per-mode extras) + format params (caption/dcolumn/digits/group_size).
Recon result — feasibility per mode:

| Mode | Feasibility | Gap to close |
|---|---|---|
| **root_solving** | **easy** | None — `_write_root_latex_if_requested` (`window_extrapolation_mixin.py:684`) ALREADY rebuilds tex post-run from a stashed payload. This is the PROVEN PATTERN to replicate. |
| **extrapolation** | **easy** | `_last_result_payloads['extrapolation']` (`:807`) drops `table_segments` (it's in the worker payload `workers_core.py:1013`). Add it to the remembered dict + thread through `_show_extrapolation_results`. |
| **error_propagation** | **moderate** | Window path (`_show_error_results`, `:998-1007`) builds a trimmed payload omitting `table_segments` + `constants` + `used_columns` that the worker's rich payload (`workers_core.py:1199-1217`) has. Retain them. |
| **statistics** | **moderate** | Plain sub-mode `_remember_last_result('statistics_single', …)` (`window_statistics_mixin.py:1653`) doesn't remember rows/units for the tex builder; grouped is nearly complete (units on the semantic snapshot). Retain rows+units for plain. |
| **fitting** | **moderate** | Single-fit `FitJob` lacks `latex_group_size`/`uncertainty_digits` fields (`workers_core.py:1479-1519`) — read live from widgets today; comparison path is complete. Snapshot or re-read at gen time; fix `variable_pairs` ordering. |

**No mode needs a deep recompute.** Format params are re-readable from persistent widgets
(dcolumn_checkbox, latex_input_precision_spin, latex_group_size_spin, uncertainty_digits_spin,
caption field) at generation time — matching the root_solving precedent. The gaps are all
compute-derived fields the window path drops; each is a small "retain N more keys" fix.

## ⚠ CRITICAL corrections from Codex design review (all confirmed against code)

1. **Do NOT add LaTeX-only data to the remembered display payload — use a SEPARATE stash.**
   `_refresh_display_format` splats the remembered payload into the display formatter:
   `_format_extrapolation_display(**payload)` (`window.py:2918`) and
   `_format_statistics_display(**payload)` (`:2938`). Those formatters accept ONLY
   `{headers,data_rows,results,ref_col}` (`window_extrapolation_mixin.py:854`) /
   `{result,value_col,n,units}` (`window_statistics_mixin.py:1569`). Adding `table_segments`
   / `rows` to the splatted dict → `TypeError`, crashing the display refresh. **Store the
   LaTeX-rebuild data in a separate `self._last_latex_inputs[mode]` dict**, never in the
   display payload.
2. **`render_pdf()` async race — BUG in the already-committed Module-1b code.**
   `compile_latex_to_pdf` runs a `_LatexCompileWorker` QThread; `last_pdf_path` is set only
   in the completion callback (`_on_latex_compile_completed`), NOT synchronously. But
   `latex_preview_dialog.render_pdf()` (`:126-139`) reads `last_pdf_path` IMMEDIATELY after
   calling compile → reads a stale/None path. **Fix: render in the compile-completion
   callback** (hook the dialog's PDF render to the worker's `completed` signal), not
   synchronously. This must be fixed as part of this work.
3. **root_solving is a post-worker rebuild, not a stash-reader.**
   `_write_root_latex_if_requested` (`window_extrapolation_mixin.py:684`) rebuilds from the
   PASSED payload and depends on run-time `generate_latex`/`output_path`. The retained data
   IS sufficient (the same payload is stashed at `:675`), but the on-demand builder must
   READ from the stash, not depend on run-time args — adapt, don't copy verbatim.
4. **error_propagation `used_columns` is LOCAL-ONLY** (not in the worker rich payload — the
   recon overstated this). It must be added to what's retained.
5. **Workspace restore clears `_last_*` stashes** (`workspace_controller.py:1784-1795,
   2037-2054`). A restored result snapshot cannot rebuild tex unless we persist the LaTeX
   inputs (or the tex source) into the workspace. **Decision needed** (see Open Question).
6. **`generate_latex_checkbox` removal blast radius:** run gate
   (`window_extrapolation_mixin.py:193-203, 234-243`), init/visibility (`window.py:568-570,
   1278-1281`), construction/dialog reparent (`panels.py:1065-1069, 1167-1194`), schema
   `output.latex.enabled` (`panels.py:1927-1933, 2002-2011`), dirty tracking
   (`window.py:822-845`), workspace capture/restore (`workspace_controller.py:745-766,
   1111-1129`), scanner (`scan_desktop_gui_schema.py:822`).

## RESOLVED (user decision, 2026-07-05): persist a full result snapshot; rebuild tex from it
The user wants the tex to be **rebuildable from the input data + computed result** at any
time — live OR after restoring a `.datalab` — so that adjusting LaTeX options regenerates
WITHOUT recompute, and `.datalab` stores NO tex config (click 生成 → tex).

**Foundation already exists (verified):** the workspace ALREADY captures a per-mode
`result_snapshot` — `_capture_semantic_result_snapshot` (`workspace_controller.py:1481`)
reads `_last_result_payloads` and builds per-mode snapshots via
`build_statistics_result_snapshot` / `build_root_result_snapshot` /
`build_fitting_comparison_result_snapshot` / `build_uncertainty_result_snapshot`
(in `datalab_core/`), persisted as `result_snapshot` in the `.datalab` and restored on load.

**So the design becomes:** the on-demand tex builder reads from this **result snapshot**
(the single source that works both live and post-restore), NOT a transient `_last_*` stash.
Concretely:
1. **Extend the snapshot builders** to carry EVERY tex-rebuild input the recon/Codex found
   missing (extrapolation: `table_segments`; error: `table_segments`+`constants`+
   `used_columns`; statistics-plain: `rows`+`sigma_rows`; fitting-single:
   `latex_group_size`+`uncertainty_digits`+`variable_pairs` order + `target_column`).
2. **Add an extrapolation snapshot** — there is currently NO
   `build_extrapolation_result_snapshot` (only statistics/fitting/root/uncertainty exist);
   add one so extrapolation results also persist + rebuild.
3. **On-demand `generate_latex_for_current_result()`** reads the current-mode snapshot +
   live LaTeX-option widgets (dcolumn/group_size/caption/input_digits — these are OPTIONS,
   deliberately re-read live so changing them regenerates) → calls the per-mode tex builder.
4. This satisfies "restored results can 生成 TeX" for free (the snapshot is in the `.datalab`)
   and "no tex config in the workspace" (only the semantic result snapshot is stored, which
   already exists for other reasons — history/compare).

This is a bigger change than the transient-stash version but matches the existing snapshot
architecture, so it reuses proven machinery rather than inventing a parallel store.

## Architecture

### A. Retain compute data per mode (`window_*_mixin.py` + `workers_core.py`)
**Store in a SEPARATE `self._last_latex_inputs[mode]` dict (NOT the display payload — see
correction 1).** Per mode, capture the tex-builder inputs at result-display time:
For each mode, ensure `self._last_result_payloads[mode]` (or the equivalent stash) retains
EVERY compute-derived input the tex builder needs (per the recon gaps above). Concretely:
- extrapolation: add `table_segments` to the remembered dict (`:807`) + thread through
  `_show_extrapolation_results`.
- error: retain `table_segments`, `constants`, `used_columns` in the window path (`:998-1007`)
  from the worker rich payload.
- statistics: retain rows + units in `statistics_single`.
- fitting: add `latex_group_size`/`uncertainty_digits` to the single-fit stash (or read
  live at gen time); fix `variable_pairs` ordering source.
- root_solving: no change (already complete).

### B. Per-mode on-demand tex builder (new `build_latex_for_current_result()`)
A dispatcher `generate_latex_for_current_result(self) -> str | None` that, based on the
current mode, reads the stashed compute data + live format-param widgets and calls the
SAME per-mode tex builder the worker used (`generate_latex_table`,
`generate_error_propagation_table`, `generate_statistics_latex`/`_grouped`, the fitting +
root writers), writing to a temp `.tex` and returning the source string. This mirrors
`_write_root_latex_if_requested` — no compute, pure rebuild. Returns None (with a friendly
message) if there is no current result.

### C. Drop the compute-time tex gate (`workers_core.py`, run trigger)

**Lead-verified consumers of the run-time tex write (what breaks if the run stops writing
tex):**
- `_load_latex_into_editor(latex_path)` (`window_extrapolation_mixin.py:580`, fitting
  `:170/217/257`) — populates the result LaTeX editor after a run. In the new model the
  on-demand 生成 TeX populates the editor instead, so this run-time load is simply removed
  (or the on-demand builder feeds the editor). NOT a blocker.
- The CSV `"latex"` column (`result_csv_spec.py:23`, extrapolation) is a per-ROW latex
  SNIPPET (via `format_uncertainty_display_latex`), NOT the full tex table — it is built in
  the display/CSV path independent of the run-time full-tex write. So dropping the full-tex
  write does NOT affect the CSV latex column. VERIFIED non-issue.
- `result.latex_path` becomes unused by the desktop run path; the on-demand builder writes
  its own temp path. Confirm no other consumer reads `result.latex_path` post-drop.

- Remove `generate_latex_checkbox` from the UI (Module 3 put it in the LaTeX options
  dialog — that dialog + button are removed, unit E).
- The compute worker NO LONGER writes tex during the run: the `if job.generate_latex:`
  blocks (`workers_core.py:985/1228/1414`, fitting/root writers) are bypassed for the
  desktop on-demand path. Simplest: the run always passes `generate_latex=False` (tex is
  built later on demand) — OR keep the worker capability but stop calling it from the
  desktop run. Decide during impl to minimize churn; the KEY is the desktop no longer
  needs the run to produce tex. (Web frontend unaffected — separate path.)

### D. Result-panel buttons + LaTeX-options entry (`panels.py`)
- Add **生成 TeX** + **预览 PDF** buttons to the result rail. 生成 TeX → build tex on demand
  (unit B) → `open_latex_preview_dialog(self, initial_tab='tex')`. 预览 PDF → build tex →
  `open_latex_preview_dialog(self, initial_tab='pdf')` (auto-compiles).
- Add a **LaTeX 选项** entry in the result area (a small button opening a
  `LatexOptionsDialog` — reuse the Module-3 `options_dialogs` machinery) holding dcolumn /
  分组位数 / caption / 输入列位数. Changing an option + clicking 生成/预览 regenerates.
- Remove the TeX + PDF tabs from `result_tabs` (`panels.py:1549/1600`), from
  `_RESULT_VIEW_ORDER` (`:128`), re-index result tabs, update reachability + scanner
  (the deletion blast radius from the prior spec's Module 4).

### E. Remove the LaTeX toolbar button + generate-checkbox (`workbench_toolbar.py`, Module-3 dialogs)
- Remove `workbench_latex_options_button` + `latex_options_dialog` from the toolbar (the
  LaTeX options now live in the result-side entry, unit D). KEEP
  `workbench_compute_options_button` + `compute_options_dialog`.
- Remove `generate_latex_checkbox` (no longer a gate). Any code reading it
  (`window_extrapolation_mixin.py:194/234`, `_toggle_latex_options`) updated: tex is always
  buildable on demand, so the checkbox is gone.

### F. Result-panel cleanup (from the prior Module 4 — still in scope)
- Delete `run_button`/`run_section` (bottom 开始执行) — re-point run shortcut/state/lang-
  restore to `workbench_run_button` (the toolbar 运行). Blast radius: `window.py:657`,
  `window_extrapolation_mixin.py:129-142`, `test_desktop_shell_layout.py:133/163`.
- Delete the empty `output_setup_section` (also from `_config_card_sections`, `panels.py:693`).
- Collapse the result-overview HISTORY section by default (a click-to-expand header).

## Load-bearing risks (test FIRST)
1. **Post-run tex rebuild matches the old run-time tex** for each of the 5 modes (golden:
   run with generate_latex on the OLD path, capture tex; on the NEW path, build on demand,
   assert byte-identical or semantically-equal source). The retained-data gaps (table_segments,
   constants, used_columns, rows/units, group_size) are exactly where a rebuild could DIVER GE
   — each mode gets a test.
2. **生成 TeX with no result** → friendly message, no crash.
3. **Changing a LaTeX option then 生成 TeX** regenerates with the new option (no recompute).
4. **No 生成 LaTeX checkbox anywhere**; the compute run does not write tex.
5. **Deletions safe** (run_button state machine, result_tabs indices, toolbar LaTeX button).

## Non-goals (YAGNI)
- No change to the compute math or the tex BUILDERS themselves (reused as-is).
- Web frontend untouched (own latex path).
- No new PDF features beyond the current render.

## Gate (project CLAUDE.md)
spec → **Codex + Gemini serial adversarial** → TDD (golden per-mode rebuild tests first) →
ruff → full desktop suite → CodeRabbit → user test → user-confirmed merge → graphify update.
main untouched; branch `feat/toolbar-options-popup`.
