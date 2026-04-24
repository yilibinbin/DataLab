from __future__ import annotations

import pytest
from mpmath import mp

from statistics_utils import compute_statistics


def test_mean_sample_vs_population_variance_denominator():
    with mp.workdps(80):
        values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
        sigmas = [None] * len(values)

        sample = compute_statistics(values, sigmas, "mean_sample", use_sample=True)
        population = compute_statistics(values, sigmas, "mean_population", use_sample=True)  # suffix must override

        assert mp.almosteq(sample["mean"], population["mean"])
        assert sample["std"] > population["std"]  # n-1 denominator is larger variance
        # Std. error uses sqrt(n) regardless of sample/population mode in this project.
        assert mp.almosteq(sample["std_mean"], sample["std"] / mp.sqrt(len(values)))
        assert mp.almosteq(population["std_mean"], population["std"] / mp.sqrt(len(values)))


@pytest.mark.parametrize("stats_mode", ["mean_sample", "mean_population", "mean"])
def test_mean_modes_do_not_crash(stats_mode: str):
    with mp.workdps(50):
        values = [mp.mpf("1.0"), mp.mpf("1.5"), mp.mpf("2.0")]
        result = compute_statistics(values, [None] * len(values), stats_mode)
        assert "mean" in result
        assert "std_mean" in result


def test_weighted_variance_toggle_changes_std_for_unequal_sigmas():
    with mp.workdps(80):
        values = [mp.mpf("10"), mp.mpf("12"), mp.mpf("11")]
        sigmas = [mp.mpf("1"), mp.mpf("3"), mp.mpf("1")]

        weighted = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)
        unweighted_var = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=False)

        assert mp.almosteq(weighted["mean"], unweighted_var["mean"])
        assert weighted["std"] != unweighted_var["std"]

