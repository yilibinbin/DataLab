from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import numeric_to_payload_string, request_digit_hint
from .parallel_options import normalize_parallel_options
from .results import ResultEnvelope, ResultKind, ResultStatus
from .session import check_cancelled
from .table_payload import normalize_headers
from shared.precision import precision_guard
from shared.root_solving_engine import (
    deserialize_root_batch_result,
    execute_root_batch_from_payload,
    serialize_root_batch_result,
)


_ROOT_MODES = {"auto", "scalar", "polynomial", "system", "scan_multiple"}
_UNKNOWN_SOURCES = {"manual", "detected"}


def build_root_solving_request(
    *,
    equations: Sequence[str],
    unknown_rows: Sequence[Mapping[str, Any]],
    data_headers: Sequence[str] = (),
    data_rows: Sequence[Sequence[Any]] = (),
    constants_enabled: bool = False,
    constants_rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = (),
    constants_view: str = "table",
    constants_text: str = "",
    mode: str = "auto",
    scan_config: Mapping[str, Any] | None = None,
    uncertainty_options: Mapping[str, Any] | None = None,
    precision_digits: int | None = None,
    display_digits: int = 10,
    uncertainty_digits: int | None = None,
    parallel: Mapping[str, Any] | None = None,
    request_id: str = "root-solving",
) -> ComputeJobRequest:
    """Build a string-preserving root-solving request.

    This is only the Phase 2 request boundary. The existing root solver,
    normalization, plotting, LaTeX, and subprocess execution paths remain
    outside ``datalab_core`` until their service adapter is migrated.
    """

    digit_hint = request_digit_hint(precision_digits)
    return ComputeJobRequest(
        mode=JobMode.ROOT_SOLVING,
        inputs={
            "equations": _normalize_equations(equations),
            "unknown_rows": _normalize_unknown_rows(unknown_rows, digit_hint=digit_hint),
            "data_headers": _normalize_optional_headers(data_headers),
            "data_rows": _normalize_data_rows(data_rows, headers=data_headers, digit_hint=digit_hint),
            "constants_enabled": _validate_bool(constants_enabled, field_name="constants_enabled"),
            "constants_rows": _normalize_constants_rows(constants_rows, digit_hint=digit_hint),
            "constants_view": _string_value(constants_view, field_name="constants_view").strip() or "table",
            "constants_text": str(constants_text or ""),
            "mode": _normalize_mode(mode),
            "scan_config": _normalize_option_mapping(
                scan_config or {},
                field_name="scan_config",
                digit_hint=digit_hint,
            ),
            "uncertainty_options": _normalize_option_mapping(
                uncertainty_options or {},
                field_name="uncertainty_options",
                digit_hint=digit_hint,
            ),
            "display_digits": _validate_int(display_digits, field_name="display_digits"),
        },
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
            parallel=normalize_parallel_options(parallel or {}, digit_hint=digit_hint),
        ),
        request_id=request_id,
    )


def run_root_solving(request: ComputeJobRequest) -> ResultEnvelope:
    """Run root-solving batch computation through the UI-neutral core service."""

    check_cancelled()
    if request.mode is not JobMode.ROOT_SOLVING:
        raise ValueError(f"Unsupported root-solving request mode: {request.mode.value}.")
    precision_digits = 16 if request.options.precision_digits is None else request.options.precision_digits
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        batch = execute_root_batch_from_payload(
            equations=_required_string_sequence(request.inputs.get("equations"), field_name="equations"),
            unknown_rows=_required_mapping_sequence(request.inputs.get("unknown_rows"), field_name="unknown_rows"),
            data_headers=_optional_string_sequence(request.inputs.get("data_headers"), field_name="data_headers"),
            data_rows=_required_row_sequence(request.inputs.get("data_rows", ()), field_name="data_rows"),
            constants_enabled=_validate_bool(
                request.inputs.get("constants_enabled", False),
                field_name="constants_enabled",
            ),
            constants_rows=_required_mapping_sequence(
                request.inputs.get("constants_rows", ()),
                field_name="constants_rows",
            ),
            constants_view=_string_value(request.inputs.get("constants_view", "table"), field_name="constants_view"),
            constants_text=str(request.inputs.get("constants_text") or ""),
            mode=_string_value(request.inputs.get("mode", "auto"), field_name="mode") or "auto",
            scan_config=_mapping_or_empty(request.inputs.get("scan_config"), field_name="scan_config"),
            uncertainty_options=_mapping_or_empty(
                request.inputs.get("uncertainty_options"),
                field_name="uncertainty_options",
            ),
            precision=precision_used,
            parallel_options=request.options.parallel,
        )
        check_cancelled()
        roots_count = sum(len(row.result.roots) for row in batch.rows if row.result is not None)
        payload = {
            "batch": serialize_root_batch_result(batch, digits=precision_used),
            "precision_used": precision_used,
            "row_count": len(batch.rows),
            "roots_count": roots_count,
        }
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=tuple(str(value) for value in batch.warnings),
    )


def root_batch_payload_to_result(payload: Mapping[str, Any]) -> Any:
    return deserialize_root_batch_result(payload)


