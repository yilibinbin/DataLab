from __future__ import annotations

from mpmath import mp

from data_extrapolation_latex_latest import (
    _auto_central_diff_step,
    _build_symbolic_partials,
    error_propagation,
    numerical_partial_derivative,
)


def test_error_propagation_symbolic_derivative_matches_expected():
    # Use a special function where symbolic derivatives are valuable at high mp.dps.
    with mp.workdps(80):
        formula = "Gamma(x)"
        variables = ["x"]
        values = [mp.mpf("3.5")]
        sigmas = [mp.mpf("1e-20")]

        partials = _build_symbolic_partials(formula, variables)
        assert partials is not None
        assert partials[0] is not None
        deriv = mp.mpf(partials[0](*values))

        result_value, result_sigma = error_propagation(formula, variables, values, sigmas)
        expected_sigma = mp.fabs(deriv) * sigmas[0]

        assert mp.almosteq(result_value, mp.gamma(values[0]))
        assert mp.almosteq(result_sigma, expected_sigma)


def test_error_propagation_falls_back_to_numeric_when_symbolic_unavailable():
    # Sympy keeps d/dx Mod(x, 2) as a Derivative(...) node, so the implementation
    # should fall back to numeric central differences.
    with mp.workdps(50):
        formula = "x % 2"
        variables = ["x"]
        values = [mp.mpf("0.3")]
        sigmas = [mp.mpf("1e-6")]

        partials = _build_symbolic_partials(formula, variables)
        assert partials is not None
        assert partials[0] is None

        _, result_sigma = error_propagation(formula, variables, values, sigmas)
        # For x in (0,2), x % 2 == x, so df/dx == 1.
        assert mp.almosteq(result_sigma, sigmas[0])


def test_auto_step_decreases_with_precision():
    with mp.workdps(30):
        h30 = _auto_central_diff_step(mp.mpf("1"))
    with mp.workdps(90):
        h90 = _auto_central_diff_step(mp.mpf("1"))
    assert h90 < h30


def test_numerical_partial_derivative_auto_step_is_reasonable():
    with mp.workdps(60):
        deriv = numerical_partial_derivative("x**2", ["x"], [mp.mpf("2")], 0, h=None)
        assert mp.almosteq(deriv, mp.mpf("4"), rel_eps=mp.mpf("1e-35"))
