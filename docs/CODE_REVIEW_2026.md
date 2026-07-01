# DataLab — Whole-Codebase Architecture Review (2026)

**Method:** Three-model swarm review. A 12-dimension Claude workflow (12 auditors + adversarial verification) produced the base findings; **Codex (gpt-5.5)** and **Antigravity/Gemini (Gemini 3.1 Pro)** independently cross-checked the draft against the actual code and added missed findings. Disagreements between models were resolved by direct verification (noted inline).
**Target:** `DataLab-claude-dev`, branch `codex/claude-handoff-20260629`.
**Scope:** Whole codebase (~95k LOC) — high-precision (mpmath) scientific toolkit; one Python core serving a PySide6 desktop GUI and a Flask web app; bilingual (中文/English). Refactor difficulty was explicitly **not** a constraint.

**Confidence legend:** ⭐⭐⭐ = independently found/confirmed by all three models (or verified by direct run); ⭐⭐ = two models; ⭐ = one model. Every finding cites a real `file:line`.

---

## 1. Executive Summary

### Overall health

DataLab is a **mature, well-disciplined codebase that is "modern by configuration but legacy by enforcement."** The architectural intent is genuinely good: a clean layered design (compute → `datalab_core` service boundary → two frontends + `shared/` + `datalab_latex/`), a single `precision_guard()` chokepoint for the process-global `mp.dps`, a tight AST-allowlist expression evaluator, exhaustive archive/recipe input bounding, full CSRF + security-header coverage on the web layer, Ed25519-signed update manifests, and a thoughtful spacing-token theme system. Type-hint coverage in the compute/core layers is excellent.

The problems cluster into **four systemic themes** rather than scattered defects:

1. **No enforcement layer.** The only CI workflow (`.github/workflows/update-manifest.yml`) signs release manifests on manual dispatch — **nothing runs pytest, ruff, or mypy on push/PR**. The documented "strict mypy on core" gate is already **red: 12 errors** (verified by direct run — see §Verification note). Every other drift risk is downstream of this.
2. **Duplicated security-critical code.** Two near-identical safe-eval expression engines (`shared/` and `datalab_latex/`) violate the project's own "one expression engine" rule, with no test linking them. A *third*, weaker sympy renderer (`formula_render_service`) is unsafe-by-construction (RCE demonstrated in isolation).
3. **Frontend asymmetry around the core boundary.** Web submits through `SessionService`; the desktop mostly does too, but MCMC refinement compute lives entirely in `app_desktop/workers_core.py`, so the web app structurally cannot offer it.
4. **Correctness/scalability drift on the web path.** Web fitting parses high-precision input *outside* the precision guard (silent ~15-sig-fig truncation), and the web serializes **all** mpmath compute behind one process-global lock held for the entire request (single-concurrency).

### Top risks (tri-model consensus)

| # | Risk | Sev | Confidence | Anchor |
|---|------|-----|-----------|--------|
| 1 | **Web fitting truncates high-precision input** to ~15 sig figs (parse outside precision guard) | high | ⭐⭐⭐ | `app_web/logic/fitting.py:767` |
| 2 | **No CI gate** — tests/ruff/mypy run on no automated event; strict-mypy already fails **12 errors** (verified) | high | ⭐⭐⭐ | `.github/workflows/update-manifest.yml:1`; `pyproject.toml:175` |
| 3 | **Unsafe sympy `parse_expr`** in formula renderer — demonstrated RCE; only incidentally unreachable today | high (latent-critical RCE) | ⭐⭐⭐ | `datalab_latex/formula_render_service.py:546` |
| 4 | **Two cloned safe-eval whitelists** with no enforced link — security boundary can silently diverge | high | ⭐⭐⭐ | `datalab_latex/expression_engine.py:36` vs `shared/expression_engine.py:34` |
| 5 | **MCMC compute embedded in desktop frontend** — feature-parity gap, web/CLI cannot use it | high | ⭐⭐⭐ | `app_desktop/workers_core.py:124` |
| 6 | **Web concurrency is strictly 1** — `@mpmath_synchronized` holds a global lock for the whole request (incl. long MCMC fits), freezing all other web users | high | ⭐ (Gemini) | `app_web/security.py:192`; `app_web/logic/fitting.py:734` |
| 7 | **Formula AST re-parsed in the hottest loops** (fitting gradients, MC sampling) | high/med | ⭐⭐⭐ | `fitting/model_parser.py:188`; `shared/error_propagation_engine.py:570` |

### Top opportunities

1. **Wire the already-configured tools into CI** (offscreen pytest + ruff + mypy on 3.11/3.12/3.13) — low effort, defends everything else. `pyproject.toml:151,166,227`
2. **Compile/cache the formula AST once** — the symbolic-partial cache already exists (`shared/derivatives.py:272`), just unwired for fitting.
3. **Collapse to one canonical expression engine** — make `datalab_latex` a shim; route `formula_render_service` through `shared.symbolic_math` (kills the clone + the RCE together).
4. **Move mpmath compute to a process pool** — removes the web single-concurrency lock *and* enables the parallel seed-variant fitting win.
5. **Fix the macOS/Linux theme lock** + Auto/Light/Dark menu — the dark stylesheet is dead on the primary build target.

**GPU note (full treatment §4):** honest answer — **mpmath arbitrary-precision math cannot run on a GPU**; the highest-value wins are algorithmic (AST caching, CPU process-parallelism), not hardware acceleration. All three models concur.

### Verification note — a resolved model disagreement

