"""The web compute routes must CLAMP the user-supplied mpmath precision (dps).

mp.dps is process-global and each compute route holds a serial lock while it runs, so an unbounded
precision value (e.g. 100_000_000) would set an absurd precision and stall the worker — a trivial
DoS (audit A1). `_parse_precision` clamps at parse time to [MIN_MPMATH_DPS, MAX_MPMATH_DPS], and
every compute route parses its precision field through it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("flask")

from app_web.logic.common import _parse_precision
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS


def test_parse_precision_clamps_pathological_high_value() -> None:
    # The DoS vector: an absurd precision must be bounded to the app's ceiling.
    assert _parse_precision("100000000") == MAX_MPMATH_DPS


def test_parse_precision_clamps_below_minimum() -> None:
    assert _parse_precision("5") == MIN_MPMATH_DPS


def test_parse_precision_passes_in_range_value() -> None:
    assert _parse_precision("80") == 80


def test_parse_precision_returns_default_when_absent() -> None:
    assert _parse_precision(None) is None
    assert _parse_precision("") is None
    assert _parse_precision(None, 80) == 80


def test_every_compute_route_parses_precision_through_the_clamp() -> None:
    """Guardrail: the compute routes must use the clamping `_parse_precision`, not the raw
    `_parse_int`, for their *_mp_precision fields — otherwise the clamp is bypassed."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app_web" / "logic"
    fields = {
        "extrapolation.py": "mp_precision",
        "error_propagation.py": "error_mp_precision",
        "statistics.py": "stats_mp_precision",
        "root_solving.py": "root_mp_precision",
        "fitting.py": "fit_mp_precision",
    }
    for filename, field in fields.items():
        source = (root / filename).read_text(encoding="utf-8")
        assert f'_parse_precision(form.get("{field}"))' in source, (
            f"{filename}: compute-precision field '{field}' must be parsed via _parse_precision "
            f"(clamped), not _parse_int"
        )
        assert f'_parse_int(form.get("{field}"))' not in source, (
            f"{filename}: '{field}' still parsed via unclamped _parse_int"
        )
