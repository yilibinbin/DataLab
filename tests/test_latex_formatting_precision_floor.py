"""The LaTeX fixed-place formatters must be self-protecting against a low ambient mp.dps.

These formatters run at the AMBIENT mp.dps unless the caller guards. The on-demand TeX rebuild path
(生成 TeX) formats a stashed high-precision result AFTER the run's own precision_guard has closed, so
the ambient dps is the process default (~15) while the requested `places` is 20-200. Without an
internal floor the intermediate mp.power(10, places) / value*factor products carry only ~15 sig
digits and silently corrupt every digit past ~16 (audit A3). `_round_to_places`/`_format_fixed_places`
now floor their working precision to comfortably exceed `places`.
"""

from __future__ import annotations

from mpmath import mp

from datalab_latex.latex_formatting import _format_fixed_places, _round_to_places
from shared.precision import precision_guard


def test_format_fixed_places_is_exact_at_low_ambient_dps() -> None:
    # Compute a 60-digit value under high precision (as a real run would), then format it AFTER the
    # ambient precision has dropped back to the process default — mirroring the on-demand rebuild.
    with precision_guard(60):
        value = mp.sqrt(2)
        reference = _format_fixed_places(value, 50)
    with precision_guard(15):
        low_dps = _format_fixed_places(value, 50)
    assert low_dps == reference
    # And it matches mpmath's own high-precision rendering (no digit corruption past ~16).
    with precision_guard(80):
        assert mp.nstr(mp.sqrt(2), 51, strip_zeros=False) == low_dps


def test_round_to_places_keeps_digits_past_ambient_precision() -> None:
    # Compare the FORMATTED strings (mpf equality is precision-sensitive); the fixed-place text must
    # carry all 40 decimals correctly, not be truncated at ambient ~15.
    with precision_guard(60):
        value = mp.sqrt(3)
    with precision_guard(15):
        rounded_str = _format_fixed_places(_round_to_places(value, 40), 40)
    with precision_guard(80):
        true_str = mp.nstr(mp.sqrt(3), 41, strip_zeros=False)
    assert rounded_str == true_str


def test_format_fixed_places_respects_high_ambient_dps_too() -> None:
    # When the ambient dps already exceeds `places`, the floor must not reduce it — and the value
    # is correctly ROUNDED (pi's 31st digit rounds the 30th up: ...3279|5 -> ...3280).
    with precision_guard(120):
        value = mp.pi
        formatted = _format_fixed_places(value, 30)
    assert formatted == "3.141592653589793238462643383280"
