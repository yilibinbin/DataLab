from __future__ import annotations

from shared.expression_registry import reserved_expression_names as _reserved_expression_names


def reserved_expression_names() -> set[str]:
    """Return expression-engine names that user variables/constants must not shadow."""
    return _reserved_expression_names()


def is_reserved_expression_name(name: str) -> bool:
    return name.lower() in reserved_expression_names()
