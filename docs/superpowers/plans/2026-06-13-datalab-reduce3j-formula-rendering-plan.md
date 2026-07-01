# DataLab Reduce3j-Style Formula Rendering Plan

## Goal
Upgrade DataLab formula preview and LaTeX export quality toward the Reduce3j/Mathematica model while preserving the product rule already clarified in Task 249:

- Users continue entering formulas in the existing DataLab/Mathematica-like syntax, for example `Sin[x]`, `Sqrt[A]`, `x^2`, `d0 + d2/(n-delta)^2`.
- The GUI exposes one preview behavior only: a rendered LaTeX-style mathematical display.
- Calculation paths do not accept LaTeX as a user-facing input language.
- Renderer selection is automatic and hidden. Users should not see Python/Mathematica/LaTeX preview modes or backend/style selectors.
- "One preview behavior" means one source syntax, one canonical LaTeX metadata result, and no user-visible style/backend choice. Compact inline preview and enlarged dialog may have different sizes, but they must not present materially different mathematical layout for the same supported formula in a shipping build.
- LaTeX export should approach Mathematica-style `TeXForm` quality for supported DataLab expressions: structured fractions, powers, roots, functions, Greek symbols, subscripts where unambiguous, implicit equations, and report/table integration should come from the same canonical metadata used by preview.

## Reduce3j Reference
Reduce3j uses a high-quality offline rendering stack:

- `wigsym/ui/web_pane.py` wraps `QWebEngineView`, registers one `QWebChannel` object named `bridge`, disables remote URL access and clipboard JavaScript, and synchronizes page background/theme.
- `wigsym/assets/result_shell.html` loads local `shell_common.js`, local `mathjax/tex-chtml.js`, and `qrc:///qtwebchannel/qwebchannel.js`.
- The shell renders LaTeX through text nodes such as `\\[ ... \\]`, then calls `MathJax.typesetPromise(...)`; user-controlled payloads are not injected as HTML.
- The shell uses a restrictive CSP, local vendored assets, theme tokens, i18n dictionaries, and MathJax CHTML color overrides for readable light/dark output.
- The design is offline-first and packaged with vendored assets rather than runtime downloads.

This is the best visual target only after DataLab has high-quality LaTeX metadata. WebEngine/MathJax cannot create structured fractions, matrices, or cases if the DataLab-to-LaTeX converter emits flat strings. Therefore the first quality lever is converter output and PNG fallback coverage; WebEngine is a later typography/layout backend contingent on measured value.

DataLab should borrow Reduce3j's offline MathJax, local shell, CSP, text-node injection, and theme discipline. It should not automatically copy Reduce3j's QWebChannel bridge if formula preview can be driven by a smaller one-way host-to-page API.

Mathematica's relevant lesson is separate from WebEngine: a high-quality formula export layer should emit structured, reusable LaTeX independent of the rendering surface. DataLab should treat preview, copy-as-LaTeX, report generation, and result-table formula snippets as consumers of the same structured export metadata.

## Current DataLab Constraints
DataLab currently has a deliberately safer shipping posture:

- Formula metadata is centralized in `datalab_latex.formula_render_service.render_formula_metadata()` and PNG rendering in `render_formula()`.
- Desktop preview widgets call `app_desktop.formula_preview.render_formula_pixmap()` and show the result in `FormulaPreviewLabel` / `FormulaPreviewDialog`.
- Shipping builds explicitly exclude `PySide6.QtWebChannel`, `PySide6.QtWebEngineCore`, `PySide6.QtWebEngineQuick`, and `PySide6.QtWebEngineWidgets` in `DataLab.spec`, `build_mac_data_gui.sh`, and `build_windows_data_gui.ps1`.
- `tests/test_packaging_qt_excludes.py` and `tests/test_webengine_shipping_import_guard.py` enforce those exclusions and forbid shipping-source imports of WebEngine modules.
- `tools/webengine_spike_report.py` currently reports WebEngine as `NO_GO` unless security, offline assets, measurements, and packaging gates have evidence.
- In the current macOS environment, direct `PySide6.QtWebEngine*` imports can fail due to code-signing / system policy, so unconditional WebEngine imports would break local runs and CI.
- `app_desktop.webengine_spike_assets` currently references a KaTeX-oriented spike manifest; a Reduce3j-quality plan should consciously choose MathJax CHTML instead of silently mixing engines.

## Architecture Decision
Use a phased renderer architecture:

1. Move formula parsing and DataLab-syntax normalization ownership to one lightweight shared syntax/registry/AST boundary used by computation, symbolic export, preview, and LaTeX export. Keep `datalab_latex.formula_render_service` as the preview/export metadata orchestrator, sanitizer, failure-message surface, and compatibility entrypoint, not as a second parser.
2. Split rendering from metadata generation:
   - Metadata stays pure Python and Qt-light.
   - Rendering becomes an interface with multiple hidden backends.
   - The first improvement target is better metadata: DataLab division, powers, functions, implicit equations, and any future matrix/list notation should become structured LaTeX where the existing syntax supports it.
3. Add a structured LaTeX export contract before any renderer change:
   - one canonical formula metadata object should carry original source, normalized source, delimiter-free canonical LaTeX, feature flags, and any unsupported-feature diagnostics;
   - display/export/mathtext variants are derived by context helpers from canonical metadata, not independently authored parser outputs;
   - export/report generation should consume the same metadata as preview, not re-parse formulas independently;
   - copy-as-LaTeX should copy the canonical export string, not the raster/backend-specific representation.
