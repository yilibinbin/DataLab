# DataLab P4.5 Hypothesis Tests Implementation Plan

Status: draft for non-Claude review
Date: 2026-06-26

Spec:
`docs/superpowers/specs/2026-06-26-datalab-p4-5-hypothesis-tests-spec.md`

## 1. Preconditions

- Claude review is disabled by current user instruction.
- Preserve the dirty worktree. Do not stage, commit, package, publish, clean, or
  revert unrelated files.
- Reuse existing statistics input collection, semantic snapshots, CSV/LaTeX
  renderers, workspace/history/report boundaries, and precision settings.
- Do not add automatic test selection or unreviewed tests.

## 2. Key Design Decisions

1. Hypothesis tests are a statistics workflow branch:
   `workflow_mode = "hypothesis_tests"`.
2. `test_kind` is separate from `stats_mode`; do not overload the existing
   statistics-method selector.
3. First release is explicit and bounded:
   - one-sample t-test;
   - paired t-test;
   - Welch two-sample t-test;
   - exact sign test;
   - chi-square goodness-of-fit.
   No GUI/user-visible release ships until all five first-release tests and the
   semantic/export/history/report gates are complete. Slice A may land only as
   hidden core infrastructure.
4. SciPy may be used for `precision_digits <= 16`; high-precision runs must use
   reviewed mpmath formulas or emit p-value-unavailable diagnostics.
5. No plots are required for the first release.
6. Hypothesis-test p-values and decisions are diagnostics/context, not
   uncertainty-budget contribution rows.

## 3. Slice P4.5-A: Core DTOs, Validators, One-Sample T, Sign Test

Goal: establish the hypothesis-test core boundary and implement the smallest
useful test set.

Likely files:

- New `datalab_core/statistics_hypothesis.py` or equivalent.
- `datalab_core/statistics.py` only for workflow dispatch/snapshot hooks.
- `tests/test_datalab_core_statistics_hypothesis.py`.

Implementation:

- Add DTO/helpers for:
  - normalized hypothesis-test options;
  - result/effect rows;
  - diagnostics;
  - JSON-safe payload conversion.
- Add closed `validate_statistics_hypothesis_payload()`.
- Implement one-sample t-test.
- Implement exact sign test.
- Add shared p-value helpers:
  - SciPy path for low precision;
  - mpmath t-distribution survival/CDF helper or explicit high-precision
    unavailable diagnostic if not ready in this slice;
  - exact binomial p-value for sign test without SciPy dependency.
- Record backend and precision used.

Verification:

- One-sample t-test agrees with SciPy at `precision_digits <= 16`.
- High-precision one-sample t-test does not call SciPy silently.
- Sign-test exact p-values cover two-sided/less/greater and ties.
- Invalid alpha, alternative, insufficient n, zero variance, and non-finite
  inputs fail closed.
- Payload validator rejects JSON floats and malformed p-values.

## 4. Slice P4.5-B: Paired T, Welch T, Chi-Square Goodness-Of-Fit

Goal: add the remaining first-release tests after the core boundary is stable.

Likely files:

- `datalab_core/statistics_hypothesis.py`
- `tests/test_datalab_core_statistics_hypothesis.py`

Implementation:

- Implement paired t-test as one-sample t-test on paired differences `A - B`
  against `delta0`.
- Implement Welch two-sample t-test with Welch-Satterthwaite degrees of
  freedom, ordered effect `mean(A) - mean(B) - delta0`, and explicit
  less/greater tail semantics tied to that direction.
- Implement chi-square goodness-of-fit:
  - observed count column;
  - expected count or expected probability column;
  - fitted-parameter count option;
  - expected-count adequacy diagnostics.
- Add high-precision p-value policy:
  - t-distribution via reviewed mpmath helper or unavailable diagnostic;
  - chi-square via reviewed mpmath incomplete-gamma helper or unavailable
    diagnostic.
- Add formula/reference tests for:
  - paired t direction `A - B`;
  - Welch standard error and Welch-Satterthwaite degrees of freedom;
  - sign-test two-sided convention `min(1, 2 * min(lower_tail, upper_tail))`;
  - chi-square upper-tail-only p-value, probability normalization, integer
    nonnegative observed counts, zero expected-count diagnostics, and `df > 0`.

Verification:

- Paired and Welch tests agree with SciPy low-precision references.
- Chi-square agrees with SciPy low-precision references.
- Paired row alignment uses original source rows and never shifts columns after
  independent filtering.
- Expected probability/count normalization is explicit and tested.
- Edge cases produce diagnostics rather than fake p-values.

## 5. Slice P4.5-C: Semantic Snapshot, Render, CSV, LaTeX

Goal: make hypothesis-test outputs durable and exportable.

Likely files:

- `datalab_core/statistics.py`
- `datalab_latex/latex_tables_common.py` or a statistics hypothesis helper.
- `statistics_utils.py` only if legacy entrypoints need a bridge.
- `tests/test_datalab_core_statistics.py`
- `tests/test_latex_generation_consistency.py`

Implementation:

