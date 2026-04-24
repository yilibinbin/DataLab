"""Benchmark the fitting pipeline (Phase 1 + Phase 2 effects).

Baseline timings for:
- Single-model fit at typical sizes
- Auto-fit across all registered linear models
- render_fitting_overview + the Phase 1 #4 PNG cache

CI captures deltas so a regression in the hot path is visible
PR-over-PR.
"""

from __future__ import annotations

import pytest


pytest.importorskip("pytest_benchmark")


@pytest.fixture
def _linear_data():
    import numpy as np  # numpy is optional; skip the benchmark when absent
    np = pytest.importorskip("numpy")
    xs = list(np.linspace(1.0, 10.0, 50))
    ys = [2.0 * x + 1.0 + 0.05 * (i - 25) for i, x in enumerate(xs)]
    return xs, ys


@pytest.mark.benchmark(group="fit")
def test_linear_model_fit_50_points(benchmark, _linear_data):
    from fitting.auto_models import AUTO_MODELS, fit_linear_model

    xs, ys = _linear_data
    linear = next(d for d in AUTO_MODELS if d.identifier == "M1")
    benchmark(fit_linear_model, linear, xs, ys, precision=50)


@pytest.mark.benchmark(group="fit")
def test_auto_fit_50_points(benchmark, _linear_data):
    from fitting.model_selector import auto_fit_dataset

    xs, ys = _linear_data
    benchmark(auto_fit_dataset, xs, ys, precision=50)


@pytest.mark.benchmark(group="render")
def test_render_fitting_overview_uncached(benchmark):
    """The uncached renderer's cost — this is what the Phase 1 #4
    cache avoids on repeat calls."""
    from fitting.plot_fitting import render_fitting_overview

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.1, 3.9, 6.2, 7.8, 9.9]
    fitted = [("linear", [1.95, 3.9, 5.85, 7.8, 9.75])]
    residuals = [("linear", [0.15, 0.0, 0.35, 0.0, 0.15])]
    benchmark(render_fitting_overview, xs, ys, fitted, residuals)


@pytest.mark.benchmark(group="render")
def test_render_fitting_overview_cached(benchmark):
    """Cache-hit cost: should be ~1 ms vs ~150 ms for the cold path."""
    from fitting.plot_fitting import (
        clear_fit_render_cache,
        render_fitting_overview_cached,
    )

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.1, 3.9, 6.2, 7.8, 9.9]
    fitted = [("linear", [1.95, 3.9, 5.85, 7.8, 9.75])]
    residuals = [("linear", [0.15, 0.0, 0.35, 0.0, 0.15])]
    clear_fit_render_cache()
    render_fitting_overview_cached(xs, ys, fitted, residuals)  # prime
    benchmark(render_fitting_overview_cached, xs, ys, fitted, residuals)
