# Section 2 — 自适应工作台分批实施计划

> Lead synthesis of five verified/adversarially-fact-checked batch plans for the DataLab Adaptive Workbench (desktop, PySide6). All file:line citations below were re-verified against live code on branch `main` at synthesis time. Where a source plan's citation was wrong, the corrected coordinate is used and the discrepancy is flagged. Frozen ratchet baselines: `panels.py`=2167, `window.py`=3181, `window_extrapolation_mixin.py`=1132 (`tests/test_file_size_ratchet.py:27` `_BASELINE`, `_HEADROOM`=40 at :22, `_SOFT_LIMIT`=800 at :19). **Current actual** line counts (verified): `panels.py`=2169, `window.py`=3198, `window_extrapolation_mixin.py`=1129, `workbench_layout.py`=154, `workbench_toolbar.py`=234, `workbench_visual_contract.py`=97, `settings_store.py`=460, `formula_preview.py`=295, `workbench_formula_panel.py`=789.

---

## 概览

Five batches. **Batch 1 is the structural keystone**; Batches 2–4 have hard or soft ordering dependencies on it. **Batch 5 (Polish) is functionally independent** of 1–4 and can land in any slot, but it touches `window.py` and adjacent formula files, so it is sequenced to avoid merge conflicts.

| # | Delivers | Depends on | Why this order |
|---|----------|-----------|----------------|
| **1 — Shell scaffold** | Icon rail as a root-HBox sibling of the splitter; wraps today's config content in a `CurrentPageStack` (page 0 = existing config); flips result-rail stretch 2:0→2:1; functional 折叠(⌘[ / Ctrl+[) + page-switch wiring. **ZERO controls moved.** | — | Establishes `workbench_config_stack` + `workbench_icon_rail`, the surfaces every later batch mounts into. Must land first so Batch 2 has a real page host and Batch 4's persisted `active_config_page` key is not a dead no-op. |
| **2 — Control migration** | Extracts the 6 compute controls (precision/uncertainty/parallel) into `workbench_options_page.py`; relocates export/workspace entry points into secondary pages. | **Batch 1 (hard, see 未决 Q-A)** | Cannot safely orphan visible controls. If Batch 1's stack exists, the extracted page mounts into 选项 page 1; otherwise it must mount into the existing visible rail (interim fallback). |
| **3 — Run/Stop toolbar state** | F04: toolbar Run/Stop reflect run state (Run visible+enabled idle; Stop visible+enabled running); deletes two ghost dispatch names; F19: pins toolbar Run as the always-visible Run (defers `run_section` relocation). | Soft: references `workbench_config_rail` (exists today, `workbench_layout.py:123`); no code dependency on Batch 1's stack. | Independent of the stack; ordered after 1–2 only to avoid `window.py` merge churn. |
| **4 — Fold-to-widen + focus + memory** | Fold-to-widen (config collapse → result rail widens via explicit `setSizes`), focus mode (Ctrl+Shift+F), layout memory (3 new QSettings keys). View menu with checkable actions. | Soft on Batch 1: `workbench_icon_rail`/`workbench_config_stack`/`active_config_page` are `getattr`-guarded no-ops until Batch 1 lands. | Fold operates on `workbench_config_rail` + `_main_splitter`, both present today, so it can precede Batch 1 — but the persisted `active_config_page` key is dead until Batch 1 (未决 Q-D). |
| **5 — Polish (F03/F14/empty-state)** | F03 compute-run progress feedback; F14 dark-mode-aware formula preview color; result-area empty-state load-example card. | None functional. | Touches `window.py` + formula files; sequence last (or in a parallel worktree) to minimize conflict with 1–4's `window.py` edits. |

**Recommended landing order: 1 → 2 → 3 → 4 → 5**, each in its own worktree/branch, merged only after the shared gate (below) is green.

---

## 全局不变量与验证策略

### 不变量 (every batch MUST preserve — verified anchors)

1. **3-pane splitter, `count()==3`.** `build_workbench_main_splitter` adds exactly three children — `config_scroll`, `workspace_scroll`, `result_frame` (`app_desktop/workbench_layout.py:130-132`), each `setCollapsible(index, False)` (`:133-134`). No batch may `addWidget`/`removeWidget` on the splitter. Guarded by `tests/test_desktop_workbench_layout.py:44`, `tests/test_splitter_persistence.py:121`, `tests/test_desktop_mode_stack.py:136`. **Fold/focus (Batch 4) hides a child via `setVisible(False)` — never removes it.**
2. **Config-rail `QScrollArea` keeps `objectName == CONFIG_RAIL_OBJECT` (`"workbench_config_rail"`).** Set in `make_config_rail` (`workbench_layout.py:57-66`, stored on owner at `:123`). Constant defined `workbench_visual_contract.py:9`. Nesting a stack *inside* the scroll is allowed; renaming the scroll is not. Guarded `tests/test_desktop_workbench_layout.py:45-46`.
3. **MRO / mixin composition frozen.** No new class or base-order change; new behavior goes onto the existing `ExtrapolationWindow` main class or an existing mixin. `closeEvent` (`window.py:3107`) is on the main class, not a mixin — extending it is legal. Guarded `tests/test_window_mixin_composition_guardrails.py` (incl. `test_no_mixin_overrides_a_qt_event_handler`).
4. **`options_box` schema-clean.** `find_unbound_required_widgets(window.options_box) == []` (`tests/test_desktop_global_options_ui.py:131`; function at `app_desktop/ui_schema_binder.py:76`). Widget↔schema binding is by `self.<attr>` and is parent-independent (`panels.py` bind calls), so re-parenting a bound widget does not unbind it.
5. **Schema keys are single-owner.** No widget may double-bind an existing schema key (e.g. `results.export.csv` / `results.image.export`, bound at `panels.py:2102-2106`). A relocated button reuses the existing bound method; it does not re-bind.
6. **`FitResult` uncertainty split** (`param_errors_stat` vs `param_errors_sys`) and **precision discipline** (`with precision_guard(dps)` at every mpmath entry) — untouched by all five batches (no compute-path edits), but must not be regressed by any new worker glue (Batch 5 F03).
7. **desktop/web sync.** None of these five batches change `shared/ui_specs.py` or `shared/help_specs.json` — all are desktop-only chrome/layout. No web mirror needed; no drift.
8. **Bilingual strings** use `_dual_msg(zh, en)` / `_register_text(widget, zh, en, setter)` (signature at `window_i18n_mixin.py:314`). New user-facing menu items and cards must follow this.
9. **Persistence blob shape.** `KEY_MAIN_SPLITTER_STATE` save/restore round-trips byte-identically (`shared/settings_store.py:411`). New keys are additive under the allowlisted `MainWindow/` prefix (`_ALLOWED_KEY_PREFIXES` at `:83`, `_validate_key` at `:119`).

### 共享验证门 (shared gate — per batch, in order; no step skipped)

Each batch runs in **its own worktree/branch**; the default branch stays untouched until the user confirms a merge.