4. Stage the renderer boundary:
   - Phase 2 keeps a narrow PNG-only desktop renderer around `FormulaPreviewMetadata`;
   - the multi-backend protocol and WebEngine surface type are introduced only if the Phase 3 value gate proves a second backend should proceed;
   - pure protocol/DTO pieces stay free of Qt imports; Qt/WebEngine implementations live under `app_desktop`, not in the core `datalab_latex` package.
5. Keep the existing matplotlib mathtext PNG backend as mandatory fallback.
6. Add a MathJax WebEngine backend only behind a capability and value gate:
   - first produce side-by-side evidence that MathJax improves cases the improved converter + mathtext fallback still renders poorly;
   - implement it in a non-shipping spike module first, or update the static import guard in the same phase that introduces the module;
   - lazy-import WebEngine modules only after the guard and capability policy explicitly allow the path;
   - never import WebEngine in ordinary shipping modules while the gate is disabled;
   - fail closed to the PNG backend if imports, assets, integrity, CSP, or platform checks fail.
7. Use one GUI control path:
   - inline formula preview and preview dialog ask a renderer manager for the best available rendered surface;
   - no preview-style combobox and no backend selector;
   - the source text area in the dialog remains a read-only copy/debug aid, not an input mode.

## Mathematica-Level LaTeX Export Requirements
- Scope:
  - applies to formula previews, copy-as-LaTeX actions, generated LaTeX reports, result summaries, fitted model equations, root-solving equations, error-propagation formulas, and implicit/self-consistent model definitions;
  - applies to formulas users enter in DataLab syntax only; LaTeX remains an output/export format, not a calculation input language.
- Output quality:
  - division should become `\frac{...}{...}` where precedence/grouping is known;
  - powers, roots, absolute values, trig/log/exp functions, Greek identifiers, and implicit equations should be consistently formatted;
  - subscript formatting should follow a documented policy, for example parameter-like `d0` may export as `d_{0}` only when that does not break DataLab's parameter identity or round-trip expectations;
  - long expressions should use readable line-break/alignment helpers in reports when appropriate, without changing inline preview semantics;
  - matrices, cases, vectors, piecewise forms, and aligned systems should be marked unsupported until DataLab input syntax intentionally supports them.
- Export integration:
  - LaTeX tables should continue using the existing table-formatting controls such as decimal alignment, numeric grouping, uncertainty digits, and `dcolumn`/equivalent package policy;
  - formula snippets embedded in tables, captions, tablenotes, and report paragraphs must use explicit formula-export embedding helpers instead of ordinary text escaping; already-exported formula LaTeX must never pass through `_escape_latex()` / `latex_escape()` style text escapers that would mangle `\frac`, `\sin`, `_`, `^`, or braces;
  - formula export helpers own delimiter/context policy: canonical formula content is delimiter-free math, and callers choose service helpers such as inline math, display math, caption-safe math, tablenote-safe math, or table-cell math instead of hand-adding `$...$`;
  - any report writer that embeds formula constructs requiring `amsmath` must include the package through its preamble helper; root-solving, fitting, error-propagation, statistics, and web LaTeX preambles must be audited before the DTO is routed into them;
  - substituted model equations that include fitted numeric values must not bypass the existing numeric formatting policy. Formula structure should come from the canonical formula exporter, while substituted parameter values should be formatted through a math-mode value formatter that shares high-precision digit policy with existing numeric utilities but is distinct from siunitx/dcolumn table-cell formatters;
  - generated `.tex` should remain compilable with the project's supported engines and package set.
- Testing:
  - add golden LaTeX tests for representative formulas and reports;
  - add compile-smoke tests for exported snippets/reports where the existing LaTeX toolchain is available;
  - add parity tests proving preview, copy-as-LaTeX, and report export use the same canonical formula metadata;
  - add regression tests for the user's target quantum-defect-style expressions and implicit equations.

## Phased Implementation Plan

### Phase 0: Remove Legacy Formula-Preview Debris
- Before adding a new renderer boundary, clean up the removed high-fidelity/preview-language remnants from Task 249 so the new architecture does not inherit ghost state:
  - delete or formally deprecate `app_desktop/formula_tex_render_worker.py` and its tests if no active production path uses it;
  - remove zombie tests that monkeypatch absent preview-worker attributes with `raising=False`;
  - remove workspace restore injection of `_workbench_formula_preview_languages` and any always-empty `_capture_formula_preview_ui` / `_restore_formula_preview_ui` helpers;
  - either delete `WorkbenchModel.with_formula_preview_language()` / `without_formula_preview_language()` or make them explicit compatibility shims with `DeprecationWarning`;
  - remove obsolete preview `language` parameters from desktop-only update helpers, or keep them as deprecated keyword-only compatibility shims that cannot change behavior;
  - if compatibility shims ignore their input, do not keep strict validation that can raise for data that is intentionally discarded;
  - correct narrow type hints around formula action layout helpers while touching the formula panel.
- Add cleanup tests proving:
  - new workspace saves omit preview-language UI state;
  - legacy workspace state is tolerated but not restored into live GUI attributes;
  - no external TeX worker is started or referenced by ordinary formula preview code;
  - core compatibility shims warn if kept.
  - structural tests replace vacuous monkeypatch tests, for example AST/namespace/import assertions proving ordinary formula preview code does not import or reference `formula_tex_render_worker`.

