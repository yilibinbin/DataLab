"""Process-pool sampler for high-precision mpmath functions.

``mp.dps`` is a **process-global** mutable attribute in mpmath, so
threads cannot help: two threads in the same process can only use one
dps at a time. Process pools are the only way to scale
``sample_mp_function`` across CPU cores while each shard keeps its own
precision.

Contract with the rest of DataLab:

- Falls back to serial evaluation whenever spawning workers would hurt
  more than it helps: small xs lists, single-worker configuration, and
  unpicklable callables (lambdas, closures capturing non-picklable
  state). The fallback is silent — we match the serial contract rather
  than raise ``PicklingError`` at the caller.
- Mirrors ``fitting.plot_fitting.sample_mp_function`` exactly for the
  exception-to-``mp.nan`` mapping and the per-worker ``precision_guard``
  wrapping, so callers see no behavioural difference besides latency.
- Uses the ``spawn`` multiprocessing context unconditionally. ``fork``
  on macOS with PySide6 / Qt / matplotlib inherits process state that
  routinely corrupts child processes; ``spawn`` is the only portable
  default.

Not yet wired into ``sample_mp_function`` by default. Callers that
benefit from parallelism (auto-fit across many models, dense preview
renders) opt in by calling this module directly.
"""

from __future__ import annotations

import logging
import multiprocessing as _mp
import pickle
from concurrent.futures import TimeoutError as _PoolTimeout
from typing import Callable, Sequence

from mpmath import mp

from shared.parallel_backend import ParallelMapExecutor
from shared.parallel_config import ParallelConfig, ParallelMode, ParallelWorkload
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard

__all__ = [
    "DEFAULT_WORKER_TIMEOUT_SECONDS",
    "PARALLEL_MIN_POINTS",
    "sample_mp_function_parallel",
]

_logger = logging.getLogger(__name__)

# Below this point count, the worker spin-up + pickling overhead
# (measured ~30–80 ms on typical dev laptops) exceeds the savings from
# parallel evaluation. Empirically tuned; callers that know their
# workload is cheap should still call the serial path directly.
PARALLEL_MIN_POINTS = 32

# Hard ceiling on how long a single worker map is allowed to run. Caps
# hang risk if a user-supplied callable enters a long/infinite mpmath
# computation (e.g. ``mp.hyp2f1`` with pathological arguments). On
# timeout the whole call falls back to serial evaluation (with the same
# timeout applied there).
DEFAULT_WORKER_TIMEOUT_SECONDS = 60.0


def _worker(args: tuple[bytes, list[str], int]) -> list[str]:
    """Worker entry point.

    Receives ``(pickled_func, xs_strings, precision)`` and returns a
    list of mpmath-string values (``"nan"`` sentinel on exception).
    String round-trip mirrors ``shared.caching``'s contract — avoids
    pickling ``mp.mpf`` objects, which are expensive to serialise at
    high precision.

    ``precision`` is clamped to ``[MIN_MPMATH_DPS, MAX_MPMATH_DPS]``
    inside ``precision_guard`` so a malicious value cannot drive
    ``mp.nstr`` into unbounded allocations.
    """
    func_pickle, xs_str, precision = args
    func = pickle.loads(func_pickle)
    out: list[str] = []
    with precision_guard(
        precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS
    ) as effective_dps:
        for s in xs_str:
            try:
                x = mp.mpf(s)
                out.append(mp.nstr(mp.mpf(func(x)), effective_dps))
            except Exception:
                out.append("nan")
    return out


def _default_workers() -> int:
    """Leaves one core free for the UI event loop / WSGI reactor.

    On a 1-CPU host this returns 1, which trips the ``workers < 2``
    guard in ``sample_mp_function_parallel`` and routes to serial —
    avoiding the cost of spinning a process pool for a machine that
    can't run it in parallel anyway.
    """
    count = _mp.cpu_count() or 2
    return max(1, count - 1)


def _clamp_precision(precision: int) -> int:
    """Normalise the caller-supplied precision against the shared
    mpmath bounds. This is belt-and-braces with the inner
    ``precision_guard`` clamp — but doing it up-front avoids paying
    the cost of a giant IPC payload (the parent-side xs stringification
    also uses ``precision``, and truncating it here limits both sides
    in lockstep)."""
    try:
        value = int(precision)
    except Exception:
        value = MIN_MPMATH_DPS
    return max(MIN_MPMATH_DPS, min(MAX_MPMATH_DPS, value))


def _stringify_xs(xs: Sequence[mp.mpf], precision: int) -> list[str]:
    """Serialise xs to strings at the requested precision. Used for
    worker IPC; does not need to match the cache-key serialization in
    ``shared.caching`` because these strings never participate in a
    cross-call hash. ``precision`` is clamped to
    ``[MIN_MPMATH_DPS, MAX_MPMATH_DPS]`` so a malicious value cannot
    drive ``mp.nstr`` into unbounded allocations on the parent side
    either."""
    with precision_guard(
        precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS
    ) as effective_dps:
        return [mp.nstr(mp.mpf(x), effective_dps) for x in xs]


