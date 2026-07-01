from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import mpmath as mp

from shared.bilingual import _dual_msg
from shared.fitting_uncertainty import (
    FitUncertaintyState as FitUncertaintyState,
    fit_uncertainty_policy as fit_uncertainty_policy,
)
from shared.input_normalization import (
    ConstantsState as ConstantsState,
    constants_rows_to_text as constants_rows_to_text,
    normalize_constants_state as normalize_constants_state,
    parse_constants_text as parse_constants_text,
)


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PARAMETER_FIELDS = ("name", "initial", "fixed", "min", "max")
PARAMETER_PERSISTED_FIELDS = (*PARAMETER_FIELDS, "source")


def coerce_string_rows(
    raw_rows: Any,
    keys: Sequence[str],
    *,
    source: str = "rows",
) -> list[dict[str, str]]:
    if not isinstance(raw_rows, Iterable) or isinstance(raw_rows, (str, bytes, dict)):
        raise ValueError(
            _dual_msg(
                f"{source} 必须是行对象列表。",
                f"{source} must be a list of row objects.",
            )
        )
    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_rows, 1):
        if not isinstance(raw_row, dict):
            raise ValueError(
                _dual_msg(
                    f"{source} 第 {index} 行格式无效。",
                    f"{source} row {index} is malformed.",
                )
            )
        rows.append({key: _string_value(raw_row.get(key)) for key in keys})
    return rows


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


# parse_constants_text and constants_rows_to_text are imported from shared.input_normalization


@dataclass(frozen=True)
class ParameterRowsState:
    rows: tuple[Mapping[str, str], ...]
    orphan_names: frozenset[str] = frozenset()
    constraints_enabled: bool = False

    def persisted_rows(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.rows]

    def compute_rows(self) -> list[dict[str, str]]:
        return [
            dict(row)
            for row in self.rows
            if not row["name"].strip() or row["name"].strip() not in self.orphan_names
        ]

    def compute_config(
        self,
        *,
        validate: bool = True,
        required_names: Sequence[str] | None = None,
    ) -> dict[str, dict[str, str]]:
        config: dict[str, dict[str, str]] = {}
        for row in self.compute_rows():
            name = row["name"].strip()
            values = {key: row[key].strip() for key in PARAMETER_FIELDS if key != "name"}
            if not name and not any(values.values()):
                continue
            if not validate and not name:
                continue
            if not name:
                raise ValueError(_dual_msg("参数名不能为空。", "Parameter name cannot be empty."))
            if not _IDENTIFIER_RE.fullmatch(name):
                raise ValueError(_dual_msg(f"参数名无效：{name}", f"Invalid parameter name: {name}"))
            if name in config:
                raise ValueError(_dual_msg(f"参数名重复：{name}", f"Duplicate parameter name: {name}"))
            active_values = {"initial": values["initial"]}
            if self.constraints_enabled:
                active_values.update(
                    {
                        "fixed": values["fixed"],
                        "min": values["min"],
                        "max": values["max"],
                    }
                )
            if not validate:
                draft_entry = {key: value for key, value in active_values.items() if value}
                if draft_entry:
                    config[name] = draft_entry
                continue
            has_initial = bool(active_values.get("initial"))
            has_fixed = bool(active_values.get("fixed"))
            if not has_initial and not has_fixed:
                raise ValueError(
                    _dual_msg(
                        f"参数 {name} 需要初值或固定值。",
                        f"Parameter {name} needs an initial or fixed value.",
                    )
                )
            validated_entry: dict[str, str] = {}
            for key, value in active_values.items():
                if not value:
                    continue
                try:
                    mp.mpf(value)
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(
                        _dual_msg(
                            f"参数 {name} 的 {key} 无效。",
                            f"Invalid {key} for parameter {name}.",
                        )
                    ) from exc
                validated_entry[key] = value
            config[name] = validated_entry
        if required_names:
            required = [str(name).strip() for name in required_names if str(name).strip()]
            missing = [name for name in required if name not in config]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(
                    _dual_msg(
                        f"缺少参数：{joined}",
                        f"Missing parameters: {joined}",
                    )
                )
            return {name: config[name] for name in required}
        return config


