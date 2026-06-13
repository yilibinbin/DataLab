from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mpmath import mp

from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import (
    numeric_to_payload_string,
    optional_numeric_to_payload_string,
    request_digit_hint,
)
from .results import ResultEnvelope, ResultKind, ResultStatus
from .session import check_cancelled
from .table_payload import normalize_headers, normalize_segments
from shared.error_propagation_engine import apply_formula_to_data
from shared.precision import precision_guard
from shared.uncertainty import UncertainValue


DEFAULT_UNCERTAINTY_PRECISION_DIGITS = 50


def build_uncertainty_request(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    formula: str,
    uncertainty_rows: Sequence[Sequence[Any | None]] | None = None,
    constants: Mapping[str, Any] | None = None,
    propagation_method: str = "taylor",
    propagation_order: int = 1,
    mc_samples: int | None = None,
    mc_seed: int | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id: str = "uncertainty",
) -> ComputeJobRequest:
    """Build a string-only uncertainty propagation request.

    This is a Phase 2 request boundary only. Existing desktop/web error
    propagation execution stays in the legacy path until that implementation is
    split from LaTeX/PDF/rendering concerns.
    """

    digit_hint = request_digit_hint(precision_digits)
    normalized_headers = normalize_headers(headers)
    normalized_formula = _normalize_formula(formula)
    values, uncertainties = _normalize_uncertainty_rows(
        rows,
        uncertainty_rows=uncertainty_rows,
        headers=normalized_headers,
        digit_hint=digit_hint,
    )
    normalized_segments = normalize_segments(segments, row_count=len(values))
    if not normalized_segments:
        raise ValueError("segments must include at least one row.")

    return ComputeJobRequest(
        mode=JobMode.UNCERTAINTY,
        inputs={
            "headers": normalized_headers,
            "values": values,
            "uncertainties": uncertainties,
            "constants": _normalize_constants(constants or {}, digit_hint=digit_hint),
            "formula": normalized_formula,
            "propagation": {
                "method": _normalize_method(propagation_method),
                "order": _validate_int(propagation_order, field_name="propagation.order"),
                "mc_samples": _validate_optional_int(mc_samples, field_name="propagation.mc_samples"),
                "mc_seed": _validate_optional_int(mc_seed, field_name="propagation.mc_seed"),
            },
            "segments": normalized_segments,
        },
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        ),
        request_id=request_id,
    )


def run_uncertainty(request: ComputeJobRequest) -> ResultEnvelope:
    """Run uncertainty propagation through the UI-neutral core service boundary."""

    check_cancelled()
    if request.mode is not JobMode.UNCERTAINTY:
        raise ValueError(f"Unsupported uncertainty request mode: {request.mode.value}.")
    precision_digits = (
        DEFAULT_UNCERTAINTY_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        headers = _required_string_sequence(request.inputs.get("headers"), field_name="headers")
        values = _required_matrix(request.inputs.get("values"), field_name="values", headers=headers)
        uncertainties = _required_matrix(
            request.inputs.get("uncertainties"),
            field_name="uncertainties",
            headers=headers,
        )
        if len(uncertainties) != len(values):
            raise ValueError("uncertainties must have the same row count as values.")
        parsed_data = _uncertain_rows(values, uncertainties)
        constants = _uncertain_constants(request.inputs.get("constants"))
        check_cancelled()
        formula = _required_text(request.inputs.get("formula"), field_name="formula")
        propagation = _mapping_or_empty(request.inputs.get("propagation"), field_name="propagation")
        method = _required_text(propagation.get("method", "taylor"), field_name="propagation.method")
        order = _validate_int(propagation.get("order", 1), field_name="propagation.order")
        mc_samples = _validate_optional_int(propagation.get("mc_samples"), field_name="propagation.mc_samples")
        mc_seed = _validate_optional_int(propagation.get("mc_seed"), field_name="propagation.mc_seed")
        warnings: list[str] = []
        results = apply_formula_to_data(
            list(headers),
            parsed_data,
            constants,
            formula,
            False,
            warnings=warnings,
            return_components=True,
            propagation_method=method,
            propagation_order=order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )
        check_cancelled()
        payload = {
            "headers": list(headers),
            "formula": formula,
            "segments": request.inputs.get("segments") or [[0, len(values)]],
            "precision_used": precision_used,
            "results": [_uncertain_result_payload(result, precision_used) for result in results],
        }
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=tuple(warnings),
    )


def uncertainty_payload_to_results(payload: Mapping[str, Any]) -> list[UncertainValue]:
    """Convert JSON-safe core uncertainty payload back to legacy result objects."""

    raw_results = payload.get("results")
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes, bytearray, memoryview)):
        raise ValueError("payload.results must be a sequence.")
    results: list[UncertainValue] = []
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, Mapping):
            raise ValueError(f"payload.results[{index}] must be a mapping.")
        contributions_raw = raw_result.get("contributions") or {}
        if not isinstance(contributions_raw, Mapping):
            raise ValueError(f"payload.results[{index}].contributions must be a mapping.")
        contributions = {
            str(name): mp.mpf(str(value))
            for name, value in contributions_raw.items()
        }
        results.append(
            UncertainValue(
                mp.mpf(str(raw_result.get("value"))),
                mp.mpf(str(raw_result.get("uncertainty"))),
                contributions=contributions or None,
            )
        )
    return results


def _required_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(f"{field_name} must be a sequence of strings.")
    items = [str(item) for item in value]
    if not items:
        raise ValueError(f"{field_name} must contain at least one item.")
    return items


