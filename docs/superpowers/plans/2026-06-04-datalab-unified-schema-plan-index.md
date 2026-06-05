# DataLab Unified Schema Program Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the reviewed unified form-schema and root-plot design into independent implementation plans that can be executed, reviewed, tested, and committed phase by phase.

**Architecture:** Phase 1 introduces schema and binder foundations without changing broad UI behavior. Phases 2-5 migrate inputs, results/workspace snapshots, root plotting, and cleanup onto that foundation.

**Tech Stack:** Python 3, PySide6, pytest/pytest-qt, existing `shared/ui_specs.py`, `app_desktop` Qt widgets, workspace controller, root-solving modules, Matplotlib-backed existing plot display.

---

## Source Spec

- `docs/superpowers/specs/2026-06-04-datalab-unified-form-schema-and-root-plot-design.md`
- External review status: Claude PASS with `findings: []`; Gemini PASS with no actionable findings.

## Plan Files

Execute in this order:

1. `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-1-foundation-plan.md`
2. `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-2-config-input-plan.md`
3. `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-3-result-workspace-plan.md`
4. `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-4-root-plot-plan.md`
5. `docs/superpowers/plans/2026-06-04-datalab-unified-schema-phase-5-convergence-plan.md`

## Cross-Phase Guardrails

- Do not use `git add .`.
- Do not stage `.superpowers/` companion cache.
- Preserve existing widget attributes and object names until the corresponding phase explicitly migrates them.
- Preserve workspace compatibility and add fixtures before changing restore/capture semantics.
- Run focused tests after each task and commit each completed task separately.
- If a phase reveals that the previous schema interface is insufficient, stop and revise the previous phase plan/spec rather than adding one-off code.

## Completion Criteria

- All five phase plans exist and pass self-review.
- Implementation of each phase leaves the app launchable in source mode.
- Final broad GUI scan covers Chinese and English modes, input help affordances, root plot generation, result snapshots, and no left-panel clipping.
