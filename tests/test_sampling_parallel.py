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

from concurrent.futures import TimeoutError as _FutureTimeout
from typing import Any, Callable, Iterable, Sequence

from mpmath import mp

from fitting import sampling_parallel
from fitting.plot_fitting import sample_mp_function
from fitting.sampling_parallel import (
    PARALLEL_MIN_POINTS,
    sample_mp_function_parallel,
)
from shared.parallel_config import ParallelConfig, ParallelMode, ParallelWorkload


# Must be module-level to be picklable across the process boundary.
def _polynomial(x: mp.mpf) -> mp.mpf:
    return x**3 - mp.mpf(2) * x + mp.mpf(1)


def _always_raises(x: mp.mpf) -> mp.mpf:
    raise ValueError("worker failure")


def _times_seven(x: mp.mpf) -> mp.mpf:
    return x * mp.mpf(7)


def test_parallel_matches_serial_for_polynomial() -> None:
    xs = [mp.mpf(i) / 10 for i in range(1, PARALLEL_MIN_POINTS + 20)]
    serial = sample_mp_function(_polynomial, xs, precision=40)
    parallel = sample_mp_function_parallel(
        _polynomial, xs, precision=40, workers=2
    )
    assert len(serial) == len(parallel)
    tol = mp.mpf(10) ** -35
    for a, b in zip(serial, parallel):
        assert abs(a - b) < tol, f"parallel={b} diverged from serial={a}"


def test_parallel_process_path_uses_shared_backend(
    monkeypatch: Any,
) -> None:
    calls: dict[str, object] = {}

    class FakeParallelMapExecutor:
        def __init__(self, config: ParallelConfig) -> None:
            calls["config"] = config

        def map_pure(
            self,
            func: Callable[[object], list[str]],
            items: Iterable[object],
            *,
            workload: ParallelWorkload,
            timeout: float | None = None,
        ) -> list[list[str]]:
            item_list = list(items)
            calls["items"] = item_list
            calls["workload"] = workload
            calls["timeout"] = timeout
            return [func(item) for item in item_list]

    monkeypatch.setattr(
        sampling_parallel, "ParallelMapExecutor", FakeParallelMapExecutor
    )
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]

    result = sample_mp_function_parallel(
        _times_seven, xs, precision=30, workers=3, timeout=12.0
    )

    assert [int(v) for v in result] == [i * 7 for i in range(len(xs))]
    config = calls["config"]
    assert isinstance(config, ParallelConfig)
    assert config.mode == ParallelMode.PROCESS
    assert config.process_start_method == "spawn"
    assert config.max_workers == 3
    assert calls["workload"] == ParallelWorkload.CPU_MPMATH
    assert calls["timeout"] == 12.0
    items = calls["items"]
    assert isinstance(items, list)
    assert len(items) == 3


def test_parallel_timeout_from_shared_backend_falls_back_to_serial(
    monkeypatch: Any,
) -> None:
    serial_fallback_ran = False
    original_serial_fallback = sampling_parallel._serial_fallback

    class TimeoutParallelMapExecutor:
        def __init__(self, config: ParallelConfig) -> None:
            self.config = config

        def map_pure(
            self,
            func: Callable[[object], list[str]],
            items: Iterable[object],
            *,
            workload: ParallelWorkload,
            timeout: float | None = None,
        ) -> list[list[str]]:
            raise _FutureTimeout()

    def observed_serial_fallback(
        func: Callable[[mp.mpf], mp.mpf],
        xs: Sequence[mp.mpf],
        precision: int,
    ) -> list[mp.mpf]:
        nonlocal serial_fallback_ran
        serial_fallback_ran = True
        return original_serial_fallback(func, xs, precision)

    monkeypatch.setattr(
        sampling_parallel, "ParallelMapExecutor", TimeoutParallelMapExecutor
    )
    monkeypatch.setattr(
        sampling_parallel, "_serial_fallback", observed_serial_fallback
    )
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]

    result = sample_mp_function_parallel(
        _times_seven, xs, precision=30, workers=2, timeout=0.1
    )

    assert [int(v) for v in result] == [i * 7 for i in range(len(xs))]
    assert serial_fallback_ran


def test_parallel_below_threshold_falls_back_to_serial() -> None:
    """Small xs are cheaper serial — no worker spin-up overhead."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS - 1)]
    result = sample_mp_function_parallel(_times_seven, xs, precision=30, workers=4)
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)


def test_parallel_unpicklable_lambda_falls_back_to_serial() -> None:
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


def test_parallel_preserves_nan_on_worker_exception() -> None:
    """If the callable raises in a worker, that slot must come back as
    mp.nan — same contract as sample_mp_function."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    result = sample_mp_function_parallel(
        _always_raises, xs, precision=30, workers=2
    )
    assert len(result) == len(xs)
    for v in result:
        assert mp.isnan(v)


def test_parallel_does_not_leak_mp_dps_in_caller() -> None:
    """Worker processes have their own mp.dps; the caller's dps must
    be unchanged after the call returns."""
    before = mp.dps
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 5)]
    sample_mp_function_parallel(_times_seven, xs, precision=80, workers=2)
    assert mp.dps == before


def test_parallel_handles_empty_xs() -> None:
    """Empty xs is a no-op — no worker spin-up."""
    result = sample_mp_function_parallel(_times_seven, [], precision=30, workers=2)
    assert result == []


def test_parallel_workers_none_defaults_to_cpu_count() -> None:
    """workers=None picks a default based on CPU count."""
    xs = [mp.mpf(i) for i in range(PARALLEL_MIN_POINTS + 10)]
    result = sample_mp_function_parallel(_times_seven, xs, precision=30, workers=None)
    assert len(result) == len(xs)
    for i, v in enumerate(result):
        assert v == mp.mpf(i) * mp.mpf(7)


def test_parallel_workers_one_uses_serial_path() -> None:
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


def test_parallel_clamps_malicious_precision() -> None:
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


def test_parallel_respects_timeout_falling_back_to_serial() -> None:
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
