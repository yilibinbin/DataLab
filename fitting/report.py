"""Text helpers for human-readable fitting summaries."""

from __future__ import annotations

from typing import Iterable

from mpmath import mp

from .hp_fitter import FitResult
from .model_selector import AutoModelResult


def _format_value(value: mp.mpf, digits: int = 6) -> str:
    return mp.nstr(value, n=digits)


def summarize_fit_result(result: FitResult) -> str:
    lines = ["=== 拟合结果 / Fit Results ==="]
    for name, value in result.params.items():
        stat = result.param_errors_stat.get(name) if result.param_errors_stat else None
        sys = result.param_errors_sys.get(name) if result.param_errors_sys else None
        total = result.param_errors_total.get(name) if result.param_errors_total else None
        stat = stat if stat is not None else result.param_errors.get(name, mp.mpf("0"))
        sys = sys if sys is not None else mp.mpf("0")
        total = total if total is not None else result.param_errors.get(name, stat)
        entry = f"{name} = {_format_value(value)} ± {_format_value(total)}"
        if sys and not mp.almosteq(sys, mp.mpf("0")):
            entry += f" (stat {_format_value(stat)}, sys {_format_value(sys)})"
        lines.append(entry)
    lines.extend(
        [
            f"χ² = {_format_value(result.chi2)}",
            f"Reduced χ² = {_format_value(result.reduced_chi2)}",
            f"AIC = {_format_value(result.aic)}",
            f"BIC = {_format_value(result.bic)}",
            f"R² = {_format_value(result.r2)}",
            f"RMSE = {_format_value(result.rmse)}",
        ]
    )
    return "\n".join(lines)


def summarize_auto_results(results: Iterable[AutoModelResult]) -> str:
    lines = ["=== 自动模型评估 / Auto Model Summary ==="]
    for result in results:
        if not result.success or not result.fit_result:
            lines.append(f"{result.label}: 失败 / Failed ({result.error})")
            continue
        lines.append(
            f"{result.label}: AIC={_format_value(result.fit_result.aic)} | "
            f"χ²={_format_value(result.fit_result.chi2)}"
        )
    return "\n".join(lines)