### Phase 1: Quality Baseline And Structured Metadata
- First reconcile the existing LaTeX conversion surfaces:
  - audit `render_formula_metadata()` / `_convert_expression()`, `format_formula_latex()` / `_format_latex_formula_sympy()`, `shared.expression_engine`, `datalab_latex.expression_engine`, `shared.expression_names`, and `fitting.symbolic_export`'s AST export path;
  - reconcile `shared.expression_engine` and `datalab_latex.expression_engine` before the exporter is implemented. Fitting computation already treats `shared.expression_engine` as the single source of truth, while symbolic export still imports normalization and allowlists from `datalab_latex.expression_engine`; the plan must not let the LaTeX exporter become canonical for the wrong or drifting engine;
  - define one lightweight syntax/registry/AST boundary that is reused by computation, reserved-name validation, symbolic export, and LaTeX export. Compatibility facades may remain, but normalization, allowlist metadata, AST caps, unsupported-node diagnostics, and parser behavior must be coverage-locked across `shared.expression_engine`, `datalab_latex.expression_engine`, `shared.expression_names`, fitting, error propagation, root solving, extrapolation, preview, and export;
  - do not add a third parser or expand regex rewriting into the new canonical export engine;
  - make the Mathematica-level exporter AST-backed, using the same DataLab normalization and operator precedence model as the computation engine so `d0 + d2/(n-delta)^2` can become `d_{0} + \frac{d_{2}}{(n-\delta)^2}` without guessing precedence from strings;
  - extract normalization / allowed-function metadata into a lightweight shared module so `datalab_latex.formula_render_service` can use the canonical AST exporter without importing `mpmath`, SymPy, PySide6, matplotlib, or heavy computation modules at import time. This is required, not optional, because the current expression-engine modules import `mpmath` and one compatibility path imports `formula_render_service`, so direct reuse would break import-purity guards and risk an import cycle. A lazy import boundary is only an interim fallback for import-time compatibility; it does not replace the lightweight registry/normalization extraction or remove private-symbol coupling. Existing import-purity tests remain release gates;
  - keep `_convert_expression()` only as a temporary compatibility facade or delete/deprecate it after callers move. It must not be the target for new Mathematica-level features such as precedence-aware fractions;
  - treat `fitting.symbolic_export` as prior art for DataLab normalization, allowlist coverage, and AST ownership only. Its existing `_render()` is not a safe template for LaTeX until it gains precedence-correct parenthesization, because it currently emits flat strings for non-atomic power bases and multiplicative operands;
  - use the SymPy-backed `format_formula_latex()` path as a deterministic oracle only for the shared Python-syntax subset where SymPy parsing is expected to succeed;
  - parity tests must assert that the SymPy path was actually used and did not silently fall back to `_format_latex_formula_manual`;
  - parity must not mean raw LaTeX string equality. Define the oracle subset and equivalence policy explicitly:
    - use targeted structural assertions for features the preview converter must gain, such as fractions and grouping;
    - tolerate documented display-convention differences such as `\left...\right`, whitespace, brace style, and subscript policy;
    - for functions whose representations differ by convention, such as `\exp(x)` versus `e^{x}` and `\ln` versus `\log`, either exclude them from SymPy string/render parity or use an explicit semantic-equivalence rule; do not let those cases make parity tests falsely red or vacuous;
  - explicitly document or reconcile `_format_latex_formula_manual` so it is not mistaken for a second canonical preview converter; it should be removed, deprecated, or fenced as legacy fallback after the AST exporter is in place;
  - if SymPy is ever proposed as canonical for all preview metadata, first add a DataLab bracket-syntax adapter and prove it does not regress `Sin[x]`, `Sqrt[A]`, or current preview tests.
- Build a small before/after visual evidence set before pursuing WebEngine:
  - representative DataLab-syntax formulas: nested division, powers, `Sqrt[...]`, trig/log/exp functions, implicit equations, long quantum-defect expressions, and any currently supported list/matrix-like notation;
  - current metadata string;
  - current PNG output;
  - expected improved LaTeX metadata where the syntax unambiguously supports it.
- Improve the DataLab-to-LaTeX converter before changing render engines:
  - render division as structured `\frac{...}{...}` when precedence and grouping are known;
  - keep powers, roots, function calls, Greek names, and constants stable;
  - add future extension points for matrices/cases only if DataLab input syntax actually supports them;
  - do not accept LaTeX syntax as calculation input.
- Build the exporter around explicit AST-node rendering rules:
  - `ast.BinOp(ast.Div)` renders as `\frac{left}{right}` with braces determined from the tree, not regex spans;
  - multiplication, unary signs, powers, and nested calls preserve computation precedence;
  - renderer rules must insert `\left(...\right)` or equivalent grouping when a child expression binds looser than its parent. Required cases include non-atomic power bases such as `(n-delta)^2`, multiplication/division over additive children such as `a*(b+c)`, right operands of non-associative subtraction/division such as `a-(b-c)` and `a/(b/c)`, unary operators over additive expressions, and nested powers such as `(a+b)^c`;
  - associativity must be explicit in tests and implementation. The exporter may use a precedence table, parent-node context, or an equivalent AST renderer, but it must not flatten child strings and rely on LaTeX readers to infer the original tree;
  - function and constant mappings are coverage-locked to the computation allowlist, as `fitting.symbolic_export` already does for SymPy/Mathematica export;
  - unsupported nodes produce diagnostics on the DTO rather than malformed LaTeX.
- Add tests proving:
  - converter output is structured for supported DataLab syntax;
  - `shared.expression_engine`, `datalab_latex.expression_engine`, `shared.expression_names`, symbolic export, and LaTeX export agree on allowlists, reserved names, normalization behavior, AST caps, unsupported-node diagnostics, and the accepted DataLab syntax subset;
  - any LaTeX emitted by the converter is rasterizable by the mandatory PNG backend;
  - unsupported advanced structures are explicitly unsupported or fallback-safe, not advertised as solved.
  - preview/export LaTeX paths have scoped parity tests over their shared syntax subset, while DataLab-bracket-only classes are tested against the preview converter contract.

