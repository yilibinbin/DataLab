"""Phase 4 #20 — centralised matplotlib backend regression tests.

Pins the rule that every module importing matplotlib.pyplot must
route through shared.plotting, so the backend stays Agg in all
contexts (headless CI, Qt threads, web workers).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
import sys

import mpmath as mp
import pytest


def test_shared_plotting_exposes_plt_and_rcparams():
    from shared.plotting import plt, rcParams

    assert plt is not None
    assert rcParams is not None


def test_backend_is_agg_after_shared_plotting_import():
    import matplotlib

    import shared.plotting  # noqa: F401

    assert matplotlib.get_backend().lower() == "agg"


def test_assert_agg_backend_does_not_raise():
    from shared.plotting import assert_agg_backend

    # Should not raise in the test environment
    assert_agg_backend()


def test_business_module_import_preserves_agg_backend():
    """Import an arbitrary business module that uses matplotlib and
    verify the backend stays Agg. Regressions where a module calls
    ``matplotlib.use("QtAgg")`` locally would fail this."""
    import matplotlib

    # Force re-imports so a stale sys.modules entry doesn't hide a bug
    for mod in list(sys.modules.keys()):
        if mod.startswith("fitting.plot_fitting") or mod == "shared.plotting":
            del sys.modules[mod]

    importlib.import_module("fitting.plot_fitting")
    assert matplotlib.get_backend().lower() == "agg"


def test_rcparams_have_cjk_fallback():
    """Post-import check: the CJK fallback chain is set, so plots
    with Chinese labels don't fall back to missing-glyph boxes."""
    from shared.plotting import rcParams

    fallback = rcParams["font.sans-serif"]
    assert any("YaHei" in font or "PingFang" in font or "SimHei" in font
               for font in fallback), (
        "CJK font fallback chain missing; Chinese labels would render "
        "as glyph-missing boxes"
    )


def test_cjk_font_properties_resolve_explicit_font_when_available():
    from shared.plotting import cjk_font_family, cjk_font_properties

    props = cjk_font_properties()
    if props is None:
        pytest.skip("No CJK-capable Matplotlib font available in this environment.")

    assert cjk_font_family()
    assert props.get_file()


def test_cjk_mathtext_preserves_italic_and_bold_styles():
    """The custom CJK mathtext fonts must keep the :italic / :bold style
    modifiers, otherwise every math expression app-wide (not just CJK) loses the
    italic-variable / bold distinction mathtext normally provides.
    """
    from shared.plotting import cjk_font_family, rcParams

    if not cjk_font_family():
        pytest.skip("No CJK-capable Matplotlib font available in this environment.")

    assert rcParams["mathtext.fontset"] == "custom"
    # Italic and bold math must carry the style modifier, not the plain family.
    assert str(rcParams["mathtext.it"]).endswith(":italic"), rcParams["mathtext.it"]
    assert str(rcParams["mathtext.bf"]).endswith(":bold"), rcParams["mathtext.bf"]
    # Roman stays the plain family; fallback keeps Computer Modern for missing math glyphs.
    assert ":" not in str(rcParams["mathtext.rm"])
    assert rcParams["mathtext.fallback"] == "cm"


def test_unicode_minus_disabled():
    """Axis labels must use ASCII minus so LaTeX exports (siunitx)
    don't trip over U+2212."""
    from shared.plotting import rcParams

    assert rcParams["axes.unicode_minus"] is False


