"""LRU cache for render_fitting_overview PNG bytes — regression tests.

DataLab renders its fitting preview through ``render_fitting_overview``
(matplotlib Agg → PNG bytes → QPixmap). Re-rendering the same plot
costs ~150–300 ms of matplotlib setup/draw work; for repeat calls with
the same inputs (log-scale toggle, LaTeX re-export, tab switch after
navigation away) we should return the cached bytes instead.

These tests pin the cache's correctness contract:
- identical inputs → byte-identical PNG from the cache
- distinct inputs → cache miss
- the cache is additive to `render_fitting_overview`; callers that
  hit the direct function still get live work (the wrapper is a
  separate public entry point)
- byte-identity is an acceptance criterion: matplotlib's PNG output
  is deterministic given identical inputs, so we can assert equality
  on the cached bytes
"""

from __future__ import annotations

import pytest

from fitting.plot_fitting import (
    clear_fit_render_cache,
    fit_render_cache_info,
    render_fitting_overview,
    render_fitting_overview_cached,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_fit_render_cache()
    yield
    clear_fit_render_cache()


def _basic_inputs():
    x_values = [1.0, 2.0, 3.0, 4.0, 5.0]
    y_values = [1.1, 1.9, 3.05, 4.0, 4.95]
    fitted_series = [("linear", [1.0, 2.0, 3.0, 4.0, 5.0])]
    residual_series = [("linear", [0.1, -0.1, 0.05, 0.0, -0.05])]
    return x_values, y_values, fitted_series, residual_series


def test_render_cache_hits_on_repeated_call():
    xs, ys, fitted, residuals = _basic_inputs()
    first = render_fitting_overview_cached(xs, ys, fitted, residuals)
    miss_count = fit_render_cache_info().misses
    second = render_fitting_overview_cached(xs, ys, fitted, residuals)
    info = fit_render_cache_info()
    assert info.hits >= 1, "second identical call must be a cache hit"
    assert info.misses == miss_count, "hit path must not bump miss counter"
    assert first == second, "cached bytes must be byte-identical to first render"


def test_render_cache_misses_on_different_y_values():
    xs, ys, fitted, residuals = _basic_inputs()
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    render_fitting_overview_cached(xs, [y + 0.5 for y in ys], fitted, residuals)
    info = fit_render_cache_info()
    assert info.misses >= 2, "different ys must miss the cache"


def test_render_cache_misses_on_log_scale_change():
    """The log_scale kwarg must participate in the cache key — toggling
    it is a common user action that changes the rendered output."""
    xs, ys, fitted, residuals = _basic_inputs()
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale=None)
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="y")
    info = fit_render_cache_info()
    assert info.misses >= 2, "different log_scale must miss the cache"


def test_render_cache_bounded_size():
    """Pin the LRU max size so a long session doesn't grow unbounded."""
    from fitting.plot_fitting import _FIT_RENDER_CACHE_MAXSIZE

    assert _FIT_RENDER_CACHE_MAXSIZE >= 32
    assert _FIT_RENDER_CACHE_MAXSIZE <= 256


def test_render_cache_bytes_magic_header_is_png():
    """Sanity: the cached bytes are a real PNG, not a partial write."""
    xs, ys, fitted, residuals = _basic_inputs()
    data = render_fitting_overview_cached(xs, ys, fitted, residuals)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "output must be a valid PNG"


def test_render_cache_matches_direct_render():
    """The cache MUST return bytes byte-identical to the uncached
    ``render_fitting_overview`` for identical inputs — otherwise a caller
    who migrates from direct to cached would see silent behavioural drift.
    Pinned here so Task 1.3's byte-identity contract can't regress."""
    xs, ys, fitted, residuals = _basic_inputs()
    direct = render_fitting_overview(xs, ys, fitted, residuals)
    cached = render_fitting_overview_cached(xs, ys, fitted, residuals)
    assert direct == cached, "cached render must match direct render byte-for-byte"


