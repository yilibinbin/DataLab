# Adaptive Workbench — Section 1: Architecture & new layout contract (DESIGN, not yet built)

> **STATUS: dual-external-model PASS (2026-07-03), v4.** Codex + Gemini 3.1 Pro both PASS after 4 rounds of adversarial review (each round found real, code-confirmed issues, all fixed): R1 rejected the 4th-pane premise; R2 fixed the options_box inventory + fold-to-0 conflicts; R3 fixed the QVBoxLayout root shape + CurrentPageStack requirement; R4 resolved the workbench_config_content/left_layout test-contract collision. Both models ran live Qt probes confirming CurrentPageStack sizing and setVisible-collapse redistribution. Safe to proceed to Section 2 (batch plan).
>
> **Batch-2 note (Codex, not a blocker):** the schema scanner + `test_desktop_global_options_ui.py:130-131` inspect `window.options_box` (`tools/scan_desktop_gui_schema.py:815-818`). Batch 2's per-control migration must preserve or update that inspection point — consistent with the deferred-migration contract below.

## Current state (verified in repo)
- `app_desktop/workbench_layout.py:build_workbench_main_splitter(owner)` builds a horizontal `QSplitter` with THREE panes:
  - `widget(0)` = `config_scroll` — a `QScrollArea` objectName `workbench_config_rail`, stretch 0, minWidth CONFIG_RAIL_MIN_WIDTH(320)+viewport overhead.
  - `widget(1)` = `workspace_scroll` — a `QScrollArea` objectName `workbench_workspace_canvas`, stretch 1, minWidth WORKSPACE_CANVAS_MIN_WIDTH(520).
  - `widget(2)` = `result_frame` — a `QFrame` objectName `workbench_result_rail`, stretch 0, minWidth RESULT_RAIL_MIN_WIDTH.
  - `splitter.setSizes([CONFIG_RAIL_WIDTH(320), workspace_width, RESULT_RAIL_WIDTH(380)])`; `setChildrenCollapsible(False)`; every pane `setCollapsible(index, False)`.
- `app_desktop/panels.py:336` calls `build_workbench_main_splitter(self)`; then `panels.py:343-347` aliases `left_layout`/`_left_scroll`=`workbench_config_rail` and calls `self._build_left_panel()` to fill the config rail.
- **FULL, VERIFIED `options_box` inventory** (`QGroupBox("选项")` at `panels.py:916`, added at `panels.py:1122`). It is a FREQUENCY-MIXED box, not purely low-freq — Codex round-2 CONFIRMED it holds MORE than precision/parallel:
  - **Low-freq (compute config):** `mpmath_precision_spin` (数值精度位数), `uncertainty_digits_spin` (不确定度位数), `parallel_mode_combo` (资源策略), `parallel_max_workers_spin` (最大 workers), `parallel_reserve_cores_spin` (保留核心), `parallel_nested_policy_combo` (嵌套并行策略).
  - **LaTeX output group** (`panels.py:1033-1089`, inside `latex_options_widget`): `generate_latex_checkbox`, `output_file_edit`+`output_browse_button`, `latex_input_precision_spin`, `dcolumn_checkbox`, `latex_group_size_spin`, `caption_checkbox`+`caption_edit`.
  - **Per-run toggles:** `generate_plots_checkbox` (生成图片, `panels.py:1091`), `verbose_checkbox` (显示详细日志, `panels.py:1097`).
  - Then `run_button` (开始执行) is added right after at `panels.py:1124` (relevant to F19).
  - All these are wired to schema via `_bind_global_options_schema_fields` (`panels.py:1100`) and read by name in workspace save/load (`workspace_controller.py:745,1112`) — so migration is a per-control CONTAINER move that MUST preserve every `self.<name>` attribute + objectName + the schema binding call.
