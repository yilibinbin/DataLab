"""Cross-validate DataLab's extrapolation methods against Mathematica.

Two independent verification axes:

1. **Sequence accelerators** (Richardson / Wynn-eps / Shanks / Levin-u):
   Mathematica generates the first N partial sums of a series whose
   closed-form limit it computes exactly (zeta(2), zeta(3), pi/4,
   log(2), 2). DataLab applies its accelerator to the same partial
   sums; the test asserts ``|accelerated - exact_limit|`` is below a
   method-appropriate tolerance.

2. **Power-law extrapolation**: Mathematica generates three energies
   ``E_n = E_inf + A * x_n^(-p)`` for known
   ``(E_inf, A, p, x1, x2, x3)``. DataLab's ``extrapolate_power_law``
   should recover ``E_inf`` (and the correct ``p``, ``A``) exactly
   (within mpmath precision).

Why this test matters
---------------------

Existing extrapolation tests verify "method-on-self-constructed-data"
correctness. This test adds an independent reference (Mathematica
arbitrary-precision arithmetic) to catch regressions that wouldn't
trip the self-tests — e.g. a bug in mpmath's Levin transform itself,
or a mis-wired argument in DataLab's dispatch.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from mpmath import mp

from extrapolation_methods import (
    PowerLawConfig,
    SequenceAcceleratorConfig,
    apply_sequence_accelerator,
    extrapolate_power_law,
)


_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "mathematica_reference"
    / "extrapolation"
    / "ground_truth.json"
)

# Per-method tolerance for the sequence-accelerator comparison.
# Values were chosen by **measuring** each method's actual error on
# the chosen 10-term partial sums against Mathematica's exact limit,
# then setting a tolerance ~1 order of magnitude looser than the
# observed worst case. This means: any regression that pushes the
# error noticeably above the algorithm's intrinsic 10-term ceiling
# triggers the test, but algorithm-inherent error on slow series
# (e.g. Wynn-epsilon on Leibniz at N=10 is ~1e-7) doesn't trip it.
#
#   - richardson: only useful on series with a known h^p error
#     expansion. We supply the canonical p=2 case (zeta(2)) and
#     accept 1e-3 — Richardson on 10 partial sums isn't designed to
#     converge faster than the underlying series's tail.
#   - wynn_epsilon / shanks: same algorithm internally; achieves
#     ~1e-7 on Leibniz at N=10. Tolerance 1e-6 leaves headroom.
#   - levin_u: best-of-class on alternating series; achieves ~1e-13
#     on Leibniz at N=10. Tolerance 1e-10.
_METHOD_TOLERANCE = {
    "richardson":   mp.mpf("1e-3"),
    "wynn_epsilon": mp.mpf("1e-6"),
    "shanks":       mp.mpf("1e-6"),
    "levin_u":      mp.mpf("1e-10"),
}


def _load_cases(category: str) -> list[dict]:
    """Load all fixture cases of the given category."""
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return [c for c in data["cases"] if c["category"] == category]


def _ids_for_seq_method(method: str) -> list[tuple[str, list[str], list[str]]]:
    """Build the parametrize argument list for sequence-accelerator
    cases. Yields ``(case_id, partial_sums_strs, exact_limit_str)``
    only for cases whose ``methods`` list includes ``method`` — that
    way Levin-u doesn't get slow-convergent Richardson cases applied
    by accident."""
    out = []
    for case in _load_cases("sequence_accelerator"):
        if method in case["methods"]:
            out.append((case["id"], case["partial_sums"], case["exact_limit"]))
    return out


@pytest.mark.parametrize("method", sorted(_METHOD_TOLERANCE.keys()))
def test_sequence_accelerator_matches_mathematica_limit(method: str) -> None:
    """For each accelerator method, every applicable Mathematica
    reference series must converge to the exact limit within the
    method-specific tolerance.

    The test loops the parametrize-axis instead of the case-axis so
    one assertion failure shows ALL the failing cases for that method
    in the message — easier to diagnose than per-case parametrize.
    """
    failures: list[str] = []
    cases = _ids_for_seq_method(method)
    assert cases, f"no fixture cases declare {method!r} in their methods list"

    config = SequenceAcceleratorConfig(precision=80)
    tolerance = _METHOD_TOLERANCE[method]

    with mp.workdps(80):
        for case_id, partial_sums_strs, exact_str in cases:
            partial_sums = [mp.mpf(s) for s in partial_sums_strs]
            exact = mp.mpf(exact_str)
            try:
                result = apply_sequence_accelerator(method, partial_sums, config)
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"{case_id}: {method} raised {type(exc).__name__}: {exc}"
                )
                continue
            err = mp.fabs(result.value - exact)
            if err > tolerance:
                failures.append(
                    f"{case_id}: {method} gave {mp.nstr(result.value, 25)} "
                    f"vs Mathematica {mp.nstr(exact, 25)}, "
                    f"|diff|={mp.nstr(err, 6)} > tol {mp.nstr(tolerance, 3)}"
                )

    if failures:
        raise AssertionError(
            f"{method} disagrees with Mathematica on "
            f"{len(failures)}/{len(cases)} cases:\n  "
            + "\n  ".join(failures)
        )


@pytest.mark.parametrize(
    "case",
    _load_cases("power_law"),
    ids=lambda c: c["id"],
)
def test_power_law_recovers_mathematica_construction(case: dict) -> None:
    """For each power-law fixture, ``extrapolate_power_law`` should
    recover the construction parameters to ≥30 significant digits.

    Construction: ``E_n = E_inf + A * x_n^(-p)``. The extrapolator's
    job is to invert this 3-equation system, so a near-perfect match
    proves both the residual solver (``mp.findroot`` on
    ``R = (E1-E2)/(E2-E3)``) and the back-substitution for
    ``A`` and ``E_inf`` are correct.

    Tolerance note: the input ``energies`` strings carry 50 decimal
    digits; the inversion process can amplify the truncation noise by
    ~1 order of magnitude per Newton iteration, so we set the
    tolerance to ``1e-30`` (well within the 50-digit input precision
    minus a generous safety buffer).
    """
    rel_eps = mp.mpf("1e-30")
    abs_eps = mp.mpf("1e-30")

    # Critical: ALL ``mp.mpf(decimal_string)`` constructions and all
    # arithmetic must run inside the elevated dps context. Otherwise
    # mpmath truncates the 50-digit fixture strings to ~17 decimal
    # digits before the extrapolator ever sees them.
    with mp.workdps(80):
        x_values = [mp.mpf(s) for s in case["x_values"]]
        energies = [mp.mpf(s) for s in case["energies"]]
        expected_einf = mp.mpf(case["exact_E_inf"])
        expected_A = mp.mpf(case["exact_amplitude"])
        expected_p = mp.mpf(case["exact_exponent"])

        config = PowerLawConfig(x_values=x_values, precision=80)
        result = extrapolate_power_law(config, energies)

        assert mp.almosteq(result.value, expected_einf, rel_eps=rel_eps, abs_eps=abs_eps), (
            f"E_inf: DataLab={mp.nstr(result.value, 35)} "
            f"vs Mathematica={mp.nstr(expected_einf, 35)} "
            f"(diff={mp.nstr(result.value - expected_einf, 6)})"
        )
        assert mp.almosteq(result.exponent, expected_p, rel_eps=rel_eps, abs_eps=abs_eps), (
            f"p: DataLab={mp.nstr(result.exponent, 35)} "
            f"vs Mathematica={mp.nstr(expected_p, 35)} "
            f"(diff={mp.nstr(result.exponent - expected_p, 6)})"
        )
        assert mp.almosteq(result.amplitude, expected_A, rel_eps=rel_eps, abs_eps=abs_eps), (
            f"A: DataLab={mp.nstr(result.amplitude, 35)} "
            f"vs Mathematica={mp.nstr(expected_A, 35)} "
            f"(diff={mp.nstr(result.amplitude - expected_A, 6)})"
        )