def _normalize_equations(equations: Sequence[str]) -> list[str]:
    if isinstance(equations, (str, bytes, bytearray, memoryview)):
        raise TypeError("equations must be a sequence of equation strings.")
    normalized = [str(equation).strip() for equation in equations if str(equation).strip()]
    if not normalized:
        raise ValueError("equations must contain at least one equation.")
    return normalized


def _required_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one value.")
    return normalized


def _optional_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    return [str(item).strip() for item in value if str(item).strip()]


def _required_mapping_sequence(value: Any, *, field_name: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if isinstance(value, Mapping) or isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of mappings.")
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise TypeError(f"{field_name}[{index}] must be a mapping.")
        normalized.append({str(key): str(item) for key, item in row.items()})
    return normalized


def _required_row_sequence(value: Any, *, field_name: str) -> list[list[str]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of rows.")
    rows: list[list[str]] = []
    for row_index, row in enumerate(value):
        if isinstance(row, (str, bytes, bytearray, memoryview)) or not isinstance(row, Sequence):
            raise TypeError(f"{field_name}[{row_index}] must be a sequence.")
        rows.append([str(cell) for cell in row])
    return rows


def _mapping_or_empty(value: Any, *, field_name: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return {str(key): item for key, item in value.items()}


def _normalize_unknown_rows(rows: Sequence[Mapping[str, Any]], *, digit_hint: int) -> list[dict[str, str]]:
    if isinstance(rows, Mapping) or isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("unknown_rows must be a sequence of row mappings.")
    if not rows:
        raise ValueError("unknown_rows must contain at least one row.")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"unknown_rows[{index}] must be a mapping.")
        name = str(row.get("name") or "").strip()
        initial = _optional_numeric_text(row.get("initial"), field_name=f"unknown_rows[{index}].initial", digit_hint=digit_hint)
        lower = _optional_numeric_text(row.get("lower"), field_name=f"unknown_rows[{index}].lower", digit_hint=digit_hint)
        upper = _optional_numeric_text(row.get("upper"), field_name=f"unknown_rows[{index}].upper", digit_hint=digit_hint)
        if not any((name, initial, lower, upper)):
            continue
        source = str(row.get("source") or "manual").strip()
        if source not in _UNKNOWN_SOURCES:
            source = "manual"
        normalized.append(
            {
                "name": name,
                "initial": initial,
                "lower": lower,
                "upper": upper,
                "source": source,
            }
        )
    if not normalized:
        raise ValueError("unknown_rows must contain at least one row with meaningful data.")
    return normalized


def _normalize_optional_headers(headers: Sequence[str]) -> list[str]:
    if not headers:
        return []
    return normalize_headers(headers)


def _normalize_data_rows(
    rows: Sequence[Sequence[Any]],
    *,
    headers: Sequence[str],
    digit_hint: int,
) -> list[list[str]]:
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("data_rows must be a sequence of row sequences.")
    if not rows:
        return []
    normalized_headers = _normalize_optional_headers(headers)
    if not normalized_headers:
        raise ValueError("data_headers must contain at least one column when data_rows are provided.")
    normalized_rows: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"Root data row {row_index + 1} must be a sequence of values.")
        if len(row) < len(normalized_headers):
            missing_header = normalized_headers[len(row)]
            raise ValueError(f"Root data row {row_index + 1} is missing column {missing_header}.")
        normalized_rows.append(
            [
                _required_cell_text(
                    row[column_index],
                    field_name=f"data_rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
                for column_index, header in enumerate(normalized_headers)
            ]
        )
    return normalized_rows


def _normalize_constants_rows(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    digit_hint: int,
) -> list[dict[str, str]]:
    source_rows: list[Mapping[str, Any]]
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        source_rows = [{"name": key, "value": value} for key, value in rows.items()]
    elif isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray, memoryview)):
        source_rows = list(rows)
    else:
        raise TypeError("constants_rows must be a mapping or sequence of row mappings.")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(source_rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"constants_rows[{index}] must be a mapping.")
        name = str(row.get("name") or "").strip()
        value = row.get("value")
        if not name and (value is None or str(value).strip() == ""):
            continue
        if not name:
            raise ValueError(f"constants_rows[{index}].name must not be empty.")
        normalized.append(
            {
                "name": name,
                "value": _required_cell_text(
                    value,
                    field_name=f"constants_rows[{index}].value",
                    digit_hint=digit_hint,
                ),
            }
        )
    return normalized


def _normalize_mode(mode: str) -> str:
    normalized = _string_value(mode, field_name="mode").strip() or "auto"
    if normalized not in _ROOT_MODES:
        raise ValueError(f"Invalid root mode: {mode}.")
    return normalized


def _normalize_option_mapping(value: Mapping[str, Any], *, field_name: str, digit_hint: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings.")
        normalized[key] = _normalize_option_value(item, field_name=f"{field_name}.{key}", digit_hint=digit_hint)
    return normalized


def _normalize_option_value(value: Any, *, field_name: str, digit_hint: int) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _normalize_option_mapping(value, field_name=field_name, digit_hint=digit_hint)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [
            _normalize_option_value(item, field_name=f"{field_name}[{index}]", digit_hint=digit_hint)
            for index, item in enumerate(value)
        ]
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _optional_numeric_text(value: Any, *, field_name: str, digit_hint: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _required_cell_text(value: Any, *, field_name: str, digit_hint: int) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty.")
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _string_value(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass text options as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string.")
    return str(value or "")


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
