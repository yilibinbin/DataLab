from __future__ import annotations


def strict_int(value: object, *, field_name: str) -> int:
    if isinstance(value, float):
        raise TypeError(f"{field_name} must be an integer, not a float.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return value
