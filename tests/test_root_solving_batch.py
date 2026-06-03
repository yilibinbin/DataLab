from __future__ import annotations

from typing import Any, cast

import pytest

from root_solving.batch import _deserialize_result_from_task, solve_root_batch
import root_solving.batch as batch_module
from root_solving.models import RootUncertaintyOptions, RootUnknown
from shared.input_normalization import normalize_constants_state
from shared.parallel_config import NestedParallelPolicy, ParallelConfig, ParallelMode, ParallelWorkload
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


def test_deserialize_result_treats_null_backend_and_mode_as_defaults() -> None:
    result = _deserialize_result_from_task(
        {
            "roots": (),
            "backend": None,
            "mode": None,
        }
    )

    assert result.backend == "mpmath"
    assert result.mode == "scalar"


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


def test_batch_parallel_config_uses_inner_allow_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, Any] = {}
    real_executor = batch_module.ParallelMapExecutor

    class SpyExecutor:
        def __init__(self, config: ParallelConfig) -> None:
            observed["config"] = config
            self._delegate = real_executor(ParallelConfig(mode=ParallelMode.SERIAL))

        def map_pure(
            self,
            func: Any,
            items: Any,
            *,
            workload: ParallelWorkload,
            timeout: float | None = None,
        ) -> list[Any]:
            item_list = list(items)
            observed["workload"] = workload
            observed["item_count"] = len(item_list)
            return self._delegate.map_pure(func, item_list, workload=workload, timeout=timeout)

    monkeypatch.setattr(batch_module, "ParallelMapExecutor", SpyExecutor)
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")
    data_rows = tuple((parse_uncertainty_format(str(value)),) for value in (4, 9, 16, 25))

    solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
        data_headers=("A",),
        data_rows=data_rows,
        constants_state=constants_state,
        mode="scalar",
        precision=16,
        parallel_config=ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, reserve_cores=0, min_process_tasks=2),
    )

    config = observed["config"]
    assert isinstance(config, ParallelConfig)
    assert config.nested_policy == NestedParallelPolicy.ALLOW
    assert config.max_workers == 2
    assert config.reserve_cores == 1
    assert config.min_process_tasks == 12
    assert observed["workload"] == ParallelWorkload.CPU_FLOAT
    assert observed["item_count"] == 4


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


def test_batch_scan_multiple_applies_max_roots_scan_config() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="0", lower="-4", upper="4"),),
        data_headers=("A",),
        data_rows=((parse_uncertainty_format("4"),),),
        constants_state=constants_state,
        mode="scan_multiple",
        precision=16,
        scan_config={"max_roots": 1, "sample_count": 100},
    )

    assert result.rows[0].result is not None
    assert len(result.rows[0].result.roots) == 1


def test_batch_forwards_uncertainty_options_to_row_problem() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="", upper=""),),
        data_headers=("A",),
        data_rows=((parse_uncertainty_format("4.0(2)"),),),
        data_text_rows=(("4.0(2)",),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        uncertainty_options={"method": "off"},
    )

    assert result.rows[0].result is not None
    assert result.rows[0].result.roots[0].uncertainty is None


def test_batch_accepts_uncertainty_options_dataclass() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    result = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="", upper=""),),
        data_headers=("A",),
        data_rows=((parse_uncertainty_format("4.0(2)"),),),
        constants_state=constants_state,
        mode="scalar",
        precision=80,
        uncertainty_options=RootUncertaintyOptions(method="taylor", taylor_order=1),
    )

    assert result.rows[0].result is not None
    assert result.rows[0].result.details["uncertainty_method"] == "taylor"
    assert result.rows[0].result.roots[0].uncertainty is not None


def test_batch_text_rows_ignore_empty_headers_without_aborting() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")

    result = solve_root_batch(
        equations=("x - A",),
        unknowns=(RootUnknown("x", initial="1", lower="", upper=""),),
        data_headers=("A", ""),
        data_rows=((parse_uncertainty_format("4"),),),
        data_text_rows=(("4", ""),),
        constants_state=constants_state,
        mode="scalar",
        precision=16,
    )

    assert result.rows[0].failure is None
    assert result.rows[0].source_values == {"A": "4"}


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
