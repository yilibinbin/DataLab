"""MCMC Gaussian log-probability scaling (audit finding F2).

The weighted branch must NOT divide the already-weighted chi-square (Σ rᵢ²/σᵢ²)
by rmse² again — that double-scaling corrupted the posterior width and the
reported credible intervals whenever sigma/weights were supplied. The unweighted
branch keeps the /rmse² plug-in variance. This pure function needs no emcee.
"""

from __future__ import annotations

from datalab_core.mcmc_refine import _gaussian_log_probability


def test_weighted_log_probability_is_not_divided_by_rmse_squared():
    residuals_sq = 4.0  # already Σ rᵢ²/σᵢ² when weighted
    rmse = 0.01  # small rmse would blow up the exponent if wrongly divided
    lp = _gaussian_log_probability(residuals_sq, rmse, weighted=True)
    # Correct weighted Gaussian: -0.5 * chi-square, independent of rmse.
    assert lp == -0.5 * residuals_sq
    # And crucially NOT the double-scaled value.
    assert lp != -0.5 * residuals_sq / (rmse**2)


def test_weighted_log_probability_ignores_rmse():
    # Same chi-square with wildly different rmse must give the SAME log-prob.
    assert _gaussian_log_probability(4.0, 0.01, weighted=True) == _gaussian_log_probability(
        4.0, 1000.0, weighted=True
    )


def test_unweighted_log_probability_keeps_rmse_normalization():
    residuals_sq = 4.0  # Σ rᵢ² (weights all 1)
    rmse = 2.0
    lp = _gaussian_log_probability(residuals_sq, rmse, weighted=False)
    assert lp == -0.5 * residuals_sq / (rmse**2)
