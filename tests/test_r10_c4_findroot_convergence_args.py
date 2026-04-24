"""R10 C4 regression: mp.findroot in hp_fitter must receive tol and maxsteps
scaled to mp.dps, so 'high precision' fitting is not silently capped at 10
Newton iterations.
"""

from __future__ import annotations

from unittest.mock import patch

from mpmath import mp

from fitting import hp_fitter
from fitting.auto_models import AUTO_MODELS, fit_linear_model


def test_findroot_called_with_tol_and_maxsteps_at_high_dps():
    """hp_fitter._solve_seed must pass tol and maxsteps to mp.findroot."""
    # Build a minimal single-free-parameter custom fit via the _solve_seed path
    # by using the public fit_custom_model entry point. We patch mp.findroot and
    # capture its kwargs; call_args inspection confirms the convergence args.
    from fitting.constraints import build_parameter_state
    from fitting.model_parser import build_model_specification

    model = build_model_specification("a * x", ["x"], ["a"])
    state = build_parameter_state({"a": {"initial": 1.0}}, ["a"])

    captured = {"kwargs": [], "args": []}
    real_findroot = mp.findroot

    def spy(*args, **kwargs):
        captured["args"].append(args)
        captured["kwargs"].append(kwargs)
        return real_findroot(*args, **kwargs)

    with patch("fitting.hp_fitter.mp.findroot", spy):
        hp_fitter.fit_custom_model(
            model=model,
            parameter_state=state,
            variable_data={"x": [mp.mpf(1), mp.mpf(2), mp.mpf(3)]},
            target_data=[mp.mpf(2), mp.mpf(4), mp.mpf(6)],
            precision=100,
        )

    assert len(captured["kwargs"]) >= 1, "mp.findroot must have been called"
    # At least ONE call must specify BOTH tol and maxsteps
    saw_convergence_args = any(
        ("tol" in kw) and ("maxsteps" in kw) for kw in captured["kwargs"]
    )
    assert saw_convergence_args, (
        f"mp.findroot was called without tol/maxsteps; at dps=100, mpmath's "
        f"default maxsteps=10 silently caps convergence. "
        f"Observed call kwargs: {captured['kwargs']!r}"
    )


def test_high_precision_linear_fit_converges_to_many_digits():
    """Linear fit on y = 2·x at dps=80 must converge to better than 1e-60."""
    # Use the linear model M1 (handled by fit_linear_model, which does QR — not
    # findroot — but still wraps in precision_guard. This is a downstream
    # sanity check that the overall fitting pipeline respects precision.)
    m1 = AUTO_MODELS[0]
    xs = [mp.mpf(1), mp.mpf(2), mp.mpf(3), mp.mpf(4), mp.mpf(5)]
    ys = [mp.mpf(2) * x for x in xs]
    result = fit_linear_model(
        definition=m1,
        x_data=xs,
        y_data=ys,
        precision=80,
    )
    # b0 should be ~0, b1 should be ~2 to many digits
    b1 = result.params["b1"]
    assert abs(b1 - mp.mpf(2)) < mp.mpf("1e-60"), (
        f"Linear fit at dps=80 gave b1={b1!r}; expected |b1 - 2| < 1e-60. "
        "Convergence is not reaching requested precision."
    )
