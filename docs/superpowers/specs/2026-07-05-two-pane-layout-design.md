# DataLab Desktop — Two-Pane Layout + Mode Selector on Toolbar

**Date:** 2026-07-05  **Status:** draft (pending dual-model + user review)
**Builds on:** `2026-07-04-toolbar-options-popup-design.md` (options already on toolbar)

## Goal (user, 2026-07-05)

Collapse the 3-pane workbench into **2 panes** and move the compute-mode selector onto
the toolbar:

1. **计算模式 (`mode_combo`) → toolbar LEFT dropdown**, right after the DataLab identity
   label, always visible (parallels the 计算/LaTeX option buttons already on the toolbar).
2. **输入栏 merges into pane 1.** The left config rail's `input_section` (使用数据文件 +
   输入数据表格) joins the workspace pane.
3. **3-pane → 2-pane:** `[输入(top) + 配置(bottom), vertically stacked]` | `[结果]`. The
   result pane becomes 1-of-2 and gains width.
4. Run button (开始执行) + formula/param config stay with pane 1.

## Confirmed decisions
1. Mode → toolbar left dropdown (NOT a top-of-pane row).
2. Pane 1 internal order: **输入 on top, 配置 on bottom, vertical stack** (NOT an inner
   left/right split — that would re-narrow what we just widened).
3. Approach: spec → dual-model serial adversarial → TDD.

## Current structure (verified against code)

- `build_workbench_main_splitter` (`workbench_layout.py:111`): three panes —
  `config_scroll` (0), `workspace_scroll` (1), `result_frame` (2);
  `setSizes([CONFIG_RAIL_WIDTH, workspace_width, RESULT_RAIL_WIDTH])` (:148);
  `setStretchFactor(2,0)` (:137).
- `self.left_layout` (pane 0) stacks **4 sections** (`panels.py:738-741`): `mode_section`,
  `input_section`, `output_setup_section` (near-empty since options moved to the toolbar),
  `run_section`.
- `mode_combo` created in `mode_box` QGroupBox "计算模式" (`panels.py:744-766`);
  `currentIndexChanged → _on_mode_change` drives per-mode config switching (`mode_stack`).
- Splitter state persisted at `KEY_MAIN_SPLITTER_STATE`; restore already guards a pane-count
  change via `extract_splitter_pane_count` (`panels.py:412-415`) — a stale 3-pane blob is
  discarded, not applied.

## Blast radius — hard-coded 3-pane assumptions (audited; expanded after Codex review)

- `workbench_layout.py:130-148` — 3× `addWidget`, `setStretchFactor(2,0)`,
  `setSizes([...3 values...])`.