def test_statistics_plot_spec_renderer_outputs_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        render_statistics_plot_from_spec,
        statistics_plot_spec_from_result,
        StatisticsPlotLabels,
    )

    labels = StatisticsPlotLabels(
        data="Data",
        mean="Mean",
        mean_band="Mean ± standard error",
        x_axis="Point index",
        y_axis="Value",
        title="Statistical mean",
    )
    spec = statistics_plot_spec_from_result(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("3.0")],
        [mp.mpf("0.1"), None, mp.mpf("0.2")],
        {"mean": "2.0", "std": "1.0", "std_mean": "0.25"},
        labels,
        batch_suffix=" - 1",
    )

    assert spec is not None
    assert spec.values == (mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("3.0"))
    assert spec.sigmas == (mp.mpf("0.1"), None, mp.mpf("0.2"))
    assert spec.std == "1.0"
    assert spec.labels is labels
    assert spec.batch_suffix == " - 1"
    png = render_statistics_plot_from_spec(spec)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_plot_labels_with_unit_only_updates_y_axis():
    from shared.plotting import statistics_plot_labels_with_unit, StatisticsPlotLabels

    labels = StatisticsPlotLabels(
        data="Data",
        mean="Mean",
        mean_band="Mean ± standard error",
        x_axis="Point index",
        y_axis="Value",
        title="Statistical mean",
    )

    with_unit = statistics_plot_labels_with_unit(labels, "m/s")
    without_unit = statistics_plot_labels_with_unit(labels, "")

    assert labels.y_axis == "Value"
    assert with_unit.y_axis == "Value [m/s]"
    assert with_unit.x_axis == labels.x_axis
    assert with_unit.title == labels.title
    assert without_unit is not labels
    assert without_unit.y_axis == "Value"


def test_fitting_plot_labels_with_units_updates_axes_and_residuals():
    from shared.plotting import FittingPlotLabels, fitting_plot_labels_with_units

    labels = FittingPlotLabels()

    with_units = fitting_plot_labels_with_units(
        labels,
        x_unit="s",
        y_unit="m",
        parameter_unit="m/s",
    )
    mixed_parameter_units = fitting_plot_labels_with_units(
        labels,
        x_unit="s",
        y_unit="m",
        parameter_unit="",
    )

    assert labels.x_axis == "x"
    assert with_units.x_axis == "x [s]"
    assert with_units.y_axis == "y [m]"
    assert with_units.residual == "Residual [m]"
    assert with_units.parameter_axis == "Value [m/s]"
    assert mixed_parameter_units.parameter_axis == "Value"


def test_statistics_plot_specs_cover_p1_6_gallery_and_render_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        render_statistics_plot_from_spec,
        statistics_plot_specs_from_result,
        StatisticsPlotLabels,
    )

    labels = StatisticsPlotLabels(
        data="数据",
        mean="平均值",
        mean_band="平均值±标准误差",
        x_axis="点序号",
        y_axis="数值",
        title="统计平均",
        median="中位数",
        histogram_title="直方图",
        box_title="箱线图",
        qq_title="正态 QQ 图",
        weighted_residual_title="加权残差",
        frequency_axis="频数",
        theoretical_quantile_axis="理论正态分位数",
        sample_quantile_axis="样本标准化分位数",
        residual_axis="标准化残差",
    )
    specs = statistics_plot_specs_from_result(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("4.0"), mp.mpf("8.0")],
        [mp.mpf("0.5"), mp.mpf("0.5"), mp.mpf("1.0"), mp.mpf("1.5")],
        {
            "mode": "weighted_sigma",
            "mean": mp.mpf("3.0"),
            "std": mp.mpf("2.0"),
            "std_mean": mp.mpf("1.0"),
            "median": mp.mpf("3.0"),
            "q1": mp.mpf("1.75"),
            "q3": mp.mpf("5.0"),
            "weighted_consistency_dof": 3,
        },
        labels,
    )

    assert [spec.plot_key for spec in specs] == [
        "statistics.series_with_mean",
        "statistics.histogram",
        "statistics.box",
        "statistics.qq",
        "statistics.weighted_residual",
    ]
    for spec in specs:
        png = render_statistics_plot_from_spec(spec)
        assert png is not None
        assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_weighted_residual_requires_weighted_mode_even_with_sigmas():
    from shared.plotting import statistics_plot_specs_from_result, StatisticsPlotLabels

    labels = StatisticsPlotLabels(
        data="Data",
        mean="Mean",
        mean_band="Mean ± standard error",
        x_axis="Point index",
        y_axis="Value",
        title="Statistical mean",
    )
    specs = statistics_plot_specs_from_result(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("4.0")],
        [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")],
        {
            "mode": "mean_sample",
            "mean": mp.mpf("2.3333333333333333"),
            "std": mp.mpf("1.5275252316519468"),
            "std_mean": mp.mpf("0.8819171036881969"),
        },
        labels,
    )

    assert "statistics.weighted_residual" not in [spec.plot_key for spec in specs]


