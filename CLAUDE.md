# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

DataLab is a high-precision (mpmath) scientific toolkit — sequence extrapolation,
curve fitting, error propagation, root solving, and weighted statistics — with
LaTeX/PDF export. One Python core serves two frontends: a **PySide6 desktop GUI**
and a **Flask web app**. The UI is bilingual (中文 / English) throughout.

> `docs/ARCHITECTURE.md` is the long-form developer guide. It predates the
> `datalab_core/` service layer (see below) and lists some older `app_desktop/`
> mixin names — trust the live code over it where they disagree, but read it for
> the deeper module-by-module rationale.

## Commands

```bash
# Run from source
python data_extrapolation_gui.py          # desktop GUI (thin shim → app_desktop/main.py)
python app_web/server.py                  # web app (default http://127.0.0.1:8000)
datalab batch config.yml                  # CLI batch runner (entry: cli.main:main)

# Install (separate dep sets per frontend — installing one does NOT give the other)
pip install -r gui_requirements.txt       # desktop (PySide6 + scientific stack)
pip install -r web_requirements.txt       # web (Flask + scientific stack)
pip install -r requirements-test.txt      # tests
# or via extras: pip install -e ".[dev]"  (desktop,web,units,mcmc,collab,test,bench,typing,docs)

# Tests — Qt tests need an offscreen platform on headless machines / CI
QT_QPA_PLATFORM=offscreen pytest -q
QT_QPA_PLATFORM=offscreen pytest tests/test_web_api_smoke.py                          # one file
QT_QPA_PLATFORM=offscreen pytest tests/test_web_api_smoke.py::test_api_ui_specs_smoke # one test
pytest -m "not slow"                       # skip slow-marked tests
pytest --cov=. --cov-report=term-missing   # coverage

# Lint / type-check (config in pyproject.toml; not wired into CI)
ruff check .                               # select = E,F,W
mypy shared fitting extrapolation_methods datalab_latex   # strict only on these four

# Native bundles (PyInstaller; spec is hand-tuned — do not regenerate)
./build_mac_data_gui.sh                    # macOS → dist app
./build_windows_data_gui.ps1              # Windows (preferred; .bat is legacy)

# Docs site (MkDocs Material; sources under docs/web/)
mkdocs serve
```

Web env vars: `DATALAB_WEB_SECRET` (**required in production** — a missing secret
is a hard failure; tests/dev set `DATALAB_DEBUG=1` to get a random key instead),
`DATALAB_HOST`, `DATALAB_PORT`, `DATALAB_DEBUG`. Behind a trusted reverse proxy,
set `DATALAB_TRUST_PROXY_HEADERS=1` (wraps the app in werkzeug `ProxyFix` so the
per-IP SSE rate limiter sees the real client IP); `DATALAB_SSE_DISABLE_RATE_LIMIT`
turns that limiter off (dev only). LaTeX sandbox limits (`app_web/latex_security.py`):
`DATALAB_LATEX_TIMEOUT`, `DATALAB_LATEX_MAX_CPU`, `DATALAB_LATEX_MAX_MEM`,
`DATALAB_LATEX_MAX_FILE`, `DATALAB_LATEX_MAX_PROC` — see `docs/web/deploy.en.md`
for defaults and meanings.

## Architecture: layered, one core → two frontends

Dependencies point downward only. Never make a lower layer import an upper one.

1. **Compute packages** (pure math, no UI): `extrapolation_methods/` (Richardson,
   Wynn-ε/Shanks accelerators, power-law fit), `fitting/` (high-precision
   Levenberg–Marquardt in `hp_fitter.py`, model registry, MCMC), `root_solving/`,
   and `statistics_utils.py`. Each method follows a **`<Method>Config` →
   `<Method>Result` dataclass** pattern — mirror it when adding methods.

2. **`datalab_core/`** — the **UI-neutral service/model boundary**. It depends on
   the compute packages but **must stay free of Qt and side-effect-heavy shared
   modules**, and nothing here may import a frontend. `service_factory.py` builds a
   `session.SessionService` that dispatches the five `JobMode`s (extrapolation,
   uncertainty, statistics, fitting, root_solving) to handlers (`run_*`). Both
   frontends call into this layer rather than the compute packages directly. Also
   houses workspaces (`workspace_v2.py`, schema `datalab.workspace.v2` → `.datalab`
   files), recipes (`recipes.py`, schema `datalab.recipe.v1`), history/compare,
   report bundles, uncertainty budget, and the extended statistics modules
   (`statistics_{bootstrap,grouped,hypothesis,matrix,time_series}.py`).

3. **Frontends** (mirror each other; keep them in sync):
   - `app_desktop/` — PySide6. Entry `app_desktop/main.py`. The main window
     `ExtrapolationWindow` (`window.py`) is composed of domain **mixins**
     (`window_*_mixin.py` — data, extrapolation, fitting [split across
     models/params/residuals/formatters], statistics, latex_pdf, i18n, images).
     `bridge_qt.py` adapts `SessionService` callbacks to Qt signals; long work runs
     on background workers (`workers_core.py`, `workers_qt.py`).
   - `app_web/` — Flask application-factory (`server.py`). Routes are Blueprints
     under `app_web/blueprints/` (`pages`, `api`, `docs`, `sse`, `collaborate`);
     per-mode glue lives in `app_web/logic/` and reuses `datalab_core` /
     `service_factory`.

4. **`shared/`** — cross-cutting utilities used by both frontends and the core:
   `ui_specs.py` + `help_specs.json` (**single source of truth** for parameter
   widgets and "?" help in both UIs), `precision.py` (`precision_guard()`),
   `expression_engine.py`, `pdf_preview*.py`, parsing/normalization, parallel
   backend, settings/logging.

5. **`datalab_latex/`** — LaTeX table generation (split into `latex_tables_*.py`
   facades), number-with-uncertainty formatting (siunitx/dcolumn), the safe
   `expression_engine.py`, and derivative computation.

## Cross-cutting conventions (these break things if ignored)

- **Precision discipline.** `mp.dps` is **process-global** in mpmath. Every
  numerical path must wrap work in `with precision_guard(dps): ...` (clamped to
  [10, 1_000_000]); never mutate `mp.dps` directly. Existing workers enter the
  guard at their entry point — any new worker that calls mpmath must do the same,
  or concurrent jobs corrupt each other's precision.
- **One expression engine.** Extrapolation custom formulas, error-propagation
  formulas, and fitting model expressions all flow through the whitelisted safe
  evaluator (`shared/expression_engine.py` / `datalab_latex/expression_engine.py`;
  `fitting/model_parser.py` reuses the same `safe_eval`). To add a math function
  (`erf`, `besselj`, …) add it to that whitelist — **do not write a second parser**.
- **Bilingual messages.** User-facing strings use `_dual_msg(zh, en)` →
  `"汉语 / English"`; the locale layer splits on `" / "`. Don't return
  single-language strings from new code paths.
- **Keep desktop and web in sync.** When a user-visible parameter changes, edit
  `shared/ui_specs.py` / `shared/help_specs.json` (which drive both UIs) — not just
  one frontend — or the two UIs drift.
- **`FitResult` uncertainty split.** Keep `param_errors_stat` (statistical) and
  `param_errors_sys` (systematic) distinct in any new fitting code path.

## Legacy shims (edit the package, not the shim)

- `data_extrapolation_gui.py` → delegates to `app_desktop/main.py`.
- `data_extrapolation_latex_latest.py` → re-exports from the `datalab_latex/` package.
