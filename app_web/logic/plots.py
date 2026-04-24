from __future__ import annotations

import io

import mpmath as mp


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
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
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
    all_contributions: dict[str, mp.mpf] = {}
    total_variance = mp.mpf("0")

    for res in results:
        if not hasattr(res, "contributions") or not res.contributions:
            continue
        for name, variance in res.contributions.items():
            all_contributions[name] = all_contributions.get(name, mp.mpf("0")) + mp.mpf(variance)
            total_variance += mp.mpf(variance)

    if not all_contributions or total_variance <= 0:
        return None

    summary = []
    for name, variance in all_contributions.items():
        percent = float((variance / total_variance) * 100) if total_variance > 0 else 0.0
        summary.append({"name": name, "percent": percent})

    summary.sort(key=lambda x: x["percent"], reverse=True)
    if not summary:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    try:
        labels = [entry["name"] for entry in summary]
        percents = [entry["percent"] for entry in summary]

        fig, ax = plt.subplots(figsize=(6.0, 0.45 * len(summary) + 1.2), dpi=180)
        y_pos = list(range(len(labels)))
        bars = ax.barh(y_pos, percents, color="#4f6bed")
        ax.invert_yaxis()
        is_en = (lang or "").lower().startswith("en")
        ax.set_xlabel("Uncertainty contribution (%)" if is_en else "不确定度贡献 (%)")
        ax.set_xlim(0, max(100.0, (max(percents) if percents else 0) * 1.1))
        ax.set_yticks(y_pos, labels)

        for bar, pct in zip(bars, percents):
            ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2, f"{pct:.2f}%", va="center")

        ax.grid(axis="x", alpha=0.3, linestyle="--")
        ax.set_title("Uncertainty contribution breakdown" if is_en else "不确定度贡献分解")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def _render_statistics_plot(
    values: list[mp.mpf],
    sigmas: list[mp.mpf | None] | None,
    stats_result: dict[str, object],
    lang: str = "zh",
) -> bytes | None:
    """Render a statistics plot showing data points, mean, and error bars."""
    if not values:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    try:
        xs = list(range(1, len(values) + 1))
        ys = [float(mp.mpf(v)) for v in values]
        yerr = None
        if sigmas and any(s is not None for s in sigmas):
            yerr = [abs(float(mp.mpf(s))) if s is not None else 0.0 for s in sigmas]

        mean_val = stats_result.get("mean", None)
        std_mean = stats_result.get("std_mean", None)
        mean_f = float(mp.mpf(mean_val)) if mean_val is not None else None
        std_mean_f = abs(float(mp.mpf(std_mean))) if std_mean is not None else None

        is_en = (lang or "").lower().startswith("en")
        label_data = "Data" if is_en else "数据"
        label_mean = "Mean" if is_en else "平均值"
        label_mean_band = "Mean ± standard error" if is_en else "平均值±标准误差"
        xlabel = "Point index" if is_en else "点序号"
        ylabel = "Value" if is_en else "数值"
        title = "Statistical mean" if is_en else "统计平均"

        fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=180)
        if yerr:
            ax.errorbar(
                xs,
                ys,
                yerr=yerr,
                fmt="o-",
                color="#1f77b4",
                ecolor="#555555",
                capsize=4,
                label=label_data,
            )
        else:
            ax.plot(xs, ys, "o-", color="#1f77b4", label=label_data)

        if mean_f is not None:
            ax.axhline(mean_f, color="#d62728", linestyle="--", label=label_mean)
            if std_mean_f is not None and std_mean_f > 0:
                ax.fill_between(
                    [min(xs) - 0.2, max(xs) + 0.2],
                    mean_f - std_mean_f,
                    mean_f + std_mean_f,
                    color="#d62728",
                    alpha=0.15,
                    label=label_mean_band,
                )

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None

