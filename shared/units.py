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
import math
from typing import Any, Optional

from mpmath import mp

from .precision import precision_guard

__all__ = [
    "HAS_PINT",
    "convert_to_si",
    "format_quantity_latex",
    "get_registry",
    "parse_quantity",
    "to_siunitx",
    "unit_backend_metadata",
]

_logger = logging.getLogger(__name__)

try:
    import pint  # noqa: F401

    _pint: Any = pint
    HAS_PINT = True
except ImportError:
    _pint = None
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


def unit_backend_metadata() -> dict[str, str | bool]:
    """Return deterministic metadata for the optional unit backend."""

    if not HAS_PINT:
        return {"backend": "none", "available": False, "version": ""}
    return {
        "backend": "pint",
        "available": True,
        "version": str(getattr(_pint, "__version__", "")),
    }


def _magnitude_text(magnitude: Any, *, precision_digits: int | None = None) -> str:
    if isinstance(magnitude, bool) or magnitude is None:
        raise ValueError(f"magnitude must be a finite number, got {magnitude!r}")
    if isinstance(magnitude, mp.mpf):
        digits = (
            max(1, int(precision_digits))
            if precision_digits is not None
            else _mpf_compact_display_digits(magnitude)
        )
        with precision_guard(digits + 10):
            text = str(mp.nstr(magnitude, n=digits)).strip()
    else:
        text = str(magnitude).strip()
    if not text:
        raise ValueError("magnitude must be a finite number, got an empty value")
    parse_digits = max(80, len(text) + 10)
    try:
        with precision_guard(parse_digits):
            parsed = mp.mpf(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"magnitude must be a finite number, got {magnitude!r}: {exc}") from exc
    if not mp.isfinite(parsed):
        raise ValueError(f"magnitude must be finite, got {magnitude!r}")
    return text


def _mpf_compact_display_digits(value: mp.mpf) -> int:
    try:
        _, mantissa, exponent, bit_count = value._mpf_  # noqa: SLF001 - mpmath exposes no public bitcount.
        mantissa = int(mantissa)
        exponent = int(exponent)
        bit_count = int(bit_count)
    except (AttributeError, IndexError, TypeError, ValueError):
        return 50
    if mantissa == 0 or bit_count <= 0:
        return 15
    significant_digits = int(math.ceil(bit_count * math.log10(2)))
    high_bit_index = bit_count + exponent - 1
    integer_digits = max(1, int(math.floor(high_bit_index * math.log10(2))) + 2)
    return min(50, max(15, significant_digits, min(50, integer_digits)))


def _pint_unit_latex(unit: str) -> str | None:
    if not HAS_PINT or not unit:
        return None
    registry = get_registry()
    try:
        unit_obj = registry.Unit(unit)
        return f"{unit_obj:Lx}"
    except Exception as exc:  # noqa: BLE001
        _logger.debug("unit LaTeX formatting failed for %r: %s", unit, exc)
        return None


def format_quantity_latex(
    magnitude: Any,
    unit: str,
    *,
    use_siunitx: bool = True,
    precision_digits: int | None = None,
) -> str:
    """Render a quantity without converting high-precision magnitudes to float."""

    magnitude_value = _magnitude_text(magnitude, precision_digits=precision_digits)
    unit_text = str(unit or "").strip()
    if use_siunitx:
        unit_latex = _pint_unit_latex(unit_text)
        if unit_latex:
            return rf"\SI{{{magnitude_value}}}{{{unit_latex}}}"

    escaped = _escape_unit_for_text(unit_text)
    if escaped:
        return rf"\num{{{magnitude_value}}}\,\text{{{escaped}}}"
    return rf"\num{{{magnitude_value}}}"


def to_siunitx(magnitude: Any, unit: str) -> str:
    """Render a (magnitude, unit) pair as LaTeX.

    When pint is available, emit ``\\SI{magnitude}{unit-in-pint-syntax}``
    via pint's own LaTeX helper. When pint is absent, fall back to
    ``\\num{magnitude}\\,\\text{escaped-unit}`` — usable with the
    ``siunitx`` package at minimum, and with plain ``amsmath`` as a
    reasonable approximation.
    """
    return format_quantity_latex(magnitude, unit)
