from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import mpmath as mp

from shared.precision import precision_guard

from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import (
    numeric_to_payload_string as _numeric_to_payload_string,
    optional_numeric_to_payload_string as _optional_numeric_to_payload_string,
    request_digit_hint as _request_digit_hint,
)
from .results import ResultEnvelope, ResultKind, ResultStatus
from .session import check_cancelled
from .statistics_compute import compute_statistics
from .table_payload import normalize_segments


DEFAULT_STATISTICS_PRECISION_DIGITS = 50


@dataclass(frozen=True)
class StatisticsRequestBatch:
    index: int
    request: ComputeJobRequest
    headers: tuple[str, ...]
    value_col: str
    row_count: int


def build_statistics_requests(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    value_col: str,
    sigma_col: str | None = None,
    stats_mode: str = "mean_sample",
    use_sample: bool = True,
    use_weighted_variance: bool = True,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id_prefix: str = "statistics",
) -> tuple[StatisticsRequestBatch, ...]:
    """Build string-only statistics core requests from normalized tabular data."""

    normalized_headers = tuple(str(header) for header in headers)
    if not value_col:
        raise ValueError("value_col must be provided.")
    if value_col not in normalized_headers:
        raise ValueError(f"Column not found: {value_col}.")
    value_index = normalized_headers.index(value_col)

    sigma_index: int | None = None
    normalized_sigma_col = (sigma_col or "").strip()
    if normalized_sigma_col:
        if normalized_sigma_col not in normalized_headers:
            raise ValueError(f"Column not found: {normalized_sigma_col}.")
        sigma_index = normalized_headers.index(normalized_sigma_col)

    normalized_segments = normalize_segments(segments, row_count=len(rows))
    batches: list[StatisticsRequestBatch] = []
    digit_hint = _request_digit_hint(precision_digits)
    for clamped_start, clamped_end in normalized_segments:
        if clamped_start >= clamped_end:
            continue
        values: list[str] = []
        sigmas: list[str | None] = []
        for row_index in range(clamped_start, clamped_end):
            row = rows[row_index]
            if value_index >= len(row):
                raise ValueError(f"Row {row_index + 1} is missing column {value_col}.")
            values.append(
                _numeric_to_payload_string(
                    row[value_index],
                    field_name=f"rows[{row_index}][{value_col}]",
                    digit_hint=digit_hint,
                )
            )
            sigmas.append(
                _resolve_sigma_payload(
                    rows,
                    sigma_rows,
                    row_index=row_index,
                    value_index=value_index,
                    sigma_index=sigma_index,
                    digit_hint=digit_hint,
                )
            )
        if not values:
            continue
        batch_index = len(batches) + 1
        request = ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": tuple(values),
                "sigmas": tuple(sigmas),
                "stats_mode": stats_mode,
                "use_sample": use_sample,
                "use_weighted_variance": use_weighted_variance,
            },
            options=JobOptions(
                precision_digits=precision_digits,
                uncertainty_digits=uncertainty_digits,
            ),
            request_id=f"{request_id_prefix}-{batch_index}",
        )
        batches.append(
            StatisticsRequestBatch(
                index=batch_index,
                request=request,
                headers=normalized_headers,
                value_col=value_col,
                row_count=len(values),
            )
        )
    if not batches:
        raise ValueError("values must contain at least one value.")
    return tuple(batches)


def run_statistics(request: ComputeJobRequest) -> ResultEnvelope:
    """Run the core statistics subset for UI-neutral service migration."""

    check_cancelled()
    stats_mode = _string_option(request.inputs.get("stats_mode"), default="mean_sample", field_name="stats_mode")
    use_sample = _bool_option(request.inputs.get("use_sample"), default=True)
    use_weighted_variance = _bool_option(request.inputs.get("use_weighted_variance"), default=True)
    precision_digits = (
        DEFAULT_STATISTICS_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )

    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        values = _parse_values(request.inputs.get("values"), field_name="values")
        sigmas = _parse_sigmas(request.inputs.get("sigmas"), count=len(values))
        check_cancelled()
        result = compute_statistics(
            values,
            sigmas,
            stats_mode,
            use_sample=use_sample,
            use_weighted_variance=use_weighted_variance,
        )
        check_cancelled()
        payload = {
            "mode": stats_mode,
            "row_count": len(values),
            "precision_used": precision_used,
            "mean": _format_mpf(result.get("mean"), precision_used),
            "std_mean": _format_mpf(result.get("std_mean"), precision_used),
            "std": _format_mpf(result.get("std"), precision_used),
            "min": _format_mpf(result.get("v_min"), precision_used),
            "max": _format_mpf(result.get("v_max"), precision_used),
            "method_label": str(result.get("method_label") or ""),
            "dropped": int(result.get("dropped") or 0),
            "effective_n": _format_optional_mpf(result.get("effective_n"), precision_used),
            "zero_sigma_anchor": bool(result.get("zero_sigma_anchor", False)),
        }
        warnings = tuple(str(item) for item in (result.get("warnings") or ()))
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=warnings,
    )


