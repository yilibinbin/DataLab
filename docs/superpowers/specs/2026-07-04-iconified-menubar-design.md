# DataLab Desktop GUI — Icon-ified Menu Bar Redesign (user-confirmed, 2026-07-03)

Baseline: clean `main` (original 3-pane layout). The abandoned page-switch sidebar
(Batch 1/2/4) is discarded — tag `abandoned/adaptive-workbench-sidebar`.

## Confirmed direction (option B)
- 3-pane layout UNCHANGED. Every config control stays IN PLACE in the config rail —
  reachable directly, never switched away, never hidden behind a non-default page.
- Menu bar becomes ICON-IFIED and gains two option menus. The current real menu bar is
  文件 · 示例 · 语言 · 主题 · 帮助 (build_menu, panels.py:201-318). Add icons to all,
  and add TWO new icon menus placed after 文件:
  - **计算 (Compute)** — two groups separated by a separator:
    - 精度: mpmath_precision_spin (精度位数, panels.py:923), uncertainty_digits_spin
      (不确定度位数, :935)
    - 并行/资源: parallel_mode_combo (资源策略, :950), parallel_max_workers_spin
      (最大 workers, :966), parallel_reserve_cores_spin (保留核心, :970),
      parallel_nested_policy_combo (嵌套策略, :985)
  - **LaTeX** — generate_latex_checkbox (生成 LaTeX 文件, :1033), output_file_edit
    (输出路径, :1041), dcolumn_checkbox (:1057), latex_group_size_spin (分组位数, :1060),
    caption_checkbox (使用标题, :1065). NOTE: latex_engine_combo (编译引擎) is NOT included —
    it is a result-output control living in the LaTeX result tab and is only reachable after a
    result exists (see the RESULT-ONLY note in the acceptance criterion); it stays where it is.
