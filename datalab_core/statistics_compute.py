from __future__ import annotations

from collections.abc import Iterable
from math import ceil, floor
from typing import Any

from mpmath import mp

from shared.precision import normal_two_sided_critical_value, student_t_two_sided_critical_value
from shared.bilingual import _dual_msg


def compute_statistics(
    values: Iterable[mp.mpf],
    sigmas: Iterable[mp.mpf | None],
    stats_mode: str,
    use_sample: bool = True,
    use_weighted_variance: bool = True,
    confidence_level: mp.mpf | str = "0.95",
    trim_fraction: mp.mpf | str | None = None,
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
    weighted_chi_square: mp.mpf | None = None
    weighted_consistency_dof: int | None = None
    weighted_reduced_chi_square: mp.mpf | None = None
    birge_ratio: mp.mpf | None = None
    weighted_ci: dict[str, Any] = {}
    warnings_list: list[str] = []
    warning_codes: list[str] = []

    sample_based = use_sample
    if stats_mode.endswith("population"):
        sample_based = False
    if stats_mode.endswith("sample"):
        sample_based = True

    if stats_mode in {"descriptive", "descriptive_sample", "descriptive_population"}:
        parsed_trim_fraction = _parse_trim_fraction(trim_fraction)
        if any(not mp.isfinite(value) for value in values_mp):
            raise ValueError(
                _dual_msg(
                    "描述统计要求所有数值都是有限数。",
                    "Descriptive statistics requires all values to be finite.",
                )
            )
        mean = mp.fsum(values_mp) / n
        centered = [value - mean for value in values_mp]
        squared = [value * value for value in centered]
        m2 = mp.fsum(squared) / n
        variance = mp.nan
        std = mp.nan
        std_mean = mp.nan
        if sample_based:
            if n >= 2:
                variance = mp.fsum(squared) / (n - 1)
                std = mp.sqrt(variance)
                std_mean = std / mp.sqrt(n)
            else:
                warnings_list.append(
                    _dual_msg(
                        "样本描述统计需要 n>=2 才能计算方差、标准差和标准误差。",
                        "Sample descriptive statistics require n>=2 for variance, standard deviation, and standard error.",
                    )
                )
                warning_codes.append("descriptive_sample_variance_n_lt_2")
        else:
            variance = m2
            std = mp.sqrt(variance)
            std_mean = std / mp.sqrt(n)

        sorted_values = sorted(values_mp)
        trimmed_mean = None
        if parsed_trim_fraction is not None:
            trim_count = int(mp.floor(n * parsed_trim_fraction))
            if trim_count * 2 >= n:
                raise ValueError(
                    _dual_msg(
                        "trim_fraction 过大：修剪后必须至少保留 1 个数据点。",
                        "trim_fraction is too large: trimming must leave at least one data point.",
                    )
                )
            trimmed_values = sorted_values[trim_count : n - trim_count]
            trimmed_mean = mp.fsum(trimmed_values) / len(trimmed_values)
        q1 = _type7_quantile(sorted_values, mp.mpf("0.25"))
        median = _type7_quantile(sorted_values, mp.mpf("0.5"))
        q3 = _type7_quantile(sorted_values, mp.mpf("0.75"))
        iqr = q3 - q1
        deviations_from_median = sorted([mp.fabs(value - median) for value in values_mp])
        mad = _type7_quantile(deviations_from_median, mp.mpf("0.5"))

        skewness = mp.nan
        excess_kurtosis = mp.nan
        zero_variance = not (m2 > 0) or mp.isnan(m2)
        if zero_variance:
            warnings_list.append(
                _dual_msg(
                    "数据方差为 0，偏度和峰度不可用。",
                    "Zero variance; skewness and kurtosis are unavailable.",
                )
            )
            warning_codes.append("descriptive_zero_variance")
            if sample_based and n < 3:
                warnings_list.append(
                    _dual_msg(
                        "样本描述统计需要 n>=3 才能计算偏度。",
                        "Sample descriptive statistics require n>=3 for skewness.",
                    )
                )
                warning_codes.append("descriptive_sample_skewness_n_lt_3")
            if sample_based and n < 4:
                warnings_list.append(
                    _dual_msg(
                        "样本描述统计需要 n>=4 才能计算无偏峰度。",
                        "Sample descriptive statistics require n>=4 for bias-corrected excess kurtosis.",
                    )
                )
                warning_codes.append("descriptive_sample_kurtosis_n_lt_4")
        else:
            m3 = mp.fsum([center * center * center for center in centered]) / n
            m4 = mp.fsum([square * square for square in squared]) / n
            if sample_based:
                if n >= 3:
                    skewness = (mp.sqrt(n * (n - 1)) / (n - 2)) * (m3 / (m2 ** mp.mpf("1.5")))
                else:
                    warnings_list.append(
                        _dual_msg(
                            "样本描述统计需要 n>=3 才能计算偏度。",
                            "Sample descriptive statistics require n>=3 for skewness.",
                        )
                    )
                    warning_codes.append("descriptive_sample_skewness_n_lt_3")
                if n >= 4:
                    g2 = (m4 / (m2 * m2)) - 3
                    excess_kurtosis = ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * g2 + 6)
                else:
                    warnings_list.append(
                        _dual_msg(
                            "样本描述统计需要 n>=4 才能计算无偏峰度。",
                            "Sample descriptive statistics require n>=4 for bias-corrected excess kurtosis.",
                        )
                    )
                    warning_codes.append("descriptive_sample_kurtosis_n_lt_4")
            else:
                skewness = m3 / (m2 ** mp.mpf("1.5"))
                excess_kurtosis = (m4 / (m2 * m2)) - 3

        method_label = "Descriptive statistics (sample)" if sample_based else "Descriptive statistics (population)"
        result = {
            "mean": mean,
            "std_mean": std_mean,
            "std": std,
            "variance": variance,
            "v_min": min(values_mp),
            "v_max": max(values_mp),
            "median": median,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "mad": mad,
            "skewness": skewness,
            "excess_kurtosis": excess_kurtosis,
            "count": n,
            "method_label": method_label,
            "dropped": dropped,
            "effective_n": effective_n,
            "warnings": warnings_list,
            "warning_codes": warning_codes,
        }
        if trimmed_mean is not None:
            result["trimmed_mean"] = trimmed_mean
        _add_unweighted_mean_ci(
            result,
            mean=mean,
            values=values_mp,
            confidence_level=confidence_level,
            warnings_list=warnings_list,
            warning_codes=warning_codes,
        )
        return result

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
        consistency_terms: list[tuple[mp.mpf, mp.mpf]] = []
        used_values: list[mp.mpf] = []
        epsilon = mp.power(10, -max(8, mp.dps // 2))
        for value, sigma in zip(values_mp, sigmas_norm):
            if sigma is None:
                dropped += 1
                continue
            if not mp.isfinite(sigma):
                raise ValueError(
                    _dual_msg(
                        "检测到非有限不确定度，数据无效。",
                        "Non-finite uncertainty encountered; data invalid.",
                    )
                )
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
            value_mp = mp.mpf(value)
            weight = mp.mpf("1") / (sigma * sigma)
            weights.append((value_mp, weight))
            if mp.isfinite(sigma) and sigma > 0:
                consistency_terms.append((value_mp, weight))
            used_values.append(value_mp)
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
            warning_codes.append("zero_sigma_anchor")
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
                "warning_codes": warning_codes,
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
            warning_codes.append("weight_sum_invalid")
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
                "warning_codes": warning_codes,
            }

        mean = mp.fsum([value * weight for value, weight in weights]) / W
        centered = [(value - mean) for value, _ in weights]
        weighted_chi_square = mp.fsum(
            [weight * ((value - mean) ** 2) for value, weight in consistency_terms]
        )
        weighted_consistency_dof = len(consistency_terms) - 1
        if weighted_consistency_dof > 0:
            weighted_reduced_chi_square = weighted_chi_square / weighted_consistency_dof
            if weighted_reduced_chi_square >= 0 and mp.isfinite(weighted_reduced_chi_square):
                birge_ratio = mp.sqrt(weighted_reduced_chi_square)
        else:
            warnings_list.append(
                _dual_msg(
                    "加权一致性检验需要至少两个有限正 σ 数据点。",
                    "Weighted consistency diagnostics require at least two finite positive sigma values.",
                )
            )
            warning_codes.append("weighted_consistency_dof_insufficient")
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
                        warning_codes.append("weighted_dof")
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
                        warning_codes.append("weighted_dof")
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
        weighted_ci = _weighted_known_sigma_mean_ci(
            mean=mean,
            weight_sum=W,
            confidence_level=confidence_level,
        )
        if not (W2 > 0) or mp.isnan(W2):
            warnings_list.append(
                _dual_msg(
                    "无法计算有效样本数（W2<=0 或非有限）。",
                    "Could not compute effective sample size (W2<=0 or non-finite).",
                )
            )
            warning_codes.append("effective_n")
        elif not mp.almosteq(W2, mp.mpf("0")):
            effective_n = (W * W) / W2
    else:
        raise ValueError(_dual_msg("未知的统计模式。", "Unknown statistics mode."))

    v_min = min(valid_values) if valid_values else mp.nan
    v_max = max(valid_values) if valid_values else mp.nan

    result = {
        "mean": mean,
        "std_mean": std_mean,
        "std": std,
        "v_min": v_min,
        "v_max": v_max,
        "method_label": method_label,
        "dropped": dropped,
        "effective_n": effective_n,
        "weighted_chi_square": weighted_chi_square,
        "weighted_consistency_dof": weighted_consistency_dof,
        "weighted_reduced_chi_square": weighted_reduced_chi_square,
        "birge_ratio": birge_ratio,
        "warnings": warnings_list,
        "warning_codes": warning_codes,
    }
    if stats_mode in {"mean_sample", "mean_population", "mean"}:
        _add_unweighted_mean_ci(
            result,
            mean=mean,
            values=values_mp,
            confidence_level=confidence_level,
            warnings_list=warnings_list,
            warning_codes=warning_codes,
        )
    elif stats_mode in {"weighted_sigma", "weighted"}:
        result.update(weighted_ci)
    return result


def _parse_trim_fraction(value: mp.mpf | str | None) -> mp.mpf | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(_dual_msg("trim_fraction 必须是数值。", "trim_fraction must be numeric."))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            fraction = mp.mpf(text)
        except Exception as exc:  # noqa: BLE001 - user numeric text boundary.
            raise ValueError(
                _dual_msg(
                    f"trim_fraction 不是有效数字：{value!r}。",
                    f"trim_fraction is not a valid number: {value!r}.",
                )
            ) from exc
    else:
        try:
            fraction = mp.mpf(value)
        except Exception as exc:  # noqa: BLE001 - user numeric boundary.
            raise ValueError(_dual_msg("trim_fraction 必须是数值。", "trim_fraction must be numeric.")) from exc
    if fraction == 0:
        return None
    if not mp.isfinite(fraction):
        raise ValueError(_dual_msg("trim_fraction 必须是有限数。", "trim_fraction must be finite."))
    if fraction < 0:
        raise ValueError(_dual_msg("trim_fraction 不能为负数。", "trim_fraction must be non-negative."))
    return fraction


def _add_unweighted_mean_ci(
    result: dict[str, Any],
    *,
    mean: mp.mpf,
    values: list[mp.mpf],
    confidence_level: mp.mpf | str,
    warnings_list: list[str],
    warning_codes: list[str],
) -> None:
    n = len(values)
    if n < 2:
        warnings_list.append(
            _dual_msg(
                "均值置信区间需要 n>=2 才能估计样本标准误差。",
                "Mean confidence interval requires n>=2 to estimate the sample standard error.",
            )
        )
        warning_codes.append("mean_ci_n_lt_2")
        return
    centered = [value - mean for value in values]
    sample_variance = mp.fsum([value * value for value in centered]) / (n - 1)
    sample_std = mp.sqrt(sample_variance)
    se = sample_std / mp.sqrt(n)
    dof = n - 1
    critical = student_t_two_sided_critical_value(confidence_level, dof)
    margin = critical * se
    result.update(
        {
            "mean_ci_confidence_level": mp.mpf(confidence_level),
            "mean_ci_lower": mean - margin,
            "mean_ci_upper": mean + margin,
            "mean_ci_margin": margin,
            "mean_ci_method_label": "Student-t mean CI (sample standard deviation)",
            "mean_ci_critical_value": critical,
            "mean_sample_se_for_ci": se,
            "mean_ci_dof": dof,
        }
    )


def _weighted_known_sigma_mean_ci(
    *,
    mean: mp.mpf,
    weight_sum: mp.mpf,
    confidence_level: mp.mpf | str,
) -> dict[str, Any]:
    se = mp.sqrt(mp.mpf("1") / weight_sum)
    critical = normal_two_sided_critical_value(confidence_level)
    margin = critical * se
    return {
        "mean_ci_confidence_level": mp.mpf(confidence_level),
        "mean_ci_lower": mean - margin,
        "mean_ci_upper": mean + margin,
        "mean_ci_margin": margin,
        "mean_ci_method_label": "Known-sigma weighted normal CI",
        "mean_ci_critical_value": critical,
        "weighted_se_known_sigma": se,
    }


def type7_quantile(sorted_values: list[mp.mpf], p: mp.mpf) -> mp.mpf:
    if not sorted_values:
        return mp.nan
    if p <= 0:
        return sorted_values[0]
    if p >= 1:
        return sorted_values[-1]
    h = (len(sorted_values) - 1) * p
    lower = int(floor(h))
    upper = int(ceil(h))
    gamma = h - lower
    return (1 - gamma) * sorted_values[lower] + gamma * sorted_values[upper]


def _type7_quantile(sorted_values: list[mp.mpf], p: mp.mpf) -> mp.mpf:
    return type7_quantile(sorted_values, p)
