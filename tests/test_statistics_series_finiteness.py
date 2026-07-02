"""series_with_mean renderer must filter non-finite values (audit F15).

The sibling statistics renderers (histogram/box/qq) drop NaN/Inf; the main
series_with_mean renderer did not, so a non-finite value could reach matplotlib
and blank the plot. This test feeds a NaN and asserts a real PNG is produced.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mpmath import mp

from shared.plotting import (
    StatisticsPlotLabels,
    StatisticsPlotSpec,
    render_statistics_plot_from_spec,
)


def _labels() -> StatisticsPlotLabels:
    return StatisticsPlotLabels(
        data="data",
        mean="mean",
        mean_band="band",
        x_axis="index",
        y_axis="value",
        title="series",
        median="median",
        histogram_title="hist",
        box_title="box",
        qq_title="qq",
        weighted_residual_title="wr",
        frequency_axis="freq",
        theoretical_quantile_axis="tq",
        sample_quantile_axis="sq",
        residual_axis="res",
        zero_line="zero",
        threshold_line="thr",
    )


def test_series_with_mean_filters_non_finite_values():
    spec = StatisticsPlotSpec(
        values=[mp.mpf("1"), mp.nan, mp.mpf("3"), mp.mpf("2")],
        sigmas=[None, None, None, None],
        mean=mp.mpf("2"),
        std=mp.mpf("1"),
        std_mean=mp.mpf("0.5"),
        labels=_labels(),
        plot_key="statistics.series_with_mean",
    )
    png = render_statistics_plot_from_spec(spec)
    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_series_with_mean_still_renders_all_finite():
    spec = StatisticsPlotSpec(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        sigmas=[None, None, None],
        mean=mp.mpf("2"),
        std=mp.mpf("1"),
        std_mean=mp.mpf("0.5"),
        labels=_labels(),
        plot_key="statistics.series_with_mean",
    )
    png = render_statistics_plot_from_spec(spec)
    assert png is not None and png.startswith(b"\x89PNG")
