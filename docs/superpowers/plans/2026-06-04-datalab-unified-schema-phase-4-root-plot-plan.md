# DataLab Unified Schema Phase 4 Root Plot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate bounded root-solving function plots when `Generate plots` is enabled, including root markers and uncertainty visualization that follows the selected root uncertainty method.

**Architecture:** Add a root plotting backend that consumes root batch results and existing root expression systems, then return PNG bytes through the existing image result area and workspace plot attachment flow. Keep plotting budgets deterministic and never evaluate every Monte Carlo sample across every grid point.

**Tech Stack:** root_solving, mpmath/scipy existing evaluation paths, Matplotlib/Agg existing image rendering approach, PySide6 result image display.

---

## Task 1: Root Plot Data Model

**Files:**
- Create: `root_solving/plotting.py`
- Test: `tests/test_root_solving_plotting.py`

- [x] Write failing tests for plot budget defaults, stable input-row-order selection, unsupported system warning, and no image for unsupported cases.
- [x] Run `PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_root_solving_plotting.py` and verify missing module failure.
- [x] Implement `RootPlotBudget`, `RootPlotRequest`, `RootPlotImage`, and deterministic row/sample selection helpers.
- [x] Run tests and commit:

```bash
git add root_solving/plotting.py tests/test_root_solving_plotting.py
git commit -m "feat: add root plot budget model"
```

## Task 2: Nominal Root Function Plots

**Files:**
- Modify: `root_solving/plotting.py`
- Test: `tests/test_root_solving_plotting.py`

- [x] Add tests for scalar `x^2 - A` plot containing nominal curve metadata, zero line, root marker, and deterministic grid length <= 300.
- [x] Implement nominal scalar/scan plot generation using safe expression evaluation and Agg PNG rendering.
- [x] Run tests and commit:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_root_solving_plotting.py
git add root_solving/plotting.py tests/test_root_solving_plotting.py
git commit -m "feat: render nominal root plots"
```

## Task 3: Taylor And Monte Carlo Visualization

**Files:**
- Modify: `root_solving/plotting.py`
- Test: `tests/test_root_solving_plotting.py`

- [x] Add tests for Taylor first-order function-value band, horizontal root-x interval, skipped/fallback no-band note, deterministic MC sample downsampling to <= 100 curves, and result detail budget notes.
- [x] Implement first-order function-value band over the x-grid using active uncertain inputs.
- [x] Implement MC envelope from deterministic downsampled input samples and root-marker distribution.
- [x] Run tests and commit:

```bash
PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_root_solving_plotting.py tests/test_root_solving_uncertainty.py
git add root_solving/plotting.py tests/test_root_solving_plotting.py
git commit -m "feat: add root plot uncertainty visualization"
```

## Task 4: Desktop Worker And Result Integration

**Files:**
- Modify: `app_desktop/workers_core.py`
- Modify: `app_desktop/window_extrapolation_mixin.py`
- Modify: `app_desktop/window.py`
- Test: `tests/test_app_desktop_workers_core.py`
- Test: `tests/test_desktop_root_solving_ui.py`
- Test: `tests/test_workspace_controller.py`

- [x] Add tests proving root mode honors `generate_plots_checkbox`, returns PNG bytes when enabled, displays the image in the existing result image tab, and saves/restores the plot attachment in workspace snapshots.
- [x] Run tests and verify failure because root workers ignore plot generation today.
- [x] Thread plot settings through `RootSolvingJob` with backward-compatible defaults.
- [x] Call root plotting only after successful root batch results and only within budget.
- [x] Display resulting bytes via existing result image APIs.
- [x] Run focused tests and commit:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_app_desktop_workers_core.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py tests/test_root_solving_plotting.py
git add app_desktop/workers_core.py app_desktop/window_extrapolation_mixin.py app_desktop/window.py tests/test_app_desktop_workers_core.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
git commit -m "feat: show root solving plots in desktop results"
```

## Final Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. /Users/fanghao/miniconda3/bin/python -m pytest -q tests/test_root_solving_plotting.py tests/test_root_solving_uncertainty.py tests/test_app_desktop_workers_core.py tests/test_desktop_root_solving_ui.py tests/test_workspace_controller.py
ruff check root_solving app_desktop tests/test_root_solving_plotting.py tests/test_app_desktop_workers_core.py tests/test_desktop_root_solving_ui.py
/Users/fanghao/miniconda3/bin/python -m compileall -q root_solving app_desktop
git diff --check
```

## Self-Review Checklist

- Root plot MC never evaluates every sample over every x point.
- Batch plots use stable input-row order, not completion order.
- Per-run image cap is enforced before adding new images.
- System roots warn instead of plotting misleading projections.
