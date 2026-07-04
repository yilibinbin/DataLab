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

So the fix is not "move the menu to the toolbar" — it is **replace the QMenu host and move
the REAL controls into a toolbar-triggered container**.

## ⚠ AMENDMENT (2026-07-04, dual-model VERDICT: INLINE) — supersedes "QFrame popup" below

A second adversarial round (Codex + Gemini, both with live offscreen probes) reversed the
earlier "QFrame(Qt.Popup)" choice once two recon facts were on the table:
- **Cocoa-grab bug is real & untestable.** A `QComboBox` inside **any** `Qt.Popup`
  top-level (QFrame(Qt.Popup) included) can be dismissed by the native macOS grab when its
  own dropdown (also a Qt.Popup) opens. Offscreen QPA no-ops the grab, so this **always
  passes CI and only fails in production on Mac** — an unacceptable unautomatable failure
  mode for the app's primary test platform.
- **Reachability friction.** A `Qt.Popup` is a separate top-level window; the reachability
  test's `isVisibleTo(window)` + stable-parent invariants don't map cleanly onto it.

**Decision: INLINE.** Each toolbar button toggles a **normal `QWidget` child panel** (NOT
`Qt.Popup`), laid out just under the toolbar, shown/hidden via `setVisible`. Because it is
an ordinary layout child: no Cocoa grab (combos open safely), `isVisibleTo(window)` is
meaningful, parent is stable from build time, and the reachability sweep needs only a
trivial "click button → panel visible" gate. Codex's probe confirmed an inline child frame
is `isWindow()==False`, `window() is main_window`, `isVisibleTo(window)==True` when shown.
Trade-off accepted: while open the panel occupies vertical space under the toolbar (it is a
drop-down *panel*, not a floating overlay); when closed the rail is gone and the result
area is maximized. Read every "QFrame(Qt.Popup)"/"popup" below as **inline toggle panel**.

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

### 1. `app_desktop/workbench_options_panel.py` (NEW, <200 lines) — INLINE, not popup
A reusable **inline toggle panel** host, no DataLab-specific knowledge:
- `build_options_panel(owner, object_name, text_zh, text_en, icon, tooltip_*) ->
  (QToolButton, QWidget)`:
  - A `QToolButton` on the toolbar (matching `make_toolbar_button` style:
    `ToolButtonTextUnderIcon`, 20×20 icon, `autoRaise`, bilingual via `_register_text`),
    made `checkable` so its checked state mirrors panel visibility.
  - A **normal `QWidget` child** (NOT `Qt.Popup`), object name `<object_name>_panel`,
    holding a `QVBoxLayout` the caller fills. It lives in the window's layout **directly
    under the toolbar**: a dedicated `options_panels_row` (a `QWidget` with an `QHBoxLayout`
    or `QVBoxLayout` holding the two panels) inserted into the shell VBox `root_layout`
    (`panels.py:342`) at **index 1** — i.e. `root_layout.insertWidget(1, options_panels_row)`,
    between the toolbar (`workbench_bar`, added at :347) and the 3-pane splitter
    (`_main_splitter`, added at :349). `setVisible(False)` initially; the row itself may be
    zero-height when both panels are hidden.
  - Toggle: button `toggled(checked)` → `panel.setVisible(checked)`. Because the panel is
    a layout child, showing it drops the row down and (when closed) reclaims the space —
    no floating window, no `Qt.Popup`, so **no macOS combo-grab bug**.
  - Only ONE panel open at a time is NOT required (both may be open); but toggling one does
    not force-close the other unless we choose to (decide during impl — default: independent).
  - Auto-close-on-outside-click is **not** provided (a Qt.Popup freebie we forgo); the
    button is a toggle. Acceptable for low-freq options. (Optional later: an event filter
    to collapse on click-outside — YAGNI for now.)
- `add_form_row(panel_layout, label_widget, field_widget)` / `add_separator(panel_layout)`
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

### 5. `tests/test_desktop_option_reachability.py` (teach the sweep a panel-open gate)
- The sweep's `_record()` skips `not isVisibleTo(window)` (`:259`). With INLINE panels
  hidden by default, add an **open-panel gate**: before the sweep (or as a gate the sweep
  tries), toggle each options button checked so `panel.setVisible(True)`, exactly like the
  existing combo/checkbox gates. Then every moved control is `isVisibleTo(window)` (INLINE
  panel is a layout child → meaningful) with parent == its panel container (stable from
  build; **no reparent-on-open**, satisfying the four parent-invariant asserts at
  ~:435/:478/:506/:538).
- LaTeX gated controls (`latex_input_precision_spin` etc.): reachable after opening the
  LaTeX panel AND ticking `generate_latex_checkbox` inside it.
- Assert `options_box` no longer sits in the left rail (not a descendant of
  `output_setup_section` / the config rail).
- Repoint the two other consumers (see §2 note): `test_desktop_global_options_ui.py:131`
  container arg, `test_desktop_shell_layout.py:34` widget-name entry.
- Keep the existing per-mode + result-only sweeps for controls that did NOT move.

## The load-bearing risk test (write FIRST, RED) — INLINE makes it real offscreen

Dual-model VERDICT: INLINE precisely because the combo-in-`Qt.Popup` dismissal is
untestable offscreen. With an INLINE (non-Popup) panel there is **no Cocoa grab**, so the
combo test is meaningful in CI. First failing tests:

```
test_options_panel_hidden_until_button_toggled:
  panel is not visible initially; after button.setChecked(True) → panel.isVisible() True,
  and every moved control isVisibleTo(window) True with parent == panel container.

test_combo_in_inline_panel_opens_without_closing_panel:
  open the 计算 panel; parallel_mode_combo.showPopup(); assert the panel is STILL visible
  (panel.isVisible() True) and combo.parent() is unchanged (combo NOT reparented). Because
  the panel is a normal layout child (not Qt.Popup), this assertion is meaningful offscreen
  — it fails if code regresses to a Qt.Popup container.

test_options_box_left_the_left_rail:
  options_box is not a descendant of the config rail / output_setup_section.
```

These gate everything. A light **manual on-screen macOS check** is still listed (open each
panel, open a combo, confirm nothing collapses) — but it is now a confirmation, not the
sole guard, since INLINE removes the untestable failure mode.

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
