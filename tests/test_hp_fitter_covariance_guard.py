"""Covariance error guard against a negative variance diagonal (audit F1).

A near-rank-deficient inverse can have a NEGATIVE diagonal (finite-precision
indefiniteness). sqrt of that is a complex mpc, which passes an isnan-only guard
and then crashes combine_error_components ('cannot create mpf from mpc'). The
error must degrade to NaN so the fit surfaces a covariance warning instead.
"""

from __future__ import annotations

from mpmath import mp

from fitting.hp_fitter import _error_from_variance, combine_error_components


def test_error_from_negative_variance_is_nan_not_complex():
    result = _error_from_variance(mp.mpf("-1e-5"))
    assert mp.isnan(result)
    # Must NOT be a complex mpc (the pre-fix behavior).
    assert not isinstance(result, mp.mpc)


def test_error_from_valid_variance_is_sqrt():
    assert _error_from_variance(mp.mpf("4")) == mp.mpf("2")


def test_error_from_nan_and_inf_variance_is_nan():
    assert mp.isnan(_error_from_variance(mp.nan))
    assert mp.isnan(_error_from_variance(mp.inf))


def test_nan_error_does_not_crash_combine_error_components():
    """The NaN degradation flows through error combination without the
    'cannot create mpf from mpc' TypeError the negative-variance path caused."""
    stat = _error_from_variance(mp.mpf("-1e-5"))  # NaN, not mpc
    stat_map, _sys_map, total_map = combine_error_components(
        {"a": mp.mpf("1")}, {"a": stat}, {}
    )
    assert mp.isnan(stat_map["a"])
    assert mp.isnan(total_map["a"])
