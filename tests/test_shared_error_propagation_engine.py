from __future__ import annotations

from mpmath import mp


def test_shared_taylor_order2_off_diagonal_hessian_contribution_is_counted_once_per_pair() -> None:
    from shared.error_propagation_engine import error_propagation

    with mp.workdps(60):
        value, sigma, components = error_propagation(
            "x*y",
            ["x", "y"],
            [mp.mpf("0"), mp.mpf("0")],
            [mp.mpf("2"), mp.mpf("3")],
            method="taylor",
            order=2,
            return_components=True,
        )

    assert mp.almosteq(value, mp.mpf("0"))
    assert mp.almosteq(sigma, mp.mpf("6"))
    contribution_by_name = dict(components)
    assert mp.almosteq(contribution_by_name["x"], mp.mpf("18"))
    assert mp.almosteq(contribution_by_name["y"], mp.mpf("18"))

