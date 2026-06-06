from __future__ import annotations

import mpmath as mp
import pytest

from root_solving.batch import solve_root_batch
from root_solving.expression import build_root_expression_system
from root_solving.models import RootInputValue, RootProblem, RootUnknown
from shared.input_normalization import normalize_constants_state
from shared.uncertainty import parse_uncertainty_format


def test_expression_adapter_keeps_constants_symbolic_for_derivatives() -> None:
    system = build_root_expression_system(
        RootProblem(
            equations=("x^2 - C",),
            unknowns=(RootUnknown("x", initial="2"),),
            constants={"C": "4.0(2)"},
            precision=50,
        )
    )

    assert system.evaluate({"x": mp.mpf("2")}) == mp.mpf("0")
    assert system.derivative_unknown("x", {"x": mp.mpf("2")}) == mp.mpf("4")
    assert system.derivative_input("C", {"x": mp.mpf("2")}) == mp.mpf("-1")


def test_expression_adapter_known_values_share_numeric_and_symbolic_scope() -> None:
    system = build_root_expression_system(
        RootProblem(
            equations=("x - a",),
            unknowns=(RootUnknown("x", initial="1"),),
            known_values=(RootInputValue("a", "1.25(5)"),),
            precision=50,
        )
    )

    assert system.evaluate({"x": mp.mpf("1.25")}) == mp.mpf("0")
    assert system.derivative_input("a", {"x": mp.mpf("1.25")}) == mp.mpf("-1")


def test_expression_scope_uses_data_row_inputs_without_known_value_model() -> None:
    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="1"),),
        data_headers=("A",),
        data_rows=((parse_uncertainty_format("4"),),),
        constants_state=normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty"),
        mode="scalar",
        precision=16,
    )

    assert result.rows[0].failure is None
    assert result.rows[0].result is not None
    assert result.rows[0].result.roots[0].name == "x"


def test_expression_normalization_consistent_for_power_syntaxes() -> None:
    caret = build_root_expression_system(
        RootProblem(equations=("x^2 - 4",), unknowns=(RootUnknown("x", initial="2"),), precision=50)
    )
    mathematica = build_root_expression_system(
        RootProblem(equations=("Power[x, 2] - 4",), unknowns=(RootUnknown("x", initial="2"),), precision=50)
    )

    assert caret.evaluate({"x": mp.mpf("3")}) == mathematica.evaluate({"x": mp.mpf("3")})
    assert caret.derivative_unknown("x", {"x": mp.mpf("3")}) == mathematica.derivative_unknown(
        "x", {"x": mp.mpf("3")}
    )


def test_polynomial_coefficients_for_single_unknown_polynomial() -> None:
    system = build_root_expression_system(
        RootProblem(
            equations=("x^2 - 1",),
            unknowns=(RootUnknown("x", initial="1"),),
            mode="polynomial",
            precision=50,
        )
    )

    assert system.polynomial_coefficients() == (mp.mpf("1"), mp.mpf("0"), mp.mpf("-1"))


def test_missing_unknown_value_raises_clear_value_error() -> None:
    system = build_root_expression_system(
        RootProblem(equations=("x - 1",), unknowns=(RootUnknown("x", initial="1"),), precision=50)
    )

    with pytest.raises(ValueError, match="Missing value for unknown x"):
        system.evaluate({})


def test_missing_constant_scope_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="outside the root scope: C"):
        build_root_expression_system(
            RootProblem(equations=("x - C",), unknowns=(RootUnknown("x", initial="1"),), precision=50)
        )


def test_expression_evaluation_uses_problem_precision_without_leaking_global_dps() -> None:
    previous = mp.mp.dps
    mp.mp.dps = 15
    try:
        system = build_root_expression_system(
            RootProblem(equations=("x + 1e-40",), unknowns=(RootUnknown("x", initial="0"),), precision=80)
        )

        with mp.workdps(80):
            expected = mp.mpf("1e-40")

        assert system.evaluate({"x": "0"}) == expected
        assert mp.mp.dps == 15
    finally:
        mp.mp.dps = previous


def test_expression_rejects_non_finite_unknown_values() -> None:
    system = build_root_expression_system(
        RootProblem(equations=("x - 1",), unknowns=(RootUnknown("x", initial="1"),), precision=50)
    )

    for value in ("nan", "inf", "-inf"):
        with pytest.raises(ValueError, match="finite"):
            system.evaluate({"x": value})


def test_expression_rejects_non_finite_evaluation_results() -> None:
    system = build_root_expression_system(
        RootProblem(equations=("Log(0)",), unknowns=(RootUnknown("x", initial="1"),), precision=50)
    )

    with pytest.raises(ValueError, match="finite"):
        system.evaluate({"x": "1"})


def test_expression_rejects_scope_collisions_at_public_adapter_boundary() -> None:
    problems = (
        RootProblem(
            equations=("x - a",),
            unknowns=(RootUnknown("x", initial="1"),),
            known_values=(RootInputValue("x", "2"),),
            precision=50,
        ),
        RootProblem(
            equations=("x - C",),
            unknowns=(RootUnknown("x", initial="1"),),
            constants={"x": "2"},
            precision=50,
        ),
        RootProblem(
            equations=("x - 1",),
            unknowns=(RootUnknown("x", initial="1"), RootUnknown("x", initial="2")),
            precision=50,
        ),
    )
    for problem in problems:
        with pytest.raises(ValueError, match=r"name collision|Duplicate"):
            build_root_expression_system(problem)


def test_expression_rejects_reserved_names_at_public_adapter_boundary() -> None:
    with pytest.raises(ValueError, match="reserved"):
        build_root_expression_system(
            RootProblem(equations=("Sin - 1",), unknowns=(RootUnknown("Sin", initial="1"),), precision=50)
        )
