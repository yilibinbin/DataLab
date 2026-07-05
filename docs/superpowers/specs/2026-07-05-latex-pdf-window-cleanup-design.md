# DataLab Desktop — LaTeX/PDF Window + Toolbar/Result-Panel Cleanup

**Date:** 2026-07-05  **Status:** draft (pending dual-model + user review)
**Builds on:** `2026-07-05-two-pane-layout-design.md` (2-pane layout + toolbar options landed)

## Goal (user, 2026-07-05)

Pull LaTeX/PDF out of the result tabs into a dedicated window, make PDF compile
tectonic-only (no local TeX), turn the toolbar option panels into real windows, and
remove dead/redundant UI in the result and merged panes.

## Verified current state (live probe + code, 2026-07-05)

- `result_tabs` = `[数值, 图像, 日志, TeX, PDF]` — TeX/PDF are tabs 3/4 (`panels.py:1433`,
  latex tab at `:1564`).
- Options live in two INLINE toolbar panels (`workbench_options_panel.py`), populated in
  `panels.py:1167-1196`: compute panel = precision + parallel + generate_plots + verbose;
  latex panel = `generate_latex_checkbox` + `latex_options_widget` (which wraps
  `output_file_edit`, `dcolumn_checkbox`, `latex_group_size_spin`, `caption_checkbox`,
  `latex_input_precision_spin`).
- PDF compile (`window_latex_compile_mixin.compile_latex_to_pdf` `:94`) picks
  `latex_engine_combo` engine, tries tectonic-no-prompt, then FALLS BACK to local
  pdflatex/xelatex (`:108-158`). tectonic is bundled + auto-downloadable
  (`shared/latex_engine.py`: `ensure_tectonic_installed` `:331`, `tectonic_compile_argv`
  `:512`, SHA256-verified 0.15.0).
- Run trigger reads options at run time: `generate_latex_checkbox.isChecked()` +
  `output_file_edit.text()` in `window_extrapolation_mixin.py:194-210`, threaded as
  `generate_latex=` / `output_path=` into every mode's run method.
- `output_setup_section`: 0 children, 20px — DEAD empty widget above 开始执行.
- `run_button` (开始执行, bottom) AND `workbench_run_button` (toolbar 运行) both exist.
- History overview buttons are WIRED (`history_panel.py:120-121`…), disabled until a row is
  selected — NOT broken; the complaint is they take space.

## Confirmed decisions (user, 2026-07-05)

1. **New windows are QDialogs** (like `FormulaPreviewDialog`), resizable/non-modal — NOT
   `Qt.Popup`.
2. **Two DIFFERENT widget strategies by window type (this resolves the apparent
   contradiction Codex flagged):**
   - **Options dialogs (计算 / LaTeX-options):** hold the REAL schema-keyed option widgets,
     reparented ONCE at build time into the dialog (a stable single parent). Required
     because the reachability test enumerates every schema-keyed input and forbids hidden
     state-holders; and because the run pipeline reads `self.<widget>` directly. NO mirror,
     NO fresh duplicates for these.
   - **LaTeX-PREVIEW window (TeX/PDF):** uses FRESH display widgets (a new
     `NumberedTextEdit` for TeX, a new scroll+label for PDF) that reuse the underlying
     tex-source string and a PURE pdf-render helper. These are display widgets, not
     schema-keyed inputs, so fresh-widget + reuse-logic is correct and avoids reparenting
     result-display widgets out of the (removed) result tab.
3. LaTeX window = ONE dialog with TWO tabs (TeX source / PDF preview).
4. 计算 button also opens a real window; LaTeX-options button opens a real window.
5. Delete bottom 开始执行 + the empty `output_setup_section`.
6. History section collapses to a header by default, click to expand.

## Architecture

### Module 1 — `app_desktop/latex_preview_dialog.py` (NEW) — TeX/PDF window
A `QDialog` (resizable, non-modal, own lifecycle; pattern from `formula_preview.py`) with a
`QTabWidget` of two tabs:
- **TeX tab**: a NEW `NumberedTextEdit` + `LatexHighlighter` (same classes the current
  `latex_edit` uses), read-only-ish, populated from the generated tex SOURCE (see reuse
  below). Footer: **复制** (copy tex → clipboard) + **保存** (save tex → `QFileDialog`
  getSaveFileName, `.tex`).
