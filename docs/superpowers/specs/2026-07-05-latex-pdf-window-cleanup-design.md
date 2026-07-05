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
2. **New controls + reuse logic** — dialogs build fresh widgets and call the underlying
   tex-gen / tectonic-compile / pdf-render logic; they do NOT reparent the real controls.
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
- **PDF tab**: a NEW `QScrollArea` + label reusing the render logic in
  `window_pdf_preview_mixin._render_pdf_preview` (refactored to accept a target
  scroll/label rather than only `self.pdf_scroll`). Compiles the current tex via tectonic
  (Module 2) to a temp PDF, renders it.
- Opened by two result-panel buttons (Module 4). Passing `initial_tab` selects TeX or PDF.
- **Reuse, not reparent:** the tex SOURCE is obtained from the existing generation path
  (the result already carries a latex payload — `results.latex.source`); the dialog reads
  that string. PDF render reuses the mixin's compile+render helpers.

**Refactor needed:** extract the tex-source string and the pdf-render-into-widget so both
the (removed) result tab and the new dialog can call them. Keep `latex_edit`/`pdf_scroll`
as the data source OR lift the payload to a plain string/Path on the window; prefer a
small helper `current_latex_source()` + `render_pdf_into(scroll, label, pdf_path)`.

### Module 2 — tectonic-only compile (`window_latex_compile_mixin.py`)
- `compile_latex_to_pdf` always uses tectonic: `ensure_tectonic_installed()` →
  `tectonic_compile_argv()`. Remove the `latex_engine_combo` engine selection and the
  pdflatex/xelatex FALLBACK branch (`:108-158`, `:205`).
- Remove `latex_engine_combo` from the UI (it lives in the LaTeX result tab today,
  `panels.py:1147` note). Any code referencing `self.latex_engine_combo`
  (`compile_latex_to_pdf`, tests) updated to the fixed tectonic path.
- Error messages: tectonic download/run failures only; drop "install pdflatex/xelatex"
  copy (`:276-277`).
- First-run: `ensure_tectonic_installed` auto-downloads (existing worker
  `workers_qt.py:581` `EnsureTectonicWorker`); surface a progress/notice, no local-TeX
  prompt.

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

### output_path decoupling (cross-module, RESOLVED)
With `output_file_edit` removed from options: at run time `output_path` is passed as empty
(tex is generated into the in-memory/`results.latex.source` payload + a temp file as
today). The user chooses the final path only when they click **保存** in the TeX tab
(Module 1) → `QFileDialog`. So the run pipeline's `output_path=` becomes "" (or a temp
path); no mode-run signature changes required — just the source of `output_path` at the
call site (`window_extrapolation_mixin.py:197,249` etc.) becomes "" instead of
`output_file_edit.text()`.

## Load-bearing risks (test FIRST)
1. **PDF renders via tectonic with NO local TeX.** Test: force local pdflatex/xelatex
   absent (PATH scrub), compile → tectonic path produces a PDF (or the ensure-install
   worker is invoked). No fallback to local engines.
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
