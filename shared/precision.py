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


def normal_inverse_cdf(probability: mp.mpf | str | int) -> mp.mpf:
    p = _validate_probability(probability)
    return mp.sqrt(2) * mp.erfinv(2 * p - 1)


def student_t_inverse_cdf(probability: mp.mpf | str | int, dof: mp.mpf | int | str) -> mp.mpf:
    p = _validate_probability(probability)
    nu = mp.mpf(dof)
    if not nu > 0:
        raise ValueError("Student-t degrees of freedom must be > 0.")
    if p == mp.mpf("0.5"):
        return mp.mpf("0")
    if p < mp.mpf("0.5"):
        return -student_t_inverse_cdf(1 - p, nu)

    lo = mp.mpf("0")
    hi = mp.mpf("1")
    while _student_t_cdf_positive(hi, nu) < p:
        hi *= 2

    tolerance = mp.power(10, -max(8, mp.dps - 8))
    for _ in range(max(80, mp.dps * 4)):
        mid = (lo + hi) / 2
        if _student_t_cdf_positive(mid, nu) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo <= tolerance * max(1, abs(mid)):
            break
    return (lo + hi) / 2


def normal_two_sided_critical_value(confidence_level: mp.mpf | str | int) -> mp.mpf:
    level = _validate_confidence_level(confidence_level)
    return normal_inverse_cdf((1 + level) / 2)


def student_t_two_sided_critical_value(
    confidence_level: mp.mpf | str | int,
    dof: mp.mpf | int | str,
) -> mp.mpf:
    level = _validate_confidence_level(confidence_level)
    return student_t_inverse_cdf((1 + level) / 2, dof)


def _student_t_cdf_positive(t_value: mp.mpf, dof: mp.mpf) -> mp.mpf:
    x = dof / (dof + t_value * t_value)
    return 1 - mp.mpf("0.5") * mp.betainc(dof / 2, mp.mpf("0.5"), 0, x, regularized=True)


def _validate_probability(probability: mp.mpf | str | int) -> mp.mpf:
    p = mp.mpf(probability)
    if not (0 < p < 1):
        raise ValueError("Probability must be in (0, 1).")
    return p


def _validate_confidence_level(confidence_level: mp.mpf | str | int) -> mp.mpf:
    level = mp.mpf(confidence_level)
    if not (0 < level < 1):
        raise ValueError("Confidence level must be in (0, 1).")
    return level
