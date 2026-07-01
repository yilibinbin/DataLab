"""Single canonical entry point for DataLab's matplotlib configuration.

Every module that uses matplotlib MUST import ``plt`` from this
module rather than calling ``matplotlib.use(...)`` locally:

    from shared.plotting import plt, rcParams  # RIGHT

    import matplotlib                           # WRONG (do not pattern this)
    matplotlib.use("Agg")

Rationale: ``matplotlib.use`` only works before the first pyplot
import. Scattering ``matplotlib.use`` calls across 8 modules creates
an order-of-import hazard — the first module to import pyplot
wins, and the later ``use`` calls emit a warning and are silently
ignored. Centralising here makes backend + rcParams config a single
source of truth.

Invariants enforced:
- Backend is ``Agg``. Thread-safe + headless + no GUI toolkit
  dependency. DataLab intentionally renders PNG bytes → QPixmap (for
  desktop) or sends raw bytes (for web), so no interactive backend
  is wanted.
- CJK fallback font list is applied at import time — Chinese / Japanese
  / Korean labels in plots render consistently across platforms.
- ``axes.unicode_minus = False`` — plots use ASCII minus so LaTeX
  export and siunitx stay happy.

A regression test (``tests/test_plotting_backend.py``) asserts the
backend is Agg after importing an arbitrary business module, so a
future commit that calls ``matplotlib.use("QtAgg")`` at module
scope fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import io
import logging
import math
from functools import lru_cache
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import matplotlib as _matplotlib
import mpmath as mp

# Lock the backend BEFORE any submodule imports pyplot. The string
# "Agg" is the thread-safe headless raster backend — do not change
# without re-testing the worker threads (Qt + matplotlib interaction
# is notoriously finicky when non-Agg backends are in use).
_matplotlib.use("Agg")

from matplotlib import font_manager  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg as _FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure as _Figure  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

_logger = logging.getLogger(__name__)


def _new_figure_ax(figsize: tuple[float, float], dpi: int) -> tuple[Any, Any]:
    """Create a standalone (fig, ax) via the object-oriented matplotlib API.

    Unlike ``plt.subplots``, this never touches the pyplot global figure
    registry — so it is thread-safe (the desktop renders plots on worker
    threads) and needs no ``plt.close`` to avoid leaking figures (P2-7). The
    figure is attached to an Agg canvas so ``fig.savefig`` works headless.
    """
    fig = _Figure(figsize=figsize, dpi=dpi)
    _FigureCanvasAgg(fig)
    ax = fig.subplots()
    return fig, ax

__all__ = [
    "plt",
    "rcParams",
    "matplotlib",
    "assert_agg_backend",
    "apply_cjk_font",
    "contribution_plot_spec_from_summary",
    "render_statistics_plot_from_spec",
    "render_statistics_plots_from_specs",
    "render_statistics_grouped_mean_overview_from_spec",
    "render_statistics_time_series_plot_from_spec",
    "render_statistics_time_series_plots_from_specs",
    "render_fitting_plot_from_spec",
    "render_fitting_plots_from_specs",
    "render_fitting_overview_from_spec",
    "render_error_contribution_plot_from_spec",
    "monte_carlo_distribution_plot_spec_from_summary",
    "render_monte_carlo_distribution_plot_from_spec",
    "cjk_font_family",
    "cjk_font_properties",
    "compute_fitting_bands",
    "fitting_plot_specs_from_result",
    "fitting_overview_spec_from_result",
    "statistics_plot_specs_from_result",
    "statistics_time_series_plot_specs_from_payload",
    "statistics_plot_spec_from_result",
    "plot_label_with_unit",
    "statistics_plot_labels_with_unit",
    "fitting_plot_labels_with_units",
    "ErrorContributionPlotLabels",
    "ErrorContributionPlotSpec",
    "FittingBandSpec",
    "FittingPlotLabels",
    "FittingPlotSpec",
    "MonteCarloDistributionPlotLabels",
    "MonteCarloDistributionPlotSpec",
    "StatisticsPlotLabels",
    "StatisticsPlotSpec",
    "StatisticsGroupedMeanOverviewLabels",
    "StatisticsGroupedMeanOverviewSpec",
    "StatisticsTimeSeriesPlotLabels",
    "StatisticsTimeSeriesPlotSpec",
]

# Re-export for callers that need access beyond plt/rcParams.
matplotlib = _matplotlib

_CJK_FONT_FAMILIES = [
    "Arial Unicode MS",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Heiti TC",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "DejaVu Sans",
]


@lru_cache(maxsize=1)
def _resolved_cjk_font() -> tuple[str, str] | None:
    for family in _CJK_FONT_FAMILIES:
        if family == "DejaVu Sans":
            continue
        try:
            path = font_manager.findfont(family, fallback_to_default=False)
        except Exception:
            continue
        return family, path
    return None


def cjk_font_family() -> str | None:
    """Return the resolved CJK-capable Matplotlib family, if available."""
    resolved = _resolved_cjk_font()
    return resolved[0] if resolved else None


@lru_cache(maxsize=1)
def cjk_font_properties() -> font_manager.FontProperties | None:
    """Return explicit font properties for Chinese result plot labels.

    ``rcParams`` is a global mutable singleton; callers, tests, or older
    imports can accidentally move DejaVu Sans back to the front. Result
    plots that contain Chinese text should call ``apply_cjk_font()`` so
    the actual text objects point at a resolved OS font file.
    """
    resolved = _resolved_cjk_font()
    if not resolved:
        return None
    _, path = resolved
    return font_manager.FontProperties(fname=path)


_resolved_family = cjk_font_family()

# CJK fallback font list — applied at import time so every figure
# created anywhere in DataLab inherits it. Order matters: the first
# family present on the host wins.
if _resolved_family:
    rcParams["font.family"] = [_resolved_family, "sans-serif"]
    rcParams["font.sans-serif"] = [
        _resolved_family,
        *[family for family in _CJK_FONT_FAMILIES if family != _resolved_family],
    ]
else:
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = list(_CJK_FONT_FAMILIES)

# Axis labels must use ASCII minus so downstream LaTeX export with
# siunitx doesn't see U+2212 and emit a "Missing $ inserted" error.
rcParams["axes.unicode_minus"] = False


def apply_cjk_font(ax: Any) -> None:
    """Apply the resolved CJK font to text owned by a Matplotlib axis."""
    props = cjk_font_properties()
    if props is None:
        return
    text_items = [
        ax.title,
        ax.xaxis.label,
        ax.yaxis.label,
        *ax.get_xticklabels(),
        *ax.get_yticklabels(),
    ]
    legend = ax.get_legend()
    if legend is not None:
        text_items.extend(legend.get_texts())
    for text in text_items:
        text.set_fontproperties(props)


@dataclass(frozen=True)
class StatisticsPlotLabels:
    data: str
    mean: str
    mean_band: str
    x_axis: str
    y_axis: str
    title: str
    median: str = "Median"
    histogram_title: str = "Histogram"
    box_title: str = "Box plot"
    qq_title: str = "Normal QQ plot"
    weighted_residual_title: str = "Weighted residuals"
    frequency_axis: str = "Frequency"
    theoretical_quantile_axis: str = "Theoretical normal quantile"
    sample_quantile_axis: str = "Sample standardized quantile"
    residual_axis: str = "Standardized residual"
    zero_line: str = "0"
    threshold_line: str = "±3"


@dataclass(frozen=True)
class StatisticsPlotSpec:
    values: tuple[Any, ...]
    sigmas: tuple[Any | None, ...] | None
    mean: Any | None
    std: Any | None
    std_mean: Any | None
    labels: StatisticsPlotLabels
    batch_suffix: str = ""
    plot_key: str = "statistics.series_with_mean"
    median: Any | None = None
    q1: Any | None = None
    q3: Any | None = None


def plot_label_with_unit(label: str, unit: str | None) -> str:
    unit_text = str(unit or "").strip()
    return f"{label} [{unit_text}]" if unit_text else label


def statistics_plot_labels_with_unit(labels: StatisticsPlotLabels, value_unit: str | None) -> StatisticsPlotLabels:
    return replace(labels, y_axis=plot_label_with_unit(labels.y_axis, value_unit))


def fitting_plot_labels_with_units(
    labels: FittingPlotLabels,
    *,
    x_unit: str | None = None,
    y_unit: str | None = None,
    parameter_unit: str | None = None,
) -> FittingPlotLabels:
    return replace(
        labels,
        x_axis=plot_label_with_unit(labels.x_axis, x_unit),
        y_axis=plot_label_with_unit(labels.y_axis, y_unit),
        residual=plot_label_with_unit(labels.residual, y_unit),
        parameter_axis=plot_label_with_unit(labels.parameter_axis, parameter_unit),
    )


@dataclass(frozen=True)
class StatisticsGroupedMeanOverviewLabels:
    x_axis: str = "Group / column"
    y_axis: str = "Mean"
    title: str = "Grouped mean overview"
    mean: str = "Mean"
    std_error: str = "Std. error"


@dataclass(frozen=True)
class StatisticsGroupedMeanOverviewSpec:
    labels: tuple[str, ...]
    means: tuple[Any, ...]
    std_means: tuple[Any | None, ...]
    plot_labels: StatisticsGroupedMeanOverviewLabels = StatisticsGroupedMeanOverviewLabels()
    plot_key: str = "statistics.grouped_mean_overview"


@dataclass(frozen=True)
class StatisticsTimeSeriesPlotLabels:
    observed: str = "Observed"
    result: str = "Smoothed / rolling"
    uncertainty_band: str = "Uncertainty band"
    x_axis: str = "Time / index"
    y_axis: str = "Value"
    title: str = "Time-series statistics"


@dataclass(frozen=True)
class StatisticsTimeSeriesPlotSpec:
    time_labels: tuple[str, ...]
    observed_values: tuple[Any, ...]
    result_values: tuple[Any | None, ...]
    uncertainties: tuple[Any | None, ...] | None
    labels: StatisticsTimeSeriesPlotLabels
    column: str
    method: str
    plot_key: str = "statistics.time_series"


@dataclass(frozen=True)
class FittingPlotLabels:
    data: str = "Data"
    fit: str = "Fit"
    residual: str = "Residual"
    x_axis: str = "x"
    y_axis: str = "y"
    index_axis: str = "Point index"
    main_title: str = "Data & Fit"
    residual_title: str = "Residual vs x"
    residual_index_title: str = "Residual vs index"
    histogram_title: str = "Residual Histogram"
    residual_summary_title: str = "Residual Summary"
    qq_title: str = "Residual QQ plot"
    theoretical_quantile_axis: str = "Theoretical normal quantile"
    sample_quantile_axis: str = "Sample residual quantile"
    count_axis: str = "Count"
    zero_line: str = "0"
    sigma_band: str = "±1σ"
    confidence_band: str = "Confidence band"
    prediction_band: str = "Prediction band"
    legacy_rmse_band: str = "±2×RMSE band"
    parameter_title: str = "Parameter Uncertainties"
    parameter_axis: str = "Value"
    correlation_title: str = "Parameter Correlation"
    multidim_message: str = "Multidimensional model\n(curve plot skipped)"


@dataclass(frozen=True)
class FittingBandSpec:
    label: str
    lower: tuple[Any, ...]
    upper: tuple[Any, ...]
    kind: str


@dataclass(frozen=True)
class FittingPlotSpec:
    plot_key: str
    x_values: tuple[Any, ...]
    y_values: tuple[Any, ...] = ()
    fitted_values: tuple[Any, ...] = ()
    residuals: tuple[Any, ...] = ()
    sigmas: tuple[Any | None, ...] | None = None
    labels: FittingPlotLabels = FittingPlotLabels()
    show_curves: bool = True
    batch_suffix: str = ""
    parameter_label: str = ""
    parameter_names: tuple[str, ...] = ()
    parameter_values: tuple[Any, ...] = ()
    parameter_errors: tuple[Any, ...] = ()
    correlation_names: tuple[str, ...] = ()
    correlation_matrix: tuple[tuple[Any, ...], ...] = ()
    confidence_band: FittingBandSpec | None = None
    prediction_band: FittingBandSpec | None = None
    comparison: tuple[tuple[str, Any, Any, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrelationHeatmapSpec:
    plot_key: str
    names: tuple[str, ...]
    matrix: tuple[tuple[Any, ...], ...]
    title: str


@dataclass(frozen=True)
class ErrorContributionPlotLabels:
    x_axis: str
    title: str
    cumulative_label: str = "Cumulative contribution"


@dataclass(frozen=True)
class ErrorContributionPlotSpec:
    labels: tuple[str, ...]
    percents: tuple[float, ...]
    plot_labels: ErrorContributionPlotLabels
    title_suffix: str = ""
    cumulative_percents: tuple[float, ...] = ()


@dataclass(frozen=True)
class MonteCarloDistributionPlotLabels:
    title: str = "Monte Carlo distribution"
    x_axis: str = "Result value"
    y_axis: str = "Sample count"
    mean: str = "Mean"
    mean_minus_std: str = "Mean - std"
    mean_plus_std: str = "Mean + std"
    percentile_2_5: str = "2.5%"
    percentile_50: str = "50%"
    percentile_97_5: str = "97.5%"


@dataclass(frozen=True)
class MonteCarloDistributionPlotSpec:
    bin_edges: tuple[float, ...]
    counts: tuple[int, ...]
    mean: float
    std: float
    percentiles: tuple[tuple[str, float], ...]
    labels: MonteCarloDistributionPlotLabels = MonteCarloDistributionPlotLabels()
    title_suffix: str = ""


def statistics_plot_spec_from_result(
    values: Sequence[Any],
    sigmas: Sequence[Any | None] | None,
    stats_result: Mapping[str, Any],
    labels: StatisticsPlotLabels,
    *,
    batch_suffix: str = "",
) -> StatisticsPlotSpec | None:
    """Build the current statistics mean/error-band plot spec.

    This intentionally models only the existing mean plot. Histogram, QQ,
    box, and residual plots belong to later P1 slices.
    """
    if not values:
        return None
    return StatisticsPlotSpec(
        values=tuple(values),
        sigmas=tuple(sigmas) if sigmas is not None else None,
        mean=stats_result.get("mean"),
        std=stats_result.get("std"),
        std_mean=stats_result.get("std_mean"),
        labels=labels,
        batch_suffix=batch_suffix,
        median=stats_result.get("median"),
        q1=stats_result.get("q1"),
        q3=stats_result.get("q3"),
    )


def statistics_plot_specs_from_result(
    values: Sequence[Any],
    sigmas: Sequence[Any | None] | None,
    stats_result: Mapping[str, Any],
    labels: StatisticsPlotLabels,
    *,
    batch_suffix: str = "",
) -> tuple[StatisticsPlotSpec, ...]:
    """Build all statistics plot specs currently supported by DataLab."""
    base = statistics_plot_spec_from_result(
        values,
        sigmas,
        stats_result,
        labels,
        batch_suffix=batch_suffix,
    )
    if base is None:
        return ()

    specs = [
        base,
        StatisticsPlotSpec(
            values=base.values,
            sigmas=base.sigmas,
            mean=base.mean,
            std=base.std,
            std_mean=base.std_mean,
            labels=labels,
            batch_suffix=batch_suffix,
            plot_key="statistics.histogram",
            median=stats_result.get("median"),
            q1=stats_result.get("q1"),
            q3=stats_result.get("q3"),
        ),
        StatisticsPlotSpec(
            values=base.values,
            sigmas=base.sigmas,
            mean=base.mean,
            std=base.std,
            std_mean=base.std_mean,
            labels=labels,
            batch_suffix=batch_suffix,
            plot_key="statistics.box",
            median=stats_result.get("median"),
            q1=stats_result.get("q1"),
            q3=stats_result.get("q3"),
        ),
    ]
    if _statistics_standardized_values(base):
        specs.append(
            StatisticsPlotSpec(
                values=base.values,
                sigmas=base.sigmas,
                mean=base.mean,
                std=base.std,
                std_mean=base.std_mean,
                labels=labels,
                batch_suffix=batch_suffix,
                plot_key="statistics.qq",
                median=stats_result.get("median"),
                q1=stats_result.get("q1"),
                q3=stats_result.get("q3"),
            )
        )
    if _statistics_weighted_residual_enabled(base, stats_result):
        specs.append(
            StatisticsPlotSpec(
                values=base.values,
                sigmas=base.sigmas,
                mean=base.mean,
                std=base.std,
                std_mean=base.std_mean,
                labels=labels,
                batch_suffix=batch_suffix,
                plot_key="statistics.weighted_residual",
                median=stats_result.get("median"),
                q1=stats_result.get("q1"),
                q3=stats_result.get("q3"),
            )
        )
    return tuple(specs)


def statistics_time_series_plot_specs_from_payload(
    payload: Mapping[str, Any],
    labels: StatisticsTimeSeriesPlotLabels | None = None,
) -> tuple[StatisticsTimeSeriesPlotSpec, ...]:
    """Build observed-vs-smoothed plot specs from a time-series payload."""

    columns = payload.get("columns")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray)):
        return ()
    method = str(payload.get("series_method") or "")
    plot_labels = labels or StatisticsTimeSeriesPlotLabels()
    specs: list[StatisticsTimeSeriesPlotSpec] = []
    for index, raw_column in enumerate(columns, 1):
        if not isinstance(raw_column, Mapping):
            continue
        raw_points = raw_column.get("points")
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes, bytearray)):
            continue
        points = [point for point in raw_points if isinstance(point, Mapping)]
        if not points:
            continue
        observed_values: list[Any] = []
        result_values: list[Any | None] = []
        uncertainties: list[Any | None] = []
        time_labels: list[str] = []
        for fallback_row, point in enumerate(points, 1):
            observed = point.get("observed_value")
            if _statistics_finite_float(observed) is None:
                observed_values = []
                break
            observed_values.append(observed)
            result = point.get("value")
            result_values.append(result if _statistics_finite_float(result) is not None else None)
            uncertainty = point.get("uncertainty")
            uncertainties.append(uncertainty if _statistics_finite_float(uncertainty) is not None else None)
            time_labels.append(str(point.get("time") or point.get("source_row_id") or fallback_row))
        if not observed_values or not any(value is not None for value in result_values):
            continue
        specs.append(
            StatisticsTimeSeriesPlotSpec(
                time_labels=tuple(time_labels),
                observed_values=tuple(observed_values),
                result_values=tuple(result_values),
                uncertainties=tuple(uncertainties) if any(value is not None for value in uncertainties) else None,
                labels=plot_labels,
                column=str(raw_column.get("value_column") or f"Column {index}"),
                method=method,
            )
        )
    return tuple(specs)


def statistics_matrix_correlation_heatmap_spec_from_payload(
    payload: Mapping[str, Any],
    *,
    title: str = "Correlation Matrix",
) -> CorrelationHeatmapSpec | None:
    columns = payload.get("columns")
    matrices = payload.get("matrices")
    if (
        not isinstance(columns, Sequence)
        or isinstance(columns, (str, bytes, bytearray))
        or not isinstance(matrices, Mapping)
    ):
        return None
    correlation = matrices.get("correlation")
    if not isinstance(correlation, Mapping):
        return None
    values = correlation.get("values")
    names = tuple(str(column) for column in columns)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return None
    matrix: list[tuple[Any, ...]] = []
    for row in values:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            return None
        if any(cell is None for cell in row):
            return None
        matrix.append(tuple(row))
    if not _correlation_heatmap_shape_is_valid(names, matrix):
        return None
    return CorrelationHeatmapSpec(
        plot_key="statistics.correlation_heatmap",
        names=names,
        matrix=tuple(matrix),
        title=title,
    )


def fitting_overview_spec_from_result(
    x_values: Sequence[Any],
    y_values: Sequence[Any],
    fitted_series: Sequence[tuple[str, Sequence[Any]]],
    residual_series: Sequence[tuple[str, Sequence[Any]]],
    *,
    labels: FittingPlotLabels | None = None,
    sigmas: Sequence[Any | None] | None = None,
    parameter_info: tuple[str, Mapping[str, object], Mapping[str, object]] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    prediction_jacobian: Sequence[Sequence[Any]] | None = None,
    covariance: Sequence[Sequence[Any]] | None = None,
    residual_variance: Any | None = None,
    comparison: Sequence[tuple[str, Any, Any, Any]] | None = None,
    show_curves: bool = True,
) -> FittingPlotSpec:
    """Build the shared overview plot spec used by desktop and Web fitting."""
    plot_labels = labels or FittingPlotLabels()
    parameter_label = ""
    parameter_names: tuple[str, ...] = ()
    parameter_values: tuple[Any, ...] = ()
    parameter_errors: tuple[Any, ...] = ()
    if parameter_info is not None:
        parameter_label, params_dict, errors_dict = parameter_info
        parameter_names = tuple(str(name) for name in params_dict.keys())
        parameter_values = tuple(params_dict[name] for name in params_dict.keys())
        parameter_errors = tuple(errors_dict.get(name, 0) for name in params_dict.keys())

    fitted_values: tuple[Any, ...] = ()
    fit_label = plot_labels.fit
    if fitted_series:
        fit_label = str(fitted_series[0][0] or plot_labels.fit)
        fitted_values = tuple(fitted_series[0][1])
    residuals: tuple[Any, ...] = ()
    if residual_series:
        residuals = tuple(residual_series[0][1])
    correlation_names, correlation_matrix = _fitting_correlation_from_diagnostics(diagnostics)
    confidence_band, prediction_band, band_diagnostics = compute_fitting_bands(
        fitted_values,
        covariance=covariance,
        parameter_jacobian=prediction_jacobian,
        residual_variance=residual_variance,
        labels=plot_labels,
    )
    return FittingPlotSpec(
        plot_key="fitting.overview",
        x_values=tuple(x_values),
        y_values=tuple(y_values),
        fitted_values=fitted_values,
        residuals=residuals,
        sigmas=tuple(sigmas) if sigmas is not None else None,
        labels=plot_labels,
        show_curves=show_curves,
        parameter_label=parameter_label or fit_label,
        parameter_names=parameter_names,
        parameter_values=parameter_values,
        parameter_errors=parameter_errors,
        correlation_names=correlation_names,
        correlation_matrix=correlation_matrix,
        confidence_band=confidence_band,
        prediction_band=prediction_band,
        comparison=tuple(comparison or ()),
        diagnostics=band_diagnostics,
    )


def fitting_plot_specs_from_result(
    x_values: Sequence[Any],
    y_values: Sequence[Any],
    fitted_series: Sequence[tuple[str, Sequence[Any]]],
    residual_series: Sequence[tuple[str, Sequence[Any]]],
    *,
    labels: FittingPlotLabels | None = None,
    sigmas: Sequence[Any | None] | None = None,
    parameter_info: tuple[str, Mapping[str, object], Mapping[str, object]] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    prediction_jacobian: Sequence[Sequence[Any]] | None = None,
    covariance: Sequence[Sequence[Any]] | None = None,
    residual_variance: Any | None = None,
    comparison: Sequence[tuple[str, Any, Any, Any]] | None = None,
    show_curves: bool = True,
) -> tuple[FittingPlotSpec, ...]:
    """Build all fitting plot specs currently supported by DataLab."""
    overview = fitting_overview_spec_from_result(
        x_values,
        y_values,
        fitted_series,
        residual_series,
        labels=labels,
        sigmas=sigmas,
        parameter_info=parameter_info,
        diagnostics=diagnostics,
        prediction_jacobian=prediction_jacobian,
        covariance=covariance,
        residual_variance=residual_variance,
        comparison=comparison,
        show_curves=show_curves,
    )
    specs = [
        overview,
        FittingPlotSpec(
            plot_key="fitting.residual",
            x_values=overview.x_values,
            residuals=overview.residuals,
            sigmas=overview.sigmas,
            labels=overview.labels,
            show_curves=overview.show_curves,
        ),
        FittingPlotSpec(
            plot_key="fitting.residual_histogram",
            x_values=overview.x_values,
            residuals=overview.residuals,
            labels=overview.labels,
        ),
    ]
    if len(_fitting_finite_values(overview.residuals)) >= 2:
        specs.append(
            FittingPlotSpec(
                plot_key="fitting.residual_qq",
                x_values=overview.x_values,
                residuals=overview.residuals,
                labels=overview.labels,
            )
        )
    if overview.correlation_names and overview.correlation_matrix:
        specs.append(
            FittingPlotSpec(
                plot_key="fitting.correlation_heatmap",
                x_values=(),
                labels=overview.labels,
                correlation_names=overview.correlation_names,
                correlation_matrix=overview.correlation_matrix,
            )
        )
    return tuple(specs)


def compute_fitting_bands(
    fitted_values: Sequence[Any],
    *,
    covariance: Sequence[Sequence[Any]] | None,
    parameter_jacobian: Sequence[Sequence[Any]] | None,
    residual_variance: Any | None,
    labels: FittingPlotLabels | None = None,
    z_value: Any = 2,
) -> tuple[FittingBandSpec | None, FittingBandSpec | None, tuple[str, ...]]:
    """Compute confidence/prediction bands from ``J_p C J_p^T``.

    Prediction bands add residual variance only when a finite non-negative
    estimate is supplied. Missing residual variance suppresses prediction
    bands without suppressing a valid confidence band.
    """
    plot_labels = labels or FittingPlotLabels()
    diagnostics: list[str] = []
    fit = _fitting_finite_values(fitted_values)
    cov = _fitting_matrix(covariance)
    jac = _fitting_matrix(parameter_jacobian)
    z = _fitting_finite_float(z_value)
    if not fit:
        return None, None, ("fitting band suppressed: fitted values unavailable.",)
    if z is None or z <= 0:
        return None, None, ("fitting band suppressed: z value is non-finite or non-positive.",)
    if cov is None:
        return None, None, ("fitting band suppressed: covariance unavailable or non-finite.",)
    if jac is None:
        return None, None, ("fitting band suppressed: parameter Jacobian unavailable or non-finite.",)
    if len(jac) != len(fit):
        return None, None, ("fitting band suppressed: parameter Jacobian row count does not match fitted values.",)
    if not cov or any(len(row) != len(cov) for row in cov):
        return None, None, ("fitting band suppressed: covariance matrix must be square.",)
    parameter_count = len(cov)
    if any(len(row) != parameter_count for row in jac):
        return None, None, ("fitting band suppressed: parameter Jacobian width does not match covariance.",)

    confidence_variances: list[float] = []
    for row in jac:
        variance = 0.0
        for i in range(parameter_count):
            for j in range(parameter_count):
                variance += row[i] * cov[i][j] * row[j]
        if variance < 0 and abs(variance) <= 1e-14:
            variance = 0.0
        if variance < 0 or not mp.isfinite(variance):
            return None, None, ("fitting band suppressed: confidence variance is negative or non-finite.",)
        confidence_variances.append(float(variance))

    confidence_half = [float(z) * (variance ** 0.5) for variance in confidence_variances]
    confidence = FittingBandSpec(
        label=plot_labels.confidence_band,
        lower=tuple(value - half for value, half in zip(fit, confidence_half)),
        upper=tuple(value + half for value, half in zip(fit, confidence_half)),
        kind="confidence",
    )

    residual_var = _fitting_finite_float(residual_variance)
    prediction = None
    if residual_var is None or residual_var < 0:
        diagnostics.append("prediction band suppressed: finite non-negative residual variance unavailable.")
    else:
        prediction_half = [float(z) * ((variance + residual_var) ** 0.5) for variance in confidence_variances]
        prediction = FittingBandSpec(
            label=plot_labels.prediction_band,
            lower=tuple(value - half for value, half in zip(fit, prediction_half)),
            upper=tuple(value + half for value, half in zip(fit, prediction_half)),
            kind="prediction",
        )
    return confidence, prediction, tuple(diagnostics)


def contribution_plot_spec_from_summary(
    summary: Sequence[Mapping[str, Any]],
    labels: ErrorContributionPlotLabels,
    *,
    title_suffix: str = "",
) -> ErrorContributionPlotSpec | None:
    """Build the current error-contribution horizontal bar plot spec."""
    if not summary:
        return None
    try:
        row_labels = tuple(str(entry["name"]) for entry in summary)
        percents = tuple(float(entry.get("percent", 0.0)) for entry in summary)
        if not all(mp.isfinite(percent) for percent in percents):
            return None
        cumulative: list[float] = []
        running = 0.0
        for percent in percents:
            running += percent
            cumulative.append(float(running))
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    return ErrorContributionPlotSpec(
        labels=row_labels,
        percents=percents,
        plot_labels=labels,
        title_suffix=title_suffix,
        cumulative_percents=tuple(cumulative),
    )


def monte_carlo_distribution_plot_spec_from_summary(
    summary: Mapping[str, Any],
    labels: MonteCarloDistributionPlotLabels | None = None,
    *,
    title_suffix: str = "",
) -> MonteCarloDistributionPlotSpec | None:
    """Build a Monte Carlo distribution histogram spec from summary metadata."""
    try:
        if summary.get("schema") != "datalab.monte_carlo_distribution_summary" or summary.get("schema_version") != 1:
            return None
        count_fields = (
            "requested_sample_count",
            "evaluated_sample_count",
            "accepted_sample_count",
            "rejected_sample_count",
            "finite_sample_count",
        )
        summary_counts: dict[str, int] = {}
        for field_name in count_fields:
            count_value = _nonnegative_plot_count(summary.get(field_name))
            if count_value is None:
                return None
            summary_counts[field_name] = count_value
        if summary_counts["evaluated_sample_count"] != summary_counts["requested_sample_count"]:
            return None
        if (
            summary_counts["accepted_sample_count"] + summary_counts["rejected_sample_count"]
            != summary_counts["evaluated_sample_count"]
        ):
            return None
        if summary_counts["finite_sample_count"] > summary_counts["accepted_sample_count"]:
            return None
        histogram = summary.get("histogram")
        percentiles = summary.get("percentiles")
        if not isinstance(histogram, Mapping) or not isinstance(percentiles, Mapping):
            return None
        bin_edges = tuple(_finite_plot_float(value) for value in histogram.get("bin_edges", ()))
        counts = tuple(_nonnegative_plot_count(value) for value in histogram.get("counts", ()))
        if not bin_edges or not counts or len(bin_edges) != len(counts) + 1:
            return None
        if any(value is None for value in bin_edges) or any(count is None for count in counts):
            return None
        checked_edges = tuple(float(value) for value in bin_edges if value is not None)
        checked_counts = tuple(int(count) for count in counts if count is not None)
        if any(right <= left for left, right in zip(checked_edges, checked_edges[1:])):
            return None
        if sum(checked_counts) <= 0:
            return None
        if sum(checked_counts) != summary_counts["finite_sample_count"]:
            return None
        mean = _finite_plot_float(summary.get("mean"))
        std = _finite_plot_float(summary.get("std"))
        if mean is None or std is None or std < 0:
            return None
        percentile_values = (
            ("2.5", _finite_plot_float(percentiles.get("2.5"))),
            ("50", _finite_plot_float(percentiles.get("50"))),
            ("97.5", _finite_plot_float(percentiles.get("97.5"))),
        )
        if any(value is None for _key, value in percentile_values):
            return None
        checked_percentiles = tuple((key, float(value)) for key, value in percentile_values if value is not None)
        percentile_numbers = tuple(value for _key, value in checked_percentiles)
        if percentile_numbers != tuple(sorted(percentile_numbers)):
            return None
        if percentile_numbers[0] < checked_edges[0] or percentile_numbers[-1] > checked_edges[-1]:
            return None
        return MonteCarloDistributionPlotSpec(
            bin_edges=checked_edges,
            counts=checked_counts,
            mean=float(mean),
            std=float(std),
            percentiles=checked_percentiles,
            labels=labels or MonteCarloDistributionPlotLabels(),
            title_suffix=title_suffix,
        )
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None


def _finite_plot_float(value: Any) -> float | None:
    try:
        parsed = mp.mpf(value)
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    if not mp.isfinite(parsed):
        return None
    return float(parsed)


def _nonnegative_plot_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return int(value)


def _statistics_plot_float(value: Any) -> float:
    return float(mp.mpf(value))


def _statistics_positive_sigma(value: Any) -> bool:
    try:
        sigma = mp.mpf(value)
    except Exception:
        return False
    return bool(mp.isfinite(sigma) and sigma > 0)


def _statistics_positive_int(value: Any) -> bool:
    try:
        parsed = mp.mpf(value)
    except Exception:
        return False
    return bool(mp.isfinite(parsed) and parsed > 0)


def _statistics_positive_sigma_pair_count(spec: StatisticsPlotSpec) -> int:
    if not spec.sigmas:
        return 0
    count = 0
    for value, sigma in zip(spec.values, spec.sigmas):
        if _statistics_finite_float(value) is not None and _statistics_positive_sigma(sigma):
            count += 1
    return count


def _statistics_weighted_residual_enabled(
    spec: StatisticsPlotSpec,
    stats_result: Mapping[str, Any],
) -> bool:
    if spec.mean is None or not spec.sigmas:
        return False
    mode = str(stats_result.get("mode") or stats_result.get("stats_mode") or "").strip()
    weighted_semantics = mode in {"weighted_sigma", "weighted"} or _statistics_positive_int(
        stats_result.get("weighted_consistency_dof")
    )
    if not weighted_semantics:
        return False
    return _statistics_positive_sigma_pair_count(spec) >= 2 or _statistics_positive_int(
        stats_result.get("weighted_consistency_dof")
    )


def _statistics_finite_float(value: Any) -> float | None:
    try:
        parsed = mp.mpf(value)
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    if not mp.isfinite(parsed):
        return None
    return float(parsed)


def _statistics_values_as_floats(values: Sequence[Any]) -> list[float]:
    converted = [_statistics_finite_float(value) for value in values]
    if any(value is None for value in converted):
        raise ValueError("statistics plot values must be finite")
    return [float(value) for value in converted if value is not None]


def _statistics_standardized_values(spec: StatisticsPlotSpec) -> list[float]:
    try:
        values = _statistics_values_as_floats(spec.values)
    except ValueError:
        return []
    if len(values) < 2:
        return []
    mean = _statistics_finite_float(spec.mean)
    if mean is None:
        mean = sum(values) / len(values)
    std = _statistics_finite_float(spec.std_mean)
    direct_std = _statistics_finite_float(spec.std)
    if direct_std is not None:
        std = direct_std
    if std is None or std <= 0:
        centered = [value - mean for value in values]
        variance = sum(value * value for value in centered) / (len(centered) - 1)
        std = variance ** 0.5
    if std <= 0:
        return []
    return sorted((value - mean) / std for value in values)


def _statistics_title(spec: StatisticsPlotSpec, title: str) -> str:
    return f"{title}{spec.batch_suffix}"


def render_statistics_plot_from_spec(spec: StatisticsPlotSpec) -> bytes | None:
    """Render a statistics plot spec to PNG bytes."""
    if not spec.values:
        return None

    if spec.plot_key == "statistics.histogram":
        return _render_statistics_histogram_from_spec(spec)
    if spec.plot_key == "statistics.box":
        return _render_statistics_box_from_spec(spec)
    if spec.plot_key == "statistics.qq":
        return _render_statistics_qq_from_spec(spec)
    if spec.plot_key == "statistics.weighted_residual":
        return _render_statistics_weighted_residual_from_spec(spec)

    fig = None
    try:
        xs = list(range(1, len(spec.values) + 1))
        ys = [_statistics_plot_float(v) for v in spec.values]
        yerr = None
        if spec.sigmas and any(s is not None for s in spec.sigmas):
            yerr = [_statistics_plot_float(abs(mp.mpf(s))) if s is not None else 0.0 for s in spec.sigmas]

        mean_f = _statistics_plot_float(spec.mean) if spec.mean is not None else None
        std_mean_f = abs(_statistics_plot_float(spec.std_mean)) if spec.std_mean is not None else None

        fig, ax = _new_figure_ax(figsize=(6.0, 4.0), dpi=180)
        if yerr:
            ax.errorbar(
                xs,
                ys,
                yerr=yerr,
                fmt="o-",
                color="#1f77b4",
                ecolor="#555555",
                capsize=4,
                label=spec.labels.data,
            )
        else:
            ax.plot(xs, ys, "o-", color="#1f77b4", label=spec.labels.data)

        if mean_f is not None:
            ax.axhline(mean_f, color="#d62728", linestyle="--", label=spec.labels.mean)
            if std_mean_f is not None and std_mean_f > 0:
                ax.fill_between(
                    [min(xs) - 0.2, max(xs) + 0.2],
                    mean_f - std_mean_f,
                    mean_f + std_mean_f,
                    color="#d62728",
                    alpha=0.15,
                    label=spec.labels.mean_band,
                )

        ax.set_xlabel(spec.labels.x_axis)
        ax.set_ylabel(spec.labels.y_axis)
        ax.set_title(_statistics_title(spec, spec.labels.title))
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def render_statistics_plots_from_specs(specs: Sequence[StatisticsPlotSpec]) -> list[bytes]:
    """Render a sequence of statistics specs, dropping plots that cannot render."""
    rendered: list[bytes] = []
    for spec in specs:
        png = render_statistics_plot_from_spec(spec)
        if png:
            rendered.append(png)
    return rendered


def render_statistics_grouped_mean_overview_from_spec(
    spec: StatisticsGroupedMeanOverviewSpec,
) -> bytes | None:
    """Render grouped per-column means with optional standard-error bars."""

    if (
        spec.plot_key != "statistics.grouped_mean_overview"
        or not spec.labels
        or len(spec.labels) != len(spec.means)
        or len(spec.std_means) != len(spec.means)
    ):
        return None
    points: list[tuple[str, float, float | None]] = []
    for label, mean, std_mean in zip(spec.labels, spec.means, spec.std_means):
        mean_value = _statistics_finite_float(mean)
        if mean_value is None:
            continue
        std_value = _statistics_finite_float(std_mean)
        if std_value is not None and std_value < 0:
            return None
        points.append((str(label), mean_value, std_value))
    if not points:
        return None

    fig = None
    try:
        plot_labels = spec.plot_labels
        width = min(12.0, max(6.0, 2.8 + 0.45 * len(points)))
        fig, ax = _new_figure_ax(figsize=(width, 4.2), dpi=180)
        xs = list(range(len(points)))
        means = [point[1] for point in points]
        std_errors = [point[2] if point[2] is not None else 0.0 for point in points]
        yerr = std_errors if any(value > 0 for value in std_errors) else None
        ax.bar(xs, means, yerr=yerr, color="#4f6bed", ecolor="#333333", capsize=4, label=plot_labels.mean)
        ax.set_xticks(xs, [point[0] for point in points], rotation=30, ha="right")
        ax.set_xlabel(plot_labels.x_axis)
        ax.set_ylabel(plot_labels.y_axis)
        ax.set_title(plot_labels.title)
        ax.grid(axis="y", alpha=0.3)
        if yerr:
            ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _time_series_x_values(labels: Sequence[str]) -> tuple[list[float], list[str] | None]:
    parsed = [_statistics_finite_float(label) for label in labels]
    if parsed and all(value is not None for value in parsed):
        return [float(value) for value in parsed if value is not None], None
    return list(range(1, len(labels) + 1)), [str(label) for label in labels]


def render_statistics_time_series_plot_from_spec(spec: StatisticsTimeSeriesPlotSpec) -> bytes | None:
    """Render a time-series statistics spec to PNG bytes."""

    if not spec.observed_values or not spec.result_values:
        return None
    fig = None
    try:
        xs, tick_labels = _time_series_x_values(spec.time_labels)
        observed = _statistics_values_as_floats(spec.observed_values)
        result_points: list[tuple[float, float, Any | None]] = []
        uncertainty_values = spec.uncertainties if spec.uncertainties is not None else (None,) * len(xs)
        for x_value, result, uncertainty in zip(xs, spec.result_values, uncertainty_values):
            result_float = _statistics_finite_float(result)
            if result_float is None:
                continue
            result_points.append((float(x_value), result_float, uncertainty))
        if not result_points:
            return None

        fig, ax = _new_figure_ax(figsize=(6.4, 4.0), dpi=180)
        ax.plot(xs, observed, "o", color="#4c78a8", markersize=4, label=spec.labels.observed)
        result_x = [point[0] for point in result_points]
        result_y = [point[1] for point in result_points]
        ax.plot(result_x, result_y, "-", color="#d62728", linewidth=2.0, label=spec.labels.result)

        band_low: list[float] = []
        band_high: list[float] = []
        band_x: list[float] = []
        for x_value, y_value, uncertainty in result_points:
            sigma = _statistics_finite_float(uncertainty)
            if sigma is None or sigma < 0:
                continue
            band_x.append(x_value)
            band_low.append(y_value - sigma)
            band_high.append(y_value + sigma)
        if band_x:
            ax.fill_between(
                band_x,
                band_low,
                band_high,
                color="#d62728",
                alpha=0.16,
                label=spec.labels.uncertainty_band,
            )

        if tick_labels:
            max_ticks = 8
            step = max(1, math.ceil(len(tick_labels) / max_ticks))
            tick_positions = xs[::step]
            shown_labels = tick_labels[::step]
            ax.set_xticks(tick_positions)
            ax.set_xticklabels(shown_labels, rotation=30, ha="right")
        ax.set_xlabel(spec.labels.x_axis)
        ax.set_ylabel(spec.labels.y_axis)
        title_suffix = f": {spec.column}" if spec.column else ""
        ax.set_title(f"{spec.labels.title}{title_suffix}")
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def render_statistics_time_series_plots_from_specs(
    specs: Sequence[StatisticsTimeSeriesPlotSpec],
) -> list[bytes]:
    """Render time-series specs, dropping plots that cannot render."""

    rendered: list[bytes] = []
    for spec in specs:
        png = render_statistics_time_series_plot_from_spec(spec)
        if png:
            rendered.append(png)
    return rendered


def _render_statistics_histogram_from_spec(spec: StatisticsPlotSpec) -> bytes | None:
    fig = None
    try:
        ys = _statistics_values_as_floats(spec.values)
        if not ys:
            return None
        bins = min(10, max(1, int(len(ys) ** 0.5 + 0.5)))
        fig, ax = _new_figure_ax(figsize=(6.0, 4.0), dpi=180)
        ax.hist(ys, bins=bins, color="#4f6bed", alpha=0.78, edgecolor="#ffffff")
        mean_f = _statistics_finite_float(spec.mean)
        if mean_f is not None:
            ax.axvline(mean_f, color="#d62728", linestyle="--", label=spec.labels.mean)
        median_f = _statistics_finite_float(spec.median)
        if median_f is not None:
            ax.axvline(median_f, color="#2ca02c", linestyle="-.", label=spec.labels.median)
        ax.set_xlabel(spec.labels.y_axis)
        ax.set_ylabel(spec.labels.frequency_axis)
        ax.set_title(_statistics_title(spec, spec.labels.histogram_title))
        ax.grid(axis="y", alpha=0.3)
        if mean_f is not None or median_f is not None:
            ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_statistics_box_from_spec(spec: StatisticsPlotSpec) -> bytes | None:
    fig = None
    try:
        ys = _statistics_values_as_floats(spec.values)
        if not ys:
            return None
        fig, ax = _new_figure_ax(figsize=(4.8, 4.0), dpi=180)
        ax.boxplot(ys, orientation="vertical", whis=1.5, showmeans=True)
        ax.set_xticks([1], [spec.labels.data])
        ax.set_ylabel(spec.labels.y_axis)
        ax.set_title(_statistics_title(spec, spec.labels.box_title))
        ax.grid(axis="y", alpha=0.3)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_statistics_qq_from_spec(spec: StatisticsPlotSpec) -> bytes | None:
    fig = None
    try:
        sample = _statistics_standardized_values(spec)
        if len(sample) < 2:
            return None
        normal = NormalDist()
        theoretical = [normal.inv_cdf((index - 0.5) / len(sample)) for index in range(1, len(sample) + 1)]
        lo = min(min(theoretical), min(sample))
        hi = max(max(theoretical), max(sample))
        fig, ax = _new_figure_ax(figsize=(5.2, 4.2), dpi=180)
        ax.scatter(theoretical, sample, color="#4f6bed", s=28)
        ax.plot([lo, hi], [lo, hi], color="#d62728", linestyle="--")
        ax.set_xlabel(spec.labels.theoretical_quantile_axis)
        ax.set_ylabel(spec.labels.sample_quantile_axis)
        ax.set_title(_statistics_title(spec, spec.labels.qq_title))
        ax.grid(True, alpha=0.3)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_statistics_weighted_residual_from_spec(spec: StatisticsPlotSpec) -> bytes | None:
    fig = None
    try:
        if spec.mean is None or not spec.sigmas:
            return None
        mean_f = _statistics_plot_float(spec.mean)
        residuals: list[float] = []
        xs: list[int] = []
        for index, (value, sigma) in enumerate(zip(spec.values, spec.sigmas), 1):
            if not _statistics_positive_sigma(sigma):
                continue
            residuals.append((_statistics_plot_float(value) - mean_f) / abs(_statistics_plot_float(sigma)))
            xs.append(index)
        if not residuals:
            return None
        fig, ax = _new_figure_ax(figsize=(6.0, 4.0), dpi=180)
        ax.axhline(0.0, color="#444444", linestyle="-", linewidth=1.0, label=spec.labels.zero_line)
        ax.axhline(3.0, color="#d62728", linestyle="--", linewidth=1.0, label=spec.labels.threshold_line)
        ax.axhline(-3.0, color="#d62728", linestyle="--", linewidth=1.0)
        ax.plot(xs, residuals, "o-", color="#4f6bed", label=spec.labels.data)
        ax.set_xlabel(spec.labels.x_axis)
        ax.set_ylabel(spec.labels.residual_axis)
        ax.set_title(_statistics_title(spec, spec.labels.weighted_residual_title))
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _fitting_finite_float(value: Any) -> float | None:
    try:
        parsed = mp.mpf(value)
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    if not mp.isfinite(parsed):
        return None
    return float(parsed)


def _fitting_finite_values(values: Sequence[Any]) -> list[float]:
    converted = [_fitting_finite_float(value) for value in values]
    if any(value is None for value in converted):
        return []
    return [float(value) for value in converted if value is not None]


def _fitting_matrix(values: Sequence[Sequence[Any]] | None) -> list[list[float]] | None:
    if values is None:
        return None
    matrix: list[list[float]] = []
    for row in values:
        converted = [_fitting_finite_float(value) for value in row]
        if any(value is None for value in converted):
            return None
        matrix.append([float(value) for value in converted if value is not None])
    return matrix


def _fitting_correlation_from_diagnostics(
    diagnostics: Mapping[str, Any] | None,
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    if not isinstance(diagnostics, Mapping):
        return (), ()
    correlation = diagnostics.get("parameter_correlation")
    if not isinstance(correlation, Mapping):
        return (), ()
    raw_names = correlation.get("parameters", ())
    raw_matrix = correlation.get("matrix", ())
    if not isinstance(raw_names, Sequence) or isinstance(raw_names, (str, bytes, bytearray, memoryview)):
        return (), ()
    if not isinstance(raw_matrix, Sequence):
        return (), ()
    names = tuple(str(name) for name in raw_names)
    matrix: list[tuple[Any, ...]] = []
    for row in raw_matrix:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            return (), ()
        matrix.append(tuple(row))
    if not _fitting_correlation_shape_is_valid(names, matrix):
        return (), ()
    return names, tuple(matrix)


def _fitting_correlation_shape_is_valid(
    names: Sequence[str],
    matrix: Sequence[Sequence[Any]],
) -> bool:
    return _correlation_heatmap_shape_is_valid(names, matrix)


def _correlation_heatmap_shape_is_valid(
    names: Sequence[str],
    matrix: Sequence[Sequence[Any]],
) -> bool:
    size = len(names)
    tolerance = 1e-9
    if size == 0 or len(matrix) != size:
        return False
    converted: list[list[float]] = []
    for row in matrix:
        if len(row) != size:
            return False
        converted_row: list[float] = []
        for value in row:
            parsed = _fitting_finite_float(value)
            if parsed is None or parsed < -1.0 - tolerance or parsed > 1.0 + tolerance:
                return False
            converted_row.append(parsed)
        converted.append(converted_row)
    for idx in range(size):
        if abs(converted[idx][idx] - 1.0) > tolerance:
            return False
        for jdx in range(idx + 1, size):
            if abs(converted[idx][jdx] - converted[jdx][idx]) > tolerance:
                return False
    return True


def _fitting_title(spec: FittingPlotSpec, title: str) -> str:
    return f"{title}{spec.batch_suffix}"


def render_fitting_plot_from_spec(spec: FittingPlotSpec) -> bytes | None:
    """Render a fitting plot spec to PNG bytes."""
    if spec.plot_key == "fitting.overview":
        return render_fitting_overview_from_spec(spec)
    if spec.plot_key == "fitting.residual":
        return _render_fitting_residual_from_spec(spec)
    if spec.plot_key == "fitting.residual_histogram":
        return _render_fitting_histogram_from_spec(spec)
    if spec.plot_key == "fitting.residual_qq":
        return _render_fitting_qq_from_spec(spec)
    if spec.plot_key == "fitting.correlation_heatmap":
        return _render_fitting_correlation_heatmap_from_spec(spec)
    return None


def render_fitting_plots_from_specs(specs: Sequence[FittingPlotSpec]) -> list[bytes]:
    rendered: list[bytes] = []
    for spec in specs:
        png = render_fitting_plot_from_spec(spec)
        if png:
            rendered.append(png)
    return rendered


def render_fitting_overview_from_spec(
    spec: FittingPlotSpec,
    *,
    log_scale: str | None = None,
    dpi: int = 220,
    export_pdf_path: str | None = None,
    export_eps_path: str | None = None,
) -> bytes | None:
    """Render the legacy fitting overview from a semantic fitting spec."""
    x_plot = _fitting_finite_values(spec.x_values)
    y_plot = _fitting_finite_values(spec.y_values)
    fitted = _fitting_finite_values(spec.fitted_values)
    residuals = _fitting_finite_values(spec.residuals)
    if spec.show_curves:
        if not x_plot or not y_plot or len(x_plot) != len(y_plot):
            return None
        if spec.fitted_values and (not fitted or len(fitted) != len(x_plot)):
            return None
        if spec.residuals and (not residuals or len(residuals) != len(x_plot)):
            return None
        if spec.sigmas and len(spec.sigmas) != len(x_plot):
            return None
        if not _fitting_band_shapes_valid(spec, len(x_plot)):
            return None
    elif spec.residuals and y_plot and len(residuals) != len(y_plot):
        return None

    if (not spec.show_curves) or not x_plot:
        x_plot = list(range(len(y_plot)))
    fig = None
    try:
        # OO figure (no pyplot global state — thread-safe, P2-7).
        fig = _Figure(figsize=(11, 8), dpi=dpi)
        _FigureCanvasAgg(fig)
        gs = fig.add_gridspec(2, 2, height_ratios=[3, 2])
        ax_main = fig.add_subplot(gs[0, 0])
        ax_resid = fig.add_subplot(gs[1, 0], sharex=ax_main)
        ax_hist = fig.add_subplot(gs[0, 1])
        ax_param = fig.add_subplot(gs[1, 1])

        if spec.show_curves and x_plot and y_plot:
            yerr = None
            if spec.sigmas:
                yerr = [abs(float(mp.mpf(sigma))) if sigma is not None else 0.0 for sigma in spec.sigmas]
            if yerr:
                ax_main.errorbar(
                    x_plot,
                    y_plot,
                    yerr=yerr,
                    fmt="o",
                    color="#1f77b4",
                    ecolor="#555555",
                    capsize=3,
                    label=f"{spec.labels.data}±σ",
                    zorder=3,
                )
            else:
                ax_main.scatter(x_plot, y_plot, c="#1f77b4", label=spec.labels.data, zorder=3)
            if fitted:
                ax_main.plot(x_plot, fitted, label=spec.parameter_label or spec.labels.fit, color="#d62728")
                _draw_fitting_bands(ax_main, x_plot, fitted, residuals, spec)
            if log_scale:
                if "x" in log_scale.lower():
                    ax_main.set_xscale("log")
                if "y" in log_scale.lower():
                    ax_main.set_yscale("log")
            ax_main.set_title(spec.labels.main_title)
            ax_main.set_ylabel(spec.labels.y_axis)
            ax_main.legend(frameon=False)
            ax_main.grid(True, alpha=0.3)
            _draw_fitting_residual_axis(ax_resid, x_plot, residuals, spec)
        else:
            ax_main.axis("off")
            ax_main.text(0.5, 0.5, spec.labels.multidim_message, ha="center", va="center")
            idx = list(range(len(residuals)))
            _draw_fitting_residual_axis(ax_resid, idx, residuals, spec, index_axis=True)

        _draw_fitting_histogram_axis(ax_hist, residuals, spec)
        _draw_fitting_comparison(ax_hist, spec)
        _draw_fitting_parameter_axis(ax_param, spec)
        for ax in (ax_main, ax_resid, ax_hist, ax_param):
            apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
        if export_pdf_path:
            try:
                fig.savefig(export_pdf_path, format="pdf", dpi=dpi)
            except OSError:
                pass
        if export_eps_path:
            try:
                fig.savefig(export_eps_path, format="eps", dpi=dpi)
            except OSError:
                pass
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _fitting_band_shapes_valid(spec: FittingPlotSpec, row_count: int) -> bool:
    for band in (spec.confidence_band, spec.prediction_band):
        if band is None:
            continue
        if len(band.lower) != row_count or len(band.upper) != row_count:
            return False
        if not _fitting_finite_values(band.lower) or not _fitting_finite_values(band.upper):
            return False
    return True


def _draw_fitting_bands(
    ax: Any,
    x_values: Sequence[float],
    fitted: Sequence[float],
    residuals: Sequence[float],
    spec: FittingPlotSpec,
) -> None:
    if spec.prediction_band is not None:
        ax.fill_between(
            x_values,
            [float(value) for value in spec.prediction_band.lower],
            [float(value) for value in spec.prediction_band.upper],
            facecolor="#f4b183",
            edgecolor="#c45f00",
            linewidth=0.5,
            alpha=0.22,
            label=spec.prediction_band.label,
            zorder=1,
        )
    if spec.confidence_band is not None:
        ax.fill_between(
            x_values,
            [float(value) for value in spec.confidence_band.lower],
            [float(value) for value in spec.confidence_band.upper],
            facecolor="#9ecae1",
            edgecolor="#3182bd",
            linewidth=0.5,
            alpha=0.35,
            label=spec.confidence_band.label,
            zorder=2,
        )
        return
    if residuals:
        rmse = (sum(value * value for value in residuals) / max(1, len(residuals))) ** 0.5
        band_half = 2.0 * rmse
        ax.fill_between(
            x_values,
            [value - band_half for value in fitted],
            [value + band_half for value in fitted],
            facecolor="#e99c9c",
            edgecolor="#d62728",
            linewidth=0.5,
            alpha=0.35,
            label=spec.labels.legacy_rmse_band,
            zorder=1,
        )


def _draw_fitting_residual_axis(
    ax: Any,
    x_values: Sequence[float],
    residuals: Sequence[float],
    spec: FittingPlotSpec,
    *,
    index_axis: bool = False,
) -> None:
    if residuals:
        ax.scatter(x_values, residuals, s=22, color="#1f77b4", label=spec.labels.residual)
        if spec.sigmas and len(spec.sigmas) == len(residuals):
            xs = list(x_values)
            upper: list[float] = []
            lower: list[float] = []
            for sigma in spec.sigmas:
                sigma_f = _fitting_finite_float(sigma)
                upper.append(abs(sigma_f) if sigma_f is not None else 0.0)
                lower.append(-abs(sigma_f) if sigma_f is not None else 0.0)
            ax.plot(xs, upper, color="#ff7f0e", linestyle=":", linewidth=0.9, label=spec.labels.sigma_band)
            ax.plot(xs, lower, color="#ff7f0e", linestyle=":", linewidth=0.9)
    else:
        ax.axis("off")
        return
    ax.axhline(0, color="black", linewidth=0.6, linestyle="--", label=spec.labels.zero_line)
    ax.set_xlabel(spec.labels.index_axis if index_axis else spec.labels.x_axis)
    ax.set_ylabel(spec.labels.residual)
    ax.set_title(spec.labels.residual_index_title if index_axis else spec.labels.residual_title)
    ax.grid(True, alpha=0.3)


def _draw_fitting_histogram_axis(ax: Any, residuals: Sequence[float], spec: FittingPlotSpec) -> None:
    if len(residuals) >= 4:
        ax.hist(residuals, bins=max(8, int(len(residuals) ** 0.5)), color="#9467bd", alpha=0.8)
        ax.set_title(spec.labels.histogram_title)
        ax.set_xlabel(spec.labels.residual)
        ax.set_ylabel(spec.labels.count_axis)
        ax.grid(True, alpha=0.25)
        return
    ax.set_title(spec.labels.residual_summary_title)
    ax.axis("off")


def _draw_fitting_comparison(ax: Any, spec: FittingPlotSpec) -> None:
    if not spec.comparison:
        return
    lines = ["Model comparison (AIC/BIC/R2):"]
    sorted_comp: Sequence[tuple[str, Any, Any, Any]]
    try:
        sorted_comp = sorted(spec.comparison, key=lambda entry: float(entry[1]))
    except Exception:
        sorted_comp = spec.comparison
    for name, aic, bic, r2 in sorted_comp:
        try:
            lines.append(f"{name}: AIC={float(aic):.3g}, BIC={float(bic):.3g}, R2={float(r2):.4g}")
        except Exception:
            lines.append(f"{name}: AIC={aic}, BIC={bic}, R2={r2}")
    ax.text(
        0.99,
        0.95,
        "\n".join(lines),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize="x-small",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#f6f6f6", edgecolor="#cccccc"),
    )


def _draw_fitting_parameter_axis(ax: Any, spec: FittingPlotSpec) -> None:
    values = _fitting_finite_values(spec.parameter_values)
    errors = _fitting_finite_values(spec.parameter_errors)
    if spec.parameter_names and values and len(values) == len(spec.parameter_names):
        yerr = errors if len(errors) == len(values) else [0.0 for _ in values]
        positions = range(len(spec.parameter_names))
        ax.ticklabel_format(axis="x", style="sci", scilimits=(-3, 3))
        ax.errorbar(values, positions, xerr=[abs(value) for value in yerr], fmt="o", color="#7570b3", ecolor="#555555", capsize=4)
        for pos, name, value in zip(positions, spec.parameter_names, values):
            ax.text(value, pos, f"{name} = {value:.4g}", va="center", ha="left", fontsize="small")
        ax.set_yticks(list(positions))
        ax.set_yticklabels(list(spec.parameter_names))
        ax.set_xlabel(spec.labels.parameter_axis)
        ax.set_title(spec.labels.parameter_title)
        ax.grid(True, axis="x", alpha=0.3)
        return
    ax.axis("off")


def _render_fitting_residual_from_spec(spec: FittingPlotSpec) -> bytes | None:
    residuals = _fitting_finite_values(spec.residuals)
    if not residuals:
        return None
    xs = _fitting_finite_values(spec.x_values)
    if (not spec.show_curves) or not xs:
        xs = list(range(len(residuals)))
    if len(xs) != len(residuals):
        return None
    fig = None
    try:
        fig, ax = _new_figure_ax(figsize=(6.0, 4.0), dpi=180)
        _draw_fitting_residual_axis(ax, xs, residuals, spec, index_axis=not spec.show_curves)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_fitting_histogram_from_spec(spec: FittingPlotSpec) -> bytes | None:
    residuals = _fitting_finite_values(spec.residuals)
    if len(residuals) < 2:
        return None
    fig = None
    try:
        fig, ax = _new_figure_ax(figsize=(5.2, 4.0), dpi=180)
        _draw_fitting_histogram_axis(ax, residuals, spec)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_fitting_qq_from_spec(spec: FittingPlotSpec) -> bytes | None:
    residuals = sorted(_fitting_finite_values(spec.residuals))
    if len(residuals) < 2:
        return None
    fig = None
    try:
        normal = NormalDist()
        theoretical = [normal.inv_cdf((index - 0.5) / len(residuals)) for index in range(1, len(residuals) + 1)]
        lo = min(min(theoretical), min(residuals))
        hi = max(max(theoretical), max(residuals))
        fig, ax = _new_figure_ax(figsize=(5.2, 4.2), dpi=180)
        ax.scatter(theoretical, residuals, color="#4f6bed", s=28)
        ax.plot([lo, hi], [lo, hi], color="#d62728", linestyle="--")
        ax.set_xlabel(spec.labels.theoretical_quantile_axis)
        ax.set_ylabel(spec.labels.sample_quantile_axis)
        ax.set_title(_fitting_title(spec, spec.labels.qq_title))
        ax.grid(True, alpha=0.3)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def _render_fitting_correlation_heatmap_from_spec(spec: FittingPlotSpec) -> bytes | None:
    return render_correlation_heatmap_from_spec(
        CorrelationHeatmapSpec(
            plot_key=spec.plot_key,
            names=spec.correlation_names,
            matrix=spec.correlation_matrix,
            title=_fitting_title(spec, spec.labels.correlation_title),
        )
    )


def render_correlation_heatmap_from_spec(spec: CorrelationHeatmapSpec) -> bytes | None:
    matrix = _fitting_matrix(spec.matrix)
    if matrix is None or not matrix or not spec.names or not _correlation_heatmap_shape_is_valid(spec.names, matrix):
        return None
    fig = None
    try:
        fig, ax = _new_figure_ax(figsize=(5.0, 4.4), dpi=180)
        image = ax.imshow(matrix, cmap="coolwarm", vmin=-1, vmax=1)
        ax.set_xticks(range(len(spec.names)), spec.names, rotation=45, ha="right")
        ax.set_yticks(range(len(spec.names)), spec.names)
        ax.set_title(spec.title)
        for i, row in enumerate(matrix):
            for j, value in enumerate(row):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="#111111", fontsize="small")
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        apply_cjk_font(ax)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def render_error_contribution_plot_from_spec(spec: ErrorContributionPlotSpec) -> bytes | None:
    """Render the current error-contribution bar plot to PNG bytes."""
    if not spec.labels or not spec.percents or len(spec.labels) != len(spec.percents):
        return None
    if spec.cumulative_percents and len(spec.cumulative_percents) != len(spec.labels):
        return None

    fig = None
    try:
        fig, ax = _new_figure_ax(figsize=(6.0, 0.45 * len(spec.labels) + 1.2), dpi=180)
        y_pos = list(range(len(spec.labels)))
        bars = ax.barh(y_pos, spec.percents, color="#4f6bed")
        ax.invert_yaxis()
        ax.set_xlabel(spec.plot_labels.x_axis)
        max_percent = max(spec.percents, default=0.0)
        if spec.cumulative_percents:
            max_percent = max(max_percent, max(spec.cumulative_percents))
        ax.set_xlim(0, max(100.0, max_percent * 1.1))
        ax.set_yticks(y_pos, spec.labels)
        for bar, pct in zip(bars, spec.percents):
            ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2, f"{pct:.2f}%", va="center")
        if spec.cumulative_percents:
            ax.plot(
                spec.cumulative_percents,
                y_pos,
                color="#d62728",
                marker="o",
                linewidth=1.6,
                label=spec.plot_labels.cumulative_label,
            )
            ax.legend(frameon=False, loc="lower right")
        ax.grid(axis="x", alpha=0.3, linestyle="--")
        title = spec.plot_labels.title
        if spec.title_suffix:
            title = f"{title} - {spec.title_suffix}"
        ax.set_title(title)
        apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def render_monte_carlo_distribution_plot_from_spec(spec: MonteCarloDistributionPlotSpec) -> bytes | None:
    """Render a Monte Carlo distribution histogram spec to PNG bytes."""
    if not spec.bin_edges or not spec.counts or len(spec.bin_edges) != len(spec.counts) + 1:
        return None
    if not all(math.isfinite(value) for value in (*spec.bin_edges, spec.mean, spec.std)):
        return None
    if spec.std < 0 or any(count < 0 for count in spec.counts):
        return None
    if any(right <= left for left, right in zip(spec.bin_edges, spec.bin_edges[1:])):
        return None
    if sum(spec.counts) <= 0:
        return None
    if not spec.percentiles or any(not math.isfinite(value) for _label, value in spec.percentiles):
        return None

    fig = None
    try:
        widths = [right - left for left, right in zip(spec.bin_edges, spec.bin_edges[1:])]
        fig, ax = _new_figure_ax(figsize=(6.0, 4.0), dpi=180)
        ax.bar(
            spec.bin_edges[:-1],
            spec.counts,
            width=widths,
            align="edge",
            color="#4f6bed",
            alpha=0.75,
            edgecolor="#2f3f8f",
            linewidth=0.6,
        )
        ax.axvline(spec.mean, color="#d62728", linewidth=1.8, label=spec.labels.mean)
        if spec.std > 0:
            ax.axvline(
                spec.mean - spec.std,
                color="#ff7f0e",
                linestyle="--",
                linewidth=1.2,
                label=spec.labels.mean_minus_std,
            )
            ax.axvline(
                spec.mean + spec.std,
                color="#ff7f0e",
                linestyle="--",
                linewidth=1.2,
                label=spec.labels.mean_plus_std,
            )
        else:
            ax.axvline(
                spec.mean,
                color="#ff7f0e",
                linestyle="--",
                linewidth=1.0,
                label=f"{spec.labels.mean_minus_std}/{spec.labels.mean_plus_std}",
            )
        percentile_labels = {
            "2.5": spec.labels.percentile_2_5,
            "50": spec.labels.percentile_50,
            "97.5": spec.labels.percentile_97_5,
        }
        for key, value in spec.percentiles:
            ax.axvline(
                value,
                color="#2ca02c",
                linestyle=":",
                linewidth=1.1,
                label=percentile_labels.get(key, key),
            )
        ax.set_xlabel(spec.labels.x_axis)
        ax.set_ylabel(spec.labels.y_axis)
        title = spec.labels.title
        if spec.title_suffix:
            title = f"{title} - {spec.title_suffix}"
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25, linestyle="--")
        ax.legend(frameon=False, fontsize=8)
        apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        _logger.warning("plot rendering failed; returning no image", exc_info=True)
        return None
    finally:
        if fig is not None:
            fig.clear()


def assert_agg_backend() -> None:
    """Verify the current backend is Agg. Called from regression tests
    to make a backend drift visible at test time rather than at user-
    visible crash time (e.g., a headless CI with Qt backend selected
    would succeed locally but fail in CI)."""
    current = _matplotlib.get_backend().lower()
    if current != "agg":
        raise RuntimeError(
            f"matplotlib backend drifted to {current!r}; expected 'agg'. "
            "Check that every module importing pyplot routes through "
            "shared.plotting."
        )
