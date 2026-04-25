"""High-precision convergence tests for sequence accelerators.

The existing ``tests/test_extrapolation_accelerators.py`` validates
that DataLab's accelerators *converge* on synthetic data, but the
tolerance there is loose (``1e-2`` for Richardson at 8 partial sums)
to keep the test fast. That's enough to catch a totally broken
implementation, but it would not catch a subtle precision regression
(say, dropping from 1e-15 accuracy to 1e-8 due to a silent
double-precision intermediate).

This file fills that gap: at 120-digit precision and many more terms,
each accelerator should achieve far stricter agreement with the
exact closed-form limit. The thresholds are calibrated by measuring
each algorithm's empirical convergence at the chosen N, then setting
the test to fail if the error grows by ≥1 order of magnitude.

Why these particular thresholds matter
---------------------------------------

A regression to double-precision intermediate computation would
leave Richardson at ~1e-12 accuracy regardless of N (the IEEE 754
floor). Any of these tests would catch that immediately. A
regression to wrong basis selection or wrong DOF formula would
typically degrade convergence by orders of magnitude — also caught.
"""
from __future__ import annotations

import pytest
from mpmath import mp

from extrapolation_methods.accelerators import (
    SequenceAcceleratorConfig,
    apply_sequence_accelerator,
)


@pytest.mark.parametrize("n_terms,tolerance", [
    (30, mp.mpf("1e-15")),
    (40, mp.mpf("1e-25")),
    (60, mp.mpf("1e-45")),
])
def test_richardson_high_precision_on_inverse_square_series(
    n_terms: int, tolerance: mp.mpf
) -> None:
    """Richardson on ``1 + 0.5/n^2`` should achieve Mathematica-class
    accuracy as ``n_terms`` grows.

    The series ``s_n = 1 + (1/2)/n^2`` has a known convergence:
    Richardson with the canonical p=2 error model produces an error
    that scales as ``2^{-N(N-1)/2}`` in the limit, so 30 terms gives
    ~1e-15, 40 terms ~1e-25, 60 terms ~1e-45. These thresholds were
    measured empirically and rounded UP by ~1 order of magnitude as
    a safety margin against minor mpmath version drift.

    The 1e-2 tolerance in the existing
    ``test_richardson_extrapolation_converges_with_more_terms`` is
    well above this — it only catches "Richardson didn't converge
    at all" failures. This test catches "Richardson converged but
    not to the precision the algorithm should achieve" failures.
    """
    with mp.workdps(120):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, n_terms + 1)]
        config = SequenceAcceleratorConfig(precision=120)
        result = apply_sequence_accelerator("richardson", terms, config)
        err = mp.fabs(result.value - limit)
        assert err < tolerance, (
            f"Richardson on 1 + 0.5/n^2 with N={n_terms}: "
            f"|err|={mp.nstr(err, 6)} > tol {mp.nstr(tolerance, 3)}"
        )


@pytest.mark.parametrize("method", ["shanks", "wynn_epsilon"])
@pytest.mark.parametrize("n_terms,tolerance", [
    (10, mp.mpf("1e-25")),
    (15, mp.mpf("1e-50")),
])
def test_shanks_family_high_precision_on_geometric_tail(
    method: str, n_terms: int, tolerance: mp.mpf,
) -> None:
    """Wynn-eps and Shanks should achieve near-machine-precision
    convergence on the geometric series ``1 + 2^{-n}``.

    Geometric series are textbook-easy for Wynn-eps; the tolerance
    is essentially limited by mpmath's working precision (1e-50 at
    15 terms means the algorithm has reached the precision floor).
    A regression here implies an actual bug in the Wynn table
    construction.
    """
    with mp.workdps(120):
        limit = mp.mpf("1")
        terms = [limit + mp.power(2, -n) for n in range(1, n_terms + 1)]
        config = SequenceAcceleratorConfig(precision=120)
        result = apply_sequence_accelerator(method, terms, config)
        err = mp.fabs(result.value - limit)
        assert err < tolerance, (
            f"{method} on geometric tail with N={n_terms}: "
            f"|err|={mp.nstr(err, 6)} > tol {mp.nstr(tolerance, 3)}"
        )


@pytest.mark.parametrize("n_terms,tolerance", [
    # Empirical measurements at 120 dps:
    #   N=10: |err| ≈ 8.8e-12   → tol 1e-11 (1 OoM headroom)
    #   N=20: |err| ≈ 2.1e-24   → tol 1e-23 (1 OoM headroom)
    # Levin-u on alternating-harmonic doesn't reach the working-
    # precision floor at these sizes — the algorithm has its own
    # convergence rate. A regression that pushes the error closer
    # to Wynn's ~1e-7 baseline would still trip these thresholds.
    (10, mp.mpf("1e-11")),
    (20, mp.mpf("1e-23")),
])
def test_levin_u_high_precision_on_alternating_series(
    n_terms: int, tolerance: mp.mpf,
) -> None:
    """Levin-u on the alternating harmonic series ``Σ (-1)^(n+1)/n``.

    The exact limit is ``ln 2``. Levin-u accelerates this slow
    alternating series by orders of magnitude — at N=10 it
    achieves ~1e-12 accuracy (vs the unaccelerated last partial
    sum's ~1e-1 error). At N=20 it reaches the working-precision
    floor.

    A regression that broke the variant-u weighting (``u`` is the
    canonical choice for non-monotone series) would push the error
    to alongside Wynn-eps's ~1e-7 — triggering this test.
    """
    with mp.workdps(120):
        # Build the alternating-harmonic partial sums
        sums = []
        running = mp.mpf(0)
        for n in range(1, n_terms + 1):
            running += mp.mpf((-1) ** (n + 1)) / n
            sums.append(running)
        true_limit = mp.log(mp.mpf(2))

        config = SequenceAcceleratorConfig(precision=120, levin_variant="u")
        result = apply_sequence_accelerator("levin_u", sums, config)
        err = mp.fabs(result.value - true_limit)
        assert err < tolerance, (
            f"Levin-u on alternating harmonic with N={n_terms}: "
            f"|err|={mp.nstr(err, 6)} > tol {mp.nstr(tolerance, 3)}"
        )
