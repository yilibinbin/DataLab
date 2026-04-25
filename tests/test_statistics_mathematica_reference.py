"""Cross-validate DataLab's statistics computation against Mathematica.

Two distinct modes are exercised:

1. **Arithmetic mean** (sample-based n-1 and population n):
   ``compute_statistics(values, sigmas, "mean_sample"/"mean_population")``.
   Compared against Mathematica's ``Total[xs]/Length[xs]`` and
   ``Sqrt[Variance / N]``.

2. **Inverse-variance weighted mean**:
   ``compute_statistics(values, sigmas, "weighted_sigma")``.
   Compared against Mathematica's
   ``mu = Sum[w_i * x_i] / Sum[w_i]`` with ``w_i = 1/sigma_i^2``,
   and standard error ``1/sqrt(Sum[w_i])``.

Why this test matters
---------------------

Existing ``tests/test_statistics_weighted.py`` does verify the
weighted-mean formula via hand-computed expected values, but only
on three tiny cases. This file extends coverage to:
- non-uniform weights with rational sigmas
- decimal-string inputs that exercise the ``mp.mpf(str)`` parsing
- the n=1 edge case
- both sample and population variance paths
- 30+ digit precision against Mathematica reference (was 1e-40
  in the existing test but only against a hand-computed expected,
  not an independent CAS).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from mpmath import mp

from statistics_utils import compute_statistics


_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "mathematica_reference"
    / "statistics"
    / "ground_truth.json"
)


def _load_cases() -> list[dict]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data["cases"])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_statistics_matches_mathematica(case: dict) -> None:
    """Mean and standard error must match Mathematica to 1e-30.

    The fixture's ``sigmas`` field is ``null`` for unweighted mean
    cases (where the mode is mean_sample / mean_population) and an
    array of decimal strings for the ``weighted_sigma`` cases.
    """
    rel_eps = mp.mpf("1e-30")
    abs_eps = mp.mpf("1e-30")

    with mp.workdps(80):
        values = [mp.mpf(s) for s in case["values"]]
        if case["sigmas"] is None:
            sigmas: list[mp.mpf | None] = [None] * len(values)
        else:
            sigmas = [mp.mpf(s) for s in case["sigmas"]]
        expected_mean = mp.mpf(case["expected_mean"])
        expected_std = mp.mpf(case["expected_std"])
        expected_std_mean = mp.mpf(case["expected_std_mean"])

        result = compute_statistics(values, sigmas, case["mode"])

        actual_mean = mp.mpf(result["mean"])
        actual_std = mp.mpf(result.get("std", mp.mpf("0")))
        actual_std_mean = mp.mpf(result.get("std_mean", mp.mpf("0")))

        assert mp.almosteq(
            actual_mean, expected_mean, rel_eps=rel_eps, abs_eps=abs_eps
        ), (
            f"{case['id']} mean: DataLab={mp.nstr(actual_mean, 35)} "
            f"vs Mathematica={mp.nstr(expected_mean, 35)} "
            f"(diff={mp.nstr(actual_mean - expected_mean, 6)})"
        )

        # std and std_mean both legitimately equal 0 for n=1 cases —
        # the rel_eps is undefined when one side is 0, so fall back
        # to a pure abs_eps check via almosteq's documented behaviour.
        assert mp.almosteq(
            actual_std, expected_std, rel_eps=rel_eps, abs_eps=abs_eps
        ), (
            f"{case['id']} std: DataLab={mp.nstr(actual_std, 35)} "
            f"vs Mathematica={mp.nstr(expected_std, 35)} "
            f"(diff={mp.nstr(actual_std - expected_std, 6)})"
        )
        assert mp.almosteq(
            actual_std_mean, expected_std_mean, rel_eps=rel_eps, abs_eps=abs_eps
        ), (
            f"{case['id']} std_mean: DataLab={mp.nstr(actual_std_mean, 35)} "
            f"vs Mathematica={mp.nstr(expected_std_mean, 35)} "
            f"(diff={mp.nstr(actual_std_mean - expected_std_mean, 6)})"
        )