### Phase 1A: Mathematica-Level LaTeX Export Contract
- Define a canonical formula export DTO that is shared by preview, copy, report, and result serialization:
  - `source_text`;
  - `normalized_datalab_text`;
  - one canonical delimiter-free formula LaTeX payload, for example `canonical_latex`;
  - optional derived render strings generated by helpers, not independently authored/stored strings, for example `display_latex`, `export_latex`, and `mathtext_latex` only when a consumer needs a restricted variant;
  - an explicit `latex_context` / helper contract for inline math, display math, caption text, tablenotes, and table cells;
  - optional substitution metadata for formulas with fitted parameter values, so symbolic structure and numeric formatting do not get collapsed into one pre-substituted source string;
  - feature/diagnostic flags for unsupported constructs.
- Route existing LaTeX report/formula export callers through this DTO instead of calling independent formatters directly. The migration matrix must explicitly cover:
  - `render_formula_metadata()` and desktop/web formula preview metadata;
  - `datalab_latex.expression_engine.format_latex_formula()` compatibility;
  - copy-as-LaTeX from `FormulaPreviewDialog` and any future copy actions;
  - `datalab_latex.latex_tables_error_propagation.generate_error_propagation_table()` formula captions/tablenotes;
  - desktop fitting reports in `app_desktop.fitting_latex_writer.build_fit_latex_block()`, including model, substituted model, implicit equation, and implicit output expression lines;
  - Web fitting LaTeX generation in `app_web.logic.fitting._generate_fitting_latex()`;
    - note that Web fitting currently emits only the model label as text and does not receive the fitted expression. Routing Web fitting through the formula DTO requires threading the actual exported expression into `_generate_fitting_latex()` before emitting a formula line. For current web fitting, the correct source is the raw `core_result.payload.get("expression")` value before it is stringified for `expression_for_csv`; do not reuse the stringified `expression_for_csv` value or the possibly blank request `model_expr` used by non-custom model modes. If the threaded expression is empty, `None`, or the legacy stringified sentinel `"None"`, the report must skip the formula line entirely rather than emitting an empty math environment or a spurious `None` formula;
  - root-solving equations/result summaries and `app_desktop.root_latex_writer`;
    - note that `root_latex_writer` currently emits numeric result tables only; exporting the root equation is new report-summary content. The root-solving equation text must be explicitly threaded from the root job/config into the export call before it is rendered through the formula DTO and inserted into the report;
  - extrapolation custom-formula reports and result summaries, including Web extrapolation's `app_web.logic.extrapolation._render_latex()` path and the shared `datalab_latex.latex_tables_extrapolation.generate_latex_table()` table writer. The custom expression is currently available in the Web request layer but is not part of the table-writer signature; the migration must explicitly thread it as optional report-summary formula metadata and skip the formula summary when no custom formula exists;
  - `app_desktop.window_fitting_formatters_mixin._build_substituted_expression()` as the producer of parameter-substituted formula display strings, plus its Markdown result-panel consumer in `_format_fit_result_text()`;
  - workspace/result serialization that stores formulas or rendered formula snippets.
    Serialization stores canonical source text, normalized source text, and typed substitution metadata only. It must not persist derived LaTeX as the source of truth; LaTeX is regenerated on load/export through the canonical exporter so old workspaces do not drift after exporter fixes.
    Legacy workspace reads must be tolerant: workspaces without typed substitution metadata or canonical formula source must load without raising. If only a historical display/pre-substituted string is available, treat it as display-only legacy text and do not claim it can be regenerated through the canonical exporter.
- Establish export-quality policies:
  - exact formatting rules for fractions, powers, roots, functions, Greek identifiers, and implicit equations;
  - explicit convention rules for `exp`/`log`/`ln` and subscript-like identifiers;
  - line-break/alignment policy for long report expressions;
  - delimiter ownership and escaping rules for every embedding context;
  - package requirements for emitted constructs, including `amsmath` where aligned/split/display helpers are emitted.
- Establish numeric-substitution policy:
  - model equations without substituted values use the canonical AST exporter directly;
  - substituted equations use the same AST/formula structure but inject formatted numeric values through a dedicated math-mode value formatter rather than `mp.nstr` or table-writer ad hoc formatting;
  - the math-mode value formatter should reuse the same precision/digit decisions as existing result-formatting utilities but emit inline-formula-safe LaTeX such as ordinary decimals or `\times 10^{...}` style scientific notation, not siunitx `S`-column / dcolumn cell syntax like `value(unc)[\text{exp}]`;
  - `_build_substituted_expression()` must stop being the LaTeX source of truth. If a human-readable substituted expression is still needed for Markdown, it should be generated from the same typed substitution metadata with display formatting appropriate to Markdown, while LaTeX export uses formula-context helpers and numeric formatters;
  - table cells continue using `format_value_for_latex_file()`, `calculate_dcolumn_format_for_column()`, `siunitx_column_spec()`, and `build_sisetup_block()`; formula exporters do not compute S/d-column specs.
- Establish escaping policy:
  - plain text still goes through the report writer's text escaper;
  - canonical formula LaTeX goes through formula-context helpers only;
  - mixed captions/tablenotes assemble text and formula fragments as typed pieces so a formula fragment is not double-escaped as text.