- `panels.py:596-629` — `_refresh_main_splitter_left_min_width`: **computes the left
  min-width entirely from `workbench_config_content`/`workbench_config_rail`** (597-615),
  then `splitter.count() < 3` early return (620) + `setSizes([left, center, right])` (3
  values, 627). **CRITICAL (Codex finding #2):** if the config rail detaches, this sizes
  the WRONG (detached) widget and the merged pane's min-width is never enforced. The whole
  function must be **re-anchored to the merged pane** (`workbench_workspace_content` /
  `workbench_workspace_canvas`), not just have `count()` tweaked to 2.
- `panels.py:348` — `self.left_layout`/`self.left_container`/`self._left_scroll` are ALIASES
  to the config rail (`workbench_config_*`). **These aliases must be re-pointed at the merged
  pane** so every consumer (sizing, scrollbar checks) targets the real left pane.
- `app_desktop/workbench_visual_contract.py:49-97` — **the visual contract is 3-pane**
  (Codex finding #1): `workbench_region_metrics` enumerates CONFIG_RAIL/WORKSPACE/RESULT
  (52-58); `visual_contract_issues` flags a "missing_workbench_region" if the config rail is
  not visible (66-67), enforces `CONFIG_RAIL_MIN_WIDTH` (72-75), and asserts
  `config.x < workspace.x < result.x` (88-96). **Must be rewritten for 2 panes** (drop the
  CONFIG region + the 3-way order assert; keep merged-pane + result checks) or it reports
  false issues once the config rail is no longer a visible pane.
- `theme.py:35-36` — `CONFIG_RAIL_WIDTH = 320`, `RESULT_RAIL_WIDTH = 380`. RESULT stays;
  the merged input+config pane gets a min width (reuse `CONFIG_RAIL_WIDTH` for the merged
  pane, or add `WORKSPACE_PANE_MIN_WIDTH`). Note `workbench_visual_contract.py:16-20` also
  hard-codes `CONFIG_RAIL_MIN_WIDTH`/`WORKSPACE_CANVAS_MIN_WIDTH`/`RESULT_RAIL_MIN_WIDTH`.
- **Tooling** (Codex finding #2, non-blocking for the app but update for consistency):
  `tools/scan_desktop_gui_schema.py:513` and `tools/capture_desktop_gui_screens.py:95`
  reference the config rail; audit and repoint.

Codex confirmed as SOUND (no change needed): splitter stale-3-pane persistence (the
pane-count guard at `panels.py:412-413` drops a real 3-pane blob — independently verified),
`mode_combo` reparent (`_on_mode_change` uses `self.mode_combo`/`self.mode_stack` not
parentage — `window.py:2179`), and `input_section` reparent (bindings on the widgets
themselves — `panels.py:447`, `window.py:1319`, `workspace_controller.py:1816/1932`).

## Decision (resolves Codex FAIL): merged pane = new left-pane source of truth
The merged left pane IS `workbench_workspace_*` (already the layout path for
formula/variable/mode-stack, `panels.py:353`). We:
1. Re-anchor `left_layout`/`left_container`/`_left_scroll` (panels.py:348) to the merged
   `workbench_workspace_*` pane.
2. Move `input_section` (and the config sections) into `workbench_workspace_layout` above
   the existing formula/mode-stack content.
3. Rewrite `_refresh_main_splitter_left_min_width` to size the merged pane.
4. Rewrite `workbench_visual_contract.py` to a 2-pane contract.
5. `workbench_config_rail`/`workbench_config_content` become compatibility-only (kept for
   attribute references, NOT a splitter pane, NOT sized/validated as a visible region).

## Architecture

### 1. `workbench_layout.py` (MODIFIED) — 2-pane splitter
- `build_workbench_main_splitter` adds **two** widgets: the merged left pane
  (`workspace_scroll`, now holding input + config) and `result_frame`. Drop
  `config_scroll` as a splitter child.
- `setStretchFactor(0,1)` (left grows) or keep result fixed-ish — decide by feel; default:
  left stretch 1, result stretch 0 with a sensible starting width (result WIDER than the
  old 380 since it is now 1-of-2). `setSizes([left_width, RESULT_RAIL_WIDTH])`.
- `config_scroll` / `workbench_config_content` attributes: **keep them created** (some code
  + tests reference `workbench_config_content`), but they are no longer a splitter pane.
  Decision: the merged pane's top holds `input_section`, bottom holds the config sections —
  we reuse the EXISTING `workspace_scroll`/`workspace_layout` as the merged pane and move
  `input_section` (+ the config sections that were in pane 0) into it. `config_scroll` may
  become an unused-but-present container, OR we repurpose `workspace_scroll` as the single
  left pane. Pick the minimal-reference-breakage option during impl (audit
  `workbench_config_content` / `workbench_config_rail` consumers first).

### 2. `panels.py` (MODIFIED) — section placement
- `mode_section` no longer added to `left_layout`; instead `mode_combo` is placed on the
  toolbar (unit 3). `mode_box` QGroupBox may be dropped (mode label lives on the toolbar
  button/dropdown) — keep `mode_combo` as `self.mode_combo` (30+ references).
- The remaining sections (`input_section`, config sections, `run_section`) are laid into the
  **single merged pane** top-to-bottom: 输入 (input_section) on top, then config, then run.
- `_refresh_main_splitter_left_min_width` (:620): change `count() < 3` → `count() < 2` and
  `setSizes([left, right])` (2 values). Compute left min from the merged pane's content.

### 3. `workbench_toolbar.py` (MODIFIED) — mode dropdown on the LEFT
- Immediately after the identity label / before 新建, add a mode control. Two options:
  - **(a) reparent `mode_combo` onto the toolbar** (a plain combo in the toolbar row), or
  - **(b) a `QToolButton` menu** listing the 5 modes, synced to `mode_combo`.
  - **Prefer (a):** the real `mode_combo` on the toolbar is one widget, no sync, and
    `_on_mode_change` keeps firing. But `mode_combo` is created in `panels.py` (build_ui)
    AFTER the toolbar. So: toolbar reserves a slot (a container/placeholder); `panels.py`
    inserts `mode_combo` into it once created (lazy/after-build, like the option panels).
    Label it 模式/Mode via `_register_text`.
- Ensure `mode_combo` stays reachable + `_on_mode_change` wiring intact; per-mode config
  still switches `mode_stack` in the merged pane.

### 4. Splitter persistence (VERIFY, likely no change)
- The `extract_splitter_pane_count` guard already discards a stale 3-pane blob. Add/confirm
  a test: a saved 3-pane state does NOT crash or missize the new 2-pane splitter (guard
  returns None-count → blob dropped → default 2-pane sizes applied).

### 5. Tests (TDD, RED first)
- **New/updated `test_desktop_shell_layout.py`**: splitter `count() == 2`; result pane is
  index 1; the merged pane contains both `input_section` and the config `mode_stack`.
- **New `test_desktop_mode_selector_on_toolbar.py`**: `mode_combo` is a descendant of
  `workbench_bar`; changing it fires `_on_mode_change`; each of the 5 modes still switches
  the visible per-mode config.
- **Updated reachability/layout tests**: input + config controls reachable in the single
  merged pane; no control stranded.
- **Splitter-migration test**: stale 3-pane persisted blob → clean 2-pane fallback.
- Keep all 5-mode behaviour tests green.
- **Existing 3-pane test assertions to UPDATE (audited — these break and are part of this
  change):**
  - `tests/test_desktop_workbench_layout.py:44` (`count()==3` → 2), `:46`
    (`widget(0)==CONFIG_RAIL_OBJECT` → merged pane object), `:51`
    (`visual_contract_issues==[]` — must pass against the rewritten 2-pane contract),
    `:72/:75` (`count()==3` → 2), `:76/:129` (left-size ≥ config-rail min → merged-pane min).
  - `tests/test_desktop_mode_stack.py:136-137` (`count()==3`, `len(sizes())==3` → 2).
  - `tests/test_desktop_gui_redesign_scan.py:126-129` (expects `workbench_config_rail`/
    `_left_scroll` findable — repoint to the merged pane's object).
  - `tests/test_desktop_workbench_visual_screenshots.py:45` (`config_rail width ≥
    CONFIG_RAIL_MIN_WIDTH` → merged-pane width check).
  - `tests/test_desktop_root_solving_ui.py:187`, `test_desktop_gui_schema_scan.py:194`
    (`sizes()[0] ≥ _main_splitter_left_min_width`) — KEEP working by ensuring the merged
    pane still populates `_main_splitter_left_min_width`.
  - **(Gemini serial-review additions — also break, also in scope):**
    - `tests/test_desktop_workbench_layout.py:47-50` (`widget(1)==WORKSPACE_CANVAS_OBJECT`,
      `widget(2)==RESULT_RAIL_OBJECT`) → 2-pane indices; `:65-66/:128-130/:153-154`
      (`sizes[1]`, `sizes[2]` min-width) → 2-value size asserts; `:185` defensive extra-pane
      reset → re-baseline for 2 panes.
    - `tests/test_desktop_shell_layout.py:71-87` asserts the left-pane section order
      `["mode_section","input_section","output_setup_section","run_section"]` and `:101`
      references `window.mode_section` — **`mode_section` is DROPPED** (mode → toolbar), so
      this expected list becomes `["input_section", …, "run_section"]` in the merged pane,
      and mode-section assertions are removed/repointed to the toolbar mode control.
    - `tests/test_desktop_workbench_data_area.py:215` (expects `mode_section`) and `:329`
      (`window.mode_section.parentWidget() is window.workbench_config_content`) — update:
      no `mode_section`; the input/config sections now parent under the merged pane.
    - `tests/test_desktop_theme_spacing.py:46`
      (`test_all_mode_section_cards_share_uniform_spacing`) — audit: if it iterates
      `mode_section` cards, repoint to the merged pane's cards or the toolbar mode control.
  - **Decision on `mode_section`:** keep `self.mode_section` as a (possibly empty/unused)
    attribute ONLY if cheaper than updating all consumers; but since tests assert its
    *parent* and *ordering*, cleaner to DROP it and update the ~4 test sites. `mode_combo`
    (the real widget, 30+ refs) is preserved and moved to the toolbar.
  - **(Lead independent sweep — TWO high-value files both models missed):**
    - `tests/test_splitter_persistence.py:121-124` asserts `count()==3`, `len(sizes())==3`,
      `sizes()[2] ≥ result_rail.minimumWidth()` → **update to 2 panes**. CRITICAL: `:149-167`
      `test_valid_looking_stale_blob_with_wrong_pane_count_reverts` builds a **2-pane** fake
      blob and expects a **3-pane** window to reject it — after the refactor the window is
      **2-pane**, so this test must **invert**: build a stale **3-pane** blob and assert the
      new 2-pane window rejects it (this becomes the primary migration test named in §4).
    - `tests/test_desktop_workbench_visual_contract.py` is the DEDICATED contract test:
      `test_workbench_exposes_three_column_visual_regions` (`:63`, expects 3 regions +
      `visual_contract_issues==[]`), `test_visual_contract_reports_minimum_width_violations`
      (`:98`), `test_visual_contract_reports_missing_regions_and_invalid_order` (`:132`) all
      encode the 3-pane contract. **Rewrite this file** alongside the contract rewrite in
      unit-4: two regions (merged + result), drop the `config.x<workspace.x<result.x` order
      assert, keep min-width + missing-region checks for the 2 surviving regions.
      `:79 test_workbench_keeps_legacy_public_widget_attributes` — keep (validates the
      compatibility attributes we retain).

## Audit convergence note
The 3-pane blast radius is now COMPLETE, cross-checked by Codex + Gemini (serial) plus two
independent lead sweeps. No architectural flaw remains — the design (merged pane =
`workbench_workspace_*` as left-pane source of truth; `config_rail` compatibility-only;
2-pane visual contract; mode_combo on toolbar) is sound. What remained were mechanical
test-update sites, now fully enumerated above. Ready for TDD.

## The load-bearing risks (write tests FIRST)
1. **Mode switching still works after moving `mode_combo` to the toolbar** —
   `_on_mode_change` must still fire and switch `mode_stack`. (Test: set each mode via the
   toolbar combo, assert the right per-mode config widget is visible.)
2. **Stale 3-pane splitter blob does not corrupt the 2-pane layout** — the pane-count guard
   must drop it. (Test with a real saved 3-pane blob.)
3. **No control stranded** by the merge — every input + config control reachable in the
   merged pane (reuse the reachability sweep).

## Non-goals (YAGNI)
- No change to the 5 job modes' compute logic, mixin MRO, or the web frontend.
- No new result-area fold/maximize control beyond the natural widening.
- No inner left/right split of the merged pane (decision #2).

## Bilingual / conventions
- Toolbar mode control labelled via `_register_text(zh, en)`; `mode_combo` already
  registered bilingually via `_register_combo`.
- Reuse `theme.py` width constants; add `WORKSPACE_PANE_MIN_WIDTH` only if needed.

## Gate (project CLAUDE.md)
spec → **Codex + Gemini serial adversarial** → TDD (RED mode-switch + splitter-migration +
reachability first) → ruff → full desktop suite (offscreen) → CodeRabbit → user test on real
macOS window → user-confirmed merge → `graphify update .`. `main` untouched; work in the
`feat/toolbar-options-popup` branch (or a fresh `feat/two-pane-layout`).
