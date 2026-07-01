# DataLab Formula Renderer Boundary Completion Plan

> **Current-state reconciliation plan.** This worktree already contains a partial renderer-boundary implementation. Do not follow older greenfield assumptions such as "file does not exist" RED tests. Implement only the remaining convergence work below.

## Goal

Complete the safe renderer-boundary portion of the Reduce3j/Mathematica-style formula rendering work by converging the existing partial implementation, preserving desktop preview performance, and adding evidence gates while keeping WebEngine/MathJax shipping disabled.

## Non-Negotiable Constraints

- Users keep entering DataLab/Mathematica-like formulas. LaTeX remains output/export/preview only.
- Do not add visible renderer/backend/style selectors.
- Do not ship or import WebEngine/MathJax in desktop runtime while existing evidence remains `NO_GO`.
- Preserve `datalab_latex.formula_render_service.render_formula()` as a compatibility API.
- Preserve unrelated dirty worktree changes; do not stage, commit, package, publish, or clean scratch files unless explicitly requested.
- Use the current canonical desktop boundary names unless a later explicit refactor plan says otherwise:
  - `app_desktop.formula_renderer.render_desktop_preview`
  - `app_desktop.formula_renderer.MathTextPngBackend`
  - `app_desktop.formula_renderer.FormulaBackend.render_formula(metadata, dpi, color)`

## Verified Current State

- `shared/formula_mathtext_png.py` exists and owns `render_mathtext_png(mathtext, *, dpi, color)`, with lazy matplotlib imports inside the function.
- `tests/test_formula_mathtext_png.py` exists and covers import purity plus PNG bytes.
- `app_desktop/formula_renderer.py` exists and exposes `render_desktop_preview()`, `FormulaBackend`, and `MathTextPngBackend`.
- `app_desktop/formula_preview.py` already imports and calls `render_desktop_preview()` in both desktop preview paths.
- `datalab_latex/formula_render_service.py` still contains its local `_render_mathtext_png()` body and `import io`; this must be delegated to the shared primitive while keeping the `_render_mathtext_png` alias monkeypatchable.
- `render_desktop_preview()` is currently uncached, so the desktop hot path no longer has the old `render_formula()` request-level cache behavior.
- Focused current RED evidence: `tests/test_formula_preview_rendering.py::test_formula_preview_with_empty_text_dispatches_selected_language` currently fails because production correctly forces `InputLanguage.DATALAB`, while the stale test still expects `InputLanguage.LATEX`.
- `app_desktop/formula_tex_render_worker.py` and `tests/test_formula_tex_render_worker.py` still exist, but production code no longer imports the worker. This is dead code from the removed high-fidelity TeX preview path and should be removed explicitly rather than silently dropped from the release matrix.
- `docs/TEST_MATRIX.md` and `tests/test_release_test_matrix.py` still reference `tests/test_formula_tex_render_worker.py`; release matrix entries need synchronization after deleting that legacy worker test.

## Task 1: Finish Shared PNG Primitive Delegation

**Files:**
- Modify: `datalab_latex/formula_render_service.py`
- Existing: `shared/formula_mathtext_png.py`
- Existing tests: `tests/test_formula_mathtext_png.py`, `tests/test_formula_render_service.py`

Steps:

1. Replace the local `_render_mathtext_png()` body in `datalab_latex/formula_render_service.py` with:
   `from shared.formula_mathtext_png import render_mathtext_png as _render_mathtext_png`.
2. Remove `import io` from `datalab_latex/formula_render_service.py`.
3. Keep all existing `_render_mathtext_png(...)` call sites unchanged so existing monkeypatch tests remain valid.
4. Keep `clear_formula_render_cache()` and `render_formula()` unchanged except for using the shared primitive through the alias.

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_mathtext_png.py tests/test_formula_render_service.py
python -m ruff check shared/formula_mathtext_png.py datalab_latex/formula_render_service.py tests/test_formula_mathtext_png.py tests/test_formula_render_service.py
python -m compileall -q shared/formula_mathtext_png.py datalab_latex/formula_render_service.py tests/test_formula_mathtext_png.py tests/test_formula_render_service.py
git diff --check -- shared/formula_mathtext_png.py datalab_latex/formula_render_service.py tests/test_formula_mathtext_png.py tests/test_formula_render_service.py
```

## Task 2: Add Request-Level Cache To Existing Desktop Boundary

**Files:**
- Modify: `app_desktop/formula_renderer.py`
- Modify: `tests/test_formula_renderer_boundary.py`

Steps:

1. Keep the existing public names: `render_desktop_preview`, `MathTextPngBackend`, and `FormulaBackend.render_formula`.
2. Add a bounded request-level default-backend cache, preferably an inner `@lru_cache(maxsize=256)`, keyed by `(source, language.value, lhs, dpi, color) -> RenderResult`.
   - Coerce the language with `InputLanguage(request.language).value`; do not use `request.language.value` directly because existing callers/tests may pass the string `"datalab"`.
3. Consult and populate this cache only when `backend is None`.
4. Bypass the cache when an injected backend is provided, so fallback and custom-backend tests are never hidden by a warm cache.
5. Expose `clear_formula_renderer_cache()` for tests.
6. Cache the full `RenderResult` for parity with the existing service cache, including fallback results, and document that this mirrors `render_formula()` compatibility behavior.
7. Add an autouse fixture in `tests/test_formula_renderer_boundary.py` clearing both `clear_formula_renderer_cache()` and `datalab_latex.formula_render_service.clear_formula_render_cache()`.
8. Add cache regressions:
   - two identical default-backend calls invoke `render_formula_metadata` once and `render_mathtext_png` once;
   - a warmed default cache does not bypass an injected backend;
   - an injected backend call does not populate the default cache;
   - `clear_formula_renderer_cache()` forces a re-render;
   - `render_desktop_preview(RenderRequest(source="x^2", language="datalab"))` succeeds and caches without `AttributeError`;
   - import purity still proves no eager `matplotlib` and no WebEngine imports.

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_renderer_boundary.py
python -m ruff check app_desktop/formula_renderer.py tests/test_formula_renderer_boundary.py
python -m compileall -q app_desktop/formula_renderer.py tests/test_formula_renderer_boundary.py
git diff --check -- app_desktop/formula_renderer.py tests/test_formula_renderer_boundary.py
```