- Add tests proving:
  - copy-as-LaTeX, preview metadata, and generated reports agree on canonical formula content;
  - precedence and associativity regressions for `(n-delta)^2`, `a*(b+c)`, `a-(b-c)`, `a/(b/c)`, `(a+b)^c`, and the quantum-defect expression produce semantically correct grouped LaTeX;
  - the migration-matrix callers above all consume the DTO or its compatibility facade;
  - substituted fitting equations use the same structure as the symbolic model and format embedded numbers according to existing precision/uncertainty controls;
  - representative exported `.tex` compiles or passes the project's LaTeX doctor checks;
  - root/fitting/error/web report preambles include the required packages for emitted formula contexts;
  - table numeric formatting (`dcolumn`/decimal alignment/grouping/uncertainty digits) remains governed by existing table-formatting utilities, not the formula exporter;
  - unsupported advanced constructs produce explicit diagnostics instead of malformed LaTeX.

### Phase 2: Renderer Boundary Without WebEngine Shipping
- Introduce a small formula-renderer boundary:
  - keep formula metadata and renderer DTOs in the Qt-free service layer;
  - keep Qt pixmap/WebEngine implementations in `app_desktop`;
  - do not make `datalab_latex` import PySide6, matplotlib Qt glue, or WebEngine.
- Move current PNG rendering behind a narrow `MathTextPngFormulaBackend` or equivalent helper. Do not introduce a broad union-typed multi-backend surface until the Phase 3 gate proves WebEngine work should continue.
- New desktop preview paths should use the `app_desktop` PNG backend. The existing `datalab_latex.formula_render_service.render_formula()` PNG path should either become a temporary compatibility wrapper or be deprecated in favor of metadata-only service calls; do not create two divergent mathtext renderers.
- Keep `render_formula_pixmap()` and `update_formula_preview_with_empty_text()` public APIs stable by routing them through the renderer manager.
- Add tests proving:
  - DataLab syntax still converts to the expected LaTeX metadata.
  - GUI preview exposes no public syntax/backend selector.
  - empty, invalid, and unsafe formulas still produce the same safe fallbacks.
  - WebEngine modules are not imported during normal import of desktop preview modules.
  - importing `datalab_latex`, `datalab_latex.formula_render_service`, and `app_web.blueprints.api` remains free of PySide6, WebEngine, SymPy, mpmath, and other heavy GUI/runtime dependencies not already allowed by existing tests.
  - the PNG backend renders representative DataLab formulas to non-null surfaces and does not silently fall back to source text for supported converter output.
- Define the backend contract as metadata-only:
  - desktop code performs the single centralized conversion with `RenderRequest(language=InputLanguage.DATALAB)`;
  - backends consume `FormulaPreviewMetadata`, never raw source text;
  - backends must not re-parse source, honor legacy `InputLanguage.LATEX`, or infer a different formula language.
- Collapse or guard the desktop-facing preview API to DATALAB-only. If `InputLanguage.LATEX` remains in the shared service for legacy display compatibility, desktop preview code must not expose or call it and tests must lock that boundary.

### Phase 3: MathJax Asset And Security Spike
- Start this phase only if Phase 1 evidence shows a real visual gap that structured metadata plus the PNG backend cannot close. The gate is concrete:
  - proceed for structural gaps only if DataLab input syntax is separately extended to constructs mathtext cannot render, such as matrices/cases, and those constructs are required for real workflows;
  - proceed for typography/layout gaps only if saved side-by-side screenshots for representative real formulas show a clearly documented readability, scaling, clipping, or glyph-quality failure in the PNG backend that MathJax fixes;
  - do not proceed merely because MathJax is generally nicer if the improved converter plus PNG backend already meets the documented examples.
- If MathJax is proposed for shipping, require a visual-consistency decision:
  - either both inline and dialog use materially equivalent rendered layout, for example by generating a safe cached MathJax raster thumbnail for inline preview;
  - or MathJax remains a non-shipping spike / optional developer evidence tool;
  - do not ship a state where the inline preview remains visibly broken or materially different while the dialog silently shows a different high-fidelity layout for the same supported formula.
- Vendor only the minimum offline MathJax CHTML assets needed for formula preview, modeled after Reduce3j's local `mathjax/tex-chtml.js` usage.
- Do not overwrite the existing workbench-spike `REQUIRED_WEBENGINE_ASSETS`. Add a formula-preview-specific asset root, scheme/host, required-asset manifest, and evidence report section so the workbench WebEngine spike and formula-preview spike cannot corrupt each other's evidence.
- Create a formula-preview HTML shell with:
  - restrictive CSP;
  - no remote network access;
  - no file URL navigation;
  - text-node injection for LaTeX payloads;
  - MathJax `typesetPromise()` error reporting;
  - theme/i18n hooks matching DataLab's palette and language system.
- Reuse existing URL, CSP, asset-normalization, manifest, integrity, and payload-validation patterns from `app_desktop.webengine_spike_contract` and `app_desktop.webengine_spike_assets`.
- That reuse requires parameterizing scheme and host through the internal URL-validation path used by asset resolution. `asset_root` is already parameterized in several asset helpers, but `validate_navigation_url()` and the transitive validation inside `resolve_asset_url()` currently hardcode the workbench scheme/host; a formula-preview helper must thread formula scheme/host through those internals rather than wrapping only the top-level call.
- Prefer no QWebChannel for formula preview. The first WebEngine prototype should load a static formula shell and push payloads through a fixed host-owned JavaScript function such as `window.DataLabFormulaPreview.render(payload)` via `runJavaScript`.
- The host must never interpolate raw LaTeX or user text into JavaScript source. Payloads passed through `runJavaScript` must be JSON-serialized with a safe encoder, and tests must cover quotes, backticks, `</script>`, newlines, Unicode line/paragraph separators, and non-ASCII identifiers.
- If a future revision proves QWebChannel is needed, explicitly allowlist `qrc:///qtwebchannel/qwebchannel.js` in CSP, asset/navigation validation, packaged-artifact evidence, and tests. Do not smuggle the qrc resource through the ordinary formula asset manifest.
- Do not reuse the existing broad WebEngine bridge method allowlist for formula preview. Define a formula-preview-specific payload contract with no `job.*`, `workspace.*`, `updates.*`, `docs.*`, or `export.*` methods.
- Add MathJax-specific macro safety:
  - configure MathJax with a minimal allowlisted TeX package set and disabled autoload/require/trusted HTML/link/style behavior;
  - treat a denylist for commands such as `\require`, `\href`, `\url`, `\class`, `\cssId`, `\style`, `\unicode`, `\enclose`, and `\mmlToken` as defense-in-depth, not the primary control;
  - explicitly record the residual CHTML `style-src 'unsafe-inline'` requirement and why CSP remains acceptable;
  - test that malicious macros remain text-safe and do not create links, styles, remote fetches, or executable HTML.
