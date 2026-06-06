from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import (
    RootBatchResult,
    RootBatchRowResult,
    RootProblem,
    RootResult,
    RootScanConfig,
    RootUncertaintyOptions,
    RootUnknown,
    RootValue,
)
from root_solving.normalization import normalize_root_problem_from_context
from root_solving.solver import resolve_root_mode, solve_prepared_root_problem
from shared.computation_inputs import (
    ComputationDataRow,
    SymbolCategories,
    build_data_rows,
    classify_expression_symbols,
    extract_uncertainties,
    validate_symbol_classification,
)
from shared.input_normalization import ConstantsState
from shared.parallel_backend import ParallelMapExecutor
from shared.parallel_config import NestedParallelPolicy, ParallelConfig, ParallelMode, ParallelWorkload
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue, parse_numeric_value


@dataclass(frozen=True)
class _RootBatchTask:
    row_index: int | None
    source_values: dict[str, str]
    nominal_inputs: dict[str, str]
    uncertain_inputs: dict[str, UncertainValue]
    equations: tuple[str, ...]
    unknowns: tuple[RootUnknown, ...]
    constants: dict[str, str]
    scan_config: RootScanConfig
    precision: int
    system: RootExpressionSystem
    mode: str
    uncertainty_options: Mapping[str, object] | RootUncertaintyOptions | None


@dataclass(frozen=True)
class _RootBatchTaskOutput:
    row_index: int | None
    source_values: dict[str, str]
    result: dict[str, object] | None = None
    failure: str | None = None
    warnings: tuple[str, ...] = ()


def solve_root_batch(
    *,
    equations: Sequence[str],
    unknowns: Sequence[RootUnknown],
    data_headers: Sequence[str],
    data_rows: Sequence[Sequence[UncertainValue]],
    constants_state: ConstantsState,
    mode: str,
    precision: int,
    scan_config: Mapping[str, object] | RootScanConfig | None = None,
    data_text_rows: Sequence[Sequence[str]] | None = None,
    uncertainty_options: Mapping[str, object] | RootUncertaintyOptions | None = None,
    parallel_config: ParallelConfig | None = None,
) -> RootBatchResult:
    clean_equations = tuple(str(equation).strip() for equation in equations if str(equation).strip())
    unknown_rows = _unknown_rows(unknowns)
    clean_headers, clean_data_rows = _clean_data_inputs(data_headers, data_rows)

    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        rows = build_data_rows(clean_headers, clean_data_rows)
    if not rows:
        rows = (ComputationDataRow(index=None),)
    text_rows = _data_text_rows(data_headers, data_text_rows)

    constants = constants_state.compute_dict(validate=True)
    classification = classify_expression_symbols(
        clean_equations,
        SymbolCategories(
            unknowns=tuple(unknown.name for unknown in unknowns),
            data_columns=clean_headers,
            constants=tuple(constants),
        ),
    )
    validate_symbol_classification(classification)
    base_problem = normalize_root_problem_from_context(
        equations=clean_equations,
        unknown_rows=unknown_rows,
        row_values={header: "0" for header in clean_headers},
        constants_state=constants_state,
        mode=mode,
        precision=precision,
        scan_config=scan_config,
        uncertainty_options=uncertainty_options,
    )
    base_system = build_root_expression_system(base_problem)
    resolved_mode = resolve_root_mode(base_problem, base_system)
    constant_nominals = {
        name: value
        for name, value in base_system.nominal_inputs.items()
        if name not in clean_headers
    }

    tasks: list[_RootBatchTask] = []
    for row in rows:
        source_values = _source_values(row, text_rows, precision=precision)
        nominal_inputs = {
            name: source_values.get(name, str(value))
            for name, value in row.values.items()
        }
        nominal_inputs.update({name: str(value) for name, value in constant_nominals.items()})
        tasks.append(
            _RootBatchTask(
                row_index=row.index,
                source_values=source_values,
                nominal_inputs=nominal_inputs,
                uncertain_inputs=dict(extract_uncertainties(row, constants_state)),
                equations=base_problem.equations,
                unknowns=base_problem.unknowns,
                constants=dict(base_problem.constants),
                scan_config=base_problem.scan_config,
                precision=base_problem.precision,
                system=base_system,
                mode=resolved_mode,
                uncertainty_options=base_problem.uncertainty_options,
            )
        )

    executor = ParallelMapExecutor(_inner_root_parallel_config(parallel_config))
    outputs = executor.map_pure(
        _solve_root_batch_task,
        tasks,
        workload=ParallelWorkload.CPU_MPMATH if precision > 16 else ParallelWorkload.CPU_FLOAT,
    )
    results = [_task_output_to_row(output) for output in outputs]
    return RootBatchResult(rows=tuple(results), headers=clean_headers)


