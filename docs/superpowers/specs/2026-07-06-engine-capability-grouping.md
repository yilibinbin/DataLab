# Engine-capability-aware digit grouping (S-column width honored when supported)

**Date:** 2026-07-06 · **Branch:** `feat/toolbar-options-popup` · `main` untouched.

## Problem

The desktop app is locked to tectonic-only PDF compilation. Its bundled siunitx (3.0.49)
does not support `digit-group-size`, so the LaTeX "分组位数" (group width) cannot be varied —
S-column grouping is fixed at 3 regardless of the setting. Verified end-to-end with real
tectonic (0.15.0 and 0.16.9 both reject the key).

Meanwhile a local TeX Live (here: 2026, siunitx **3.4.14** 2025-07-09) DOES honor
`digit-group-size` — `\sisetup{digit-group-size = 6}` renders `123456 789012` in a real S
column. The original DataLab-review project "supported" width only because it compiled with
such an external siunitx.

## Decision (user-confirmed)

**Engine-capability probe + auto-fallback**, with a **user-selectable engine**:

1. **Engine selection (UI, default 自动):** a selector with three modes —
   `auto` (detect best), `bundled` (force internal tectonic), `local` (force a PATH engine).
   Lives in the LaTeX 选项 dialog (where the other LaTeX options are).
2. **Capability probe:** the first time a PDF is compiled with a given resolved engine,
   compile a tiny probe `.tex` containing `\sisetup{digit-group-size = 4}`. Success → the
   engine's siunitx supports variable width; failure (LaTeX3 key-unknown) → it does not.
   Cache the boolean per engine path for the session.
3. **Grouping strategy driven by the probe:**
   - **Supports it** → keep the S column + emit `digit-group-size = {group_size}` in the
     siunitx preamble (native variable-width grouping — the user's preferred "S 环境").
   - **Does NOT support it** → app-side text grouping: pre-group each cell with
     `group_digits_both_sides(cell, group_size)`, wrap in `\text{...}`, use a plain `r`
     column, and emit NO `digit-group-size` (so a v3.0.49 doc still compiles). This is the
     already-prototyped path.
4. **dcolumn stays a separate opt-in and is NOT defaulted on.** dcolumn mode deliberately
   disables siunitx grouping (`group-digits = false`) for alignment, so defaulting it on
   would give NO grouping. Leave it unchecked by default.

Either engine → group width works, identical UX.

## Current structure (recon)

- `shared/latex_engine.resolve_engine(engine, bundle_root)` already returns an
  `EngineChoice(path, source)` where source ∈ {system, bundled, auto-tectonic}. The
  capability to pick a non-tectonic engine already exists.
- The tectonic-only lock is `engine = "tectonic"` hardcoded at
  `app_desktop/window_latex_compile_mixin.py:134` (+ `_ensure_latex_engine` tectonic
  install path). The engine selector replaces this hardcode with the user's choice, falling
  back through resolve_engine.
- `datalab_latex/sisetup_block.build_sisetup_block(group_size, include_dcolumn)` is the
  single sisetup emitter; it currently guards `digit-group-size` behind
  `\@ifpackagelater{2024/01/01}`. New: it takes an explicit `emit_digit_group_size: bool`
  (from the probe) instead of the date guard — the app decides, not the document.
- `datalab_latex/latex_formatting.group_digits_both_sides` (PROTOTYPED) — app-side grouping,
  any width, both integer + fractional parts.

## Scope (implementation order)

1. **Engine selection + capability probe** (engine layer):
   - Add an engine-mode setting (auto/bundled/local), persisted, surfaced in the LaTeX 选项
     dialog. Default `auto`.
   - `_ensure_latex_engine` resolves per the mode (auto: prefer a PATH engine whose siunitx
     probes capable, else bundled tectonic; bundled: tectonic; local: a PATH engine).
   - Capability probe helper: compile a minimal probe doc with the resolved engine, cache
     `path -> supports_digit_group_size: bool`.
2. **sisetup emitter** takes `emit_digit_group_size` from the probe (drop the date guard).
3. **Grouping strategy** in each mode's writer non-dcolumn path: probe-capable → S column +
   native grouping; not-capable → app-side `group_digits_both_sides` + `\text{}` + `r`
   column. Statistics is prototyped; extend to root / extrapolation / error / fitting.
4. **Tests (TDD):** unit tests for `group_digits_both_sides` (widths 3/4/6/0, sign, frac,
   uncertainty tail); sisetup emitter with/without `emit_digit_group_size`; a probe-stub
   test for each strategy branch; golden regression; real-tectonic e2e that width renders
   (app-side path) and a local-engine e2e (skipped if no PATH engine) that S-column width
   renders. Full desktop + latex suites.
5. **Gate:** desktop + latex suites green + ruff → dual-model (Codex + Gemini serial) →
   CodeRabbit → user test → user-confirmed merge → graphify update.

## Risks / notes

- App-side grouping changes all modes' non-dcolumn cell text + column spec — wide golden
  blast radius; do per-mode with tests.
- The probe adds a one-time compile on first PDF per engine (~100s of ms). Cache it.
- Local-engine compiles are NOT tectonic — network-free, but depend on the user's TeX. Keep
  bundled tectonic as the guaranteed fallback so a broken local TeX never blocks a PDF.
- Keep `.tex` export intact (both strategies still produce compilable, reusable .tex).
