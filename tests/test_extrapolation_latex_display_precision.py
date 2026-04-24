from __future__ import annotations

from mpmath import mp

from data_extrapolation_latex_latest import format_uncertainty_display_latex


def test_extrapolation_latex_display_is_stable_under_low_global_precision():
    # Regression for a GUI-only mismatch:
    # - core computation runs at high mp.dps
    # - GUI display happens after mp.dps is restored to a low default
    #
    # The LaTeX formatter must therefore accept high-precision mp.mpf inputs and
    # still format them correctly even when the current global mp.dps is low.
    with mp.workdps(80):
        a = mp.mpf("-4.5202990221721750383611561329370")
        b = mp.mpf("-4.5202990221721753321700006947534")
        c = mp.mpf("-4.5202990221721753325590995935427")
        v = ((c - b) ** 2) / (b - a) + c
        sigma = mp.fabs(v - c)

    with mp.workdps(15):
        text, is_latex = format_uncertainty_display_latex(
            v,
            sigma,
            mp_precision=80,
            latex_digits=16,
            uncertainty_digits=1,
        )

    assert is_latex is True
    assert text == "-4.5202990221721753325596(5)"