- Add `validate_statistics_hypothesis_snapshot()`.
- Add snapshot branch for `mode == "hypothesis_tests"`.
- Add `render_statistics_hypothesis_snapshot_outputs(snapshot)` returning
  `(markdown_text, csv_rows, csv_headers)`, and route
  `render_statistics_snapshot_outputs()` to it for hypothesis snapshots.
- Add deterministic text and CSV regeneration from
  `snapshot["hypothesis_test"]`; do not derive artifacts from `metric_rows` or
  rendered caches.
- Add LaTeX table generation from the same authoritative
  `snapshot["hypothesis_test"]` payload using existing dcolumn/siunitx numeric
  formatting.
- Keep structured `hypothesis_test` payload authoritative; rendered caches are
  non-authoritative.

Verification:

- Snapshot round-trip has no JSON floats.
- Malformed payloads fail closed.
- CSV and text regenerate from semantic snapshot.
- LaTeX compiles for representative tests with dcolumn and siunitx options.

## 6. Slice P4.5-D: Desktop GUI And Workspace

Goal: expose explicit hypothesis tests in Desktop.

Likely files:

- `app_desktop/views/statistics.py`
- `app_desktop/window_statistics_mixin.py`
- `app_desktop/workspace_controller.py`
- `app_desktop/workbench_specs.py`
- `tests/test_desktop_statistics_ui.py`
- `tests/test_workspace_controller.py`
- `tests/test_desktop_gui_schema_scan.py`

Implementation:

- Add or reuse a statistics workflow selector with a Hypothesis tests branch.
- Add `test_kind` selector and dynamically visible required inputs:
  - `one_sample_t`: value column A, `mu0`, alternative, alpha.
  - `paired_t`: value column A, value column B, `delta0`, alternative, alpha.
  - `welch_t`: value column A, value column B, `delta0`, alternative, alpha.
  - `sign_test`: mode selector `one_sample` or `paired`; one-sample uses value
    column A plus `m0`; paired uses value column A, value column B, and
    `delta0`; both use alternative and alpha.
  - `chi_square_gof`: observed count column, expected count column or expected
    probability column, fitted-parameter count, alpha.
- Hide irrelevant descriptive/weighted/bootstrap controls.
- Store/restore a per-test workspace config with only the controls relevant to
  the active `test_kind`, plus defaults for legacy/absent fields.
- Route execution through core hypothesis-test helpers.

Verification:

- GUI schema metadata, tooltips, language refresh, and no horizontal overflow.
- Each visible test kind has the required controls and no irrelevant controls.
- Workspace round trips cover every `test_kind` and preserve ordered column
  direction where applicable.
- Workspace save/restore preserves options and output.
- Old statistics workspaces restore normal statistics mode.

## 7. Slice P4.5-E: History, Report Bundle, Budget, Docs, Examples

Goal: complete integration and user-facing guidance.

Likely files:

- `datalab_core/history_compare.py`
- `datalab_core/uncertainty_budget.py`
- `app_desktop/report_bundle_export.py`
- `datalab_latex/report_bundle.py`
- `docs/desktop/statistics.en.md`
- `docs/desktop/statistics.zh.md`
- `docs/TEST_MATRIX.md`
- `tools/generate_example_workspaces.py`
- example workspace for hypothesis tests

Implementation:

- Add same-family history comparison for statistic, p-value, alpha, decision,
  backend, ordered value-column direction, and diagnostics using keys
  `(test_kind, metric_key)` and `(test_kind, effect_key)`.
- Add report-bundle semantic CSV/LaTeX export through the branch renderer that
  reads `snapshot["hypothesis_test"]`.
- Expose hypothesis-test rows in budget dashboard as diagnostics only, keyed by
  family/category/test/metric; never as variance contributions.
- Add examples for one-sample t and chi-square goodness-of-fit.
- Document assumptions, limitations, high-precision p-value policy, and
  deferred tests.

Verification:

- History compare fixtures.
- Report-bundle round-trip.
- Budget extractor diagnostic behavior.
- Example workspaces open as templates and calculate.
- Docs guardrails and test matrix pass.

## 8. Review And Quality Gates

Before implementation:

- Codex main-thread review of spec and plan.
- Codex subagent read-only review of spec and plan.
- Gemini/Antigravity review only if available, focused, and responsive.
- Claude must not be used under the current user instruction.
- `git diff --check` for the spec, plan, and planning files.

Per implementation slice:

- Write focused tests first where practical.
- Run focused pytest for touched behavior.
- Run GUI schema scan for Desktop changes.
- Run Ruff, compileall, feasible mypy, and scoped diff-check.
- Run a non-Claude read-only review after substantive code changes.
- Fix accepted findings before starting the next slice.

## 9. Stop Conditions

- If high-precision p-value formulas are not ready, expose explicit
  high-precision unavailable diagnostics rather than silently using SciPy.
- If GUI workflow selection would overload `stats_mode`, stop and add a
  separate workflow field.
- If LaTeX requires duplicated numeric formatting, stop and reuse/extract a
  shared helper.
- If a new test needs a different input model, split it into a later reviewed
  slice.
