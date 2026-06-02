from __future__ import annotations

import mpmath as mp
import pytest

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootInputValue, RootProblem, RootUnknown
from root_solving.solver import solve_root_problem
from shared.precision import precision_guard
from shared.uncertainty import UncertainValue


def test_scalar_quadratic_constant_uncertainty_propagates_to_root() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="2"),),
            constants={"C": "4.0"},
            mode="scalar",
            precision=80,
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    root = result.roots[0]
    assert mp.almosteq(root.value, mp.mpf("2"))
    assert root.uncertainty is not None
    assert mp.almosteq(root.uncertainty, mp.mpf("0.05"), rel_eps=mp.mpf("1e-70"))
    assert root.contributions == {"C": mp.mpf("0.05")}
    assert result.jacobian_condition == mp.mpf("1.0")
    assert result.warnings == ()


def test_solver_reuses_expression_system_for_uncertainty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    original = build_root_expression_system

    def counted_build(problem: RootProblem) -> RootExpressionSystem:
        nonlocal calls
        calls += 1
        return original(problem)

    monkeypatch.setattr("root_solving.solver.build_root_expression_system", counted_build)

    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="2"),),
            constants={"C": "4.0"},
            mode="scalar",
            precision=80,
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.roots[0].uncertainty is not None
    assert calls == 1


def test_scalar_zero_jacobian_warns_without_misleading_uncertainty() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="0"),),
            constants={"C": "0.0"},
            mode="scalar",
            precision=80,
        ),
        uncertain_inputs={"C": UncertainValue("0.0", "0.1")},
    )

    root = result.roots[0]
    assert mp.almosteq(root.value, mp.mpf("0"))
    assert root.uncertainty is None
    assert root.contributions == {}
    assert any("Jacobian" in warning or "singular" in warning for warning in result.warnings)


def test_square_system_uncertainty_uses_covariance_diagonal_per_root() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x + y - A", "x - y - B"),
            unknowns=(RootUnknown("x", initial="2"), RootUnknown("y", initial="1")),
            constants={"A": "3.0", "B": "1.0"},
            mode="system",
            precision=80,
        ),
        uncertain_inputs={"A": UncertainValue("3.0", "0.3"), "B": UncertainValue("1.0", "0.4")},
    )

    roots = {root.name: root for root in result.roots}
    assert mp.almosteq(roots["x"].value, mp.mpf("2"))
    assert mp.almosteq(roots["y"].value, mp.mpf("1"))
    assert roots["x"].uncertainty is not None
    assert roots["y"].uncertainty is not None
    assert mp.almosteq(roots["x"].uncertainty, mp.mpf("0.25"), abs_eps=mp.mpf("1e-16"))
    assert mp.almosteq(roots["y"].uncertainty, mp.mpf("0.25"), abs_eps=mp.mpf("1e-16"))
    assert mp.almosteq(roots["x"].contributions["A"], mp.mpf("0.15"), abs_eps=mp.mpf("1e-16"))
    assert mp.almosteq(roots["x"].contributions["B"], mp.mpf("0.2"), abs_eps=mp.mpf("1e-16"))
    assert mp.almosteq(roots["y"].contributions["A"], mp.mpf("0.15"), abs_eps=mp.mpf("1e-16"))
    assert mp.almosteq(roots["y"].contributions["B"], mp.mpf("0.2"), abs_eps=mp.mpf("1e-16"))
    assert result.warnings == ()


def test_ill_conditioning_threshold_allows_condition_just_below_boundary() -> None:
    precision = 80
    with precision_guard(precision):
        threshold = 1 / mp.sqrt(mp.eps)
        alpha = 2 / threshold
        initial_y = 1 / alpha

    result = solve_root_problem(
        _diagonal_condition_problem(alpha, initial_y, precision),
        uncertain_inputs={"A": UncertainValue("1.0", "0.1"), "B": UncertainValue("1.0", "0.1")},
    )

    assert result.jacobian_condition is not None
    with precision_guard(precision):
        assert result.jacobian_condition < 1 / mp.sqrt(mp.eps)
    assert result.warnings == ()
    assert all(root.uncertainty is not None for root in result.roots)


def test_ill_conditioning_threshold_rejects_condition_just_above_boundary() -> None:
    precision = 80
    with precision_guard(precision):
        threshold = 1 / mp.sqrt(mp.eps)
        alpha = mp.mpf("0.5") / threshold
        initial_y = 1 / alpha

    result = solve_root_problem(
        _diagonal_condition_problem(alpha, initial_y, precision),
        uncertain_inputs={"A": UncertainValue("1.0", "0.1"), "B": UncertainValue("1.0", "0.1")},
    )

    assert result.jacobian_condition is not None
    with precision_guard(precision):
        assert result.jacobian_condition > 1 / mp.sqrt(mp.eps)
    assert all(root.uncertainty is None for root in result.roots)
    assert any("ill-conditioned" in warning for warning in result.warnings)


def test_complex_roots_with_uncertain_inputs_warn_without_uncertainty() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 + C",),
            unknowns=(RootUnknown("x", initial="1"),),
            constants={"C": "1.0"},
            mode="polynomial",
            precision=80,
        ),
        uncertain_inputs={"C": UncertainValue("1.0", "0.1")},
    )

    assert all(root.uncertainty is None for root in result.roots)
    assert all(root.contributions == {} for root in result.roots)
    assert any("real-valued roots" in warning for warning in result.warnings)


def _diagonal_condition_problem(alpha: mp.mpf, initial_y: mp.mpf, precision: int) -> RootProblem:
    return RootProblem(
        equations=("x - A", f"{mp.nstr(alpha, 60)}*y - B"),
        unknowns=(RootUnknown("x", initial="1"), RootUnknown("y", initial=mp.nstr(initial_y, 60))),
        known_values=(RootInputValue("A", "1.0"), RootInputValue("B", "1.0")),
        mode="system",
        precision=precision,
    )
