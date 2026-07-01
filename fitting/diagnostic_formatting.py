"""UI-neutral formatting helpers for fitting diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mpmath import mp

from .diagnostics import fit_diagnostic_warnings, fit_diagnostics
from .hp_fitter import FitResult

FormatValue = Callable[[object], str]
EscapeText = Callable[[str], str]
UNAVAILABLE_LATEX_CELL = r"\multicolumn{1}{c}{Unavailable}"


@dataclass(frozen=True)
class FittingDiagnosticMetric:
    key: str
    label: str
    value: mp.mpf
    note: str = ""


@dataclass(frozen=True)
class FittingDiagnosticCorrelation:
    left: str
    right: str
    value: mp.mpf


@dataclass(frozen=True)
class FittingDiagnosticResidual:
    index: int
    value: mp.mpf
    label: str
    method: str


@dataclass(frozen=True)
class FittingDiagnosticView:
    metrics: tuple[FittingDiagnosticMetric, ...]
    correlations: tuple[FittingDiagnosticCorrelation, ...]
    residuals: tuple[FittingDiagnosticResidual, ...]
    warnings: tuple[str, ...]


def fitting_diagnostic_view(fit_result: FitResult) -> FittingDiagnosticView:
    diagnostics = fit_diagnostics(fit_result)
    metrics: list[FittingDiagnosticMetric] = []
    p_value = diagnostics.get("chi_square_p_value")
    if p_value is not None:
        metrics.append(
            FittingDiagnosticMetric(
                key="chi_square_p_value",
                label="χ² p-value",
                value=_mp_or_nan(p_value),
            )
        )

    residual_info = diagnostics.get("residuals")
    residual_rows: list[FittingDiagnosticResidual] = []
    if isinstance(residual_info, dict):
        residual_label = str(residual_info.get("label") or "Standardized residual")
        residual_method = str(residual_info.get("method") or "")
        max_abs = residual_info.get("max_abs")
        if max_abs is not None:
            metrics.append(
                FittingDiagnosticMetric(
                    key="max_standardized_residual",
                    label="Max standardized residual",
                    value=_mp_or_nan(max_abs),
                    note=residual_label,
                )
            )
        for idx, value in enumerate(residual_info.get("values", []) or [], start=1):
            residual_rows.append(
                FittingDiagnosticResidual(
                    index=idx,
                    value=_mp_or_nan(value),
                    label=residual_label,
                    method=residual_method,
                )
            )

    correlations: list[FittingDiagnosticCorrelation] = []
    correlation = diagnostics.get("parameter_correlation")
    if isinstance(correlation, dict):
        names = [str(name) for name in correlation.get("parameters", [])]
        for i, corr_row in enumerate(correlation.get("matrix", []) or []):
            for j, corr_val in enumerate(corr_row):
                left = names[i] if i < len(names) else str(i + 1)
                right = names[j] if j < len(names) else str(j + 1)
                correlations.append(
                    FittingDiagnosticCorrelation(
                        left=left,
                        right=right,
                        value=_mp_or_nan(corr_val),
                    )
                )

    return FittingDiagnosticView(
        metrics=tuple(metrics),
        correlations=tuple(correlations),
        residuals=tuple(residual_rows),
        warnings=fit_diagnostic_warnings(fit_result),
    )


def build_fitting_diagnostic_csv_rows(
    fit_result: FitResult,
    *,
    batch: int,
    format_value: FormatValue,
) -> list[dict[str, object]]:
    view = fitting_diagnostic_view(fit_result)
    rows: list[dict[str, object]] = []
    for metric in view.metrics:
        rows.append(_csv_row(batch, "metric", metric.key, format_value(metric.value), note=metric.note))
    for residual in view.residuals:
        rows.append(
            _csv_row(
                batch,
                "residual_diagnostic",
                f"standardized_residual[{residual.index}]",
                format_value(residual.value),
                note=residual.label,
            )
        )
    for correlation in view.correlations:
        rows.append(
            _csv_row(
                batch,
                "correlation",
                f"corr[{correlation.left},{correlation.right}]",
                format_value(correlation.value),
            )
        )
    for warning in view.warnings:
        rows.append(_csv_row(batch, "note", "diagnostic_warning", warning))
    return rows


def build_fitting_diagnostic_latex_entries(
    fit_result: FitResult,
    *,
    format_value: FormatValue,
    escape_text: EscapeText | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    escape = escape_text or (lambda value: value)
    view = fitting_diagnostic_view(fit_result)
    entries: list[tuple[str, str]] = []
    for metric in view.metrics:
        entries.append((_latex_metric_label(metric), safe_latex_diagnostic_value(metric.value, format_value)))
    for correlation in view.correlations:
        entries.append(
            (
                f"Corr {escape(correlation.left)},{escape(correlation.right)}",
                safe_latex_diagnostic_value(correlation.value, format_value),
            )
        )
    for residual in view.residuals:
        entries.append(
            (
                f"{escape(residual.label)} {residual.index}",
                safe_latex_diagnostic_value(residual.value, format_value),
            )
        )
    warnings = [escape(warning) for warning in view.warnings]
    return entries, warnings


def _latex_metric_label(metric: FittingDiagnosticMetric) -> str:
    if metric.key == "chi_square_p_value":
        return "$\\chi^2$ p-value"
    return metric.label


def safe_latex_diagnostic_value(value: object, format_value: FormatValue) -> str:
    """Format finite diagnostics numerically and non-finite diagnostics as text."""

    numeric = _mp_or_nan(value)
    if not mp.isfinite(numeric):
        return UNAVAILABLE_LATEX_CELL
    return format_value(numeric)


def _csv_row(
    batch: int,
    section: str,
    name: str,
    value: object,
    *,
    note: str = "",
) -> dict[str, object]:
    return {
        "batch": batch,
        "section": section,
        "name": name,
        "value": value,
        "uncertainty": "",
        "stat_error": "",
        "sys_error": "",
        "note": note,
    }


def _mp_or_nan(value: object) -> mp.mpf:
    try:
        return mp.mpf(value)
    except Exception:
        return mp.nan
