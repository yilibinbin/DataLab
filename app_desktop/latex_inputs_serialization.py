"""Serialize the on-demand-tex stash (``_last_latex_inputs``) for workspace persistence.

The stash holds mpmath-heavy, mode-specific data (``mp.mpf`` scalars, ``FitResult`` dataclasses,
``UncertainValue`` objects, and nested lists/tuples/dicts). JSON can't carry those directly, so
this module recursively encodes them into a JSON-safe form with small type tags, and decodes
back to the exact originals. ``mp.mpf`` is stored via ``mp.nstr`` at high precision so re-opening
a workspace regenerates identical TeX without recomputing.

Type tags (dict with a single ``__t__`` key):
- ``mpf``   → mpmath float, value stored as a decimal string (full precision)
- ``tuple`` → tuple (JSON only has arrays; we must not silently turn tuples into lists)
- ``uv``    → ``UncertainValue``
- ``fit``   → ``FitResult``
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

import mpmath as mp

from fitting.hp_fitter import FitResult
from shared.precision import MAX_MPMATH_DPS, precision_guard
from shared.uncertainty import UncertainValue

# Working precision used to RECONSTRUCT an mpf from its raw (sign, mantissa, exp) parts. It must
# comfortably exceed the mantissa bit width of any stored value; 1e6 dps (the app's clamp ceiling)
# guarantees the man * 2^exp product is formed without rounding. See _decode.
_MPF_RECONSTRUCT_DPS = 1_000_000


def _encode(obj: Any) -> Any:
    if isinstance(obj, bool):  # bool before int/mpf (bool is an int subclass)
        return obj
    if isinstance(obj, mp.mpf):
        # Store the EXACT binary value as (sign, mantissa, exp) integers — NOT a decimal string
        # via mp.nstr, which capped precision at a fixed digit count AND re-rounded to the ambient
        # mp.dps on decode (two-sided precision loss, review S1). A finite mpf equals
        # (-1)^sign * mantissa * 2^exp exactly; special values (inf/nan) have no finite mantissa
        # so fall back to their string form.
        if mp.isfinite(obj):
            sign, man, exp, _bc = obj._mpf_
            return {"__t__": "mpf", "s": int(sign), "m": str(int(man)), "e": int(exp)}
        return {"__t__": "mpf_special", "v": mp.nstr(obj)}
    if isinstance(obj, FitResult):
        return {
            "__t__": "fit",
            "fields": {f.name: _encode(getattr(obj, f.name)) for f in dataclass_fields(obj)},
        }
    if isinstance(obj, UncertainValue):
        return {
            "__t__": "uv",
            "value": _encode(obj.value),
            "uncertainty": _encode(obj.uncertainty),
            "uncertainty_digits": obj.uncertainty_digits,
        }
    if isinstance(obj, tuple):
        return {"__t__": "tuple", "items": [_encode(x) for x in obj]}
    if isinstance(obj, list):
        return [_encode(x) for x in obj]
    if isinstance(obj, dict):
        # Keys in the stash are always strings; coerce defensively for JSON.
        return {str(k): _encode(v) for k, v in obj.items()}
    if isinstance(obj, (str, int, float)) or obj is None:
        return obj
    # Unknown type: fall back to a string tag so encoding never raises (fail-soft). The decoder
    # returns it verbatim; a builder that needs the real object will simply see a string.
    return {"__t__": "repr", "v": repr(obj)}


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        tag = obj.get("__t__")
        if tag == "mpf":
            # Reconstruct man * 2^exp under a working precision wide enough that the product is
            # formed WITHOUT rounding to the ambient mp.dps — exact regardless of session dps.
            if "m" in obj:
                with precision_guard(_MPF_RECONSTRUCT_DPS, clamp_max=MAX_MPMATH_DPS):
                    value = mp.mpf(int(obj["m"])) * mp.power(2, int(obj["e"]))
                    return -value if int(obj.get("s", 0)) else value
            # Back-compat: an older workspace may hold the legacy decimal-string form. Parse it
            # under high precision so at least the stored digits survive.
            with precision_guard(_MPF_RECONSTRUCT_DPS, clamp_max=MAX_MPMATH_DPS):
                return mp.mpf(obj["v"])
        if tag == "mpf_special":
            return mp.mpf(obj["v"])
        if tag == "tuple":
            return tuple(_decode(x) for x in obj["items"])
        if tag == "uv":
            return UncertainValue(
                _decode(obj["value"]),
                _decode(obj["uncertainty"]),
                uncertainty_digits=obj.get("uncertainty_digits"),
            )
        if tag == "fit":
            return FitResult(**{k: _decode(v) for k, v in obj["fields"].items()})
        if tag == "repr":
            return obj["v"]
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(x) for x in obj]
    return obj


def encode_latex_inputs(store: dict[str, Any] | None) -> dict[str, Any]:
    """Encode the whole ``_last_latex_inputs`` store to a JSON-safe dict (empty if falsy)."""
    if not isinstance(store, dict):
        return {}
    return {str(kind): _encode(inputs) for kind, inputs in store.items()}


def decode_latex_inputs(encoded: dict[str, Any] | None) -> dict[str, Any]:
    """Decode a previously-encoded store back to the original mpmath-bearing structures."""
    if not isinstance(encoded, dict):
        return {}
    return {str(kind): _decode(inputs) for kind, inputs in encoded.items()}
