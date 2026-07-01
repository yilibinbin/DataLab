from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import re
from typing import Any

from mpmath import mp

from datalab_core.statistics import (
    statistics_output_uncertainty_unit,
    statistics_output_value_unit,
    statistics_row_flag_detail,
    statistics_units_have_output_annotations,
    statistics_warning_display_text,
)

from .sisetup_block import build_sisetup_block


def _normalize_input_lines(lines: list[str]) -> list[str]:
    """Strip trailing whitespace and leading blank lines."""
    trimmed = [line.rstrip() for line in lines]
    start = 0
    while start < len(trimmed) and not trimmed[start].strip():
        start += 1
    return trimmed[start:]


UNICODE_MINUS_SIGNS = {
    "\u2212",  # minus sign
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\uFF0D",  # fullwidth hyphen minus
    "\u2010",  # hyphen
    "\uFE58",  # small em dash
    "\uFE63",  # small hyphen-minus
    "\u2012",  # figure dash
}
UNICODE_PLUS_SIGNS = {
    "\uFF0B",  # fullwidth plus
    "\uFE62",  # small plus
}


def _normalize_numeric_token(token: str) -> str:
    """Replace Unicode minus/plus characters with ASCII equivalents."""
    result = token.strip()
    for ch in UNICODE_MINUS_SIGNS:
        result = result.replace(ch, "-")
    for ch in UNICODE_PLUS_SIGNS:
        result = result.replace(ch, "+")
    return result


def _string_length_hint(text: str | None) -> int:
    if not text:
        return 0
    cleaned = str(text)
    cleaned = cleaned.replace("\\,", "").replace(" ", "")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = cleaned.replace("[", "").replace("]", "")
    return max(1, len(cleaned))


def _estimate_page_geometry(column_lengths: list[int], num_rows: int) -> tuple[float, float]:
    total_chars = sum(max(length, 4) for length in column_lengths) + 6
    width = min(max(8.0, 0.6 + total_chars * 0.085), 18.0)
    base_height = 0.8 + (num_rows + 3) * 0.19
    height = min(max(9.0, base_height), 13.5)
    return width, height


_CJK_CHAR_PATTERN = re.compile(
    r"[\u3040-\u30FF\u31F0-\u31FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF66-\uFF9F\uFF00-\uFFEF]"
)


def _contains_cjk_characters(text: str | None) -> bool:
    """Return True if the text contains CJK characters."""
    if not text:
        return False
    return bool(_CJK_CHAR_PATTERN.search(str(text)))


def _needs_cjk_support(*segments: str) -> bool:
    """Check a collection of text fragments for any CJK characters."""
    for segment in segments:
        if _contains_cjk_characters(segment):
            return True
    return False


def _build_standalone_preamble(
    width_in: float,
    *,
    include_dcolumn: bool = False,
    needs_cjk: bool = False,
    latex_group_size: int = 3,
) -> list[str]:
    """Return a minimal standalone LaTeX preamble tuned for fast compilation.

    Args:
        latex_group_size: Group size for grouping digits (0 = no grouping)
    """
    group_size = max(0, int(latex_group_size))
    doc_class = "\\documentclass[varwidth={0:.2f}in,border=12pt]{{standalone}}".format(width_in)
    preamble = [doc_class]
    if needs_cjk:
        preamble.extend(
            [
                "\\usepackage{fontspec}",
                "\\usepackage{xeCJK}",
            ]
        )
    else:
        preamble.append("\\usepackage[utf8]{inputenc}")

    preamble.extend(
        [
            "\\usepackage{amsmath}",
            "\\usepackage{array}",
            "\\usepackage{booktabs}",
            "\\usepackage{threeparttable}",
        ]
    )

    if include_dcolumn:
        preamble.append("\\usepackage{dcolumn}")
    preamble.append("\\usepackage{siunitx}")

    preamble.append("")

    if include_dcolumn:
        preamble.extend(
            [
                "% Configure dcolumn for decimal point alignment",
                "\\newcolumntype{d}[1]{D{.}{.}{#1}}",
                "",
            ]
        )

    # Centralized v2/v3-compatible \sisetup{...} body. The helper emits
    # a guard around the siunitx-v3-only ``digit-group-size`` key so
    # documents still compile against older TeX Live distributions where
    # siunitx v2 is the default. (Was 5 near-duplicate inline copies
    # before — removing them all keeps the format drift-free.)
    preamble.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=include_dcolumn,
        ).rstrip("\n")
    )
    preamble.append("")

    preamble.extend(
        [
            "\\begin{document}",
            "",
            "\\centering",
        ]
    )

    return preamble


