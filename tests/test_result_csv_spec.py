"""The result-CSV spec is the single source of truth for each result kind's
base CSV headers + export filename, shared by the first-render path (_show_*
mixins) and the reformat path (_refresh_display_format) so they cannot drift
(audit R3 CSV-spec dedup)."""

from __future__ import annotations

import inspect
import linecache

from app_desktop.result_csv_spec import (
    _RESULT_CSV_SPEC,
    result_csv_filename,
    result_csv_headers,
)


def test_result_csv_headers_returns_fresh_mutable_copy():
    a = result_csv_headers("extrapolation")
    a.append("EXTRA")
    b = result_csv_headers("extrapolation")
    assert b == ["index", "value", "uncertainty", "latex"], "spec must not be mutated by callers"
    assert "EXTRA" not in b


def test_result_csv_spec_values():
    assert result_csv_headers("extrapolation") == ["index", "value", "uncertainty", "latex"]
    assert result_csv_filename("extrapolation") == "extrapolation_results.csv"
    assert result_csv_headers("statistics") == ["batch", "metric", "value", "uncertainty"]
    assert result_csv_filename("statistics") == "statistics_results.csv"
    assert result_csv_headers("fit_single")[:4] == ["batch", "section", "name", "value"]
    assert result_csv_filename("fit_single") == "fitting_results.csv"


def test_reformat_and_first_render_read_the_same_spec():
    """Both the reformat path (window._refresh_display_format) and the first-render
    paths (window_*_mixin _show_* methods) must source headers/filename from the
    spec — no hardcoded '..._results.csv' string literals should remain in those
    methods, or the two paths can silently diverge again."""
    from app_desktop import window as window_mod
    from app_desktop import window_extrapolation_mixin, window_statistics_mixin

    # inspect.getsource reads through linecache; drop stale entries a prior test
    # may have left so getsource re-reads the current source (see #72).
    linecache.clearcache()
    refresh_src = inspect.getsource(window_mod.ExtrapolationWindow._refresh_display_format)
    # The spec's kinds must be routed through the accessors, not re-hardcoded.
    for kind in _RESULT_CSV_SPEC:
        fname = result_csv_filename(kind)
        # A bare filename literal next to _set_csv_data in the reformat method
        # would mean the literal was re-hardcoded rather than sourced from spec.
        assert f'suggestion="{fname}"' not in refresh_src, (
            f"reformat path hardcodes {fname} instead of result_csv_filename({kind!r})"
        )

    extrap_src = inspect.getsource(window_extrapolation_mixin)
    stats_src = inspect.getsource(window_statistics_mixin)
    # The extrapolation/statistics first-render _show_* paths use the accessors.
    assert 'result_csv_filename("extrapolation")' in extrap_src
    assert 'result_csv_filename("statistics")' in stats_src