def _solve_root_batch_task(task: _RootBatchTask) -> _RootBatchTaskOutput:
    source_values = dict(task.source_values)
    try:
        uncertainty_options = _row_uncertainty_options(task.uncertainty_options, task.row_index)
        problem = RootProblem(
            equations=task.equations,
            unknowns=task.unknowns,
            row_values=source_values,
            constants=task.constants,
            mode=task.mode,
            precision=task.precision,
            scan_config=task.scan_config,
        )
        with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
            system = replace(
                task.system,
                nominal_inputs={
                    name: parse_numeric_value(value, precision=problem.precision)
                    for name, value in task.nominal_inputs.items()
                },
            )
            result = solve_prepared_root_problem(
                problem,
                system,
                task.mode,
                uncertain_inputs=task.uncertain_inputs,
                uncertainty_options=uncertainty_options,
            )
            if task.uncertain_inputs:
                result = replace(
                    result,
                    details={
                        **result.details,
                        "plot_uncertain_inputs": _plot_uncertain_inputs_payload(task.uncertain_inputs),
                    },
                )
        return _RootBatchTaskOutput(
            row_index=task.row_index,
            source_values=source_values,
            result=_serialize_result_for_task(result),
            warnings=result.warnings,
        )
    except Exception as exc:  # noqa: BLE001
        return _RootBatchTaskOutput(
            row_index=task.row_index,
            source_values=source_values,
            failure=str(exc),
            warnings=(str(exc),),
        )


def _serialize_result_for_task(result: RootResult) -> dict[str, object]:
    return {
        "roots": tuple(
            {
                "name": root.name,
                "value": root.value,
                "uncertainty": root.uncertainty,
                "contributions": dict(root.contributions),
            }
            for root in result.roots
        ),
        "backend": result.backend,
        "mode": result.mode,
        "residual_norm": result.residual_norm,
        "jacobian_condition": result.jacobian_condition,
        "warnings": tuple(result.warnings),
        "details": dict(result.details),
    }


def _plot_uncertain_inputs_payload(values: Mapping[str, UncertainValue]) -> dict[str, dict[str, str]]:
    return {
        name: {
            "value": str(value.value),
            "uncertainty": str(value.uncertainty),
        }
        for name, value in values.items()
        if mp.isfinite(value.uncertainty) and value.uncertainty > 0
    }


def _task_output_to_row(output: _RootBatchTaskOutput) -> RootBatchRowResult:
    result = None if output.result is None else _deserialize_result_from_task(output.result)
    return RootBatchRowResult(
        row_index=output.row_index,
        source_values=output.source_values,
        result=result,
        failure=output.failure,
        warnings=output.warnings,
    )


