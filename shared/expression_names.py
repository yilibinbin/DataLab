from __future__ import annotations

from shared.expression_engine import _ALLOWED_CONSTANTS, _ALLOWED_FUNCTIONS


def reserved_expression_names() -> set[str]:
    """Return expression-engine names that user variables/constants must not shadow."""
    return {name.lower() for name in _ALLOWED_FUNCTIONS} | {
        name.lower() for name in _ALLOWED_CONSTANTS
    }


def is_reserved_expression_name(name: str) -> bool:
    return name.lower() in reserved_expression_names()