def statistics_payload_to_compute_result(
    payload: Mapping[str, Any],
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Convert a core statistics payload back to the legacy compute-result shape.

    Desktop and web adapters still share plotting and LaTeX renderers that expect
    the historical ``compute_statistics()`` dictionary. Keep the conversion here
    so both hosts use one interpretation of the JSON-safe core payload.
    """

    def _mpf_from_payload(key: str) -> mp.mpf:
        value = payload.get(key)
        if value is None:
            return mp.nan
        return mp.mpf(str(value))

    effective_n = payload.get("effective_n")
    return {
        "mean": _mpf_from_payload("mean"),
        "std_mean": _mpf_from_payload("std_mean"),
        "std": _mpf_from_payload("std"),
        "v_min": _mpf_from_payload("min"),
        "v_max": _mpf_from_payload("max"),
        "method_label": str(payload.get("method_label") or ""),
        "dropped": int(payload.get("dropped") or 0),
        "effective_n": None if effective_n is None else mp.mpf(str(effective_n)),
        "zero_sigma_anchor": bool(payload.get("zero_sigma_anchor", False)),
        "warnings": list(warnings),
    }


def _parse_values(value: Any, *, field_name: str) -> list[mp.mpf]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{field_name} must be a list of numeric strings.")
    parsed = [_parse_mpf(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]
    if not parsed:
        raise ValueError(f"{field_name} must contain at least one value.")
    return parsed


def _parse_sigmas(value: Any, *, count: int) -> list[mp.mpf | None]:
    if value is None:
        return [None] * count
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError("sigmas must be a list of numeric strings or nulls.")
    if len(value) != count:
        raise ValueError("sigmas must have the same length as values.")
    return [
        None if item is None else _parse_mpf(item, field_name=f"sigmas[{index}]")
        for index, item in enumerate(value)
    ]


def _parse_mpf(value: Any, *, field_name: str) -> mp.mpf:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a numeric string.")
    try:
        return mp.mpf(value)
    except Exception as exc:  # noqa: BLE001 - user numeric text boundary.
        raise ValueError(f"{field_name} is not a valid number: {value!r}.") from exc


def _string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value.strip() or default


def _bool_option(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("boolean statistics options must be booleans.")
    return value


def _format_optional_mpf(value: Any, precision_digits: int) -> str | None:
    if value is None:
        return None
    return _format_mpf(value, precision_digits)


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _resolve_sigma_payload(
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None,
    *,
    row_index: int,
    value_index: int,
    sigma_index: int | None,
    digit_hint: int,
) -> str | None:
    if sigma_index is not None:
        row = rows[row_index]
        if sigma_index >= len(row):
            return None
        sigma_text = _optional_numeric_to_payload_string(
            row[sigma_index],
            field_name=f"rows[{row_index}][sigma]",
            digit_hint=digit_hint,
            absolute=True,
        )
        return sigma_text
    if not sigma_rows or row_index >= len(sigma_rows):
        return None
    sigma_row = sigma_rows[row_index]
    if value_index >= len(sigma_row):
        return None
    entry = sigma_row[value_index]
    if entry is None:
        return None
    if hasattr(entry, "uncertainty"):
        entry = getattr(entry, "uncertainty", None)
    return _optional_numeric_to_payload_string(
        entry,
        field_name=f"sigma_rows[{row_index}][{value_index}]",
        digit_hint=digit_hint,
        absolute=True,
    )
