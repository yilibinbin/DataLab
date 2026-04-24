"""R10 C3 regression: sample_mp_function must use precision_guard.

Bare 'mp.dps = precision' mutation outside precision_guard causes concurrent-
job corruption because mp.dps is process-global. This test asserts that
precision_guard is the sole mechanism used.
"""

from __future__ import annotations

from unittest.mock import patch

from mpmath import mp

from fitting import plot_fitting


def test_sample_mp_function_delegates_to_precision_guard():
    """sample_mp_function must enter shared.precision.precision_guard."""
    called = {"count": 0}

    import shared.precision as _precision

    orig_guard = _precision.precision_guard

    def spy_guard(*args, **kwargs):
        called["count"] += 1
        return orig_guard(*args, **kwargs)

    # Patch at both the shared.precision module AND the local binding in
    # plot_fitting (handles either `from shared.precision import precision_guard`
    # or `from shared import precision; precision.precision_guard(...)` styles).
    with patch("shared.precision.precision_guard", spy_guard), \
         patch.object(plot_fitting, "precision_guard", spy_guard, create=True):
        plot_fitting.sample_mp_function(
            func=lambda x: mp.mpf(x) * mp.mpf(2),
            x_values=[mp.mpf(1), mp.mpf(2)],
            precision=50,
        )

    assert called["count"] >= 1, (
        "sample_mp_function did not call precision_guard at all — it is likely "
        "still using raw mp.dps = ... assignment which races across threads."
    )


def test_mp_dps_restored_on_exception_inside_sampler():
    """If the callback raises, mp.dps must be restored."""
    before = mp.dps

    class Boom(Exception):
        pass

    def boom_func(_):
        raise Boom("explode mid-iteration")

    try:
        plot_fitting.sample_mp_function(
            func=boom_func,
            x_values=[mp.mpf(1)],
            precision=200,
        )
    except Boom:
        pass
    # sample_mp_function's current contract catches Exception and appends mp.nan;
    # but if we ever change that, the guard must still restore.
    assert mp.dps == before, (
        f"mp.dps leaked: expected {before} after sample_mp_function, got {mp.dps}. "
        "This indicates the precision guard is missing or broken."
    )


def test_mp_dps_not_mutated_when_precision_none():
    """Passing precision=None must leave mp.dps untouched."""
    before = mp.dps
    plot_fitting.sample_mp_function(
        func=lambda x: mp.mpf(x),
        x_values=[mp.mpf(1)],
        precision=None,
    )
    assert mp.dps == before
