# 4·4d — Remove generate_latex_checkbox (LaTeX options become always-visible)

**Date:** 2026-07-05 · **Branch:** `feat/toolbar-options-popup` · `main` untouched.
**Prereq:** 4·4a/b/c landed (4f4c7c6, 1afab05, df94b00).

## Problem

`generate_latex_checkbox` ("生成 LaTeX 文件") no longer gates anything: the run never
writes tex (on-demand generation replaced it, 4224fad). It survives only as (a) a
visibility toggle for `latex_options_widget` in the LaTeX 选项 dialog, (b) a schema-bound
input `output.latex.enabled`, and (c) a workspace-persisted flag `generate_latex`. User
decision: **彻底移除,选项改常驻** — delete the checkbox; the LaTeX options
(dcolumn / group_size / caption / input_digits) become always-visible in the dialog.

## Key facts (recon)

- The gating is **UI-only** (`_toggle_latex_options` → `latex_options_widget.setVisible`),
  NOT a schema `visible_when` rule — so `output.latex.*` fields have no schema gate parent
  to update. They were only visually hidden by the Qt toggle.
- The run trigger already passes `generate_latex=False` regardless of the checkbox, so the
  checkbox is inert at run time. Tests that set it (+ empty output path) to trigger a
  validation path are vestigial — the assertions don't depend on the checkbox.
- `output_file_edit` stays a detached compat widget (already the case); untouched.

## Changes

**panels.py**
- Delete `generate_latex_checkbox` creation + `_toggle_latex_options` connect + its
  `options_layout.addWidget` + the `removeWidget` line + the `latex_content_layout.addWidget`.
- `latex_content` (LaTeX 选项 dialog content) now holds just `latex_options_widget`
  (always visible).
- Delete the `generate_latex_field` FormFieldSpec (`output.latex.enabled`) + its entry in
  the checkbox binding loop.

**window.py**
- Delete `_toggle_latex_options` (method) + the init call at ~569.
- Drop `"generate_latex_checkbox"` from the dirty-tracking checkbox list (~829).

**workspace_controller.py**
- Capture (~1115): drop the `"generate_latex"` key from the common config dict.
- Restore (~755): drop the `_set_checked_if(window, "generate_latex_checkbox", ...)` line.
- Back-compat: an old `.datalab` with `generate_latex` in common config is simply ignored
  on restore (no crash — `_set_checked_if` gone; the extra key is dropped).

**Reachability (test_desktop_option_reachability.py)**
- `_reveal_output_gates`: drop `window.generate_latex_checkbox.setChecked(True)` — the
  LaTeX options are always visible now; keep the caption gate (`caption_checkbox`).
- The triply-gated caption_edit test (~668-678): drop the checkbox line, keep the panel-open
  + caption_checkbox gates.
- `output.latex.enabled` disappears from the enumerated inputs (widget gone), so no
  reachability entry is needed for it.

**Other tests**
- test_desktop_global_options_ui.py:67 — drop the `output.latex.enabled` schema-key assert.
- test_desktop_options_dialogs.py:53 — drop `generate_latex_checkbox` from `_LATEX_CONTROLS`.
- test_desktop_workbench_results.py (1040/1055/1115) — drop the vestigial
  `generate_latex_checkbox.setChecked(True)` + `output_file_edit.setText("")` setup lines
  (the assertions about the result overview don't depend on them).
- test_desktop_example_workspace_menu.py:265 — drop the `setChecked(False)` line.

## Tests (TDD)

- RED: assert `not hasattr(window, "generate_latex_checkbox")`, `latex_options_widget`
  is visible when the LaTeX dialog opens, and `output.latex.enabled` is absent from the
  enumerated schema keys.
- Regression: reachability suite, global-options, options-dialogs, workbench-results,
  example-workspace, workspace round-trip, on-demand golden tests — then full desktop suite.

## Gate

Full desktop + workspace suite green + ruff → this completes 4·4 → dual-model (Codex +
Gemini serial) → CodeRabbit → user test → user-confirmed merge → `graphify update .`.
