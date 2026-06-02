from __future__ import annotations

from collections.abc import Sequence

from root_solving.models import RootBatchResult, RootBatchRowResult, RootUnknown
from root_solving.normalization import normalize_root_problem
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
) -> RootBatchResult:
    clean_equations = tuple(str(equation).strip() for equation in equations if str(equation).strip())
    unknown_rows = _unknown_rows(unknowns)
    normalize_root_problem(
        equations=clean_equations,
        unknown_rows=unknown_rows,
        known_rows=(),
        constants_enabled=constants_state.enabled,
        constants_rows=constants_state.persisted_rows(),
        constants_view=constants_state.view,
        constants_text=constants_state.text,
        mode=mode,
        precision=precision,
    )

    rows = build_data_rows(tuple(data_headers), tuple(data_rows))
    if not rows:
        rows = (ComputationDataRow(index=None),)

    constants = constants_state.compute_dict(validate=True)
    classification = classify_expression_symbols(
        clean_equations,
        SymbolCategories(
            unknowns=tuple(unknown.name for unknown in unknowns),
            data_columns=tuple(data_headers),
            constants=tuple(constants),
        ),
    )
    validate_symbol_classification(classification)

    results: list[RootBatchRowResult] = []
    for row in rows:
        source_values = {name: str(row.values[name]) for name in row.values}
        try:
            known_rows = [{"name": name, "value": value} for name, value in source_values.items()]
            problem, _unused_uncertain = normalize_root_problem(
                equations=clean_equations,
                unknown_rows=unknown_rows,
                known_rows=known_rows,
                constants_enabled=constants_state.enabled,
                constants_rows=constants_state.persisted_rows(),
                constants_view=constants_state.view,
                constants_text=constants_state.text,
                mode=mode,
                precision=precision,
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

    return RootBatchResult(rows=tuple(results), headers=tuple(data_headers))


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
