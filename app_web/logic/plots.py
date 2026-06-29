from __future__ import annotations

from collections.abc import Mapping
import io

import mpmath as mp

from shared.error_contributions import (
    aggregate_contribution_summary,
    render_error_contribution_plot,
    render_monte_carlo_distribution_plot,
)


def _render_extrapolation_plot(
    row_values: tuple[mp.mpf, ...],
    extrap_value: mp.mpf,
    sigma: mp.mpf,
    idx: int,
    lang: str = "zh",
) -> bytes | None:
    """
    Generate extrapolation trend plot for a single row.

    Returns PNG bytes or None if plotting fails.
    """
    if not row_values:
        return None

    try:
        from shared.plotting import apply_cjk_font, plt  # centralised backend = Agg
    except Exception:
        return None

    try:
        y_vals = [float(mp.mpf(v)) for v in row_values]
        x_vals = list(range(1, len(y_vals) + 1))
        x_extrap = x_vals[-1] + 1
        y_extrap = float(extrap_value)
        yerr = abs(float(sigma))

        is_en = (lang or "").lower().startswith("en")
        label_data = "Data" if is_en else "数据"
        label_extrap = f"Extrapolated ±σ (row {idx})" if is_en else f"外推值±σ (行 {idx})"
        xlabel = "Point index" if is_en else "点序号"
        ylabel = "Value" if is_en else "数值"
        title = f"Extrapolation trend: row {idx}" if is_en else f"外推趋势：行 {idx}"

        fig, ax = plt.subplots(figsize=(6, 4), dpi=180)
        ax.plot(x_vals, y_vals, marker="o", linestyle="-", color="#1f77b4", label=label_data)
        ax.plot([x_vals[-1], x_extrap], [y_vals[-1], y_extrap], linestyle="--", color="#d62728", alpha=0.7)
        ax.errorbar(
            x_extrap,
            y_extrap,
            yerr=yerr,
            fmt="o",
            color="#d62728",
            ecolor="#555555",
            capsize=4,
            label=label_extrap,
        )
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        apply_cjk_font(ax)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def _render_contribution_plot(
    results: list[object],
    lang: str = "zh",
) -> bytes | None:
    """Generate uncertainty contribution breakdown plot (PNG bytes)."""
    summary = aggregate_contribution_summary(results)
    total_variance = sum(mp.mpf(entry.get("variance", mp.mpf("0"))) for entry in summary)
    if total_variance <= 0:
        return None
    return render_error_contribution_plot(
        summary,
        lang,
        title_en="Uncertainty contribution breakdown",
        title_zh="不确定度贡献分解",
    )


def _render_monte_carlo_distribution_plot(
    summary: object,
    lang: str = "zh",
    *,
    row_index: int | None = None,
) -> bytes | None:
    if not isinstance(summary, Mapping):
        return None
    result = render_monte_carlo_distribution_plot(summary, lang, row_index=row_index)
    return result if isinstance(result, bytes) or result is None else None


def _render_statistics_plot(
    values: list[mp.mpf],
    sigmas: list[mp.mpf | None] | None,
    stats_result: dict[str, object],
    lang: str = "zh",
) -> bytes | None:
    """Render a statistics plot showing data points, mean, and error bars."""
    try:
        from shared.plotting import (
            render_statistics_plot_from_spec,
            statistics_plot_spec_from_result,
            StatisticsPlotLabels,
        )
    except Exception:
        return None

    is_en = (lang or "").lower().startswith("en")
    spec = statistics_plot_spec_from_result(
        values,
        sigmas,
        stats_result,
        StatisticsPlotLabels(
            data="Data" if is_en else "数据",
            mean="Mean" if is_en else "平均值",
            mean_band="Mean ± standard error" if is_en else "平均值±标准误差",
            x_axis="Point index" if is_en else "点序号",
            y_axis="Value" if is_en else "数值",
            title="Statistical mean" if is_en else "统计平均",
        ),
    )
    if spec is None:
        return None
    return render_statistics_plot_from_spec(spec)


def _render_statistics_plots(
    values: list[mp.mpf],
    sigmas: list[mp.mpf | None] | None,
    stats_result: dict[str, object],
    lang: str = "zh",
) -> list[bytes]:
    """Render all supported statistics plots."""
    try:
        from shared.plotting import (
            render_statistics_plots_from_specs,
            statistics_plot_specs_from_result,
            StatisticsPlotLabels,
        )
    except Exception:
        return []

    is_en = (lang or "").lower().startswith("en")
    specs = statistics_plot_specs_from_result(
        values,
        sigmas,
        stats_result,
        StatisticsPlotLabels(
            data="Data" if is_en else "数据",
            mean="Mean" if is_en else "平均值",
            mean_band="Mean ± standard error" if is_en else "平均值±标准误差",
            x_axis="Point index" if is_en else "点序号",
            y_axis="Value" if is_en else "数值",
            title="Statistical mean" if is_en else "统计平均",
            median="Median" if is_en else "中位数",
            histogram_title="Histogram" if is_en else "直方图",
            box_title="Box plot" if is_en else "箱线图",
            qq_title="Normal QQ plot" if is_en else "正态 QQ 图",
            weighted_residual_title="Weighted residuals" if is_en else "加权残差",
            frequency_axis="Frequency" if is_en else "频数",
            theoretical_quantile_axis="Theoretical normal quantile" if is_en else "理论正态分位数",
            sample_quantile_axis="Sample standardized quantile" if is_en else "样本标准化分位数",
            residual_axis="Standardized residual" if is_en else "标准化残差",
        ),
    )
    return render_statistics_plots_from_specs(specs)