def _required_matrix(value: Any, *, field_name: str, headers: Sequence[str]) -> list[list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(f"{field_name} must be a sequence of rows.")
    rows: list[list[str]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            raise ValueError(f"{field_name}[{row_index}] must be a sequence.")
        if len(row) != len(headers):
            raise ValueError(f"{field_name}[{row_index}] must have {len(headers)} columns.")
        rows.append([str(item) for item in row])
    if not rows:
        raise ValueError(f"{field_name} must contain at least one row.")
    return rows


def _uncertain_rows(values: Sequence[Sequence[str]], uncertainties: Sequence[Sequence[str]]) -> list[list[UncertainValue]]:
    return [
        [
            UncertainValue(mp.mpf(value), mp.mpf(uncertainty))
            for value, uncertainty in zip(value_row, uncertainty_row, strict=True)
        ]
        for value_row, uncertainty_row in zip(values, uncertainties, strict=True)
    ]


def _uncertain_constants(value: Any) -> dict[str, UncertainValue]:
    constants = _mapping_or_empty(value, field_name="constants")
    parsed: dict[str, UncertainValue] = {}
    for raw_name, raw_entry in constants.items():
        name = str(raw_name)
        if not isinstance(raw_entry, Mapping):
            raise ValueError(f"constants.{name} must be a mapping.")
        parsed[name] = UncertainValue(
            mp.mpf(str(raw_entry.get("value"))),
            mp.mpf(str(raw_entry.get("uncertainty", "0"))),
        )
    return parsed


def _mapping_or_empty(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _uncertain_result_payload(result: UncertainValue, precision_digits: int) -> dict[str, Any]:
    contributions = getattr(result, "contributions", None) or {}
    return {
        "value": _format_mpf(result.value, precision_digits),
        "uncertainty": _format_mpf(result.uncertainty, precision_digits),
        "contributions": {
            str(name): _format_mpf(value, precision_digits)
            for name, value in contributions.items()
        },
    }


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _normalize_uncertainty_rows(
    rows: Sequence[Sequence[Any]],
    *,
    uncertainty_rows: Sequence[Sequence[Any | None]] | None,
    headers: Sequence[str],
    digit_hint: int,
) -> tuple[list[list[str]], list[list[str]]]:
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("rows must be a sequence of row sequences.")
    if not rows:
        raise ValueError("rows must contain at least one row.")
    if uncertainty_rows is not None and len(uncertainty_rows) != len(rows):
        raise ValueError("uncertainty_rows must have the same length as rows.")

    values: list[list[str]] = []
    uncertainties: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"Row {row_index + 1} must be a sequence of values.")
        if len(row) < len(headers):
            missing_header = headers[len(row)]
            raise ValueError(f"Row {row_index + 1} is missing column {missing_header}.")
        uncertainty_row = None if uncertainty_rows is None else uncertainty_rows[row_index]
        row_values: list[str] = []
        row_uncertainties: list[str] = []
        for column_index, header in enumerate(headers):
            cell_value, embedded_uncertainty = _split_uncertain_value(row[column_index])
            row_values.append(
                numeric_to_payload_string(
                    cell_value,
                    field_name=f"rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
            )
            explicit_uncertainty = None
            if uncertainty_row is not None and column_index < len(uncertainty_row):
                explicit_uncertainty = uncertainty_row[column_index]
            uncertainty_value = embedded_uncertainty if explicit_uncertainty is None else explicit_uncertainty
            row_uncertainties.append(
                _uncertainty_payload_or_zero(
                    uncertainty_value,
                    field_name=f"uncertainty_rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
            )
        values.append(row_values)
        uncertainties.append(row_uncertainties)
    return values, uncertainties


def _normalize_constants(constants: Mapping[str, Any], *, digit_hint: int) -> dict[str, dict[str, str]]:
    if not isinstance(constants, Mapping):
        raise TypeError("constants must be a mapping.")
    normalized: dict[str, dict[str, str]] = {}
    for raw_name, raw_value in constants.items():
        if not isinstance(raw_name, str):
            raise TypeError("constant names must be strings.")
        name = raw_name.strip()
        if not name:
            raise ValueError("constant names must not be empty.")
        value, uncertainty = _split_constant_value(raw_value)
        normalized[name] = {
            "value": numeric_to_payload_string(
                value,
                field_name=f"constants.{name}.value",
                digit_hint=digit_hint,
            ),
            "uncertainty": _uncertainty_payload_or_zero(
                uncertainty,
                field_name=f"constants.{name}.uncertainty",
                digit_hint=digit_hint,
            ),
        }
    return normalized


def _split_uncertain_value(value: Any) -> tuple[Any, Any | None]:
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        return getattr(value, "value"), getattr(value, "uncertainty")
    return value, None


def _split_constant_value(value: Any) -> tuple[Any, Any | None]:
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        return getattr(value, "value"), getattr(value, "uncertainty")
    if isinstance(value, Mapping):
        if "value" not in value:
            raise ValueError("constant mappings must include a value field.")
        return value.get("value"), value.get("uncertainty")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        if len(value) != 2:
            raise ValueError("constant tuple values must contain value and uncertainty.")
        return value[0], value[1]
    return value, None


def _uncertainty_payload_or_zero(value: Any | None, *, field_name: str, digit_hint: int) -> str:
    text = optional_numeric_to_payload_string(
        value,
        field_name=field_name,
        digit_hint=digit_hint,
        absolute=True,
    )
    return "0" if text is None else text


def _normalize_formula(formula: str) -> str:
    if not isinstance(formula, str):
        raise TypeError("formula must be a string.")
    normalized = formula.strip()
    if not normalized:
        raise ValueError("formula must not be empty.")
    return normalized


def _normalize_method(method: str) -> str:
    if not isinstance(method, str):
        raise TypeError("propagation.method must be a string.")
    normalized = method.strip()
    if not normalized:
        raise ValueError("propagation.method must not be empty.")
    return normalized


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
