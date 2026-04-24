from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import error_propagation


def test_taylor_order2_adds_second_order_contribution():
    # f(x)=x^2 at x=0 has df/dx=0 (order-1 gives 0), but f''(x)=2 adds a non-zero
    # second-order variance term: Var ≈ 1/2 * (2^2 * σ^4) = 2 for σ=1.
    with mp.workdps(60):
        formula = "x**2"
        variables = ["x"]
        values = [mp.mpf("0")]
        sigmas = [mp.mpf("1")]

        value1, sigma1 = error_propagation(formula, variables, values, sigmas, method="taylor", order=1)
        value2, sigma2 = error_propagation(formula, variables, values, sigmas, method="taylor", order=2)

        assert mp.almosteq(value1, mp.mpf("0"))
        assert mp.almosteq(value2, mp.mpf("1"))  # mean correction: E[x^2] = σ^2
        assert mp.almosteq(sigma1, mp.mpf("0"))
        assert mp.almosteq(sigma2, mp.sqrt(2))


def test_taylor_order2_matches_order1_when_hessian_zero():
    with mp.workdps(60):
        formula = "x + y"
        variables = ["x", "y"]
        values = [mp.mpf("1.25"), mp.mpf("-0.75")]
        sigmas = [mp.mpf("0.3"), mp.mpf("0.4")]

        _, sigma1 = error_propagation(formula, variables, values, sigmas, method="taylor", order=1)
        _, sigma2 = error_propagation(formula, variables, values, sigmas, method="taylor", order=2)

        expected = mp.sqrt(sigmas[0] ** 2 + sigmas[1] ** 2)
        assert mp.almosteq(sigma1, expected)
        assert mp.almosteq(sigma2, expected)


def test_monte_carlo_rejects_unsafe_expression():
    with pytest.raises(ValueError) as excinfo:
        error_propagation(
            "__import__('os')",
            ["x"],
            [mp.mpf("1")],
            [mp.mpf("0.1")],
            method="monte_carlo",
            mc_samples=200,
            mc_seed=1,
        )
    text = str(excinfo.value)
    assert ("不支持的函数调用" in text) or ("Unsupported function call" in text)


def test_monte_carlo_mean_std_reasonable_for_linear_case():
    with mp.workdps(60):
        formula = "x"
        variables = ["x"]
        values = [mp.mpf("0.5")]
        sigmas = [mp.mpf("0.2")]

        mean, std = error_propagation(
            formula,
            variables,
            values,
            sigmas,
            method="monte_carlo",
            mc_samples=2000,
            mc_seed=123,
        )

        assert mp.fabs(mean - values[0]) < mp.mpf("0.02")
        assert mp.fabs(std - sigmas[0]) < mp.mpf("0.02")