1. **TDD.** RED test first (must actually fail), then minimal GREEN, then REFACTOR. Qt tests run under `QT_QPA_PLATFORM=offscreen`.
2. **`ruff check .`** (select E,F,W) + **`mypy`** on the strict set where the touched file qualifies (`shared` is strict → Batch 4's `settings_store.py` and Batch 5's Qt-free helper modules get mypy).
3. **Codex + Gemini adversarial review** of the diff (prefer the Claude-CLI path to preserve main-account quota). Default every finding to spurious unless grounded in file:line evidence.
4. **Full suite** `QT_QPA_PLATFORM=offscreen pytest -q` green, including `tests/test_file_size_ratchet.py`.
5. **User-confirmed merge**, then **`graphify update .`**.

**Offscreen layout caveat (applies to any pane-width assertion — Batches 1, 3, 4):** an offscreen splitter reads `sizes()==[0,0,0]` until laid out. Any test asserting pane widths MUST first run `win.resize(1400,900); win.show(); QApplication.processEvents()` (pattern already used at `tests/test_splitter_persistence.py:89-91`). Prefer `isHidden()`/explicit-flag assertions over `isVisibleTo()` for visibility.

---

## Batch 1 — Shell scaffold (icon rail + config stack, ZERO test breakage)

**Files touched**
- `app_desktop/workbench_icon_rail.py` — **NEW** (~120-160 lines, <800). `make_icon_rail(owner)`. Collapse button via `_call_owner(owner, '_toggle_config_rail')` + `setShortcut('Ctrl+[')` (Q-E: `Ctrl+[`, not `Ctrl+B`). **Page-switch buttons must use `lambda`/`functools.partial` capturing the index — NOT `_call_owner`**, which passes no index arg (`workbench_toolbar.py:43-62`, confirmed).
- `app_desktop/workbench_layout.py` — `make_config_rail` returns a **4-tuple** (adds the `CurrentPageStack`); build the stack, `scroll.setWidget(stack)` **directly** (do not route through `_scroll_wrapper`, which renames its content arg — objectName-clobber risk). `build_workbench_main_splitter` stores `owner.workbench_config_stack` and flips `setStretchFactor(2, 0)` → `setStretchFactor(2, 1)` (currently `:137`, verified — result rail is child index 2, stretch 0 today).
- `app_desktop/panels.py` — in `build_ui`, replace `addWidget(_main_splitter, 1)` (currently at `:337`) with an HBox host `[icon_rail | splitter]`; add `workbench_icon_rail`. Leave `_refresh_main_splitter_left_min_width` (defined `panels.py:583`) unchanged.
- `app_desktop/window.py` — add `_toggle_config_rail` (alias `_toggle_config_collapsed` used by Batch 4) and `_show_config_page(index)` delegators, bounds-guarded `0 <= index < stack.count()`.
- `tests/test_desktop_workbench_icon_rail.py` — **NEW**.

**Ordered TDD steps**
1. **RED** — write the test file with the *corrected* collapse assertion (see risk C1 below): do NOT assert `visual_contract_issues == []` after collapse.
2. **GREEN (layout)** — `make_config_rail` builds `config_content` (explicit `objectName`), wraps in `CurrentPageStack` (page 0 = config_content), `scroll.setWidget(stack)` directly; return 4-tuple; splitter stores `owner.workbench_config_stack`, flips stretch `(2,0)→(2,1)`.
3. **GREEN (icon rail)** — collapse button via `_call_owner`; page buttons via `lambda`/`partial(index)`.
4. **GREEN (panels)** — HBox host replaces the `addWidget(_main_splitter,1)` at `panels.py:337`.
5. **GREEN (window)** — `_toggle_config_rail` + `_show_config_page` with the `0 <= index < stack.count()` guard.
6. **VERIFY** — new test + pinned suite under offscreen; watch `tests/test_desktop_workbench_layout.py:44-46`.
7. **REFACTOR** — ruff the five files; confirm ratchet headroom.

**New/updated tests**
- `test_icon_rail_is_root_hbox_sibling_not_splitter_child` — icon rail lives in the HBox host; `splitter.count()==3`; `splitter.indexOf(icon_rail)==-1`.
- `test_config_stack_page0_is_config_content` — the stack is a `CurrentPageStack`, is the config scroll's `.widget()`, and `widget(0) IS workbench_config_content`.
- `test_collapse_hides_config_and_widens_result` — after collapse: `config_rail.isVisible()` False; `count()==3`; result width increased; visual-contract issues limited to the single config missing-region entry (**NOT `== []`** — see C1).
- `test_splitter_state_still_round_trips` — save/restore keeps 3 panes + left-min-width invariant.

**Behavior preservation (file:line)**
- 3-pane count preserved: icon rail goes into the new HBox host, never `splitter.addWidget` (`workbench_layout.py:130-132` unchanged).
- Config scroll keeps `CONFIG_RAIL_OBJECT`; the stack is nested *inside* it (`workbench_layout.py:57-66`).
- No mixin/MRO edits → `tests/test_window_mixin_composition_guardrails.py` unaffected.
- `options_box` stays a child of config_content page 0; `window.options_box` still resolves (`tests/test_desktop_global_options_ui.py:131`).
- Splitter save/restore blob shape unchanged (nesting deeper, but splitter children identical) — `tests/test_splitter_persistence.py:121`.
- left-min-width math unchanged: `CurrentPageStack.minimumSizeHint` delegates to config_content (`current_page_stack.py:16-20`); leave `panels.py:597` untouched.

**Risks + mitigations**
- **C1 (CONFIRMED DEFECT in the naïve test):** after collapse, `visual_contract_issues` is NOT `[]` — the `missing_workbench_region` check (`workbench_visual_contract.py:66-67`, verified) fires for the hidden config rail because it is *not* gated by visibility. → Rewrite the assertion to expect exactly the config missing-region entry. **(Batch 4 later relaxes this check to make a hidden config rail a legal state — see cross-batch section.)**
- **C2 (CONFIRMED):** `_call_owner` passes no index; page-switch buttons need `lambda`/`partial`.
- **C3 (CONFIRMED):** objectName clobber if the stack is routed through `_scroll_wrapper` (renames content arg). → Set config_content name explicitly + `scroll.setWidget(stack)` directly.
- **C4 (CONFIRMED):** `_show_config_page` needs the `0 <= index < stack.count()` guard (out-of-range `setCurrentIndex` warns; not a clean no-op).

**File-size impact:** `panels.py` 2169 → ~2175 (limit 2207, PASS). `workbench_layout.py` 154 → ~164 (<800). NEW `workbench_icon_rail.py` ~120-160 (<800). `window.py` 3198 → ~3212 (limit 3221, PASS, ~9-line headroom — tight). Test file exempt.

---

## Batch 2 — Control migration + frequency tiering

> **Adjudication (contradiction between the two Batch-2 readings resolved in favor of the fact-checked version):** the original plan's mitigation of "leave the extracted page parentless on owner until Batch 1" is **rejected as a user-visible regression** — it removes 6 live controls from the running GUI. This batch **hard-depends on Batch 1** (未决 Q-A); if the orchestrator insists on landing it before Batch 1, the extracted page MUST mount into the existing visible rail (`workbench_config_layout` / `output_setup_section_layout`) as an interim fallback.

