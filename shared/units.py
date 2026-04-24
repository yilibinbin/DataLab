"""Optional pint units integration.

DataLab works with or without ``pint`` installed. When pint is
present, ``parse_quantity`` / ``convert_to_si`` / ``to_siunitx``
produce real ``pint.Quantity`` objects with full dimensional
arithmetic and LaTeX-friendly output. When pint is absent, the
bare-number fallbacks keep callers working without any unit tracking.

Usage pattern expected:

    from shared.units import HAS_PINT, parse_quantity, to_siunitx
    if HAS_PINT:
        q = parse_quantity(user_text)  # pint.Quantity
        latex = to_siunitx(q.magnitude, str(q.units))
    else:
        latex = to_siunitx(user_number, user_unit_string)

This module never raises at import time — the pint-import is wrapped
in a try/except so web deploys that skipped ``pint`` in
requirements can still load the module.

Why pint and not sympy's units: pint has a dedicated dimensional
system, a canonical unit registry, and first-class LaTeX/siunitx
formatting. sympy.units would require per-dimension definitions
and duplicate the siunitx logic.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

__all__ = [
    "HAS_PINT",
    "convert_to_si",
    "get_registry",
    "parse_quantity",
    "to_siunitx",
]

_logger = logging.getLogger(__name__)

try:
    import pint as _pint  # noqa: F401

    HAS_PINT = True
except ImportError:
    _pint = None  # type: ignore[assignment]
    HAS_PINT = False


_registry: Optional[Any] = None  # typed Any since pint may be absent


def get_registry() -> Any:
    """Return the lazily-initialised ``pint.UnitRegistry``.

    Raises ``ModuleNotFoundError`` if pint isn't installed — callers
    should guard on ``HAS_PINT`` first.
    """
    global _registry
    if not HAS_PINT:
        raise ModuleNotFoundError(
            "pint is not installed. Add 'pint' to your requirements "
            "to enable unit-tracked arithmetic in DataLab."
        )
    if _registry is None:
        _registry = _pint.UnitRegistry()
    return _registry


def parse_quantity(text: str) -> Any:
    """Parse a ``"<number> <unit>"`` string to a ``pint.Quantity``.

    Raises:
    - ``ModuleNotFoundError`` if pint isn't installed
    - ``ValueError`` if the input cannot be parsed as a pint quantity
    """
    if not HAS_PINT:
        raise ModuleNotFoundError(
            "pint is not installed — parse_quantity requires it."
        )
    registry = get_registry()
    try:
        return registry.Quantity(text)
    except Exception as exc:  # pint errors vary by version
        raise ValueError(
            f"Could not parse {text!r} as a pint quantity: {exc}"
        ) from exc


def convert_to_si(text: str) -> Any:
    """Parse a quantity and convert to its SI base representation.

    Canonicalises the input to the pint registry's base units (metres,
    kilograms, seconds, amperes, kelvins, moles, candelas) so any
    downstream mathematical operation uses a consistent dimensional
    basis.
    """
    q = parse_quantity(text)
    return q.to_base_units()


# siunitx LaTeX escape table for the bare-number fallback. Unit
# strings can contain characters that LaTeX parses as special tokens;
# when we embed into ``\text{…}`` we at minimum neutralise the
# obvious culprits so a user-supplied string like "m/s%" doesn't
# accidentally start a LaTeX comment.
_LATEX_SPECIAL_ESCAPES = str.maketrans({
    "$": r"\$",
    "%": r"\%",
    "#": r"\#",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
})


def _escape_unit_for_text(unit: str) -> str:
    """Escape LaTeX specials in a unit string for the ``\\text{…}``
    fallback formatting. Backslashes are left alone — siunitx users
    often want to pass ``\\metre`` etc. through the unit field."""
    return (unit or "").translate(_LATEX_SPECIAL_ESCAPES)


def to_siunitx(magnitude: Any, unit: str) -> str:
    """Render a (magnitude, unit) pair as LaTeX.

    When pint is available, emit ``\\SI{magnitude}{unit-in-pint-syntax}``
    via pint's own LaTeX helper. When pint is absent, fall back to
    ``\\num{magnitude}\\,\\text{escaped-unit}`` — usable with the
    ``siunitx`` package at minimum, and with plain ``amsmath`` as a
    reasonable approximation.
    """
    try:
        mag_float = float(magnitude)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"magnitude must be a number, got {magnitude!r}: {exc}"
        ) from exc

    if HAS_PINT:
        registry = get_registry()
        try:
            q = mag_float * registry(unit)
            # pint's "L" LaTeX format spec emits a siunitx-compatible string.
            return f"{q:Lx}"
        except Exception as exc:  # noqa: BLE001
            _logger.debug(
                "to_siunitx: pint formatting failed for %r %r: %s",
                mag_float, unit, exc,
            )
            # Fall through to the bare fallback so a caller with a
            # non-pint-recognised unit string still gets useful output.

    escaped = _escape_unit_for_text(unit)
    if escaped:
        return rf"\num{{{mag_float}}}\,\text{{{escaped}}}"
    return rf"\num{{{mag_float}}}"
