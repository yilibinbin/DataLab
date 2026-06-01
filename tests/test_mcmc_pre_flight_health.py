"""Pre-flight + post-run health checks for MCMC refinement.

Background
----------

In practice (user reported on data_nihe.txt with σ ≈ 1e-19), enabling
MCMC refinement printed a flood of ``RuntimeWarning: invalid value
encountered in scalar subtract`` from emcee's red-blue move kernel
plus ``Too few points to create valid contours`` from corner — the
chain was essentially noise but the user got no clear signal that
the result was unreliable.

This file pins the two safeguards added to ``_attach_mcmc_refinement``:

  1. **Pre-flight check**: sample log_probability at the LSQ best-fit
     and at small perturbations. If every sample is ``-inf``, skip
     the MCMC entirely (it would just be 800 wasted iterations) and
     attach a bilingual warning to ``details["mcmc_warning"]``.

  2. **Post-run health check**: emcee's documented healthy
     acceptance-fraction range is roughly [0.1, 0.7]. Anything below
     0.05 or above 0.85 indicates the chain isn't mixing; surface
     the diagnostic via ``details["mcmc_warning"]``.

Both warnings are bilingual (zh / en) per project convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest


# ``_attach_mcmc_refinement`` lives in app_desktop/workers_core.py.
# We import lazily so a missing PySide6 (e.g. on a headless CI without
# Qt) doesn't tank collection — the test file itself doesn't need Qt.
def _import_target():
    from app_desktop import workers_core

    _attach_mcmc_refinement = getattr(workers_core, "_attach_mcmc_refinement", None)
    if _attach_mcmc_refinement is None:
        pytest.skip("MCMC refinement attachment is not present in the current fitting worker path.")
    return _attach_mcmc_refinement


@dataclass
class _FakeFitResult:
    """Stand-in for ``fitting.hp_fitter.FitResult`` — only the fields
    ``_attach_mcmc_refinement`` actually reads."""

    params: dict[str, float]
    residuals: list[float] = field(default_factory=list)
    fitted_curve: list[float] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeAutoModelResult:
    identifier: str
    label: str
    success: bool
    fit_result: _FakeFitResult


@dataclass
class _FakeSummary:
    best_model: str | None
    _best: _FakeAutoModelResult

    def best(self) -> _FakeAutoModelResult:
        return self._best


@dataclass
class _FakeJob:
    """Minimal AutoFitJob stand-in carrying only the fields MCMC reads."""

    x_series: list[float]
    y_series: list[float]
    refine_with_mcmc: bool = True
    variable_data: dict[str, list[float]] | None = None
    target_series: list[float] | None = None
    sigma_series: list[float | None] | None = None
    weights: list[float] | None = None
    parameter_names: list[str] | None = None
    parameter_config: dict[str, dict[str, object]] | None = None


def _make_summary_with_evaluator(
    evaluator,
    *,
    params: dict[str, float] | None = None,
) -> tuple[_FakeSummary, _FakeJob]:
    """Build a fake (summary, job) pair where ``best().fit_result``
    has the supplied evaluator wired into ``details["evaluator"]``,
    matching what the real ``fit_linear_model`` produces."""
    if params is None:
        params = {"a": 1.0, "b": 2.0}
    fit = _FakeFitResult(
        params=params,
        residuals=[0.01, -0.02, 0.015],
        fitted_curve=[1.0, 2.0, 3.0],
        details={"evaluator": evaluator},
    )
    best = _FakeAutoModelResult("M1", "Linear", True, fit)
    summary = _FakeSummary(best_model="M1", _best=best)
    job = _FakeJob(
        x_series=[1.0, 2.0, 3.0],
        y_series=[1.0, 2.0, 3.0],
    )
    return summary, job


# ---------------------------------------------------------------- pre-flight

def test_mcmc_skipped_when_evaluator_always_returns_nan() -> None:
    """If the LSQ evaluator returns NaN for every sample, MCMC must
    skip entirely and surface a bilingual warning rather than running
    800 doomed iterations."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _bad_evaluator(_params, _x):
        return float("nan")

    summary, job = _make_summary_with_evaluator(_bad_evaluator)

    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        _attach(summary, job)

    # MCMC must NOT have been invoked.
    assert not mock_run.called, "MCMC should be skipped when all log-probs are -inf"
    # Warning surfaced to user-readable details.
    fit = summary.best().fit_result
    assert "mcmc_warning" in fit.details
    msg = fit.details["mcmc_warning"]
    assert "MCMC" in msg
    # Bilingual: zh half + en half.
    assert "病态" in msg or "ill-conditioned" in msg