- **Menu = ADDITIONAL entry point, NOT the only one.** The controls stay in the config
  rail. Menu items reflect/drive the SAME widget (two-way sync — literally the same
  QWidget's value, or a menu action bound to the same model path). Never a duplicate
  widget competing for one schema key.

## ⚠ CORRECTIONS from external dual-model review (Codex + Gemini, both CONFIRMED against code)
1. **LaTeX controls ARE schema-bound** (the spec's "LaTeX controls are plain widgets" was WRONG). They carry schema keys / FormFieldSpec bindings (`panels.py:1856-1956`, plus `results.latex.*` at `:1396/1407`). Treat them like the other schema-bound controls for sync.
2. **`latex_engine_combo` is a RESULT-OUTPUT control in the LaTeX result tab (right panel), NOT a config-rail option** (`panels.py:1466`, moved there per the comment at `:1115`). Its outer container `self.tabs` is hidden until a result exists (`workbench_results.py:362`), so it is NOT reachable pre-result even by switching the subtab. → Removed from the config menu; it stays in the result tab where it belongs (see acceptance criterion RESULT-ONLY note).
3. **Result popover MUST be a separate top-level popup** (`QWidget(window, Qt.WindowType.Popup)` or `QMenu`/`QFrame` popup) positioned near the overview card. Qt clips a layout-managed child to its parent's bounds, so a card cannot "progressively enlarge" over its siblings in-layout. Do NOT reparent/move the existing overview widgets — Codex: reusing/moving `workbench_result_status_badge` (`workbench_results.py:45-103`) or the shell footer strip (`workbench_layout.py:93-108`) would recreate the one-parent hiding problem. CREATE NEW popup + status widgets that READ from the same status source; don't move existing ones.
4. **Reachability test must also assert parent/identity UNCHANGED** (not just `isVisible()`): after the visible gate action, assert `widget.isVisibleTo(window)` True AND `widget.parent()` is the same as before (no reparent). This is the stronger guard against the prior hiding bug.
5. Menu build order / lazy sync: build the two new icon menus in `build_menu` (panels.py:201-319) AFTER 文件; the checkable-action↔checkbox sync signals must be connected AFTER both the menu action and the target checkbox exist (lazy/after-build), guarded with `blockSignals`.

## Result overview + status strip
- Result overview card → click/hover opens a POPOVER that progressively enlarges,
  showing the full overview (method / value / uncertainty / elapsed / #points), and
  disappears on mouse-away / click-outside.
- A MINIMAL always-visible status strip (result area footer): status badge
  (waiting/running/done/error) + method + elapsed. Visible even when panels collapse,
  so calculation status is always judgable.
- (Result maximization / fold can be a later, separate increment — NOT bundled here to
  keep this change surgical. This spec covers the menu bar + popover + status strip.)

## HARD acceptance criterion (the bug class the user caught)
Add an automated **reachability test**: for EVERY config control, assert it is reachable
via a VISIBLE, user-operable gate — i.e. after performing the visible action that reveals
it (check the gate checkbox / switch the input mode / open the menu), **`widget.isVisibleTo(window)`
is True AND `widget.parent()` is UNCHANGED** from before the action (no reparent). NEVER behind
a non-default page. Baseline on clean main (verified by probe):
- Always visible: mode_combo, method_combo, mpmath_precision_spin, uncertainty_digits_spin,
  parallel_* (4), generate_latex_checkbox, generate_plots_checkbox, verbose_checkbox, run_button.
- Gated-but-reachable (must STAY reachable): manual_data_edit (input-mode QStackedWidget),
  LaTeX config group (revealed by checking generate_latex_checkbox → verified:
  latex_input_precision_spin becomes visible), display_digits_spin/scientific_checkbox (result
  numeric tab, revealed by switching to that tab).
- **RESULT-ONLY, reachable only after a result exists** (Codex, CONFIRMED by probe):
  `latex_engine_combo` (panels.py:1466) lives in the LaTeX result subtab, and its OUTER
  container `self.tabs` is HIDDEN in the empty-result state (`tabs.setVisible(not is_empty)`,
  workbench_results.py:362). Probe: even after `result_tabs.setCurrentIndex(latex)`,
  `latex_engine_combo.isVisibleTo(window)` stays False until a result populates the tabs.
  → This is a RESULT-OUTPUT control, not a config-time option. HANDLING: do NOT put it in the
  计算/LaTeX config menu as if it were reachable pre-result. Either (a) put a LaTeX-engine item
  in the menu that is DISABLED with a tooltip ("compute a result first") until `self.tabs` is
  visible, enabling it via the same result-state signal that shows the tabs; or (b) omit it from
  the menu entirely (it already lives, correctly, in the LaTeX result tab). Prefer (b) —
  keep the menu to genuinely config-time options; the engine picker stays where results are.
  The reachability test for latex_engine_combo asserts it becomes visible ONLY in the
  non-empty-result state (drive a fake result / _update_result_visibility(is_empty=False)).
The redesign MUST keep all of these reachable AND must make the menu path reach the config-time
ones. It must NOT claim the result-only engine picker is reachable from a config menu pre-result.

## Implementation notes
- Icons: Qt has QStyle.StandardPixmap / theme icons; match existing toolbar icon style.
  Menu QActions get icons via action.setIcon(...).
- Two-way sync (RESOLVED — controls are schema-bound, verified): precision/uncertainty/
  parallel are bound via FormFieldSpec with schema keys (options.precision_digits,
  options.uncertainty_digits, parallel.mode/max_workers/reserve_cores/nested_policy;
  panels.py:_bind_global_options_schema_fields). **LaTeX controls are ALSO schema-bound**
  (Codex/Gemini CONFIRMED: config-LaTeX bindings at panels.py:1856/1947; results.latex.* at
  :1396/1407; latex_engine_combo bound via latex.engine at :1982/1991) — treat them like the
  other schema-bound controls, do NOT assume plain widgets.
  DECISION — do NOT reparent or duplicate any widget (that is exactly what hid controls
  last time). The menu items are NAVIGATION, not second copies:
    - For every control: the menu action does `focus + ensureVisible/scrollTo` the SAME
      in-rail widget (reveal its gate first if gated — e.g. check generate_latex_checkbox,
      switch input mode — then focus). One source of truth: the in-rail widget.
    - Checkboxes (dcolumn, caption, generate_latex, scientific, verbose, generate_plots)
      MAY additionally be mirrored as a `checkable` QAction kept in two-way sync via
      signals (action.toggled ↔ checkbox.toggled, guarded against recursion). This is the
      only place a menu item carries state; it drives the SAME checkbox, never a copy.
  This keeps a single widget per option, so nothing can be "hidden on the wrong page".
- Bilingual via _register_text; no shared/ui_specs change unless a control genuinely needs it.
- File-size ratchet: keep menu-building code in panels.py within baseline or extract to a
  new <800-line module (e.g. app_desktop/menu_options.py) if it grows.

## Gate per increment
TDD (RED reachability + behavior test first) → ruff/mypy → Codex + Gemini adversarial →
full desktop suite → CodeRabbit → user test → user-confirmed merge → graphify update.

---

## AMENDMENT (2026-07-04, user-confirmed): in-menu editors, not navigation

User tested the navigation-style menu and wants the OPTIONS to be ADJUSTABLE IN THE MENU
(a small inline editor / popup), not a shortcut that jumps to the config rail.

**Mechanism (safe — no reparenting):** each 计算/LaTeX value item becomes a `QWidgetAction`
hosting a NEW mirror widget (a fresh QSpinBox/QComboBox/QCheckBox matching the real
control's range/items), two-way synced to the real in-rail control via signals with
recursion guards (blockSignals). The real control STAYS in the config rail — the menu
shows an editable copy. This preserves the single-parent invariant (the reachability
test still passes — no widget is reparented) AND gives real in-menu adjustment.

- Compute controls (verified): mpmath_precision_spin (QSpinBox 10..1000000), uncertainty_digits_spin
  (1..12), parallel_max_workers_spin (0..1024), parallel_reserve_cores_spin (0..1024) →
  mirror QSpinBox; parallel_mode_combo (自动/串行优先/线程优先/进程优先), parallel_nested_policy_combo
  (嵌套时串行/允许嵌套) → mirror QComboBox.
- LaTeX: generate_latex_checkbox/dcolumn_checkbox/caption_checkbox → mirror checkable (already
  done as checkable QAction); output_file_edit (QLineEdit) → mirror QLineEdit or a "browse…" that
  drives the real one; latex_input_precision_spin/latex_group_size_spin → mirror QSpinBox.
- Sync: mirror.valueChanged/currentIndexChanged/textChanged → real.set*, and real's signal →
  mirror, both blockSignals-guarded to prevent loops. The real control is the source of truth.
- Gated LaTeX editors: setting them still reveals the gate (check generate_latex_checkbox) as today.
- The menu must not close on every keystroke — a QWidgetAction keeps the menu open while editing.

The reachability test is UNAFFECTED (real controls not moved). Add tests: the mirror editor
in the menu changes the real control's value and vice versa (two-way), no recursion, menu stays
open while editing.
