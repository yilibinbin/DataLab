"""Lightweight expression name registry and syntax normalization helpers."""

from __future__ import annotations

import re
from typing import Final


# Keep this import-light registry in sync with both expression engines.
# tests/test_expression_registry.py is part of the release matrix and fails on
# drift while avoiding mpmath/sympy imports in UI metadata paths.
_ALLOWED_FUNCTION_NAMES: Final[tuple[str, ...]] = (
    "Sin",
    "Cos",
    "Tan",
    "Asin",
    "Acos",
    "Atan",
    "Sinh",
    "Cosh",
    "Tanh",
    "Asinh",
    "Acosh",
    "Atanh",
    "Exp",
    "Log",
    "Ln",
    "Log10",
    "Sqrt",
    "Power",
    "Abs",
    "Erf",
    "Gamma",
    "Zeta",
    "Hyp0f1",
    "Hyp1f1",
    "Hyp2f1",
    "PolyLog",
    "BesselJ",
    "BesselY",
    "Airy",
)
_ALLOWED_CONSTANT_NAMES: Final[tuple[str, ...]] = ("Pi", "E")
_BRACKET_CALL_RE: Final = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*\[")
_LOWERCASE_CALL_RE: Final = re.compile(r"\b([a-z][a-zA-Z0-9_]*)\s*[\[(]")


def allowed_function_names() -> tuple[str, ...]:
    """Return allowed Mathematica-style function names in registry source order."""

    return _ALLOWED_FUNCTION_NAMES


def allowed_constant_names() -> tuple[str, ...]:
    """Return allowed expression constant names in registry source order."""

    return _ALLOWED_CONSTANT_NAMES


def reserved_expression_names() -> set[str]:
    """Return lowercase expression-engine names user identifiers must not shadow."""

    return {name.lower() for name in (*_ALLOWED_FUNCTION_NAMES, *_ALLOWED_CONSTANT_NAMES)}


def is_reserved_expression_name(name: str) -> bool:
    return name.lower() in reserved_expression_names()


def normalize_expression(expr: str) -> str:
    """Convert DataLab/Mathematica bracket and power syntax to Python syntax."""

    normalized = _BRACKET_CALL_RE.sub(r"\1(", expr)
    normalized = normalized.replace("]", ")")
    return normalized.replace("^", "**")


def detect_lowercase_allowed_function_calls(expression: str) -> set[str]:
    """Return lowercase calls matching allowed names but missing capitalization."""

    allowed_lower = {name.lower() for name in _ALLOWED_FUNCTION_NAMES}
    matches = _LOWERCASE_CALL_RE.findall(expression or "")
    return {name for name in matches if name.lower() in allowed_lower}