def normalize_parameter_rows(
    rows: Iterable[dict[str, Any]] | dict[str, Any] | None,
    *,
    constraints_enabled: bool,
    orphan_names: Iterable[str] = (),
) -> ParameterRowsState:
    if isinstance(rows, dict):
        clean_rows: list[dict[str, str]] = []
        for name, value in rows.items():
            row_values = value if isinstance(value, dict) else {"initial": value}
            clean_rows.append(
                {
                    "name": str(name),
                    "initial": _string_value(row_values.get("initial")),
                    "fixed": _string_value(row_values.get("fixed")),
                    "min": _string_value(row_values.get("min")),
                    "max": _string_value(row_values.get("max")),
                }
            )
    elif rows is None:
        clean_rows = []
    else:
        clean_rows = coerce_string_rows(rows, PARAMETER_PERSISTED_FIELDS, source="Parameter rows")
    clean_rows = [
        {key: value for key, value in row.items() if key != "source" or value}
        for row in clean_rows
    ]
    return ParameterRowsState(
        rows=_freeze_rows(clean_rows),
        orphan_names=frozenset(str(name).strip() for name in orphan_names if str(name).strip()),
        constraints_enabled=bool(constraints_enabled),
    )


# ConstantsState and normalize_constants_state are imported from shared.input_normalization


@dataclass(frozen=True)
class ParameterInput:
    rows: Iterable[dict[str, Any]] | dict[str, Any] | None = None
    constraints_enabled: bool = False
    orphan_names: Iterable[str] = ()
    required_names: Sequence[str] | None = None


@dataclass(frozen=True)
class ConstantsInput:
    enabled: bool = False
    view: str = "table"
    rows: Iterable[dict[str, Any]] | dict[str, Any] | None = None
    text: str = ""
    numeric_mode: str = "uncertainty"


@dataclass(frozen=True)
class WorkerInputRequest:
    headers: Sequence[str]
    data_rows: Sequence[Sequence[mp.mpf]]
    sigma_rows: Sequence[Sequence[object | None]]
    variable_mapping: Mapping[str, str]
    sigma_column: str | None = None


@dataclass(frozen=True)
class WorkerInputState:
    variable_map: Mapping[str, str]
    variable_data: Mapping[str, tuple[mp.mpf, ...]]
    target_series: tuple[mp.mpf, ...]
    sigma_series: tuple[mp.mpf | None, ...]
    weights: tuple[mp.mpf, ...] | None


@dataclass(frozen=True)
class NormalizedFittingInput:
    model_type: str
    expression: str
    variable_names: tuple[str, ...]
    target_column: str
    parameters: ParameterRowsState
    parameter_config: Mapping[str, Mapping[str, str]]
    constants: ConstantsState
    constants_dict: Mapping[str, str]
    implicit_variable: str = ""
    implicit_equation: str = ""
    output_expression: str = ""
    uncertainty: FitUncertaintyState | None = None
    worker_input: WorkerInputState | None = None