- **PDF tab**: a NEW `QScrollArea` + label with the dialog's OWN render state (zoom, dpi).
  **Codex #1 (confirmed):** `_render_pdf_preview` (`window_pdf_preview_mixin.py:92`) is
  coupled to main-window state — `self.pdf_zoom`/`self._pdf_base_dpi` (`:116`),
  `self.pdf_container_layout`/`self.pdf_scroll` (`:186,:198,:220`), `self.last_pdf_path`
  (`:222`), and result-tab auto-select (`:229`). Passing a target scroll is NOT enough.
  **Refactor to a PURE helper:** extract `pdf_to_images(pdf_path, dpi) -> list[QImage]`
  (no `self` state) into `shared/pdf_preview*.py` or the mixin; the dialog owns its zoom/dpi
  and lays the images into its own scroll. The main-window `_render_pdf_preview` (if still
  needed) also calls the pure helper. NO result-tab auto-select from the dialog path.
- Opened by two result-panel buttons (Module 4). Passing `initial_tab` selects TeX or PDF.
- **tex SOURCE (Codex #2, confirmed):** `results.latex.source` is only a schema KEY on
  `latex_edit` (`panels.py:1494`) — NOT a `CalcResult` payload (`CalcResult` carries only
  `latex_path`, `workers_core.py:710`). Modes are FILE-FIRST: they write tex to
  `job.output_path` (extrapolation `workers_core.py:985`, error `:1228`, statistics `:1419`)
  and root/fitting SKIP writing when `output_path` is empty (`window_extrapolation_mixin.py:714`,
  `window_fitting_residuals_mixin.py:524`). Therefore the dialog's tex source = the string
  currently in `latex_edit` (populated post-run by `_load_latex_into_editor(latex_path)`),
  which REQUIRES the run to have written tex to SOME path → see the mandatory temp-path
  resolution below.

### Module 2 — tectonic-only compile (`window_latex_compile_mixin.py`)
- `compile_latex_to_pdf` always uses tectonic: `ensure_tectonic_installed()` →
  `tectonic_compile_argv()`. Remove the `latex_engine_combo` engine selection and the
  pdflatex/xelatex FALLBACK branch (`:108-158`, `:205`).
- Remove `latex_engine_combo` from the UI (it lives in the LaTeX result tab today,
  `panels.py:1147` note). Any code referencing `self.latex_engine_combo`
  (`compile_latex_to_pdf`, tests) updated to the fixed tectonic path.
- Error messages: tectonic download/run failures only; drop "install pdflatex/xelatex"
  copy (`:276-277`).
- First-run auto-install (Codex #5, confirmed): `resolve_engine("tectonic")`
  (`shared/latex_engine.py:289`) only finds an ALREADY-installed binary; the actual install
  today is the PROMPT-based `_offer_tectonic_install()` (`window_latex_compile_mixin.py:447`).
  For tectonic-only, the compile path must call `ensure_tectonic_installed` DIRECTLY (via
  the existing `EnsureTectonicWorker`, `workers_qt.py:581`) with a progress notice — no
  yes/no prompt, no local-TeX escape. Offline first-run failure surfaces a clear "could not
  download the TeX engine; check your connection" error (acceptable per the tectonic-only
  decision — there is intentionally no local-TeX fallback).
- The worker-level fallback to local engines (`workers_qt.py:665,:706`) is removed too.

### Module 3 — options as dialogs (`app_desktop/options_dialogs.py` NEW)
- `ComputeOptionsDialog` (QDialog): precision digits, uncertainty digits, resource policy,
  max workers, reserve cores, nested policy, generate_plots, verbose. New controls,
  two-way synced to the SAME underlying option STATE the run trigger reads.
- `LatexOptionsDialog` (QDialog): generate_latex, dcolumn, group_size, caption,
  input_precision — **NO 输出路径 field** (removed; path chosen at save-time in Module 1).
- The toolbar `workbench_compute_options_button` / `workbench_latex_options_button` now
  OPEN these dialogs (not toggle inline panels). The inline-panel row
  (`workbench_options_panel.py`) + its population (`panels.py:1155-1210`) is removed;
  `workbench_options_panel.py` may be deleted if nothing else uses it.
- **State model (RESOLVED — the dialog widgets ARE the option controls; no hidden
  state-holders, no mirror).** The reachability test (`test_desktop_option_reachability.py`)
  enumerates EVERY schema-keyed input and asserts each is `isVisibleTo(window)` via a user
  gate, with `_ALLOWLIST_UNREACHABLE` empty. So we CANNOT keep the real option widgets as
  hidden state-holders (a hidden `generate_latex_checkbox` = an unreachable schema-keyed
  input → test fails). Therefore:
  - The dialog's controls (`mpmath_precision_spin`, `generate_latex_checkbox`, …) are the
    ONE real instances — the SAME widget objects, reparented into the dialog once at build
    (a dialog is a stable single parent; unlike the abandoned QStackedWidget page, a
    QDialog does not "hide on the wrong page" — it is either open or closed, and its
    children are `isVisibleTo(window)` when open).
  - The run pipeline keeps reading `self.generate_latex_checkbox.isChecked()` etc.
    unchanged — same objects, just housed in the dialog.
  - Reachability gate: the sweep opens the dialog (like the current "open the panel" gate)
    → the option widgets are `isVisibleTo(window)` with a stable dialog parent. Add the
    dialog-open gate to the sweep's selector list.
  - This is the SAME single-real-widget principle as the current inline panels (which
    reparent the real controls, `panels.py:1172-1196`) — we swap the inline panel host for
    a QDialog host. NO mirror widgets, NO hidden duplicates.

### Module 4 — result-panel + merged-pane cleanup (`panels.py`)
- **Result panel buttons:** add **生成 TeX** + **预览 PDF** buttons at the top of the
  result rail; each opens the Module-1 dialog on the right tab. Remove the TeX + PDF tabs
  from `result_tabs` (`panels.py` latex/pdf addTab sites) → `result_tabs` = `[数值, 图像,
  日志]`.
- **Delete** `run_button`/`run_section` (bottom 开始执行) — toolbar 运行 is the single
  trigger. Any `run_button.clicked` wiring re-pointed to the toolbar button (already
  wired). Update `_config_card_sections` / tests that reference `run_section`.
- **Delete** `output_setup_section` (empty 20px widget) from the merged pane.
- **History:** wrap the history section in a collapsible header (default collapsed). Reuse
  or add a small collapsible container; `build_history_panel` gains a collapsed-by-default
  header toggling `entry_list` + buttons visibility.

### output_path decoupling (cross-module, RESOLVED — refined after recon)
**Verified flow today:** the run WRITES tex to a file (`result.latex_path`,
`window_extrapolation_mixin.py:514`) then `_load_latex_into_editor(latex_path)` reads it
into `latex_edit` (`:607, :735`; fitting `residuals_mixin:170/217/257`). `compile_latex_to_pdf`
→ `_persist_latex_editor` (`:296`) which writes `latex_edit.toPlainText()` to
`current_latex_path`, and **pops a save dialog if `current_latex_path` is None**
(`:299-308`). So naively removing `output_file_edit` would make every PDF preview pop a
save dialog — wrong.

**Resolution (three points):**
1. **Run always materializes tex to a TEMP path when no user path is set.** At the call
   site the run's `output_path` becomes a per-run temp file (not "" — a temp `.tex` under a
   tempdir), so `result.latex_path` exists and `_load_latex_into_editor` still populates
   `latex_edit`. The tex SOURCE is thus always retained as a string in `latex_edit`
   (`results.latex.source`). Confirm each of the 5 modes materializes tex when
   `generate_latex` is on regardless of a user path (fitting/extrapolation/statistics/
   root-solving/error).
