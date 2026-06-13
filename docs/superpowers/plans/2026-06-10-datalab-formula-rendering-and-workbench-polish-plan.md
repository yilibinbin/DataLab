# DataLab Formula Rendering and Workbench Polish Plan

## Goal

Complete the remaining gap between the current DataLab workbench and the approved professional sketch, with the formula system as the first-class priority. The current preview is readable but still too rough: it only renders through matplotlib mathtext after ad-hoc expression conversion and does not support a real LaTeX input language, advanced formula constructs, robust error feedback, or a high-fidelity preview path.

## Current Evidence

- `app_desktop/formula_preview.py::render_formula_pixmap()` converts input through `_convert_expression()` and renders with matplotlib mathtext. The docstring explicitly says it never calls external LaTeX.
- A more maintainable expression-to-LaTeX path already exists in `datalab_latex/expression_engine.py::format_latex_formula()`, and symbolic normalization already exists in `shared/symbolic_math.py`.
- `app_desktop/workbench_formula_panel.py` already owns the common formula card, debounced refresh timer, active editor tracking, and a single persistent `FormulaPreviewLabel`.
- Existing infrastructure can be reused carefully for high-fidelity rendering: TeX engine discovery helpers in `shared/latex_engine.py`, raster caps in `shared/pdf_preview_raster.py`, and Qt worker patterns in `app_desktop/workers_qt.py`. The formula preview path must wrap these in a formula-specific sandbox and must not reuse any auto-install/network path.
- The existing workbench rules still apply: no cloned data/parameter/constants/result widgets, no second compute parser, no second i18n/help registry, and no GUI-thread blocking for expensive work.

## Non-Negotiable Constraints

- Keep computation inputs single-source. Formula syntax choices are preview interpretation only in this phase. LaTeX input is display/render-only and is not fed into fitting, root solving, uncertainty propagation, safe evaluation, or workspace compute hashes.
- Do not add a third independent expression converter. Formula preview, dialogs, docs, and any future formula display should call one shared render service.
- Inline preview must be deterministic and must not require an external TeX install.
- High-fidelity LaTeX rendering may be offered only as an optional async path with timeout, cancellation, cache, and missing-engine fallback.
- All new user-facing strings must be bilingual and covered by the existing GUI inventory/scanner conventions.
- All tests must be RED first for new behavior, then GREEN with focused implementation.

## Phase 1: Unified Formula Render Service

Create a pure, non-Qt service in `datalab_latex/formula_render_service.py`.

Responsibilities:
- Define `InputLanguage`: `DATALAB`, `PYTHON`, `MATHEMATICA`, `LATEX`.
- Define `RenderRequest` and `RenderResult` dataclasses.
- Convert DataLab/Python/Mathematica-like expressions into LaTeX by reusing existing symbolic normalization and SymPy-backed formatting. The service must reconcile the current split between `datalab_latex/expression_engine.py::format_latex_formula()` and `shared/symbolic_math.py` instead of treating either path as already authoritative.
- Treat LaTeX input as display-only source, with sanitization for unsafe commands such as file inclusion, write/shell escape, definitions, and excessive length.
- Render the default preview through matplotlib mathtext, producing PNG bytes or a structured fallback. This pure service returns bytes and metadata only; it must not import PySide6 or construct `QPixmap`.
- Return structured render errors with enough data for a GUI error strip: message, source language, fallback text, and optional error position.
- Add an LRU cache keyed by source, language, lhs, dpi, color mode, and render tier.

Implementation rules:
- Refactor `datalab_latex/expression_engine.py::format_latex_formula()` to delegate to the new pure service or to a shared helper owned by that service.
- Refactor `app_desktop/formula_preview.py` to keep its public API but delegate conversion/rendering to the new service and only adapt PNG bytes into `QPixmap`.
- Remove or quarantine `_convert_expression()` and related regex conversion helpers from the active rendering path.
- Keep `FormulaPreviewDialog`, `FormulaPreviewLabel`, `render_formula_pixmap()`, and `update_formula_preview_with_empty_text()` stable for callers.

