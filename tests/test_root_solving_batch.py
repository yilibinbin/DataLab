from __future__ import annotations

from typing import Any, cast

import pytest

from root_solving.batch import solve_root_batch
from root_solving.models import RootUnknown
from shared.input_normalization import normalize_constants_state
from shared.uncertainty import parse_uncertainty_format


def _real_float(value: object) -> float:
    if isinstance(value, complex):
        assert value.imag == 0
        return float(value.real)
    return float(cast(Any, value))


def test_empty_data_runs_one_default_row_context() -> None:
    constants_state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "C", "value": "4"}],
        numeric_mode="uncertainty",
    )

    result = solve_root_batch(
        equations=("x**2 - C",),
        unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
        data_headers=(),
        data_rows=(),
        constants_state=constants_state,
        mode="scalar",
        precision=16,
    )

    assert len(result.rows) == 1
    assert result.rows[0].row_index is None
    assert result.rows[0].failure is None
    assert result.rows[0].result is not None
    assert result.rows[0].result.roots[0].name == "x"


def test_non_empty_data_solves_one_problem_per_row() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")
    data_rows = (
        (parse_uncertainty_format("4"),),
        (parse_uncertainty_format("9"),),
    )

    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
        data_headers=("A",),
        data_rows=data_rows,
        constants_state=constants_state,
        mode="scalar",
        precision=16,
    )

    assert [row.row_index for row in result.rows] == [0, 1]
    assert all(row.failure is None for row in result.rows)
    assert [row.source_values["A"] for row in result.rows] == ["4.0", "9.0"]


def test_batch_scan_multiple_returns_multiple_roots_per_row() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")
    data_rows = (
        (parse_uncertainty_format("4"),),
        (parse_uncertainty_format("9"),),
    )

    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="0", lower="-4", upper="4"),),
        data_headers=("A",),
        data_rows=data_rows,
        constants_state=constants_state,
        mode="scan_multiple",
        precision=16,
    )

    values_by_row = [
        sorted(round(_real_float(root.value), 6) for root in row.result.roots)
        for row in result.rows
        if row.result is not None
    ]
    assert values_by_row == [[-2.0, 2.0], [-3.0, 3.0]]


def test_row_failure_does_not_abort_other_rows() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")
    data_rows = (
        (parse_uncertainty_format("4"),),
        (parse_uncertainty_format("9"),),
    )

    result = solve_root_batch(
        equations=("1/(A - 9) + x",),
        unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
        data_headers=("A",),
        data_rows=data_rows,
        constants_state=constants_state,
        mode="scalar",
        precision=16,
    )

    assert result.rows[0].result is not None
    assert result.rows[1].failure


def test_empty_equations_raise_before_row_iteration() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    with pytest.raises(ValueError, match="Equation list cannot be empty"):
        solve_root_batch(
            equations=("",),
            unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
            data_headers=("A",),
            data_rows=((parse_uncertainty_format("4"),),),
            constants_state=constants_state,
            mode="scalar",
            precision=16,
        )


def test_invalid_mode_raises_before_row_iteration() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    with pytest.raises(ValueError, match="Invalid root mode"):
        solve_root_batch(
            equations=("x**2 - A",),
            unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
            data_headers=("A",),
            data_rows=((parse_uncertainty_format("4"),),),
            constants_state=constants_state,
            mode="not-a-mode",
            precision=16,
        )


def test_duplicate_unknown_names_raise_before_row_iteration() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    with pytest.raises(ValueError, match="Duplicate unknown"):
        solve_root_batch(
            equations=("x**2 - A",),
            unknowns=(
                RootUnknown("x", initial="1", lower="", upper=""),
                RootUnknown("x", initial="2", lower="", upper=""),
            ),
            data_headers=("A",),
            data_rows=((parse_uncertainty_format("4"),),),
            constants_state=constants_state,
            mode="system",
            precision=16,
        )