2. **PDF PREVIEW compiles from a TEMP file, never the save dialog.** Refactor the compile
   path so preview writes `current tex source` to a temp `.tex`, tectonic-compiles to a
   temp `.pdf`, renders — WITHOUT touching `current_latex_path` or prompting to save. The
   save dialog is ONLY reachable via the 保存 button.
3. **保存 button** (TeX tab) = `QFileDialog.getSaveFileName` → write the current tex source
   to the chosen path (the ONLY user-path write). **复制** = tex source → clipboard. No
   `output_file_edit` anywhere.

So no mode-run *signature* changes, but the `output_path` VALUE at the call sites
(`window_extrapolation_mixin.py:197,249`, and the other modes) changes from
`output_file_edit.text()` to a per-run temp path, and the compile/preview path is
refactored to use a temp file rather than `_persist_latex_editor`'s save-or-prompt.

## Deletion blast radius (Codex #4 — complete, audited)

Deleting these is bigger than the naive list; each site must be handled:
- **`run_button` / `run_section`:** drives shortcut + button-state in
  `window_extrapolation_mixin.py:129,:137,:147`; language-state restoration reads it at
  `window.py:657`; tests click/assert it at `test_desktop_shell_layout.py:133,:163`.
  → Re-point the run shortcut + state logic to `workbench_run_button` (the toolbar 运行);
  update the two tests to the toolbar button; keep the state-transition (run↔stop) working.
