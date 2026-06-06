"""LRU cache for mpmath sampling — regression tests.

Covers the ``shared.caching`` layer added in Phase 1 #1. The cache must:

- hit on identical (func, xs, precision) repeats
- miss on precision change
- miss on xs change
- preserve the ``precision=None`` "don't touch dps" contract by bypassing
  the cache entirely (callers that skip precision pinning are typically
  inside an outer ``precision_guard`` already)
- preserve the existing ``mp.nan`` fallback for functions that raise
- distinguish xs at precisions above the _MIN_KEY_PRECISION floor
- bypass the cache gracefully when the callable is unhashable
- bypass the cache when xs exceeds the per-entry cap
- honor the ``cache_token`` parameter for callers that close over
  mutable state and want explicit invalidation
- route all precision changes through ``shared.precision.precision_guard``
"""

from __future__ import annotations

import mpmath as mp
import pytest
from mpmath import mp as _mp_obj

from fitting.plot_fitting import sample_mp_function
from shared.caching import (
    _MAX_KEY_PRECISION,
    _MAX_XS_PER_ENTRY,
    _MIN_KEY_PRECISION,
    _MIN_PRECISION,
    clear_sampling_cache,
    sample_with_cache,
    sampling_cache_info,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_sampling_cache()
    yield
    clear_sampling_cache()


def _square(x):
    return x * x


def _plus_one(x):
    return x + 1


def test_sample_mp_function_caches_identical_args():
    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    sample_mp_function(_square, xs, precision=50)
    hits_before = sampling_cache_info().hits
    sample_mp_function(_square, xs, precision=50)
    hits_after = sampling_cache_info().hits
    assert hits_after == hits_before + 1, "second call should be a cache hit"


def test_sample_mp_function_different_precision_misses():
    xs = [mp.mpf("0.5")]
    sample_mp_function(_plus_one, xs, precision=30)
    sample_mp_function(_plus_one, xs, precision=60)
    info = sampling_cache_info()
    assert info.misses >= 2, "different precision must miss the cache"


def test_sample_mp_function_different_xs_misses():
    sample_mp_function(_square, [mp.mpf("1")], precision=30)
    sample_mp_function(_square, [mp.mpf("2")], precision=30)
    info = sampling_cache_info()
    assert info.misses >= 2, "different xs must miss the cache"


def test_sample_mp_function_precision_none_bypasses_cache():
    """precision=None means the caller is already inside a precision_guard;
    we must not persist a result keyed to whatever dps happens to be
    current when the cache is populated."""
    xs = [mp.mpf("1")]
    sample_mp_function(_plus_one, xs, precision=None)
    sample_mp_function(_plus_one, xs, precision=None)
    info = sampling_cache_info()
    assert info.hits == 0, "precision=None must not touch the cache"


def test_sample_mp_function_preserves_nan_fallback():
    """Exceptions inside func still map to mp.nan (legacy behavior)."""

    def blows_up(x):
        raise ValueError("nope")

    result = sample_mp_function(blows_up, [mp.mpf("1")], precision=30)
    assert len(result) == 1
    assert mp.isnan(result[0])


def test_sample_mp_function_values_are_correct_after_cache_hit():
    """Round-trip via cache must not lose precision."""
    xs = [mp.mpf("2"), mp.mpf("3")]
    first = sample_mp_function(_square, xs, precision=50)
    second = sample_mp_function(_square, xs, precision=50)
    assert len(first) == len(second) == 2
    for a, b in zip(first, second):
        assert a == b
    assert first[0] == mp.mpf("4")
    assert first[1] == mp.mpf("9")


# ---- Fixes for three-reviewer HIGH findings ---------------------------------


def test_key_precision_widens_for_precision_above_floor():
    """When precision > _MIN_KEY_PRECISION, xs are stringified at the
    higher precision so two xs that differ only beyond 200 dps still
    produce distinct cache entries."""
    floor = _MIN_KEY_PRECISION
    above = floor + 50

    # Construct two xs that differ only in the (floor+1)-th digit.
    eps_str = "1e-" + str(floor + 10)
    x1 = mp.mpf("1")
    with _mp_obj.workdps(above + 20):
        x2 = mp.mpf("1") + mp.mpf(eps_str)

    sample_with_cache(_plus_one, [x1], precision=above)
    sample_with_cache(_plus_one, [x2], precision=above)
    info = sampling_cache_info()
    assert info.misses >= 2, (
        "higher-precision xs that differ below the _MIN_KEY_PRECISION floor "
        "must not collide in the cache"
    )


def test_unhashable_callable_bypasses_cache_gracefully():
    """A callable with custom __eq__ but no __hash__ is unhashable in
    Python 3, which would raise TypeError inside the lru_cache key
    calculation. The wrapper must fall back to direct evaluation."""

    class _Unhashable:
        __hash__ = None  # type: ignore[assignment]

        def __call__(self, x):
            return x + 1

        def __eq__(self, other):
            return isinstance(other, _Unhashable)

    f = _Unhashable()
    result = sample_with_cache(f, [mp.mpf("2")], precision=30)
    assert len(result) == 1
    assert result[0] == mp.mpf("3")
    # Hits must not have counted a successful cache populate
    info = sampling_cache_info()
    assert info.hits == 0


def test_xs_exceeding_cap_bypasses_cache():
    """Oversized xs lists are not cached — they'd pin unbounded memory."""
    xs_big = [mp.mpf(i) for i in range(_MAX_XS_PER_ENTRY + 5)]
    result = sample_with_cache(_plus_one, xs_big, precision=20)
    assert len(result) == len(xs_big)
    info = sampling_cache_info()
    assert info.currsize == 0, "oversized xs must not populate the cache"


def test_cache_token_invalidates_on_change():
    """Callers that close over mutable state can bump the cache_token to
    force a re-evaluation. The default token (None) is stable across
    calls for callers that freeze their closure state at creation."""
    state = {"coeff": mp.mpf("2")}

    def evaluator(x):
        # Closes over state; if caller mutates state["coeff"] they must
        # bump cache_token.
        return state["coeff"] * x

    xs = [mp.mpf("5")]
    r1 = sample_with_cache(evaluator, xs, precision=30, cache_token=("v", 1))
    assert r1[0] == mp.mpf("10")

    state["coeff"] = mp.mpf("3")
    # Same token → stale cache hit (documents the contract)
    r_stale = sample_with_cache(evaluator, xs, precision=30, cache_token=("v", 1))
    assert r_stale[0] == mp.mpf("10"), "same token must return cached value"

    # Bumped token → fresh evaluation
    r_fresh = sample_with_cache(evaluator, xs, precision=30, cache_token=("v", 2))
    assert r_fresh[0] == mp.mpf("15"), "bumped token must force fresh eval"


def test_sample_with_cache_routes_through_precision_guard():
    """mp.dps must be restored after the call, even on exception. This is
    the R10 C3 thread-safety invariant — any code path that mutates
    mp.dps without precision_guard will fail this."""
    before = _mp_obj.dps
    sample_with_cache(_plus_one, [mp.mpf("1")], precision=150)
    assert _mp_obj.dps == before, "mp.dps must be restored by precision_guard"


def test_sample_with_cache_rejects_nonpositive_precision_via_floor():
    """precision <= 0 would crash mp.nstr. The wrapper clamps to
    _MIN_PRECISION before touching mpmath."""
    assert _MIN_PRECISION >= 1
    # Should not raise — the floor kicks in.
    result = sample_with_cache(_plus_one, [mp.mpf("1")], precision=0)
    assert len(result) == 1
    assert result[0] == mp.mpf("2")

    result_neg = sample_with_cache(_plus_one, [mp.mpf("1")], precision=-5)
    assert len(result_neg) == 1


def test_sample_with_cache_caps_key_precision_to_prevent_dos():
    """An unbounded ``key_precision`` would let a caller drive ``mp.nstr``
    into billion-digit strings. The cap keeps each key allocation small
    (at the cost of collisions beyond the cap — acceptable since
    evaluation precision is uncapped)."""
    assert _MAX_KEY_PRECISION >= _MIN_KEY_PRECISION
    # precision far above the cap — should still return promptly
    result = sample_with_cache(
        _plus_one, [mp.mpf("1")], precision=_MAX_KEY_PRECISION * 100
    )
    assert len(result) == 1
    assert result[0] == mp.mpf("2")


def test_sample_with_cache_bypasses_cache_above_key_precision_cap():
    with _mp_obj.workdps(_MAX_KEY_PRECISION + 200):
        x1 = mp.mpf("1") + mp.power(10, -(_MAX_KEY_PRECISION + 100))
        x2 = mp.mpf("1") + 2 * mp.power(10, -(_MAX_KEY_PRECISION + 100))

        first = sample_with_cache(lambda x: x, [x1], precision=_MAX_KEY_PRECISION + 100)
        second = sample_with_cache(lambda x: x, [x2], precision=_MAX_KEY_PRECISION + 100)

    assert first[0] != second[0]
    info = sampling_cache_info()
    assert info.hits == 0
    assert info.currsize == 0


def test_sample_mp_function_forwards_cache_token():
    """The public sample_mp_function entry point must expose cache_token
    so callers with mutable closures can invalidate — otherwise the
    documented escape hatch is unreachable from DataLab's actual code
    paths."""
    state = {"k": mp.mpf("7")}

    def evaluator(x):
        return state["k"] + x

    xs = [mp.mpf("0")]
    first = sample_mp_function(evaluator, xs, precision=30, cache_token=("t", 1))
    assert first[0] == mp.mpf("7")

    state["k"] = mp.mpf("99")
    fresh = sample_mp_function(evaluator, xs, precision=30, cache_token=("t", 2))
    assert fresh[0] == mp.mpf("99")


def test_sample_with_cache_unhashable_does_not_leak_dps():
    """When the unhashable-callable bypass fires, mp.dps must still be
    restored — the direct-eval path uses precision_guard too."""

    class _Unhashable:
        __hash__ = None  # type: ignore[assignment]

        def __call__(self, x):
            return x

        def __eq__(self, other):
            return True

    before = _mp_obj.dps
    sample_with_cache(_Unhashable(), [mp.mpf("1")], precision=75)
    assert _mp_obj.dps == before
