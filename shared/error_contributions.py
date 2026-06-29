from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import mpmath as mp


ContributionSummaryRow = dict[str, object]


def aggregate_contribution_variances(results: Sequence[object]) -> dict[str, mp.mpf]:
    """Aggregate valid per-result contribution variances by contribution name."""
    contrib_sum: dict[str, mp.mpf] = {}
    for entry in results:
        contribs = getattr(entry, "contributions", None)
        if not contribs:
            continue
        for name, value in contribs.items():
            try:
                contrib_sum[str(name)] = contrib_sum.get(str(name), mp.mpf("0")) + mp.mpf(value)
            except Exception:
                continue
    return contrib_sum


def contribution_summary_rows(contrib_map: Mapping[str, Any]) -> list[ContributionSummaryRow]:
    if not contrib_map:
        return []

    normalized: dict[str, mp.mpf] = {}
    for name, value in contrib_map.items():
        try:
            normalized[str(name)] = mp.mpf(value)
        except Exception:
            continue
    if not normalized:
        return []

    total_var = sum(normalized.values())
    if total_var <= 0:
        total_var = mp.mpf("0")

    summary: list[ContributionSummaryRow] = []
    for name, var in normalized.items():
        sigma = mp.sqrt(var) if var >= 0 else mp.mpf("0")
        percent = float(var / total_var * 100) if total_var != 0 else 0.0
        summary.append({"name": name, "variance": var, "sigma": sigma, "percent": percent})
    summary.sort(key=lambda item: mp.mpf(item.get("variance", mp.mpf("0"))), reverse=True)
    return summary


def aggregate_contribution_summary(results: Sequence[object]) -> list[ContributionSummaryRow]:
    return contribution_summary_rows(aggregate_contribution_variances(results))


def render_error_contribution_plot(
    summary: Sequence[Mapping[str, object]],
    lang: str,
    *,
    title_suffix: str | None = None,
    title_en: str = "Uncertainty breakdown",
    title_zh: str = "不确定度贡献分解",
) -> bytes | None:
    if not summary:
        return None
    try:
        from shared.plotting import (
            contribution_plot_spec_from_summary,
            ErrorContributionPlotLabels,
            render_error_contribution_plot_from_spec,
        )
    except Exception:
        return None

    is_en = (lang or "").lower().startswith("en")
    labels = ErrorContributionPlotLabels(
        x_axis="Uncertainty contribution (%)" if is_en else "不确定度贡献 (%)",
        title=title_en if is_en else title_zh,
        cumulative_label="Cumulative contribution" if is_en else "累计贡献",
    )
    spec = contribution_plot_spec_from_summary(summary, labels, title_suffix=title_suffix or "")
    if spec is None:
        return None
    return render_error_contribution_plot_from_spec(spec)


def render_monte_carlo_distribution_plot(
    summary: Mapping[str, object] | None,
    lang: str,
    *,
    row_index: int | None = None,
    title_suffix: str | None = None,
    value_unit: str | None = None,
) -> bytes | None:
    if not isinstance(summary, Mapping):
        return None
    try:
        from shared.plotting import (
            MonteCarloDistributionPlotLabels,
            monte_carlo_distribution_plot_spec_from_summary,
            render_monte_carlo_distribution_plot_from_spec,
        )
    except Exception:
        return None

    is_en = (lang or "").lower().startswith("en")
    suffix = title_suffix
    if suffix is None and row_index is not None:
        suffix = f"row {row_index}" if is_en else f"行 {row_index}"
    labels = MonteCarloDistributionPlotLabels(
        title="Monte Carlo distribution" if is_en else "蒙特卡洛分布",
        x_axis=_label_with_unit("Result value" if is_en else "结果值", value_unit),
        y_axis="Sample count" if is_en else "样本数",
        mean="Mean" if is_en else "均值",
        mean_minus_std="Mean - std" if is_en else "均值 - 标准差",
        mean_plus_std="Mean + std" if is_en else "均值 + 标准差",
    )
    try:
        spec = monte_carlo_distribution_plot_spec_from_summary(summary, labels, title_suffix=suffix or "")
        if spec is None:
            return None
        return render_monte_carlo_distribution_plot_from_spec(spec)
    except Exception:
        return None


def _label_with_unit(label: str, unit: str | None) -> str:
    unit_text = str(unit or "").strip()
    return f"{label} [{unit_text}]" if unit_text else label