def _normalize_table_segments(total_rows: int, table_segments: list[tuple[int, int]] | None) -> list[tuple[int, int]]:
    if total_rows <= 0:
        return []
    if not table_segments:
        return [(0, total_rows)]
    normalized: list[tuple[int, int]] = []
    last_end = 0
    ordered = sorted(table_segments, key=lambda pair: pair[0])
    for start, end in ordered:
        start = max(0, min(start, total_rows))
        end = max(start, min(end, total_rows))
        if start != last_end or end <= start:
            return [(0, total_rows)]
        normalized.append((start, end))
        last_end = end
    if normalized[-1][1] != total_rows:
        return [(0, total_rows)]
    return normalized


def _normalize_header_to_symbol(header: str, index: int) -> str:
    """Convert a column header to a safe Python identifier, ensuring uniqueness."""
    base = re.sub(r"[^0-9A-Za-z_]", "_", header.strip()) or f"col_{index+1}"
    if base[0].isdigit():
        base = f"c_{base}"
    base = base.strip("_") or f"col_{index+1}"
    return base


def _apply_aliases(formula: str, alias_map: dict[str, str]) -> str:
    """Replace alias tokens (e.g., x1) with canonical variable names."""
    result = formula
    # replace longer aliases first to avoid partial overlaps
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        target = alias_map[alias]
        pattern = r"\b" + re.escape(alias) + r"\b"
        result = re.sub(pattern, target, result)
    return result


StatisticsLatexValueFormatter = Callable[[Any, Any | None, bool], str]
StatisticsLatexTextFormatter = Callable[[str], str]


def format_statistics_latex_value(
    value: Any,
    sigma: Any | None,
    *,
    digits: int,
    use_dcolumn: bool,
    uncertainty_digits: int | None = None,
    is_input: bool = True,
    latex_group_size: int = 3,
) -> str:
    """Format a statistics numeric cell through the canonical LaTeX formatter."""

    from datalab_latex.latex_formatting import format_value_for_latex_file

    sigma_digits = uncertainty_digits
    if sigma is not None and hasattr(sigma, "uncertainty_digits"):
        sigma_digits = getattr(sigma, "uncertainty_digits", None) or sigma_digits
    if sigma is not None and hasattr(sigma, "uncertainty"):
        try:
            sigma = sigma.uncertainty
        except Exception:
            pass
    if sigma is not None:
        try:
            sigma = mp.mpf(sigma)
        except Exception:
            sigma = None
    return str(
        format_value_for_latex_file(
            value,
            sigma,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=digits,
            is_input=is_input,
            latex_group_size=max(0, int(latex_group_size)),
            uncertainty_digits=sigma_digits,
        )
    )


def latex_numeric_values_from_rows(rows: Sequence[tuple[str, str]]) -> list[str]:
    """Return cells usable for dcolumn/siunitx table-format estimation."""

    values = [value for _label, value in rows if not value.lstrip().startswith("\\multicolumn")]
    return values or [value for _label, value in rows]


