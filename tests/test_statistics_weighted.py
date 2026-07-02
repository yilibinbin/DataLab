from __future__ import annotations

import pytest
from mpmath import mp

from statistics_utils import compute_statistics


def test_weighted_mean_known_case():
    with mp.workdps(80):
        values = [mp.mpf("10"), mp.mpf("12"), mp.mpf("11")]
        sigmas = [mp.mpf("1"), mp.mpf("2"), mp.mpf("1")]

        result = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)

        W = mp.mpf("1") + mp.mpf("0.25") + mp.mpf("1")
        W2 = mp.mpf("1") + mp.mpf("0.0625") + mp.mpf("1")
        expected_mean = mp.mpf("24") / mp.mpf("2.25")
        expected_se = mp.sqrt(mp.mpf("1") / W)

        centered = [values[0] - expected_mean, values[1] - expected_mean, values[2] - expected_mean]
        numer = mp.fsum(
            [
                mp.mpf("1") * centered[0] ** 2,
                mp.mpf("0.25") * centered[1] ** 2,
                mp.mpf("1") * centered[2] ** 2,
            ]
        )
        denom = W - (W2 / W)
        expected_std = mp.sqrt(numer / denom)

        assert mp.almosteq(result["mean"], expected_mean, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result["std_mean"], expected_se, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result["std"], expected_std, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result["effective_n"], (W * W) / W2, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))


def test_weighted_variance_reduces_to_unweighted_when_sigmas_equal():
    with mp.workdps(80):
        values = [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("3.0"), mp.mpf("4.0")]
        sigmas = [mp.mpf("2.0")] * 4

        weighted = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)
        unweighted = compute_statistics(values, [None] * 4, "mean_sample", use_sample=True)

        assert mp.almosteq(weighted["mean"], unweighted["mean"], rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(weighted["std"], unweighted["std"], rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))


def test_weighted_zero_sigma_anchor_conflict_rejected():
    with mp.workdps(80):
        values = [mp.mpf("1.0"), mp.mpf("2.0")]
        sigmas = [mp.mpf("0.0"), mp.mpf("0.0")]
        with pytest.raises(ValueError) as excinfo:
            compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)
        assert "σ=0" in str(excinfo.value)


def test_weighted_effective_n_computed_for_tiny_but_positive_w2():
    """Very large sigmas give tiny (but strictly positive) weights, so W2 is a
    tiny positive number. effective_n = W^2/W2 must still be computed — the guard
    must not treat almosteq(W2, 0) as "cannot compute" (audit R3 D4). For equal
    weights, W^2/W2 == n regardless of the weight magnitude."""
    with mp.workdps(80):
        values = [mp.mpf("10"), mp.mpf("12"), mp.mpf("11")]
        sigmas = [mp.mpf("1e30"), mp.mpf("1e30"), mp.mpf("1e30")]  # weights ~1e-60, W2 ~1e-120 > 0

        result = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)

        assert result["effective_n"] is not None, "effective_n dropped for tiny positive W2"
        assert mp.almosteq(result["effective_n"], mp.mpf("3"), rel_eps=mp.mpf("1e-30"), abs_eps=mp.mpf("1e-30"))
        assert "effective_n" not in result.get("warning_codes", [])