The swarm claimed "strict mypy fails with 12 errors"; Codex **refuted** this (citing `tests/test_mypy_strict_clean_modules.py`, which asserts a *curated subset* is clean). **I settled it by direct run:** `mypy shared fitting extrapolation_methods datalab_latex` today reports **exactly 12 errors in 8 files** (redundant casts in `datalab_core/history.py:403`/`workbench_model.py:106`; a `Literal` arg-type in `statistics_grouped.py:964`; and three `attr-defined` against the dynamic `data_extrapolation_latex_latest` shim in `datalab_latex/latex_tables_*`). The strict `[[tool.mypy.overrides]]` perimeter transitively pulls `datalab_core` + the legacy shim beyond the test's curated list. **Swarm confirmed, Codex refute incorrect.**

---

## 2. Per-Dimension Sections

> Sections 2.1–2.6, 2.11, 2.12 are the swarm's verified findings (confidence marks show where Codex/Gemini independently confirmed). Sections 2.7–2.10 returned schema-placeholder stubs in the swarm pass and are **filled here from the Codex + Gemini cross-checks**, which covered those areas substantively.

### 2.1 GUI Design

**Summary.** The theme system is genuinely modern: unified spacing tokens (`SPACE_XS..LG`), property-driven QSS cards, a documented GroupBox title-overlap fix, status badges, full dark/light palettes; the web mirrors it with CSS custom properties, responsive grids, KaTeX previews, an interactive spreadsheet, and a complete bilingual dictionary. Two systemic gaps undercut the polish: **accessibility** (zero keyboard shortcuts; no visible focus indicator on common controls) and **theming correctness** (OS dark-mode detection is Windows-only, so the dark stylesheet is dead on macOS/Linux).

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| medium *(swarm high → Codex/Gemini medium)* | ⭐⭐ | Desktop dark-mode ignored on macOS/Linux (Windows-only detection) | `app_desktop/resources.py:133` (gate `main.py:137`) | Detect via `QStyleHints.colorScheme()`/`Qt::ColorScheme`; add Auto/Light/Dark menu | M |
| medium *(was high)* | ⭐⭐ | Full menu bar, **zero** keyboard shortcuts | `app_desktop/panels.py:207` | Assign `QKeySequence.StandardKey.*`; `QShortcut(Ctrl+Return)` on Run | S |
| medium *(was high)* | ⭐⭐ | No visible focus indicator on common controls | `app_web/static/style.css:296`; desktop `theme.py:329` | Add `:focus-visible` rules (web) + `QPushButton:focus` border (desktop) | S |
| medium | ⭐⭐ | Link/accent color fails contrast on web light theme (#45d3ff on white ≈1.4:1) | `app_web/static/style.css:78` | Add darker `--accent-text`; reserve bright accent for fills | S |
| medium | ⭐⭐ | Web POST form gives no submit feedback | `app_web/templates/index.html:196` | Disable button + localized "Running…" + `aria-busy` | M |
| medium | ⭐⭐ | Web forms `novalidate`, no client validation | `app_web/templates/index.html:17` | Drop `novalidate`/add HTML5 constraints or submit-time validator | M |
| low | ⭐ | Instant section collapse; no `prefers-reduced-motion` | `app_desktop/section_panel.py:80` | `QPropertyAnimation` on height; reduced-motion media block | S |
| low | ⭐ | Collapse state signalled by glyph/color only | `app_desktop/section_panel.py:84` | Reflect state in `accessibleName`; mirror `aria-expanded` | S |

**Assessment.** The visual craftsmanship is high, but the codebase confuses *having a dark theme* with *shipping a dark theme* — on non-Windows, `_apply_system_theme` is gated behind `os.name == "nt"`, so Qt's default light palette wins and the dark branch is effectively dead. Codex/Gemini both downgraded the "hard-locked" framing (it's "OS dark-mode ignored," not a total lock) but confirmed the substance. All fixes are S/M and self-contained.

### 2.2 GUI / Compute Separation

**Summary.** Coarse layering holds: `datalab_core` has zero Qt imports, no compute/core module imports a frontend. But two real violation classes exist: **inverted dependencies** in the statistics/LaTeX subsystem, and **MCMC compute embedded in the desktop frontend**. A headline finding (desktop bypasses `SessionService` for fitting) was **refuted on verification** — the live path routes through `build_fitting_request` → `create_core_session_service().submit()`; the direct-call code is dead/legacy (Gemini confirms it is dead code).

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | MCMC refinement compute lives in the desktop worker, not core | `app_desktop/workers_core.py:124` | Move refine step into `run_fitting` (gated); keep only corner-plot/progress in frontend | L |
| medium | ⭐⭐ | `statistics_utils.py` (layer-1) imports UP from `datalab_core` (L2) + `datalab_latex` (L5) | `statistics_utils.py:18` | Relocate LaTeX emitters; reference validators from their home | M |
| medium | ⭐⭐ | `datalab_latex` (lowest layer) imports UP from `datalab_core` | `datalab_latex/latex_tables_common.py:9` | Move shared snapshot validators down into `shared/` | M |
| medium | ⭐ (Gemini) | Web frontend directly generates LaTeX doc strings + imports internal formatters | `app_web/logic/fitting.py:372` | Move LaTeX rendering into `datalab_latex/`; expose a clean bundle API | M |
| low *(was high; refuted)* | ⭐⭐ | Dead synchronous fit methods still call compute directly | `app_desktop/window_fitting_models_mixin.py:238` | Delete unused `_execute_*` + now-unused imports after updating the one test | M |

**Assessment.** The verification pass was valuable: the "desktop bypasses SessionService" claim is **false** (live path already refactored onto the core service); what remains is low-severity dead-code cleanup. The genuine parity gap is MCMC — `_attach_mcmc_refinement_to_fit` composes the likelihood in the GUI layer; no MCMC exists in `app_web/`. Gemini adds the web LaTeX-generation leak as a second (smaller) separation seam.

