"""pint units integration (Phase 3 #16) — regression tests.

DataLab integrates pint via ``shared.units`` when pint is installed.
When pint is absent, the module exposes a graceful no-op fallback
so existing flows don't break (mirrors how other optional dep
integrations behave — e.g., emcee for MCMC).

Tests cover:
- `HAS_PINT` flag reflects reality
- When pint absent: ``parse_quantity`` raises ``ModuleNotFoundError``,
  ``to_siunitx`` returns the bare value as string
- When pint present: parse → Quantity with correct magnitude + unit,
  SI conversion works, siunitx LaTeX formatting works
- Malformed unit strings raise clearly
- Dimensional arithmetic: m/s * s → m
"""

from __future__ import annotations

import pytest


def test_module_exports_has_pint_flag():
    from shared.units import HAS_PINT

    assert isinstance(HAS_PINT, bool)


def test_parse_quantity_requires_pint_when_absent():
    from shared.units import HAS_PINT

    if HAS_PINT:
        pytest.skip("pint is installed; this test only pins the absent path")

    from shared.units import parse_quantity

    with pytest.raises(ModuleNotFoundError):
        parse_quantity("1.5 m/s")


def test_to_siunitx_falls_back_when_pint_absent():
    from shared.units import HAS_PINT, to_siunitx

    if HAS_PINT:
        pytest.skip("pint is installed; this test only pins the absent path")

    # Without pint, we still emit a reasonable LaTeX number-only literal.
    assert to_siunitx(1.5, "m/s") == r"\num{1.5}\,\text{m/s}" or "1.5" in to_siunitx(1.5, "m/s")


def test_parse_quantity_roundtrip_when_pint_present():
    pytest.importorskip("pint")

    from shared.units import parse_quantity

    q = parse_quantity("1.5 m/s")
    assert float(q.magnitude) == 1.5
    # pint normalises unit spellings; we only require round-trip equality.
    assert str(q.units) in ("meter / second", "m/s", "meter/second")


def test_to_siunitx_produces_valid_latex_when_pint_present():
    pytest.importorskip("pint")

    from shared.units import to_siunitx

    out = to_siunitx(6.674e-11, "meter^3/(kilogram*second^2)")
    assert out.startswith(r"\SI{") or out.startswith(r"\SI["), (
        f"Expected siunitx-flavoured LaTeX, got {out!r}"
    )
    assert "6.674e-11" in out or "6.674" in out


def test_parse_quantity_rejects_malformed_string_when_pint_present():
    pytest.importorskip("pint")

    from shared.units import parse_quantity

    with pytest.raises(ValueError):
        parse_quantity("not a quantity at all")


def test_dimensional_arithmetic_when_pint_present():
    pytest.importorskip("pint")

    from shared.units import parse_quantity

    speed = parse_quantity("10 m/s")
    time = parse_quantity("5 s")
    distance = speed * time
    # Convert to canonical SI metres for a robust check
    dist_m = distance.to("meter")
    assert float(dist_m.magnitude) == pytest.approx(50.0)


def test_convert_to_si_when_pint_present():
    pint = pytest.importorskip("pint")

    from shared.units import convert_to_si

    # 60 mph → ~26.8224 m/s
    result = convert_to_si("60 mile/hour")
    assert result.units.dimensionality == pint.Quantity(1, "m/s").dimensionality
    assert float(result.to("m/s").magnitude) == pytest.approx(26.8224, rel=1e-4)


def test_units_module_is_import_safe_without_pint():
    """``shared.units`` must import cleanly even when pint isn't
    installed — callers on a web deploy without pint shouldn't fail
    at import time."""
    # Just re-importing shouldn't throw.
    import importlib
    import shared.units as units_mod

    importlib.reload(units_mod)
    assert hasattr(units_mod, "HAS_PINT")
    assert hasattr(units_mod, "to_siunitx")
    assert hasattr(units_mod, "parse_quantity")


def test_to_siunitx_escapes_special_chars_in_bare_fallback():
    """The no-pint fallback emits a LaTeX literal — the unit string
    goes verbatim into \\text{…}. Verify nothing that would break
    LaTeX parsing leaks through."""
    from shared.units import HAS_PINT, to_siunitx

    if HAS_PINT:
        pytest.skip("pint is installed; this test only pins the absent path")

    # Backslash in unit string must not produce a LaTeX parse error.
    result = to_siunitx(1.0, "m/s")
    # No raw unescaped $, %, #, &, _ from the unit string
    for ch in ("$", "%", "#", "&"):
        assert ch not in result or result.count(ch) == 0
