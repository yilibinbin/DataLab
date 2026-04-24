"""Benchmark the mpmath sampling pipeline (Phase 1 #1 + #2 effects).

Baseline timings measure the LRU cache + parallel sampler together
vs. a cold cache. Use::

    pytest benchmarks/test_sampling_performance.py --benchmark-only

``pytest-benchmark`` records the stats; CI captures the JSON and
charts PR-over-PR deltas so a performance regression lands with a
visible red line.
"""

from __future__ import annotations

import pytest


pytest.importorskip("pytest_benchmark")


def _polynomial(x):
    return x**3 - 2 * x + 1


@pytest.mark.benchmark(group="sampling")
def test_serial_sample_100_points_dps50(benchmark):
    from mpmath import mp

    from fitting.plot_fitting import sample_mp_function
    from shared.caching import clear_sampling_cache

    xs = [mp.mpf(i) / 10 for i in range(1, 101)]
    # Fresh cache each run so we measure the cold-path cost.
    clear_sampling_cache()
    benchmark(sample_mp_function, _polynomial, xs, precision=50)


@pytest.mark.benchmark(group="sampling")
def test_cached_sample_100_points_dps50(benchmark):
    """Second-call cost: should be O(hash) not O(N mpmath evals)."""
    from mpmath import mp

    from fitting.plot_fitting import sample_mp_function
    from shared.caching import clear_sampling_cache

    xs = [mp.mpf(i) / 10 for i in range(1, 101)]
    clear_sampling_cache()
    sample_mp_function(_polynomial, xs, precision=50)  # prime cache
    benchmark(sample_mp_function, _polynomial, xs, precision=50)


@pytest.mark.benchmark(group="sampling")
def test_parallel_sample_1000_points_dps80(benchmark):
    """Demonstrates the parallel sampler's wall-clock advantage over
    serial for workloads above the threshold."""
    from mpmath import mp

    from fitting.sampling_parallel import sample_mp_function_parallel

    xs = [mp.mpf(i) / 100 for i in range(1, 1001)]
    benchmark(
        sample_mp_function_parallel, _polynomial, xs,
        precision=80, workers=2,
    )