### 2.3 Backend Performance

**Summary.** The hot paths are dominated by one structural problem: `safe_eval` **re-parses the formula string into an AST on every evaluation**, and the two most expensive numerical paths call it in their innermost loops with no compiled-AST reuse. The symbolic-partial cache (`shared/derivatives.py:272`) exists but fitting gradients ignore it. None of this is on the GUI thread.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | Custom-model fit re-parses formula AST on every gradient eval | `fitting/model_parser.py:188` | Compile model/derivative once; wire fitting to the symbolic-partial cache | M |
| medium *(was high)* | ⭐⭐⭐ | MC error propagation re-parses AST once per sample (default 5000×) | `shared/error_propagation_engine.py:570` | Compile once before the sampling loop; evaluate values-only inside | M |
| high | ⭐ (Gemini) | **Web concurrency is strictly 1**: `@mpmath_synchronized` holds a global lock for the entire request (incl. long MCMC fits) | `app_web/security.py:192`; `app_web/logic/fitting.py:734` | Dispatch mpmath jobs to a separate process pool with isolated `mp` state | L |
| medium | ⭐⭐ | mpmath fitting fully serial despite embarrassingly-parallel variants | `fitting/hp_fitter.py:612` | Dispatch variants/models through `ParallelMapExecutor` `CPU_MPMATH`/PROCESS | L |
| medium | ⭐⭐ | Covariance JᵀJ built in pure-Python triple loop `O(N·k²)` | `fitting/hp_fitter.py:237` | Build Jacobian as `mp.matrix`; compute `J.T * J` | S |
| low | ⭐⭐ | Redundant `mp.mpf()` re-wrapping of already-mpf values in inner loops | `fitting/model_parser.py:69` | `isinstance` fast-path; convert once at entry | S |
| low | ⭐ | Default fitting precision dps=80 vs 50 elsewhere | `datalab_core/fitting.py:25` | Align to ~50 unless requested, or document why 80 | S |

**Assessment.** Highest-ROI structural dimension. The gradient path drives `mp.findroot` with no analytic Jacobian, so mpmath computes a numerical Jacobian — multiplying the re-parse cost. The caching machinery already exists and is proven on the error-propagation path; fitting was never wired to it. Gemini's **web global-lock** finding is the scalability counterpart: the same process-pool move that parallelizes fitting also removes the single-concurrency web bottleneck. GPU is *not* the answer here (§4).

### 2.4 Code Quality

**Summary.** More disciplined than the scale suggests: excellent type hints in compute/core, **zero bare `except:`**, broad-except mostly acknowledged with `# noqa: BLE001`. Structural weaknesses: (1) quality gates configured but **not in CI**; (2) two hand-cloned security-critical expression engines; (3) extreme-complexity hotspots; (4) 31 files over the 800-line cap, 8 over 2000.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | Two safe-eval whitelists hand-cloned, risk silent divergence | `datalab_latex/expression_engine.py:36` vs `shared/expression_engine.py:34` | Collapse to one engine; make `datalab_latex` a shim; add identity test | M |
| high | ⭐⭐⭐ | mypy-strict/ruff/blind-except gates configured but not enforced | `pyproject.toml:166` | CI: offscreen pytest + ruff + mypy; promote BLE001/N802/ANN into ruff `select` | M |
| medium | ⭐⭐ | `_execute_calc_job` is 668 lines, ~178 cyclomatic | `app_desktop/workers_core.py:801` | Extract per-JobMode handlers mirroring core `run_*` | L |
| medium | ⭐⭐ | 31 files over 800-line cap; 8 over 2000 | `app_desktop/window.py:1` (3167) | Split window.py + >2000 core modules; CI line-cap warning | XL |
| medium | ⭐⭐ | `_on_stats_mode_change` 148-line, ~118-cyclomatic | `app_desktop/window.py:1306` | Declarative workflow→visible-widget table | M |
| low | ⭐ (Gemini) | Silent latin-1 mojibake fallback in file reader | `app_desktop/workers_core.py:478` | Remove `latin-1` fallback; catch `UnicodeDecodeError`, prompt for UTF-8 | S |
| low | ⭐ | `app_web` least-typed layer, outside strict mypy | `app_web/logic/fitting.py:1` | Backfill annotations; add app_web to gradual mypy | M |

**Assessment.** The marker counts (136 `BLE001`, 174 `type: ignore`, strict config) *strengthen* the central finding: tooling exists and is respected locally — only the *gate* is missing. The whitelist-clone is the most architecturally dangerous (security boundary). Gemini adds the silent-encoding fallback as a "fail-loud" violation.

### 2.5 Maintainability

**Summary.** Dominated by the `ExtrapolationWindow` god-object.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐ | `ExtrapolationWindow` god-object | `app_desktop/window.py:465` | 3167 LOC / 151 methods / 7 mixins, ~479 `self.*` attrs; finish `views/` migration with a typed window-facade `Protocol` | XL |

**Assessment.** Confirmed; the only correction was the attribute count (479, not 592). The partial `views/` migration makes "finish it with a typed facade Protocol" concrete rather than a rewrite. Sequence after dead-code + dispatcher extraction shrink the surface.

### 2.6 Modernization

