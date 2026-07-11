# 4·4b — Remove TeX/PDF tabs from `result_tabs` (keep widgets off-screen)

**Date:** 2026-07-05
**Branch:** `feat/toolbar-options-popup` (worktree `DataLab-menubar`; `main` untouched)
**Prereq:** on-demand LaTeX feature complete (4·2/4·3), 4·4a landed (`4f4c7c6`).

## Problem

The result details area's `result_tabs` still shows two tabs — **TeX** (`result.latex`)
and **PDF** (`result.pdf`) — that are now visually redundant: the on-demand LaTeX
**preview dialog** (`latex_preview_dialog.py`) is the real viewer, opened by the
result-panel 生成 TeX / 预览 PDF buttons. The two inline tabs duplicate it.

User decision (2026-07-05): **移除页签,组件转后台** — remove the two visible tabs, but
KEEP the underlying widgets alive (they are load-bearing, see below).

## Why the widgets must stay (cannot just delete the tabs)

`latex_widget` / `pdf_widget` build widgets that other code paths read:

- `latex_edit` (`NumberedTextEdit`, schema `results.latex.source`) — written by the
  on-demand builders via `_load_latex_into_editor`; read by the preview dialog
  (`window.latex_edit.toPlainText()`), the workspace controller (persist/restore of
  `latex_source`), i18n placeholder refresh, and the compile mixin.
- `latex_engine_combo` (schema `latex.engine`), `latex_engine_path_button`,
  `latex_compile_button`, `latex_view_pdf_button`, `latex_open/save/reload_button`,
  `latex_status_label` — read by `window_latex_compile_mixin`.
- `pdf_scroll`, `pdf_container(_layout)`, `pdf_zoom_spin` (schema `pdf.zoom_percent`),
  `pdf_zoom_in/out/reset_button`, `pdf_status_label` — read by `window_pdf_preview_mixin`.

Deleting them would break the preview dialog, workspace round-trip, and compile paths.

## Reachability contract (the load-bearing constraint)

`tests/test_desktop_option_reachability.py` requires every schema-**input** widget be
reachable through a real user gate. In the removed tabs the input-typed widgets are
exactly three (everything else is QLabel/QPushButton/QScrollArea — documented
non-inputs, already exempt via `_NON_INPUT_SCHEMA_TYPES`):

| widget | schema key | type |
|---|---|---|
| `latex_edit` | `results.latex.source` | QPlainTextEdit |
| `latex_engine_combo` | `latex.engine` | QComboBox |
| `pdf_zoom_spin` | `pdf.zoom_percent` | QDoubleSpinBox |

Today `_reveal_result_only_control` reveals these by switching `result_tabs` to
`indices["latex"]` / `indices["pdf"]`. After removal those indices no longer exist, so
the reveal helper must switch to making the **off-screen holder** visible.

The `latex`/`pdf` prefixes stay in `_RESULT_ONLY_PREFIXES` (still result-only state),
and the three keys stay enumerated inputs — we change only HOW they are revealed, not
whether they are required reachable. This keeps the anti-masking guards intact.

## Approach

1. **`panels.py` — off-screen holder.** Build `latex_widget` and `pdf_widget` exactly
   as now (all widgets, schema keys, bindings, signals unchanged). Instead of
   `self.result_tabs.addTab(latex_widget, …)` / `addTab(pdf_widget, …)`, add both to a
   new hidden holder:
   ```python
   self._offscreen_result_views = QWidget()
   self._offscreen_result_views.setObjectName("offscreen_result_views")
   _holder = QVBoxLayout(self._offscreen_result_views)
   _holder.addWidget(latex_widget)
   _holder.addWidget(pdf_widget)
   self._offscreen_result_views.setVisible(False)
   # parented to the details panel so it is a child of the window (findChildren sees it)
   # but never shown as a tab.
   ```
   Remove the two `addTab` + `setTabToolTip` calls and the now-unused `latex_index` /
   `pdf_index` locals. Keep `_bind_result_latex_pdf_schema_fields(...)` — the widgets
   still exist, the bindings are unchanged.

2. **`_RESULT_VIEW_ORDER`** → drop `"result.latex"`, `"result.pdf"` (leaves
   numeric/image/log). This automatically shrinks `result_view_specs`,
   `datalab_schema_tabs`, and `result_tabs_indices` (built by enumerating the order).

3. **Reveal-helper update (test).** In `_reveal_result_only_control`, replace the
   `indices["latex"]` / `indices["pdf"]` branches with:
   ```python
   elif key in {"results.latex.source", "latex.engine", "pdf.zoom_percent"}:
       window._offscreen_result_views.setVisible(True)
   ```
   (a real, if internal, visibility gate — the widgets become `isVisibleTo(window)`).
   Keep `pdf.zoom_percent` classified result-only.

4. **i18n / titles.** `result_view_tab_title`/`tooltip` for latex/pdf are no longer
   used for tabs; the `_register_text` calls on the inner widgets stay (labels still
   need retranslation). Verify `result_tabs_indices` consumers (`window.py:657`
   language-restore, `_reveal_result_only_control`) don't index `["latex"]`/`["pdf"]`
   anywhere else.

## Tests (TDD)

- **RED first:** a new test asserting `result_tabs` has exactly the numeric/image/log
  tabs (no TeX/PDF tab titles), AND `window.latex_edit` / `window.pdf_zoom_spin` still
  exist and carry their schema keys, AND `_offscreen_result_views` hosts them.
- Update `test_desktop_option_reachability.py::_reveal_result_only_control` per step 3.
- Regression: full reachability suite, `test_desktop_gui_workflows.py` (root round-trip
  reads `latex_edit`), `test_desktop_latex_preview_dialog.py`, workspace round-trip,
  the on-demand golden tests, shell-layout.
- Any test asserting a latex/pdf **tab** in `result_tabs` gets updated to the new
  reality (the display moved to the dialog).

## Out of scope (later 4·4 items)

- `generate_latex_checkbox` full removal (still a non-gate state-holder in the dialog).
- Bottom 「开始执行」 run_button deletion (re-point run state machine).
- Cross-restore `_last_latex_inputs` rehydration.

## Gate

Desktop suite green + ruff clean → dual-model (Codex + Gemini serial) → CodeRabbit →
user test → user-confirmed merge → `graphify update .`.
