from __future__ import annotations

import mpmath as mp
import pytest
from typing import Any, cast

from root_solving.models import RootInputValue, RootProblem, RootScanConfig, RootUnknown
from root_solving.solver import (
    _SCIPY_FLOAT_UNSAFE_WARNING,
    _scipy_scalar_secant_second_guess,
    solve_root_problem,
)


def _real_float(value: object) -> float:
    if isinstance(value, complex):
        assert value.imag == 0
        return float(value.real)
    if isinstance(value, mp.mpc):
        assert mp.im(value) == 0
        return float(mp.re(value))
    return float(cast(Any, value))


def test_scalar_bracketed_scipy_solves_quadratic_root() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 4",),
            unknowns=(RootUnknown("x", lower="0", upper="3", initial="1"),),
            precision=16,
        )
    )

    assert result.backend == "scipy"
    assert result.mode == "scalar"
    assert result.details["requested_mode"] == "auto"
    assert result.details["resolved_mode"] == "scalar"
    assert result.roots[0].name == "x"
    assert mp.almosteq(result.roots[0].value, mp.mpf("2"))
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_high_precision_scalar_uses_mpmath_for_sqrt_two() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 2",),
            unknowns=(RootUnknown("x", initial="1.5"),),
            mode="scalar",
            precision=80,
        )
    )

    assert result.backend == "mpmath"
    assert result.mode == "scalar"
    with mp.workdps(80):
        assert mp.almosteq(result.roots[0].value, mp.sqrt(mp.mpf("2")), rel_eps=mp.mpf("1e-70"))
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_scalar_unbracketed_precision_16_uses_scipy_root() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 9",),
            unknowns=(RootUnknown("x", initial="4"),),
            mode="scalar",
            precision=16,
        )
    )

    assert result.backend == "scipy"
    assert result.mode == "scalar"
    assert mp.almosteq(result.roots[0].value, mp.mpf("3"))
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_scalar_scipy_secant_seed_is_float_distinct_for_large_initial_value() -> None:
    initial = mp.mpf("1e30")

    second = _scipy_scalar_secant_second_guess(initial)

    assert second != initial
    assert float(second) != float(initial)


def test_scipy_failure_falls_back_to_mpmath_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import scipy.optimize  # type: ignore[import-untyped]

    def fail_root_scalar(*_args: object, **_kwargs: object) -> object:
        class Failed:
            converged = False
            root = mp.mpf("nan")

        return Failed()

    monkeypatch.setattr(scipy.optimize, "root_scalar", fail_root_scalar)

    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 2",),
            unknowns=(RootUnknown("x", initial="1.5"),),
            mode="scalar",
            precision=16,
        )
    )

    assert result.backend == "mpmath"
    assert result.mode == "scalar"
    assert mp.almosteq(result.roots[0].value, mp.sqrt(mp.mpf("2")), rel_eps=mp.mpf("1e-14"))
    assert "SciPy validation failed; used mpmath fallback." in result.warnings
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_square_system_scipy_solve_records_finite_residual_norm() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x + y - 3", "x - y - 1"),
            unknowns=(RootUnknown("x", initial="1"), RootUnknown("y", initial="1")),
            mode="system",
            precision=16,
        )
    )

    assert result.backend == "scipy"
    assert result.mode == "system"
    assert {root.name: root.value for root in result.roots} == {"x": mp.mpf("2.0"), "y": mp.mpf("1.0")}
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_polynomial_mode_returns_all_roots() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 1",),
            unknowns=(RootUnknown("x", initial="1"),),
            mode="polynomial",
            precision=16,
        )
    )

    assert result.mode == "polynomial"
    roots = sorted(mp.mpf(root.value) for root in result.roots)
    assert roots == [mp.mpf("-1.0"), mp.mpf("1.0")]
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)


def test_scan_multiple_finds_scalar_roots_in_range() -> None:
    problem = RootProblem(
        equations=("x**2 - 4",),
        unknowns=(RootUnknown("x", initial="0", lower="-3", upper="3"),),
        mode="scan_multiple",
        precision=16,
    )

    result = solve_root_problem(problem)

    assert result.backend == "scipy"
    assert result.mode == "scan_multiple"
    values = sorted(round(_real_float(root.value), 6) for root in result.roots)
    assert values == [-2.0, 2.0]
    assert [root.name for root in result.roots] == ["x", "x"]
    assert result.residual_norm is not None
    assert result.residual_norm <= mp.mpf("1e-10")


def test_scan_multiple_rejects_system_shape() -> None:
    problem = RootProblem(
        equations=("x + y", "x - y"),
        unknowns=(RootUnknown("x", initial="1"), RootUnknown("y", initial="1")),
        mode="scan_multiple",
        precision=16,
    )

    with pytest.raises(ValueError, match=r"scan|single|scalar"):
        solve_root_problem(problem)


def test_high_precision_scan_multiple_uses_mpmath() -> None:
    problem = RootProblem(
        equations=("x**2 - 2",),
        unknowns=(RootUnknown("x", initial="0", lower="-2", upper="2"),),
        mode="scan_multiple",
        precision=80,
    )

    result = solve_root_problem(problem)

    assert result.backend == "mpmath"
    with mp.workdps(80):
        values = sorted(mp.mpf(root.value) for root in result.roots)
        assert abs(values[0] + mp.sqrt(2)) < mp.mpf("1e-60")
        assert abs(values[1] - mp.sqrt(2)) < mp.mpf("1e-60")