def _deserialize_result_from_task(payload: Mapping[str, object]) -> RootResult:
    roots_payload = payload.get("roots", ())
    if not isinstance(roots_payload, Sequence) or isinstance(roots_payload, (str, bytes)):
        roots_payload = ()
    warnings_payload = payload.get("warnings", ())
    if not isinstance(warnings_payload, Sequence) or isinstance(warnings_payload, (str, bytes)):
        warnings_payload = ()
    details_payload = payload.get("details", {})
    details = dict(details_payload) if isinstance(details_payload, Mapping) else {}
    backend_value = payload.get("backend")
    mode_value = payload.get("mode")
    return RootResult(
        roots=tuple(
            RootValue(
                name=str(root_payload.get("name", "")),
                value=root_payload.get("value"),
                uncertainty=root_payload.get("uncertainty"),
                contributions=_mapping_dict(root_payload.get("contributions", {})),
            )
            for root_payload in roots_payload
            if isinstance(root_payload, Mapping)
        ),
        backend=str(backend_value if backend_value is not None else "mpmath"),
        mode=str(mode_value if mode_value is not None else "scalar"),
        residual_norm=payload.get("residual_norm"),
        jacobian_condition=payload.get("jacobian_condition"),
        warnings=tuple(str(warning) for warning in warnings_payload),
        details=details,
    )


def _mapping_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _inner_root_parallel_config(config: ParallelConfig | None) -> ParallelConfig:
    base = config or ParallelConfig()
    if base.mode == ParallelMode.SERIAL:
        return base
    # Root solving runs inside a killable worker process. That boundary
    # increments DataLab's parallel depth, so the batch row fan-out must opt in
    # to one inner process pool; worker count and reserve cores still come from
    # the user's shared parallel settings.
    return replace(
        base,
        reserve_cores=max(0, int(base.reserve_cores)) + 1,
        nested_policy=NestedParallelPolicy.ALLOW,
        min_process_tasks=max(12, int(base.min_process_tasks)),
    )


def _row_uncertainty_options(
    options: Mapping[str, object] | RootUncertaintyOptions | None,
    row_index: int | None,
) -> Mapping[str, object] | RootUncertaintyOptions | None:
    if not options or row_index is None:
        return options
    if isinstance(options, RootUncertaintyOptions):
        seed = str(options.monte_carlo_seed or "").strip()
    else:
        seed = str(options.get("monte_carlo_seed", "") or "").strip()
    if not seed:
        return options
    if isinstance(options, RootUncertaintyOptions):
        return replace(options, monte_carlo_seed=f"{seed}:{row_index}")
    derived = dict(options)
    derived["monte_carlo_seed"] = f"{seed}:{row_index}"
    return derived


def _unknown_rows(unknowns: Sequence[RootUnknown]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "name": unknown.name,
            "initial": unknown.initial,
            "lower": unknown.lower,
            "upper": unknown.upper,
            "source": unknown.source,
        }
        for unknown in unknowns
    )


def _data_text_rows(
    data_headers: Sequence[str],
    data_text_rows: Sequence[Sequence[str]] | None,
) -> tuple[dict[str, str], ...]:
    if data_text_rows is None:
        return ()
    return tuple(
        {
            header: str(cell).strip()
            for raw_header, cell in zip(data_headers, row, strict=False)
            if (header := str(raw_header).strip())
        }
        for row in data_text_rows
    )


def _clean_data_inputs(
    data_headers: Sequence[str],
    data_rows: Sequence[Sequence[UncertainValue]],
) -> tuple[tuple[str, ...], tuple[tuple[UncertainValue, ...], ...]]:
    headers = tuple(str(header).strip() for header in data_headers)
    clean_headers = tuple(header for header in headers if header)
    clean_rows: list[tuple[UncertainValue, ...]] = []
    for index, row in enumerate(data_rows):
        clean_row = tuple(cell for header, cell in zip(headers, row, strict=False) if header)
        if len(clean_row) != len(clean_headers):
            raise ValueError(f"data row {index + 1} has the wrong number of columns")
        clean_rows.append(clean_row)
    return clean_headers, tuple(clean_rows)


def _source_values(
    row: ComputationDataRow,
    text_rows: tuple[dict[str, str], ...],
    *,
    precision: int,
) -> dict[str, str]:
    if row.index is not None and 0 <= row.index < len(text_rows):
        return dict(text_rows[row.index])
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        return {name: str(row.values[name]) for name in row.values}
