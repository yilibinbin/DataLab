# DataLab Desktop — Toolbar Options Popups (QFrame) Design

**Date:** 2026-07-04  **Status:** approved (user confirmed 2026-07-04)
**Supersedes:** the icon-ified *menu-bar* approach (`2026-07-04-iconified-menubar-design.md`)

## Why this pivot

The prior redesign put 计算/LaTeX options in `self.menuBar()`. On macOS `QMenuBar` is
pulled into the **global system menu bar** (top of screen), so the options were
invisible in the window — and the left "选项" panel (`options_box`) stayed in place, so
no space was freed and the result area never grew. The user caught this in a screenshot:
"并没有按照我的要求实现GUI".

**Dual-model adversarial (Codex + Gemini, serial) returned `VERDICT: FRAME`**, with a
live Cocoa probe by Codex:
- A `QComboBox` embedded in a `QMenu` (via `QWidgetAction`) is **fragile**: the menu's
  auto-close grab fights the combo's own popup; in Codex's automation the menu behaved
  inconsistently.
- A **`QFrame(Qt.Popup | Qt.FramelessWindowHint)`** hosting the same combo **stayed open**
  when the combo dropdown opened — Qt's popup stack handles the nested popup correctly.

So the fix is not "move the menu to the toolbar" — it is **replace the QMenu host with a
QFrame popup and move the REAL controls into it**.

## Goal

Move low-frequency options out of the left config rail into two **in-window toolbar
dropdown buttons**, shrinking the rail so the result area maximizes — the user's original
request. No option may become hidden or unusable (the single-parent invariant that the
abandoned sidebar violated).

## Confirmed decisions (user, 2026-07-04)

1. **Two buttons: 计算 + LaTeX** (not one combined "选项" button).
2. **计算 popup** holds: 精度位数, 不确定度位数 · *sep* · 资源策略, 最大 workers,
   保留核心, 嵌套策略 · *sep* · 生成图片, 显示详细日志.
3. **LaTeX popup** holds: 生成 LaTeX 文件 (gate), 输出路径, 输入列位数, dcolumn, 分组位数,
   使用标题 (+ caption edit). `latex_engine_combo` stays in the LaTeX **result** tab
   (compile-time, result-only) — NOT in this popup.
4. **Freed space → result area grows.**

## Architecture (units, each independently testable)

### 1. `app_desktop/workbench_options_popup.py` (NEW, <200 lines)
A reusable popup host, no DataLab-specific knowledge:
- `build_options_popup_button(owner, object_name, text_zh, text_en, icon, tooltip_*) ->
  (QToolButton, QFrame)`:
  - A `QToolButton` (matching `make_toolbar_button` style: `ToolButtonTextUnderIcon`,
    20×20 icon, `autoRaise`, bilingual via `_register_text`).
  - A `QFrame(parent=owner)` with window flags `Qt.WindowType.Popup |
    Qt.WindowType.FramelessWindowHint`, object name `<object_name>_popup`, holding a
    `QVBoxLayout` the caller fills.
  - Toggle: button `clicked` → if frame visible, hide; else position the frame just below
    the button (`button.mapToGlobal(QPoint(0, button.height()))`, clamped to the screen)
    and `show()`. `Qt.Popup` auto-closes on outside click — no manual event filter.
- `add_form_row(frame_layout, label_widget, field_widget)` / `add_separator(frame_layout)`
  helpers so the caller lays controls out with the existing labels.
- **No control creation here** — it only hosts widgets handed in by `panels.py`.

### 2. `app_desktop/panels.py` (MODIFIED — surgical)
- **Keep every control-creation line as-is** (creation order, ranges, signal wiring,
  `_register_text`, `_bind_global_options_schema_fields`). This preserves schema binding
  and parallel-prefs persistence exactly.
- Replace the `options_layout.addWidget(...)` / `addLayout(...)` chain and the final
  `self.output_setup_section_layout.addWidget(options_box)` (line 1147) with: hand the
  assembled control groups to the two toolbar popups' frame layouts.
  - The LaTeX sub-controls are already grouped in `self.latex_options_widget` (a
    self-contained `QWidget`) — move that whole widget into the LaTeX popup as one unit;
    `generate_latex_checkbox` + the caption row go above it.