def test_mcmc_skipped_when_initial_guess_outside_domain() -> None:
    """Models like ``log(x)`` are -inf at x=0 in some parameterisations.
    The pre-flight check must catch this without crashing."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _evaluator_returns_inf(_params, _x):
        return float("inf")

    summary, job = _make_summary_with_evaluator(_evaluator_returns_inf)
    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        _attach(summary, job)
    assert not mock_run.called
    assert "mcmc_warning" in summary.best().fit_result.details


def test_mcmc_pre_flight_does_not_skip_well_conditioned_data() -> None:
    """Sanity: a well-behaved evaluator must NOT trigger the
    skip-with-warning path. The pre-flight check exists to prevent
    wasted runs on pathological data, not to gate every MCMC call."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * x + float(params["b"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator,
        params={"a": 1.0, "b": 0.0},
    )
    job.x_series = [1.0, 2.0, 3.0, 4.0, 5.0]
    job.y_series = [1.0, 2.0, 3.0, 4.0, 5.0]

    # Stub run_mcmc so the test doesn't actually do 800 iterations
    # of real emcee — we only care that it WAS called.
    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        from fitting.mcmc_fitter import MCMCResult
        mock_run.return_value = MCMCResult(
            chain=None, log_prob=None,
            param_names=["a", "b"],
            medians={"a": 1.0, "b": 0.0},
            lo_ci={"a": 0.99, "b": -0.01},
            hi_ci={"a": 1.01, "b": 0.01},
            acceptance_fraction=0.4,  # healthy
        )
        with patch("fitting.mcmc_fitter.render_corner_plot",
                   return_value=b""):
            _attach(summary, job)

    assert mock_run.called, "Well-conditioned data must reach run_mcmc"
    assert "mcmc_warning" not in summary.best().fit_result.details
    # Refinement attached.
    assert "mcmc_refinement" in summary.best().fit_result.details