STATISTICS_LATEX_SUMMARY_LABEL_KEYS = {
    "Mean": "mean",
    "Trimmed mean": "trimmed_mean",
    "Std. error": "std_mean",
    "Mean CI lower": "mean_ci_lower",
    "Mean CI upper": "mean_ci_upper",
    "Mean CI margin": "mean_ci_margin",
    "CI level": "mean_ci_confidence_level",
    "Sample SE for CI": "mean_sample_se_for_ci",
    "Known-sigma weighted SE": "weighted_se_known_sigma",
    "CI dof": "mean_ci_dof",
    "CI critical value": "mean_ci_critical_value",
    "Min": "min",
    "Max": "max",
    "Std. dev.": "std",
    "Count": "count",
    "Variance": "variance",
    "Median": "median",
    "Q1": "q1",
    "Q3": "q3",
    "IQR": "iqr",
    "MAD": "mad",
    "Skewness": "skewness",
    "Excess kurtosis": "excess_kurtosis",
    "Weighted chi-square": "weighted_chi_square",
    "Weighted consistency dof": "weighted_consistency_dof",
    "Weighted reduced chi-square": "weighted_reduced_chi_square",
    "Birge ratio": "birge_ratio",
}


def statistics_latex_output_unit_for_keys(units: Mapping[str, Any] | None, *keys: object) -> str:
    for key in keys:
        text = str(key or "").strip()
        if not text:
            continue
        unit = statistics_output_value_unit(units, text)
        if unit:
            return unit
    return ""


def statistics_latex_summary_unit_for_label(units: Mapping[str, Any] | None, label: str) -> str:
    key = STATISTICS_LATEX_SUMMARY_LABEL_KEYS.get(label)
    if not key:
        return ""
    value_unit = statistics_output_value_unit(units, key)
    uncertainty_unit = statistics_output_uncertainty_unit(units, key)
    if value_unit and uncertainty_unit and value_unit != uncertainty_unit:
        return f"{value_unit}; uncertainty {uncertainty_unit}"
    return value_unit or uncertainty_unit


def statistics_latex_summary_units_for_rows(
    units: Mapping[str, Any] | None,
    summary_rows: Sequence[tuple[str, str]],
) -> dict[str, str]:
    if not statistics_units_have_output_annotations(units):
        return {}
    result: dict[str, str] = {}
    for label, _value in summary_rows:
        unit = statistics_latex_summary_unit_for_label(units, label)
        if unit:
            result[label] = unit
    return result


def build_statistics_latex_summary_rows(
    result: Mapping[str, Any],
    *,
    format_value: StatisticsLatexValueFormatter,
    format_text: StatisticsLatexTextFormatter | None = None,
) -> list[tuple[str, str]]:
    """Build the shared non-UI statistics summary rows for LaTeX tables."""

    rows: list[tuple[str, str]] = []
    if _statistics_latex_has_finite_value(result, "mean"):
        rows.append(
            (
                "Mean",
                format_value(result["mean"], _statistics_latex_finite_or_none(result.get("std_mean")), False),
            )
        )
    if _statistics_latex_has_finite_value(result, "trimmed_mean"):
        rows.append(("Trimmed mean", format_value(result["trimmed_mean"], None, True)))
    if _statistics_latex_has_finite_value(result, "std_mean"):
        rows.append(
            (
                "Std. error",
                format_value(result["std_mean"], None, True),
            )
        )
    for label, key in (
        ("Mean CI lower", "mean_ci_lower"),
        ("Mean CI upper", "mean_ci_upper"),
        ("Mean CI margin", "mean_ci_margin"),
        ("CI level", "mean_ci_confidence_level"),
        ("Sample SE for CI", "mean_sample_se_for_ci"),
        ("Known-sigma weighted SE", "weighted_se_known_sigma"),
        ("CI dof", "mean_ci_dof"),
        ("CI critical value", "mean_ci_critical_value"),
    ):
        if _statistics_latex_has_finite_value(result, key):
            rows.append((label, format_value(result[key], None, True)))
    ci_method = str(result.get("mean_ci_method_label") or "").strip()
    if ci_method:
        text_formatter = format_text or (lambda text: text)
        rows.append(("CI method", _statistics_latex_text_cell(ci_method, format_text=text_formatter)))
    min_key = "v_min" if "v_min" in result else "min"
    max_key = "v_max" if "v_max" in result else "max"
    if _statistics_latex_has_finite_value(result, min_key):
        rows.append(("Min", format_value(result[min_key], None, True)))
    if _statistics_latex_has_finite_value(result, max_key):
        rows.append(("Max", format_value(result[max_key], None, True)))
    if _statistics_latex_has_std(result):
        rows.append(
            (
                "Std. dev.",
                format_value(result["std"], None, True),
            )
        )
    for label, key in (
        ("Count", "count"),
        ("Variance", "variance"),
        ("Median", "median"),
        ("Q1", "q1"),
        ("Q3", "q3"),
        ("IQR", "iqr"),
        ("MAD", "mad"),
        ("Skewness", "skewness"),
        ("Excess kurtosis", "excess_kurtosis"),
        ("Weighted chi-square", "weighted_chi_square"),
        ("Weighted consistency dof", "weighted_consistency_dof"),
        ("Weighted reduced chi-square", "weighted_reduced_chi_square"),
        ("Birge ratio", "birge_ratio"),
    ):
        if _statistics_latex_has_finite_value(result, key):
            rows.append((label, format_value(result[key], None, True)))
    rows.extend(
        build_statistics_latex_diagnostic_rows(
            result,
            format_text=format_text,
        )
    )
    return rows


