from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .numeric_payload import numeric_to_payload_string


def normalize_headers(headers: Sequence[str]) -> list[str]:
    if isinstance(headers, (str, bytes, bytearray, memoryview)):
        raise TypeError("headers must be a sequence of column names.")
    normalized = [str(header).strip() for header in headers]
    if not normalized:
        raise ValueError("headers must contain at least one column.")
    if any(not header for header in normalized):
        raise ValueError("headers must not contain empty column names.")
    return normalized


def normalize_numeric_rows(
    rows: Sequence[Sequence[Any]],
    *,
    headers: Sequence[str],
    digit_hint: int,
) -> list[list[str]]:
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("rows must be a sequence of row sequences.")
    if not rows:
        raise ValueError("rows must contain at least one row.")

    normalized_rows: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"Row {row_index + 1} must be a sequence of values.")
        if len(row) < len(headers):
            missing_header = headers[len(row)]
            raise ValueError(f"Row {row_index + 1} is missing column {missing_header}.")
        normalized_rows.append(
            [
                numeric_to_payload_string(
                    row[column_index],
                    field_name=f"rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
                for column_index, header in enumerate(headers)
            ]
        )
    return normalized_rows


def normalize_segments(
    segments: Sequence[tuple[int, int]] | None,
    *,
    row_count: int,
) -> list[list[int]]:
    source_segments = tuple(segments or ((0, row_count),))
    normalized: list[list[int]] = []
    for index, segment in enumerate(source_segments):
        if (
            isinstance(segment, (str, bytes, bytearray, memoryview))
            or not isinstance(segment, Sequence)
            or len(segment) != 2
        ):
            raise ValueError(f"segments[{index}] must contain start and end.")
        start, end = segment
        if isinstance(start, bool) or isinstance(end, bool):
            raise TypeError(f"segments[{index}] bounds must be integers.")
        if isinstance(start, float) or isinstance(end, float):
            raise TypeError(
                f"JSON floats are not allowed at segments[{index}]; pass segment bounds as integers."
            )
        if not isinstance(start, int) or not isinstance(end, int):
            raise TypeError(f"segments[{index}] bounds must be integers.")
        clamped_start = max(0, start)
        clamped_end = min(row_count, max(clamped_start, end))
        if clamped_start >= clamped_end:
            continue
        normalized.append([clamped_start, clamped_end])
    return normalized
