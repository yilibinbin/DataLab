from __future__ import annotations

import warnings

import pytest

import mpmath as mp

from app_web.logic import plots


def test_web_plot_generation_produces_png_bytes_when_matplotlib_available():
    pytest.importorskip("matplotlib")

    extrap = plots._render_extrapolation_plot(
        row_values=(mp.mpf("1.0"), mp.mpf("1.1"), mp.mpf("1.2")),
        extrap_value=mp.mpf("1.25"),
        sigma=mp.mpf("0.05"),
        idx=1,
        lang="en",
    )
    assert extrap is not None
    assert extrap.startswith(b"\x89PNG")

    class _Res:
        def __init__(self, contributions):
            self.contributions = contributions

    contrib = plots._render_contribution_plot(
        results=[_Res({"A": mp.mpf("1"), "B": mp.mpf("2")})],
        lang="en",
    )
    assert contrib is not None
    assert contrib.startswith(b"\x89PNG")

    stats = plots._render_statistics_plot(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        sigmas=[mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.1")],
        stats_result={"mean": mp.mpf("2"), "std_mean": mp.mpf("0.1")},
        lang="en",
    )
    assert stats is not None
    assert stats.startswith(b"\x89PNG")


def test_web_statistics_plot_routes_shared_spec(monkeypatch):
    from shared import plotting

    captured = {}

    def fake_render(spec):
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nweb"

    monkeypatch.setattr(plotting, "render_statistics_plot_from_spec", fake_render)

    png = plots._render_statistics_plot(
        values=[mp.mpf("1"), mp.mpf("2")],
        sigmas=[mp.mpf("0.1"), None],
        stats_result={"mean": mp.mpf("1.5"), "std_mean": mp.mpf("0.5")},
        lang="en",
    )

    assert png == b"\x89PNG\r\n\x1a\nweb"
    spec = captured["spec"]
    assert spec.values == (mp.mpf("1"), mp.mpf("2"))
    assert spec.sigmas == (mp.mpf("0.1"), None)
    assert spec.mean == mp.mpf("1.5")
    assert spec.std_mean == mp.mpf("0.5")
    assert spec.labels.title == "Statistical mean"
    assert spec.labels.mean_band == "Mean ± standard error"
    assert spec.batch_suffix == ""


def test_web_statistics_plot_gallery_routes_shared_specs(monkeypatch):
    from shared import plotting

    captured = {}

    def fake_render(specs):
        captured["specs"] = specs
        return [b"\x89PNG\r\n\x1a\nseries", b"\x89PNG\r\n\x1a\nhist"]

    monkeypatch.setattr(plotting, "render_statistics_plots_from_specs", fake_render)

    pngs = plots._render_statistics_plots(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("4")],
        sigmas=[mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")],
        stats_result={
            "mode": "weighted_sigma",
            "mean": mp.mpf("2"),
            "std": mp.mpf("1.5"),
            "std_mean": mp.mpf("0.5"),
            "median": mp.mpf("2"),
            "weighted_consistency_dof": 2,
        },
        lang="en",
    )

    assert pngs == [b"\x89PNG\r\n\x1a\nseries", b"\x89PNG\r\n\x1a\nhist"]
    specs = captured["specs"]
    assert [spec.plot_key for spec in specs] == [
        "statistics.series_with_mean",
        "statistics.histogram",
        "statistics.box",
        "statistics.qq",
        "statistics.weighted_residual",
    ]
    assert specs[0].labels.title == "Statistical mean"
    assert specs[1].labels.histogram_title == "Histogram"


def test_web_statistics_plot_gallery_omits_weighted_residual_for_single_weighted_pair(monkeypatch):
    from shared import plotting

    captured = {}

    def fake_render(specs):
        captured["specs"] = specs
        return []

    monkeypatch.setattr(plotting, "render_statistics_plots_from_specs", fake_render)

    plots._render_statistics_plots(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("4")],
        sigmas=[mp.mpf("0.1"), None, mp.mpf("0")],
        stats_result={
            "mode": "weighted_sigma",
            "mean": mp.mpf("1"),
            "std": mp.mpf("0"),
            "std_mean": mp.mpf("0"),
            "weighted_consistency_dof": 0,
        },
        lang="en",
    )

    assert "statistics.weighted_residual" not in [spec.plot_key for spec in captured["specs"]]


def test_web_statistics_plot_gallery_does_not_raise_for_non_finite_values():
    pngs = plots._render_statistics_plots(
        values=[mp.nan, mp.mpf("1")],
        sigmas=[None, None],
        stats_result={
            "mode": "mean_sample",
            "mean": mp.mpf("1"),
            "std": mp.nan,
            "std_mean": mp.nan,
        },
        lang="en",
    )

    assert isinstance(pngs, list)
    assert all(png.startswith(b"\x89PNG\r\n\x1a\n") for png in pngs)


