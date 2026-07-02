# DataLab Architecture & Developer Guide

> 项目架构 + 开发者上手指南。终端用户请看仓库根的 [README.md](../README.md)。
> Architecture + developer onboarding. End-users: see the repo-root [README.md](../README.md).

## Project Overview

DataLab is a high-precision (mpmath-based) scientific tool for **sequence extrapolation, curve fitting, and error propagation**, with LaTeX export and inline PDF preview. A single Python codebase serves two front-ends — a **PySide6 desktop GUI** and a **Flask web app** — both backed by the same shared computation modules. The UI is bilingual (中文 / English) throughout.

## Common Commands

### Run from source

```bash
# Desktop GUI (thin shim → app_desktop/main.py)
python data_extrapolation_gui.py

# Web app (default http://127.0.0.1:8000)
python app_web/server.py
```

Web env vars: `DATALAB_WEB_SECRET` (required in production), `DATALAB_HOST`, `DATALAB_PORT`, `DATALAB_DEBUG`.

### Install dependencies (separate sets — pick by frontend)

```bash
pip install -r gui_requirements.txt       # Desktop (PySide6 + scientific stack)
pip install -r web_requirements.txt       # Web (Flask + scientific stack)
pip install -r requirements-test.txt      # Tests (pytest-qt, pytest-cov)
pip install -r requirements-docs.txt      # MkDocs Material docs
```

### Tests

```bash
pytest                                                                       # all
pytest tests/test_web_api_smoke.py                                           # one file
pytest tests/test_web_api_smoke.py::test_api_ui_specs_smoke                  # one test
QT_QPA_PLATFORM=offscreen pytest                                             # headless GUI / CI
pytest --cov=. --cov-report=term-missing                                     # with coverage
```

Test config bootstrap is in `tests/conftest.py` (puts the project root on `sys.path`).

Desktop-GUI tests use `pytest-qt`; set `QT_QPA_PLATFORM=offscreen` on machines without a display server (CI, SSH, containers) or the Qt tests will fail to create a `QApplication`.

### Build native bundles (PyInstaller, fully self-contained)

```bash
./build_mac_data_gui.sh                   # macOS → dist/DataExtrapolationGUI.app
./build_windows_data_gui.ps1              # Windows (preferred)
./build_windows_data_gui.bat              # Windows (legacy)
```

Spec file: `DataLab.spec`. It is **hand-tuned** to exclude large Qt sub-modules (3D, multimedia, web, etc.) — do not regenerate from scratch.

### Documentation (MkDocs Material)

```bash
mkdocs serve                              # live preview
mkdocs build                              # static site → site/
```

Config: `mkdocs.yml`; sources under `docs/web/`.

### LaTeX requirement (runtime)

A TeX distribution providing `pdflatex` or `xelatex` is required for PDF export. The desktop GUI auto-detects common locations or lets the user browse to a custom executable.

## Architecture

### Two frontends, one core

- **`app_desktop/`** — PySide6 GUI. Entry: `app_desktop/main.py`. The main window class `ExtrapolationWindow` (`app_desktop/window.py`) is composed of **domain mixins**: `window_data_mixin.py`, `window_extrapolation_mixin.py`, `window_fitting_mixin.py`, `window_statistics_mixin.py`, `window_latex_pdf_mixin.py`, `window_images_mixin.py`, `window_i18n_mixin.py`. Long-running work dispatches to background workers in `workers_core.py` (`CalcJob`, `FitJob`). The former one-click model-selection workflow was removed; desktop fitting uses explicit `FitJob` / `FitWorker` paths only.
- **`app_web/`** — Flask app using the application-factory pattern (`app_web/server.py`). Routes are split into Blueprints under `app_web/blueprints/` (`pages.py`, `api.py`, `docs.py`). Web-specific computation glue lives in `app_web/logic/` and **mirrors** desktop functionality but reuses the same shared modules below.
- **Shared scientific modules** (used by both frontends): `extrapolation_methods/`, `fitting/`, `datalab_latex/`, `shared/`, `statistics_utils.py`, `formula_help.py`.