def test_statistics_weighted_residual_requires_two_positive_sigma_pairs():
    from shared.plotting import statistics_plot_specs_from_result, StatisticsPlotLabels

    labels = StatisticsPlotLabels(
        data="Data",
        mean="Mean",
        mean_band="Mean ± standard error",
        x_axis="Point index",
        y_axis="Value",
        title="Statistical mean",
    )
    specs = statistics_plot_specs_from_result(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("4.0")],
        [mp.mpf("0.1"), None, mp.mpf("0")],
        {
            "mode": "weighted_sigma",
            "mean": mp.mpf("1.0"),
            "std": mp.mpf("0"),
            "std_mean": mp.mpf("0"),
            "weighted_consistency_dof": 0,
        },
        labels,
    )

    assert "statistics.weighted_residual" not in [spec.plot_key for spec in specs]


def test_statistics_plot_specs_omit_qq_without_raising_for_non_finite_values():
    from shared.plotting import statistics_plot_specs_from_result, StatisticsPlotLabels

    labels = StatisticsPlotLabels(
        data="Data",
        mean="Mean",
        mean_band="Mean ± standard error",
        x_axis="Point index",
        y_axis="Value",
        title="Statistical mean",
    )
    specs = statistics_plot_specs_from_result(
        [mp.nan, mp.mpf("1")],
        [None, None],
        {
            "mode": "mean_sample",
            "mean": mp.mpf("1"),
            "std": mp.nan,
            "std_mean": mp.nan,
        },
        labels,
    )

    assert "statistics.qq" not in [spec.plot_key for spec in specs]


