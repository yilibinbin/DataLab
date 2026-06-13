from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import mpmath as mp

from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import numeric_payload_tree, numeric_to_payload_string, request_digit_hint
from .parallel_options import normalize_parallel_options
from .results import ResultEnvelope, ResultKind, ResultStatus
from .session import check_cancelled
from .table_payload import normalize_headers, normalize_numeric_rows
from shared.fitting_engine import (
    DirectFitInput,
    deserialize_fit_result,
    execute_direct_fit,
    serialize_fit_result,
)
from shared.precision import precision_guard


_PARAMETER_FIELDS = ("initial", "fixed", "min", "max", "expr")
DEFAULT_FITTING_PRECISION_DIGITS = 80


def build_fitting_request(
    *,
    model_type: str,
    headers: Sequence[str],
    data_rows: Sequence[Sequence[Any]],
    variable_map: Mapping[str, str],
    target_column: str,
    model_expr: str = "",
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    sigma_series: Sequence[Any | None] | None = None,
    parameter_config: Mapping[str, Mapping[str, Any]] | None = None,
    parameter_names: Sequence[str] | None = None,
    template_expr: str | None = None,
    template_params: Mapping[str, Any] | None = None,
    poly_degree: int = 0,
    inverse_min: int = 1,
    inverse_max: int = 3,
    pade_m: int = 1,
    pade_n: int = 1,
    auto_identifier: str | None = None,
    weighted: bool = False,
    label: str = "",
    is_multidim: bool | None = None,
    implicit_definition: Mapping[str, Any] | object | None = None,
    timeout_seconds: Any | None = None,
    custom_constants: Mapping[str, Any] | None = None,
    weights: Sequence[Any | None] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    parallel: Mapping[str, Any] | None = None,
    request_id: str = "fitting",
) -> ComputeJobRequest:
    """Build a string-only fitting request from already-normalized inputs.

    This is the Phase 2 request boundary. Direct non-subprocess fitting
    execution is handled by ``run_fitting``; self-consistent subprocess
    cancellation, plotting, and LaTeX output stay in adapter layers.
    """

    digit_hint = request_digit_hint(precision_digits)
    normalized_headers = normalize_headers(headers)
    normalized_rows = normalize_numeric_rows(
        data_rows,
        headers=normalized_headers,
        digit_hint=digit_hint,
    )
    normalized_sigmas = _normalize_sigma_rows(
        sigma_rows,
        headers=normalized_headers,
        row_count=len(normalized_rows),
        digit_hint=digit_hint,
    )
    normalized_variable_map = _normalize_variable_map(variable_map, headers=normalized_headers)
    normalized_target = _normalize_column_name(
        target_column,
        field_name="target_column",
        headers=normalized_headers,
    )
    column_index = {header: index for index, header in enumerate(normalized_headers)}
    variable_data = {
        variable: [row[column_index[column]] for row in normalized_rows]
        for variable, column in normalized_variable_map.items()
    }
    target_index = column_index[normalized_target]
    target_series = [row[target_index] for row in normalized_rows]
    normalized_sigma_series = _normalize_optional_numeric_sequence(
        sigma_series,
        field_name="sigma_series",
        expected_length=len(normalized_rows),
        digit_hint=digit_hint,
    )
    if normalized_sigma_series is None:
        normalized_sigma_series = [_sigma_series_value(row[target_index]) for row in normalized_sigmas]
    primary_variable = "x" if "x" in variable_data else next(iter(variable_data))
    parameter_payload = _normalize_parameter_config(parameter_config or {}, digit_hint=digit_hint)
    return ComputeJobRequest(
        mode=JobMode.FITTING,
        inputs={
            "model_type": _required_text(model_type, field_name="model_type"),
            "headers": normalized_headers,
            "data_rows": normalized_rows,
            "sigma_rows": normalized_sigmas,
            "x_series": list(variable_data[primary_variable]),
            "y_series": target_series,
            "sigma_series": normalized_sigma_series,
            "weights": _normalize_optional_numeric_sequence(
                weights,
                field_name="weights",
                expected_length=len(normalized_rows),
                digit_hint=digit_hint,
            ),
            "variable_map": normalized_variable_map,
            "variable_data": variable_data,
            "target_series": target_series,
            "target_column": normalized_target,
            "model_expr": _text_value(model_expr, field_name="model_expr"),
            "parameter_config": parameter_payload,
            "parameter_names": _normalize_parameter_names(parameter_names, parameter_payload=parameter_payload),
            "template_expr": _optional_text(template_expr, field_name="template_expr"),
            "template_params": numeric_payload_tree(
                dict(template_params or {}),
                field_name="template_params",
                digit_hint=digit_hint,
            ),
            "poly_degree": _validate_int(poly_degree, field_name="poly_degree"),
            "inverse_min": _validate_int(inverse_min, field_name="inverse_min"),
            "inverse_max": _validate_int(inverse_max, field_name="inverse_max"),
            "pade_m": _validate_int(pade_m, field_name="pade_m"),
            "pade_n": _validate_int(pade_n, field_name="pade_n"),
            "auto_identifier": _optional_text(auto_identifier, field_name="auto_identifier"),
            "weighted": _validate_bool(weighted, field_name="weighted"),
            "label": _text_value(label, field_name="label"),
            "is_multidim": bool(len(normalized_variable_map) > 1) if is_multidim is None else _validate_bool(is_multidim, field_name="is_multidim"),
            "implicit_definition": _normalize_implicit_definition(
                implicit_definition,
                digit_hint=digit_hint,
            ),
            "timeout_seconds": _optional_numeric_text(
                timeout_seconds,
                field_name="timeout_seconds",
                digit_hint=digit_hint,
            ),
            "custom_constants": _normalize_string_mapping(
                custom_constants or {},
                field_name="custom_constants",
                digit_hint=digit_hint,
            ),
        },
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
            parallel=normalize_parallel_options(parallel or {}, digit_hint=digit_hint),
        ),
        request_id=request_id,
    )


