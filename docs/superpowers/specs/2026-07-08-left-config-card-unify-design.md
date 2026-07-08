# Left workspace column → two blocks (data + one config card)

## Problem

The left workspace column stacks **four** blocks top-to-bottom:

1. `input_section` — data input (输入数据 / 常数 tabs)
2. `workbench_formula_panel` — shared formula input (per-mode QStackedWidget)
3. `workbench_variable_panel` — shared variable mapping (per-mode QStackedWidget)
4. `mode_stack` — per-mode config card (`CurrentPageStack`)

Two user complaints follow from this:

- **Fitting order feels backwards**: the model selector lives in the mode card (block 4, last),
  so formula/variable info appears *above* the model selector. The user expects
  "choose the model first, then see its fields".
- **Not one config box**: each mode should present exactly two blocks — `[输入数据]` and
  `[one config box for that mode]` — not four separate stacked widgets.

## Key facts established from the code

- All three config widgets (`mode_stack`, `workbench_formula_panel`,
  `workbench_variable_panel`) are ALREADY per-mode: each is a stacked widget with a page per
  mode, switched together on mode change. The "which mode uses what" logic already exists.
- The formula/variable panels ALREADY self-hide when the current mode has no formula/variables
  (`panel.setVisible(page_has_visible_variables)` in `refresh_variable_workspace_panel`, and
  the analogous formula refresh). So grouping them into a card leaves no empty gap — unused
  sub-blocks disappear on their own.

## Design

Wrap the three config widgets in a single container `QGroupBox` — `workbench_config_card` —
laid out vertically in this order:

1. `mode_stack` (mode selector + mode-specific config) — **top**
2. `workbench_formula_panel` (formula input)
3. `workbench_variable_panel` (variable mapping)

Add this ONE card to the workspace column as the second block, replacing the three separate
`addWidget` calls. The per-mode switching and self-hide logic inside each stack is untouched.

Result: the left column has exactly two blocks — `[输入数据 tabs]` + `[config card]`. In fitting
the card reads model-selector → (formula when custom) → variables. Modes that don't use
formula/variables show only their mode config (the sub-panels self-hide).

## Scope / blast radius

- **Touched**: `panels.py` (the build-order section that adds the three widgets — reparent them
  into a new `workbench_config_card` in the new order); `theme.py` (style for
  `workbench_config_card`, reusing the existing config-card style).
- **NOT touched**: the 5 mode views, the schema/reveal system, serialization, per-mode
  formula/variable population + self-hide logic.
- **Tests to update**: layout/screenshot tests that assert the three panels are direct children
  of the workspace column; add assertions that the column now has two blocks and the card's
  internal order is mode → formula → variable.

## Testing

- Workspace column has exactly two visible direct blocks: data tabs + `workbench_config_card`.
- Inside the card, child order is `mode_stack`, then formula panel, then variable panel.
- Switching each mode keeps the card content correct; formula/variable sub-blocks self-hide in
  modes that don't use them (no empty gap).
- Screenshot manifest updated for the new grouping.

---

## Known bugs from the three-model serial review (Claude → Codex → Gemini, code-grounded, reproduced)

Run against diff `74109e7..HEAD` (this session's UI work). To be fixed alongside / before the
config-card restructure. Severity + attribution noted.

### In-scope (introduced this session) — fix before merge

- **S1 [HIGH] mpf precision loss, two-sided.** `app_desktop/latex_inputs_serialization.py`:
  `_MPF_STR_DIGITS = 50` caps encoding at 50 significant digits, and `_decode` does
  `mp.mpf(obj["v"])` which reparses at the ambient `mp.dps`. A high-precision workspace (UI allows
  compute up to `MAX_MPMATH_DPS` + 200 LaTeX digits) loses precision on reopen → regenerated
  on-demand TeX is numerically wrong. Reproduced by all three models.
  **Fix**: encode with enough digits for the value's own precision (not a fixed 50 — e.g. derive
  from `mp.mp.dps` at encode time or a large safe cap); decode inside `mp.workdps(N)` so the parse
  is not truncated by the ambient session precision.

- **~~S2~~ [WITHDRAWN — was a misjudgment].** Codex-2 flagged that restore clears
  `use_constants_file_checkbox` → "file-backed constants silently become manual". Verifying
  against the suite showed this is BY DESIGN: on save the file's CONTENTS are captured as an
  attachment and inlined into the editor on restore, so the workspace is self-contained and does
  not depend on the external file still existing (test
  `test_workspace_restores_file_backed_data_for_statistics_time_series` deletes the file then
  asserts checkbox=False + data inlined). The proposed "fix" broke that decoupling and was
  reverted. No data is lost; only the file-source toggle is intentionally off. Kept a regression
  test asserting the file CONTENT survives the round-trip. (Lesson: a review finding that
  contradicts an existing intentional test must be verified against the suite before "fixing".)

- **S3 [MEDIUM] `mode_stack` Maximum policy clips dynamic-growth modes.** The hollow-gap fix set
  `mode_stack` to `QSizePolicy.Maximum` + stretch=0. A mode whose config grows after layout
  (fitting → comparison reveals a candidate list) is clipped ~19px (page.height 586 < sizeHint
  603, even in a tall window). **Fix**: use `Preferred` vertical policy (grows to content) with the
  column's existing `AlignTop` preventing short-page inflation — verified un-clips (626, gap=0 on
  short modes preserved).

- **S4 [MEDIUM] stale tests** assert `manual_box` is a direct child of `input_section`, but it now
  lives under `_data_tab`: `tests/test_desktop_workbench_data_area.py:46`,
  `tests/test_desktop_workbench_editor_canvas.py:34`. **Fix**: update the parent assertions.

- **S5 [cosmetic] status chip duplication.** `_refresh_toolbar_status_chip` builds
  `f"{label} · {summary}"`; for failed/running states `_value_summary` returns the same word →
  "Failed · Failed" / "Running · Running". **Fix**: omit the summary when it equals the status word.

### Pre-existing (some newly reachable via the new constants-file UI) — separate fix

- **P-A [MEDIUM crash] unguarded file read** in `workspace_controller._capture_data_section:264`
  (`Path(path_text).read_bytes()`): saving a workspace crashes (`FileNotFoundError`) if the data OR
  constants file was moved/deleted. Exists on main for the data path; the new constants-file UI
  adds a second trigger. **Fix**: guard the read (skip/attach-empty + keep the path) for both.
- **P-B [low]** `line.split()` in the file-text canonicaliser drops empty cells → column shift.
- **P-C [low]** `use_file` True + empty path tags `source_kind="file"` but captures the manual
  table (inconsistent state, no attachment). Newly reachable via constants file UI.
- **P-D [low]** unsafe `row["name"]/row["value"]` in constants capture (KeyError on malformed row;
  compare the safe `.get()` used elsewhere). Newly reachable via constants file UI.
- **P-E [low]** implicit-config migration double-convert `AttributeError` for legacy `schema != 2`
  workspaces. Unrelated to this session.

### Refuted / theoretical (note only)

- **`__t__` tag collision**: a stash dict colliding with a real serializer tag (`{"__t__":"mpf",...}`)
  would misdecode, but the stash never holds user-controlled arbitrary dicts — not reachable.
  Optional defense-in-depth: wrap plain dicts under a `"dict"` tag so no bare `__t__` is trusted.

Adversarial note: Codex escalated S1 to the encode side; Codex refuted S3 but the refutation was
OVERTURNED by a tall-window reproduction; Gemini surfaced the pre-existing serialization cluster
(P-A…P-E). The Gemini CLI channel timed out on the full prompt and succeeded on a shorter retry.
