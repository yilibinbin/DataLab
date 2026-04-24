from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import error_propagation


@pytest.mark.parametrize("alias", ["mc", "monte_carlo", "montecarlo", "monte-carlo"])
def test_error_propagation_monte_carlo_method_aliases_are_equivalent(alias: str):
    with mp.workdps(60):
        formula = "A + B"
        variables = ["A", "B"]
        values = [mp.mpf("1.0"), mp.mpf("2.0")]
        sigmas = [mp.mpf("0.1"), mp.mpf("0.2")]

        mean_ref, std_ref = error_propagation(
            formula,
            variables,
            values,
            sigmas,
            method="monte_carlo",
            mc_samples=2000,
            mc_seed=123,
        )
        mean_alias, std_alias = error_propagation(
            formula,
            variables,
            values,
            sigmas,
            method=alias,
            mc_samples=2000,
            mc_seed=123,
        )

        assert mean_alias == mean_ref
        assert std_alias == std_ref


def test_error_propagation_taylor_unknown_method_falls_back_to_taylor():
    with mp.workdps(60):
        formula = "A + B"
        variables = ["A", "B"]
        values = [mp.mpf("1.0"), mp.mpf("2.0")]
        sigmas = [mp.mpf("0.1"), mp.mpf("0.2")]

        mean_taylor, std_taylor = error_propagation(formula, variables, values, sigmas, method="taylor", order=1)
        mean_other, std_other = error_propagation(formula, variables, values, sigmas, method="unknown", order=1)
        assert mean_other == mean_taylor
        assert std_other == std_taylor