- **`latex_engine_combo`:** used by compile (`window_latex_compile_mixin.py:105,:361`),
  workspace capture/restore (`workspace_controller.py:766,:1128`), and schema binding
  (`panels.py:2067`). → Remove the combo; workspace capture/restore must tolerate its
  absence (drop the field from the captured schema, migrate old workspaces gracefully);
  drop the schema-binding field.
- **TeX/PDF result tabs:** in `_RESULT_VIEW_ORDER` (`panels.py:128`), result indices
  (`:1624`), reachability (`test_desktop_option_reachability.py:373,:384`), and scanner
  scenarios (`tools/scan_desktop_gui_schema.py:71`). → Remove from `_RESULT_VIEW_ORDER`,
  re-index result tabs, update reachability (the latex_edit/pdf controls move to the dialog;
  their schema keys move with them or are re-scoped to the dialog), update scanner scenarios.
- **`output_setup_section`:** empty widget — safe delete, but check `_config_card_sections`
  (`panels.py:693`) which lists it; remove from that tuple.
- **`workbench_options_panel.py`:** delete if the dialogs replace both inline panels;
  update `test_desktop_toolbar_options_panel.py` (asserts the inline panels) to the dialog
  behavior.

## MANDATORY temp-path resolution (Codex #2/#3 — hard requirement, not optional)

Because all 5 modes are file-first and SKIP tex when `output_path` is empty, the run MUST
write tex to a per-run TEMP `.tex` when `generate_latex` is on and the user set no path.
Implement by making the call sites pass a temp path (a `tempfile`-managed `.tex`) as
`output_path` instead of `output_file_edit.text()` — for EVERY mode
(`window_extrapolation_mixin.py:197,249,...`, root `_write_root_latex_if_requested:714`,
fitting `residuals_mixin:524`). Then `result.latex_path` exists, `_load_latex_into_editor`
populates the (dialog's) tex source, and PDF preview compiles that temp file. The 保存
button copies the current tex source to a user-chosen path. This is REQUIRED for the design
to function — "materialize only on Save" is explicitly rejected (it breaks tex generation).

## Load-bearing risks (test FIRST)
1. **PDF renders via tectonic with NO local TeX.** Test: force local pdflatex/xelatex
   absent (PATH scrub), compile → tectonic path produces a PDF (or the ensure-install
   worker is invoked). No fallback to local engines. **Codex #5:** the existing
   `test_desktop_latex_compile_ui.py:114` ASSERTS the old fallback — it must be rewritten to
   assert the tectonic-only path (fallback removed). Update, don't just delete.
2. **Options dialog drives the run.** Test: change generate_latex in the dialog → the
   run trigger sees it (the hidden real checkbox reflects it); a silent-set regression
   fails (mirror downstream-signal assertion, like the menu-editor test).
3. **No control stranded / single-parent kept.** The options dialogs hold the REAL option
   widgets (reparented once into the dialog, a stable single parent — like today's inline
   panels). Reachability: options reachable by opening the dialog (add the dialog-open gate
   to the sweep). NO hidden state-holders, NO mirror widgets. (The LaTeX-PREVIEW window is
   different: its TeX/PDF views are NEW display widgets reusing the render/gen LOGIC, since
   `latex_edit`/`pdf_scroll` are result-display widgets, not schema-keyed inputs.)
4. **result_tabs no longer has TeX/PDF; the 2 buttons open the dialog on the right tab.**
5. **Bottom run + empty area gone; toolbar 运行 still triggers a run for all 5 modes.**

## Non-goals (YAGNI)
- No change to the compute math, the 5 modes' logic, or the web frontend's LaTeX (web has
  its own latex route; this is desktop-only unless a shared helper changes — keep shared
  `latex_engine.py` behavior compatible).
- No new PDF features (annotations, print) beyond the current render + zoom.
- History content/behavior unchanged beyond the collapse.

## Gate (project CLAUDE.md)
spec → **Codex + Gemini serial adversarial** → TDD (RED tectonic-only + options-dialog
drives-run + result-buttons-open-dialog first) → ruff → full desktop suite → CodeRabbit →
user test on real macOS → user-confirmed merge → `graphify update .`. `main` untouched;
work in the `feat/toolbar-options-popup` branch (or a new `feat/latex-pdf-window`).