def test_mcmc_uses_fit_job_variable_data_and_target_series() -> None:
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()
    calls: list[tuple[dict[str, float], object]] = []

    def _good_evaluator(params, observation):
        calls.append((dict(params), observation))
        return float(params["a"]) * float(observation["x"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator,
        params={"a": 1.0},
    )
    job.x_series = []
    job.y_series = []
    job.variable_data = {"x": [1.0, 2.0, 3.0]}
    job.target_series = [1.0, 2.0, 3.0]
    job.parameter_names = ["a"]
    job.parameter_config = {"a": {"initial": "1"}}

    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        from fitting.mcmc_fitter import MCMCResult

        mock_run.return_value = MCMCResult(
            chain=None,
            log_prob=None,
            param_names=["a"],
            medians={"a": 1.0},
            lo_ci={"a": 0.99},
            hi_ci={"a": 1.01},
            acceptance_fraction=0.4,
        )
        with patch("fitting.mcmc_fitter.render_corner_plot", return_value=b""):
            _attach(summary, job)

    assert mock_run.called
    assert calls
    assert all(observation in [{"x": 1.0}, {"x": 2.0}, {"x": 3.0}] for _params, observation in calls)


def test_mcmc_samples_only_free_parameters_from_fit_job_config() -> None:
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * float(x)

    summary, job = _make_summary_with_evaluator(
        _good_evaluator,
        params={"a": 1.0, "fixed_b": 2.0, "derived_c": 3.0},
    )
    job.parameter_names = ["a", "fixed_b", "derived_c"]
    job.parameter_config = {
        "a": {"initial": "1"},
        "fixed_b": {"fixed": "2"},
        "derived_c": {"expr": "a + fixed_b"},
    }

    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        from fitting.mcmc_fitter import MCMCResult

        mock_run.return_value = MCMCResult(
            chain=None,
            log_prob=None,
            param_names=["a"],
            medians={"a": 1.0},
            lo_ci={"a": 0.99},
            hi_ci={"a": 1.01},
            acceptance_fraction=0.4,
        )
        with patch("fitting.mcmc_fitter.render_corner_plot", return_value=b""):
            _attach(summary, job)

    assert mock_run.call_args.args[2] == ["a"]


def test_mcmc_composes_fixed_and_dependent_parameters_for_probability() -> None:
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()
    seen_params: list[dict[str, float]] = []

    def _good_evaluator(params, x):
        seen_params.append(dict(params))
        return float(params["a"] + params["fixed_b"] + params["derived_c"]) * float(x)

    summary, job = _make_summary_with_evaluator(
        _good_evaluator,
        params={"a": 1.0, "fixed_b": 2.0, "derived_c": 3.0},
    )
    job.parameter_names = ["a", "fixed_b", "derived_c"]
    job.parameter_config = {
        "a": {"initial": "1"},
        "fixed_b": {"fixed": "2"},
        "derived_c": {"expr": "a + fixed_b"},
    }
    job.y_series = [6.0, 12.0, 18.0]

    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        from fitting.mcmc_fitter import MCMCResult

        mock_run.return_value = MCMCResult(
            chain=None,
            log_prob=None,
            param_names=["a"],
            medians={"a": 1.0},
            lo_ci={"a": 0.99},
            hi_ci={"a": 1.01},
            acceptance_fraction=0.4,
        )
        with patch("fitting.mcmc_fitter.render_corner_plot", return_value=b""):
            _attach(summary, job)

    assert mock_run.called
    assert seen_params
    assert all(params["fixed_b"] == 2.0 for params in seen_params)
    assert all(params["derived_c"] == params["a"] + 2.0 for params in seen_params)


def test_mcmc_log_probability_uses_weights_and_point_index() -> None:
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()
    point_indices: list[int] = []

    class _IndexedEvaluator:
        def __init__(self) -> None:
            self.index = -1

        def set_implicit_point_index(self, index: int) -> None:
            self.index = index
            point_indices.append(index)

        def __call__(self, params, observation):
            return float(params["a"]) * float(observation["x"])

    summary, job = _make_summary_with_evaluator(_IndexedEvaluator(), params={"a": 1.0})
    job.variable_data = {"x": [1.0, 2.0, 3.0]}
    job.target_series = [1.0, 2.0, 3.0]
    job.parameter_names = ["a"]
    job.parameter_config = {"a": {"initial": "1"}}
    job.weights = [1.0, 4.0, 9.0]

    captured_log_prob = None

    def _capture_run_mcmc(log_probability, *_args, **_kwargs):
        nonlocal captured_log_prob
        captured_log_prob = log_probability
        from fitting.mcmc_fitter import MCMCResult

        return MCMCResult(
            chain=None,
            log_prob=None,
            param_names=["a"],
            medians={"a": 1.0},
            lo_ci={"a": 0.99},
            hi_ci={"a": 1.01},
            acceptance_fraction=0.4,
        )

    with patch("fitting.mcmc_fitter.run_mcmc", side_effect=_capture_run_mcmc):
        with patch("fitting.mcmc_fitter.render_corner_plot", return_value=b""):
            _attach(summary, job)

    assert captured_log_prob is not None
    weighted_lp = captured_log_prob([0.0])
    assert weighted_lp < -1.0
    assert point_indices[:3] == [0, 1, 2]


def test_mcmc_evaluator_internal_type_error_is_not_retried_as_different_arity() -> None:
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()
    calls = 0

    def _broken_evaluator(params, observation):
        nonlocal calls
        calls += 1
        raise TypeError("internal evaluator failure")

    summary, job = _make_summary_with_evaluator(_broken_evaluator, params={"a": 1.0})
    job.variable_data = {"x": [1.0, 2.0, 3.0]}
    job.target_series = [1.0, 2.0, 3.0]
    job.parameter_names = ["a"]
    job.parameter_config = {"a": {"initial": "1"}}

    with patch("fitting.mcmc_fitter.run_mcmc") as mock_run:
        _attach(summary, job)

    assert not mock_run.called
    assert calls == 3
    assert "mcmc_warning" in summary.best().fit_result.details


# ---------------------------------------------------------------- post-run

def test_mcmc_warning_surfaces_low_acceptance_fraction() -> None:
    """An acceptance fraction below 0.05 indicates the chain didn't
    mix — surface this as a warning so the user knows the credible
    intervals can't be trusted at face value."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * x + float(params["b"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator, params={"a": 1.0, "b": 0.0},
    )

    from fitting.mcmc_fitter import MCMCResult
    bad_chain = MCMCResult(
        chain=None, log_prob=None,
        param_names=["a", "b"],
        medians={"a": 1.0, "b": 0.0},
        lo_ci={"a": 0.99, "b": -0.01},
        hi_ci={"a": 1.01, "b": 0.01},
        acceptance_fraction=0.01,  # very low
    )
    with patch("fitting.mcmc_fitter.run_mcmc", return_value=bad_chain):
        with patch("fitting.mcmc_fitter.render_corner_plot",
                   return_value=b""):
            _attach(summary, job)

    fit = summary.best().fit_result
    assert "mcmc_warning" in fit.details
    msg = fit.details["mcmc_warning"]
    assert "0.01" in msg
    assert "接受率" in msg or "acceptance" in msg


def test_mcmc_warning_surfaces_high_acceptance_fraction() -> None:
    """An acceptance fraction above 0.85 means proposal_scale is too
    small — the walkers move too easily, producing a chain that
    doesn't actually explore the posterior."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * x + float(params["b"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator, params={"a": 1.0, "b": 0.0},
    )

    from fitting.mcmc_fitter import MCMCResult
    too_easy = MCMCResult(
        chain=None, log_prob=None,
        param_names=["a", "b"],
        medians={"a": 1.0, "b": 0.0},
        lo_ci={"a": 0.99, "b": -0.01},
        hi_ci={"a": 1.01, "b": 0.01},
        acceptance_fraction=0.95,
    )
    with patch("fitting.mcmc_fitter.run_mcmc", return_value=too_easy):
        with patch("fitting.mcmc_fitter.render_corner_plot",
                   return_value=b""):
            _attach(summary, job)

    fit = summary.best().fit_result
    assert "mcmc_warning" in fit.details
    msg = fit.details["mcmc_warning"]
    assert "0.95" in msg
    assert "proposal_scale" in msg


