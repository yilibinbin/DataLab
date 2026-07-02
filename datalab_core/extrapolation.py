from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from mpmath import mp

from extrapolation_methods import PowerLawConfig
from shared.extrapolation_engine import (
    ExtrapolationOptions,
    ExtrapolationResult,
    process_extrapolation_rows,
)
from shared.precision import precision_guard

from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import numeric_payload_tree, request_digit_hint
from .results import ResultEnvelope, ResultKind, ResultStatus
from .session import check_cancelled
from .table_payload import normalize_headers, normalize_numeric_rows, normalize_segments


DEFAULT_EXTRAPOLATION_PRECISION_DIGITS = 50


def build_extrapolation_request(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    method: str = "power_law",
    method_options: Mapping[str, Any] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id: str = "extrapolation",
) -> ComputeJobRequest:
    """Build a string-only extrapolation core request from normalized table data.

    This is only the Phase 2 request boundary. Existing desktop/web
    extrapolation execution remains outside ``datalab_core`` until its
    LaTeX-coupled implementation can be split safely.
    """

    normalized_headers = normalize_headers(headers)
    normalized_rows = normalize_numeric_rows(
        rows,
        headers=normalized_headers,
        digit_hint=request_digit_hint(precision_digits),
    )
    normalized_segments = normalize_segments(segments, row_count=len(normalized_rows))
    if not normalized_segments:
        raise ValueError("segments must include at least one row.")

    digit_hint = request_digit_hint(precision_digits)
    return ComputeJobRequest(
        mode=JobMode.EXTRAPOLATION,
        inputs={
            "headers": normalized_headers,
            "rows": normalized_rows,
            "method": _normalize_method(method),
            "method_options": numeric_payload_tree(
                dict(method_options or {}),
                field_name="method_options",
                digit_hint=digit_hint,
            ),
            "segments": normalized_segments,
        },
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        ),
        request_id=request_id,
    )


def run_extrapolation(request: ComputeJobRequest) -> ResultEnvelope:
    """Run extrapolation through the UI-neutral core service boundary."""

    check_cancelled()
    if request.mode is not JobMode.EXTRAPOLATION:
        raise ValueError(f"Unsupported extrapolation request mode: {request.mode.value}.")
    precision_digits = (
        DEFAULT_EXTRAPOLATION_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        headers = _required_string_sequence(request.inputs.get("headers"), field_name="headers")
        rows = _required_matrix(request.inputs.get("rows"), field_name="rows", headers=headers)
        method = _required_text(request.inputs.get("method", "power_law"), field_name="method")
        method_options = _mapping_or_empty(request.inputs.get("method_options"), field_name="method_options")
        options = _options_from_payload(
            method,
            method_options,
            precision_digits=precision_used,
            uncertainty_digits=request.options.uncertainty_digits,
        )
        parsed_rows = [tuple(mp.mpf(str(cell)) for cell in row) for row in rows]
        check_cancelled()
        data_rows, results = process_extrapolation_rows(
            headers,
            parsed_rows,
            verbose=False,
            options=options,
        )
        check_cancelled()
        payload = {
            "headers": list(headers),
            "data_rows": [[_format_mpf(value, precision_used) for value in row] for row in data_rows],
            "method": method,
            "method_options": dict(method_options),
            "segments": request.inputs.get("segments") or [[0, len(data_rows)]],
            "precision_used": precision_used,
            "results": [_result_payload(result, precision_used) for result in results],
        }
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=tuple(options.warnings),
    )


def extrapolation_payload_to_rows(payload: Mapping[str, Any]) -> list[tuple[mp.mpf, ...]]:
    """Convert JSON-safe core extrapolation row payloads back to mp rows."""

    raw_rows = payload.get("data_rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray, memoryview)):
        raise ValueError("payload.data_rows must be a sequence.")
    rows: list[tuple[mp.mpf, ...]] = []
    for row_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Sequence) or isinstance(raw_row, (str, bytes, bytearray, memoryview)):
            raise ValueError(f"payload.data_rows[{row_index}] must be a sequence.")
        rows.append(tuple(mp.mpf(str(cell)) for cell in raw_row))
    return rows