RED tests:
- `tests/test_formula_render_service.py`
  - DataLab/Python/Mathematica expression variants produce expected LaTeX fragments.
  - LaTeX source is accepted as render-only and unsafe LaTeX commands are rejected.
  - SymPy/mathtext preview returns non-empty PNG bytes for scalar formulas.
  - Unsupported advanced constructs fall back with `ok=False` and fallback text instead of blank output.
  - `lhs` formatting works.
  - cache hit avoids duplicate rendering.
  - syntax error includes a useful error message and position where available.
- `tests/test_expression_engine_formula_rendering_integration.py`
  - `format_latex_formula()` and formula preview use the same pure service path.
  - no active preview code path calls the old `_convert_expression()` regex chain.
- `tests/test_formula_preview_rendering.py`
  - public preview API still returns `QPixmap` for valid formulas.
  - invalid input falls back to source text.
  - preview label and enlarge dialog use the same render service.

## Phase 2: Formula GUI Language and Error UX

Upgrade the formula card without changing computation ownership.

Responsibilities:
- Add a compact preview syntax selector to the formula card or active formula toolbar. Its label and tooltip must make clear that it controls preview interpretation only.
- Compute editors initially expose preview interpretations for DataLab, Python-like, and Mathematica-like text. The selected interpretation must never rewrite editor text, normalize compute input, or affect model evaluation.
- LaTeX input UI must not appear until the high-fidelity preview path in Phase 3 is available. LaTeX remains render-only and is not a compute-mode formula language.
- Add a localized non-blocking error strip below the preview canvas.
- Add a clear formula-library/function-help entry that reuses existing help specs and allowed function lists.
- Persist per-mode/per-formula preview syntax choice under the existing workspace `ui` state, keyed by formula schema key, with legacy default `DATALAB`. Do not persist it under computation `config`.

RED tests:
- `tests/test_desktop_workbench_formula_panel.py`
  - language selector is visible, bilingual, and mode-aware.
  - switching syntax re-renders preview.
  - error strip appears for bad input and hides after correction.
  - function/library entry opens from the formula card.
  - the formula card still has only one persistent preview label.
- `tests/test_workspace_controller.py`
  - formula syntax choices round-trip.
  - legacy workspaces default to `DATALAB`.
  - changing preview syntax does not change `compute_workspace_hash()` and computation still consumes the raw editor text.
- `tests/test_desktop_bilingual_inventory.py`
  - new strings are bilingual and covered by affordance/tooltips.

## Phase 3: Optional High-Fidelity LaTeX Preview

Add an optional async high-fidelity render path and LaTeX-source preview UI together. This phase is the MVP for LaTeX-language rendering; do not expose LaTeX paste/input controls before this backend and its fallbacks exist.

Responsibilities:
- Create `app_desktop/formula_tex_render_worker.py` using the existing Qt worker pattern.
- Resolve TeX engines through a formula-specific wrapper around `shared/latex_engine.py`. The wrapper must disable auto-install, network/package fetch paths, and any silent engine acquisition.
- Compile a minimal sandboxed temporary document with timeout and no shell execution. The worker owns an isolated temporary working directory, no user-controlled filenames, cleanup on all exits, process-group kill on timeout/cancel, and explicit sandbox/no-shell flags where supported by the engine.
- Rasterize PDF output through `shared/pdf_preview_raster.py`.
- Emit PNG bytes to the GUI thread; construct `QPixmap` only in the GUI thread.
- Add cancellation/superseding so typing or closing the dialog cannot leave stale workers running.
- Add a cache keyed by LaTeX, engine, dpi, color mode, and page/raster settings.
- If no engine or rasterizer is available, show a localized "high-fidelity unavailable" message and keep mathtext/source fallback.
- Add LaTeX render-only input in the enlarged dialog in the same phase as the high-fidelity backend.

RED tests:
- `tests/test_formula_tex_render_worker.py`
  - mocked engine emits image bytes.
  - missing engine fails gracefully.
  - cancel before completion emits cancelled state.
  - timeout path is handled.
  - timeout/cancel kills the process group and prevents stale results from updating the closed or superseded dialog.
  - cache hit skips compile.
  - argv/env/cwd are formula-sandboxed, use no shell, use no user filenames, and do not invoke auto-install/network code.
  - missing rasterizer fails gracefully.
  - CI/no-TeX environment behavior stays deterministic.
  - matrix/cases-style LaTeX can be handled through the mocked high-fidelity path.