def normalize_fitting_input(
    *,
    model_type: str,
    expression: str,
    variable_names: Sequence[str],
    target_column: str = "",
    implicit_variable: str = "",
    implicit_equation: str = "",
    output_expression: str = "",
    parameters: ParameterInput | None = None,
    constants: ConstantsInput | None = None,
    sigma_values: Sequence[mp.mpf | None] | None = None,
    weighted: bool = False,
    worker_request: WorkerInputRequest | None = None,
    validate: bool = True,
) -> NormalizedFittingInput:
    parameter_input = parameters or ParameterInput()
    constants_input = constants or ConstantsInput()
    parameter_state = normalize_parameter_rows(
        parameter_input.rows,
        constraints_enabled=parameter_input.constraints_enabled,
        orphan_names=parameter_input.orphan_names,
    )
    constants_state = normalize_constants_state(
        enabled=constants_input.enabled,
        view=constants_input.view,
        rows=constants_input.rows,
        text=constants_input.text,
        numeric_mode=constants_input.numeric_mode,
    )
    worker_input = None
    effective_sigmas = list(sigma_values) if sigma_values is not None else None
    if worker_request is not None and target_column:
        resolved_sigmas = normalize_data_uncertainty(
            headers=worker_request.headers,
            rows=worker_request.data_rows,
            sigma_rows=worker_request.sigma_rows,
            target_column=target_column,
            sigma_column=worker_request.sigma_column,
        )
        effective_sigmas = resolved_sigmas
        worker_input = normalize_worker_input(
            headers=worker_request.headers,
            rows=worker_request.data_rows,
            variable_mapping=worker_request.variable_mapping,
            target_column=target_column,
            sigma_values=resolved_sigmas,
            weighted=weighted,
        )
    uncertainty = fit_uncertainty_policy(effective_sigmas, weighted=weighted) if effective_sigmas is not None else None
    parameter_config = parameter_state.compute_config(
        validate=validate,
        required_names=parameter_input.required_names,
    )
    constants_dict = constants_state.compute_dict(validate=validate)
    return NormalizedFittingInput(
        model_type=str(model_type),
        expression=str(expression),
        variable_names=tuple(str(name).strip() for name in variable_names if str(name).strip()),
        target_column=str(target_column or "").strip(),
        implicit_variable=str(implicit_variable or "").strip(),
        implicit_equation=str(implicit_equation or "").strip(),
        output_expression=str(output_expression or "").strip(),
        parameters=parameter_state,
        parameter_config=_freeze_nested_mapping(parameter_config),
        constants=constants_state,
        constants_dict=MappingProxyType(dict(constants_dict)),
        uncertainty=uncertainty,
        worker_input=worker_input,
    )


def _freeze_nested_mapping(values: Mapping[str, Mapping[str, str]]) -> Mapping[str, Mapping[str, str]]:
    return MappingProxyType({key: MappingProxyType(dict(value)) for key, value in values.items()})


def _freeze_rows(rows: Iterable[Mapping[str, str]]) -> tuple[Mapping[str, str], ...]:
    return tuple(MappingProxyType(dict(row)) for row in rows)


def normalize_worker_input(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[mp.mpf]],
    variable_mapping: Mapping[str, str],
    target_column: str,
    sigma_values: Sequence[mp.mpf | None],
    weighted: bool,
) -> WorkerInputState:
    variable_data = {
        str(variable): tuple(_column_series(headers, rows, column))
        for variable, column in variable_mapping.items()
    }
    target_series = tuple(_column_series(headers, rows, target_column))
    uncertainty = fit_uncertainty_policy(sigma_values, weighted=weighted)
    return WorkerInputState(
        variable_map=MappingProxyType({str(key): str(value) for key, value in variable_mapping.items()}),
        variable_data=MappingProxyType(variable_data),
        target_series=target_series,
        sigma_series=tuple(uncertainty.data_sigmas),
        weights=uncertainty.weights,
    )


def _column_series(headers: Sequence[str], rows: Sequence[Sequence[mp.mpf]], column: str) -> list[mp.mpf]:
    if column not in headers:
        raise ValueError(_dual_msg(f"未找到列 {column}。", f"Column not found: {column}."))
    column_index = list(headers).index(column)
    values: list[mp.mpf] = []
    for row_index, row in enumerate(rows, 1):
        if column_index >= len(row):
            raise ValueError(
                _dual_msg(
                    f"第 {row_index} 行缺少列 {column}。",
                    f"Row {row_index} is missing column {column}.",
                )
            )
        values.append(mp.mpf(row[column_index]))
    return values


