from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .numeric_payload import numeric_to_payload_string


def normalize_parallel_options(value: Mapping[str, Any], *, digit_hint: int) -> dict[str, Any]:
    """Normalize parallel execution options for core request payloads."""

    if not isinstance(value, Mapping):
        raise TypeError("parallel must be a mapping.")
    return {
        _required_text(key, field_name="parallel.<key>"): _normalize_parallel_value(
            item,
            field_name=f"parallel.{key}",
            digit_hint=digit_hint,
        )
        for key, item in value.items()
    }


def _normalize_parallel_value(value: Any, *, field_name: str, digit_hint: int) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if isinstance(value, int | str):
        return value
    if isinstance(value, Mapping):
        return {
            _required_text(key, field_name=f"{field_name}.<key>"): _normalize_parallel_value(
                item,
                field_name=f"{field_name}.{key}",
                digit_hint=digit_hint,
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [
            _normalize_parallel_value(item, field_name=f"{field_name}[{index}]", digit_hint=digit_hint)
            for index, item in enumerate(value)
        ]
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _required_text(value: Any, *, field_name: str) -> str:
    text = _text_value(value, field_name=field_name)
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _text_value(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass text inputs as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string.")
    return str(value or "").strip()
