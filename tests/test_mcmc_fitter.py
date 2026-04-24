"""MCMC fitter (Phase 3 #12) — regression tests.

The test suite is conditional on emcee / numpy being installed. The
non-dependent tests pin the public API shape and the graceful-
fallback behaviour.
"""

from __future__ import annotations

import pytest


def test_module_exports_has_emcee_flag():
    from fitting.mcmc_fitter import HAS_EMCEE

    assert isinstance(HAS_EMCEE, bool)


def test_run_mcmc_requires_emcee_when_absent():
    from fitting.mcmc_fitter import HAS_EMCEE, run_mcmc

    if HAS_EMCEE:
        pytest.skip("emcee is installed; absent-path test not applicable")

    with pytest.raises(ModuleNotFoundError, match="emcee"):
        run_mcmc(
            log_probability=lambda p: 0.0,
            initial_guess=[1.0, 1.0],
            param_names=["a", "b"],
        )


def test_run_mcmc_rejects_empty_initial_guess_when_emcee_present():
    pytest.importorskip("emcee")

    from fitting.mcmc_fitter import run_mcmc

    with pytest.raises(ValueError, match="non-empty"):
        run_mcmc(
            log_probability=lambda p: 0.0,
            initial_guess=[],
            param_names=[],
        )


def test_run_mcmc_rejects_mismatched_param_names_when_emcee_present():
    pytest.importorskip("emcee")

    from fitting.mcmc_fitter import run_mcmc

    with pytest.raises(ValueError, match="length"):
        run_mcmc(
            log_probability=lambda p: 0.0,
            initial_guess=[1.0, 2.0, 3.0],
            param_names=["a", "b"],  # wrong length
        )


def test_run_mcmc_rejects_too_few_walkers_when_emcee_present():
    pytest.importorskip("emcee")

    from fitting.mcmc_fitter import run_mcmc

    with pytest.raises(ValueError, match="n_walkers"):
        run_mcmc(
            log_probability=lambda p: 0.0,
            initial_guess=[1.0, 1.0],
            param_names=["a", "b"],
            n_walkers=3,  # below max(4, 2*2)=4
        )


def test_run_mcmc_rejects_burn_in_too_large_when_emcee_present():
    pytest.importorskip("emcee")

    from fitting.mcmc_fitter import run_mcmc

    with pytest.raises(ValueError, match="burn_in"):
        run_mcmc(
            log_probability=lambda p: 0.0,
            initial_guess=[1.0, 1.0],
            param_names=["a", "b"],
            n_steps=100,
            n_burn_in=200,
        )


def test_run_mcmc_recovers_gaussian_posterior_when_emcee_present():
    """For a 2D Gaussian likelihood at known truth, MCMC median
    should match truth within statistical error and 95% CI should
    contain truth."""
    emcee = pytest.importorskip("emcee")
    np = pytest.importorskip("numpy")

    from fitting.mcmc_fitter import run_mcmc

    true_mu = np.array([1.0, 2.0])

    def log_prob(p):
        # Unit-covariance Gaussian centred on truth
        diff = np.array(p) - true_mu
        return -0.5 * float(np.dot(diff, diff))

    result = run_mcmc(
        log_probability=log_prob,
        initial_guess=[0.0, 0.0],
        param_names=["mu_x", "mu_y"],
        n_walkers=32,
        n_steps=2000,
        n_burn_in=500,
    )
    # Median within 0.2 (3σ for a unit Gaussian / sqrt(n_samples))
    assert abs(result.medians["mu_x"] - 1.0) < 0.2
    assert abs(result.medians["mu_y"] - 2.0) < 0.2
    # ±1σ CI must bracket the truth
    assert result.lo_ci["mu_x"] < 1.0 < result.hi_ci["mu_x"]
    assert result.lo_ci["mu_y"] < 2.0 < result.hi_ci["mu_y"]
    # Acceptance fraction in the healthy range
    assert 0.05 < result.acceptance_fraction < 0.95


def test_mcmc_module_is_import_safe_without_emcee():
    """``fitting.mcmc_fitter`` must import cleanly even when emcee
    isn't installed."""
    import importlib
    import fitting.mcmc_fitter as mod

    importlib.reload(mod)
    assert hasattr(mod, "HAS_EMCEE")
    assert hasattr(mod, "run_mcmc")
    assert hasattr(mod, "MCMCResult")
