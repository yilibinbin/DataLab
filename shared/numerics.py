from __future__ import annotations

from mpmath import mp


def noise_floor(*, min_digits: int = 30) -> mp.mpf:
    """
    Small positive floor derived from the current mp.dps.

    This is used to keep log/ratio metrics numerically stable when χ² is ~0.
    """
    digits = max(int(min_digits), int(mp.dps) // 2)
    return mp.power(10, -digits)

