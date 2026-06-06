"""LRU cache for mpmath high-precision sampling.

The ``sample_mp_function`` hot-path in :mod:`fitting.plot_fitting` evaluates
the same ``(func, xs, precision)`` triple every time the user re-renders a
fitting preview (tab switch, LaTeX re-export, zoom change). Each call costs
O(N_points) mpmath function evaluations at dps≥50, which on interactive
workflows becomes the single largest contributor to UI latency.

This module caches the result keyed on:

- ``id(func)`` — object identity; cheap. We also hold a strong reference to
  the callable inside the cache tuple so its ``id`` cannot be reused while
  the entry is alive (reusing a freed id would otherwise produce a silent
  wrong-cache hit).
- A string serialization of ``xs`` at an *oversampled* precision equal to
  ``max(_MIN_KEY_PRECISION, precision)``. Using a fixed ceiling would
  silently truncate xs when callers request a higher-precision fit; we
  widen the key precision to whichever is larger so precision-sensitive
  callers stay correct.
- The requested ``precision`` itself.
- An optional ``cache_token`` (opaque, hashable) that callers may pass to
  invalidate the cache when their callable closes over mutable state. For
  current DataLab callers (``build_linear_evaluator`` in
  ``fitting/auto_models.py`` and the custom-model evaluators) the closure
  state is fixed at creation time, so the default token is sufficient.

All precision mutations flow through ``shared.precision.precision_guard``
— the project-canonical context manager — so concurrent workers never
observe half-mutated ``mp.dps`` (it is process-global in mpmath). The
cache also falls back gracefully when the callable is unhashable (e.g.
when a third-party caller passes a class instance with a custom
``__eq__`` but no ``__hash__``).

Values are cached as strings and re-materialized to ``mp.mpf`` on hit.
``mp.nan`` is encoded as the literal ``"nan"`` so the legacy
"exception → mp.nan" contract in ``sample_mp_function`` survives the
cache round-trip.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Hashable, NamedTuple, Sequence

import mpmath as mp

from shared.precision import precision_guard

__all__ = [
    "sample_with_cache",
    "sampling_cache_info",
    "clear_sampling_cache",
]

# Lower bound on the key-stringification precision (significant digits —
# mp.nstr uses sig-figs, and at the magnitudes we see in practice they
# are close enough to dps that the distinction does not matter for
# correctness; the key only needs to be stable and unique). When the
# caller's requested precision exceeds this, we use the caller's
# precision instead so that distinct ``xs`` at precisions > 200 are
# still distinguished.
_MIN_KEY_PRECISION = 200

# Hard cap on key-stringification precision. Without this, a caller
# (including a web form) could pass ``precision=10**9`` and trigger
# ``mp.nstr(x, 10**9)`` which produces a billion-digit string per xs
# value — an unbounded allocation. Above this cap we bypass caching
# instead of truncating the key, because a truncated high-precision key
# can silently alias distinct inputs.
_MAX_KEY_PRECISION = 1_000

# Minimum accepted ``precision`` argument. ``mp.nstr(x, 0)`` raises and
# ``precision_guard`` clamps dps to ``>= 1`` — we enforce the same
# floor here to fail fast instead of feeding zero/negative through.
_MIN_PRECISION = 1

# Per-entry cap on xs length. Prevents a pathological caller from pinning
# unbounded memory in the LRU. DataLab plots typically have <10,000 points;
# 50,000 is a generous ceiling for desktop and web alike (at
# ``_MAX_KEY_PRECISION=1000`` sig-figs, 50k * 2 * 1000 chars ≈ 100 MB
# worst-case per entry).
_MAX_XS_PER_ENTRY = 50_000

_MAXSIZE = 256  # LRU bound → ~few MB of cached samples for typical use


class _CacheInfo(NamedTuple):
    hits: int
    misses: int
    currsize: int
    # ``functools.lru_cache.cache_info().maxsize`` is ``int | None``
    # because ``lru_cache(maxsize=None)`` is unbounded. Mirror the
    # stdlib type so re-serializing the info doesn't require a cast.
    maxsize: int | None


def _xs_to_key(xs: Sequence[mp.mpf], key_precision: int) -> tuple[str, ...]:
    """Stringify xs at ``key_precision`` dps for a stable hash key."""
    with precision_guard(key_precision):
        return tuple(mp.nstr(mp.mpf(x), key_precision) for x in xs)


@lru_cache(maxsize=_MAXSIZE)
def _cached_sample_impl(
    func_id: int,
    xs_key: tuple[str, ...],
    precision: int,
    cache_token: Hashable,
    func_ref: Callable[..., Any],  # held so lru_cache keeps a strong reference
) -> tuple[str, ...]:
    """Inner cached worker.

    ``func_ref`` is part of the args so ``lru_cache`` holds a strong
    reference while the entry lives — otherwise the caller could
    garbage-collect ``func`` and a subsequent ``id()`` collision with an
    unrelated callable would produce a silent bad cache hit.

    ``cache_token`` is an opaque hashable provided by the caller for
    closure-invalidation; see module docstring.
    """
    del func_id, cache_token  # only carried for cache-key uniqueness
    with precision_guard(precision):
        out: list[str] = []
        for x_str in xs_key:
            x = mp.mpf(x_str)
            try:
                out.append(mp.nstr(mp.mpf(func_ref(x)), precision))
            except Exception:
                out.append("nan")
        return tuple(out)


def _evaluate_direct(
    func: Callable[[mp.mpf], mp.mpf],
    xs: Sequence[mp.mpf],
    precision: int,
) -> list[mp.mpf]:
    """Uncached path — used when the callable is unhashable or xs exceeds
    the per-entry cap. Still routes through ``precision_guard`` so the
    thread-safety contract holds."""
    with precision_guard(precision):
        out: list[mp.mpf] = []
        for value in xs:
            try:
                out.append(mp.mpf(func(mp.mpf(value))))
            except Exception:
                out.append(mp.nan)
        return out


def sample_with_cache(
    func: Callable[[mp.mpf], mp.mpf],
    xs: Sequence[mp.mpf],
    precision: int,
    *,
    cache_token: Hashable = None,
) -> list[mp.mpf]:
    """Cached sampler.

    Returns a fresh list of ``mp.mpf`` on every call (cache hits
    re-materialize from stored strings so callers may mutate the list
    freely).

    Parameters
    ----------
    func:
        Callable from ``mp.mpf`` to ``mp.mpf``. Must raise Exception (not
        silently return a bogus value) for inputs outside its domain; the
        exception is trapped and encoded as ``mp.nan``.
    xs:
        Sequence of x values.
    precision:
        Target ``mp.dps`` used for both evaluation and string
        serialization of the cached result.
    cache_token:
        Optional opaque hashable. Bump this when ``func`` closes over
        mutable state that changed since the last call. ``None`` (the
        default) is appropriate for all current DataLab callers whose
        evaluators freeze their parameters at creation time.
    """
    # Normalize the precision argument before anything else. Enforces the
    # minimum floor (mp.nstr(x, 0) raises) and prevents the caller from
    # driving mp.nstr with arbitrarily large precision.
    precision_int = max(_MIN_PRECISION, int(precision))

    if len(xs) > _MAX_XS_PER_ENTRY or precision_int > _MAX_KEY_PRECISION:
        return _evaluate_direct(func, xs, precision_int)

    key_precision = min(
        _MAX_KEY_PRECISION,
        max(_MIN_KEY_PRECISION, precision_int),
    )
    xs_key = _xs_to_key(xs, key_precision)

    try:
        strs = _cached_sample_impl(
            id(func), xs_key, precision_int, cache_token, func
        )
    except TypeError:
        # Unhashable callable (e.g. instance with custom __eq__ and no
        # __hash__) — fall back to direct evaluation.
        return _evaluate_direct(func, xs, precision_int)

    with precision_guard(precision_int):
        return [mp.nan if s == "nan" else mp.mpf(s) for s in strs]


def sampling_cache_info() -> _CacheInfo:
    info = _cached_sample_impl.cache_info()
    return _CacheInfo(info.hits, info.misses, info.currsize, info.maxsize)


def clear_sampling_cache() -> None:
    _cached_sample_impl.cache_clear()