- Add asset integrity and size evidence through the existing WebEngine evidence tooling.

### Phase 4: Lazy WebEngine Backend Prototype
- Implement `MathJaxWebEngineFormulaBackend` in a non-shipping spike module or update the static import-guard policy in the same phase. The current guard scans all `app_desktop/**/*.py`, including function-local imports, so a lazy import inside `app_desktop` still fails until the guard has an explicit spike-module exception.
- Add a capability probe:
  - checks explicit feature flag or spike decision;
  - attempts lazy imports;
  - validates asset manifest and integrity;
  - verifies platform policy allows WebEngine load;
  - returns a structured disabled reason for logs/tests.
- Use a minimal page API surface:
  - input payload: sanitized LaTeX string, UI locale, theme, and text direction;
  - no arbitrary file, shell, or network methods;
  - no calculation callbacks from JavaScript.
- The preferred no-QWebChannel path must not assume `runJavaScript` awaits MathJax promises. Qt's `runJavaScript` callback returns the last statement's plain-data value and unsupported result types include `Promise`, so the shell must expose a tested plain-data status mechanism:
  - the render entrypoint synchronously accepts a JSON payload, stores a token, starts `MathJax.typesetPromise()`, and returns plain JSON-compatible acknowledgement data only;
  - MathJax completion updates shell-owned status state keyed by token;
  - the host polls or reads `window.DataLabFormulaPreview.status(token)` through `runJavaScript`, which returns only JSON-compatible plain data;
  - synchronous validation or entrypoint failures surface in the acknowledgement; asynchronous MathJax resolve/reject results surface through the token status path;
  - status entries are evicted when a token is superseded, a dialog closes, or a terminal status has been observed;
  - a QWebChannel callback is allowed only as an explicitly approved fallback with the qrc/CSP/packaging evidence described above.
  Fast MathJax failures should surface through this status path and fall back promptly; timeouts are a backstop, not the normal failure path.
- Specify async/lifecycle rules before wiring into `FormulaPreviewDialog`. Inline `FormulaPreviewLabel` remains on the synchronous PNG path until the visual-consistency gate explicitly chooses a safe shared-thumbnail approach; do not put live WebEngine on the per-keystroke inline hot path unless a later plan redesigns the synchronous API contract.
  - WebEngine widgets are owned and destroyed by the preview dialog on the GUI thread;
  - every dialog render request carries a monotonically increasing token so a late completion cannot overwrite a newer dialog snapshot or a closed dialog;
  - backend render attempts have a timeout and fall back to PNG/text;
  - closing a dialog invalidates pending tokens and drops pending `runJavaScript` callbacks;
  - disconnecting bridge signals applies only to a future QWebChannel fallback, not the preferred one-way page API.
- Keep the preview manager fallback-first: WebEngine failure must not make formula preview unusable.

### Phase 5: Gate Flip For Shipping, Only If Evidence Is Clean
- Change WebEngine from `NO_GO` to `GO` only after all required evidence is present:
  - security tests;
  - asset manifest/integrity tests;
  - import guard tests updated for isolated backend rules;
  - packaging exclude list changes synchronized across macOS/Windows/spec;
  - packaged artifact inspections proving QtWebEngine runtime files, helper processes, resources, translations, custom-scheme assets, and MathJax files are actually bundled on macOS and Windows;
  - artifact-size and startup/memory measurements;
  - macOS and Windows packaged-app smoke tests.
- Remove WebEngine excludes from all packaging entrypoints in one commit only after tests prove the shipping app still starts and previews formulas.
- Update release test matrix and release notes with the new evidence, not just code changes.

### Phase 6: UX Polish
- Inline preview remains compact, readable, and synchronous through the PNG backend unless the MathJax gate explicitly adds a safe equivalent-thumbnail path.
- Clicking preview opens a larger MathJax-quality rendered dialog when available, falling back to the PNG preview when not.
- The dialog should support:
  - copy rendered LaTeX source;
  - copy original DataLab expression;
  - clear error message when rendering fails;
  - light/dark theme contrast;
  - no user-facing backend mode.
- Long formulas should scroll horizontally in the preview surface without forcing the left configuration rail to widen or create horizontal scrollbars.

## Testing Plan
- Pure service tests:
  - DataLab syntax to LaTeX metadata for arithmetic, functions, powers, fractions, implicit equations, constants, matrices/cases if supported.
  - unsafe LaTeX/environment rejection remains intact for display metadata.
