from __future__ import annotations

import mpmath as mp
import pytest
from collections.abc import Callable
from typing import Any

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.batch import solve_root_batch
from root_solving.models import RootProblem, RootResult, RootUncertaintyOptions, RootUnknown
from root_solving.solver import solve_root_problem
from shared.input_normalization import ConstantsState
from shared.uncertainty import UncertainValue


def _quadratic_problem(options: RootUncertaintyOptions) -> RootProblem:
    return RootProblem(
        equations=("x^2 - C",),
        unknowns=(RootUnknown("x", initial="2"),),
        constants={"C": "4.0"},
        mode="scalar",
        precision=80,
        uncertainty_options=options,
    )


def test_uncertainty_method_off_suppresses_uncertainty() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="off")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.roots[0].uncertainty is None
    assert result.roots[0].contributions == {}
    assert result.details["uncertainty_method"] == "off"


def test_uncertainty_method_auto_uses_linear_for_real_roots() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="auto")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert mp.almosteq(result.roots[0].uncertainty, mp.mpf("0.05"), rel_eps=mp.mpf("1e-50"))
    assert result.details["uncertainty_method"] == "linear"


def test_uncertainty_method_reports_skipped_when_linear_cannot_attach() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="0"),),
            constants={"C": "0.0"},
            mode="scalar",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(method="linear"),
        ),
        uncertain_inputs={"C": UncertainValue("0.0", "0.1")},
    )

    assert result.roots[0].uncertainty is None
    assert result.details["uncertainty_method"] == "skipped"


def test_uncertainty_inactive_inputs_leave_details_unchanged() -> None:
    for method in ("linear", "off"):
        result = solve_root_problem(
            RootProblem(
                equations=("x^2 - C",),
                unknowns=(RootUnknown("x", initial="2"),),
                constants={"C": "4.0", "unused": "1.0"},
                mode="scalar",
                precision=80,
                uncertainty_options=RootUncertaintyOptions(method=method),
            ),
            uncertain_inputs={"unused": UncertainValue("1.0", "0.1")},
        )

        assert result.roots[0].uncertainty is None
        assert "uncertainty_method" not in result.details


def test_uncertainty_complex_roots_preserve_real_root_warning() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 + C",),
            unknowns=(RootUnknown("x", initial="1"),),
            constants={"C": "1.0"},
            mode="polynomial",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(method="linear"),
        ),
        uncertain_inputs={"C": UncertainValue("1.0", "0.1")},
    )

    assert all(root.uncertainty is None for root in result.roots)
    assert result.details["uncertainty_method"] == "skipped"
    assert any("real-valued roots" in warning for warning in result.warnings)