### Computation modules

- **`extrapolation_methods/`** — Sequence accelerators in `accelerators.py` (Richardson, Wynn-ε / Shanks) and `power_law.py` (three-point power-law fit). Methods are dispatched by string key; each takes a `<Method>Config` dataclass and returns a `<Method>Result` dataclass. Per-method size validation lives at the dispatch boundary (Richardson ≥4 points; Wynn-ε / Shanks ≥3).
- **`fitting/`** — High-precision Levenberg–Marquardt engine in `hp_fitter.py`. `auto_models.py` registers predefined linear-basis models (polynomial, Padé, inverse series); `model_selector.py` ranks them via AIC/BIC. Custom user expressions are parsed in `model_parser.py`, which **reuses `safe_eval` from `data_extrapolation_latex_latest`** — do **not** introduce a parallel parser. `constraints.py` uses SymPy for parameter constraints. `FitResult` separates `param_errors_stat` (statistical) and `param_errors_sys` (systematic) — keep this distinction in any new code paths.
- **`datalab_latex/`** — LaTeX table generation. `latex_tables.py` is the public facade; `latex_formatting.py` handles number-with-uncertainty formatting (dcolumn / siunitx); `expression_engine.py` is the **safe formula evaluator** (Mathematica-style `Sin[x]`, whitelist of ~30 functions, AST node/depth caps); `derivatives.py` computes numerical partial derivatives for error propagation.
- **`shared/`** — `ui_specs.py` (parameter-widget specs consumed by **both** desktop and web — single source of truth for method parameters), `precision.py` (`precision_guard()` context manager wrapping `mp.dps` changes, clamped to [10, 1 000 000]), `pdf_preview*.py` (pdftoppm with Ghostscript fallback for inline PDF preview), `help_specs.json` (single source for "?" help popovers in both UIs).

> **Layering guard (P2-5).** `datalab_latex/` is presentation and must not import
> upward into `datalab_core/`. `tests/test_layering_latex_no_core_imports.py`
> enforces this via a static AST scan. One documented exception remains:
> `datalab_latex/latex_tables_common.py` still imports five statistics *display*
> helpers (`statistics_output_value_unit`, `statistics_row_flag_detail`, …) from
> `datalab_core.statistics`. These are UI-neutral and also called inside
> `datalab_core`, so the fix is to relocate them to `shared/statistics_display.py`
> (tracked as P2-5 Stage B — a larger core-schema move); the guard lists this file
> as a known exception until then. `statistics_utils.py` at the repo root is a
> *frontend-glue bridge* (a LaTeX generator that consumes both core results and
> `datalab_latex` renderers), not compute — its name predates the layering split.

### `datalab_core/` service layer

> This section postdates the original guide: the `datalab_core/` package is the
> UI-neutral service/model boundary between the computation modules above and the
> two frontends. See the root `CLAUDE.md` ("Architecture" §2) for the layering
> rules — this is a concise map, not a duplicate.

- **`service_factory.create_core_session_service(...)`** builds a
  `session.SessionService` pre-populated with the migrated core handlers (one per
  `JobMode`).
- **`jobs.JobMode`** enumerates the five job kinds — `EXTRAPOLATION`,
  `UNCERTAINTY`, `STATISTICS`, `FITTING`, `ROOT_SOLVING`. Callers submit a
  `ComputeJobRequest` (with a `mode`) via `SessionService.submit(request)`, which
  dispatches to the handler registered for that mode and returns a
  `ResultEnvelope`.
- **Handlers** are the `run_*` functions (`run_extrapolation`, `run_uncertainty`,
  `run_statistics`, `run_fitting`, `run_root_solving`) wired in
  `service_factory._CORE_HANDLER_REGISTRY`; each lives in its same-named module
  (`datalab_core/extrapolation.py`, `fitting.py`, …) and depends only on the
  computation modules, never on a frontend.
