from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from mpmath import mp

from root_solving.batch import solve_root_batch
from root_solving.models import (
    RootBackend,
    RootBatchResult,
    RootBatchRowResult,
    RootMode,
    RootResult,
    RootUnknown,
    RootValue,
)
from shared.input_normalization import normalize_constants_state
from shared.integer_validation import strict_int
from shared.parallel_config import ParallelConfig
from shared.parallel_options import parallel_config_from_mapping
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.uncertainty import parse_uncertainty_format


def execute_root_batch_from_payload(
    *,
    equations: Sequence[str],
    unknown_rows: Sequence[Mapping[str, str]],
    data_headers: Sequence[str],
    data_rows: Sequence[Sequence[str]],
    constants_enabled: bool,
    constants_rows: Sequence[Mapping[str, str]],
    constants_view: str,
    constants_text: str,
    mode: str,
    scan_config: Mapping[str, object],
    uncertainty_options: Mapping[str, object],
    precision: int,
    parallel_options: Mapping[str, object] | None = None,
) -> RootBatchResult:
    constants_state = normalize_constants_state(
        enabled=constants_enabled,
        rows=[dict(row) for row in constants_rows],
        view=constants_view,
        text=constants_text,
        numeric_mode="uncertainty",
    )
    with precision_guard(precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        parsed_data_rows = tuple(
            tuple(parse_uncertainty_format(str(cell), precision=precision) for cell in row)
            for row in data_rows
        )
    unknowns = tuple(RootUnknown(**dict(row)) for row in unknown_rows if str(row.get("name", "")).strip())
    return solve_root_batch(
        equations=tuple(str(value) for value in equations),
        unknowns=unknowns,
        data_headers=tuple(str(value) for value in data_headers),
        data_rows=parsed_data_rows,
        constants_state=constants_state,
        mode=str(mode),
        precision=precision,
        scan_config=dict(scan_config),
        data_text_rows=tuple(tuple(str(cell) for cell in row) for row in data_rows),
        uncertainty_options=dict(uncertainty_options),
        parallel_config=_parallel_config_from_mapping(parallel_options or {}),
    )


def serialize_root_batch_result(batch: RootBatchResult, *, digits: int) -> dict[str, Any]:
    return {
        "headers": [str(value) for value in batch.headers],
        "warnings": [str(value) for value in batch.warnings],
        "details": _json_safe_tree(batch.details, digits),
        "rows": [_serialize_root_batch_row(row, digits=digits) for row in batch.rows],
    }


def deserialize_root_batch_result(payload: Mapping[str, Any]) -> RootBatchResult:
    return RootBatchResult(
        rows=tuple(_deserialize_root_batch_row(row) for row in _required_sequence(payload, "rows")),
        headers=tuple(str(value) for value in _required_sequence(payload, "headers")),
        warnings=tuple(str(value) for value in payload.get("warnings") or ()),
        details=dict(payload.get("details") or {}),
    )


def _serialize_root_batch_row(row: RootBatchRowResult, *, digits: int) -> dict[str, Any]:
    return {
        "row_index": row.row_index,
        "source_values": {str(key): str(value) for key, value in row.source_values.items()},
        "failure": row.failure,
        "warnings": [str(value) for value in row.warnings],
        "result": None if row.result is None else _serialize_root_result(row.result, digits=digits),
    }


def _deserialize_root_batch_row(payload: Any) -> RootBatchRowResult:
    if not isinstance(payload, Mapping):
        raise TypeError("root batch row payload must be an object.")
    result_payload = payload.get("result")
    return RootBatchRowResult(
        row_index=_optional_int(payload.get("row_index"), field_name="row_index"),
        source_values={str(key): str(value) for key, value in dict(payload.get("source_values") or {}).items()},
        result=None if result_payload is None else _deserialize_root_result(result_payload),
        failure=None if payload.get("failure") is None else str(payload.get("failure")),
        warnings=tuple(str(value) for value in payload.get("warnings") or ()),
    )


def _serialize_root_result(result: RootResult, *, digits: int) -> dict[str, Any]:
    return {
        "roots": [_serialize_root_value(root, digits=digits) for root in result.roots],
        "backend": result.backend,
        "mode": result.mode,
        "residual_norm": _optional_number_payload(result.residual_norm, digits=digits),
        "jacobian_condition": _optional_number_payload(result.jacobian_condition, digits=digits),
        "warnings": [str(value) for value in result.warnings],
        "details": _json_safe_tree(result.details, digits),
    }


def _deserialize_root_result(payload: Any) -> RootResult:
    if not isinstance(payload, Mapping):
        raise TypeError("root result payload must be an object.")
    return RootResult(
        roots=tuple(_deserialize_root_value(root) for root in _required_sequence(payload, "roots")),
        backend=_root_backend(payload.get("backend")),
        mode=_root_mode(payload.get("mode")),
        residual_norm=_optional_number_from_payload(payload.get("residual_norm")),
        jacobian_condition=_optional_number_from_payload(payload.get("jacobian_condition")),
        warnings=tuple(str(value) for value in payload.get("warnings") or ()),
        details=dict(payload.get("details") or {}),
    )


def _serialize_root_value(root: RootValue, *, digits: int) -> dict[str, Any]:
    return {
        "name": root.name,
        "value": _number_payload(root.value, digits=digits),
        "uncertainty": _optional_number_payload(root.uncertainty, digits=digits),
        "contributions": {
            str(key): _mp_to_string(value, digits)
            for key, value in root.contributions.items()
        },
    }


def _deserialize_root_value(payload: Any) -> RootValue:
    if not isinstance(payload, Mapping):
        raise TypeError("root value payload must be an object.")
    return RootValue(
        name=str(payload["name"]),
        value=_number_from_payload(payload["value"]),
        uncertainty=_optional_number_from_payload(payload.get("uncertainty")),
        contributions={
            str(key): _real_number_from_payload(value)
            for key, value in dict(payload.get("contributions") or {}).items()
        },
    )


def _number_payload(value: Any, *, digits: int) -> dict[str, str]:
    if isinstance(value, complex):
        return {
            "kind": "complex",
            "real": _mp_to_string(value.real, digits),
            "imag": _mp_to_string(value.imag, digits),
        }
    mp_value = mp.mpc(value)
    if mp_value.imag:
        return {
            "kind": "complex",
            "real": _mp_to_string(mp_value.real, digits),
            "imag": _mp_to_string(mp_value.imag, digits),
        }
    return {"kind": "real", "value": _mp_to_string(mp_value.real, digits)}


def _optional_number_payload(value: Any | None, *, digits: int) -> dict[str, str] | None:
    if value is None:
        return None
    return _number_payload(value, digits=digits)


def _number_from_payload(payload: Any) -> mp.mpf | mp.mpc:
    if not isinstance(payload, Mapping):
        if isinstance(payload, float):
            raise TypeError("JSON floats are not allowed in root-solving numeric payloads; pass numeric values as strings.")
        return mp.mpf(payload)
    kind = str(payload.get("kind") or "real")
    if kind == "complex":
        real = payload.get("real", "0")
        imag = payload.get("imag", "0")
        if isinstance(real, float) or isinstance(imag, float):
            raise TypeError("JSON floats are not allowed in root-solving numeric payloads; pass numeric values as strings.")
        return mp.mpc(mp.mpf(real), mp.mpf(imag))
    value = payload.get("value", "0")
    if isinstance(value, float):
        raise TypeError("JSON floats are not allowed in root-solving numeric payloads; pass numeric values as strings.")
    return mp.mpf(value)


def _optional_number_from_payload(payload: Any | None) -> mp.mpf | mp.mpc | None:
    if payload is None:
        return None
    return _number_from_payload(payload)


def _real_number_from_payload(payload: Any) -> mp.mpf:
    value = _number_from_payload(payload)
    if isinstance(value, mp.mpc):
        if value.imag:
            raise ValueError("root-solving contribution payloads must be real numbers.")
        return mp.mpf(value.real)
    return mp.mpf(value)


def _json_safe_tree(value: Any, digits: int) -> Any:
    if isinstance(value, (mp.mpf, mp.mpc)):
        return _number_payload(value, digits=digits)
    if isinstance(value, float):
        return _mp_to_string(value, digits)
    if isinstance(value, (str, int, bool, type(None))):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_tree(item, digits) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [_json_safe_tree(item, digits) for item in value]
    return repr(value)


def _mp_to_string(value: Any, digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, digits)))


def _required_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = payload[key]
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{key} must be a sequence.")
    return cast(Sequence[Any], value)


def _root_backend(value: object) -> RootBackend:
    text = str(value if value is not None else "mpmath")
    if text == "scipy":
        return "scipy"
    return "mpmath"


def _root_mode(value: object) -> RootMode:
    text = str(value if value is not None else "scalar")
    if text == "auto":
        return "auto"
    if text == "polynomial":
        return "polynomial"
    if text == "system":
        return "system"
    if text == "scan_multiple":
        return "scan_multiple"
    return "scalar"


def _optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    return strict_int(value, field_name=field_name)


def _parallel_config_from_mapping(value: Mapping[str, object]) -> ParallelConfig:
    return parallel_config_from_mapping(value)
