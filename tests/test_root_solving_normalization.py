from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import pytest
from mpmath import mp

from root_solving.models import RootProblem
from root_solving.normalization import normalize_root_problem
from root_solving.batch import solve_root_batch
from root_solving.models import RootUnknown
from shared.input_normalization import normalize_constants_state
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS
from shared.uncertainty import UncertainValue, parse_uncertainty_format


def normalize(
    *,
    equations: Iterable[Any] = ("x - 1",),
    unknown_rows: Iterable[dict[str, Any]] = ({"name": "x", "initial": "1"},),
    known_rows: Iterable[dict[str, Any]] = (),
    constants_enabled: bool = False,
    constants_rows: Iterable[dict[str, Any]] | dict[str, Any] | None = (),
    constants_view: str = "table",
    constants_text: str = "",
    mode: str = "auto",
    precision: Any = 16,
) -> tuple[RootProblem, dict[str, UncertainValue]]:
    return normalize_root_problem(
        equations=equations,
        unknown_rows=unknown_rows,
        known_rows=known_rows,
        constants_enabled=constants_enabled,
        constants_rows=constants_rows,
        constants_view=constants_view,
        constants_text=constants_text,
        mode=mode,
        precision=precision,
    )


def test_normalize_root_problem_reuses_uncertainty_constants() -> None:
    problem, uncertain = normalize(
        equations=["x^2 - C"],
        unknown_rows=[{"name": "x", "initial": "2"}],
        constants_enabled=True,
        constants_rows=[{"name": "C", "value": "4.0(2)"}],
    )

    assert problem.equations == ("x^2 - C",)
    assert problem.constants == {"C": "4.0(2)"}
    assert isinstance(uncertain["C"], UncertainValue)
    assert uncertain["C"].value == mp.mpf("4.0")
    assert uncertain["C"].uncertainty == mp.mpf("0.2")


def test_normalize_root_problem_freezes_constants_mapping() -> None:
    problem, _uncertain = normalize(
        equations=["x^2 - C"],
        unknown_rows=[{"name": "x", "initial": "2"}],
        constants_enabled=True,
        constants_rows=[{"name": "C", "value": "4.0(2)"}],
    )

    with pytest.raises(TypeError):
        cast(Any, problem.constants)["C"] = "9.0"


def test_normalize_root_problem_accepts_constants_rows_mapping() -> None:
    problem, uncertain = normalize(
        equations=["x^2 - C"],
        unknown_rows=[{"name": "x", "initial": "2"}],
        constants_enabled=True,
        constants_rows={"C": "4.0(2)"},
    )

    assert problem.constants == {"C": "4.0(2)"}
    assert uncertain["C"].uncertainty == mp.mpf("0.2")


def test_normalize_root_problem_accepts_compact_exponent_notation() -> None:
    _problem, uncertain = normalize(
        equations=["x - CR"],
        unknown_rows=[{"name": "x", "initial": "3.2e9"}],
        constants_enabled=True,
        constants_rows=[{"name": "CR", "value": "3.2898419602500(36)[+9]"}],
        mode="scalar",
        precision=30,
    )

    assert uncertain["CR"].value == mp.mpf("3.2898419602500e9")


def test_normalize_root_problem_rejects_duplicate_unknowns() -> None:
    with pytest.raises(ValueError, match="Duplicate unknown|未知量重复"):
        normalize(unknown_rows=[{"name": "x"}, {"name": "x"}])


def test_normalize_root_problem_ignores_source_only_unknown_rows() -> None:
    problem, _uncertain = normalize(unknown_rows=[{"source": "detected"}])

    assert problem.unknowns == ()


def test_normalize_root_problem_invalid_source_defaults_to_manual_for_non_empty_unknown_row() -> None:
    problem, _uncertain = normalize(unknown_rows=[{"name": "x", "initial": "1", "source": "stale"}])

    assert problem.unknowns[0].source == "manual"


def test_normalize_root_problem_rejects_malformed_unknown_row_payload() -> None:
    with pytest.raises(ValueError, match="Unknown rows row 1 is malformed|Unknown rows 第 1 行格式无效"):
        normalize(unknown_rows=[object()])  # type: ignore[list-item]


def test_normalize_root_problem_uses_localized_identifier_labels() -> None:
    with pytest.raises(ValueError) as exc_info:
        normalize(known_rows=[{"value": "1"}])

    message = str(exc_info.value)
    assert "已知量第 1 行名称不能为空" in message
    assert "known value row 1 name cannot be empty" in message
    assert "known value 第" not in message


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("unknowns", "knowns", "constants", "message"),
    [
        ([{"name": "x"}], [{"name": "x", "value": "1"}], [], "name collision|名称冲突"),
        ([{"name": "x"}], [], [{"name": "x", "value": "1"}], "name collision|名称冲突"),
        ([{"name": "x"}], [{"name": "C", "value": "1"}], [{"name": "C", "value": "2"}], "name collision|名称冲突"),
        ([{"name": "Sin"}], [], [], "reserved|保留"),
    ],
)
def test_normalize_root_problem_rejects_scope_collisions(
    unknowns: list[dict[str, str]],
    knowns: list[dict[str, str]],
    constants: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize(
            equations=["x + C"],
            unknown_rows=unknowns,
            known_rows=knowns,
            constants_enabled=True,
            constants_rows=constants,
        )


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("precision", "expected"),
    [
        (MIN_MPMATH_DPS - 1, MIN_MPMATH_DPS),
        (MAX_MPMATH_DPS + 1, MAX_MPMATH_DPS),
    ],
)
def test_normalize_root_problem_clamps_precision(precision: int, expected: int) -> None:
    problem, _uncertain = normalize(precision=precision)

    assert problem.precision == expected


def test_normalize_root_problem_disabled_constants_do_not_create_uncertain_inputs() -> None:
    problem, uncertain = normalize(
        equations=["x - C"],
        constants_enabled=False,
        constants_rows=[{"name": "C", "value": "4.0(2)"}],
    )

    assert problem.constants == {}
    assert "C" not in uncertain


def test_root_normalization_rejects_data_column_constant_collision() -> None:
    constants_state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "A", "value": "2"}],
        numeric_mode="uncertainty",
    )

    with pytest.raises(ValueError, match="collision|冲突"):
        solve_root_batch(
            equations=("x - A",),
            unknowns=(RootUnknown("x", initial="1"),),
            data_headers=("A",),
            data_rows=((parse_uncertainty_format("1"),),),
            constants_state=constants_state,
            mode="scalar",
            precision=16,
        )
