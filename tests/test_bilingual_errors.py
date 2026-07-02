from __future__ import annotations

import pytest

from statistics_utils import compute_statistics


def test_statistics_errors_are_bilingual():
    with pytest.raises(ValueError) as excinfo:
        compute_statistics([], [], "mean")
    assert " / " in str(excinfo.value)


def test_web_parse_errors_are_bilingual():
    from app_web.logic import _parse_fit_data, _parse_stats_data

    with pytest.raises(ValueError) as excinfo:
        _parse_fit_data("A\n")  # header-only
    assert " / " in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        _parse_stats_data("A\n")  # header-only
    assert " / " in str(excinfo.value)


def test_constraint_parse_errors_are_bilingual():
    import sympy as sp

    from fitting.constraints import _parse_expr_safe

    # ``a @ b`` passes the AST whitelist but fails sympy parse, hitting the
    # "无法解析表达式" ValueError path.
    with pytest.raises(ValueError) as excinfo:
        _parse_expr_safe("a @ b", {"a": sp.Symbol("a"), "b": sp.Symbol("b")})
    assert " / " in str(excinfo.value)


def test_mcmc_validation_errors_are_bilingual():
    from fitting import mcmc_fitter

    if not mcmc_fitter.HAS_EMCEE:
        pytest.skip("emcee not installed; validation errors unreachable")

    def log_prob(_params):
        return 0.0

    # empty initial_guess
    with pytest.raises(ValueError) as excinfo:
        mcmc_fitter.run_mcmc(log_prob, [], [])
    assert " / " in str(excinfo.value)

    # mismatched param_names length
    with pytest.raises(ValueError) as excinfo:
        mcmc_fitter.run_mcmc(log_prob, [1.0, 2.0], ["a"])
    assert " / " in str(excinfo.value)

    # too few walkers
    with pytest.raises(ValueError) as excinfo:
        mcmc_fitter.run_mcmc(log_prob, [1.0], ["a"], n_walkers=1)
    assert " / " in str(excinfo.value)

    # burn-in >= steps
    with pytest.raises(ValueError) as excinfo:
        mcmc_fitter.run_mcmc(
            log_prob, [1.0], ["a"], n_walkers=4, n_steps=10, n_burn_in=10
        )
    assert " / " in str(excinfo.value)