def extrapolation_payload_to_results(payload: Mapping[str, Any]) -> list[ExtrapolationResult]:
    """Convert JSON-safe core extrapolation payloads back to legacy result objects."""

    raw_results = payload.get("results")
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes, bytearray, memoryview)):
        raise ValueError("payload.results must be a sequence.")
    results: list[ExtrapolationResult] = []
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, Mapping):
            raise ValueError(f"payload.results[{index}] must be a mapping.")
        raw_details = raw_result.get("details") or {}
        if not isinstance(raw_details, Mapping):
            raise ValueError(f"payload.results[{index}].details must be a mapping.")
        details: dict[str, mp.mpf | str] = {}
        for name, value in raw_details.items():
            details[str(name)] = _detail_from_payload(value)
        raw_value = raw_result.get("value")
        raw_uncertainty = raw_result.get("uncertainty")
        if raw_value is None:
            raise ValueError(f"payload.results[{index}].value is required.")
        if raw_uncertainty is None:
            raise ValueError(f"payload.results[{index}].uncertainty is required.")
        results.append(
            ExtrapolationResult(
                value=mp.mpf(str(raw_value)),
                uncertainty=mp.mpf(str(raw_uncertainty)),
                method=str(raw_result.get("method") or "quadratic"),
                details=details,
            )
        )
    return results


def _normalize_method(method: str) -> str:
    if not isinstance(method, str):
        raise TypeError("method must be a string.")
    normalized = method.strip()
    if not normalized:
        raise ValueError("method must not be empty.")
    return normalized


def _options_from_payload(
    method: str,
    method_options: Mapping[str, Any],
    *,
    precision_digits: int,
    uncertainty_digits: int | None,
) -> ExtrapolationOptions:
    power_config = _power_law_config_from_payload(method_options.get("power_law_config"), precision_digits)
    return ExtrapolationOptions(
        method=method,
        power_law_config=power_config,
        uncertainty_column=_optional_text(method_options.get("uncertainty_column")),
        mp_precision=precision_digits,
        levin_variant=_optional_text(method_options.get("levin_variant")) or "u",
        custom_formula=_optional_text(method_options.get("custom_formula")),
        uncertainty_digits=uncertainty_digits,
    )


def _power_law_config_from_payload(value: Any, precision_digits: int) -> PowerLawConfig | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("method_options.power_law_config must be a mapping.")
    x_values = value.get("x_values")
    if not isinstance(x_values, Sequence) or isinstance(x_values, (str, bytes, bytearray, memoryview)):
        raise ValueError("method_options.power_law_config.x_values must be a sequence.")
    return PowerLawConfig(
        x_values=tuple(str(item) for item in x_values),
        precision=_optional_int(value.get("precision"), default=precision_digits, field_name="power_law_config.precision"),
        exponent_override=_optional_text(value.get("exponent_override")),
        initial_guess=str(value.get("initial_guess", "1.0")),
        seed_guesses=_optional_string_tuple(value.get("seed_guesses"), field_name="power_law_config.seed_guesses"),
    )


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


def _mapping_or_empty(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _required_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        items = [token for token in re.split(r"[,\s]+", value.strip()) if token]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise ValueError(f"{field_name} must be a sequence of strings.")
    return tuple(items) if items else None


def _optional_int(value: Any, *, default: int, field_name: str) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass integer options as integers.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer.")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?\d+", text):
        raise TypeError(f"{field_name} must be an integer.")
    return int(text)


def _result_payload(result: ExtrapolationResult, precision_digits: int) -> dict[str, Any]:
    return {
        "value": _format_mpf(result.value, precision_digits),
        "uncertainty": _format_mpf(result.uncertainty, precision_digits),
        "method": result.method,
        "details": {
            str(name): _detail_to_payload(value, precision_digits)
            for name, value in result.details.items()
        },
    }


def _detail_to_payload(value: mp.mpf | str, precision_digits: int) -> str:
    if isinstance(value, mp.mpf):
        return _format_mpf(value, precision_digits)
    return str(value)


def _detail_from_payload(value: Any) -> mp.mpf | str:
    text = str(value)
    try:
        return mp.mpf(text)
    except Exception:
        return text


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), max(int(precision_digits), 1)))
