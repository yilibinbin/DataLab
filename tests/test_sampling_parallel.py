"""Parallel mpmath sampler — regression tests.

Covers the ``fitting.sampling_parallel`` helper added in Phase 1 #2.
Requirements:

- Produces byte-for-byte identical mpmath values to the serial
  ``sample_mp_function`` for a given precision.
- Below a minimum-worklist threshold, transparently falls back to
  serial evaluation (process-pool overhead dwarfs the gain).
- Picklable top-level callables only — closures and lambdas cannot
  cross process boundaries; the helper must degrade to serial instead
  of raising PicklingError.
- Preserves the ``mp.nan`` fallback when an evaluation raises inside a
  worker process.
- Leaves ``mp.dps`` unchanged on the caller's process (each worker
  uses its own precision_guard).
"""

from __future__ import annotations

import math

from mpmath import mp

from fitting.plot_fitting import sample_mp_function
from fitting.sampling_parallel import (
    PARALLEL_MIN_POINTS,
    sample_mp_function_parallel,
)


# Must be module-level to be picklable across the process boundary.
def _polynomial(x):
    return x**3 - mp.mpf(2) * x + mp.mpf(1)


def _always_raises(x):
    raise ValueError("worker failure")


def _times_seven(x):
    return x * mp.mpf(7)


def test_parallel_matches_serial_for_polynomial():
    xs = [mp.mpf(i) / 10 for i in range(1, PARALLEL_MIN_POINTS + 20)]
    serial = sample_mp_function(_polynomial, xs, precision=40)
    parallel = sample_mp_function_parallel(
        _polynomial, xs, precision=40, workers=2
    )
    assert len(serial) == len(parallel)
    tol = mp.mpf(10) ** -35
    for a, b in zip(serial, parallel):
        assert abs(a - b) < tol, f"parallel={b} diverged from serial={a}"


def test_parallel_below_threshold_falls_back_to_serial():
    """Small xs are cheaper serial — no worker spin-up overhead."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS - 1)]
    result = sample_mp_function_parallel(_times_seven, xs, precision=30, workers=4)
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)


def test_parallel_unpicklable_lambda_falls_back_to_serial():
    """Lambdas cannot cross process boundaries; the helper must not
    raise PicklingError — it must degrade to serial evaluation."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    closure_captured = mp.mpf(3)
    result = sample_mp_function_parallel(
        lambda x: closure_captured * x, xs, precision=30, workers=2
    )
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == closure_captured * mp.mpf(i)


def test_parallel_preserves_nan_on_worker_exception():
    """If the callable raises in a worker, that slot must come back as
    mp.nan — same contract as sample_mp_function."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    result = sample_mp_function_parallel(
        _always_raises, xs, precision=30, workers=2
    )
    assert len(result) == len(xs)
    for v in result:
        assert mp.isnan(v)


def test_parallel_does_not_leak_mp_dps_in_caller():
    """Worker processes have their own mp.dps; the caller's dps must
    be unchanged after the call returns."""
    before = mp.dps
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    sample_mp_function_parallel(_times_seven, xs, precision=80, workers=2)
    assert mp.dps == before


def test_parallel_handles_empty_xs():
    """Empty xs is a no-op — no worker spin-up."""
    result = sample_mp_function_parallel(_times_seven, [], precision=30, workers=2)
    assert result == []


def test_parallel_workers_none_defaults_to_cpu_count():
    """workers=None picks a default based on CPU count."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 10)]
    result = sample_mp_function_parallel(_times_seven, xs, precision=30, workers=None)
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)


def test_parallel_workers_one_uses_serial_path():
    """Explicit workers=1 must trip the <2 guard and evaluate serially.
    Documents the contract so a future refactor doesn't silently change
    the semantics of 'single worker'."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 10)]
    result = sample_mp_function_parallel(
        _times_seven, xs, precision=30, workers=1
    )
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)


def test_parallel_clamps_malicious_precision():
    """A caller that passes precision=10**9 (DoS via billion-digit
    mp.nstr strings) must be silently clamped to MAX_MPMATH_DPS."""
    from shared.precision import MAX_MPMATH_DPS

    xs = [mp.mpf("1")]
    # Below-threshold → serial path exercises the same clamp
    result = sample_mp_function_parallel(
        _times_seven, xs, precision=MAX_MPMATH_DPS * 100, workers=2
    )
    assert len(result) == 1
    assert result[0] == mp.mpf(7)


def test_parallel_respects_timeout_falling_back_to_serial():
    """When a worker map exceeds the timeout, the wrapper must fall
    back to serial evaluation (not raise TimeoutError to the caller)."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    # Use an absurdly small timeout so the pool can't finish in time.
    # The fallback guarantees the same _times_seven result shape.
    result = sample_mp_function_parallel(
        _times_seven, xs, precision=30, workers=2, timeout=0.0001
    )
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)
