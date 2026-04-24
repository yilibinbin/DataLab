"""Residual comparison view (Phase 2 #8) — regression tests.

After auto-fit, DataLab shows each model's residuals separately. The
residual-comparison view overlays them on a single axis so the user can
eyeball which model tracks best across x. This is a purely presentation-
layer addition — the underlying residual arrays come from the existing
auto-fit worker; we just give them a new render entry point.

Contract:
- ``render_residual_diff`` accepts x values + a list of (label, residuals)
  tuples and returns PNG bytes.
- Input validation: mismatched lengths raise ValueError; empty input
  returns a blank-but-valid PNG (so callers don't need to null-check).
- Color cycle: distinct colors up to 10 series; beyond that, repeats
  from the start (rather than raising).
- Output is byte-deterministic for identical inputs (required for the
  PNG cache introduced in Phase 1 #4 to work at this layer too).
"""

from __future__ import annotations

import pytest


def test_render_residual_diff_returns_png_bytes():
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    series = [
        ("linear", [0.1, -0.1, 0.05, 0.0, -0.05]),
        ("quadratic", [0.02, -0.03, 0.01, 0.0, -0.02]),
    ]
    png = render_residual_diff(xs, series)
    assert isinstance(png, (bytes, bytearray))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_residual_diff_byte_deterministic():
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 2.0, 3.0]
    series = [("a", [0.1, 0.0, -0.1]), ("b", [-0.05, 0.02, -0.02])]
    first = render_residual_diff(xs, series)
    second = render_residual_diff(xs, series)
    assert first == second, "identical inputs must produce byte-identical PNG"


def test_render_residual_diff_empty_series_returns_valid_png():
    """Empty series still returns a PNG with an empty axes — callers
    don't have to null-check."""
    from fitting.plot_fitting import render_residual_diff

    png = render_residual_diff([1.0, 2.0], [])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_residual_diff_rejects_mismatched_lengths():
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 2.0, 3.0]
    series = [("bad", [0.1, 0.2])]  # 2 values, not 3
    with pytest.raises(ValueError, match="residuals"):
        render_residual_diff(xs, series)


def test_render_residual_diff_rejects_empty_xs_with_nonempty_series():
    from fitting.plot_fitting import render_residual_diff

    with pytest.raises(ValueError):
        render_residual_diff([], [("a", [0.1])])


def test_render_residual_diff_handles_many_series_without_error():
    """More than 10 series should cycle colors rather than raise."""
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 2.0, 3.0]
    series = [
        (f"model_{i}", [0.01 * i, -0.02 * i, 0.015 * i])
        for i in range(15)
    ]
    png = render_residual_diff(xs, series)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_residual_diff_dpi_clamped():
    """Same DPI clamp as render_fitting_overview — DoS defense."""
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 2.0]
    series = [("a", [0.1, 0.0])]
    # Must not raise, must not allocate gigabytes
    png = render_residual_diff(xs, series, dpi=100_000)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_residual_diff_accepts_log_scale_x():
    from fitting.plot_fitting import render_residual_diff

    xs = [1.0, 10.0, 100.0]
    series = [("a", [0.1, 0.05, 0.01])]
    png = render_residual_diff(xs, series, log_scale="x")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_residual_diff_accepts_mpmath_values():
    """DataLab's auto-fit worker produces mp.mpf residuals — the
    renderer must float-convert transparently."""
    from mpmath import mp

    from fitting.plot_fitting import render_residual_diff

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    series = [("hp", [mp.mpf("0.1"), mp.mpf("-0.1"), mp.mpf("0.05")])]
    png = render_residual_diff(xs, series)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