def run_fitting(request: ComputeJobRequest) -> ResultEnvelope:
    """Run direct, non-subprocess fitting through the UI-neutral service boundary."""

    check_cancelled()
    if request.mode is not JobMode.FITTING:
        raise ValueError(f"Unsupported fitting request mode: {request.mode.value}.")
    model_type = _required_text(request.inputs.get("model_type"), field_name="model_type")
    if model_type == "self_consistent":
        raise ValueError(
            "self_consistent fitting still requires the subprocess execution path."
        )
    precision_digits = (
        DEFAULT_FITTING_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        fit_input = _direct_fit_input_from_request(
            request,
            model_type=model_type,
            precision=precision_used,
        )
        check_cancelled()
        output = execute_direct_fit(fit_input)
        check_cancelled()
        keep_digits = max(precision_used + 10, 30)
        payload = {
            "model_type": model_type,
            "expression": output.expression,
            "precision_used": precision_used,
            "fit_result": serialize_fit_result(output.fit_result, keep_digits),
            "logs": list(output.logs),
            "warnings": list(output.warnings),
        }
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        logs=output.logs,
        warnings=output.warnings,
    )


def fitting_payload_to_fit_result(payload: Mapping[str, Any]) -> Any:
    return deserialize_fit_result(payload)


def _direct_fit_input_from_request(
    request: ComputeJobRequest,
    *,
    model_type: str,
    precision: int,
) -> DirectFitInput:
    inputs = request.inputs
    sigma_series = cast(
        Sequence[mp.mpf | None],
        _optional_numeric_sequence_as_mpf(
            inputs.get("sigma_series"),
            field_name="sigma_series",
        )
        or (),
    )
    return DirectFitInput(
        model_type=model_type,
        x_series=_required_numeric_sequence(inputs.get("x_series"), field_name="x_series"),
        y_series=_required_numeric_sequence(inputs.get("y_series"), field_name="y_series"),
        sigma_series=sigma_series,
        weights=_optional_numeric_sequence_as_mpf(
            inputs.get("weights"),
            field_name="weights",
            allow_none_items=False,
        ),
        variable_map=_required_string_mapping(inputs.get("variable_map"), field_name="variable_map"),
        variable_data=_required_numeric_mapping(inputs.get("variable_data"), field_name="variable_data"),
        target_series=_required_numeric_sequence(
            inputs.get("target_series"),
            field_name="target_series",
        ),
        target_column=_required_text(inputs.get("target_column"), field_name="target_column"),
        model_expr=_text_value(inputs.get("model_expr", ""), field_name="model_expr"),
        parameter_config=_mapping_or_empty(inputs.get("parameter_config"), field_name="parameter_config"),
        parameter_names=_required_string_sequence(
            inputs.get("parameter_names", ()),
            field_name="parameter_names",
        ),
        template_expr=_optional_text(inputs.get("template_expr"), field_name="template_expr"),
        template_params=_mapping_or_empty(inputs.get("template_params"), field_name="template_params"),
        poly_degree=_validate_int(inputs.get("poly_degree", 0), field_name="poly_degree"),
        inverse_min=_validate_int(inputs.get("inverse_min", 1), field_name="inverse_min"),
        inverse_max=_validate_int(inputs.get("inverse_max", 3), field_name="inverse_max"),
        pade_m=_validate_int(inputs.get("pade_m", 1), field_name="pade_m"),
        pade_n=_validate_int(inputs.get("pade_n", 1), field_name="pade_n"),
        precision=precision,
        weighted=_validate_bool(inputs.get("weighted", False), field_name="weighted"),
        label=_text_value(inputs.get("label", ""), field_name="label"),
        custom_constants=_normalize_string_mapping(
            _mapping_or_empty(inputs.get("custom_constants"), field_name="custom_constants"),
            field_name="custom_constants",
            digit_hint=precision,
        ),
    )