def test_web_contribution_plot_routes_shared_spec(monkeypatch):
    from shared import plotting

    class _Res:
        def __init__(self, contributions):
            self.contributions = contributions

    captured = {}

    def fake_render(spec):
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nweb-contribution"

    monkeypatch.setattr(plotting, "render_error_contribution_plot_from_spec", fake_render)

    png = plots._render_contribution_plot(
        results=[
            _Res({"B": mp.mpf("3"), "A": mp.mpf("1")}),
            _Res({"A": mp.mpf("1")}),
        ],
        lang="en-US",
    )

    assert png == b"\x89PNG\r\n\x1a\nweb-contribution"
    spec = captured["spec"]
    assert spec.labels == ("B", "A")
    assert spec.percents == pytest.approx((60.0, 40.0))
    assert spec.cumulative_percents == pytest.approx((60.0, 100.0))
    assert spec.plot_labels.x_axis == "Uncertainty contribution (%)"
    assert spec.plot_labels.title == "Uncertainty contribution breakdown"
    assert spec.plot_labels.cumulative_label == "Cumulative contribution"
    assert spec.title_suffix == ""


def test_web_contribution_plot_returns_none_for_zero_total_variance(monkeypatch):
    from shared import plotting

    class _Res:
        def __init__(self, contributions):
            self.contributions = contributions

    def fail_render(_spec):
        raise AssertionError("zero-variance Web contribution plot should not render")

    monkeypatch.setattr(plotting, "render_error_contribution_plot_from_spec", fail_render)

    png = plots._render_contribution_plot(
        results=[
            _Res({"B": mp.mpf("0"), "A": mp.mpf("0")}),
        ],
        lang="en",
    )

    assert png is None


def test_web_monte_carlo_distribution_plot_routes_shared_spec(monkeypatch):
    from shared import plotting

    captured = {}

    def fake_render(spec):
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nweb-distribution"

    monkeypatch.setattr(plotting, "render_monte_carlo_distribution_plot_from_spec", fake_render)

    png = plots._render_monte_carlo_distribution_plot(
        {
            "schema": "datalab.monte_carlo_distribution_summary",
            "schema_version": 1,
            "requested_sample_count": 100,
            "evaluated_sample_count": 100,
            "accepted_sample_count": 100,
            "rejected_sample_count": 0,
            "finite_sample_count": 100,
            "mean": "1.0",
            "std": "0.2",
            "histogram": {"bin_edges": ["0.0", "1.0", "2.0"], "counts": [50, 50]},
            "percentiles": {"2.5": "0.1", "50": "1.0", "97.5": "1.9"},
        },
        lang="en-US",
        row_index=2,
    )

    assert png == b"\x89PNG\r\n\x1a\nweb-distribution"
    spec = captured["spec"]
    assert spec.labels.title == "Monte Carlo distribution"
    assert spec.labels.x_axis == "Result value"
    assert spec.labels.y_axis == "Sample count"
    assert spec.title_suffix == "row 2"


def test_web_monte_carlo_distribution_plot_fails_closed_for_invalid_summary(monkeypatch):
    from shared import plotting

    def fail_render(_spec):
        raise AssertionError("invalid distribution summary should not render")

    monkeypatch.setattr(plotting, "render_monte_carlo_distribution_plot_from_spec", fail_render)

    assert plots._render_monte_carlo_distribution_plot({"schema": "wrong"}, lang="en", row_index=1) is None


def test_web_plot_generation_uses_cjk_safe_font_when_rcparams_are_clobbered():
    pytest.importorskip("matplotlib")
    from shared.plotting import cjk_font_properties, rcParams

    if cjk_font_properties() is None:
        pytest.skip("No CJK-capable Matplotlib font available in this environment.")

    class _Res:
        def __init__(self, contributions):
            self.contributions = contributions

    previous_family = rcParams["font.family"]
    previous_sans = rcParams["font.sans-serif"]
    try:
        rcParams["font.family"] = ["DejaVu Sans"]
        rcParams["font.sans-serif"] = ["DejaVu Sans"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            contrib = plots._render_contribution_plot(
                results=[_Res({"A": mp.mpf("1"), "B": mp.mpf("2")})],
                lang="zh",
            )
            stats = plots._render_statistics_plot(
                values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
                sigmas=[mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.1")],
                stats_result={"mean": mp.mpf("2"), "std_mean": mp.mpf("0.1")},
                lang="zh",
            )
    finally:
        rcParams["font.family"] = previous_family
        rcParams["font.sans-serif"] = previous_sans

    missing_glyph_warnings = [
        str(item.message)
        for item in caught
        if "glyph" in str(item.message).lower() and "missing" in str(item.message).lower()
    ]
    assert contrib is not None
    assert stats is not None
    assert missing_glyph_warnings == []