def test_statistics_time_series_plot_specs_render_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        render_statistics_time_series_plot_from_spec,
        statistics_time_series_plot_specs_from_payload,
        StatisticsTimeSeriesPlotLabels,
    )

    specs = statistics_time_series_plot_specs_from_payload(
        {
            "series_method": "rolling_mean",
            "columns": [
                {
                    "value_column": "A",
                    "points": [
                        {
                            "source_row_id": "1",
                            "time": "day_1",
                            "observed_value": "1.0",
                            "value": None,
                            "uncertainty": None,
                        },
                        {
                            "source_row_id": "2",
                            "time": "day_2",
                            "observed_value": "2.0",
                            "value": "1.5",
                            "uncertainty": "0.1",
                        },
                        {
                            "source_row_id": "3",
                            "time": "day_3",
                            "observed_value": "4.0",
                            "value": "3.0",
                            "uncertainty": "0.2",
                        },
                    ],
                }
            ],
        },
        StatisticsTimeSeriesPlotLabels(title="Time series"),
    )

    assert len(specs) == 1
    assert specs[0].plot_key == "statistics.time_series"
    png = render_statistics_time_series_plot_from_spec(specs[0])
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_fitting_plot_specs_cover_p2_1b_gallery_bands_and_render_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        compute_fitting_bands,
        fitting_plot_specs_from_result,
        render_fitting_plot_from_spec,
    )

    diagnostics = {
        "parameter_correlation": {
            "parameters": ["a", "b"],
            "matrix": [[mp.mpf("1"), mp.mpf("0.5")], [mp.mpf("0.5"), mp.mpf("1")]],
        }
    }
    confidence, prediction, band_diagnostics = compute_fitting_bands(
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5"), mp.mpf("7")],
        covariance=[[mp.mpf("0.01"), mp.mpf("0")], [mp.mpf("0"), mp.mpf("0.04")]],
        parameter_jacobian=[
            [mp.mpf("1"), mp.mpf("0")],
            [mp.mpf("1"), mp.mpf("1")],
            [mp.mpf("1"), mp.mpf("2")],
            [mp.mpf("1"), mp.mpf("3")],
        ],
        residual_variance=mp.mpf("0.25"),
    )

    assert confidence is not None
    assert prediction is not None
    assert band_diagnostics == ()
    assert confidence.lower[0] == pytest.approx(0.8)
    assert confidence.upper[3] == pytest.approx(8.216552506)
    assert prediction.lower[0] == pytest.approx(-0.019803903)

    specs = fitting_plot_specs_from_result(
        [mp.mpf("0"), mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        [mp.mpf("1.1"), mp.mpf("2.9"), mp.mpf("5.2"), mp.mpf("6.8")],
        [("Fit", [mp.mpf("1"), mp.mpf("3"), mp.mpf("5"), mp.mpf("7")])],
        [("Residuals", [mp.mpf("0.1"), mp.mpf("-0.1"), mp.mpf("0.2"), mp.mpf("-0.2")])],
        sigmas=[mp.mpf("0.2"), mp.mpf("0.2"), mp.mpf("0.2"), mp.mpf("0.2")],
        diagnostics=diagnostics,
        covariance=[[mp.mpf("0.01"), mp.mpf("0")], [mp.mpf("0"), mp.mpf("0.04")]],
        prediction_jacobian=[
            [mp.mpf("1"), mp.mpf("0")],
            [mp.mpf("1"), mp.mpf("1")],
            [mp.mpf("1"), mp.mpf("2")],
            [mp.mpf("1"), mp.mpf("3")],
        ],
        residual_variance=mp.mpf("0.25"),
    )

    assert [spec.plot_key for spec in specs] == [
        "fitting.overview",
        "fitting.residual",
        "fitting.residual_histogram",
        "fitting.residual_qq",
        "fitting.correlation_heatmap",
    ]
    assert specs[0].confidence_band is not None
    assert specs[0].prediction_band is not None
    assert specs[-1].correlation_names == ("a", "b")
    for spec in specs:
        png = render_fitting_plot_from_spec(spec)
        assert png is not None
        assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_fitting_prediction_band_suppression_keeps_valid_confidence_band():
    from shared.plotting import compute_fitting_bands

    confidence, prediction, diagnostics = compute_fitting_bands(
        [mp.mpf("10"), mp.mpf("20")],
        covariance=[[mp.mpf("0.25")]],
        parameter_jacobian=[[mp.mpf("1")], [mp.mpf("2")]],
        residual_variance=None,
    )

    assert confidence is not None
    assert confidence.lower == pytest.approx((9.0, 18.0))
    assert confidence.upper == pytest.approx((11.0, 22.0))
    assert prediction is None
    assert diagnostics == ("prediction band suppressed: finite non-negative residual variance unavailable.",)


def test_fitting_bands_fail_closed_without_parameter_jacobian():
    from shared.plotting import compute_fitting_bands

    confidence, prediction, diagnostics = compute_fitting_bands(
        [mp.mpf("10"), mp.mpf("20")],
        covariance=[[mp.mpf("0.25")]],
        parameter_jacobian=None,
        residual_variance=mp.mpf("0.1"),
    )

    assert confidence is None
    assert prediction is None
    assert diagnostics == ("fitting band suppressed: parameter Jacobian unavailable or non-finite.",)


def test_fitting_bands_fail_closed_without_covariance():
    from shared.plotting import compute_fitting_bands

    confidence, prediction, diagnostics = compute_fitting_bands(
        [mp.mpf("10"), mp.mpf("20")],
        covariance=None,
        parameter_jacobian=[[mp.mpf("1")], [mp.mpf("2")]],
        residual_variance=mp.mpf("0.1"),
    )

    assert confidence is None
    assert prediction is None
    assert diagnostics == ("fitting band suppressed: covariance unavailable or non-finite.",)


def test_fitting_bands_fail_closed_without_fitted_values():
    from shared.plotting import compute_fitting_bands

    for fitted_values in ([], [mp.nan, mp.mpf("20")]):
        confidence, prediction, diagnostics = compute_fitting_bands(
            fitted_values,
            covariance=[[mp.mpf("0.25")]],
            parameter_jacobian=[[mp.mpf("1")], [mp.mpf("2")]],
            residual_variance=mp.mpf("0.1"),
        )

        assert confidence is None
        assert prediction is None
        assert diagnostics == ("fitting band suppressed: fitted values unavailable.",)


def test_invalid_fitting_overview_spec_returns_none_without_leaking_figures():
    from shared.plotting import FittingPlotSpec, plt, render_fitting_overview_from_spec

    before = tuple(plt.get_fignums())
    png = render_fitting_overview_from_spec(
        FittingPlotSpec(
            plot_key="fitting.overview",
            x_values=(mp.mpf("0"), mp.mpf("1")),
            y_values=(mp.mpf("1"),),
            fitted_values=(mp.mpf("1"), mp.mpf("2")),
            residuals=(mp.mpf("0"), mp.mpf("0")),
        )
    )

    assert png is None
    assert tuple(plt.get_fignums()) == before


def test_invalid_fitting_residual_spec_returns_none_without_leaking_figures():
    from shared.plotting import FittingPlotSpec, plt, render_fitting_plot_from_spec

    before = tuple(plt.get_fignums())
    png = render_fitting_plot_from_spec(
        FittingPlotSpec(
            plot_key="fitting.residual",
            x_values=(mp.mpf("0"), mp.mpf("1")),
            residuals=(mp.mpf("0"),),
        )
    )

    assert png is None
    assert tuple(plt.get_fignums()) == before


def test_malformed_fitting_correlation_heatmap_fails_closed():
    from shared.plotting import FittingPlotSpec, fitting_plot_specs_from_result, render_fitting_plot_from_spec

    diagnostics = {
        "parameter_correlation": {
            "parameters": ["a", "b"],
            "matrix": [[mp.mpf("1")]],
        }
    }
    specs = fitting_plot_specs_from_result(
        [mp.mpf("0"), mp.mpf("1")],
        [mp.mpf("1"), mp.mpf("2")],
        [("Fit", [mp.mpf("1"), mp.mpf("2")])],
        [("Residuals", [mp.mpf("0"), mp.mpf("0")])],
        diagnostics=diagnostics,
    )

    assert "fitting.correlation_heatmap" not in [spec.plot_key for spec in specs]
    assert render_fitting_plot_from_spec(
        FittingPlotSpec(
            plot_key="fitting.correlation_heatmap",
            x_values=(),
            correlation_names=("a", "b"),
            correlation_matrix=((mp.mpf("1"),),),
        )
    ) is None


def test_invalid_correlation_values_do_not_emit_heatmap_specs():
    from shared.plotting import FittingPlotSpec, fitting_plot_specs_from_result, render_fitting_plot_from_spec

    malformed_matrices = (
        [[mp.mpf("1"), mp.mpf("2")], [mp.mpf("2"), mp.mpf("1")]],
        [[mp.mpf("1"), mp.mpf("0.9")], [mp.mpf("0.1"), mp.mpf("1")]],
        [[mp.mpf("0.5"), mp.mpf("0")], [mp.mpf("0"), mp.mpf("1")]],
    )
    for matrix in malformed_matrices:
        diagnostics = {
            "parameter_correlation": {
                "parameters": ["a", "b"],
                "matrix": matrix,
            }
        }
        specs = fitting_plot_specs_from_result(
            [mp.mpf("0"), mp.mpf("1")],
            [mp.mpf("1"), mp.mpf("2")],
            [("Fit", [mp.mpf("1"), mp.mpf("2")])],
            [("Residuals", [mp.mpf("0"), mp.mpf("0")])],
            diagnostics=diagnostics,
        )

        assert "fitting.correlation_heatmap" not in [spec.plot_key for spec in specs]
        assert render_fitting_plot_from_spec(
            FittingPlotSpec(
                plot_key="fitting.correlation_heatmap",
                x_values=(),
                correlation_names=("a", "b"),
                correlation_matrix=tuple(tuple(row) for row in matrix),
            )
        ) is None


def test_fitting_histogram_and_qq_save_failures_do_not_leak_figures(monkeypatch):
    from matplotlib.figure import Figure

    from shared.plotting import FittingPlotSpec, plt, render_fitting_plot_from_spec

    def fail_savefig(self, *args, **kwargs):
        raise RuntimeError("forced save failure")

    monkeypatch.setattr(Figure, "savefig", fail_savefig)

    for plot_key in ("fitting.residual_histogram", "fitting.residual_qq"):
        before = tuple(plt.get_fignums())
        png = render_fitting_plot_from_spec(
            FittingPlotSpec(
                plot_key=plot_key,
                x_values=(mp.mpf("0"), mp.mpf("1"), mp.mpf("2"), mp.mpf("3")),
                residuals=(mp.mpf("-1"), mp.mpf("-0.25"), mp.mpf("0.25"), mp.mpf("1")),
            )
        )

        assert png is None
        assert tuple(plt.get_fignums()) == before


def test_render_residual_diff_save_failure_returns_empty_bytes_without_leaking_figures(monkeypatch):
    from matplotlib.figure import Figure

    from fitting.plot_fitting import render_residual_diff
    from shared.plotting import plt

    def fail_savefig(self, *args, **kwargs):
        raise RuntimeError("forced save failure")

    monkeypatch.setattr(Figure, "savefig", fail_savefig)

    before = tuple(plt.get_fignums())
    png = render_residual_diff(
        [mp.mpf("0"), mp.mpf("1")],
        [("model", [mp.mpf("-0.1"), mp.mpf("0.1")])],
    )

    assert png == b""
    assert tuple(plt.get_fignums()) == before


def test_desktop_fit_plot_routes_diagnostics_and_covariance_to_shared_overview(monkeypatch):
    from types import SimpleNamespace

    from app_desktop import window_fitting_residuals_mixin as mixin_mod
    from fitting.hp_fitter import FitResult

    captured = {}

    def fake_render(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return b"\x89PNG\r\n\x1a\ndesktop-fit"

    monkeypatch.setattr(mixin_mod, "render_fitting_overview", fake_render)

    class Dummy(mixin_mod.WindowFittingResidualsMixin):
        def _sanitize_log_scale(self, log_scale, x_series, y_series):
            return log_scale

        def _current_log_scale(self):
            return None

        def _build_standard_plot_series(self, fit_result):
            return fit_result.fitted_curve, fit_result.residuals

        def _tr(self, zh, en):
            return en

        def _append_log(self, message):
            captured["log"] = message

        def _fit_input_unit_for_job(self, units, job):
            return "s" if units else ""

        def _fit_output_unit(self, units, target_column=None):
            return "m" if units else ""

        def _fit_single_parameter_axis_unit(self, units, names):
            return "m/s" if units else ""

    diagnostics = {"parameter_correlation": {"parameters": ["a"], "matrix": [[mp.mpf("1")]]}}
    fit_result = FitResult(
        params={"a": mp.mpf("1")},
        param_errors={"a": mp.mpf("0.1")},
        chi2=mp.mpf("1"),
        reduced_chi2=mp.mpf("1"),
        aic=mp.mpf("1"),
        bic=mp.mpf("1"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("0.1"),
        residuals=[mp.mpf("0.1"), mp.mpf("-0.1")],
        fitted_curve=[mp.mpf("1"), mp.mpf("2")],
        covariance=[[mp.mpf("0.01")]],
        details={"diagnostics": diagnostics},
    )
    job = SimpleNamespace(
        x_series=[mp.mpf("0"), mp.mpf("1")],
        y_series=[mp.mpf("1.1"), mp.mpf("1.9")],
        is_multidim=False,
        model_type="custom",
        sigma_series=[mp.mpf("0.2"), mp.mpf("0.2")],
        label="linear",
        model_expr="a*x",
        variable_map={"x": "x"},
        target_column="y",
    )

    png = Dummy()._render_fit_plot_bytes(
        job,
        fit_result,
        units={"inputs": {"x": {"unit": "s"}}, "outputs": {"y": {"unit": "m"}}, "parameters": {"a": {"unit": "m/s"}}},
    )

    assert png == b"\x89PNG\r\n\x1a\ndesktop-fit"
    assert captured["kwargs"]["diagnostics"] == diagnostics
    assert captured["kwargs"]["covariance"] == [[mp.mpf("0.01")]]
    labels = captured["kwargs"]["labels"]
    assert labels.x_axis == "x [s]"
    assert labels.y_axis == "y [m]"
    assert labels.residual == "Residual [m]"
    assert labels.parameter_axis == "Value [m/s]"


def test_error_contribution_plot_spec_renderer_outputs_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        contribution_plot_spec_from_summary,
        ErrorContributionPlotLabels,
        render_error_contribution_plot_from_spec,
    )

    labels = ErrorContributionPlotLabels(
        x_axis="Uncertainty contribution (%)",
        title="Uncertainty breakdown",
    )
    spec = contribution_plot_spec_from_summary(
        [
            {"name": "x", "percent": 75.0},
            {"name": "y", "percent": 25.0},
        ],
        labels,
        title_suffix="row 1",
    )

    assert spec is not None
    assert spec.labels == ("x", "y")
    assert spec.percents == (75.0, 25.0)
    assert spec.cumulative_percents == (75.0, 100.0)
    assert spec.plot_labels is labels
    assert spec.title_suffix == "row 1"
    png = render_error_contribution_plot_from_spec(spec)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_error_contribution_plot_rejects_invalid_percent_shape_without_open_figure():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        ErrorContributionPlotLabels,
        ErrorContributionPlotSpec,
        plt,
        render_error_contribution_plot_from_spec,
    )

    plot_labels = ErrorContributionPlotLabels(
        x_axis="Uncertainty contribution (%)",
        title="Uncertainty breakdown",
    )
    before = set(plt.get_fignums())

    assert (
        render_error_contribution_plot_from_spec(
            ErrorContributionPlotSpec(labels=("x",), percents=(), plot_labels=plot_labels)
        )
        is None
    )
    assert (
        render_error_contribution_plot_from_spec(
            ErrorContributionPlotSpec(labels=("x", "y"), percents=(100.0,), plot_labels=plot_labels)
        )
        is None
    )
    assert (
        render_error_contribution_plot_from_spec(
            ErrorContributionPlotSpec(
                labels=("x", "y"),
                percents=(75.0, 25.0),
                plot_labels=plot_labels,
                cumulative_percents=(75.0,),
            )
        )
        is None
    )

    assert set(plt.get_fignums()) == before


@pytest.mark.parametrize("bad_percent", [float("nan"), float("inf"), float("-inf")])
def test_error_contribution_plot_spec_rejects_non_finite_percent(bad_percent):
    from shared.plotting import contribution_plot_spec_from_summary, ErrorContributionPlotLabels

    labels = ErrorContributionPlotLabels(
        x_axis="Uncertainty contribution (%)",
        title="Uncertainty breakdown",
    )

    assert contribution_plot_spec_from_summary([{"name": "x", "percent": bad_percent}], labels) is None


def test_monte_carlo_distribution_plot_spec_renderer_outputs_png_bytes():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        MonteCarloDistributionPlotLabels,
        monte_carlo_distribution_plot_spec_from_summary,
        render_monte_carlo_distribution_plot_from_spec,
    )

    summary = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "2.0",
        "std": "0.1",
        "histogram": {
            "bin_edges": ["1.8", "2.0", "2.2"],
            "counts": [50, 50],
        },
        "percentiles": {
            "2.5": "1.81",
            "50": "2.0",
            "97.5": "2.19",
        },
    }
    labels = MonteCarloDistributionPlotLabels(title="MC", x_axis="y", y_axis="n")

    spec = monte_carlo_distribution_plot_spec_from_summary(summary, labels, title_suffix="row 1")

    assert spec is not None
    assert spec.bin_edges == pytest.approx((1.8, 2.0, 2.2))
    assert spec.counts == (50, 50)
    assert spec.mean == pytest.approx(2.0)
    assert spec.std == pytest.approx(0.1)
    assert [key for key, _value in spec.percentiles] == ["2.5", "50", "97.5"]
    assert [value for _key, value in spec.percentiles] == pytest.approx([1.81, 2.0, 2.19])
    assert spec.labels is labels
    png = render_monte_carlo_distribution_plot_from_spec(spec)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_monte_carlo_distribution_plot_handles_all_equal_histogram():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        monte_carlo_distribution_plot_spec_from_summary,
        render_monte_carlo_distribution_plot_from_spec,
    )

    summary = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "3.0",
        "std": "0",
        "histogram": {
            "bin_edges": ["2.5", "3.5"],
            "counts": [100],
        },
        "percentiles": {
            "2.5": "3.0",
            "50": "3.0",
            "97.5": "3.0",
        },
    }

    spec = monte_carlo_distribution_plot_spec_from_summary(summary)

    assert spec is not None
    assert spec.std == 0.0
    png = render_monte_carlo_distribution_plot_from_spec(spec)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_monte_carlo_distribution_plot_rejects_invalid_shape_without_open_figure():
    pytest.importorskip("matplotlib")
    from shared.plotting import (
        MonteCarloDistributionPlotSpec,
        monte_carlo_distribution_plot_spec_from_summary,
        plt,
        render_monte_carlo_distribution_plot_from_spec,
    )

    before = set(plt.get_fignums())
    summary = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "2.0",
        "std": "0.1",
        "histogram": {
            "bin_edges": ["1.8", "2.0"],
            "counts": [50, 50],
        },
        "percentiles": {
            "2.5": "1.81",
            "50": "2.0",
            "97.5": "2.19",
        },
    }

    assert monte_carlo_distribution_plot_spec_from_summary(summary) is None
    valid_summary = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "2.0",
        "std": "0.1",
        "histogram": {
            "bin_edges": ["1.8", "2.0", "2.2"],
            "counts": [50, 50],
        },
        "percentiles": {
            "2.5": "1.81",
            "50": "2.0",
            "97.5": "2.19",
        },
    }
    missing_schema = dict(valid_summary)
    missing_schema.pop("schema")
    missing_count = dict(valid_summary)
    missing_count.pop("finite_sample_count")
    inconsistent_counts = dict(valid_summary)
    inconsistent_counts["requested_sample_count"] = 0
    inverted_percentiles = dict(valid_summary)
    inverted_percentiles["percentiles"] = {
        "2.5": "2.19",
        "50": "2.0",
        "97.5": "1.81",
    }
    assert monte_carlo_distribution_plot_spec_from_summary(missing_schema) is None
    assert monte_carlo_distribution_plot_spec_from_summary(missing_count) is None
    assert monte_carlo_distribution_plot_spec_from_summary(inconsistent_counts) is None
    assert monte_carlo_distribution_plot_spec_from_summary(inverted_percentiles) is None
    assert (
        render_monte_carlo_distribution_plot_from_spec(
            MonteCarloDistributionPlotSpec(
                bin_edges=(1.0, 1.0),
                counts=(1,),
                mean=1.0,
                std=0.0,
                percentiles=(("50", 1.0),),
            )
        )
        is None
    )
    assert set(plt.get_fignums()) == before


def test_desktop_plot_modules_route_matplotlib_through_shared_plotting():
    """Desktop result images must inherit DataLab's CJK font chain."""
    repo_root = Path(__file__).resolve().parents[1]
    module_paths = [
        repo_root / "app_desktop" / "workers_core.py",
        repo_root / "app_desktop" / "workers_qt.py",
        repo_root / "app_desktop" / "window_statistics_mixin.py",
        repo_root / "app_web" / "logic" / "plots.py",
    ]

    offenders: list[str] = []
    for path in module_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "matplotlib" or alias.name.startswith("matplotlib."):
                        offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "matplotlib" or (node.module or "").startswith("matplotlib."):
                    offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}: from {node.module} import ...")

    assert offenders == []
