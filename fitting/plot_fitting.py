"""Matplotlib-based visualization helpers for fitting results."""

from __future__ import annotations

import io
from typing import Callable, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
from matplotlib import rcParams  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from mpmath import mp

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = [
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
rcParams["axes.unicode_minus"] = False


def sample_mp_function(
    func: Callable[[mp.mpf], mp.mpf],
    x_values: Sequence[mp.mpf],
    precision: int | None = None,
) -> list[mp.mpf]:
    """Evaluate an mp function across a sequence while preserving precision."""

    previous_dps = None
    if precision is not None and precision > mp.dps:
        previous_dps = mp.dps
        mp.dps = precision
    samples: list[mp.mpf] = []
    try:
        for value in x_values:
            mp_x = mp.mpf(value)
            try:
                samples.append(mp.mpf(func(mp_x)))
            except Exception:
                samples.append(mp.nan)
    finally:
        if previous_dps is not None:
            mp.dps = previous_dps
    return samples


def render_fitting_overview(
    x_values: Sequence[float],
    y_values: Sequence[float],
    fitted_series: Sequence[tuple[str, Sequence[float]]],
    residual_series: Sequence[tuple[str, Sequence[float]]],
    uncertainties: Sequence[float] | None = None,
    comparison: Sequence[tuple[str, float, float, float]] | None = None,
    parameter_info: tuple[str, dict[str, object], dict[str, object]] | None = None,
    log_scale: str | None = None,
    dpi: int = 220,
    export_pdf_path: str | None = None,
    export_eps_path: str | None = None,
    show_curves: bool = True,
) -> bytes:
    x_plot = [float(val) for val in x_values]
    y_plot = [float(val) for val in y_values]
    if show_curves and not x_plot:
        raise ValueError("show_curves=True requires non-empty x_values.")
    # For multidimensional cases (no curve plot), synthesize a dummy x axis to keep downstream plots stable.
    if (not show_curves) or not x_plot:
        x_plot = list(range(len(y_plot)))
    n = len(x_plot)
    if show_curves:
        if len(y_plot) != n:
            raise ValueError("x_values and y_values must have the same length.")
        if uncertainties is not None and len(uncertainties) != n:
            raise ValueError("uncertainties must have the same length as x_values.")
        if fitted_series:
            if len(fitted_series[0][1]) != n:
                raise ValueError("fitted_series[0] length must match x_values length.")
        if residual_series:
            if len(residual_series[0][1]) != n:
                raise ValueError("residual_series[0] length must match x_values length.")
    else:
        if residual_series and residual_series[0][1]:
            if len(residual_series[0][1]) != len(y_plot):
                raise ValueError("In multidimensional mode, residual_series[0] must match y_values length.")
    fig = plt.figure(figsize=(11, 8), dpi=dpi)
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 2])

    ax_main = fig.add_subplot(gs[0, 0])
    ax_resid = fig.add_subplot(gs[1, 0], sharex=ax_main)
    ax_hist = fig.add_subplot(gs[0, 1])
    ax_param = fig.add_subplot(gs[1, 1])

    # 1) 数据散点 + 拟合曲线/置信带
    if show_curves and x_plot and y_plot:
        if uncertainties:
            yerr = [abs(float(u)) for u in uncertainties]
            ax_main.errorbar(
                x_plot,
                y_plot,
                yerr=yerr,
                fmt="o",
                color="#1f77b4",
                ecolor="#555555",
                capsize=3,
                label="Data±σ",
                zorder=3,
            )
        else:
            ax_main.scatter(x_plot, y_plot, c="#1f77b4", label="Data", zorder=3)

        if fitted_series:
            label, series = fitted_series[0]
            fit_vals = [float(v) for v in series]
            ax_main.plot(x_plot, fit_vals, label=label, color="#d62728")
            # 置信带: 使用 residual_series 或直接计算 (y_fit - y_data) 的 RMSE
            rmse = None
            if residual_series and residual_series[0][1]:
                resid = [float(r) for r in residual_series[0][1]]
                rmse = (sum(r * r for r in resid) / max(1, len(resid))) ** 0.5
            if rmse is None and len(fit_vals) == len(y_plot):
                resid = [f - y for f, y in zip(fit_vals, y_plot)]
                rmse = (sum(r * r for r in resid) / max(1, len(resid))) ** 0.5 if resid else None
            if rmse is not None:
                band_half = 2.0 * rmse  # show ±2×RMSE and label accordingly
                upper = [y + band_half for y in fit_vals]
                lower = [y - band_half for y in fit_vals]
                ax_main.fill_between(
                    x_plot,
                    lower,
                    upper,
                    facecolor="#e99c9c",
                    edgecolor="#d62728",
                    linewidth=0.5,
                    alpha=0.35,
                    label="±2×RMSE band",
                    zorder=1,
                )

        if log_scale:
            if "x" in log_scale.lower():
                ax_main.set_xscale("log")
            if "y" in log_scale.lower():
                ax_main.set_yscale("log")

        ax_main.set_title("Data & Fit")
        ax_main.set_ylabel("y")
        ax_main.legend(frameon=False)
        ax_main.grid(True, alpha=0.3)

        # 2) 残差 vs x
        if residual_series:
            label_r, series_r = residual_series[0]
            ax_resid.scatter(x_plot, [float(v) for v in series_r], s=22, color="#1f77b4", label=label_r)
        ax_resid.axhline(0, color="black", linewidth=0.6, linestyle="--")
        ax_resid.set_xlabel("x")
        ax_resid.set_ylabel("Residual")
        ax_resid.set_title("Residual vs x")
        ax_resid.grid(True, alpha=0.3)
    else:
        ax_main.axis("off")
        ax_main.text(0.5, 0.5, "Multidimensional model\n(curve plot skipped)", ha="center", va="center")
        if residual_series and residual_series[0][1]:
            resid_vals = [float(v) for v in residual_series[0][1]]
            idx = list(range(len(resid_vals)))
            ax_resid.scatter(idx, resid_vals, s=22, color="#1f77b4")
            ax_resid.axhline(0, color="black", linewidth=0.6, linestyle="--")
            ax_resid.set_xlabel("Point index")
            ax_resid.set_ylabel("Residual")
            ax_resid.set_title("Residual vs index")
            ax_resid.grid(True, alpha=0.3)
        else:
            ax_resid.axis("off")

    # 3) 残差直方图
    hist_drawn = False
    if residual_series:
        resid_vals = [float(v) for v in residual_series[0][1]]
        if len(resid_vals) >= 4:
            ax_hist.hist(resid_vals, bins=max(8, int(len(resid_vals) ** 0.5)), color="#9467bd", alpha=0.8)
            ax_hist.set_title("Residual Histogram")
            ax_hist.set_xlabel("Residual")
            ax_hist.set_ylabel("Count")
            ax_hist.grid(True, alpha=0.25)
            hist_drawn = True
    if not hist_drawn:
        ax_hist.set_title("Residual Summary")
        ax_hist.axis("off")

    if comparison:
        lines = ["Model comparison (AIC/BIC/R2):"]
        try:
            sorted_comp = sorted(comparison, key=lambda t: t[1])
        except Exception:
            sorted_comp = comparison
        for name, aic, bic, r2 in sorted_comp:
            lines.append(f"{name}: AIC={aic:.3g}, BIC={bic:.3g}, R2={r2:.4g}")
        ax_hist.text(
            0.99,
            0.95,
            "\n".join(lines),
            transform=ax_hist.transAxes,
            ha="right",
            va="top",
            fontsize="x-small",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f6f6f6", edgecolor="#cccccc"),
        )

    if parameter_info:
        label, params_dict, errors_dict = parameter_info
        names = list(params_dict.keys())
        values = [float(params_dict[name]) for name in names]
        yerr = [abs(float(errors_dict.get(name, 0))) for name in names]
        positions = range(len(names))
        # use scientific notation for x-axis
        ax_param.ticklabel_format(axis="x", style="sci", scilimits=(-3, 3))
        ax_param.errorbar(
            values,
            positions,
            xerr=yerr,
            fmt="o",
            color="#7570b3",
            ecolor="#555555",
            capsize=4,
        )
        for pos, name, value in zip(positions, names, values):
            ax_param.text(
                value,
                pos,
                f"{name} = {value:.4g}",
                va="center",
                ha="left",
                fontsize="small",
            )
        ax_param.set_yticks(list(positions))
        ax_param.set_yticklabels(names)
        ax_param.set_xlabel("Value")
        ax_param.set_title("Parameter Uncertainties")
        ax_param.grid(True, axis="x", alpha=0.3)
    else:
        ax_param.axis("off")

    buf = io.BytesIO()
    fig.tight_layout()
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
    plt.close(fig)
    return buf.getvalue()
