from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import mpmath as mp

from .model_comparison import FitComparisonResult, FitComparisonRow

COMPARISON_TABLE_HEADERS = [
    "candidate_id",
    "order",
    "model_label",
    "status",
    "free_parameters",
    "chi2",
    "reduced_chi2",
    "aic",
    "bic",
    "rmse",
    "r2",
    "warnings",
    "error",
]


def build_comparison_table_rows(
    result: FitComparisonResult,
    *,
    format_value: Callable[[mp.mpf], str] | None = None,
) -> list[dict[str, Any]]:
    formatter = format_value or _default_format_value
    return [_format_row(row, formatter) for row in result.rows]


def build_comparison_table_rows_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if isinstance(rows, (str, bytes, bytearray, memoryview)) or not isinstance(rows, Sequence):
        raise ValueError("comparison payload rows must be a sequence.")
    return [_format_payload_row(row, index=index) for index, row in enumerate(rows)]


def _format_row(
    row: FitComparisonRow,
    format_value: Callable[[mp.mpf], str],
) -> dict[str, Any]:
    return {
        "candidate_id": row.candidate_id,
        "order": row.order,
        "model_label": row.model_label,
        "status": row.status,
        "free_parameters": row.free_parameter_count,
        "chi2": _format_optional(row.chi2, format_value),
        "reduced_chi2": _format_optional(row.reduced_chi2, format_value),
        "aic": _format_optional(row.aic, format_value),
        "bic": _format_optional(row.bic, format_value),
        "rmse": _format_optional(row.rmse, format_value),
        "r2": _format_optional(row.r2, format_value),
        "warnings": "; ".join(row.warnings),
        "error": row.error or "",
    }


def _format_payload_row(row: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError(f"comparison payload rows[{index}] must be a mapping.")
    warnings_text = _warnings_text(row.get("warnings", ""))
    return {
        "candidate_id": str(row.get("candidate_id") or ""),
        "order": row.get("order", index + 1),
        "model_label": str(row.get("model_label") or ""),
        "status": str(row.get("status") or ""),
        "free_parameters": row.get("free_parameter_count", row.get("free_parameters", "")),
        "chi2": _payload_metric(row.get("chi2")),
        "reduced_chi2": _payload_metric(row.get("reduced_chi2")),
        "aic": _payload_metric(row.get("aic")),
        "bic": _payload_metric(row.get("bic")),
        "rmse": _payload_metric(row.get("rmse")),
        "r2": _payload_metric(row.get("r2")),
        "warnings": warnings_text,
        "error": str(row.get("error") or ""),
    }


def _format_optional(
    value: mp.mpf | None,
    format_value: Callable[[mp.mpf], str],
) -> str:
    if value is None:
        return ""
    return format_value(value)


def _default_format_value(value: mp.mpf) -> str:
    return str(mp.nstr(value, 12))


def _payload_metric(value: Any) -> str:
    return "" if value is None else str(value)


def _warnings_text(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        parts = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                parts.append(text)
        return "; ".join(parts)
    return str(value or "").strip()