def test_uncertainty_method_monte_carlo_is_deterministic_with_seed() -> None:
    options = RootUncertaintyOptions(method="monte_carlo", monte_carlo_samples=400, monte_carlo_seed="42")
    first = solve_root_problem(
        _quadratic_problem(options),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )
    second = solve_root_problem(
        _quadratic_problem(options),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert first.details["uncertainty_method"] == "monte_carlo"
    assert first.roots[0].uncertainty is not None
    assert first.roots[0].uncertainty == second.roots[0].uncertainty
    assert mp.mpf("0.035") < first.roots[0].uncertainty < mp.mpf("0.07")


def test_monte_carlo_reuses_expression_system_without_recursive_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds = 0
    uncertainty_dispatches = 0
    original_build = build_root_expression_system
    import root_solving.solver as solver_module

    original_dispatch: Callable[..., RootResult] = getattr(solver_module, "attach_root_uncertainty")

    def counted_build(problem: RootProblem) -> RootExpressionSystem:
        nonlocal builds
        builds += 1
        return original_build(problem)

    def counted_dispatch(**kwargs: Any) -> RootResult:
        nonlocal uncertainty_dispatches
        uncertainty_dispatches += 1
        return original_dispatch(**kwargs)

    monkeypatch.setattr(solver_module, "build_root_expression_system", counted_build)
    monkeypatch.setattr(solver_module, "attach_root_uncertainty", counted_dispatch)

    result = solve_root_problem(
        _quadratic_problem(
            RootUncertaintyOptions(method="monte_carlo", monte_carlo_samples=8, monte_carlo_seed="11")
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.details["uncertainty_method"] == "monte_carlo"
    assert builds == 1
    assert uncertainty_dispatches == 1


def test_batch_monte_carlo_uses_uncertain_data_columns() -> None:
    constants_state = ConstantsState(enabled=False, rows=(), text="", view="table", numeric_mode="uncertainty")
    batch = solve_root_batch(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2"),),
        data_headers=("A",),
        data_rows=((UncertainValue("4.0", "0.2"),),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        data_text_rows=(("4.0(2)",),),
        uncertainty_options={
            "method": "monte_carlo",
            "monte_carlo_samples": 200,
            "monte_carlo_seed": "9",
        },
    )

    result = batch.rows[0].result
    assert result is not None
    root = result.roots[0]
    assert result.details["uncertainty_method"] == "monte_carlo"
    assert root.uncertainty is not None
    assert root.uncertainty > 0


def test_monte_carlo_reports_skipped_with_first_failure_when_samples_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import root_solving.solver as solver_module

    def fail_sample(*_args: object, **_kwargs: object) -> RootResult:
        raise ValueError("sample solve failed for diagnostic test")

    monkeypatch.setattr(solver_module, "_solve_nominal_inputs", fail_sample)

    result = solve_root_problem(
        _quadratic_problem(
            RootUncertaintyOptions(method="monte_carlo", monte_carlo_samples=8, monte_carlo_seed="12")
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.roots[0].uncertainty is None
    assert result.details["uncertainty_method"] == "skipped"
    assert result.details["uncertainty_requested_method"] == "monte_carlo"
    assert result.details["monte_carlo_failures"] == 8
    assert "diagnostic test" in str(result.details["monte_carlo_first_failure"])
    assert any("fewer than two valid samples" in warning for warning in result.warnings)


def test_monte_carlo_rejects_scan_multiple_without_root_matching() -> None:
    result = solve_root_problem(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="0", lower="-3", upper="3"),),
            constants={"C": "4.0"},
            mode="scan_multiple",
            precision=80,
            uncertainty_options=RootUncertaintyOptions(
                method="monte_carlo",
                monte_carlo_samples=20,
                monte_carlo_seed="1",
            ),
        ),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.details["uncertainty_method"] == "none"
    assert any("Monte Carlo" in warning and "scalar and system" in warning for warning in result.warnings)


def test_second_order_ignores_unused_uncertain_batch_columns() -> None:
    constants_state = ConstantsState(enabled=False, rows=(), text="", view="table", numeric_mode="uncertainty")
    batch = solve_root_batch(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2"),),
        data_headers=("A", "unused"),
        data_rows=((UncertainValue("4.0", "0.2"), UncertainValue("10.0", "1.0")),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        data_text_rows=(("4.0(2)", "10.0(1.0)"),),
        uncertainty_options={"method": "second_order"},
    )

    assert batch.rows[0].failure is None
    result = batch.rows[0].result
    assert result is not None
    root = result.roots[0]
    assert root.uncertainty is not None
    assert result.details["uncertainty_method"] == "second_order"


def test_uncertainty_method_second_order_scalar_reports_bias_and_uncertainty() -> None:
    result = solve_root_problem(
        _quadratic_problem(RootUncertaintyOptions(method="second_order")),
        uncertain_inputs={"C": UncertainValue("4.0", "0.2")},
    )

    assert result.details["uncertainty_method"] == "second_order"
    assert result.roots[0].uncertainty is not None
    assert mp.mpf("0.049") < result.roots[0].uncertainty < mp.mpf("0.052")
    assert "uncertainty_bias" in result.details