**Summary.** Tooling config is modern (PEP 621, `importlib.metadata` version single-source, tomllib) but the **enforcement layer is aspirational** — same root cause as Code Quality: no CI. Secondary debt: dependencies declared in four overlapping drifted places; lower-bound-only specs.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | No CI runs tests/ruff/mypy | `.github/workflows/update-manifest.yml:1` | Push/PR workflow: offscreen pytest + ruff + mypy on 3.11/3.12/3.13; pin action SHAs | M |
| high | ⭐⭐ (verified by run) | Documented strict-mypy gate fails with **12 errors** today | `pyproject.toml:175` | Fix 12 errors / justified ignores; drop unused overrides; re-point `datalab_latex` off the shim | M |
| medium | ⭐⭐⭐ | Deps in four overlapping sources, already drifted | `pyproject.toml:59` | Make extras the single source; requirements files → `-e .[...]` shims | M |
| medium | ⭐⭐ | Lower-bound-only deps *(Codex/Gemini note: `uv.lock` exists but is gitignored — commit it)* | `pyproject.toml:38` | Commit lockfile; add tested upper bounds for volatile scientific stack | M |
| low | ⭐ | PyInstaller exclude list (53 modules) hand-duplicated across 3 files | `DataLab.spec:115` | Single shared source consumed by spec + shell + PS1 | S |

**Assessment.** Converges with Code Quality on the same P0: **CI**. Direct-run confirmed the 12 mypy errors. Dependency drift is a real reproducibility hazard for a numerical tool. Codex/Gemini refined the lockfile point (it exists but is gitignored — so "commit it" not "create it").

### 2.7 LaTeX Output *(filled from Codex/Gemini — swarm returned a stub)*

**Summary.** LaTeX generation is broad and mostly correct, but escaping is **inconsistent across table families**, which is both a correctness and an injection concern.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| medium | ⭐ (Codex) | Inconsistent LaTeX escaping — extrapolation inserts raw captions/headers while other paths escape | `datalab_latex/latex_tables_extrapolation.py:306`,`:409`; cf. `statistics_utils.py:34`,`:242` | Route all caption/header text through one `latex_escape` helper | M |
| medium | ⭐ (Codex) | Error-prop header handling only strips `$`, not full escaping | `datalab_latex/latex_tables_error_propagation.py:176` | Use the same escaping helper as other tables | S |
| medium | ⭐ (Gemini) | Incomplete regex LaTeX sanitization (`_UNSAFE_LATEX_RE` misses `\let`, `\@@input`, LuaTeX/XeTeX primitives) | `datalab_latex/formula_render_service.py:73` | Rely on `-no-shell-escape` + filesystem isolation, not a brittle regex blocklist | M |
| medium | ⭐⭐ | Tectonic binary downloaded+executed with no checksum/signature verification | `shared/latex_engine.py:335` | Pin per-platform sha256; verify before `os.replace`+exec | S |

**Assessment.** The escaping inconsistency can corrupt output (a `_` or `&` in a user caption breaks the table) and, combined with the regex-blocklist weakness, is defense-in-depth relevant. A dedicated LaTeX rendering-fidelity audit (siunitx/dcolumn number-with-uncertainty rounding) remains a recommended follow-up.

### 2.8 Formula Rendering *(filled from Codex/Gemini — swarm returned a stub)*

**Summary.** The safe expression engine is well-designed (AST allowlist), but there are **three parsers where the project mandates one**, and the weakest is unsafe by construction. See also §2.12.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high (latent-critical RCE) | ⭐⭐⭐ | sympy `parse_expr` renderer omits `__builtins__:{}` and AST pre-check — RCE demonstrated | `datalab_latex/formula_render_service.py:546` | Add `_validate_symbolic_ast` + `"__builtins__": {}`; route through `shared.symbolic_math` | S |
| high | ⭐⭐⭐ | Two cloned safe-eval whitelists (see §2.4) — divergence = a function callable/safe in one path, not the other | `shared/expression_engine.py:34` vs `datalab_latex/expression_engine.py:36` | One canonical engine; the other a shim; identity test | M |

**Assessment.** The engine allowlist itself is solid; the risk is the *duplication* and the *third weaker path*. Consolidating to one hardened `shared.symbolic_math` entry point resolves both. A KaTeX/LaTeX rendering-fidelity audit (unary minus, implicit multiplication, `convert_xor` edge cases) is a recommended follow-up.

### 2.9 GPU Acceleration *(see §4 for full treatment)*

**Summary.** All three models concur: **the mpmath arbitrary-precision core cannot be GPU-accelerated** without abandoning the defining feature. Only fp64/approximate side-paths (a separate "fast mode", MC sampling at fp64, plot rasterization) are even candidates, and none touch the high-precision value proposition. The real wins are algorithmic (AST caching) and CPU process-parallelism. **No GPU work recommended for the core.**

### 2.10 Feature Support *(filled from Codex/Gemini — swarm returned a stub)*

**Summary.** Method coverage is broad (extrapolation, fitting incl. MCMC, five statistics families, root solving, uncertainty). The concrete gaps are **frontend parity**, not missing math.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | MCMC refinement is desktop-only (see §2.2) | `app_desktop/workers_core.py:124` | Move into core `run_fitting` | L |
| medium | ⭐ (Codex) | Web has no root-solving UI despite core + desktop support | `app_web/blueprints/pages.py:98`; `base.html:29`; cf. `app_desktop/views/root_solving.py:27` | Add a web root-solving route/view routed through the existing core `run_root_solving` | M |

**Assessment.** The core exposes all five `JobMode`s, but the web frontend surfaces only four families and no MCMC — so the web is a strict subset of the desktop. A capability matrix (desktop vs web vs CLI) would make these gaps explicit and is a recommended artifact.

### 2.11 Bugs / Concurrency