def _serial_fallback(
    func: Callable[[mp.mpf], mp.mpf],
    xs: Sequence[mp.mpf],
    precision: int,
) -> list[mp.mpf]:
    """Serial path used when parallelism is disabled, unprofitable, or
    impossible (unpicklable callable, pool spawn failure, map timeout).
    Matches ``sample_mp_function`` semantics exactly — parallel callers
    that hit a fallback observe zero behavioural difference, only a
    latency penalty.

    Structurally mirrors ``shared.caching._evaluate_direct``; if the
    nan-sentinel contract ever changes, both must be updated.
    """
    out: list[mp.mpf] = []
    with precision_guard(
        precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS
    ):
        for value in xs:
            try:
                out.append(mp.mpf(func(mp.mpf(value))))
            except Exception:
                out.append(mp.nan)
    return out


def sample_mp_function_parallel(
    func: Callable[[mp.mpf], mp.mpf],
    xs: Sequence[mp.mpf],
    precision: int,
    workers: int | None = None,
    timeout: float | None = DEFAULT_WORKER_TIMEOUT_SECONDS,
) -> list[mp.mpf]:
    """Parallel equivalent of ``sample_mp_function``.

    Parameters
    ----------
    func:
        Mapping ``mp.mpf -> mp.mpf``. **Must be picklable** across
        process boundaries to benefit from parallelism; unpicklable
        callables silently fall back to serial evaluation. Callers
        deploying this in a multi-tenant web context **must** restrict
        ``func`` to trusted (module-level, allow-listed) callables —
        ``pickle.dumps(func)`` followed by ``pickle.loads`` inside a
        worker is equivalent to code execution in the worker process.
    xs:
        Input values.
    precision:
        Target ``mp.dps``. Clamped to
        ``[MIN_MPMATH_DPS, MAX_MPMATH_DPS]`` before use so an
        untrusted value cannot drive ``mp.nstr`` into unbounded
        allocations.
    workers:
        Number of worker processes. ``None`` picks
        ``max(1, cpu_count - 1)``; ``<2`` falls back to serial.
    timeout:
        Per-map wall-clock timeout in seconds. On timeout the whole
        call falls back to serial (with the same timeout applied via
        the caller's thread — serial has no inherent cancellation, so
        pathological callables should also be caught at the input
        validation layer). Pass ``None`` to disable (not recommended
        in web contexts).
    """
    if not xs:
        return []

    safe_precision = _clamp_precision(precision)

    resolved_workers = workers if workers is not None else _default_workers()
    if resolved_workers < 2 or len(xs) < PARALLEL_MIN_POINTS:
        return _serial_fallback(func, xs, safe_precision)

    # Pickle the callable up-front; any failure means we can't ship it
    # to a worker, so degrade to serial without raising.
    try:
        func_pickle = pickle.dumps(func)
    except (pickle.PicklingError, AttributeError, TypeError) as exc:
        _logger.warning(
            "sampling_parallel: callable is not picklable (%s), "
            "falling back to serial evaluation",
            type(exc).__name__,
        )
        return _serial_fallback(func, xs, safe_precision)

    xs_str = _stringify_xs(xs, safe_precision)
    n = len(xs_str)
    chunk = (n + resolved_workers - 1) // resolved_workers
    shards = [
        (func_pickle, xs_str[i : i + chunk], safe_precision)
        for i in range(0, n, chunk)
    ]

    try:
        executor = ParallelMapExecutor(
            ParallelConfig(
                mode=ParallelMode.PROCESS,
                max_workers=resolved_workers,
                min_process_tasks=1,
                reserve_cores=0,
                process_start_method="spawn",
            )
        )
        results = executor.map_pure(
            _worker,
            shards,
            workload=ParallelWorkload.CPU_MPMATH,
            timeout=timeout,
        )
    except _PoolTimeout:
        _logger.warning(
            "sampling_parallel: map timed out after %.1fs, falling "
            "back to serial evaluation",
            timeout if timeout is not None else float("inf"),
        )
        return _serial_fallback(func, xs, safe_precision)
    except Exception as exc:
        _logger.warning(
            "sampling_parallel: pool failure (%s: %s), falling back "
            "to serial evaluation",
            type(exc).__name__,
            exc,
        )
        return _serial_fallback(func, xs, safe_precision)

    flat_strs = [s for shard in results for s in shard]
    with precision_guard(
        safe_precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS
    ):
        return [
            mp.nan if s == "nan" else mp.mpf(s) for s in flat_strs
        ]