def test_scan_multiple_does_not_accept_near_zero_false_roots() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x*(x - 1e-12)",),
            unknowns=(RootUnknown("x", lower="0", upper="2e-10"),),
            mode="scan_multiple",
            precision=80,
        )
    )

    with mp.workdps(80):
        values = sorted(mp.mpf(root.value) for root in result.roots)
        assert len(values) == 2
        assert values[0] == 0
        assert abs(values[1] - mp.mpf("1e-12")) < mp.mpf("1e-50")


def test_scan_multiple_refines_small_scale_candidates_before_accepting() -> None:
    problem = RootProblem(
        equations=("x*(x - 1e-11)",),
        unknowns=(RootUnknown("x", lower="-1e-10", upper="1e-10"),),
        mode="scan_multiple",
        precision=16,
        scan_config=RootScanConfig(sample_count=200, max_roots=20),
    )

    result = solve_root_problem(problem)

    values = sorted(mp.mpf(root.value) for root in result.roots)
    assert len(values) == 2
    assert abs(values[0]) <= mp.mpf("1e-12")
    assert abs(values[1] - mp.mpf("1e-11")) <= mp.mpf("1e-12")


def test_scan_multiple_finds_off_grid_even_multiplicity_root() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("(x - 1.003)^2",),
            unknowns=(RootUnknown("x", lower="-2", upper="2"),),
            mode="scan_multiple",
            precision=16,
        )
    )

    values = sorted(round(_real_float(root.value), 6) for root in result.roots)
    assert values == [1.003]


def test_large_scale_scipy_validation_does_not_spuriously_fallback() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x - C",),
            unknowns=(RootUnknown("x", initial="9.9e11"),),
            constants={"C": "1e12"},
            mode="scalar",
            precision=16,
        )
    )

    assert result.backend == "scipy"
    assert result.warnings == ()
    assert result.residual_norm is not None
    assert result.residual_norm <= mp.mpf("1e-10") * mp.mpf("1e12")


def test_tiny_root_scipy_validation_uses_absolute_floor() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x - 1e-14",),
            unknowns=(RootUnknown("x", initial="0"),),
            mode="scalar",
            precision=16,
        )
    )

    assert result.backend == "scipy"
    assert result.warnings == ()
    assert result.residual_norm is not None
    assert result.residual_norm <= mp.mpf("1e-10")


def test_high_precision_polynomial_roots_preserve_mpmath_precision() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 2",),
            unknowns=(RootUnknown("x", initial="1"),),
            mode="polynomial",
            precision=80,
        )
    )

    assert result.backend == "mpmath"
    with mp.workdps(80):
        positive = max(mp.mpf(root.value) for root in result.roots)
        assert abs(positive - mp.sqrt(mp.mpf("2"))) < mp.mpf("1e-70")
    assert result.residual_norm is not None
    assert result.residual_norm < mp.mpf("1e-70")


def test_precision_16_polynomial_falls_back_when_coefficients_exceed_float_fidelity() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x-c",),
            unknowns=(RootUnknown("x"),),
            known_values=(RootInputValue("c", "100000000000000000001"),),
            mode="polynomial",
            precision=16,
        )
    )

    with mp.workdps(80):
        assert result.backend == "mpmath"
        assert abs(result.roots[0].value - mp.mpf("100000000000000000001")) <= mp.mpf("1e5")
        assert result.residual_norm is not None
        assert mp.isfinite(result.residual_norm)
    assert _SCIPY_FLOAT_UNSAFE_WARNING in result.warnings


def test_precision_16_polynomial_rejects_decimal_coefficients_not_exact_in_float() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x - 0.1",),
            unknowns=(RootUnknown("x"),),
            mode="polynomial",
            precision=16,
        )
    )

    assert result.backend == "mpmath"
    assert _SCIPY_FLOAT_UNSAFE_WARNING in result.warnings
    with mp.workdps(30):
        assert abs(result.roots[0].value - mp.mpf("0.1")) < mp.mpf("1e-16")


def test_high_precision_polynomial_complex_roots_remain_finite() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 + 1",),
            unknowns=(RootUnknown("x", initial="1"),),
            mode="polynomial",
            precision=80,
        )
    )

    assert result.backend == "mpmath"
    assert len(result.roots) == 2
    assert any(isinstance(root.value, mp.mpc) for root in result.roots)
    with mp.workdps(80):
        imaginary_parts = sorted(abs(mp.im(root.value)) for root in result.roots)
        assert abs(imaginary_parts[-1] - mp.mpf("1")) < mp.mpf("1e-70")
    assert result.residual_norm is not None
    assert mp.isfinite(result.residual_norm)
    assert result.residual_norm < mp.mpf("1e-70")


def test_high_precision_polynomial_preserves_small_nonzero_imaginary_roots() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - 2e-42*x + 2e-84",),
            unknowns=(RootUnknown("x", initial="0"),),
            mode="polynomial",
            precision=80,
        )
    )

    assert result.backend == "mpmath"
    assert all(isinstance(root.value, mp.mpc) for root in result.roots)
    with mp.workdps(80):
        assert min(abs(mp.im(root.value)) for root in result.roots) > mp.mpf("1e-43")
    assert result.residual_norm is not None
    assert result.residual_norm < mp.mpf("1e-110")


def test_scipy_validation_independent_of_ambient_mpmath_precision() -> None:
    previous = mp.mp.dps
    try:
        outcomes = []
        for ambient_dps in (15, 80):
            mp.mp.dps = ambient_dps
            result = solve_root_problem(
                RootProblem(
                    equations=("x - C",),
                    unknowns=(RootUnknown("x", initial="9.9e11"),),
                    constants={"C": "1e12"},
                    mode="scalar",
                    precision=16,
                )
            )
            outcomes.append((result.backend, result.warnings, str(result.residual_norm)))
    finally:
        mp.mp.dps = previous

    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0] == "scipy"