def _normalize_sigma_rows(
    rows: Sequence[Sequence[Any | None]] | None,
    *,
    headers: Sequence[str],
    row_count: int,
    digit_hint: int,
) -> list[list[dict[str, Any] | str | None]]:
    if rows is None or not rows:
        return [[None for _ in headers] for _ in range(row_count)]
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("sigma_rows must be a sequence of row sequences.")
    if len(rows) != row_count:
        raise ValueError("sigma_rows must have the same length as data_rows.")

    normalized: list[list[dict[str, Any] | str | None]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"sigma_rows[{row_index}] must be a sequence of values.")
        if len(row) < len(headers):
            missing_header = headers[len(row)]
            raise ValueError(f"sigma_rows[{row_index}] is missing column {missing_header}.")
        normalized.append(
            [
                _normalize_sigma_value(
                    row[column_index],
                    field_name=f"sigma_rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
                for column_index, header in enumerate(headers)
            ]
        )
    return normalized


def _normalize_sigma_value(value: Any | None, *, field_name: str, digit_hint: int) -> dict[str, Any] | str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        uncertainty_digits = getattr(value, "uncertainty_digits", None)
        return {
            "kind": "uncertain",
            "value": numeric_to_payload_string(
                getattr(value, "value"),
                field_name=f"{field_name}.value",
                digit_hint=digit_hint,
            ),
            "uncertainty": numeric_to_payload_string(
                getattr(value, "uncertainty"),
                field_name=f"{field_name}.uncertainty",
                digit_hint=digit_hint,
            ),
            "uncertainty_digits": _validate_optional_int(
                uncertainty_digits,
                field_name=f"{field_name}.uncertainty_digits",
            ),
        }
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _sigma_series_value(value: Mapping[str, Any] | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return str(value.get("uncertainty") or "")
    return value


def _normalize_variable_map(value: Mapping[str, str], *, headers: Sequence[str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("variable_map must be a mapping.")
    normalized: dict[str, str] = {}
    for raw_variable, raw_column in value.items():
        variable = _required_text(raw_variable, field_name="variable_map.<key>")
        column = _normalize_column_name(raw_column, field_name=f"variable_map.{variable}", headers=headers)
        normalized[variable] = column
    if not normalized:
        raise ValueError("variable_map must contain at least one variable.")
    return normalized


def _normalize_column_name(value: Any, *, field_name: str, headers: Sequence[str]) -> str:
    column = _required_text(value, field_name=field_name)
    if column not in headers:
        raise ValueError(f"{field_name} {column} is not in headers.")
    return column


def _normalize_parameter_config(
    value: Mapping[str, Mapping[str, Any]],
    *,
    digit_hint: int,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise TypeError("parameter_config must be a mapping.")
    normalized: dict[str, dict[str, str]] = {}
    for raw_name, raw_config in value.items():
        name = _required_text(raw_name, field_name="parameter_config.<key>")
        if not isinstance(raw_config, Mapping):
            raise TypeError(f"parameter_config.{name} must be a mapping.")
        entry: dict[str, str] = {}
        for field_name in _PARAMETER_FIELDS:
            if field_name not in raw_config:
                continue
            text = _optional_parameter_text(
                raw_config[field_name],
                field_name=f"parameter_config.{name}.{field_name}",
                digit_hint=digit_hint,
            )
            if text:
                target_field = "expr" if field_name == "expr" else field_name
                entry[target_field] = text
        normalized[name] = entry
    return normalized


def _normalize_parameter_names(
    value: Sequence[str] | None,
    *,
    parameter_payload: Mapping[str, Mapping[str, str]],
) -> list[str]:
    if value is None:
        return list(parameter_payload)
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError("parameter_names must be a sequence of strings.")
    names = [_required_text(item, field_name=f"parameter_names[{index}]") for index, item in enumerate(value)]
    return names


def _normalize_implicit_definition(value: Mapping[str, Any] | object | None, *, digit_hint: int) -> dict[str, Any] | None:
    if value is None:
        return None
    solve_options = _field_value(value, "solve_options", default={})
    if solve_options is None:
        solve_options = {}
    _validate_mapping_or_object(solve_options, field_name="implicit_definition.solve_options")
    return {
        "x_variables": _required_string_sequence(
            _field_value(value, "x_variables"),
            field_name="implicit_definition.x_variables",
        ),
        "implicit_variable": _required_text(
            _field_value(value, "implicit_variable"),
            field_name="implicit_definition.implicit_variable",
        ),
        "equation": _required_text(
            _field_value(value, "equation"),
            field_name="implicit_definition.equation",
        ),
        "output_expression": _required_text(
            _field_value(value, "output_expression"),
            field_name="implicit_definition.output_expression",
        ),
        "parameters": _required_string_sequence(
            _field_value(value, "parameters"),
            field_name="implicit_definition.parameters",
        ),
        "constants": _normalize_string_mapping(
            _field_value(value, "constants", default={}) or {},
            field_name="implicit_definition.constants",
            digit_hint=digit_hint,
        ),
        "solve_options": _normalize_implicit_solve_options(
            solve_options,
            digit_hint=digit_hint,
        ),
    }


def _normalize_implicit_solve_options(value: Mapping[str, Any] | object, *, digit_hint: int) -> dict[str, Any]:
    return {
        "method": _text_value(_field_value(value, "method", default="fixed_point"), field_name="implicit_definition.solve_options.method") or "fixed_point",
        "initial": _text_numeric_or_expression(
            _field_value(value, "initial", default="0"),
            field_name="implicit_definition.solve_options.initial",
            digit_hint=digit_hint,
        ) or "0",
        "tolerance": _text_numeric_or_expression(
            _field_value(value, "tolerance", default="1e-30"),
            field_name="implicit_definition.solve_options.tolerance",
            digit_hint=digit_hint,
        ) or "1e-30",
        "max_iterations": _validate_int(
            _field_value(value, "max_iterations", default=80),
            field_name="implicit_definition.solve_options.max_iterations",
        ),
    }


def _normalize_string_mapping(value: Mapping[str, Any], *, field_name: str, digit_hint: int) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, str] = {}
    for raw_name, raw_value in value.items():
        name = _required_text(raw_name, field_name=f"{field_name}.<key>")
        normalized[name] = _text_numeric_or_expression(
            raw_value,
            field_name=f"{field_name}.{name}",
            digit_hint=digit_hint,
        )
    return normalized


def _mapping_or_empty(value: Any, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return dict(value)


def _required_string_mapping(value: Any, *, field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _required_text(raw_key, field_name=f"{field_name}.<key>")
        normalized[key] = _required_text(raw_value, field_name=f"{field_name}.{key}")
    return normalized


def _required_numeric_mapping(value: Any, *, field_name: str) -> dict[str, list[mp.mpf]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return {
        _required_text(raw_key, field_name=f"{field_name}.<key>"): _required_numeric_sequence(
            raw_values,
            field_name=f"{field_name}.{raw_key}",
        )
        for raw_key, raw_values in value.items()
    }


def _normalize_optional_numeric_sequence(
    value: Sequence[Any | None] | None,
    *,
    field_name: str,
    expected_length: int | None = None,
    digit_hint: int,
) -> list[str | None] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(f"{field_name} must be a sequence.")
    if expected_length is not None and len(value) != expected_length:
        raise ValueError(f"{field_name} must have the same length as data_rows.")
    return [
        _optional_numeric_text(item, field_name=f"{field_name}[{index}]", digit_hint=digit_hint)
        for index, item in enumerate(value)
    ]


def _required_numeric_sequence(value: Any, *, field_name: str) -> list[mp.mpf]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    return [_mpf_from_payload(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]


def _optional_numeric_sequence_as_mpf(
    value: Any,
    *,
    field_name: str,
    allow_none_items: bool = True,
) -> list[mp.mpf | None] | list[mp.mpf] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    return [
        (
            None
            if item is None and allow_none_items
            else _mpf_from_payload(item, field_name=f"{field_name}[{index}]")
        )
        for index, item in enumerate(value)
    ]


def _mpf_from_payload(value: Any, *, field_name: str) -> mp.mpf:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, not boolean.")
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    try:
        return mp.mpf(value)
    except Exception as exc:  # noqa: BLE001 - core payload boundary reports field context.
        raise ValueError(f"{field_name} is not a valid number: {value!r}.") from exc


def _field_value(source: Mapping[str, Any] | object, key: str, *, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _validate_mapping_or_object(value: Any, *, field_name: str) -> None:
    if isinstance(value, Mapping):
        return
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(f"{field_name} must be a mapping or object.")
    if isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a mapping or object.")
    if not hasattr(value, "__dict__") and not hasattr(type(value), "__dataclass_fields__"):
        raise TypeError(f"{field_name} must be a mapping or object.")


def _required_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    return [_required_text(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]


def _required_text(value: Any, *, field_name: str) -> str:
    text = _text_value(value, field_name=field_name)
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _optional_text(value: Any | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _text_value(value, field_name=field_name)


def _text_value(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass text inputs as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string.")
    return str(value or "").strip()


def _optional_parameter_text(value: Any, *, field_name: str, digit_hint: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be text or numeric text, not boolean.")
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _text_numeric_or_expression(value: Any, *, field_name: str, digit_hint: int) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be text or numeric text, not boolean.")
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if value is None:
        return ""
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _optional_numeric_text(value: Any | None, *, field_name: str, digit_hint: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _validate_bool(value: bool, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean.")
    return value


def _validate_int(value: int, *, field_name: str) -> int:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass integer options as integers.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _validate_optional_int(value: int | None, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _validate_int(value, field_name=field_name)