def test_mcmc_no_warning_for_healthy_acceptance() -> None:
    """A chain in [0.1, 0.7] is the documented healthy range; no
    warning should be attached."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * x + float(params["b"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator, params={"a": 1.0, "b": 0.0},
    )

    from fitting.mcmc_fitter import MCMCResult
    healthy = MCMCResult(
        chain=None, log_prob=None,
        param_names=["a", "b"],
        medians={"a": 1.0, "b": 0.0},
        lo_ci={"a": 0.99, "b": -0.01},
        hi_ci={"a": 1.01, "b": 0.01},
        acceptance_fraction=0.35,
    )
    with patch("fitting.mcmc_fitter.run_mcmc", return_value=healthy):
        with patch("fitting.mcmc_fitter.render_corner_plot",
                   return_value=b""):
            _attach(summary, job)

    fit = summary.best().fit_result
    assert "mcmc_warning" not in fit.details
    assert "mcmc_refinement" in fit.details


def test_mcmc_run_failure_surfaces_warning() -> None:
    """If ``run_mcmc`` raises (numerical instability propagates as
    a Python exception), the existing log-warning code path stays
    but ALSO attaches a user-facing warning to ``details``."""
    pytest.importorskip("emcee", reason="MCMC tests need emcee")

    _attach = _import_target()

    def _good_evaluator(params, x):
        return float(params["a"]) * x + float(params["b"])

    summary, job = _make_summary_with_evaluator(
        _good_evaluator, params={"a": 1.0, "b": 0.0},
    )

    with patch("fitting.mcmc_fitter.run_mcmc",
               side_effect=ValueError("toy failure")):
        _attach(summary, job)

    fit = summary.best().fit_result
    assert "mcmc_warning" in fit.details
    msg = fit.details["mcmc_warning"]
    assert "toy failure" in msg
