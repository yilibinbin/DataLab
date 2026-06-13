from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import mpmath as mp

from ._payload import validate_optional_int


DEFAULT_PAYLOAD_PRECISION_DIGITS = 50


def request_digit_hint(
    precision_digits: int | None,
    *,
    default_digits: int = DEFAULT_PAYLOAD_PRECISION_DIGITS,
) -> int:
    if precision_digits is None:
        validated_default = validate_optional_int(default_digits, field_name="default_digits")
        if validated_default is None:
            validated_default = DEFAULT_PAYLOAD_PRECISION_DIGITS
        return max(1, validated_default)
    validated_precision = validate_optional_int(precision_digits, field_name="precision_digits")
    if validated_precision is None:
        validated_precision = DEFAULT_PAYLOAD_PRECISION_DIGITS
    return max(1, validated_precision)


def numeric_to_payload_string(value: Any, *, field_name: str, digit_hint: int) -> str:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, not boolean.")
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty.")
        return text
    if isinstance(value, int):
        return str(value)
    try:
        if isinstance(value, mp.mpf):
            return str(mp.nstr(value, n=_mpf_payload_digits(value, digit_hint, preserve_intrinsic=True)))
        value_mpf = mp.mpf(value)
        return str(mp.nstr(value_mpf, n=_mpf_payload_digits(value_mpf, digit_hint, preserve_intrinsic=False)))
    except Exception as exc:  # noqa: BLE001 - adapter boundary reports field context.
        raise ValueError(f"{field_name} is not a valid number: {value!r}.") from exc


def optional_numeric_to_payload_string(
    value: Any,
    *,
    field_name: str,
    digit_hint: int,
    absolute: bool,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    text = numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)
    if not absolute:
        return text
    return absolute_numeric_text(text)


def numeric_payload_tree(value: Any, *, field_name: str, digit_hint: int) -> Any:
    """Convert numeric-like payload leaves to strings while rejecting floats.

    Core request builders use this for method options that may contain numeric
    parameter text plus ordinary JSON flags. Boolean/null/string leaves remain
    JSON leaves; ints and ``mp.mpf`` values become strings to avoid binary float
    boundaries and preserve user-selected precision.
    """

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if isinstance(value, str):
        return value
    if isinstance(value, int | mp.mpf):
        return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"Only string mapping keys are allowed at {field_name}.<key>.")
            converted[key] = numeric_payload_tree(item, field_name=f"{field_name}.{key}", digit_hint=digit_hint)
        return converted
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [
            numeric_payload_tree(item, field_name=f"{field_name}[{index}]", digit_hint=digit_hint)
            for index, item in enumerate(value)
        ]
    try:
        return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)
    except ValueError:
        pass
    return value


def absolute_numeric_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) > 1 and stripped[0] in "+-" and (
        stripped[1].isdigit() or stripped[1] == "." or stripped[1:].lower() in {"inf", "infinity"}
    ):
        return stripped[1:]
    return stripped


def _mpf_payload_digits(value: mp.mpf, digit_hint: int, *, preserve_intrinsic: bool) -> int:
    max_digits = max(DEFAULT_PAYLOAD_PRECISION_DIGITS, digit_hint)
    raw = getattr(value, "_mpf_", None)
    if isinstance(raw, tuple) and len(raw) >= 4 and isinstance(raw[3], int) and raw[3] > 0:
        intrinsic_digits = max(15, int(raw[3] * 0.3010299956639812))
        if preserve_intrinsic:
            return max(1, intrinsic_digits)
        return max(1, min(max_digits, intrinsic_digits))
    return max_digits