def test_render_cache_dpi_clamped_to_safe_range():
    """A caller passing ``dpi=100000`` (OOM attack surface for matplotlib
    Agg) must be clamped to the same ceiling as direct calls. Confirm
    (a) the call returns a valid PNG, (b) the result is identical to the
    clamped-dpi direct call."""
    xs, ys, fitted, residuals = _basic_inputs()
    cached = render_fitting_overview_cached(xs, ys, fitted, residuals, dpi=100_000)
    # Same call with a post-clamp dpi should collide in the cache.
    cached_at_ceiling = render_fitting_overview_cached(
        xs, ys, fitted, residuals, dpi=600
    )
    assert cached == cached_at_ceiling, (
        "dpi beyond the safe ceiling must collapse into the clamped key"
    )
    assert cached[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_cache_log_scale_normalized():
    """``log_scale`` variants that produce identical renders
    (``"x"``/``"X"``/``"x "``) must collapse to the same cache entry —
    otherwise an attacker could exhaust the LRU by cycling variants."""
    xs, ys, fitted, residuals = _basic_inputs()
    clear_fit_render_cache()
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="x")
    miss_baseline = fit_render_cache_info().misses
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="X")
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="x ")
    info = fit_render_cache_info()
    assert info.misses == miss_baseline, (
        "log_scale casing/whitespace must not create distinct cache entries"
    )
    assert info.hits >= 2


def test_render_cache_log_scale_xy_same_as_yx():
    """``"xy"`` and ``"yx"`` toggle both scales identically — one entry."""
    xs, ys, fitted, residuals = _basic_inputs()
    clear_fit_render_cache()
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="xy")
    miss_baseline = fit_render_cache_info().misses
    render_fitting_overview_cached(xs, ys, fitted, residuals, log_scale="yx")
    info = fit_render_cache_info()
    assert info.misses == miss_baseline, (
        "log_scale='xy' and 'yx' must collapse — both toggle both axes"
    )


def test_render_cache_uncertainties_none_vs_empty_distinct():
    """``uncertainties=None`` (renderer takes scatter branch) and
    ``uncertainties=[]`` (renderer validates length — raises for
    non-empty x_values) are DIFFERENT; the cache must not collapse
    them."""
    xs, ys, fitted, residuals = _basic_inputs()
    # None = no error bars; should succeed
    render_fitting_overview_cached(
        xs, ys, fitted, residuals, uncertainties=None
    )
    # Empty [] with non-empty xs: the uncached renderer raises
    # "uncertainties must have the same length as x_values". The cache
    # must route to the uncached path (and also raise) rather than
    # returning the None-path PNG from its cache.
    with pytest.raises(ValueError):
        render_fitting_overview_cached(
            xs, ys, fitted, residuals, uncertainties=[]
        )


def test_render_cache_nan_values_still_hit():
    """NaN defeats ``float('nan') == float('nan')``, so a naive
    tuple-of-floats key would never hit for NaN-containing data. The
    cache must use a NaN-stable encoding."""
    xs = [1.0, 2.0, 3.0]
    ys = [1.0, float("nan"), 3.0]
    fitted = [("linear", [1.0, 2.0, 3.0])]
    residuals = [("linear", [0.0, float("nan"), 0.0])]
    clear_fit_render_cache()
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    miss_baseline = fit_render_cache_info().misses
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    info = fit_render_cache_info()
    assert info.misses == miss_baseline, (
        "identical NaN-containing inputs must hit the cache — a raw "
        "float('nan') key would miss forever"
    )
    assert info.hits >= 1


def test_render_cache_clear_resets_counters():
    """``clear_fit_render_cache`` must reset hits/misses — callers rely
    on this to start a clean measurement window."""
    xs, ys, fitted, residuals = _basic_inputs()
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    assert fit_render_cache_info().hits >= 1
    clear_fit_render_cache()
    info = fit_render_cache_info()
    assert info.hits == 0
    assert info.misses == 0
    assert info.currsize == 0


def test_render_cache_export_path_bypasses_cache(tmp_path):
    """When export_pdf_path or export_eps_path is set, the function must
    skip the cache so the file-write side effect actually fires."""
    xs, ys, fitted, residuals = _basic_inputs()
    # Prime the cache with a regular (cached) call:
    render_fitting_overview_cached(xs, ys, fitted, residuals)
    hits_before = fit_render_cache_info().hits
    pdf_path = tmp_path / "out.pdf"
    render_fitting_overview_cached(
        xs, ys, fitted, residuals, export_pdf_path=str(pdf_path)
    )
    # The export-path call must NOT count as a cache hit — it bypassed
    # the lookup entirely. (It still invokes the uncached renderer which
    # writes the PDF.)
    hits_after = fit_render_cache_info().hits
    assert hits_after == hits_before, (
        "export-path calls must bypass the cache to fire the file-write side effect"
    )
    assert pdf_path.exists(), "PDF side effect must have fired"
