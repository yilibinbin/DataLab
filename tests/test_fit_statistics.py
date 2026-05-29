from __future__ import annotations

import mpmath as mp
import pytest

from fitting.statistics import compute_fit_statistics


def test_compute_fit_statistics_empty_input_contract() -> None:
    stats = compute_fit_statistics([], [], None, free_param_count=2)

    assert stats.dof == -2
    for value in (stats.chi2, stats.reduced_chi2, stats.r2, stats.rmse, stats.aic, stats.bic):
        assert mp.isnan(value)


def test_compute_fit_statistics_unweighted_nonempty_values() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        [mp.mpf("0.5"), mp.mpf("-0.25"), mp.mpf("0.75")],
        None,
        free_param_count=1,
    )

    assert stats.dof == 2
    assert stats.chi2 == mp.mpf("0.875")
    assert stats.reduced_chi2 == mp.mpf("0.4375")
    assert stats.rmse == mp.sqrt(mp.mpf("0.875") / 3)
    assert mp.almosteq(stats.r2, mp.mpf("1") - mp.mpf("0.875") / mp.mpf("8"))
    assert not mp.isnan(stats.aic)
    assert not mp.isnan(stats.bic)


def test_compute_fit_statistics_weighted_nonempty_values() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        [mp.mpf("0.5"), mp.mpf("-0.25"), mp.mpf("0.75")],
        [mp.mpf("2"), mp.mpf("1"), mp.mpf("3")],
        free_param_count=1,
    )

    assert stats.dof == 2
    assert stats.chi2 == mp.mpf("2.25")
    assert stats.reduced_chi2 == mp.mpf("1.125")
    assert stats.rmse == mp.sqrt(mp.mpf("2.25") / 6)
    assert not mp.isnan(stats.aic)
    assert not mp.isnan(stats.bic)


def test_compute_fit_statistics_dof_guard_and_constant_target_r2() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("2"), mp.mpf("2")],
        [mp.mpf("0"), mp.mpf("0")],
        None,
        free_param_count=1,
    )

    assert stats.dof == 1
    assert stats.r2 == mp.mpf("1")

    no_dof = compute_fit_statistics(
        [mp.mpf("2"), mp.mpf("2")],
        [mp.mpf("1"), mp.mpf("-1")],
        None,
        free_param_count=2,
    )
    assert no_dof.dof == 0
    assert no_dof.chi2 == mp.mpf("2")
    assert mp.isnan(no_dof.reduced_chi2)
    assert mp.isnan(no_dof.r2)
    assert mp.isnan(no_dof.aic)
    assert mp.isnan(no_dof.bic)


def test_compute_fit_statistics_validates_lengths_and_weights() -> None:
    with pytest.raises(ValueError, match="Residual count"):
        compute_fit_statistics([mp.mpf("1")], [], None, free_param_count=1)

    with pytest.raises(ValueError, match="Weight count"):
        compute_fit_statistics([mp.mpf("1")], [mp.mpf("0")], [], free_param_count=1)

    with pytest.raises(ValueError, match="Weights must be positive"):
        compute_fit_statistics(
            [mp.mpf("1")],
            [mp.mpf("0")],
            [mp.mpf("-1")],
            free_param_count=1,
            validate_weights=True,
        )