**Summary.** Precision/concurrency discipline is generally careful — `mp.dps` assignment confined to `shared/precision.py`, web mpmath serialized, Qt workers signal-only, FitResult stat/sys/total split preserved. Found one genuine high-precision correctness bug (web fitting parse outside guard), one systematic bilingual violation, and one latent cancellation trap.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high | ⭐⭐⭐ | Web fitting parses high-precision input OUTSIDE the precision guard → silent ~15-sig-fig truncation | `app_web/logic/fitting.py:767` | Hoist one guard to wrap parse+request-build for both branches | S |
| medium | ⭐⭐ | Four extended-statistics modules raise English-only errors (250+ raises, zero `_dual_msg`) | `datalab_core/statistics_hypothesis.py:209` | Wrap user-facing raises in `_dual_msg(zh,en)`; add a no-bare-English-raise test | M |
| medium | ⭐⭐ | In-worker `check_cancelled()` is a no-op in the process-pool path (ContextVar doesn't cross the boundary) | `datalab_core/statistics_bootstrap.py:478` | Remove misleading check or propagate a `multiprocessing.Event` | M |
| medium | ⭐ (Gemini) | IP spoofing in security logs — `request.remote_addr` logs the proxy IP behind a reverse proxy | `app_web/security.py:120` | Use `werkzeug.middleware.proxy_fix.ProxyFix` to parse `X-Forwarded-For` | S |
| low | ⭐ | Plot rendering uses global pyplot state, not the OO Figure API | `fitting/plot_fitting.py:215` | Use `Figure()`+`FigureCanvasAgg`; latent thread-safety hazard | M |
| low | ⭐ | Plot renderers swallow all exceptions → empty bytes | `fitting/plot_fitting.py:255` | `_logger.exception(...)` before sentinel | S |

**Assessment.** The web-fitting truncation is the single most important **correctness** finding — verified by line inspection and empirically (~35 digits lost). One-line-block hoist to fix; directly defeats the product's core value on the affected page. The bilingual violation is systematic and hits exactly the audience the bilingual UI exists for. Gemini adds the ProxyFix log-integrity gap.

### 2.12 Security

**Summary.** Posture is unusually strong: tight AST-allowlist `safe_eval`, exhaustively bounded recipe/archive loading (zip-slip/symlink/bomb defenses), full CSRF + security headers + hard-fail secret policy + SSE rate limiting, `-no-shell-escape` LaTeX, Ed25519-signed updates. The serious issue is the weaker sympy renderer.

| Sev | Conf | Title | File:line | Recommendation | Effort |
|---|---|---|---|---|---|
| high (latent-critical RCE) | ⭐⭐⭐ | sympy `parse_expr` renderer is an unsafe sandbox (RCE demonstrated) | `datalab_latex/formula_render_service.py:546` | `_validate_symbolic_ast` + `"__builtins__": {}`; route through `shared.symbolic_math` | S |
| medium | ⭐⭐ | Tectonic binary downloaded+executed with no checksum/signature verification | `shared/latex_engine.py:335` | Pin per-platform sha256; verify before exec | S |
| medium | ⭐ (Codex) | Web CDN assets (KaTeX) lack SRI `integrity`; no Content-Security-Policy | `app_web/templates/base.html:16`; `app_web/security.py:309` | Add SRI hashes + a CSP header | S |
| low | ⭐ (Codex) | Collaboration tokens accepted in query strings (leak via logs/referrers) | `app_web/blueprints/collaborate.py:13`,`:634` | Move token to header/body; reject `?token=` | S |
| medium | ⭐ (Codex) | SSE fitting validates cells with `float(cell)` before high-precision parse | `app_web/blueprints/sse.py:220` | Validate as string / mpmath; don't gate on binary64 | S |
| low | ⭐ | `SESSION_COOKIE_SECURE` defaults False | `app_web/security.py:300` | Default True; tie insecure opt-out to `DATALAB_DEBUG` | S |

**Assessment.** The security baseline is the strongest dimension — defenses are real, layered, tested. The sympy finding is correctly **high, not critical**: the PoC executes, but both production callers compute-first via `safe_eval` (which rejects the gadget syntax), so it is **not reachable end-to-end today** — it is one refactor from being a critical RCE. The fix is small and, routed through `shared.symbolic_math`, also resolves the §2.4 clone. Codex adds SRI/CSP, the collaboration-token leak, and the SSE float-gate.

---

## 3. Cross-Cutting Themes

**T1 — "Configured but unenforced" (the enforcement vacuum).** Tools exist and are respected locally (136 `BLE001`, 174 `type: ignore`, strict-mypy config, ruff config) but **no automated event runs them**. The mypy gate is red (12 errors, verified). *Every drift finding is downstream of this.* Fixing CI is the highest-leverage action. (⭐⭐⭐)

**T2 — Duplicated security-critical code with no enforced link.** Three parsers where the project mandates one: `shared/` and `datalab_latex/` expression engines (cloned) plus the weaker `formula_render_service` sympy path. Consolidating to a single hardened `shared.symbolic_math` resolves a high code-quality *and* a high security finding together. (⭐⭐⭐)

**T3 — Frontend asymmetry around the `SessionService` boundary.** Web routes everything through `submit(request)`; desktop keeps MCMC compute and dead synchronous fit methods outside it, and the web keeps a high-precision parse step + a global lock outside the ideal. Symptom: silent feature/behavior divergence between frontends. (⭐⭐⭐)

**T4 — Re-parsing / re-wrapping in hot loops.** The performance story is almost entirely "the same constant expression is re-parsed every iteration." A compile-once-cache pattern (which already exists for symbolic partials) applied to fitting gradients + MC propagation is the dominant win. (⭐⭐⭐)

**T5 — Silent failure vs "fail loud."** Broad-except → `pass`/empty-bytes/default-step (numerical + plotting), English-only raises, web parse truncation, latin-1 mojibake fallback all "degrade silently," contradicting the stated fail-loud principle. Worth a lint rule + structured logging. (⭐⭐)

**T6 — God-files concentrate change risk.** `window.py` (3167), `workers_core.py` (2781), `statistics.py` (2768), `uncertainty.py` (2407). The mixin decomposition is leaky. This is the maintainability tax that makes every other change riskier. (⭐⭐)

---

## 4. GPU Acceleration — Honest Feasibility

**Bottom line: DataLab's core numerical work cannot be meaningfully GPU-accelerated without abandoning its defining feature.** This is a fundamental property of the math, not a tooling gap. All three review models independently reached this conclusion.

### Why the core can't be GPU'd

DataLab's value proposition *is* arbitrary-precision arithmetic via mpmath (`mp.dps` configurable to thousands of digits). GPUs are built for **fixed-width** parallel arithmetic (fp16/fp32/fp64, with fp64 itself throttled on consumer hardware). There is **no production GPU library for arbitrary-precision floating point** comparable to mpmath:

- CUDA/CuPy/PyTorch/JAX operate on fp16/fp32/fp64; none expose `dps=80` mantissas.
- Arbitrary-precision-on-GPU research (multi-limb double-double/quad-double, GMP-on-GPU) tops out ~32–64 digits at enormous complexity, no maintained Python binding, and can't reach DataLab's configurable thousand-digit regime.
- The hot path is **scalar, sequential, dependency-chained**: `mp.findroot` Newton iterations, Welford accumulation in MC, Richardson/Wynn-ε recurrences. Even on CPU the parallelism is *across independent solves*, not *within* an op.

The precision tradeoff is binary, not a dial: **to use a GPU you would have to drop to fp64**, which is exactly what the tool exists to avoid.

### What *could* plausibly be GPU'd (and why it's marginal)

| Candidate | GPU-able? | Verdict |
|---|---|---|
| A separate **fp64 "fast mode"** fit path (scipy/JAX) | Yes | A *new product feature*, not acceleration of the core; needs its own precision-tradeoff UX |
| **MC error-propagation sampling** (5000 independent samples) | Only at fp64 | Independent (embarrassingly parallel) but each needs arbitrary-precision `safe_eval`; GPU forces fp64, defeating the point. Right fix = §2.3 AST-cache + CPU process-parallelism |
| **Plot rasterization** | Technically | matplotlib-Agg is CPU; not a bottleneck; not worth it |
| **Independent seed-variant / model solves** | No (need mpmath) | Right acceleration is **CPU multiprocessing** (`ParallelMapExecutor`), already shipped, unused for fitting |

### Honest recommendation

Do **not** pursue GPU for the core. Raise the performance ceiling with (1) caching the parsed AST (likely the single biggest real-world speedup) and (2) fanning independent mpmath solves across CPU cores via the existing process-pool backend. If fp64 throughput ever becomes a genuine need, ship it as an explicit, separately-labeled "fast/approximate mode" — never a silent substitution under the high-precision paths.

---

## 5. Phased Roadmap

Effort key: S ≤ ½ day · M ≈ 1–3 days · L ≈ 1–2 weeks · XL = multi-week. Order favors *correctness/security first*, then *high-leverage quality/perf/UX*, then *modernization/features*.

### P0 — Correctness & Security (do first)

| # | Item | Dim | Effort | Depends | Why this order |
|---|------|-----|--------|---------|----------------|
| P0-1 | **Hoist web-fitting parse inside the precision guard** (both branches) | Bugs | S | — | Active silent high-precision correctness bug; trivial fix, highest correctness ROI |
| P0-2 | **Harden the sympy renderer** (`_validate_symbolic_ast` + `"__builtins__": {}`, ideally route through `shared.symbolic_math`) | Security | S | — | Unsafe-by-construction RCE; routing also begins P0-3 |
| P0-3 | **Collapse the two safe-eval engines to one** canonical `shared` engine; `datalab_latex` → shim; identity test | Quality/Security | M | P0-2 | Security boundary can silently diverge; one fix removes clone + completes renderer consolidation |
| P0-4 | **Add the CI gate** (offscreen pytest + ruff + mypy on 3.11/3.12/3.13; pinned SHAs) | Modernization | M | P0-5 | Enforcement vacuum is the root enabler of all drift |
| P0-5 | **Fix the 12 mypy-strict errors** (or justified ignores); drop unused overrides; re-point `datalab_latex` off the shim | Modernization | M | — | Gate is already red; must be green before P0-4 can enforce it |
| P0-6 | **Verify Tectonic download** against a pinned per-platform sha256 before exec | Security | S | — | Unverified binary download+exec; project already owns the hashing primitives |

### P1 — High-Leverage Quality / Perf / UX

| # | Item | Dim | Effort | Depends | Why |
|---|------|-----|--------|---------|-----|
| P1-1 | **Cache/compile the formula AST once**; wire fitting gradients to the symbolic-partial cache; hoist MC parse out of the loop | Perf | M | P0-3 | Largest real-world speedup; cache already exists |
| P1-2 | **Move web mpmath compute to a process pool** (removes the global-lock single-concurrency) | Perf | L | — | Web freezes for all users during any long fit (Gemini) |
| P1-3 | **Move MCMC refinement into `datalab_core` `run_fitting`** (gated); keep only corner-plot/progress in desktop | Separation/Feature | L | P0-4 | Concrete parity gap; restores web/CLI access |
| P1-4 | **Localize the 250+ English-only raises** in the four extended-stats modules; add a no-bare-English-raise test | Bugs | M | P0-4 | User-visible to the bilingual audience |
| P1-5 | **Fix macOS/Linux theme detection** + Auto/Light/Dark menu | GUI | M | — | Dark stylesheet dead on the primary build target |
| P1-6 | **Parallelize independent seed-variant/model solves** via `ParallelMapExecutor` | Perf | L | P1-1 | Existing process-pool backend unused for fitting |
| P1-7 | **Keyboard shortcuts + focus-visible rings** (desktop + web) | GUI | S | — | Baseline a11y; near one-liners; WCAG 2.4.7 |
| P1-8 | **Add a web root-solving route/view** through the existing core handler | Feature | M | — | Web is a strict subset of desktop (Codex) |
| P1-9 | **Delete dead synchronous fit methods** after updating the one test | Separation | M | P1-3 | Removes the refuted-finding's dead code |
| P1-10 | **Web submit feedback + light-theme contrast fix + ProxyFix for logs** | GUI/Security | S–M | — | Double-submit confusion, WCAG AA fail, log integrity |

### P2 — Modernization / Features / Structural

| # | Item | Dim | Effort | Depends | Why |
|---|------|-----|--------|---------|-----|
| P2-1 | **Commit a lockfile + tested upper bounds** for the scientific stack | Modernization | M | P0-4 | Reproducibility for a numerical tool |
| P2-2 | **Unify the four dependency sources** behind pyproject extras | Modernization | M | P2-1 | Removes drift |
| P2-3 | **Extract `_execute_calc_job` into per-JobMode handlers** mirroring core `run_*` | Quality | L | P1-3 | 668-line/~178-cyclomatic dispatch |
| P2-4 | **Split the god-files** + finish `views/` migration with a typed facade `Protocol`; 800-line CI warning | Maintainability | XL | P2-3 | Highest structural cost; do after surface shrinks |
| P2-5 | **Fix the dependency inversions** (`statistics_utils` ↔ `datalab_latex` ↔ core) + move web LaTeX generation into `datalab_latex` | Separation | M | P0-3 | The remaining real layering knot |
| P2-6 | **Consistent LaTeX escaping** (one `latex_escape` helper for all captions/headers) + drop the regex blocklist in favor of `-no-shell-escape`+isolation | LaTeX/Security | M | — | Output-corruption + defense-in-depth (Codex/Gemini) |
| P2-7 | **OO Figure API for plotting**; log instead of swallowing; declarative widget-visibility table; SRI+CSP on web | Bugs/Security | M | — | Thread-safety + silent-failure + web hardening |
| P2-8 | **Optional fp64 "fast mode" + GPU**, *only if* a real user need emerges, as an explicit separately-labeled path | Perf/Feature | XL | P1-1, P1-6 | Per §4: not core acceleration; last and conditional |

**Sequencing rationale.** P0 makes the product correct and safe and installs CI (P0-5 precedes P0-4 — you can't gate on a red check). P1 spends the protection on the highest-visibility wins, ordered so the AST cache (P1-1) lands before parallelism (P1-6) and core handlers (P1-3) exist before the desktop dispatcher is refactored to mirror them (P2-3). P2 is the structural/modernization long tail, GPU explicitly last and conditional per §4.

---

## Execution log & two deliberate non-executions (P1-2, P1-6)

**P0 — all 6 done** (`050df51`, `997cf96`, `3693169`, `f84960d`, `10ee11c`, `0b72c62`).
**P1 — P1-1/P1-3/P1-4/P1-5/P1-7/P1-8/P1-9/P1-10 done.** P1-2 and P1-6 were
deliberately **not** implemented as written. Both concerns are real but the
roadmap wording prescribes a fix that is worse than the disease; the honest
engineering call is documented here, with what a genuine ("根治") fix would take.

### P1-2 — web mpmath process pool: **not recommended as specified**

*The finding (Gemini):* `app_web/security.py` guards all mpmath compute with a
process-global `_mpmath_lock` (`mpmath_synchronized`), so within one WSGI worker
only one fit runs at a time — a long fit blocks other users *in that worker*.

*Why the prescribed fix is wrong:* the codebase **already** solves this by the
standard mechanism, and says so. `app_web/blueprints/sse.py` documents it
verbatim — *"Real deployments scale by adding worker processes, not threads"* —
and `docs/DATALAB_WEB_GUIDE.md` ships the production command `gunicorn -w 4`
(and `-w 9` under load). Each gunicorn worker is a separate OS process with its
**own** `mp.dps`; there is no cross-process lock. The per-worker lock is
*correct* — it protects the one piece of process-global state mpmath exposes.
Dropping an in-process `ProcessPoolExecutor` inside each worker would (a)
duplicate what `-w N` already provides, (b) break SSE progress streaming (you
can't stream `mp.workdps` progress out of a pool subprocess without a second IPC
channel), (c) add pickle round-trips of mpmath objects on every request, and (d)
contradict a documented, tested design. Net: more code, more failure modes, no
real concurrency gain over `-w N`.

**Root-fix applied — deployment layer (done).** Added `gunicorn.conf.py`, which
sizes workers from the CPU count (`2*cores+1`, ceiling 16) with a **hard floor of
2**, overridable via `WEB_CONCURRENCY`. Both deployment guides now recommend
`gunicorn -c gunicorn.conf.py` as the primary command and explain *why* multiple
worker processes (not threads) are the concurrency mechanism for a process-global
`mp.dps`. The systemd unit also sets `DATALAB_TRUST_PROXY_HEADERS=1` so the
per-IP rate limiter sees real client IPs behind the documented nginx proxy. The
floor-of-2 is the load-bearing invariant — it makes "one user's long fit blocks
everyone" structurally impossible out of the box — and is pinned by
`tests/test_gunicorn_config.py`.

*If single-process heavy concurrency were ever a hard requirement* (it is not, for
a tool that scales horizontally), the deeper code fix would be to drop mpmath's
process-global `mp.dps` for per-call contexts (`mpmath.workprec`, or `gmpy2`
contexts) so threads run truly concurrently — an XL change touching every
`precision_guard` site. Not pursued: the deployment fix fully addresses the
concern.

### P1-6 — parallelize seed-variant solves: **not recommended without a refactor**

*The finding:* `fitting/hp_fitter.py::_run_once` tries N deterministic seed
variants sequentially (`_generate_seed_variants`, then a fallback set) and keeps
the best by χ². These solves are independent, so "parallelize them" looks free.

*Why it isn't free:* the per-variant solve is a **closure** (`_solve_seed` /
`_try_variant`) that captures `gradient_funcs` (which wrap compiled model
evaluators), mutates `candidates`/`last_exc` via `nonlocal`, and returns
`_FitComputation` objects holding mpmath values and closures. That state is
**not picklable**, so a `ProcessPoolExecutor` can't take it without a rewrite;
and a *thread* pool buys nothing because mpmath is CPU-bound under the GIL. On
top of that, `mp.findroot` reads process-global `mp.dps`, so any process worker
must re-enter `precision_guard` — and the variant count is typically only 5–15,
so the parallel speedup ceiling is small while the correctness blast radius (the
precision-critical numerical core) is large.

**Root-fix applied — the medium refactor (done).** The former `_solve_seed`
closure is now a pure, top-level, **picklable** worker: `_solve_seed_variant_task`
takes a `_SeedSolveTask` carrying only the model *recipe* (expression + names +
constants, not the closure-bearing `ModelSpecification`) plus the parameter
state, data, and seed; it rebuilds the model and gradient system inside the
worker under `precision_guard`, then root-finds. `_run_once` maps the variants
with `ParallelMapExecutor` (`CPU_MPMATH` workload) — the executor's own
`min_process_tasks` / worker-budget gating keeps small fits serial, and the
solve→process split keeps the (cheap) statistics/covariance post-processing in
the main process. Parallelism is guarded to the safe case (`model_factory is
None`, no non-picklable dependent-parameter defs); anything else falls back to
the in-process solve, as does a failed picklability check. A determinism test
(`tests/test_hp_fitter_seed_parallel.py`) proves a process-pool run yields
bit-identical solutions to a serial run, so the best-χ² pick can never diverge
across machines. 295 fitting tests pass with the refactor; mp.dps is re-entered
inside each worker so concurrent solves cannot corrupt each other's precision.

### P2-5 — dependency inversions: **partially untangled + guarded**

The `datalab_latex → datalab_core` inversion had three edges. A workflow recon
mapped them and corrected a key point: the inverted functions are *also* called
inside `datalab_core`, so their destination is `shared/`, not `datalab_latex/`.

- **Stage A (done):** the grouped and matrix renderers re-ran
  `validate_statistics_*_payload`, which the core already runs upstream before the
  payload reaches the renderer. Dropped the redundant re-validation — **2 of 3
  edges removed** with zero behavior change.
- **Stage B (deferred, tracked):** the last edge is `latex_tables_common.py`
  importing five UI-neutral statistics *display* helpers. Relocating them to
  `shared/statistics_display.py` is a ~250-line move of core schema tables
  (`_STATISTICS_METRIC_ROWS` and its derived constants have 40+ internal callers),
  so it is a real medium refactor with re-export ripple and no functional benefit
  (the edge is directional-only — no cycle, no failing test, no mypy error). It is
  documented as a known exception and left for a focused follow-up.
- **Guard (done):** `tests/test_layering_latex_no_core_imports.py` statically
  asserts datalab_latex does not import datalab_core, with `latex_tables_common`
  the single tracked exception, so the boundary can't silently erode further.
- `statistics_utils.py` (repo root) is reclassified in `docs/ARCHITECTURE.md` as a
  frontend-glue bridge (a LaTeX generator consuming both core + latex), not
  compute — its name predates the layering split.

---

## Appendix A — External cross-check: Codex (gpt-5.5)

Codex verified all 29 swarm HIGH/MEDIUM findings (CONFIRM/PARTIAL/REFUTE) and added 6 missed findings. Full table in the review body above (confidence marks). **One Codex error was caught and corrected by direct verification:** Codex REFUTED the "12 mypy errors" claim, but a direct `mypy` run confirms exactly 12 errors — the swarm was right (see §1 Verification note).

## Appendix B — External cross-check: Antigravity/Gemini (Gemini 3.1 Pro)

Gemini confirmed the four load-bearing findings (web-parse truncation, sympy RCE, cloned whitelists, MCMC-in-frontend) and contributed **five distinct high-value findings** the swarm missed: the **web global-lock single-concurrency** (its most important addition), incomplete LaTeX regex sanitization (`\let`/`\@@input`), IP spoofing in security logs (ProxyFix), the leaky web→LaTeX dependency, and the silent latin-1 mojibake fallback. Gemini also correctly identified `_execute_custom_fit` as dead code (→ Low), agreeing with the swarm's own refutation.

---

*Every finding is anchored to a verified `file:line`. Confidence marks (⭐/⭐⭐/⭐⭐⭐) indicate single-/two-/three-model agreement. Severity recalibrations from the adversarial + cross-check passes are flagged inline. The four load-bearing claims — web-fitting truncation (§2.11), sympy RCE (§2.12), whitelist clone (§2.4/§2.8), and the CI/mypy gap (§2.6, verified by direct run) — are the highest-confidence, highest-leverage items.*
