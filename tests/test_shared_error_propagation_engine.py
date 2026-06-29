from __future__ import annotations

from typing import Any, cast

from mpmath import mp
import pytest


def test_error_propagation_alias_rewrite_is_single_pass() -> None:
    from shared.error_propagation_engine import _apply_aliases

    assert _apply_aliases("x1 + x2", {"x1": "x2", "x2": "B"}) == "x2 + B"


def test_shared_taylor_order2_off_diagonal_hessian_contribution_is_counted_once_per_pair() -> None:
    from shared.error_propagation_engine import error_propagation

    with mp.workdps(60):
        value, sigma, components = cast(
            tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]],
            error_propagation(
                "x*y",
                ["x", "y"],
                [mp.mpf("0"), mp.mpf("0")],
                [mp.mpf("2"), mp.mpf("3")],
                method="taylor",
                order=2,
                return_components=True,
            ),
        )

    assert mp.almosteq(value, mp.mpf("0"))
    assert mp.almosteq(sigma, mp.mpf("6"))
    contribution_by_name = dict(components)
    assert mp.almosteq(contribution_by_name["x"], mp.mpf("18"))
    assert mp.almosteq(contribution_by_name["y"], mp.mpf("18"))


def test_shared_monte_carlo_default_does_not_return_distribution_metadata() -> None:
    from shared.error_propagation_engine import apply_formula_to_data, error_propagation
    from shared.uncertainty import UncertainValue

    with mp.workdps(60):
        direct = error_propagation(
            "x",
            ["x"],
            [mp.mpf("1")],
            [mp.mpf("0.1")],
            method="monte_carlo",
            mc_samples=120,
            mc_seed=7,
        )
        rows = apply_formula_to_data(
            ["x"],
            [[UncertainValue("1", "0.1")]],
            {},
            "x",
            propagation_method="monte_carlo",
            mc_samples=120,
            mc_seed=7,
        )

    assert len(direct) == 2
    assert getattr(rows[0], "monte_carlo_distribution", None) is None


def test_shared_monte_carlo_opt_in_returns_distribution_metadata() -> None:
    from shared.error_propagation_engine import apply_formula_to_data, error_propagation
    from shared.uncertainty import UncertainValue

    with mp.workdps(60):
        direct = cast(
            tuple[mp.mpf, mp.mpf, dict[str, Any]],
            error_propagation(
                "x",
                ["x"],
                [mp.mpf("1")],
                [mp.mpf("0.1")],
                method="monte_carlo",
                mc_samples=120,
                mc_seed=7,
                collect_monte_carlo_distribution=True,
            ),
        )
        rows = apply_formula_to_data(
            ["x"],
            [[UncertainValue("1", "0.1")]],
            {},
            "x",
            propagation_method="monte_carlo",
            mc_samples=120,
            mc_seed=7,
            collect_monte_carlo_distribution=True,
        )

    assert len(direct) == 3
    mean, std, summary = direct
    assert isinstance(summary, dict)
    assert summary["requested_sample_count"] == 120
    assert summary["accepted_sample_count"] == 120
    assert summary["rejected_sample_count"] == 0
    assert summary["finite_sample_count"] == 120
    assert mp.almosteq(mp.mpf(summary["mean"]), mean)
    assert mp.almosteq(mp.mpf(summary["std"]), std)
    assert rows[0].monte_carlo_distribution is not None
    histogram = cast(dict[str, Any], rows[0].monte_carlo_distribution["histogram"])
    assert histogram["counts"]


def test_shared_monte_carlo_distribution_handles_zero_uncertainty_deterministically() -> None:
    from shared.error_propagation_engine import error_propagation

    mean, std, summary = cast(
        tuple[mp.mpf, mp.mpf, dict[str, Any]],
        error_propagation(
            "x",
            ["x"],
            [mp.mpf("3")],
            [mp.mpf("0")],
            method="monte_carlo",
            mc_samples=120,
            mc_seed=7,
            collect_monte_carlo_distribution=True,
        ),
    )

    assert mean == mp.mpf("3")
    assert std == mp.mpf("0")
    assert isinstance(summary, dict)
    assert summary["finite_sample_count"] == 120
    histogram = cast(dict[str, Any], summary["histogram"])
    assert histogram["counts"] == [120]
    assert summary["percentiles"] == {
        "2.5": mp.mpf("3"),
        "50": mp.mpf("3"),
        "97.5": mp.mpf("3"),
    }


def test_shared_error_propagation_checks_cancellation_in_row_and_monte_carlo_loops() -> None:
    from shared.error_propagation_engine import apply_formula_to_data, error_propagation
    from shared.uncertainty import UncertainValue

    row_calls = 0

    def cancel_on_second_row() -> None:
        nonlocal row_calls
        row_calls += 1
        if row_calls >= 2:
            raise RuntimeError("cancelled row loop")

    with pytest.raises(RuntimeError, match="cancelled row loop"):
        apply_formula_to_data(
            ["x"],
            [[UncertainValue("1", "0.1")], [UncertainValue("2", "0.1")]],
            {},
            "x",
            cancellation_checker=cancel_on_second_row,
        )
    assert row_calls >= 2

    mc_calls = 0

    def cancel_during_mc() -> None:
        nonlocal mc_calls
        mc_calls += 1
        if mc_calls >= 3:
            raise RuntimeError("cancelled monte carlo")

    with pytest.raises(RuntimeError, match="cancelled monte carlo"):
        error_propagation(
            "x",
            ["x"],
            [mp.mpf("1")],
            [mp.mpf("0.1")],
            method="monte_carlo",
            mc_samples=300,
            mc_seed=7,
            cancellation_checker=cancel_during_mc,
        )
    assert mc_calls >= 3

    apply_mc_calls = 0

    def cancel_during_apply_mc() -> None:
        nonlocal apply_mc_calls
        apply_mc_calls += 1
        if apply_mc_calls >= 3:
            raise RuntimeError("cancelled apply monte carlo")

    with pytest.raises(RuntimeError, match="cancelled apply monte carlo"):
        apply_formula_to_data(
            ["x"],
            [[UncertainValue("1", "0.1")]],
            {},
            "x",
            propagation_method="monte_carlo",
            mc_samples=300,
            mc_seed=7,
            cancellation_checker=cancel_during_apply_mc,
        )
    assert apply_mc_calls >= 3