- `tests/test_formula_preview_dialog.py`
  - dialog exposes high-fidelity toggle.
  - LaTeX source can be pasted/rendered in dialog preview mode.
  - inline preview never invokes external TeX.
  - `cases` and matrix-style LaTeX use the mocked high-fidelity path, while inline preview falls back explicitly when TeX is unavailable.

## Phase 4: Workbench Information Architecture Polish

Continue visual convergence with the sketch after the formula system is stable.

Scope:
- Center workbench: reduce vertical sprawl by making data, formula, and variables clearer as a workflow rather than stacked legacy controls.
- Formula card: improve captions, examples, empty states, and dense multi-formula layouts using descriptor metadata, not duplicate strings.
- Constants/parameters: improve section summary, collapse/expand affordances, and compact row controls while preserving `ParameterTable`, `DetectedRowsTable`, and `ConstantsEditor`.
- Result overview: add real run-derived summary only, such as output artifact availability, warning/error count, and paths when present. Do not add fake progress or decorative metrics.
- Examples/docs: add example workspace explanations for formula syntax modes and high-fidelity preview behavior.

Tests:
- Extend screenshot matrix to include formula syntax states, but keep external TeX out of screenshot gates.
- Keep schema scan deterministic and independent of local TeX installation.
- Add workspace round-trip tests for any new UI state.
- Add visual regression assertions for panel visibility, no duplicate state owners, no horizontal scrollbars in the left rail, and formula preview readability.

## Phase 5: Quality Gates and Review

Focused gates:
- `QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_render_service.py tests/test_formula_preview_rendering.py tests/test_formula_preview_dialog.py`
- `QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_workbench_formula_panel.py tests/test_desktop_bilingual_inventory.py tests/test_workspace_controller.py`
- `QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_tex_render_worker.py`
- `QT_QPA_PLATFORM=offscreen python tools/scan_desktop_gui_schema.py`
- `QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900`

Release-quality gates:
- `python -m compileall -q .`
- `python -m ruff check $(git diff --name-only -- '*.py' 'tests/*.py' 'tools/*.py')`
- `QT_QPA_PLATFORM=offscreen pytest -q`
- Final Claude review after implementation.
- Codex review after plan and after implementation.

## Deferred

- Treating LaTeX as a computable model language.
- Full LaTeX editor with syntax highlighting/autocomplete.
- Bundling or auto-downloading TeX from the formula-preview path.
- Making inline preview render every LaTeX environment; high-fidelity dialog owns that path.
- Replacing existing compute parsers or safe-expression engines.
- Exposing LaTeX input in compute editors.

## Risks

- LaTeX-as-compute scope creep would break the existing safe-expression architecture.
- Leaving both `_convert_expression()` and SymPy-backed formatting active would preserve the current drift.
- Placing the pure render service under `app_desktop` would tie future docs/export rendering to desktop imports. The pure service belongs in `datalab_latex` or `shared`; desktop owns only Qt adapters.
- External TeX rendering can freeze the GUI if not strictly async.
- CI and screenshot gates can become flaky if they depend on local TeX availability.
- `QPixmap` cannot be safely constructed in a worker thread.
- Formula language UI state must be backward-compatible for old workspace files.
- Advanced LaTeX input must be sanitized because TeX is an execution-capable language.

## Codex Review Checklist

- Does the plan truly use one expression-to-LaTeX path?
- Is the pure language-to-LaTeX service outside `app_desktop`, with desktop only adapting bytes to Qt?
- Does it reconcile `datalab_latex/expression_engine.py` and `shared/symbolic_math.py` instead of adding a third converter?
- Does it keep LaTeX and syntax selectors render-only in this phase?
- Does the preview syntax selector leave compute text, config state, and compute hash unchanged?
- Does it avoid cloned data/parameter/constants/result state?
- Are inline preview and high-fidelity preview separated clearly?
- Are LaTeX input UI and high-fidelity rendering delivered together?
- Are all expensive paths asynchronous, cancellable, sandboxed, no-network, no-auto-install, and timeout-killed?
- Are screenshot/schema gates deterministic without TeX?
- Are workspace migration and bilingual strings covered?
- Are advanced editor features correctly deferred?