- LaTeX export tests:
  - Mathematica-style export golden cases for fractions, nested powers, roots, functions, Greek identifiers, implicit equations, and long quantum-defect expressions;
  - AST-backed exporter tests proving DataLab normalization and computation precedence drive LaTeX generation, including chained divisions, nested powers, unary signs, and function calls;
  - expression-engine drift tests proving `shared.expression_engine`, `datalab_latex.expression_engine`, `shared.expression_names`, symbolic export, and LaTeX export share one effective allowlist, reserved-name set, normalization behavior, AST complexity caps, and unsupported-node diagnostics;
  - precedence/associativity tests proving non-atomic AST children are grouped correctly, including `(n-delta)^2`, `a*(b+c)`, `a-(b-c)`, `a/(b/c)`, and `(a+b)^c`;
  - copy-as-LaTeX, preview, and report export all consume the same canonical metadata;
  - migration-matrix tests for error propagation, desktop fitting, web fitting, root solving, extrapolation custom formulas, result summaries, and formula preview compatibility, including Web fitting's empty-expression and stringified-`"None"` cases where no formula line should be emitted;
  - context-helper tests proving formula fragments are not double-escaped when embedded in captions, tablenotes, tables, and report paragraphs;
  - substituted-equation tests proving embedded fitted parameter values honor existing precision/digit policy but use inline-math-safe number LaTeX, not siunitx/dcolumn table-cell syntax;
  - workspace/result serialization tests proving source and typed substitution metadata round-trip, while derived LaTeX is regenerated rather than persisted as authoritative state. Add legacy-read tolerance tests for workspaces missing typed substitution metadata or canonical formula source so those files degrade to display-only legacy text rather than crashing or silently claiming canonical regeneration;
  - generated reports compile or pass LaTeX doctor checks with the supported engine/package set;
  - numeric table formatting remains controlled by the shared table formatter.
- Converter/PNG quality tests:
  - structured LaTeX metadata for supported DataLab syntax;
  - non-null PNG/pixmap output for representative supported formulas;
  - explicit unsupported/fallback behavior for structures not expressible in DataLab syntax.
- Desktop import tests:
  - importing `app_desktop.formula_preview` does not import WebEngine modules.
  - WebEngine backend module can be absent or failing and preview still falls back.
- GUI tests:
  - preview label and dialog render one style only.
  - no syntax/backend selectors exist.
  - formula preview works in error propagation, extrapolation, custom fitting, self-consistent fitting, and root solving.
  - language and theme refresh update preview text/error labels.
- WebEngine lifecycle tests, if the WebEngine spike proceeds:
  - late render completions cannot overwrite a newer dialog snapshot or a closed dialog;
  - the `runJavaScript` entrypoint returns plain JSON-compatible acknowledgement data and never relies on returning a `Promise`;
  - fast MathJax failures are observed through the shell status polling/read path and fall back promptly;
  - WebEngine timeout falls back to PNG/text without freezing the GUI when no completion arrives;
  - backend import/asset/runtime failure falls back to the PNG backend;
  - closing the preview dialog invalidates callbacks and pending render completions are ignored;
  - payload schema uses `locale` for UI language and never exposes a formula input-language selector.
  - inline preview remains synchronous and does not instantiate WebEngine.
  - `runJavaScript` calls serialize payloads safely and do not allow formula text to break out of the JavaScript argument.
  - if MathJax is intended for shipping, visual regression evidence proves inline and dialog outputs are materially equivalent for supported formulas, or the gate stays `NO_GO`.
- WebEngine spike tests:
  - CSP is restrictive.
  - remote URLs are denied.
  - only manifest-listed assets resolve.
  - the fixed JavaScript entrypoint or any future QWebChannel bridge is formula-specific and payload-limited.
  - HTML shell inserts formula payloads through text nodes.
- Packaging tests:
  - before GO: current exclude/import guards stay green.
  - after GO: packaging scripts/spec are updated together and release gates assert the new synchronized state.
- Visual tests:
  - screenshot capture confirms readable previews, no left-rail horizontal scrollbar, no overlap, and correct fallback state when WebEngine is unavailable.

## Non-Goals
- Do not reintroduce LaTeX syntax as a calculation input language.
- Do not expose multiple formula preview styles to users.
- Do not use Tectonic or external TeX compilation for live preview.
- Do not enable WebEngine in the shipping app by default before the existing evidence gate flips to `GO`.
- Do not duplicate formula parsing or constants/parameter recognition logic in the GUI layer.
- Do not ship two independent WebEngine math engines without a specific follow-up decision. The current KaTeX-oriented workbench spike remains separate and `NO_GO`; if either spike moves toward shipping, choose a single engine or document why a dual-engine bundle is justified.

