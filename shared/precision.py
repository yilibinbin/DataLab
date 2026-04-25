from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from mpmath import mp

MIN_MPMATH_DPS = 10
MAX_MPMATH_DPS = 1_000_000


def _coerce_int(value: object) -> int | None:
    """Best-effort int coercion.

    Accepts anything ``int(...)`` would accept (str, bytes, ints, or
    any object implementing ``__int__`` / ``__index__`` / ``__trunc__``).
    The ``object`` parameter type is intentionally permissive — the
    only current caller is ``precision_guard``, which already typed
    ``dps`` as ``int | None``, but the helper is intended for future
    boundary callers (parsing user text, worker payloads, etc.) that
    have not validated the input yet. Returns ``None`` on any
    failure rather than raising, so callers can use it as a
    permissive parser.

    Implementation note: ``cast(Any, value)`` is a mypy-only
    annotation escape — runtime is unchanged, only the type checker
    is told to accept the broad ``int(...)`` call. The ``except``
    clause includes ``OverflowError`` so that ``float('inf')`` /
    ``float('nan')`` fall back to ``None`` rather than propagating
    (``int(float('inf'))`` raises ``OverflowError`` in CPython).
    """
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError, OverflowError):
        return None


@contextmanager
def precision_guard(
    dps: int | None,
    *,
    clamp_min: int = 1,
    clamp_max: int | None = None,
) -> Iterator[int]:
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