- **PER-CONTROL migration decision (Batch 2 will finalize; NOT "move the whole box"):** precision + parallel (6 controls) → 选项 panel page (genuinely low-freq). LaTeX-output group + generate_plots + verbose are per-RUN, not low-freq — they likely stay in/near the run area OR move to a 导出 panel page; decided in Batch 2, not assumed here.
- **⚠ CORRECTION (Codex round-1, CONFIRMED):** 显示位数/小数位数 (`display_digits_spin`) and 科学计数 (`scientific_checkbox`) are NOT in options_box — they live in the RESULT NUMERIC TAB (`panels.py:1224-1235`, `numeric_layout`), modeled as `result.numeric` in `DESKTOP_RESULT_VIEWS` (`shared/ui_specs.py:807`). They STAY in the result tab.
- The 5 job modes live in `self.mode_stack` (reparented into the workspace canvas at `panels.py:353`).
- `_refresh_main_splitter_left_min_width()` + `_clamp_workbench_splitter_sizes()` (panels.py) keep min-widths; they tolerate a defensive 4th pane already (tests `test_splitter_refresh_preserves_defensive_extra_panes`, `..._fallback_total_excludes_extra_panes`).
- Pinned layout-contract test: `tests/test_desktop_workbench_layout.py:test_main_area_uses_config_workspace_result_regions` asserts `splitter.count()==3`, `widget(0)` is a QScrollArea named config_rail, `widget(1)` canvas, `widget(2)` result frame. Other tests reference CONFIG_RAIL_MIN_WIDTH etc. `visual_contract_issues(window)` in `workbench_visual_contract.py` also enforces invariants.

## Proposed new structure (4 zones)
Replace the 3-pane splitter's left side with an icon rail + a collapsible config panel STACK:

```
[icon rail] │ [config panel stack]   │ [workspace canvas]  │ [result rail]
  ~52px     │  collapsible ~210px     │  elastic stretch=1  │  elastic stretch=1
 always on  │  QStackedWidget         │  (mode_stack etc.)  │
 stretch 0  │  stretch 0, foldable    │                     │
```

- **Icon rail** (NEW, `workbench_icon_rail`): thin always-visible `QFrame` with icon buttons.
- **Config panel stack**: a `QStackedWidget` holding config + low-freq pages.
- **Workspace canvas + result rail**: result rail stretch 0 → **stretch 1** (fold-to-widen).

## ⚠ REVISED after external review (Gemini FAIL — 3 code-confirmed flaws; ALL adjudicated CONFIRMED against code)
The original "add a 4th splitter pane / icon rail at widget(0)" is UNSAFE and REJECTED:
- **Index shift breaks live logic.** `_refresh_main_splitter_left_min_width()` (panels.py:604-625) hardcodes panes 0/1/2 = config/workspace/result (`sizes[:3]`, `minimums=[left,center,right]`). Icon rail at index 0 shifts every pane → wrong clamping. Its 4th-pane tolerance is TRAILING-only (`sizes[3:]`), never leading. CONFIRMED at panels.py:604-625.
- **count()==3 asserted in THREE test files** (not one): test_desktop_workbench_layout.py:44/72/75, test_desktop_mode_stack.py:136, test_splitter_persistence.py:121/178. And `QSplitter.saveState()` persistence (closeEvent saves it; restore asserts `sizes()[0..2]` + `_left_scroll.horizontalScrollBar().maximum()==0`, test_splitter_persistence.py:121-125) becomes incompatible with a pane-count change. CONFIRMED.
- **Fold-to-0 fights three guards:** `CONFIG_RAIL_MIN_WIDTH=320` via setMinimumWidth (workbench_layout.py:64) + `setChildrenCollapsible(False)`/`setCollapsible(index,False)` (115/134) + `visual_contract_issues` flags `config.width<320` (workbench_visual_contract.py:72). CONFIRMED.

## Proposed new structure (3 panes PRESERVED — icon rail OUTSIDE the splitter)
Keep the splitter at EXACTLY 3 panes. **CORRECTION (Codex round-2, CONFIRMED):** `workbench_root` is a **QVBoxLayout** (`panels.py:330`) stacking toolbar / splitter / status vertically — NOT an HBox. So the icon rail can't be a "root sibling left of the splitter." Correct shape: introduce an **inner content HBox** that holds `[icon rail | splitter]`, and add THAT hbox to the root VBox in the splitter's current slot (`root_layout.addWidget(self._main_splitter, 1)` at `panels.py:337` → becomes `root_layout.addWidget(content_hbox_container, 1)`).

