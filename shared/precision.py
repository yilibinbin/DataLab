from __future__ import annotations

from contextlib import contextmanager

from mpmath import mp

MIN_MPMATH_DPS = 10
MAX_MPMATH_DPS = 1_000_000


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


@contextmanager
def precision_guard(
    dps: int | None,
    *,
    clamp_min: int = 1,
    clamp_max: int | None = None,
):
    """
    Temporarily set `mp.dps` and restore it on exit.

    - If dps is None or invalid, keeps the current precision.
    - Returns the precision that was active inside the context via `yield`.
    """
    previous = mp.dps
    if dps is None:
        yield previous
        return
    coerced = _coerce_int(dps)
    if coerced is None:
        yield previous
        return
    clamped = max(int(clamp_min), int(coerced))
    if clamp_max is not None:
        clamped = min(int(clamp_max), clamped)
    mp.dps = max(1, int(clamped))
    try:
        yield mp.dps
    finally:
        mp.dps = previous