## Task 3: Finish Desktop Preview Compatibility Tests

**Files:**
- Modify: `app_desktop/formula_preview.py`
- Modify: `tests/test_formula_preview_rendering.py`
- Modify: `tests/test_expression_engine_formula_rendering_integration.py` only if current assertions still mention render-service delegation
- Modify: `tests/test_desktop_workbench_formula_panel.py` only if stale expectations remain

Steps:

1. Keep `app_desktop.formula_preview` routed through `render_desktop_preview()`.
2. Preserve the forced `InputLanguage.DATALAB` behavior for legacy `language=` arguments because formula calculation input is not LaTeX.
3. Keep the legacy `language=` keyword as a silent, non-raising compatibility shim in this plan. Do not add a new deprecation warning here; removing/deprecating the parameter is a separate API cleanup.
4. Update the stale selected-language test to assert:
   - the render request source is stripped;
   - request language is forced to `InputLanguage.DATALAB`;
   - return result language is `InputLanguage.DATALAB`;
   - the label fallback text keeps the user's original spacing.
5. Ensure all preview monkeypatches target `render_desktop_preview`, not `render_formula` or a non-existent `render_formula_preview`.
6. Add a structural guard that `app_desktop.formula_preview` no longer exposes `render_formula`.

Known retargeted test behaviors to verify:

- `tests/test_expression_engine_formula_rendering_integration.py::test_desktop_formula_preview_delegates_png_rendering_to_render_service` should either be renamed to the renderer boundary or assert the current boundary correctly.
- `tests/test_formula_preview_rendering.py::test_formula_preview_with_empty_text_dispatches_selected_language` should become a compatibility-shim test for forced DataLab language.
- `tests/test_desktop_workbench_formula_panel.py::test_formula_workspace_preview_uses_datalab_render_language`.
- `tests/test_desktop_workbench_formula_panel.py::test_formula_workspace_error_strip_tracks_bad_preview_input`.

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py
python -m ruff check app_desktop/formula_preview.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py
python -m compileall -q app_desktop/formula_preview.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py
git diff --check -- app_desktop/formula_preview.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_preview_dialog.py
```

## Task 4: Lock Metadata/Web Boundary

**Files:**
- Modify: `tests/test_formula_render_service.py`
- Keep: `tests/test_app_web_formula_resources_baseline.py`

Steps:

1. Add a subprocess test proving `render_formula_metadata(RenderRequest(...))` does not import `app_desktop.formula_renderer`.
2. Do not add redundant concrete forbidden names to the web baseline if it already forbids the `app_desktop` prefix.
3. Keep `render_formula()` compatibility tests green.

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_render_service.py tests/test_app_web_formula_resources_baseline.py
python -m ruff check tests/test_formula_render_service.py tests/test_app_web_formula_resources_baseline.py
python -m compileall -q tests/test_formula_render_service.py tests/test_app_web_formula_resources_baseline.py
```

## Task 5: Add Renderer Value-Gate Evidence And Matrix Sync

**Files:**
- Create: `tools/formula_renderer_value_gate.py`
- Create: `tests/test_formula_renderer_value_gate.py`
- Delete or replace: `tests/test_formula_renderer_value.py`
- Modify: `docs/TEST_MATRIX.md`
- Modify: `tests/test_release_test_matrix.py`
- Delete: `app_desktop/formula_tex_render_worker.py`
- Delete: `tests/test_formula_tex_render_worker.py`
- Modify: `tests/test_formula_preview_dialog.py`

Steps:

1. Add `tools/formula_renderer_value_gate.py` with `build_report()` returning:
   - `decision: "NO_GO"`
   - `shipping_backend: "mathtext_png"`
   - `webengine_enabled: False`
   - representative formula rows containing source, metadata status, LaTeX, PNG status, and PNG error text.