def build_statistics_latex_diagnostic_rows(
    result: Mapping[str, Any],
    *,
    format_text: StatisticsLatexTextFormatter | None = None,
) -> list[tuple[str, str]]:
    """Build current statistics warning/diagnostic rows for LaTeX summaries."""

    text_formatter = format_text or (lambda text: text)
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    analysis_rows = result.get("analysis_rows")
    if isinstance(analysis_rows, Sequence) and not isinstance(analysis_rows, (str, bytes, bytearray)):
        for row in analysis_rows:
            if not isinstance(row, Mapping):
                continue
            if row.get("render_group") == "plot_annotation":
                continue
            severity = str(row.get("severity") or "")
            key = str(row.get("key") or "")
            if row.get("render_group") == "row_flag" and key.startswith("outlier."):
                message = f"value {row.get('value')}; {statistics_row_flag_detail(row)}"
                if message in seen:
                    continue
                seen.add(message)
                rows.append(("Outlier flag", _statistics_latex_text_cell(message, format_text=text_formatter)))
                continue
            if severity != "warning" and not key.startswith("warning."):
                continue
            message = statistics_warning_display_text(row.get("value"), fallback=row.get("message_key") or key)
            if not message or message in seen:
                continue
            seen.add(message)
            rows.append(("Warning", _statistics_latex_text_cell(message, format_text=text_formatter)))
        if rows:
            return rows

    warning_codes = result.get("warning_codes")
    if isinstance(warning_codes, Sequence) and not isinstance(warning_codes, (str, bytes, bytearray)):
        for code in warning_codes:
            message = statistics_warning_display_text(code)
            if message in seen:
                continue
            seen.add(message)
            rows.append(("Warning", _statistics_latex_text_cell(message, format_text=text_formatter)))
    if rows:
        return rows

    warnings = result.get("warnings")
    if isinstance(warnings, Sequence) and not isinstance(warnings, (str, bytes, bytearray)):
        for warning in warnings:
            message = statistics_warning_display_text(warning)
            if not message or message in seen:
                continue
            seen.add(message)
            rows.append(("Warning", _statistics_latex_text_cell(message, format_text=text_formatter)))
    return rows


def _statistics_latex_text_cell(
    text: str,
    *,
    format_text: StatisticsLatexTextFormatter,
) -> str:
    return f"\\multicolumn{{1}}{{l}}{{{format_text(text)}}}"


def _statistics_latex_has_std(result: Mapping[str, Any]) -> bool:
    return _statistics_latex_has_finite_value(result, "std")


def _statistics_latex_has_finite_value(result: Mapping[str, Any], key: str) -> bool:
    if result.get(key) is None:
        return False
    try:
        value = mp.mpf(result.get(key, mp.nan))
        return not (mp.isnan(value) or mp.isinf(value))
    except Exception:
        return True


def _statistics_latex_finite_or_none(value: Any) -> Any | None:
    try:
        numeric = mp.mpf(value)
    except Exception:
        return value
    if mp.isnan(numeric) or mp.isinf(numeric):
        return None
    return value