**Files touched**
- `app_desktop/workbench_options_page.py` — **NEW**. Extract `panels.py:920-1032` (the 6 compute controls + parallel restore/save wiring). **Do NOT move `panels.py:916-919`** — that is `options_box = QGroupBox('选项')` + `self.options_box = options_box` + title registration + `options_layout = QVBoxLayout(options_box)`; `options_box` must stay in `panels.py` as the schema-scanned container. **`build_options_stack_page(owner)` must return `tuple[QWidget, dict]` where the dict carries all 8 bind inputs**: `label_precision`, `unc_label`, `lbl_parallel_mode`, `lbl_parallel_workers`, `lbl_parallel_reserve`, `lbl_nested_policy`, **`parallel_mode_items`**, **`nested_policy_items`** — the last two are consumed by the bind call (`panels.py:1108-1109`). Returning only labels raises `TypeError` at the bind call.
- `app_desktop/panels.py` — `build_left_panel` (698-1137). Source all 8 bind inputs from the returned dict at the `_bind_global_options_schema_fields` call (`panels.py:1100-1113`, takes 11 kwargs). `_bind_global_options_schema_fields` itself (defined `panels.py:1772`) is **not** moved — only called. Mount the returned page widget into a **visible** container this batch.
- `app_desktop/workbench_history_page.py` — **NEW** (secondary pages). Reuse existing handlers — verified names: `self.new_workspace` / `self.open_workspace` / `self.save_workspace` / `self.save_workspace_as` / `self.open_example_workspace` (workspace QActions in `build_menu`, `panels.py:207-243` — the **menu bar**, not toolbar buttons), and `self._export_csv_data` / `self._export_result_plot` (export buttons at `panels.py:1247` / `:1275`). **NOT** `self.export_csv` / `self.export_*` as an earlier draft stated. Do not re-bind `results.export.csv` / `results.image.export` on relocated buttons (already owned, `panels.py:2102-2106`).
- `tests/test_desktop_options_page_migration.py` — **NEW**.
- `tests/test_file_size_ratchet.py` — **OPTIONAL** baseline lower for hygiene; **not test-forced** (growth-only check at `:108`; actual 2169 already ≤ 2167+40).

**Ordered TDD steps**
1. **RED (attribute preservation)** — assert the 6 widgets survive with identical `objectName`/range/default/schema_key. Verified ranges: precision `MIN..MAX_MPMATH_DPS` default 16 (`panels.py:924-925`); uncertainty 1..12 default 1 (`:935-937`); max_workers 0..1024 default 0 (`:966-968`); reserve 0..1024 default 1 (`:970-972`). Schema keys: `options.precision_digits`, `options.uncertainty_digits`, `parallel.mode`, `parallel.max_workers`, `parallel.reserve_cores`, `parallel.nested_policy` (`panels.py:1789-1855`). **`datalab_schema_required` is True only for precision/uncertainty/mode/nested_policy**; `max_workers` + `reserve_cores` are `required=False` (`panels.py:1830,1840`) — do NOT assert required=True on those two.
2. **GREEN (extract)** — move `panels.py:920-1032`; return `tuple[QWidget, dict]` with all 8 inputs.
3. **RED (schema binding intact)** — `find_unbound_required_widgets(window.options_box) == []` still holds (moved required widgets are no longer Qt-children of `options_box`; `ui_schema_binder.py:76-87`).
4. **GREEN (rewire bind)** — source all 8 values from the returned dict. Inline LaTeX-group labels (`panels.py:1049,1055,1063`) stay in `options_box`, passed unchanged.
5. **RED (page hosts controls, visibly)** — assert each of the 6 controls' parent-ancestry reaches **`window.workbench_config_rail`** (the visible pane-0 scroll area), NOT `workbench_config_content`. **⚠ CORRECTION (Codex, CONFIRMED against `current_page_stack.py:7`):** page 0 of the stack IS `workbench_config_content`; a NEW 选项 page mounted in `workbench_config_stack` is a **sibling** of `workbench_config_content` and a **child of the stack**, so migrated controls are NOT descendants of `workbench_config_content`. Asserting ancestry to `workbench_config_content` would FALSE-FAIL. Assert ancestry to `workbench_config_stack` (Batch-1-present) or `workbench_config_rail` (always valid, covers the interim mount too). This still catches the orphan regression (a parentless page fails the rail-ancestry check).
6. **GREEN (placement)** — mount the page widget into the 选项 stack page (Batch 1 present) or into `output_setup_section_layout` (interim). Same batch — do not defer mounting.
7. **RED (secondary pages reuse handlers)** — assert workspace buttons connect to `self.new_workspace`/`open_workspace`/`save_workspace` and export buttons to `self._export_csv_data`/`self._export_result_plot`.
8. **GREEN (thin relocation)** — connect new `QPushButton`s to the exact existing bound methods; **do not re-bind** export schema keys. Mount into a stack page only if `getattr(owner,'workbench_config_stack',None)` exists.
9. **Regression sweep** — include `tests/test_desktop_global_options_ui.py` (`:131` options_box schema-clean).
10. **Ratchet (optional)** — `wc -l`; lower `_BASELINE['app_desktop/panels.py']` only for hygiene.
11. `graphify update .`