- **Workspaces & recipes** — `workspace_v2.py` (schema `datalab.workspace.v2`,
  persisted to `.datalab` files) and `recipes.py` (schema `datalab.recipe.v1`)
  are the serialization/replay layer. History/compare, report bundles, the
  uncertainty budget, and the extended statistics modules
  (`statistics_{bootstrap,grouped,hypothesis,matrix,time_series}.py`) also live
  here.
- Both frontends call into this layer rather than the computation modules
  directly. Cooperative cancellation flows through
  `session.external_cancellation_scope` / `check_cancelled`.

### Cross-cutting conventions (follow these)

- **Bilingual messages**: user-facing errors and labels use `_dual_msg(zh, en)` returning `"汉语 / English"`. The locale layer splits on `" / "` to extract the active language. Don't return single-language strings from new code paths.
- **Precision discipline**: every numerical computation wraps work in `with precision_guard(dps): ...`. Don't mutate `mp.dps` directly — direct mutations leak across threads/jobs. Defaults: power-law=50, accelerators=80, fitting=formula-dependent. `mp.dps` is **process-global** in mpmath; existing workers (`CalcJob`, `FitJob`) already enter `precision_guard` at their entry point. Any new worker or new code path that calls mpmath directly must wrap the same way, or concurrent jobs will corrupt each other's precision.
- **Single expression engine**: extrapolation custom formulas, error-propagation formulas, and fitting model expressions all flow through `data_extrapolation_latex_latest` / `datalab_latex/expression_engine.py`. Add new functions to its whitelist; don't write a second parser.
- **Config/Result DTO pattern**: each method has a `<Method>Config` and `<Method>Result` dataclass. Mirror this when adding new methods.

### Documentation system (two-track)

- **`docs/web/`** — MkDocs Material site (Markdown). Also served live at `/docs` from the Flask app via `app_web/blueprints/docs.py`.
- **`docs/desktop/`** — Markdown bundled into PyInstaller artifacts; loaded at runtime through `desktop_doc_loader.py` (with path-traversal protection). Bilingual via filename pattern `<slug>.<lang>.md`.

### Legacy entry points

- `data_extrapolation_latex_latest.py` is a backwards-compatible shim that re-exports from the `datalab_latex/` package. Edit the package, not the shim.
- `data_extrapolation_gui.py` at the repo root is a thin shim that delegates to `app_desktop/main.py`.

## Project-Specific Gotchas

- **Two requirements files for two frontends.** Installing only `web_requirements.txt` will not give you PySide6, and vice-versa. Pick the one that matches what you're working on.
- **Windows ≠ Gunicorn.** The web deploy doc (`docs/web/deploy.md`) mandates Waitress on Windows (Gunicorn imports `fcntl`). Production WSGI is Waitress.
- **Internal review history removed.** Past internal-review markdowns (`CODE_REVIEW_R*.md`, `FITTING_REVIEW_UPDATED.md`, `Document.md`, etc.) were dropped when the public release was prepared — they were process notes, not design specs. For the current architecture see this file plus the per-tab guides under `docs/desktop/` and `docs/web/`. Past commit messages (especially the merge commits for PRs #28–#39) carry the recent design decisions.
- **Keep desktop and web in sync.** `shared/ui_specs.py` and `shared/help_specs.json` are the **single source of truth** for parameter widgets and help popovers — editing them updates both frontends. Editing a mixin in `app_desktop/` or a blueprint in `app_web/` without touching the shared specs when a user-visible parameter changes will cause drift between the two UIs.
- **Adding a math function requires whitelisting it.** `datalab_latex/expression_engine.py` rejects unknown identifiers by AST inspection. If fitting, extrapolation custom formulas, or error propagation needs a new function (e.g. `erf`, `besselj`), add it to the whitelist in `expression_engine.py` — not to a local import list — so all three code paths see it.