## Risks And Mitigations
- **Risk: WebEngine breaks packaged app startup.** Mitigation: lazy import, fallback backend, and no exclude-list changes until evidence passes.
- **Risk: WebEngine adds complexity without improving DataLab-syntax formulas.** Mitigation: make structured converter output and PNG fallback coverage Phase 1, then continue WebEngine only with measured before/after evidence.
- **Risk: MathJax assets increase bundle size.** Mitigation: minimal vendored asset set, recorded artifact-size evidence, and release gate.
- **Risk: HTML/JS injection through formulas.** Mitigation: metadata sanitization plus text-node insertion and CSP.
- **Risk: preview and export LaTeX converters drift.** Mitigation: reconcile `render_formula_metadata()` with `format_formula_latex()` in Phase 1 and lock parity with tests before adding render backends.
- **Risk: Mathematica-like export grows into a second formula engine.** Mitigation: centralize export metadata and keep LaTeX as output only; do not make export parsing separate from the DataLab expression engine.
- **Risk: AST-backed export breaks import-light metadata endpoints.** Mitigation: extract DataLab normalization/AST-export helpers into a lightweight module that keeps current import-purity guards green; do not import `mpmath`, SymPy, Qt, matplotlib, or fitting backends at formula-service import time. Lazy imports are only an interim fallback for import-time compatibility, not a substitute for the shared registry/normalization boundary.
- **Risk: substituted formulas use table-number syntax in inline math.** Mitigation: add a dedicated math-mode value formatter for formula substitutions that shares precision decisions with existing numeric utilities but emits inline-formula-safe decimals/scientific notation rather than siunitx/dcolumn table-cell syntax.
- **Risk: two expression engines drift under a single-export claim.** Mitigation: reconcile `shared.expression_engine`, `datalab_latex.expression_engine`, and `shared.expression_names` into one effective syntax/registry/AST boundary, keep compatibility facades thin, and add drift tests across computation, reserved-name validation, symbolic export, preview, and LaTeX export.
- **Risk: formula fragments are escaped as plain text in legacy report writers.** Mitigation: add typed formula/text embedding helpers and migrate report writers through them before inserting canonical formula LaTeX.
- **Risk: substituted equations silently ignore precision and uncertainty display options.** Mitigation: treat substitutions as typed parameter placeholders formatted by existing numeric utilities, not as an already-substituted source string passed through the formula exporter.
- **Risk: AST export preserves the tree but drops required parentheses.** Mitigation: define a precedence/associativity grouping algorithm and lock it with regressions for non-atomic power bases, multiplicative/additive nesting, non-associative right operands, unary grouping, and the quantum-defect formula.
- **Risk: workspace/result files freeze stale derived LaTeX.** Mitigation: persist source/normalized source/substitution metadata only and regenerate LaTeX through the current canonical exporter on load/export.
- **Risk: two renderer backends drift.** Mitigation: all backends consume the same `FormulaPreviewMetadata` and only differ in final rendering.
- **Risk: stale KaTeX workbench-spike assets confuse the implementation.** Mitigation: create a separate formula-preview MathJax manifest/scheme/asset root and leave the existing workbench-spike manifest untouched unless that separate spike is deliberately updated.
- **Risk: formulas become visually better but computationally ambiguous.** Mitigation: preview is display-only; compute still uses the existing safe DataLab expression engine.

## Review Status
- Codex adversarial review: PASS after iterative revisions for the formula-rendering/WebEngine plan before the Mathematica-level export expansion.
- Antigravity/Gemini 3.1 Pro adversarial review: PASS after iterative revisions for the formula-rendering/WebEngine plan before the Mathematica-level export expansion.
- Claude adversarial review: PASS after iterative revisions for the formula-rendering/WebEngine plan before the Mathematica-level export expansion.
- Mathematica-level LaTeX export expansion first focused follow-up review:
  - Codex: CONTESTED. Accepted findings on AST-backed canonical export, delimiter/context ownership, and migration-matrix scope.
  - Antigravity/Gemini 3.1 Pro: CONTESTED. Accepted findings on substituted-equation numeric formatting, double-escaping, and report preamble/package requirements.
  - Claude: REJECT. Accepted findings on the need to reuse computation AST semantics for structured fractions, enumerate real export emitters, model substituted equations, and reduce DTO field drift.
  - Plan revised to address those findings; requires focused re-review before implementation starts.
- Mathematica-level LaTeX export expansion second focused follow-up review:
  - Codex: PASS.
  - Antigravity/Gemini 3.1 Pro: PASS.
  - Claude: CONTESTED. Accepted findings on explicit precedence/associativity parenthesization, `_build_substituted_expression()` and Markdown result-panel migration, serialization not persisting derived LaTeX as truth, and Web fitting's current label-only emission.
  - Plan revised to address those findings; requires focused re-review before implementation starts.
- Mathematica-level LaTeX export expansion third focused follow-up review:
  - Antigravity/Gemini 3.1 Pro: PASS.
  - Codex: CONTESTED. Accepted finding that `shared.expression_engine` must be reconciled with `datalab_latex.expression_engine` before the exporter can claim a single canonical syntax/AST source.
  - Claude: PASS, with accepted clarifications on math-mode value formatting for substitutions, root-equation report-summary scope, and mandatory lightweight extraction/lazy boundary.
  - Plan revised to address the Codex finding and Claude clarifications; requires focused re-review before implementation starts.
- Mathematica-level LaTeX export expansion final incremental re-gate:
  - Codex: PASS. Main-thread review found no remaining implementation-blocking plan findings after the shared syntax/registry/AST ownership, import-purity, escaping, substitution-formatting, web fitting, root-equation, serialization, precedence/associativity, and WebEngine-gating revisions.
  - Claude for Codex: PASS with no findings after final follow-up revisions. A broad max-quality multi-path background job was lost by worker heartbeat before producing output, so the re-gate was completed as narrower plan-only strong reviews. Claude first returned PASS with accepted medium/low clarifications on legacy serialization reads, Web fitting empty-expression behavior, and extrapolation custom-formula report threading. After those were incorporated, Claude returned PASS with one accepted low clarification on using the raw `core_result.payload.get("expression")` rather than stringified `expression_for_csv`. After that final clarification was incorporated, Claude returned PASS with `Findings: None`.
  - Gemini final re-gate: PASS with no findings. After Gemini recovered, Antigravity/Gemini 3.1 Pro was available again, but the tracked Antigravity job `agy-mqciw5jf-1285b3e77fb1` lost its worker heartbeat before producing output and was cancelled once the worker process was gone. The independent Gemini for Codex background job `job-mqcj2pfj-01a048` then completed successfully with verdict `PASS`, `Findings: None`, and lead judgment that no actionable findings remain across shared syntax/registry/AST ownership, import-purity boundaries, escaping, substituted numeric formatting, web/root/extrapolation threading, legacy serialization tolerance, precedence/associativity, and WebEngine gating.
  - Final status: Codex, Claude, and Gemini are clean for the current plan text. The plan is ready for implementation.
