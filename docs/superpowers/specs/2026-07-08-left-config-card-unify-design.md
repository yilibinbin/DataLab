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
