"""Cross-validate DataLab's Taylor 1st-order error propagation against
Mathematica's symbolic-derivative reference values.

Mathematica computes ``D[f, x_i]`` symbolically, evaluates each
partial derivative at the supplied point, and assembles the
propagated uncertainty via
``sigma_y = Sqrt[Sum_i (∂f/∂x_i)^2 * sigma_i^2]``. The result is the
exact 1st-order Taylor propagation against which DataLab's numerical
approach (Sympy or finite-difference partials, then mpmath sqrt of the
variance sum) is compared.

The 10 fixture cases cover:
- linear and polynomial combinations
- products and quotients (multiplicative error propagation)
- physics-classroom problems (Ohm's law, kinetic energy)
- transcendental compositions (Sin, Exp, Log, Sqrt)

A regression in DataLab's ``error_propagation`` — e.g. a flipped
sign on a partial, a missing variance term, or a precision leak in
the squared-sigma sum — fails this test loudly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from mpmath import mp

from datalab_latex.latex_tables_error_propagation import error_propagation


_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "mathematica_reference"
    / "error_propagation"
    / "ground_truth.json"
)


def _load_cases() -> list[dict]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data["cases"])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_taylor_first_order_matches_mathematica(case: dict) -> None:
    """For every fixture, DataLab's 1st-order Taylor propagation must
    match Mathematica's symbolic propagation to ≥30 significant
    digits (rel_eps=1e-30, abs_eps=1e-30).

    The 50-digit fixture strings exceed mpmath's default 15 dps, so
    ALL ``mp.mpf(decimal_string)`` constructions and the
    ``error_propagation`` call itself run inside ``mp.workdps(80)``.
    """
    formula = case["formula"]
    variables = list(case["variables"])

    rel_eps = mp.mpf("1e-30")
    abs_eps = mp.mpf("1e-30")

    with mp.workdps(80):
        values = [mp.mpf(s) for s in case["values"]]
        sigmas = [mp.mpf(s) for s in case["sigmas"]]
        expected_value = mp.mpf(case["expected_value"])
        expected_sigma = mp.mpf(case["expected_sigma"])

        actual_value, actual_sigma = error_propagation(
            formula, variables, values, sigmas,
            method="taylor", order=1,
        )

        assert mp.almosteq(
            actual_value, expected_value,
            rel_eps=rel_eps, abs_eps=abs_eps,
        ), (
            f"{case['id']} value: DataLab={mp.nstr(actual_value, 35)} "
            f"vs Mathematica={mp.nstr(expected_value, 35)} "
            f"(diff={mp.nstr(actual_value - expected_value, 6)})"
        )
        assert mp.almosteq(
            actual_sigma, expected_sigma,
            rel_eps=rel_eps, abs_eps=abs_eps,
        ), (
            f"{case['id']} sigma: DataLab={mp.nstr(actual_sigma, 35)} "
            f"vs Mathematica={mp.nstr(expected_sigma, 35)} "
            f"(diff={mp.nstr(actual_sigma - expected_sigma, 6)})"
        )