**New/updated tests**
- `test_moved_compute_controls_preserved` — 6 widgets survive identical `objectName`/range/default/schema_key; NOT asserting required=True on `parallel.max_workers`/`parallel.reserve_cores`. Guards workspace save/load getattr at `app_desktop/workspace_controller.py:752-753` (load) / `:1113-1114` (save) — **corrected path/lines** (an earlier draft's `workspace_controller.py:745,1112` implying `datalab_core/` is wrong on both file and line).
- `test_options_box_has_no_unbound_required_widgets` — `find_unbound_required_widgets(window.options_box) == []` (function `ui_schema_binder.py:76`; assertion mirrors `test_desktop_global_options_ui.py:131`).
- `test_compute_controls_remain_visible` (**ADDED**) — parent-ancestry of each of the 6 controls reaches `window.workbench_config_rail` (or `workbench_config_stack` when Batch 1 present), NOT `workbench_config_content` (migrated controls are siblings of page 0, not its descendants — see step 5).
- `test_secondary_pages_reuse_existing_entrypoints` — reuse of `self._export_csv_data`/`_export_result_plot` and `self.new_workspace`/`open_workspace`/`save_workspace`.

**Behavior preservation (file:line)**
- `options_box` created at `panels.py:916-919`, added to `output_setup_section_layout` at `:1122`; kept in `panels.py`. Moving `920-1032` is safe for the schema-clean test (`:131` checks only `options_box`'s own Qt-child subtree).
- `_bind_global_options_schema_fields` (`panels.py:1772-1786`) requires 11 kwargs incl. `parallel_mode_items`+`nested_policy_items` (`:1781-1782`) → extraction must return them.
- Widget binding is parent-independent (`bind_field` by `self.<attr>`, `panels.py:1930-1956`).
- 3-pane splitter untouched this batch (`count()==3`).
- Export buttons carry schema (`panels.py:2102-2106`) → reuse handler, no re-bind.

**Risks + mitigations**
- **Orphaned controls (rejected mitigation):** leaving the page parentless removes 6 visible controls. → Mount into the visible rail in-batch; treat Batch 1's stack re-parent as a later no-op.
- **Wrong return signature:** `dict[str,QLabel]` omits the two item-lists → `TypeError` at bind. → Return all 8.
- **Wrong citations (corrected):** `workspace_controller` is `app_desktop/` at `752-753`/`1113-1114`/`1474-1476`; `find_unbound_required_widgets` is `ui_schema_binder.py:76`; schema-clean assertion is `test_desktop_global_options_ui.py:131`.
- **Wrong handler names (corrected):** `self._export_csv_data`, `self._export_result_plot`; workspace actions are menu `QAction`s (`panels.py:207-243`). No double-bind of export schema keys.

**File-size impact:** `panels.py` 2169 → ~2056 after moving ~113 lines (well under limit). Two new modules <800. Ratchet update optional (growth-only check, actual already under baseline+40).

---

## Batch 3 — Layout-coupled GUI fixes (F19 Run placement, F04 toolbar Run/Stop state)

**Files touched**
- `app_desktop/workbench_toolbar.py` — Run method list `['run_extrapolation','run_calculation']` (`:175-176`); Stop list `['stop_calculation','_stop_current_worker']` (`:186-187`). **Neither `run_extrapolation` nor `stop_calculation` is a desktop OWNER method** — toolbar dispatch resolves only against the owner (the window) via `_call_owner` (`workbench_toolbar.py:43`), and the window has no such attribute (`getattr(window,'run_extrapolation',None) is None`), so both are no-op fall-throughs and safe to delete. **⚠ Precision (Codex, CONFIRMED):** `run_extrapolation` is NOT literally "zero defs anywhere" — it exists as a core service function at `datalab_core/extrapolation.py:103` (unrelated to toolbar dispatch); `stop_calculation` genuinely has zero defs. Deleting the two toolbar STRINGS is safe regardless, because dispatch never reaches the core function. Delete both ghost strings → Run `['run_calculation_start']`, Stop `['_stop_current_worker']`. Add `dynamic_owner.workbench_stop_button.setVisible(False)` after `:192`.
- `app_desktop/window.py` — overrides `_set_button_to_stop_mode` (`:677`) and `_set_button_to_run_mode` (`:683`, verified). Append `apply_workbench_run_toolbar_state(self, running=True/False)` at each tail (lazy import inside the method, matching existing style).
- `app_desktop/workbench_run_toolbar_state.py` — **NEW** (<60 lines). `apply_workbench_run_toolbar_state(owner, *, running)` with `getattr` None-guards on `workbench_run_button`/`workbench_stop_button`. running: stop visible+enabled, run hidden; idle: reverse.
- `app_desktop/window_extrapolation_mixin.py` — `run_calculation` at `:180-184` **is a toggle** (`if self._has_running_worker(): self._stop_current_worker(); return`); `_has_running_worker` at `:112-119`. Add `run_calculation_start(self)` to **this same mixin** (no MRO change): `if self._has_running_worker(): return; self.run_calculation()`.
- `tests/test_desktop_workbench_toolbar.py` — EXISTS (133 lines); **ADD** F04/F19 tests, do not overwrite.
- `app_desktop/theme.py` — OPTIONAL `#workbench_stop_button` rule mirroring the run-button active style (`:698-702`); `theme.py` is not ratchet-baselined. Skip if default styling acceptable.

**Ordered TDD steps**
1. **STEP 0 (orient)** — confirmed: neither ghost is a desktop OWNER method (`getattr(window,...) is None`), so both toolbar strings are safe to delete (note `run_extrapolation` DOES exist as a core service fn at `datalab_core/extrapolation.py:103`, unrelated to toolbar dispatch; `stop_calculation` has no def); `run_calculation` toggle at mixin `:180-184`; window overrides `:677`/`:683`; config-panel run_button (`panels.py:1124-1136`) unchanged. Correction: config rail + splitter are built in `workbench_layout.py:57-66,110-123`, NOT `panels.py`; only `run_section` is in `panels.py:717-721`. Toolbar is added to `workbench_root` (`panels.py:334-335`) BEFORE `_main_splitter` (`:336`) → toolbar is outside the splitter.
2. **RED (F04 state)** — idle: run `isHidden()==False`, stop `isHidden()==True` (use `isHidden()`, not `isVisibleTo`, under offscreen). Then `_set_button_to_stop_mode()` → stop shown/run hidden; `_set_button_to_run_mode()` → reverted. **Idle correctness depends entirely on STEP 6.**
3. **RED (F04 no-toggle)** — stub `_has_running_worker→True` (plain bool), record `_stop_current_worker`, click `workbench_run_button`, assert `_stop_current_worker` NOT called. Genuinely RED today (Run's first method resolves to the toggle).
4. **GUARD (not RED)** — assert `getattr(window,'run_extrapolation',None) is None` and `getattr(window,'stop_calculation',None) is None`. Already None today — a green regression guard, not RED-first.
5. **GREEN** — create `workbench_run_toolbar_state.py` with None-guarded getattr.
6. **GREEN (choke point)** — append `apply_workbench_run_toolbar_state(self, running=True)` after `window.py:681`; `running=False` after `:685`.
7. **GREEN (initial state — MANDATORY)** — add `workbench_stop_button.setVisible(False)` after `workbench_toolbar.py:192`. This is the ONLY thing establishing idle state at build; STEP 2 depends on it.
8. **GREEN (no-toggle Run)** — add `run_calculation_start` to the mixin; flip the two toolbar lists; delete both ghosts. `_call_owner` passes `clicked(bool)` then falls back to no-arg on `TypeError` (`workbench_toolbar.py:52-53`) — behavior-neutral.
9. **VERIFY (shortcut)** — config-panel `run_button.clicked→run_calculation()` (`panels.py:1135`) + `setShortcut('Ctrl+Return')` (`:1130`) UNCHANGED.
10. **F19 (defer relocation)** — do NOT reparent `run_section`. ADD test asserting `window.workbench_config_rail.isAncestorOf(window.workbench_run_button) is False` (rail attr at `workbench_layout.py:123`). Relocating `run_section` would break `tests/test_desktop_shell_layout.py` left_layout order pin — deferred to a later batch that updates that test.
11. **REGRESSION** — offscreen pytest on `test_desktop_workbench_toolbar.py`, `test_desktop_shell_layout.py`, `test_desktop_workbench_layout.py`, `test_file_size_ratchet.py`, `test_window_mixin_composition_guardrails.py`. Confirm `test_toolbar_language_switch_keeps_actions` stays green — the new helper NEVER calls `setText` (visibility only).
12. `graphify update .`

**New/updated tests** (append to `tests/test_desktop_workbench_toolbar.py`)
- `test_toolbar_run_stop_reflect_run_state` — idle run visible/stop hidden (via STEP 7); after stop-mode stop shown/run hidden; reverted after run-mode. Use `isHidden()`, not `isVisibleTo`.
- `test_toolbar_run_does_not_stop_running_job` — stub running, click Run, assert `_stop_current_worker` NOT called. RED today.
- `test_toolbar_stop_button_stops_running_worker` — stub running, click Stop, assert `_stop_current_worker` called once.
- `test_toolbar_no_ghost_dispatch_names` — `run_extrapolation`/`stop_calculation` attrs None AND Run/Stop resolve real callables (`run_calculation_start`/`_stop_current_worker`).
- `test_toolbar_run_button_is_outside_config_scroll` — `workbench_config_rail.isAncestorOf(workbench_run_button) is False`. Pins F19.

**Behavior preservation (file:line)**
- 3-pane count==3: splitter (`workbench_layout.py:110-123`) untouched; toolbar edits are outside the splitter (`panels.py:334-335`).
- `run_calculation_start` on the EXISTING `WindowExtrapolationMixin` (owns `run_calculation` `:180`, `_has_running_worker` `:112`) — no new class/base-order → `test_window_mixin_composition_guardrails.py` unaffected.
- Config-panel run_button + Ctrl+Return unchanged (`panels.py:1130,1135`); `run_calculation` still a toggle for the in-config button. Toolbar helper is additive, visibility-only.
- i18n: `_apply_language` (`window.py:650-663`) re-invokes `_set_button_to_(stop|run)_mode`; the helper runs inside those, so visibility re-applies on language switch. Helper never `setText` → `test_toolbar_language_switch_keeps_actions` green.
- No widget attr renamed/removed; `workbench_run_button` (`:169`), `workbench_stop_button` (`:180`), `run_button` (`panels.py:1124`) preserved.
- No `shared/ui_specs.py`/`help_specs.json` edit → no drift. `options_box` untouched.

**Risks + mitigations**
- Ghosts confirmed non-resolvable as owner methods (`run_extrapolation` exists only as a core service fn, not on the window; `stop_calculation` has no def) → deleting the toolbar strings is behavior-neutral.
- `_has_running_worker` returns a truthy short-circuit chain, not strict bool → `run_calculation_start` guard uses truthiness; STEP 3 stub returns plain `True`.
- Idle assertion has no existing initializer → STEP 7 `setVisible(False)` is MANDATORY.
- `apply_...toolbar_state` may run before buttons exist → getattr None-guards; transitions fire only post-build.
- `run_calculation_start` reintroducing a toggle → guard before delegating; `run_calculation` stop-branch (`:182-184`) unreachable once guard passes; test pins it.
- Stop unstyled when shown → optional `theme.py` rule (outside ratchet).
- **F19 relocation batch (future)** must edit `workbench_layout.py` and WILL break `test_desktop_shell_layout.py` left_layout order pin — that test updates in that batch. (未决 Q-F: confirm the always-visible toolbar Run/Stop pair satisfies "always-visible Run" for Batch 3.)

**File-size impact:** `window.py` 3181 baseline (+~4, safe). `panels.py` no edit this batch (stays 2169). `window_extrapolation_mixin.py` 1132 baseline, actual 1129 (+~4 `run_calculation_start`, safe). NEW `workbench_run_toolbar_state.py` ~50 (<800). `workbench_toolbar.py` (234) and `theme.py` not baselined.

---

## Batch 4 — Fold-to-widen + focus mode + layout memory

> **Adjudication (contradiction with Batch 1's "never call setSizes" rule resolved):** the fold-to-widen mechanism must be **deterministic and testable offscreen**, which stretch-factor redistribution is NOT (it depends on live geometry / resize events). [Codex's own probe confirmed `setStretchFactor(2,1)`+hide DOES widen result in a live window `[0,862,530]`, but it's non-deterministic offscreen — so stretch handles interactive drag, and Batch 4 uses an explicit `setSizes` for the testable fold target.] Snapshot sizes and call `setSizes([~0, workspace, enlarged_result])` with a **length-3** list (`==count()`). This does not violate the splitter invariant — existing tests only forbid *wrong-length* `setSizes`. `count()==3` is preserved by `setVisible(False)`, never add/remove.

**Files touched**
- `app_desktop/workbench_fold.py` — **NEW** (~130-180 lines). Pure free functions on the window owner: `toggle_config_collapsed` / `set_config_collapsed` / `toggle_focus_mode` / `set_focus_mode` / `save_layout_state` / `restore_layout_state`. Fold-to-widen via snapshot + length-3 `setSizes`.
- `app_desktop/workbench_visual_contract.py` — **line numbers corrected:** `visual_contract_issues()` at `:62`; missing-region check at `:66-67` (`if not metric.visible or metric.width <= 0 or metric.height <= 0`); config.visible-gated width check at `:74`; region_order at `:92`. **Relaxation:** in the `:66` loop, skip the `missing_workbench_region` emission for `CONFIG_RAIL_OBJECT` when that widget's `isHidden()` is True. `visual_contract_issues(root)` takes only `root` — read live `isHidden()`, not a passed-in flag. ~4-6 lines; file is 97 lines, no ratchet concern. **This is the relaxation that turns Batch 1's C1 config-collapsed state into a legal `== []` state.**
- `app_desktop/panels.py` — (a) call `workbench_fold.restore_layout_state(self)` at **~L432, AFTER the splitter-restore try/except block that ends at `:431`** (restoring earlier is clobbered by `splitter.restoreState`/`setSizes`). (b) `build_menu`: add a View `QMenu` with two checkable `QAction`s (`Ctrl+[` collapse, `Ctrl+Shift+F` focus) via `_register_text(widget, zh, en, 'setText'|'setTitle')` (signature `window_i18n_mixin.py:314`). If the menu grows, move it into `workbench_fold.build_view_menu`.
- `app_desktop/window.py` — non-mixin delegators mirroring the `_refresh_main_splitter_left_min_width` delegator at `window.py:593-595` (pattern `from . import workbench_fold; workbench_fold.<fn>(self, ...)`). Extend `closeEvent` (**def at `:3107`**, on `ExtrapolationWindow` main class L467, NOT a mixin) to also call `workbench_fold.save_layout_state(self)`.
- `shared/settings_store.py` — add `KEY_MAIN_CONFIG_COLLAPSED` / `KEY_MAIN_FOCUS_MODE` / `KEY_MAIN_ACTIVE_CONFIG_PAGE` next to `KEY_MAIN_SPLITTER_STATE` (`:411`), under the `MainWindow/` prefix (`_ALLOWED_KEY_PREFIXES` at `:83`). Reuse `save_bool`/`load_bool` (`:318`/`:328`) and `save_int`/`load_int` (`:267`/`:278`). +3 constants only.
- `tests/test_desktop_workbench_fold.py` — **NEW** (must run `resize(1400,900); show(); processEvents()` before any width assertion).
- `tests/test_desktop_workbench_visual_contract.py` — UPDATE (additive): `visual_contract_issues(window) == []` after `set_config_collapsed(win, True)`.
- `tests/test_splitter_persistence.py` — UPDATE (additive): one new test round-tripping the 3 keys, reusing `_fake_settings` (`:37`). Existing 3 tests unchanged (note `:123-124` reads `sizes()[0]`/`[2]` post-layout — valid, do not disturb).

**Ordered TDD steps**
1. **STEP 0 (orient)** — confirmed absent: `workbench_icon_rail`, `workbench_config_stack`, View menu, `Ctrl+[`/Ctrl+Shift+F. Fold operates on `self.workbench_config_rail` (`workbench_layout.py:123`) + `self._main_splitter`. `mode_stack` is in `workbench_workspace_layout` (center pane, `panels.py:353`), NOT a splitter child → `count()==3` regardless of fold.
2. **RED (collapse)** — `resize/show/processEvents`; snapshot pre-collapse result width; `_toggle_config_collapsed()`; assert `config_rail.isVisible() is False`, `count()==3`, `len(sizes())==3`, result width ≥ pre-collapse. Toggle back → visible True, count 3.
3. **GREEN (collapse)** — `set_config_collapsed(win, True)`: snapshot `cur = splitter.sizes()` (len 3); `config_scroll.setVisible(False)`; build length-3 sizes putting ~0 (or config min) at index 0, adding freed width to result (index 2), keeping workspace (index 1) ≥ min; `splitter.setSizes(new_sizes)`. Expand: `setVisible(True)` + restore snapshot. Add window.py delegators per `:593-595` pattern.
4. **RED (focus)** — same setup; `_toggle_focus_mode()`; assert focus flag True, config hidden, result is widest (`max(sizes())` index==2), `count()==3`; toggle off restores prior config visibility.
5. **GREEN (focus)** — `set_focus_mode(win, True)`: snapshot `_pre_focus_config_collapsed` + sizes; hide config rail; hide `getattr(win,'workbench_icon_rail',None)` if present; `setSizes` pushing max width to result (index 2). Exit: restore config to `_pre_focus_config_collapsed` + restore snapshot; re-show icon rail if previously shown. `mode_stack` untouched (5-mode invariant, `test_desktop_mode_stack.py` indices 0-4).
6. **RED (visual contract)** — `visual_contract_issues(window) == []` with config collapsed; normal window still `== []`.
7. **GREEN (visual contract)** — in the `:66` loop, skip `missing_workbench_region` for `CONFIG_RAIL_OBJECT` when its live `isHidden()` is True. `:74`/`:92` checks are already config.visible-gated, auto-skip a hidden rail.
8. **RED (memory)** — set collapsed+focus, `save_layout_state(win)`, restore into a fresh window / re-read keys, assert flags restored (via `_fake_settings`).
9. **GREEN (memory)** — `save_layout_state` writes `KEY_MAIN_CONFIG_COLLAPSED` (save_bool), `KEY_MAIN_FOCUS_MODE` (save_bool), `KEY_MAIN_ACTIVE_CONFIG_PAGE` (save_int from `getattr(config_stack,'currentIndex',lambda:0)()`) via `win._settings_store` (cached in `build_ui`, `panels.py:383`). `restore_layout_state`: load_bool default False, load_int default 0 (min 0/max pages); apply set_config_collapsed/set_focus_mode; apply active page only if `workbench_config_stack` exists. Wiring: closeEvent save (`window.py:3107`) + build_ui restore at `panels.py:~432` after `:431`.
10. **INTEGRATION** — offscreen pytest on listed files + `test_file_size_ratchet.py`; ruff + mypy on `shared/settings_store.py` (mypy strict covers `shared`); `graphify update .`
11. **STEP 11 (animation)** — animation is OFF by default (Q-E): the `set_*` collapse/focus path is the non-animated path and is what tests exercise; any 150ms fold animation is an optional, off-by-default enhancement layered on top, never in the test path.

**New/updated tests**
- `test_config_collapse_hides_rail_keeps_count_three` (show/resize/processEvents before width asserts).
- `test_focus_mode_maximizes_result` (`max(sizes())` index==2, needs layout cycle).
- `test_focus_exit_restores_prior_collapse`.
- `test_layout_state_round_trips` (via `_fake_settings`; save_bool/load_bool + save_int/load_int).
- `test_shortcuts_registered` (`Ctrl+[` / Ctrl+Shift+F QActions present & checkable).
- `test_collapsed_config_rail_is_a_legal_state` (isHidden()-gated skip).
- `test_layout_flags_round_trip` (additive; existing 3 splitter-persistence tests unchanged).

**Behavior preservation (file:line)**
- 3-pane count: collapse = `setVisible(False)` on config child + length-3 `setSizes`; never add/remove, never wrong-length `setSizes`. `count()==3` (`test_splitter_persistence.py:121/178`, `test_desktop_mode_stack.py:136`).
- MRO: only free functions + non-mixin delegators mirroring `window.py:593-595`; `closeEvent` extension on the main class (`:3107`), not a mixin → `test_no_mixin_overrides_a_qt_event_handler` green.
- `options_box` untouched (only View menu + restore call added).
- workspace/`.datalab` path untouched; layout memory uses separate `MainWindow/` keys.
- No `shared/ui_specs.py`/`help_specs.json` change → no drift.
- Persistence: `KEY_MAIN_SPLITTER_STATE` save/restore byte-identical; new keys additive under allowlisted prefix (`_validate_key` at `:119`).

**Risks + mitigations**
- **setStretchFactor redistribution is non-deterministic offscreen** (Codex probe: live window `[0,862,530]` DOES widen, but not reliably in headless tests) → Batch 4 uses an explicit length-3 `setSizes` for a deterministic, testable fold target. (Overrides Batch 1's blanket "never setSizes" → narrowed to "never wrong-length setSizes".)
- **Offscreen sizes read `[0,0,0]` until show/resize/processEvents** → every width-asserting test runs the layout cycle first.
- **`isHidden()` distinguishes explicit `setVisible(False)` from off-screen parent** → STEP 7 relaxation sound.
- **Corrected line numbers:** `visual_contract_issues` `:62`; window delegator template `:593-595`; `closeEvent` def `:3107`; `_refresh_main_splitter_left_min_width` def `:583` (called `:363`/`:418`); splitter-restore block spans `:373-431` → restore at `:432`.
- **Ratchet math (frozen baselines):** `panels.py` current 2169, baseline 2167, limit 2207, headroom LEFT 38; `window.py` current 3198, baseline 3181, limit 3221, headroom LEFT 23 — keep window additions terse.
- icon_rail/config_stack absent → getattr-guarded no-ops.
- `Ctrl+[` / Ctrl+Shift+F custom `QKeySequence` strings, no in-app collision; mirrored in View menu.

**File-size impact:** NEW `workbench_fold.py` ~130-180 (<800). `panels.py` 2169 → ~2187 (limit 2207, 38-line cushion). `window.py` 3198 → ~3208 (limit 3221, 23-line cushion). `workbench_visual_contract.py` 97 → ~103. `settings_store.py` +3 constants (460 → ~463). No baseline raise required.

---

## Batch 5 — Polish (F03 progress feedback, F14 dark-mode formula preview, empty-state card)

> Functionally independent of Batches 1–4. Touches `window.py` + formula files, so sequence last (or a parallel worktree) to avoid `window.py` merge churn. **`window.py` ratchet headroom is tight (23 lines) — see file-size impact.**

**Files touched**
- `app_desktop/formula_render_color.py` — **NEW** (<60 lines, Qt-free). `preview_formula_color(dark: bool) -> str` → `'#111827'` (light) / a light gray (e.g. `'#E5E7EB'`) (dark). Single source for F14.
- `app_desktop/formula_preview.py` — add an optional `color` param (default `'#111827'` — keeps legacy/dialog callers byte-identical) to `render_formula_pixmap()` (def `:198`; `RenderRequest` built `:218`) AND `update_formula_preview_with_empty_text()` (def `:237`; `RenderRequest` built `:258-264`). Pass `color` into BOTH `RenderRequest` constructions. Both call sites currently omit `color`, so `RenderRequest.color` falls back to its dataclass default `'#111827'`.
- `app_desktop/workbench_formula_panel.py` — in `refresh_formula_workspace_panel()` (def `:408`) compute `color = preview_formula_color(is_dark_theme())` and pass into the `update_formula_preview_with_empty_text(...)` call (`:453-462`). **`is_dark_theme` is NOT currently imported here** (theme import block `:24-32` omits it) → add `is_dark_theme` + `preview_formula_color` imports.
- `app_desktop/window.py` — **F14:** `_apply_desktop_theme()` (def `:2135`) does NOT currently refresh the formula preview (the `refresh_workbench_formula_panel` calls at `:2202-2203`/`:2345-2346` live in `_on_mode_change` etc.) → adding a refresh is genuinely new behavior. Reuse the already-computed `new_dark` (`:2144`) + already-imported `is_dark_theme` (`:2137`); add the `clear_formula_renderer_cache` import (not yet imported). Call the WINDOW method `self.refresh_workbench_formula_panel()` (def `:605`, hasattr-guarded like sibling refreshes `:2161-2172`) — NOT the module-level `refresh_formula_workspace_panel(self)`. **F03:** `_start_worker_with_workbench_result_state()` (def `:2741`) currently only connects `worker.failed` via `_install_workbench_worker_failure_guard` (`:2746`/`:2753`) with a try/except marking failed → wire the progress helper here.
- `app_desktop/workbench_run_progress.py` — **NEW** (<200 lines). Progress-feedback helper for F03 compute runs.
- Empty-state load-example card — result-area widget shown when no result exists, offering a load-example action.

**Ordered TDD steps**
1. **RED (F14 color source)** — unit-test `preview_formula_color(True)` != `preview_formula_color(False)`; light == `'#111827'`.
2. **GREEN** — create `formula_render_color.py`.
3. **RED (formula_preview threads color)** — assert both `render_formula_pixmap` and `update_formula_preview_with_empty_text` accept `color` and pass it into `RenderRequest`; default `'#111827'` keeps `FormulaPreviewDialog._render_formula` (`:122`) byte-identical.
4. **GREEN** — add the param + thread into both `RenderRequest` constructions.
5. **RED (panel uses theme color)** — assert `refresh_formula_workspace_panel` passes a dark-aware color; requires the new imports.
6. **GREEN** — add imports + compute `preview_formula_color(is_dark_theme())`.
7. **RED (theme change refreshes preview)** — assert `_apply_desktop_theme` calls `self.refresh_workbench_formula_panel()` (hasattr-guarded).
8. **GREEN** — reuse `new_dark`/`is_dark_theme`; add `clear_formula_renderer_cache` import; call the window method.
9. **RED (F03 progress)** — assert `_start_worker_with_workbench_result_state` wires progress feedback without regressing the existing failure guard (`:2746`/`:2753`).
10. **GREEN** — create `workbench_run_progress.py`; wire it in.
11. **RED/GREEN (empty-state card)** — result area shows the load-example card when no result; the card's action reuses an existing example-load handler.
12. **REGRESSION** — offscreen pytest on formula/window/result tests + `test_file_size_ratchet.py`; ruff + mypy on the Qt-free `formula_render_color.py`; `graphify update .`

**New/updated tests**
- `test_preview_formula_color_is_theme_aware` (Qt-free unit).
- `test_formula_preview_threads_color_into_render_request` (both functions; default byte-identical).
- `test_formula_panel_uses_dark_aware_color`.
- `test_apply_desktop_theme_refreshes_formula_preview` (hasattr-guarded window method call).
- `test_start_worker_wires_progress_without_regressing_failure_guard`.
- `test_result_area_shows_empty_state_card_when_no_result`.

**Behavior preservation (file:line)**
- Default `color='#111827'` keeps `FormulaPreviewDialog._render_formula` (`:122`) and all legacy callers byte-identical.
- `_apply_desktop_theme` reuses existing `new_dark` (`:2144`) / `is_dark_theme` (`:2137`); the new preview refresh is additive and hasattr-guarded (mirrors `:2161-2172`).
- F03 wiring is additive to `_start_worker_with_workbench_result_state`; the existing failure guard (`:2746`/`:2753`) stays connected.
- No compute-path edit → precision discipline + `FitResult` split untouched.
- No `shared/ui_specs.py`/`help_specs.json` change → no drift.
- 3-pane splitter untouched (result-area card is a result-rail child, not a splitter child).

**Risks + mitigations**
- **Wrong refresh call:** `refresh_formula_workspace_panel(self)` is the module-level func; the window delegates via `panels.refresh_workbench_formula_panel` → call `self.refresh_workbench_formula_panel()` (def `:605`).
- **Missing imports:** `is_dark_theme` (in `workbench_formula_panel.py`) and `clear_formula_renderer_cache` (in `window.py`) are not yet imported → add them.
- **`window.py` ratchet:** current 3198, limit 3221, only 23-line cushion. F14+F03 additions must be terse; if `_apply_desktop_theme` + `_start_worker...` glue exceeds budget, push logic into `workbench_run_progress.py` / a helper rather than inline.
- Multi-line `RenderRequest` at `:258-264` (an earlier draft cited only `:259`) — edit the whole construction.

**File-size impact:** NEW `formula_render_color.py` <60, `workbench_run_progress.py` <200 (both <800). `formula_preview.py` 295 → ~300 (not baselined). `workbench_formula_panel.py` 789 → ~793 (approaching 800 soft limit — watch it; if it crosses, the empty-state helper must go elsewhere). `window.py` 3198 → keep under 3221 (tight, ~23-line budget for F14+F03 glue combined). Not ratchet-baselined: `formula_preview.py`, `workbench_formula_panel.py` (789 is under the 800 soft limit but any new file/split must stay under 800).

---

## 跨批次一致性

**Shared attributes / objectNames established once, consumed later (do NOT rename after creation):**

| Symbol | Created in | Consumed by |
|--------|-----------|-------------|
| `owner.workbench_config_stack` (a `CurrentPageStack`) | Batch 1 (`workbench_layout.py` `build_workbench_main_splitter`) | Batch 2 (mount 选项/历史/工作区 pages), Batch 4 (`active_config_page` restore) |
| `owner.workbench_icon_rail` | Batch 1 (`panels.py` HBox host) | Batch 4 (hide/show in focus mode, getattr-guarded) |
| `_toggle_config_rail` / `_toggle_config_collapsed` / `_show_config_page(index)` | Batch 1 (`window.py`) | Batch 4 (fold/focus reuse the collapse path) |
| `CONFIG_RAIL_OBJECT == "workbench_config_rail"` | Existing (`workbench_visual_contract.py:9`, `workbench_layout.py:123`) | **Must remain unchanged** — Batch 1 nests a stack inside it; Batch 3 asserts ancestry against it; Batch 4 gates the visual-contract relaxation on its `isHidden()`. |
| `owner.workbench_run_button` / `owner.workbench_stop_button` | Existing (`workbench_toolbar.py:169`/`:180`) | Batch 3 flips their dispatch lists + visibility; must not be renamed. |
| `run_calculation_start` | Batch 3 (`window_extrapolation_mixin.py`) | Toolbar Run dispatch |
| `KEY_MAIN_CONFIG_COLLAPSED` / `KEY_MAIN_FOCUS_MODE` / `KEY_MAIN_ACTIVE_CONFIG_PAGE` | Batch 4 (`settings_store.py`) | Layout memory round-trip |
| `preview_formula_color` | Batch 5 (`formula_render_color.py`) | `formula_preview.py` + `workbench_formula_panel.py` |

**Ordering constraints:**
- **Batch 2 hard-depends on Batch 1** for the page host (未决 Q-A). If landed out of order, Batch 2 uses the interim visible-rail mount.
- **Batch 4's `active_config_page` key is a dead no-op until Batch 1** provides the stack (未决 Q-D).
- **Batch 4's visual-contract relaxation should land after (or with) Batch 1**, because Batch 1's collapse path first creates the hidden-config state that trips the un-relaxed `missing_workbench_region` check (Batch 1 risk C1). If Batch 4 precedes Batch 1, its relaxation is harmless (no hidden config exists yet) but its `test_collapsed_config_rail_is_a_legal_state` needs the collapse path — so Batch 4's own `set_config_collapsed` (which it defines) satisfies this independently of Batch 1.
- **Batch 3's F19 relocation is explicitly deferred**; the future relocation batch must edit `workbench_layout.py` and update `tests/test_desktop_shell_layout.py`'s left_layout order pin.

**⚠ CUMULATIVE `window.py` ratchet budget (Codex, CONFIRMED — was budgeted per-batch, must be cross-batch):**
`window.py` is 3198 lines today; ratchet baseline 3181 + 40 headroom → hard limit **3221** (`test_file_size_ratchet.py:27,108`). Batches 1/3/4/5 each add glue to `window.py` and were EACH budgeted against 3198 in isolation — but the ratchet is cumulative, so their combined additions can exceed 3221 and fail a LATER batch's suite even though each looked fine alone. **Rule:** track a shared running total. Est. additions: B1 ~23, B3 ~15, B4 ~20, B5 ~12 → 3198+70 = ~3268 > 3221. **Mitigation (mandatory):** each `window.py`-touching batch must either (a) move its new glue into a NEW <800-line module (preferred — e.g. `workbench_fold_controller.py`, `workbench_run_state.py`) and keep `window.py` a thin caller, or (b) consciously raise the baseline in `test_file_size_ratchet.py` in that batch's PR with a one-line rationale. Default to (a). Batch 1's `_toggle_config_*`/`_show_config_page` and Batch 4's fold/focus controller are the biggest — put them in new modules, not `window.py`.

**What CANNOT change until which batch:**
- The 3-pane splitter's child set and `count()==3` — **never** (all batches).
- `CONFIG_RAIL_OBJECT` — **never**.
- `options_box`'s identity + schema-clean status — must survive Batch 2's extraction unchanged (only its 6 compute children move; `options_box` itself stays in `panels.py:916-919`).
- The two ghost dispatch strings `run_extrapolation`/`stop_calculation` — removed **only in Batch 3**; earlier batches must not depend on them (they are already no-ops).
- `run_section` placement in `left_layout` — **frozen through Batch 3** (F19 relocation deferred); do not reparent until the dedicated relocation batch.

**Explicitly-flagged contradiction between source plans (adjudicated + corrected by external review):**
- Batch 1 asserts "never call `setSizes`" as a splitter-safety rule; Batch 4 needs fold-to-widen. **Resolution:** the real invariant is "never a *wrong-length* `setSizes`, never add/remove children." A length-3 `setSizes` is safe and is the deterministic Batch-4 mechanism.
- **⚠ CORRECTION (Codex, CONFIRMED via its own offscreen probe):** the plan's justification "`setStretchFactor` alone does NOT widen the result rail, probe `[0,109,69]`" is **FALSE for the live window**. Codex's probe: hide-only keeps result unchanged (`[0,1072,320]`), but `setStretchFactor(2,1)` + hide DID widen result (`[0,862,530]`). So the result-rail `stretch 0→1` (Section 1) already contributes to fold-to-widen. The reason to STILL use an explicit length-3 `setSizes` in Batch 4 is **determinism** (stretch redistribution depends on live geometry / resize events and is not reliable offscreen for tests), NOT because stretch "doesn't work." Fix the plan's wording to say: stretch handles interactive redistribution; Batch 4 uses length-3 `setSizes` for a deterministic, testable fold target.

---

## 已决问题 (RESOLVED via external dual-model adjudication — Codex + Gemini 3.1 Pro, 2026-07-03)

Both models adjudicated all 6. Q-A/C/D/F: both AGREED. Q-B/E: models split → adjudicated against code (below).

- **Q-A → HARD-GATE Batch 2 on Batch 1** (both agree). Clean mount into the `workbench_config_stack` 选项 page; the interim visible-rail mount stays documented only as an emergency fallback if forced out of order.
- **Q-B → DO NOT seed empty pages; keep page 0 only, make page-switch buttons for non-existent pages disabled/no-op until Batch 2** (Codex; adjudicated over Gemini's "seed empty pages"). *Reasoning:* empty pages would show a blank panel when clicked (worse UX than a disabled button) and add inert widgets; disabled buttons are simpler and honest. `CurrentPageStack.minimumSizeHint()` follows the current page (`current_page_stack.py:16`) so a single-page stack sizes correctly.
- **Q-C → Relocate ONLY existing entry points; reuse the workspace menu `QAction` handlers (`panels.py:207-243`) and existing export buttons; NO history/compare logic and NO duplicate schema-bound surfaces in Batch 2** (both agree). Duplicating a schema-bound export widget would create two widgets competing for one key (`panels.py:2102-2106`).
- **Q-D → Ship `KEY_MAIN_ACTIVE_CONFIG_PAGE` only in the layout-memory batch (Batch 4), getattr-guarded — NOT before Batch 1's stack exists** (both agree; Codex: persisting a constant 0 today proves nothing).
- **Q-E → (1) freed width goes to the RESULT rail (index 2) via explicit length-3 `setSizes`; (2) shortcut = `Ctrl+[` (not `Ctrl+B`); (3) animation OFF by default.** *Reasoning:* Codex CONFIRMED all text editors are `QPlainTextEdit`/`NumberedTextEdit` (no built-in Ctrl+B bold — that's `QTextEdit`), so `Ctrl+B` has no ACTUAL conflict; but Gemini's UX point stands that `Ctrl+B` reads as "bold" to users, and `Ctrl+[` has zero downside — adjudicated to `Ctrl+[`. Result-rail target and animation-off: both agree.
- **Q-F → Toolbar Run/Stop pair SATISFIES F19 for this batch; `run_section` relocation deferred; config-panel `run_button` stays as-is (its `_set_button_to_stop_mode` toggle unchanged this batch)** (both agree). Expanding the config button's toggle logic would widen Batch 3's scope/risk.

## 审阅记录 (methodology)
Section 2 plan passed the external gate after: Gemini **PASS** (all anchors/invariants/contradictions verified); Codex **FAIL → 4 findings, all adjudicated CONFIRMED against code and fixed in-place**: (1) Batch-2 ancestry test must target `workbench_config_stack`/`workbench_config_rail` not `workbench_config_content`; (2) cumulative `window.py` ratchet budget (est. 3268 > 3221 limit → move glue to new <800-line modules); (3) the `setStretchFactor` "doesn't widen" justification was false (use length-3 `setSizes` for DETERMINISM, not because stretch fails); (4) `run_extrapolation` wording (it exists in `datalab_core/extrapolation.py:103`, just not as a desktop owner method — toolbar deletion still safe). A re-review confirms the corrected plan (below).