```
workbench_root (QVBoxLayout — unchanged)
├─ workbench_bar (toolbar)
├─ content HBox  ← NEW wrapper (replaces the direct splitter row)
│    ├─ [icon rail]  ← NEW, ~52px fixed QFrame, LEFT of splitter, NOT a splitter child
│    └─ QSplitter (STILL 3 panes, indices unchanged)
│         ├ widget(0) config zone    │ widget(1) workspace │ widget(2) result rail
│           objectName config_rail       canvas (unchanged)    stretch 0→1 (elastic)
│           hosts a CurrentPageStack
└─ status strip
```

- **Icon rail** = sibling of the splitter INSIDE the new content HBox → does NOT change `splitter.count()`, index math, or `_main_splitter.saveState()` (close saves only splitter state, `window.py:3120`).
- **Config zone = pane 0, SAME objectName `workbench_config_rail`** → QSS, `_left_scroll`, persistence, and index-0 `_refresh_*` logic all keep working. Inside it: a **`CurrentPageStack`** (`app_desktop/current_page_stack.py:7`, NOT a plain `QStackedWidget`) — page 0 = current `_build_left_panel` content; new pages = 选项 (the 6 low-freq controls), 历史, 工作区, 导出.
- **⚠ Why CurrentPageStack, not QStackedWidget (Codex round-2, CONFIRMED):** `_refresh_main_splitter_left_min_width()` derives pane-0 min-width from `workbench_config_content.minimumSizeHint()` (`panels.py:595-599`). A plain `QStackedWidget.minimumSizeHint()` is driven by the LARGEST/hidden page, which would inflate pane-0 min-width and could force the very scrollbar we're removing. The repo already has `CurrentPageStack` (a QStackedWidget subclass overriding sizeHint/minimumSizeHint to the CURRENT page) for exactly this — the config stack MUST use it.

