from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mpmath import mp

from shared.bilingual import _dual_msg


def compute_statistics(
    values: Iterable[mp.mpf],
    sigmas: Iterable[mp.mpf | None],
    stats_mode: str,
    use_sample: bool = True,
    use_weighted_variance: bool = True,
) -> dict[str, Any]:
    values_mp = [mp.mpf(v) for v in values]
    sigmas_norm = [mp.mpf(s) if s is not None else None for s in sigmas]
    n = len(values_mp)
    if n == 0:
        raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))
    valid_values: list[mp.mpf] = list(values_mp)

    stats_mode = (stats_mode or "").strip()
    dropped = 0
    effective_n: mp.mpf | None = None
    warnings_list: list[str] = []

    sample_based = use_sample
    if stats_mode.endswith("population"):
        sample_based = False
    if stats_mode.endswith("sample"):
        sample_based = True

    if stats_mode in {"mean_sample", "mean_population", "mean"}:
        mean = mp.fsum(values_mp) / n
        if n > 1:
            denom = (n - 1) if sample_based else n
            var = mp.fsum([(v - mean) ** 2 for v in values_mp]) / denom
            std = mp.sqrt(var)
        else:
            std = mp.mpf("0")
        denom_se = max(1, n)
        std_mean = std / mp.sqrt(denom_se) if n > 1 else std
        method_label = "Arithmetic mean (sample)" if sample_based else "Arithmetic mean (population)"
    elif stats_mode in {"weighted_sigma", "weighted"}:
        zero_sigma_values: list[mp.mpf] = []
        weights: list[tuple[mp.mpf, mp.mpf]] = []
        used_values: list[mp.mpf] = []
        epsilon = mp.power(10, -max(8, mp.dps // 2))
        for value, sigma in zip(values_mp, sigmas_norm):
            if sigma is None:
                dropped += 1
                continue
            if sigma < 0:
                raise ValueError(
                    _dual_msg(
                        "检测到负的不确定度，数据无效。",
                        "Negative uncertainty encountered; data invalid.",
                    )
                )
            if mp.fabs(sigma) <= epsilon:
                zero_sigma_values.append(mp.mpf(value))
                continue
            weights.append((mp.mpf(value), mp.mpf("1") / (sigma * sigma)))
            used_values.append(mp.mpf(value))
        if zero_sigma_values:
            anchor = zero_sigma_values[0]
            if any(value != anchor for value in zero_sigma_values[1:]):
                raise ValueError(
                    _dual_msg(
                        "存在 σ=0 但数值不一致的数据点，无法计算加权平均。",
                        "Conflicting zero-uncertainty points.",
                    )
                )
            mean = anchor
            std = mp.mpf("0")
            std_mean = mp.mpf("0")
            method_label = "Weighted mean (σ=0 anchor)"
            effective_n = mp.mpf(len(zero_sigma_values))
            valid_values = zero_sigma_values + used_values
            warnings_list.append(
                _dual_msg("检测到 σ=0，按无限权重处理。", "Detected σ=0; treated as infinite weight.")
            )
            return {
                "mean": mean,
                "std_mean": std_mean,
                "std": std,
                "v_min": min(valid_values),
                "v_max": max(valid_values),
                "method_label": method_label,
                "dropped": dropped,
                "effective_n": effective_n,
                "zero_sigma_anchor": True,
                "warnings": warnings_list,
            }
        if not weights:
            raise ValueError(
                _dual_msg(
                    "未找到有效的不确定度，无法进行加权平均。",
                    "No valid uncertainties were found; cannot compute a weighted mean.",
                )
            )
        valid_values = used_values
        W = mp.fsum([weight for _, weight in weights])
        W2 = mp.fsum([weight * weight for _, weight in weights])
        if not (W > 0) or mp.isnan(W):
            warnings_list.append(
                _dual_msg(
                    "权重总和为 0（或非有限），已回退为算术平均。",
                    "Sum of weights is 0 (or non-finite); fell back to arithmetic mean.",
                )
            )
            mean = mp.fsum(valid_values) / len(valid_values)
            if len(valid_values) > 1:
                denom = (len(valid_values) - 1) if sample_based else len(valid_values)
                var = mp.fsum([(value - mean) ** 2 for value in valid_values]) / denom
                std = mp.sqrt(var)
            else:
                std = mp.mpf("0")
            std_mean = std / mp.sqrt(max(1, len(valid_values))) if len(valid_values) > 1 else std
            method_label = "Weighted mean (fallback to unweighted)"
            effective_n = mp.mpf(len(valid_values))
            return {
                "mean": mean,
                "std_mean": std_mean,
                "std": std,
                "v_min": min(valid_values) if valid_values else mp.nan,
                "v_max": max(valid_values) if valid_values else mp.nan,
                "method_label": method_label,
                "dropped": dropped,
                "effective_n": effective_n,
                "warnings": warnings_list,
            }

        mean = mp.fsum([value * weight for value, weight in weights]) / W
        centered = [(value - mean) for value, _ in weights]
        if use_weighted_variance:
            if len(weights) > 1:
                numer = mp.fsum([weight * (center * center) for (_, weight), center in zip(weights, centered)])
                if sample_based and W > 0:
                    if not (W2 > 0) or mp.isnan(W2):
                        warnings_list.append(
                            _dual_msg(
                                "无法计算加权样本有效自由度（W2<=0 或非有限），未使用样本校正。",
                                "Could not compute effective weighted degrees of freedom (W2<=0 or non-finite); sample correction disabled.",
                            )
                        )
                        dof = mp.mpf("0")
                    else:
                        dof = W - (W2 / W)
                    denom = dof if dof > 0 else W
                    if dof <= 0:
                        warnings_list.append(
                            _dual_msg(
                                "加权样本有效自由度不足（dof<=0），已回退到总体加权方差。",
                                "Effective weighted degrees of freedom is insufficient (dof<=0); fell back to population-weighted variance.",
                            )
                        )
                else:
                    denom = W
                var = numer / denom if denom != 0 else mp.mpf("0")
                std = mp.sqrt(var)
            else:
                std = mp.mpf("0")
            std_mean = mp.sqrt(mp.mpf("1") / W) if W > 0 else mp.nan
        else:
            count_w = len(weights)
            if count_w > 1:
                denom = (count_w - 1) if sample_based else count_w
                var = mp.fsum([center * center for center in centered]) / denom
                std = mp.sqrt(var)
            else:
                std = mp.mpf("0")
            denom_se = max(1, len(weights))
            std_mean = std / mp.sqrt(denom_se) if len(weights) > 0 else std
        method_label = "Weighted mean (sample)" if sample_based else "Weighted mean (population)"
        if not (W2 > 0) or mp.isnan(W2):
            warnings_list.append(
                _dual_msg(
                    "无法计算有效样本数（W2<=0 或非有限）。",
                    "Could not compute effective sample size (W2<=0 or non-finite).",
                )
            )
        elif not mp.almosteq(W2, mp.mpf("0")):
            effective_n = (W * W) / W2
    else:
        raise ValueError(_dual_msg("未知的统计模式。", "Unknown statistics mode."))

    v_min = min(valid_values) if valid_values else mp.nan
    v_max = max(valid_values) if valid_values else mp.nan

    return {
        "mean": mean,
        "std_mean": std_mean,
        "std": std,
        "v_min": v_min,
        "v_max": v_max,
        "method_label": method_label,
        "dropped": dropped,
        "effective_n": effective_n,
        "warnings": warnings_list,
    }