def normalize_fitting_input_from_widgets(
    *,
    model_type: str,
    expression: str,
    variable_names: Sequence[str],
    parameter_table: Any = None,
    constants_editor: Any = None,
    target_column: str = "",
    required_parameter_names: Sequence[str] | None = None,
    sigma_values: Sequence[mp.mpf | None] | None = None,
    weighted: bool = False,
    validate: bool = True,
) -> NormalizedFittingInput:
    constants_enabled = bool(constants_editor is not None and constants_editor.isChecked())
    return normalize_fitting_input(
        model_type=model_type,
        expression=expression,
        variable_names=variable_names,
        target_column=target_column,
        parameters=ParameterInput(
            rows=parameter_table.rows() if parameter_table is not None else [],
            constraints_enabled=(
                parameter_table.constraints_enabled()
                if parameter_table is not None
                else False
            ),
            orphan_names=(
                parameter_table.orphan_names()
                if parameter_table is not None
                else ()
            ),
            required_names=required_parameter_names,
        ),
        constants=ConstantsInput(
            enabled=constants_enabled,
            view=(
                "text"
                if constants_editor is not None and constants_editor.using_text_view()
                else "table"
            ),
            rows=constants_editor.rows() if constants_editor is not None else None,
            text=constants_editor.raw_text() if constants_editor is not None else "",
            numeric_mode=(
                constants_editor.numeric_mode()
                if constants_editor is not None
                else "uncertainty"
            ),
        ),
        sigma_values=sigma_values,
        weighted=weighted,
        validate=validate,
    )


def normalize_data_uncertainty(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[mp.mpf]],
    sigma_rows: Sequence[Sequence[object | None]],
    target_column: str,
    sigma_column: str | None = None,
    absolute: bool = True,
) -> list[mp.mpf | None]:
    requested_column = (sigma_column or "").strip()
    if requested_column:
        if requested_column not in headers:
            raise ValueError(_dual_msg(f"未找到列 {requested_column}。", f"Column not found: {requested_column}."))
        column_index = list(headers).index(requested_column)
        explicit_sigmas: list[mp.mpf | None] = []
        for row_index, row in enumerate(rows, 1):
            if column_index >= len(row):
                raise ValueError(
                    _dual_msg(
                        f"第 {row_index} 行缺少列 {requested_column}。",
                        f"Row {row_index} is missing column {requested_column}.",
                    )
                )
            sigma = mp.mpf(row[column_index])
            explicit_sigmas.append(mp.fabs(sigma) if absolute else sigma)
        return explicit_sigmas
    if target_column not in headers:
        raise ValueError(_dual_msg(f"未找到列 {target_column}。", f"Column not found: {target_column}."))
    target_index = list(headers).index(target_column)
    resolved: list[mp.mpf | None] = []
    for row_sigmas in sigma_rows:
        if target_index < len(row_sigmas):
            entry = row_sigmas[target_index]
            entry_val = getattr(entry, "uncertainty", entry)
            if entry_val is None:
                resolved.append(None)
                continue
            try:
                sigma = mp.mpf(entry_val)
            except Exception:
                sigma = None
            if sigma is None:
                resolved.append(None)
            elif absolute:
                resolved.append(sigma if sigma and sigma > 0 else None)
            else:
                resolved.append(sigma)
        else:
            resolved.append(None)
    if any(sigma is not None for sigma in resolved):
        return resolved
    lower_headers = [str(header).lower() for header in headers]
    candidate_idx = None
    keywords = ("sigma", "err", "error", "unc", "uncertainty", "Δ")
    target_lower = target_column.lower()
    for idx, name in enumerate(lower_headers):
        if idx == target_index:
            continue
        if name.startswith(target_lower) and any(key in name for key in keywords):
            candidate_idx = idx
            break
    if candidate_idx is None:
        for idx, name in enumerate(lower_headers):
            if idx == target_index:
                continue
            if any(key in name for key in keywords):
                candidate_idx = idx
                break
    if candidate_idx is None:
        return resolved
    detected_sigmas: list[mp.mpf | None] = []
    for row in rows:
        if candidate_idx >= len(row):
            detected_sigmas.append(None)
            continue
        sigma = mp.mpf(row[candidate_idx])
        detected_sigmas.append(mp.fabs(sigma) if absolute else sigma)
    return detected_sigmas