2. Treat the value-gate report as evidence/posture documentation, not a computed shipping decision.
3. Add a CLI `--out` option that writes JSON.
4. Replace the scratch precursor `tests/test_formula_renderer_value.py` with `tests/test_formula_renderer_value_gate.py`; the old test writes `formula_renderer_value.json` in the repo root and must not remain collected by full pytest.
5. Add tests for `build_report()` and CLI JSON writing. The CLI test must write only under `tmp_path`; it must not create `formula_renderer_value.json` in the repository root. If matplotlib is unavailable, use graceful evidence capture or `pytest.importorskip("matplotlib")` for PNG-success assertions.
6. Delete `app_desktop/formula_tex_render_worker.py` and `tests/test_formula_tex_render_worker.py` because the high-fidelity TeX preview path is dead code and no production module imports it.
7. Add a structural guard in `tests/test_formula_preview_dialog.py` proving the legacy worker module file no longer exists and the dialog does not expose high-fidelity TeX controls.
   - Convert any remaining `raising=False` monkeypatch of a missing `FormulaTexRenderWorker` into a positive absence/single-preview assertion so the test is not vacuous after deletion.
8. In `docs/TEST_MATRIX.md`, remove the stale `tests/test_formula_tex_render_worker.py` reference and add:
   - `tests/test_formula_mathtext_png.py`
   - `tests/test_formula_renderer_boundary.py`
   - `tests/test_formula_renderer_value_gate.py`
9. In `tests/test_release_test_matrix.py::_required_release_tests()`, make the same path changes so bidirectional matrix consistency remains green.
10. Keep the JSON value-gate command in an evidence subsection, not in a mandatory packaging gate block.

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py tests/test_formula_preview_dialog.py
QT_QPA_PLATFORM=offscreen python tools/formula_renderer_value_gate.py --out build/formula-renderer-value-gate.json
python -m ruff check tools/formula_renderer_value_gate.py tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py tests/test_formula_preview_dialog.py
python -m compileall -q tools/formula_renderer_value_gate.py tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py tests/test_formula_preview_dialog.py
git diff --check -- tools/formula_renderer_value_gate.py tests/test_formula_renderer_value_gate.py tests/test_formula_renderer_value.py docs/TEST_MATRIX.md tests/test_release_test_matrix.py tests/test_formula_preview_dialog.py app_desktop/formula_tex_render_worker.py tests/test_formula_tex_render_worker.py
```

## Task 6: Aggregate Validation And External Review

Validation:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_mathtext_png.py tests/test_formula_renderer_boundary.py tests/test_formula_render_service.py tests/test_formula_preview_rendering.py tests/test_formula_preview_dialog.py tests/test_desktop_workbench_formula_panel.py tests/test_expression_engine_formula_rendering_integration.py tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_formula_export.py tests/test_formula_latex_export.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_webengine_shipping_import_guard.py tests/test_packaging_qt_excludes.py tests/test_webengine_spike_report.py tests/test_webengine_spike_assets.py tests/test_webengine_spike_contract.py tests/test_webengine_evidence_bundle_tool.py
QT_QPA_PLATFORM=offscreen python tools/scan_desktop_gui_schema.py
QT_QPA_PLATFORM=offscreen python tools/capture_desktop_gui_screens.py --out build/gui-screenshots --width 1440 --height 900
python -m ruff check shared/formula_mathtext_png.py app_desktop/formula_renderer.py app_desktop/formula_preview.py datalab_latex/formula_render_service.py tools/formula_renderer_value_gate.py tests/test_formula_mathtext_png.py tests/test_formula_renderer_boundary.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py
python -m compileall -q shared/formula_mathtext_png.py app_desktop/formula_renderer.py app_desktop/formula_preview.py datalab_latex/formula_render_service.py tools/formula_renderer_value_gate.py tests/test_formula_mathtext_png.py tests/test_formula_renderer_boundary.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_renderer_value_gate.py tests/test_release_test_matrix.py
git diff --check -- shared/formula_mathtext_png.py app_desktop/formula_renderer.py app_desktop/formula_preview.py datalab_latex/formula_render_service.py tools/formula_renderer_value_gate.py tests/test_formula_mathtext_png.py tests/test_formula_renderer_boundary.py tests/test_formula_preview_rendering.py tests/test_expression_engine_formula_rendering_integration.py tests/test_desktop_workbench_formula_panel.py tests/test_formula_renderer_value_gate.py docs/TEST_MATRIX.md tests/test_release_test_matrix.py task_plan.md findings.md progress.md
```

External review after implementation:

- Run Claude max review on the working tree.
- Run Antigravity/Gemini `Gemini 3.1 Pro (High)` review if `gemini-companion` continues returning `INVALID_STREAM`; record the fallback.
- Accept only locally supported findings, add tests, fix, and rerun focused validation plus the finding model until no actionable findings remain.

## Explicit Non-Goals

- Do not implement or ship `QWebEngineView`.
- Do not vendor MathJax assets.
- Do not remove existing PyInstaller/WebEngine excludes.
- Do not change calculation syntax to accept LaTeX.
- Do not add GUI backend selectors.
- Do not stage, commit, package, or publish.