- **⚠ EXPLICIT MIGRATION CONTRACT for `workbench_config_content` / `left_layout` (Codex round-3, CONFIRMED conflict — resolved here):**
  Today (`panels.py:343-345`): `left_layout` = `workbench_config_layout`, `left_container` = `workbench_config_content`, `_left_scroll` = `workbench_config_rail`. Load-bearing test contracts on these:
  - `test_desktop_shell_layout.py:75-85` asserts `left_layout` directly contains, IN ORDER, the widgets `mode_section` / `input_section` / `output_setup_section` / `run_section`.
  - `test_desktop_gui_redesign_scan.py:89-91` injects a probe widget into `window.workbench_config_layout` and expects it to drive the config-rail horizontal-scroll check.
  - `test_desktop_workbench_data_area.py:44,327-332` assert config sections are direct children of `workbench_config_content`.
  **The collision:** to fix hidden-page min-width, `_refresh_*` must read the STACK's current-page hint — but if `workbench_config_content` simply BECOMES the CurrentPageStack, the 4 sections stop being its direct children and all three test contracts break.
  **Resolution (design decision):** DO NOT rename `workbench_config_content`. Instead:
  1. Page 0 of the CurrentPageStack IS today's `workbench_config_content` (holding `left_layout` with the 4 sections, unchanged) → the shell-layout + data-area + scan contracts stay GREEN, `left_layout`/`left_container`/`_left_scroll` aliases unchanged.
  2. Introduce the stack as a NEW attribute `workbench_config_stack` (a `CurrentPageStack`) that CONTAINS `workbench_config_content` as page 0 plus the new pages (选项/历史/工作区/导出).
  3. Update `_refresh_main_splitter_left_min_width()` to derive pane-0 min-width from `workbench_config_stack.minimumSizeHint()` (the current-page hint) when the stack exists, falling back to `workbench_config_content` otherwise. This is a SMALL, explicit code change in Batch 1 — call it out, don't leave it implicit.
  4. The `output_setup_section`/`run_section` stay on page 0 (they're the run controls). Only the low-freq CONTROLS inside `options_box` migrate to the 选项 page in Batch 2 — the SECTION widgets themselves stay where the tests expect them on page 0. This keeps Batch 1 (shell) test-clean and defers control migration to Batch 2.
- **Fold mechanism (NOT width-0):** collapse via `config_rail.setVisible(False)` (a hidden splitter child keeps count()==3 but yields its space to the elastic result rail) OR a collapsed-state flag that relaxes the 320 min ONLY when collapsed. The 320 min-width contract stays for the EXPANDED state; the collapsed state is a separate explicitly-tested mode. MUST be prototyped in Batch 1 to confirm persistence + visual_contract behave.
- **Result rail stretch 0 → 1:** freed space flows to the result. `setSizes`/clamp operate on explicit sizes so stretch mainly affects user-drag redistribution (low risk) — a guard test is required.

## New layout contract (EXTENDS the 3-pane tests, same PR — existing count()==3 tests STAY GREEN)
- Splitter STILL `count()==3`: widget(0)=config zone (objectName `workbench_config_rail`, now a QStackedWidget host), widget(1)=workspace canvas, widget(2)=result rail (stretch 1).
- Icon rail asserted as a root-HBox sibling of the splitter (new test), NOT a splitter child.
- New guard tests: (a) no main-area vertical scrollbar when controls fit; (b) collapsing the config zone widens the result rail; (c) icon click switches the stack page; (d) saved splitter state round-trips (persistence test stays green); (e) `visual_contract_issues` updated to allow the collapsed state.

## Tooling/coupling that Batch 1 MUST update (Codex, all CONFIRMED — broader than "one contract test")
Keeping objectName `workbench_config_rail` on pane 0 (the revised plan) means MOST of these keep working unchanged. Still to handle:
- `visual_contract_issues()` hardcodes config/workspace/result objects+order (`workbench_visual_contract.py:49`) → extend to allow the icon rail sibling + collapsed state.
- Screenshot test asserts `workbench_config_rail` width (`test_desktop_workbench_visual_screenshots.py:44`) → still valid in expanded state; add collapsed-state coverage.
- Theme QSS targets `QScrollArea#workbench_config_rail` (`theme.py:716`) → keep the objectName so QSS still applies; add icon-rail QSS.
- Scan tooling searches for the rail + forces 3-pane sizes (`tools/scan_desktop_gui_schema.py:513,625`) → still 3-pane under the revised plan, but the icon rail + stack pages need scan coverage.
- **Splitter-state persistence:** restore rejects+deletes blobs whose stored pane count differs (`panels.py:395`). The revised plan KEEPS count()==3, so existing blobs stay valid — but adding the config-stack inside pane 0 does not change saved geometry. Call out in Batch 1 that any future pane-count change would invalidate blobs (graceful discard already exists).
- **No blocking issue for options_box state binding / workspace save-load** (Codex): `workspace_controller.py:745,1107` use `getattr(...)` on the control attributes, not parentage — so moving the 6 controls into a new panel page is safe as long as their `self.<name>` attributes + objectNames are preserved.

## Preserved invariants (explicit)
- **All 5 job modes** unaffected: `mode_stack` stays in the workspace canvas; only its left-of-canvas neighbors change.
- **Window mixin composition + MRO guardrails** (`tests/test_window_mixin_composition_guardrails.py`): NO mixin changes — all work is in `panels.py` (shell/panel construction) + `workbench_layout.py` (+ new small modules). No new `__init__` in mixins, no Qt-event overrides, MRO frozen list untouched.
- **Desktop/web sync**: NO semantic change to `shared/ui_specs.py` / `help_specs.json`. Controls move CONTAINERS, not specs; web frontend unaffected.
- **File-size ratchet** (`tests/test_file_size_ratchet.py`): panels.py is already at baseline 2167; moving code OUT of it (into new icon-rail/panel-stack modules) should REDUCE it, not grow it. New modules must stay <800 lines.

## Explicit questions for the external reviewers
1. Is adding a 4th splitter pane safe given `_clamp_workbench_splitter_sizes`/`_refresh_main_splitter_left_min_width` already handle N-pane, or does anything assume exactly 3 panes beyond the one contract test we plan to rewrite?
2. Does moving the options_box controls to a new panel-stack page risk breaking any state-binding (`_bind_workbench_state_roles`, `STATE_ROLE_MODEL_PATHS`) or the workspace save/load round-trip, given the widgets keep the same objectNames/attributes?
3. Is `visual_contract_issues()` (workbench_visual_contract.py) going to fail on the new structure, and is that in-scope to update in the same PR?
4. Any risk to `test_desktop_gui_screenshot_smoke` / `..._visual_screenshots` from the new zone?
5. Is making result rail stretch=1 (from 0) going to fight the existing setSizes/clamp logic?