- `options_box` is **not added to the rail**. Two existing consumers must be handled
  (audited — these are the only references besides the docs):
  - `tests/test_desktop_global_options_ui.py:131` calls
    `find_unbound_required_widgets(window.options_box)` — repoint at the new popup
    container(s) (the compute + LaTeX popup frames) so the "all required widgets bound"
    guarantee is preserved, not lost.
  - `tests/test_desktop_shell_layout.py:34` lists `"options_box"` as an expected shell
    widget — update the expected-widget list to the new toolbar buttons/popups.
  - Decision: **keep `self.options_box` as the popup-content container** rather than
    deleting the attribute — simplest way to preserve the two consumers and the schema
    audit. It just moves from the rail into the 计算 popup frame (or the frame holds it).
    Confirm during implementation whether a QGroupBox reads well inside a popup; if not,
    reparent its children into the frame's layout and drop the box.
- `window.py:1279` (`self.latex_options_widget.setVisible(checked)` in
  `_toggle_latex_options`) is **unaffected** — `latex_options_widget` stays intact, only
  reparented into the LaTeX popup; the visibility toggle keeps working.
- The popups are built during toolbar construction (see unit 3); `panels.py` fills them
  after the controls exist. Build order: controls created in `build_ui` as today → popups
  filled at the same point `options_box` used to be added.

### 3. `app_desktop/workbench_toolbar.py` (MODIFIED)
- After 停止 (line 192), before `addStretch`, add the two popup buttons via unit 1,
  storing them on the owner (`owner.compute_options_button`,
  `owner.compute_options_popup`, `owner.latex_options_button`,
  `owner.latex_options_popup`). Icons: 计算 = `SP_ComputerIcon`, LaTeX =
  `SP_FileDialogDetailedView` (match the prior menu icons).
- The toolbar builds the empty popups; `panels.py` fills their layouts once controls exist
  (lazy/after-build, same pattern the old `wire_option_menus` used).

### 4. DELETE the old QMenu/mirror approach
- `app_desktop/menu_options.py`, `app_desktop/menu_option_editors.py`
- `tests/test_desktop_option_menu_editors.py`, `tests/test_desktop_option_menus.py`
- Remove the `build_option_menus` / `wire_option_menus` calls in `panels.py` (≈:249/:381)
  and the imports.
- **KEEP** `app_desktop/result_overview_popover.py` + `result_status_strip.py` and their
  tests — unaffected, already fixed (left-click guard landed).

### 5. `tests/test_desktop_option_reachability.py` (REWRITE the popup portion)
- Every schema-bound low-freq control must be reachable by **opening its toolbar popup**:
  `owner.compute_options_button.click()` (or `popup.show()`), then assert
  `control.isVisibleTo(popup)` is True AND `control.parent()` is the popup's container
  (single-parent invariant, no reparent-elsewhere).
- LaTeX gated controls (`latex_input_precision_spin` etc.): reachable after ticking
  `generate_latex_checkbox` **inside** the LaTeX popup.
- Assert `options_box` is **no longer in the left rail** (e.g.
  `getattr(owner, "options_box", None)` is None, or not a child of
  `output_setup_section_layout`).
- Keep the existing per-mode + result-only sweeps for controls that did NOT move.

## The load-bearing risk test (write FIRST, RED)

Per both models, the single biggest risk is **macOS combo-popup focus/close inside the
QFrame popup**. First failing test:

```
test_combo_dropdown_does_not_close_the_options_popup:
  open the 计算 popup; programmatically open parallel_mode_combo's view
  (combo.showPopup()); assert the 计算 popup frame is STILL visible
  (popup.isVisible() is True) and the combo view is visible.
```

If this fails, the whole approach is wrong — so it gates everything. (Offscreen Qt may not
fully reproduce Cocoa grab behavior; if the offscreen result is inconclusive, the spec
requires a real on-screen manual check before merge, per Codex's caveat.)

## Non-goals (YAGNI)
- No result-area fold/maximize toggle beyond the natural growth from a narrower rail.
- No change to the 5 job modes, mixin MRO, or web frontend.
- No hover-to-open; click-to-toggle only (simpler, matches a dropdown button).

## Bilingual / conventions
- All popup button + label text via `_register_text(zh, en)`; combos already registered.
- Match `make_toolbar_button` visual style; popup frame themed via `theme.py` if needed
  (add a `#<name>_popup` selector only if the default frame looks wrong — decide during
  implementation, not speculatively).

## Gate (project CLAUDE.md, per round)
TDD (RED combo-in-popup + reachability first) → ruff → **Codex + Gemini serial adversarial**
→ full desktop suite (offscreen) → CodeRabbit → user test on real macOS window →
user-confirmed merge → `graphify update .`. `main` stays untouched; work in the
`feat/iconified-menubar` worktree/branch (rename optional).
