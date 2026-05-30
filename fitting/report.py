"""Text helpers for human-readable fitting summaries."""

from __future__ import annotations

from mpmath import mp

from .hp_fitter import FitResult


def _format_value(value: mp.mpf, digits: int = 6) -> str:
    # mpmath has no stubs; mp.nstr() is typed Any, so widen explicitly
    # to str to keep the public signature honest.
    return str(mp.nstr(value, n=digits))


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
    details = result.details or {}
    solver = details.get("optimizer_backend") or details.get("optimizer")
    if solver:
        lines.append(f"Solver = {solver}")
    if "scipy_safety_passed" in details:
        status = "passed" if bool(details.get("scipy_safety_passed")) else "not used"
        lines.append(f"SciPy precision check = {status}")
    if "precision" in details:
        lines.append(f"Precision = {details.get('precision')}")
    if result.residuals:
        max_abs = max((mp.fabs(value) for value in result.residuals), default=mp.mpf("0"))
        lines.append(f"Residual max |r| = {_format_value(max_abs)}")
    return "\n".join(lines)
