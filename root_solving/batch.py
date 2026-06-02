from __future__ import annotations

from collections.abc import Mapping, Sequence

from root_solving.models import RootBatchResult, RootBatchRowResult, RootScanConfig, RootUncertaintyOptions, RootUnknown
from root_solving.normalization import normalize_root_problem_from_context
from root_solving.solver import solve_root_problem
from shared.computation_inputs import (
    ComputationDataRow,
    SymbolCategories,
    build_data_rows,
    classify_expression_symbols,
    extract_uncertainties,
    validate_symbol_classification,
)
from shared.input_normalization import ConstantsState
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue


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
    normalize_root_problem_from_context(
        equations=clean_equations,
        unknown_rows=unknown_rows,
        row_values={header: "0" for header in clean_headers},
        constants_state=constants_state,
        mode=mode,
        precision=precision,
        scan_config=scan_config,
        uncertainty_options=uncertainty_options,
    )

    results: list[RootBatchRowResult] = []
    for row in rows:
        source_values = _source_values(row, text_rows, precision=precision)
        try:
            problem = normalize_root_problem_from_context(
                equations=clean_equations,
                unknown_rows=unknown_rows,
                row_values=source_values,
                constants_state=constants_state,
                mode=mode,
                precision=precision,
                scan_config=scan_config,
                uncertainty_options=uncertainty_options,
            )
            result = solve_root_problem(
                problem,
                uncertain_inputs=dict(extract_uncertainties(row, constants_state)),
            )
            results.append(
                RootBatchRowResult(
                    row_index=row.index,
                    source_values=source_values,
                    result=result,
                    warnings=result.warnings,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                RootBatchRowResult(
                    row_index=row.index,
                    source_values=source_values,
                    failure=str(exc),
                    warnings=(str(exc),),
                )
            )

    return RootBatchResult(rows=tuple(results), headers=clean_headers)


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
