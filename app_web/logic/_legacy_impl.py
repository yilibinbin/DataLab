#!/usr/bin/env python3
"""Legacy monolithic implementation kept for compatibility.

This file is a snapshot of the historical single-file web logic that existed
before `app_web.logic` was split into submodules.

New code should **not** import from here. Prefer the compatibility facade:

  - `app_web.logic.common`
  - `app_web.logic.extrapolation`
  - `app_web.logic.error_propagation`
  - `app_web.logic.fitting`
  - `app_web.logic.statistics`
  - `app_web.logic.plots`

Planned deprecation: keep for at least one more review cycle; remove once all
downstream imports (if any) have migrated.
"""

from __future__ import annotations

import base64
import io
import math
import os
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mpmath as mp

from .._security_shim import (
    compile_latex_safe,
    mpmath_synchronized,
    validate_latex_engine,
    validate_text_size,
)

# Ensure project root is importable when the module is executed directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_extrapolation_latex_latest import (  # noqa: E402
    DEFAULT_THREE_POINT_FORMULA,
    ExtrapolationOptions,
    _dual_msg,
    apply_formula_to_data,
    calculate_dcolumn_format_for_column,
    detect_used_error_propagation_inputs,
    format_result_with_uncertainty_latex,
    format_value_for_latex_file,
    generate_error_propagation_table,
    generate_latex_table,
    parse_uncertainty_format,
    process_constants_string,
    process_data_string,
    process_uncertainty_string,
    siunitx_column_spec,
)
from data_extrapolation_latex_latest import _precision_guard  # noqa: E402
from extrapolation_methods import (  # noqa: E402
    PowerLawComputationError,
    PowerLawConfig,
    SequenceAccelerationError,
    SequenceAcceleratorConfig,
    apply_sequence_accelerator,
    extrapolate_power_law,
)
from fitting import (  # noqa: E402
    AUTO_MODELS,
    auto_fit_dataset,
    build_inverse_series_definition,
    build_model_specification,
    build_parameter_state,
    build_polynomial_definition,
    fit_custom_model,
    render_fitting_overview,
    summarize_auto_results,
    summarize_fit_result,
)
from statistics_utils import compute_statistics, generate_statistics_latex  # noqa: E402

@dataclass
class ExtrapolationResultBundle:
    headers: list[str]
    rows: list[tuple[mp.mpf, ...]]
    results: list[object]
    formatted_rows: list[dict[str, object]]
    latex_text: str
    pdf_b64: str | None
    plot_b64_list: list[str | None] | None
    csv_data: str | None
    warnings: list[str]
    method: str
    caption: str | None
    mp_precision: int | None


@dataclass
class ErrorPropagationBundle:
    headers: list[str]
    rows: list[list[object]]
    results: list[object]
    formatted_rows: list[dict[str, object]]
    latex_text: str
    pdf_b64: str | None
    plot_b64: str | None
    csv_data: str | None
    warnings: list[str]
    formula: str
    mp_precision: int | None


@dataclass
class FitResultBundle:
    headers: list[str]
    x: list[mp.mpf]
    y: list[mp.mpf]
    sigma: list[mp.mpf] | None
    best_label: str
    params: list[dict[str, object]]
    metrics: dict[str, object]
    plot_b64: str | None
    summary_text: str
    warnings: list[str]
    csv_data: str | None
    mp_precision: int | None
    latex_text: str
    pdf_b64: str | None


@dataclass
class StatsResultBundle:
    headers: list[str]
    rows: list[tuple[mp.mpf, ...]]
    sigmas: list[tuple[mp.mpf | None, ...]]
    result: dict
    latex_text: str
    pdf_b64: str | None
    plot_b64: str | None
    csv_data: str | None
    raw_csv_data: str | None
    warnings: list[str]
    stats_mode: str
    mp_precision: int | None


def _extract_data_text(form, files, allow_file: bool = True) -> str:
    """Prefer uploaded file content only when allowed; otherwise use textarea text."""
    if allow_file and "data_file" in files and files["data_file"]:
        file = files["data_file"]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, "上传文件")
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"上传文件无法读取为 UTF-8 文本: {exc}",
                        f"Uploaded file could not be decoded as UTF-8 text: {exc}",
                    )
                ) from exc
    text = (form.get("data_text") or "").strip()
    return validate_text_size(text, "数据文本")


def _extract_named_text(text_field: str, file_field: str, form, files, allow_file: bool = True) -> str:
    """Generic extractor for either textarea or file upload field."""
    if allow_file and file_field in files and files[file_field]:
        file = files[file_field]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, f"上传文件 ({file_field})")
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"上传文件无法读取为 UTF-8 文本: {exc}",
                        f"Uploaded file could not be decoded as UTF-8 text: {exc}",
                    )
                ) from exc
    text = (form.get(text_field) or "").strip()
    return validate_text_size(text, text_field)


def _parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception as exc:
        # Be tolerant to inputs like "80.0" or "1e2" coming from browsers.
        try:
            as_float = float(text)
            if as_float.is_integer():
                return int(as_float)
        except Exception:
            pass
        raise ValueError(f"无法解析整数: {text} / Failed to parse integer: {text}") from exc


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception as exc:
        raise ValueError(
            _dual_msg(
                f"无法解析浮点数: {text}",
                f"Failed to parse float: {text}",
            )
        ) from exc


def _norm_token(token: str) -> str:
    return (
        token.replace("−", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("＋", "+")
    )


def _is_checked(form, name: str, default: bool = False) -> bool:
    """
    Normalize checkbox state:

    - If the checkbox key is present, treat it as checked (unless explicitly false-ish).
    - If the key is absent in a non-empty submitted form, treat it as unchecked.
    - If the form is empty (e.g. initial GET render), fall back to default.
    """
    if form is None:
        return default
    if name in form:
        value = form.get(name)
        if value is None:
            return True
        normalized = str(value).strip().lower()
        if normalized in {"0", "false", "off", "no"}:
            return False
        return True

    # On a real submission, an unchecked checkbox is omitted from the POST body.
    # Honor that instead of "default", otherwise users cannot turn off default-on options.
    try:
        if len(form) > 0:
            return False
    except Exception:
        if bool(form):
            return False
    return default


def _format_number(value, digits: int = 10) -> str:
    try:
        return mp.nstr(value, digits)
    except Exception:
        return str(value)


def _format_with_precision(value, mp_precision: int | None = None) -> str:
    """
    Format number respecting mp.dps precision limit.

    Args:
        value: The mpf value to format
        mp_precision: The mpmath precision (dps), None means use default (16)

    Returns:
        Formatted string with precision not exceeding mp.dps
    """
    try:
        if mp_precision is None:
            mp_precision = 16  # Use default precision
        # Use mp_precision as the max significant digits
        # This ensures we don't show more digits than what mpmath can accurately represent
        result = mp.nstr(value, min(int(mp_precision), 50))  # Cap at 50 for safety
        return str(result) if result else str(value)
    except Exception:
        return str(value)


def _generate_csv_from_rows(formatted_rows: list[dict[str, object]], headers: list[str] | None = None) -> str:
    """
    Generate CSV content from formatted result rows.

    Args:
        formatted_rows: List of dicts with keys like 'index', 'value', 'uncertainty', 'latex'
        headers: Optional custom headers. If None, uses keys from first row.

    Returns:
        CSV formatted string
    """
    if not formatted_rows:
        return ""

    import csv

    output = io.StringIO()

    # Determine headers
    if headers is None:
        # Use keys from first row (maintaining order: index, value, uncertainty, latex)
        first_row = formatted_rows[0]
        if "index" in first_row and "value" in first_row and "uncertainty" in first_row and "latex" in first_row:
            headers = ["index", "value", "uncertainty", "latex"]
        else:
            headers = list(first_row.keys())

    writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
    writer.writeheader()
    writer.writerows(formatted_rows)

    return output.getvalue()


def _latex_to_plain(text: str) -> str:
    text = text.replace(r"\,", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    return text.replace("\\", "")


def _format_rows(
    headers: list[str],
    rows: Iterable[tuple[mp.mpf, ...]],
    results: Iterable,
    digits: int = 10,
    uncertainty_digits: int | None = None,
    mp_precision: int | None = None,
) -> list[dict[str, object]]:
    """
    Format extrapolation results as 3-column format.

    Returns list of dicts with keys:
    - index: row number
    - value: numerical value (limited by mp_precision)
    - uncertainty: numerical uncertainty (limited by mp_precision)
    - latex: LaTeX formatted display with uncertainty
    """
    formatted: list[dict[str, object]] = []
    for idx, (_row, result) in enumerate(zip(rows, results), 1):
        value, sigma = _split_result(result)
        latex = format_result_with_uncertainty_latex(value, sigma, uncertainty_digits)
        formatted.append(
            {
                "index": idx,
                "value": _format_with_precision(value, mp_precision),
                "uncertainty": _format_with_precision(sigma, mp_precision),
                "latex": _latex_to_plain(latex),
            }
        )
    return formatted


def _split_result(result) -> tuple[mp.mpf, mp.mpf]:
    """Normalize result objects/tuples to (value, sigma)."""
    try:
        from data_extrapolation_latex_latest import ExtrapolationResult as _Result
    except Exception:
        _Result = None  # pragma: no cover
    if _Result and isinstance(result, _Result):
        return mp.mpf(result.value), mp.mpf(result.uncertainty)
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        return mp.mpf(result[0]), mp.mpf(result[1])
    return mp.mpf(result), mp.mpf("0")


def _format_fit_rows(fit_res, expression: str | None, mp_precision: int | None = None, batch: int = 1) -> list[dict[str, object]]:
    """Build tabular rows for fitting results (parameters, metrics, covariance)."""
    rows: list[dict[str, object]] = []

    def _fmt(value) -> str:
        return _format_with_precision(value, mp_precision)

    if expression:
        rows.append(
            {
                "batch": batch,
                "section": "model",
                "name": "expression",
                "value": expression,
                "uncertainty": "",
                "stat_error": "",
                "sys_error": "",
                "note": "",
            }
        )

    params = getattr(fit_res, "params", {}) or {}
    stat_errors = getattr(fit_res, "param_errors_stat", {}) or {}
    sys_errors = getattr(fit_res, "param_errors_sys", {}) or {}
    total_errors = getattr(fit_res, "param_errors_total", {}) or getattr(fit_res, "param_errors", {}) or {}
    for name, value in params.items():
        rows.append(
            {
                "batch": batch,
                "section": "parameter",
                "name": name,
                "value": _fmt(value),
                "uncertainty": _fmt(total_errors.get(name, 0)),
                "stat_error": _fmt(stat_errors.get(name, "")) if name in stat_errors else "",
                "sys_error": _fmt(sys_errors.get(name, "")) if name in sys_errors else "",
                "note": "",
            }
        )

    metrics = [
        ("chi2", getattr(fit_res, "chi2", None)),
        ("reduced_chi2", getattr(fit_res, "reduced_chi2", None)),
        ("aic", getattr(fit_res, "aic", None)),
        ("bic", getattr(fit_res, "bic", None)),
        ("r2", getattr(fit_res, "r2", None)),
        ("rmse", getattr(fit_res, "rmse", None)),
    ]
    for name, val in metrics:
        rows.append(
            {
                "batch": batch,
                "section": "metric",
                "name": name,
                "value": _fmt(val),
                "uncertainty": "",
                "stat_error": "",
                "sys_error": "",
                "note": "",
            }
        )

    covariance = getattr(fit_res, "covariance", None)
    if covariance:
        for i, cov_row in enumerate(covariance):
            for j, cov_val in enumerate(cov_row):
                rows.append(
                    {
                        "batch": batch,
                        "section": "covariance",
                        "name": f"cov[{i + 1},{j + 1}]",
                        "value": _fmt(cov_val),
                        "uncertainty": "",
                        "stat_error": "",
                        "sys_error": "",
                        "note": "",
                    }
                )

    if getattr(fit_res, "details", {}):
        details = getattr(fit_res, "details", {})
        if details.get("weighted"):
            rows.append(
                {
                    "batch": batch,
                    "section": "note",
                    "name": "weighted",
                    "value": "True",
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        uncertainty_note = details.get("uncertainty_note")
        if uncertainty_note:
            rows.append(
                {
                    "batch": batch,
                    "section": "note",
                    "name": "uncertainty_note",
                    "value": str(uncertainty_note),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        sys_warning = details.get("systematic_warning")
        if sys_warning:
            rows.append(
                {
                    "batch": batch,
                    "section": "note",
                    "name": "systematic_warning",
                    "value": str(sys_warning),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
    return rows


def _format_statistics_rows(stats_result: dict, row_count: int, mp_precision: int | None = None) -> list[dict[str, object]]:
    """Convert statistics result dict into CSV-friendly rows."""

    def _fmt(value) -> str:
        return _format_with_precision(value, mp_precision)

    rows: list[dict[str, object]] = [
        {"metric": "method", "value": stats_result.get("method_label", ""), "uncertainty": ""},
        {
            "metric": "mean",
            "value": _fmt(stats_result.get("mean", mp.nan)),
            "uncertainty": _fmt(stats_result.get("std_mean", mp.nan)),
        },
        {"metric": "rows", "value": row_count, "uncertainty": ""},
        {"metric": "min", "value": _fmt(stats_result.get("v_min", mp.nan)), "uncertainty": ""},
        {"metric": "max", "value": _fmt(stats_result.get("v_max", mp.nan)), "uncertainty": ""},
    ]

    std_val = stats_result.get("std", mp.nan)
    try:
        if not mp.isnan(mp.mpf(std_val)):
            rows.append({"metric": "std", "value": _fmt(std_val), "uncertainty": ""})
    except Exception:
        pass
    eff_n = stats_result.get("effective_n")
    if eff_n is not None:
        rows.append({"metric": "effective_n", "value": _fmt(eff_n), "uncertainty": ""})
    dropped = stats_result.get("dropped", 0)
    if dropped:
        rows.append({"metric": "dropped", "value": dropped, "uncertainty": ""})
    return rows


def _render_latex(
    headers: list[str],
    rows: list[tuple[mp.mpf, ...]],
    results: list,
    *,
    caption: str | None,
    latex_precision: int | None,
    latex_group_size: int,
    use_dcolumn: bool,
    result_digits: int | None,
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "extrapolation.tex"
        generate_latex_table(
            headers,
            rows,
            results,
            tex_path,
            caption=caption,
            precision=latex_precision,
            verbose=False,
            use_dcolumn=use_dcolumn,
            table_segments=None,
            result_uncertainty_digits=result_digits,
            latex_group_size=latex_group_size,
        )
        return tex_path.read_text(encoding="utf-8")


# Note: _compile_latex has been replaced with compile_latex_safe from latex_security module
# The secure version includes: engine whitelist, timeout, resource limits, and -no-shell-escape


def _format_uncertain_value(uv, digits: int = 10, uncertainty_digits: int | None = None) -> str:
    """Format an UncertainValue-like object using GUI-style uncertainty notation."""
    val = getattr(uv, "value", uv)
    sigma = getattr(uv, "uncertainty", 0)
    latex = format_result_with_uncertainty_latex(val, sigma, uncertainty_digits)
    return _latex_to_plain(latex)


def _format_uncertainty_rows(
    headers: list[str],
    rows: list[list[object]],
    results: list[object],
    digits: int = 10,
    uncertainty_digits: int | None = None,
    mp_precision: int | None = None,
) -> list[dict[str, object]]:
    """
    Format error propagation results as 3-column format.

    Returns list of dicts with keys:
    - index: row number
    - value: numerical result value (limited by mp_precision)
    - uncertainty: numerical uncertainty (limited by mp_precision)
    - latex: LaTeX formatted display with uncertainty
    """
    formatted: list[dict[str, object]] = []
    for idx, (_row, res) in enumerate(zip(rows, results), 1):
        val = getattr(res, "value", res)
        sigma = getattr(res, "uncertainty", mp.mpf("0"))
        latex = format_result_with_uncertainty_latex(val, sigma, uncertainty_digits)
        formatted.append(
            {
                "index": idx,
                "value": _format_with_precision(val, mp_precision),
                "uncertainty": _format_with_precision(sigma, mp_precision),
                "latex": _latex_to_plain(latex) if latex else "",
            }
        )
    return formatted


def _render_error_latex(
    headers: list[str],
    parsed_data: list[list[object]],
    results: list[object],
    constants: dict,
    formula: str,
    *,
    caption: str | None,
    latex_precision: int | None,
    latex_group_size: int,
    use_dcolumn: bool,
    result_digits: int | None,
    used_columns: list[str] | None,
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "error.tex"
        generate_error_propagation_table(
            headers,
            parsed_data,
            results,
            constants,
            formula,
            tex_path,
            caption=caption,
            verbose=False,
            use_dcolumn=use_dcolumn,
            table_segments=None,
            precision=latex_precision,
            result_uncertainty_digits=result_digits,
            used_columns=used_columns,
            latex_group_size=latex_group_size,
        )
        return tex_path.read_text(encoding="utf-8")


def _build_power_config(form, mp_precision: int | None) -> PowerLawConfig:
    x1 = form.get("x1") or "1"
    x2 = form.get("x2") or "2"
    x3 = form.get("x3") or "3"
    exponent_override = form.get("power_exponent") or None
    initial_guess = form.get("power_seed") or None
    seed_guesses_raw = (form.get("power_seed_guesses") or "").strip()
    seed_guesses = None
    if seed_guesses_raw:
        seed_guesses = [token for token in re.split(r"[,\s]+", seed_guesses_raw) if token]
    return PowerLawConfig(
        x_values=[x1, x2, x3],
        precision=mp_precision or 80,
        exponent_override=exponent_override,
        initial_guess=initial_guess or 1.0,
        seed_guesses=seed_guesses,
    )


@mpmath_synchronized
def _run_extrapolation(data_text: str, form, lang: str = "zh") -> ExtrapolationResultBundle:
    method = (form.get("method") or "power_law").strip()
    mp_precision = _parse_int(form.get("mp_precision"))
    latex_precision = _parse_int(form.get("latex_precision"))
    latex_group_size = _parse_int(form.get("latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("result_digits"))
    if result_digits is None:
        result_digits = 1
    reference_mode = (form.get("reference_column_mode") or "").strip()
    reference_column_raw = (form.get("reference_column") or "").strip()
    reference_column = "auto_max_diff" if reference_mode.lower() == "auto_max_diff" else (reference_column_raw or None)
    caption_text = (form.get("caption") or "").strip()
    use_caption = _is_checked(form, "use_caption", default=False) if "use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    use_dcolumn = _is_checked(form, "use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "compile_pdf", default=False)
    latex_engine = (form.get("latex_engine") or "xelatex").strip() or "xelatex"
    # Dynamic (ui_specs) fields may use shorter names; keep legacy names as fallback.
    levin_variant = (form.get("variant") or form.get("levin_variant") or "u").strip() or "u"
    richardson_p = _parse_float(form.get("p"))
    if richardson_p is None:
        richardson_p = 2.0
    levin_order = _parse_int(form.get("order"))
    if levin_order is None:
        levin_order = 2
    levin_weight = (form.get("weight") or "default").strip() or "default"
    levin_beta = _parse_float(form.get("beta"))
    if levin_beta is None:
        levin_beta = 1.0
    custom_formula = (form.get("custom_formula") or "").strip() or None

    accelerators = {"richardson", "shanks", "levin_u", "wynn_epsilon"}
    if mp_precision is None and (method in accelerators or method == "power_law"):
        mp_precision = 80

    power_config = _build_power_config(form, mp_precision) if method == "power_law" else None

    options = ExtrapolationOptions(
        method=method,
        power_law_config=power_config,
        uncertainty_column=reference_column,
        mp_precision=mp_precision,
        levin_variant=levin_variant,
        custom_formula=custom_formula,
        uncertainty_digits=result_digits,
        richardson_p=richardson_p,
        levin_order=levin_order,
        levin_weight=levin_weight,
        levin_beta=levin_beta,
    )
    headers, data_rows, raw_results = process_data_string(
        data_text,
        verbose=False,
        options=options,
    )
    latex_text = _render_latex(
        headers,
        data_rows,
        raw_results,
        caption=caption,
        latex_precision=latex_precision,
        latex_group_size=latex_group_size,
        use_dcolumn=use_dcolumn,
        result_digits=result_digits,
    )
    formatted_rows = _format_rows(headers, data_rows, raw_results, digits=12, uncertainty_digits=result_digits, mp_precision=mp_precision)

    # Generate plots if requested
    generate_plots = _is_checked(form, "generate_plots", default=False)
    plot_b64_list = None
    if generate_plots and data_rows and raw_results:
        plot_b64_list = []
        for idx, (row, result) in enumerate(zip(data_rows, raw_results), 1):
            try:
                extrap_val = result.value if hasattr(result, "value") else result
                extrap_sigma = result.uncertainty if hasattr(result, "uncertainty") else mp.mpf("0")
                plot_bytes = _render_extrapolation_plot(row, extrap_val, extrap_sigma, idx, lang=lang)
                if plot_bytes:
                    plot_b64_list.append(_encode_b64(plot_bytes))
                else:
                    plot_b64_list.append(None)
            except Exception:
                plot_b64_list.append(None)

    pdf_b64 = None
    if compile_pdf:
        # Validate LaTeX engine before compilation
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, options.warnings, "extrapolation")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    # Generate CSV data
    csv_data = _generate_csv_from_rows(formatted_rows) if formatted_rows else None

    return ExtrapolationResultBundle(
        headers=headers,
        rows=data_rows,
        results=raw_results,
        formatted_rows=formatted_rows,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64_list=plot_b64_list,
        csv_data=csv_data,
        warnings=options.warnings,
        method=method,
        caption=caption,
        mp_precision=mp_precision,
    )


@mpmath_synchronized
def _run_error_propagation(data_text: str, constants_text: str, form, lang: str = "zh") -> ErrorPropagationBundle:
    mp_precision = _parse_int(form.get("error_mp_precision"))
    latex_precision = _parse_int(form.get("error_latex_precision"))
    latex_group_size = _parse_int(form.get("error_latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("error_result_digits"))
    if result_digits is None:
        result_digits = 1
    use_dcolumn = _is_checked(form, "error_use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "error_compile_pdf", default=False)
    latex_engine = (form.get("error_latex_engine") or "xelatex").strip() or "xelatex"
    constants_enabled = _is_checked(form, "error_constants_enabled", default=False)
    constants_use_file = _is_checked(form, "constants_use_file", default=False)
    caption_text = (form.get("error_caption") or "").strip()
    use_caption = _is_checked(form, "error_use_caption", default=False) if "error_use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    formula = (form.get("error_formula") or "").strip()
    propagation_method = (form.get("error_propagation_method") or "taylor").strip() or "taylor"
    propagation_order = _parse_int(form.get("error_propagation_order"))
    if propagation_order is None:
        propagation_order = 1
    mc_samples = _parse_int(form.get("error_mc_samples"))
    mc_seed = _parse_int(form.get("error_mc_seed"))

    warnings: list[str] = []
    with _precision_guard(mp_precision):
        headers, parsed_data = process_uncertainty_string(data_text, verbose=False)
        constants = {}
        if constants_enabled:
            # constants_text already empty if file not allowed/unchecked
            constants = process_constants_string(constants_text, verbose=False)
        used_headers, used_constants = detect_used_error_propagation_inputs(headers, constants, formula)
        constants_used = {name: constants[name] for name in used_constants if name in constants}
        results = apply_formula_to_data(
            headers,
            parsed_data,
            constants_used,
            formula,
            verbose=False,
            warnings=warnings,
            return_components=True,
            propagation_method=propagation_method,
            propagation_order=propagation_order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )
        latex_text = _render_error_latex(
            headers,
            parsed_data,
            results,
            constants_used,
            formula,
            caption=caption,
            latex_precision=latex_precision,
            latex_group_size=latex_group_size,
            use_dcolumn=use_dcolumn,
            result_digits=result_digits,
            used_columns=used_headers,
        )
        formatted_rows = _format_uncertainty_rows(
            headers,
            parsed_data,
            results,
            digits=12,
            uncertainty_digits=result_digits,
            mp_precision=mp_precision,
        )

    # Generate plots if requested
    generate_plots = _is_checked(form, "error_generate_plots", default=False)
    plot_b64 = None
    if generate_plots:
        plot_bytes = _render_contribution_plot(results, lang=lang)
        if plot_bytes:
            plot_b64 = _encode_b64(plot_bytes)

    pdf_b64 = None
    if compile_pdf:
        # Validate LaTeX engine before compilation
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "error")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    # Generate CSV data
    csv_data = _generate_csv_from_rows(formatted_rows) if formatted_rows else None

    return ErrorPropagationBundle(
        headers=headers,
        rows=parsed_data,
        results=results,
        formatted_rows=formatted_rows,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64=plot_b64,
        csv_data=csv_data,
        warnings=warnings,
        formula=formula,
        mp_precision=mp_precision,
    )


def _parse_fit_data(text: str):
    """
    Parse fitting data table with optional uncertainties.

    Supports formats:
    - Plain numbers: "1.0 2.1 0.05"
    - Parentheses uncertainty: "1.0 2.1(5) 0.05"
    - Mixed: "1.0 2.1(5)"

    Matches desktop GUI's _parse_generic_table behavior.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(
            _dual_msg(
                "拟合数据至少需要表头和一行数据。",
                "Fitting data requires a header and at least one data row.",
            )
        )
    headers = lines[0].split()
    if len(headers) < 1:
        raise ValueError(
            _dual_msg(
                "拟合数据表头不能为空。",
                "Fitting table header must not be empty.",
            )
        )

    def _parse_value(token: str, line_num: int) -> tuple[mp.mpf, mp.mpf | None]:
        """Parse a single value token, extracting value and optional uncertainty."""
        token = _norm_token(token)
        if "(" in token and ")" in token:
            try:
                uv = parse_uncertainty_format(token, lang="zh")
                val = mp.mpf(uv.value)
                sig = mp.mpf(uv.uncertainty) if uv.uncertainty > 0 else None
                return val, sig
            except Exception as exc:
                # If parentheses format fails, try plain number
                pass
        try:
            return mp.mpf(token), None
        except Exception as exc:
            raise ValueError(
                _dual_msg(
                    f"第 {line_num} 行无法解析数值: {token} ({exc})",
                    f"Could not parse numeric value on line {line_num}: {token} ({exc})",
                )
            ) from exc

    rows: list[tuple[mp.mpf, ...]] = []
    sigma_rows: list[tuple[mp.mpf | None, ...]] = []

    for line_num, line in enumerate(lines[1:], 2):
        parts = line.split()
        if not parts:
            continue

        # Check column count matches headers (like desktop GUI does)
        if len(parts) != len(headers):
            raise ValueError(
                _dual_msg(
                    f"第 {line_num} 行列数与表头不匹配（期望 {len(headers)} 列，实际 {len(parts)} 列）。",
                    f"Column count mismatch on line {line_num} (expected {len(headers)}, got {len(parts)}).",
                )
            )

        values: list[mp.mpf] = []
        sigmas: list[mp.mpf | None] = []

        for token in parts:
            val, sig = _parse_value(token, line_num)
            values.append(val)
            sigmas.append(sig)

        rows.append(tuple(values))
        sigma_rows.append(tuple(sigmas))

    return headers, rows, sigma_rows


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _column_series(headers: list[str], rows: list[tuple[mp.mpf, ...]], column: str) -> list[mp.mpf]:
    if not column:
        raise ValueError(_dual_msg("列名为空。", "Column name is empty."))
    if column not in headers:
        raise ValueError(_dual_msg(f"未找到列 {column}。", f"Column not found: {column}."))
    idx = headers.index(column)
    series: list[mp.mpf] = []
    for row in rows:
        if idx >= len(row):
            raise ValueError(
                _dual_msg(
                    f"列 {column} 在某些行缺失值。",
                    f"Column {column} is missing values in some rows.",
                )
            )
        series.append(mp.mpf(row[idx]))
    return series


def _power_limit_template() -> tuple[str, dict[str, dict[str, float]]]:
    return (
        "A*x**(-p) + C",
        {
            "A": {"initial": 1.0},
            "p": {"initial": 1.0, "min": 0.1},
            "C": {"initial": 0.0},
        },
    )


def _pade_template(m: int, n: int) -> tuple[str, dict[str, dict[str, float]]] | None:
    if m < 0 or n < 0:
        return None
    num_terms = []
    params: dict[str, dict[str, float]] = {}
    for power in range(m + 1):
        name = f"a{power}"
        params[name] = {"initial": 1.0 if power == 0 else 0.0}
        if power == 0:
            num_terms.append(name)
        else:
            num_terms.append(f"{name}*x**{power}")
    den_terms = ["1"]
    for power in range(1, n + 1):
        name = f"b{power}"
        params[name] = {"initial": 0.0}
        den_terms.append(f"{name}*x**{power}")
    numerator = " + ".join(num_terms) if num_terms else "a0"
    denominator = " + ".join(den_terms)
    expression = f"({numerator})/({denominator})"
    return expression, params


def _generate_fitting_latex(
    best_label: str,
    params: list[dict[str, object]],
    metrics: dict[str, object],
    use_dcolumn: bool,
    caption: str | None,
    latex_precision: int,
    latex_group_size: int = 3,
    uncertainty_digits: int | None = None,
) -> str:
    """
    Generate LaTeX document for fitting results.

    Args:
        best_label: Label for the fitted model
        params: List of parameter dicts with keys: name, value, uncertainty, latex
        metrics: Dict of fitting metrics (chi2, R2, etc.)
        use_dcolumn: Whether to use dcolumn package for alignment
        caption: Optional table caption
        latex_precision: Precision for LaTeX formatting

    Returns:
        LaTeX document as string
    """
    from statistics_utils import latex_escape

    group_size = max(0, int(latex_group_size))

    def _parse_mpf(value: object) -> mp.mpf | None:
        if value is None:
            return None
        if isinstance(value, mp.mpf):
            return value
        try:
            return mp.mpf(str(value))
        except Exception:
            return None

    def _format_dcolumn_number(value: mp.mpf) -> str:
        if value is None:
            return ""
        try:
            if mp.isnan(value):
                return "nan"
            if mp.isinf(value):
                return "-\\infty" if value < 0 else "\\infty"
        except Exception:
            pass
        if mp.almosteq(value, mp.mpf("0")):
            return "0"
        mag = mp.fabs(value)
        exp = int(mp.floor(mp.log10(mag)))
        mant = value / mp.power(10, exp)
        if mp.fabs(mant) >= 10:
            mant /= 10
            exp += 1
        mant_str = mp.nstr(mant, n=max(1, int(latex_precision)))
        if exp == 0:
            raw = mant_str
        else:
            exp_str = f"+{exp}" if exp > 0 else str(exp)
            raw = f"{mant_str}[\\text{{{exp_str}}}]"
        try:
            from data_extrapolation_latex_latest import add_spacing_to_number

            if "[" in raw:
                mantissa, rest = raw.split("[", 1)
                mant_spaced = add_spacing_to_number(mantissa, group_size=group_size).replace(" ", "\\,")
                return f"{mant_spaced}[{rest}"
            return add_spacing_to_number(raw, group_size=group_size).replace(" ", "\\,")
        except Exception:
            return raw

    lines = [
        "\\documentclass{article}",
        "\\usepackage{ifxetex}",
        "\\usepackage{ifluatex}",
        "\\ifxetex",
        "  \\usepackage{xeCJK}",
        "\\else",
        "  \\ifluatex",
        "    \\usepackage{xeCJK}",
        "  \\else",
        "    \\usepackage[utf8]{inputenc}",
        "    \\usepackage[T1]{fontenc}",
        "  \\fi",
        "\\fi",
        "\\usepackage{amsmath}",
        "\\usepackage{array}",
        "\\usepackage{booktabs}",
        "\\usepackage{threeparttable}",
    ]

    if use_dcolumn:
        lines.extend(
            [
                "\\usepackage{dcolumn}",
                "\\newcolumntype{d}[1]{D{.}{.}{#1}}",
            ]
        )
    lines.append("\\usepackage{siunitx}")

    # Configure siunitx: dcolumn never uses grouping, siunitx only if group_size > 0
    sisetup_lines = ["\\sisetup{"]

    if use_dcolumn:
        # dcolumn mode: no grouping
        sisetup_lines.extend(
            [
                "    group-digits = false,",
                "    tight-spacing = true,",
                "    uncertainty-mode = compact,",
            ]
        )
    else:
        # siunitx S-column mode: group only if group_size > 0
        if group_size > 0:
            sisetup_lines.extend(
                [
                    "    group-digits = decimal,",
                    f"    digit-group-size = {group_size},",
                    r"    group-separator = {\,},",
                    f"    group-minimum-digits = {group_size},",
                    "    tight-spacing = true,",
                    "    uncertainty-mode = compact,",
                ]
            )
        else:
            sisetup_lines.extend(
                [
                    "    group-digits = false,",
                    "    tight-spacing = true,",
                    "    uncertainty-mode = compact,",
                ]
            )

    sisetup_lines.append("}")
    lines.extend(sisetup_lines)

    table_caption = caption if caption else f"Fitting Results: {latex_escape(best_label)}"

    lines.extend([
        "\\usepackage{geometry}",
        "\\usepackage{graphicx}",
        "\\geometry{margin=1in}",
        "\\begin{document}",
        "\\sloppy",
        f"\\section*{{Fitting Results}}",
        f"Model: \\texttt{{{latex_escape(best_label)}}}",
        "",
    ])

    # Parameters table
    if params:
        prepared: list[tuple[str, str]] = []
        value_cells: list[str] = []
        for param in params:
            name = latex_escape(str(param.get("name", "")))
            parsed_value = _parse_mpf(param.get("value_raw", param.get("value")))
            parsed_unc = _parse_mpf(param.get("uncertainty_raw", param.get("uncertainty")))

            if parsed_value is None:
                formatted_value = str(param.get("latex", ""))
            else:
                formatted_value = format_value_for_latex_file(
                    parsed_value,
                    parsed_unc if (parsed_unc is not None and parsed_unc > 0) else None,
                    use_dcolumn=use_dcolumn,
                    latex_input_decimals=latex_precision,
                    is_input=False,
                    latex_group_size=group_size,
                    uncertainty_digits=uncertainty_digits,
                )

            prepared.append((name, formatted_value))
            value_cells.append(formatted_value)

        num_spec = (
            calculate_dcolumn_format_for_column(value_cells, "fit_param_values")
            if use_dcolumn
            else siunitx_column_spec(value_cells)
        )
        col_spec = f"l {num_spec}"
        lines.extend(
            [
                "\\begin{table}[!ht]",
                "\\centering",
                "\\caption{Fitted Parameters}",
                f"\\begin{{tabular}}{{{col_spec}}}",
                "\\toprule",
                "Parameter & \\multicolumn{1}{c}{value} \\\\",
                "\\midrule",
            ]
        )

        for name, formatted_value in prepared:
            lines.append(f"{name} & {formatted_value} \\\\")

        lines.extend(
            [
                "\\bottomrule",
                "\\end{tabular}",
                "\\end{table}",
                "",
            ]
        )

    # Metrics table
    if metrics:
        prepared: list[tuple[str, str]] = []
        value_cells: list[str] = []
        metric_labels = {
            "chi2": "$\\chi^2$",
            "reduced_chi2": "Reduced $\\chi^2$",
            "aic": "AIC",
            "bic": "BIC",
            "r2": "$R^2$",
            "rmse": "RMSE",
        }

        for key, label in metric_labels.items():
            if key in metrics:
                parsed = _parse_mpf(metrics[key])
                if parsed is None:
                    formatted = latex_escape(str(metrics[key]))
                else:
                    formatted = format_value_for_latex_file(
                        parsed,
                        None,
                        use_dcolumn=use_dcolumn,
                        latex_input_decimals=latex_precision,
                        is_input=True,
                        latex_group_size=group_size,
                        uncertainty_digits=uncertainty_digits,
                    )
                prepared.append((label, formatted))
                value_cells.append(formatted)

        num_spec = (
            calculate_dcolumn_format_for_column(value_cells, "fit_metric_values")
            if use_dcolumn
            else siunitx_column_spec(value_cells)
        )
        col_spec = f"l {num_spec}"
        lines.extend(
            [
                "\\begin{table}[!ht]",
                "\\centering",
                "\\caption{Goodness of Fit Metrics}",
                f"\\begin{{tabular}}{{{col_spec}}}",
                "\\toprule",
                "Metric & \\multicolumn{1}{c}{Value} \\\\",
                "\\midrule",
            ]
        )

        for label, formatted in prepared:
            lines.append(f"{label} & {formatted} \\\\")

        lines.extend([
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ])

    lines.append("\\end{document}")

    return "\n".join(lines)


@mpmath_synchronized
def _run_fit(data_text: str, form) -> FitResultBundle:
    mp_precision = _parse_int(form.get("fit_mp_precision")) or 80
    log_scale = (form.get("fit_log_scale") or "").strip().lower()
    fit_mode = (form.get("fit_mode") or "auto").strip()
    selected_model_id = form.get("fit_model_id") or None
    custom_expr = (form.get("fit_custom_expr") or "").strip()
    custom_params_text = form.get("fit_custom_params") or ""
    poly_degree = _parse_int(form.get("fit_poly_degree")) or 3
    inv_min = _parse_int(form.get("fit_inverse_min")) or 1
    inv_max = _parse_int(form.get("fit_inverse_max")) or 3
    pade_m = _parse_int(form.get("fit_pade_m")) or 1
    pade_n = _parse_int(form.get("fit_pade_n")) or 1
    use_weights = _is_checked(form, "fit_weighted", False)
    target_column = (form.get("fit_target_column") or "").strip()
    x_column = (form.get("fit_x_column") or "").strip()
    sigma_column = (form.get("fit_sigma_column") or "").strip()
    var_mapping_text = (form.get("fit_var_mapping") or "").strip()
    # LaTeX-related settings (for future use or consistency)
    result_digits = _parse_int(form.get("fit_result_digits"))
    if result_digits is None:
        result_digits = 1
    latex_precision = _parse_int(form.get("fit_latex_precision"))
    latex_group_size = _parse_int(form.get("fit_latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    caption_text = (form.get("fit_caption") or "").strip()
    use_caption = _is_checked(form, "fit_use_caption", default=False) if "fit_use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    use_dcolumn = _is_checked(form, "fit_use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "fit_compile_pdf", default=False)
    latex_engine = (form.get("fit_latex_engine") or "xelatex").strip() or "xelatex"
    generate_plots = _is_checked(form, "fit_generate_plots", default=False)

    headers, rows, sigma_rows = _parse_fit_data(data_text)
    if not x_column:
        x_column = headers[0] if headers else ""
    if not target_column:
        target_column = headers[1] if len(headers) > 1 else x_column

    x_vals = _column_series(headers, rows, x_column)
    y_vals = _column_series(headers, rows, target_column)

    # Resolve sigma series
    sigma_list: list[mp.mpf | None] | None = None
    if sigma_column:
        sigma_list = _column_series(headers, rows, sigma_column)
    else:
        # try to reuse parsed sigma rows aligned to target column
        target_idx = headers.index(target_column)
        collected: list[mp.mpf | None] = []
        for sig_row in sigma_rows:
            entry = sig_row[target_idx] if target_idx < len(sig_row) else None
            collected.append(mp.mpf(entry) if entry is not None else None)
        if any(val is not None for val in collected):
            sigma_list = collected

    sigmas_for_fit = sigma_list if (use_weights and sigma_list) else None
    var_mapping: dict[str, str] = {}
    if var_mapping_text:
        for line in var_mapping_text.splitlines():
            if ":" in line or "=" in line:
                if ":" in line:
                    name, col = line.split(":", 1)
                else:
                    name, col = line.split("=", 1)
                name = name.strip()
                col = col.strip()
                if name and col:
                    if col not in headers:
                        raise ValueError(
                            _dual_msg(
                                f"变量映射列 {col} 未找到。",
                                f"Variable mapping column not found: {col}.",
                            )
                        )
                    var_mapping[name] = col
    params: list[dict[str, object]] = []
    metrics: dict[str, object] = {}
    summary_text = ""
    warnings: list[str] = []
    best_label = ""
    fit_res = None
    plot_b64 = None
    expression_for_csv: str | None = None

    def _collect_params(fit_res):
        collected = []
        for name, value in fit_res.params.items():
            err = fit_res.param_errors_total.get(name) if fit_res.param_errors_total else None
            if err is None:
                err = fit_res.param_errors.get(name) if fit_res.param_errors else None
            val = mp.mpf(value)
            sigma = mp.mpf(err) if err is not None else mp.mpf("0")
            latex = format_result_with_uncertainty_latex(val, sigma, result_digits)
            collected.append(
                {
                    "name": name,
                    "value_raw": val,
                    "uncertainty_raw": sigma,
                    "value": _format_number(val, 10),
                    "uncertainty": _format_number(sigma, 10),
                    "latex": _latex_to_plain(latex) if latex else "",
                }
            )
        return collected

    def _collect_metrics(fit_res):
        return {
            "chi2": _format_number(fit_res.chi2, 8),
            "reduced_chi2": _format_number(fit_res.reduced_chi2, 8),
            "aic": _format_number(fit_res.aic, 8),
            "bic": _format_number(fit_res.bic, 8),
            "r2": _format_number(fit_res.r2, 8),
            "rmse": _format_number(fit_res.rmse, 8),
        }

    def _render_plot(fit_res):
        if not generate_plots:
            return None
        try:
            plot_bytes = render_fitting_overview(
                x_vals,
                y_vals,
                [("Fit", fit_res.fitted_curve)],
                [("Residuals", fit_res.residuals)],
                uncertainties=sigma_list,
                comparison=None,
                parameter_info=None,
                log_scale=log_scale if log_scale else None,
                dpi=200,
                show_curves=True,
            )
            return _encode_b64(plot_bytes)
        except Exception:
            return None

    with _precision_guard(mp_precision):
        if fit_mode == "preset" and selected_model_id:
            from fitting.auto_models import fit_linear_model

            definition = next((m for m in AUTO_MODELS if m.identifier == selected_model_id), None)
            if not definition:
                raise ValueError(_dual_msg("未找到所选模型。", "Selected model was not found."))
            fit_res = fit_linear_model(
                definition,
                x_vals,
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = definition.label
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = fit_res.details.get("expression")
        elif fit_mode == "poly":
            definition = build_polynomial_definition(max(1, poly_degree))
            from fitting.auto_models import fit_linear_model

            fit_res = fit_linear_model(
                definition,
                x_vals,
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = definition.label
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = fit_res.details.get("expression")
        elif fit_mode == "inverse":
            definition = build_inverse_series_definition(inv_min, inv_max)
            from fitting.auto_models import fit_linear_model

            fit_res = fit_linear_model(
                definition,
                x_vals,
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = definition.label
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = fit_res.details.get("expression")
        elif fit_mode in {"log_poly", "exp_combo"}:
            target_id = "M4B" if fit_mode == "log_poly" else "M7B"
            definition = next((m for m in AUTO_MODELS if m.identifier == target_id), None)
            if not definition:
                raise ValueError(_dual_msg("未找到对应模型。", "Target model was not found."))
            from fitting.auto_models import fit_linear_model

            fit_res = fit_linear_model(
                definition,
                x_vals,
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigma_list,
            )
            best_label = definition.label
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = fit_res.details.get("expression")
        elif fit_mode == "power_limit":
            expr, params_cfg = _power_limit_template()
            spec = build_model_specification(expr, ["x"], list(params_cfg.keys()))
            state = build_parameter_state(params_cfg, list(params_cfg.keys()))
            fit_res = fit_custom_model(
                spec,
                state,
                {"x": x_vals},
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = "幂律极限模型 / Power-law limit model"
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = expr
        elif fit_mode == "pade":
            payload = _pade_template(pade_m, pade_n)
            if not payload:
                raise ValueError(_dual_msg("Padé 参数无效。", "Invalid Padé parameters."))
            expr, params_cfg = payload
            spec = build_model_specification(expr, ["x"], list(params_cfg.keys()))
            state = build_parameter_state(params_cfg, list(params_cfg.keys()))
            fit_res = fit_custom_model(
                spec,
                state,
                {"x": x_vals},
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = f"Padé({pade_m}|{pade_n})"
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = expr
        elif fit_mode == "custom" and custom_expr:
            try:
                variable_names = list(var_mapping.keys()) if var_mapping else ["x"]
                import json

                params_cfg = json.loads(custom_params_text) if str(custom_params_text).strip() else {}
                if not isinstance(params_cfg, dict):
                    raise ValueError(
                        _dual_msg(
                            "参数配置必须为 JSON 对象（key 为参数名）。",
                            "Parameter config must be a JSON object.",
                        )
                    )
                # Normalize shorthand values: {"A": 1.0} -> {"A": {"initial": 1.0}}
                normalized_cfg: dict[str, dict[str, object]] = {}
                for name, conf in params_cfg.items():
                    if isinstance(conf, dict):
                        normalized_cfg[str(name)] = conf
                    else:
                        normalized_cfg[str(name)] = {"initial": conf}
                parameter_names = list(normalized_cfg.keys())
                spec = build_model_specification(custom_expr, variable_names, parameter_names)
                params_state = build_parameter_state(normalized_cfg, parameter_names)
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"自定义模型解析失败: {exc}",
                        f"Failed to parse custom model: {exc}",
                    )
                ) from exc
            data_mapping = {name: _column_series(headers, rows, col) for name, col in var_mapping.items()} if var_mapping else {"x": x_vals}
            fit_res = fit_custom_model(
                spec,
                params_state,
                data_mapping,
                y_vals,
                precision=mp_precision,
                weights=None,
                data_sigmas=sigmas_for_fit,
            )
            best_label = "自定义模型 / Custom model"
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            summary_text = summarize_fit_result(fit_res)
            plot_b64 = _render_plot(fit_res)
            expression_for_csv = custom_expr
        else:
            summary = auto_fit_dataset(
                x_vals,
                y_vals,
                precision=mp_precision,
                data_sigmas=sigmas_for_fit,
            )
            best = summary.best()
            if not best or not best.fit_result:
                raise ValueError(
                    _dual_msg(
                        "自动模型选择未获得有效结果。",
                        "Auto model selection did not produce a valid result.",
                    )
                )
            fit_res = best.fit_result
            best_label = best.label
            params = _collect_params(fit_res)
            metrics = _collect_metrics(fit_res)
            plot_b64 = _render_plot(fit_res)
            summary_text = summarize_auto_results(summary.results)
            failed = [res for res in summary.results if not res.success]
            if failed:
                n_failed = len(failed)
                warnings.append(
                    f"{n_failed} 个模型拟合失败，已在摘要中列出。 / {n_failed} model fits failed; see summary."
                )
            expression_for_csv = fit_res.details.get("expression")
    csv_data = None
    if fit_res:
        fit_rows = _format_fit_rows(fit_res, expression_for_csv, mp_precision)
        if fit_rows:
            csv_headers = ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"]
            csv_data = _generate_csv_from_rows(fit_rows, headers=csv_headers)

    # Generate LaTeX table for fitting results
    latex_text = _generate_fitting_latex(
        best_label=best_label,
        params=params,
        metrics=metrics,
        use_dcolumn=use_dcolumn,
        caption=caption,
        latex_precision=latex_precision or 10,
        latex_group_size=latex_group_size,
        uncertainty_digits=result_digits,
    )

    # Compile PDF if requested
    pdf_b64 = None
    if compile_pdf:
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "fitting")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    return FitResultBundle(
        headers=headers,
        x=x_vals,
        y=y_vals,
        sigma=sigma_list,
        best_label=best_label,
        params=params,
        metrics=metrics,
        plot_b64=plot_b64,
        summary_text=summary_text,
        warnings=warnings,
        csv_data=csv_data,
        mp_precision=mp_precision,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
    )


def _parse_stats_data(text: str):
    """
    Parse statistics data in format:
    - Single column: value (can have parentheses uncertainty like 1.23(4))
    - Two columns: value sigma

    Matches desktop GUI's _parse_generic_table behavior.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(
            _dual_msg(
                "统计数据至少需要表头和一行数据。",
                "Statistics data requires a header and at least one data row.",
            )
        )
    headers = lines[0].split()
    if len(headers) < 1:
        raise ValueError(_dual_msg("表头至少需要一列。", "Table header must contain at least one column."))

    values: list[mp.mpf] = []
    sigmas: list[mp.mpf | None] = []
    data_rows: list[tuple[mp.mpf, ...]] = []
    sigma_rows: list[tuple[mp.mpf | None, ...]] = []

    for line_num, line in enumerate(lines[1:], 2):
        parts = line.split()
        if not parts:
            continue

        # Handle different formats:
        # 1. Single column with parentheses: "1152842742.723(12)"
        # 2. Two columns: "2.1 0.05"
        # 3. Single column plain number: "2.1"

        if len(parts) == 1:
            # Single value, may have parentheses uncertainty
            token = _norm_token(parts[0])
            try:
                uv = parse_uncertainty_format(token, lang="zh")
                val = mp.mpf(uv.value)
                sigma_val = mp.mpf(uv.uncertainty) if uv.uncertainty > 0 else None
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行无法解析数字: {parts[0]} ({exc})",
                        f"Could not parse number on line {line_num}: {parts[0]} ({exc})",
                    )
                ) from exc

            values.append(val)
            sigmas.append(sigma_val)
            data_rows.append((val,))
            sigma_rows.append((sigma_val,))

        elif len(parts) >= 2:
            # Two or more columns: first is value, second is sigma
            try:
                # Try parsing first column with uncertainty format
                token1 = _norm_token(parts[0])
                try:
                    uv1 = parse_uncertainty_format(token1, lang="zh")
                    val = mp.mpf(uv1.value)
                except Exception:
                    val = mp.mpf(token1)

                # Parse second column as sigma
                token2 = _norm_token(parts[1])
                try:
                    uv2 = parse_uncertainty_format(token2, lang="zh")
                    sigma_val = mp.mpf(uv2.value)
                except Exception:
                    sigma_val = mp.mpf(token2)

            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行无法解析为数字: {line} ({exc})",
                        f"Could not parse line {line_num} as numbers: {line} ({exc})",
                    )
                ) from exc

            values.append(val)
            sigmas.append(sigma_val if sigma_val > 0 else None)
            data_rows.append((val,))
            sigma_rows.append((sigma_val if sigma_val > 0 else None,))

    return headers, values, sigmas, data_rows, sigma_rows


def _render_extrapolation_plot(
    row_values: tuple[mp.mpf, ...],
    extrap_value: mp.mpf,
    sigma: mp.mpf,
    idx: int,
    lang: str = "zh",
) -> bytes | None:
    """
    Generate extrapolation trend plot for a single row.

    Args:
        row_values: Original data values
        extrap_value: Extrapolated value
        sigma: Uncertainty
        idx: Row index (1-based)

    Returns:
        PNG bytes or None if plotting fails
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
    """
    Generate uncertainty contribution breakdown plot.

    Args:
        results: List of UncertainValue objects with contributions

    Returns:
        PNG bytes or None if plotting fails
    """
    # Collect all contributions from all results
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

    # Calculate percentages
    summary = []
    for name, variance in all_contributions.items():
        percent = float((variance / total_variance) * 100) if total_variance > 0 else 0.0
        summary.append({"name": name, "percent": percent})

    # Sort by percentage descending
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
            ax.errorbar(xs, ys, yerr=yerr, fmt="o-", color="#1f77b4", ecolor="#555555", capsize=4, label=label_data)
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


@mpmath_synchronized
def _run_statistics(data_text: str, form, lang: str = "zh") -> StatsResultBundle:
    mp_precision = _parse_int(form.get("stats_mp_precision"))
    latex_precision = _parse_int(form.get("stats_digits")) or 12
    latex_group_size = _parse_int(form.get("stats_latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("stats_uncertainty_digits"))
    if result_digits is None:
        result_digits = 1
    use_dcolumn = _is_checked(form, "stats_use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "stats_compile_pdf", default=False)
    generate_plots = _is_checked(form, "stats_generate_plots", default=False)
    latex_engine = (form.get("stats_latex_engine") or "xelatex").strip() or "xelatex"
    caption_text = (form.get("stats_caption") or "").strip()
    use_caption = _is_checked(form, "stats_use_caption", default=False) if "stats_use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    stats_mode = (form.get("stats_mode") or "mean_sample").strip()
    use_sample = _is_checked(form, "stats_use_sample", default=False)
    use_weighted_variance = _is_checked(form, "stats_use_weighted_variance", default=False)

    headers, values, sigmas, data_rows, sigma_rows = _parse_stats_data(data_text)
    warnings: list[str] = []
    with _precision_guard(mp_precision):
        stats_result = compute_statistics(values, sigmas, stats_mode, use_sample=use_sample, use_weighted_variance=use_weighted_variance)
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "stats.tex"
            generate_statistics_latex(
                headers[0] if headers else "value",
                data_rows,
                sigma_rows,
                stats_result,
                digits=latex_precision,
                tex_path=str(tex_path),
                use_dcolumn=use_dcolumn,
                uncertainty_digits=result_digits,
                caption=caption,
                latex_group_size=latex_group_size,
            )
            latex_text = tex_path.read_text(encoding="utf-8")
    mean_latex = ""
    try:
        mean_val = stats_result.get("mean")
        std_mean = stats_result.get("std_mean")
        if mean_val is not None and std_mean is not None:
            latex = format_result_with_uncertainty_latex(mean_val, std_mean, result_digits)
            mean_latex = _latex_to_plain(latex) if latex else ""
    except Exception:
        mean_latex = ""
    display_result: dict[str, object] = {}
    for key, val in stats_result.items():
        if isinstance(val, mp.mpf):
            display_result[key] = _format_number(val, 12)
        else:
            display_result[key] = val
    display_result["mean_latex"] = mean_latex
    pdf_b64 = None
    if compile_pdf:
        # Validate LaTeX engine before compilation
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "stats")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    plot_b64 = None
    if generate_plots and values:
        plot_bytes = _render_statistics_plot(values, sigmas, stats_result, lang=lang)
        if plot_bytes:
            plot_b64 = _encode_b64(plot_bytes)

    # Generate CSV data for statistics results (main) and optional raw data
    csv_data = None
    stats_rows = _format_statistics_rows(stats_result, len(values), mp_precision)
    if stats_rows:
        csv_headers = ["metric", "value", "uncertainty"]
        csv_data = _generate_csv_from_rows(stats_rows, headers=csv_headers)

    raw_csv_data = None
    if data_rows and headers:
        raw_rows = []
        has_sigma = sigmas and any(sigma_row and any(s is not None for s in sigma_row) for sigma_row in sigma_rows)

        for idx, row in enumerate(data_rows, 1):
            csv_row: dict[str, object] = {"index": idx}
            # Add data values
            for h_idx, header in enumerate(headers):
                if h_idx < len(row):
                    csv_row[header] = _format_with_precision(row[h_idx], mp_precision)
            # Add sigma values if available
            if has_sigma and idx <= len(sigma_rows):
                sigma_row = sigma_rows[idx - 1]
                for h_idx, header in enumerate(headers):
                    if sigma_row and h_idx < len(sigma_row) and sigma_row[h_idx] is not None:
                        csv_row[f"{header}_sigma"] = _format_with_precision(sigma_row[h_idx], mp_precision)
            raw_rows.append(csv_row)

        if raw_rows:
            raw_headers = ["index"] + list(headers)
            if has_sigma:
                raw_headers += [f"{h}_sigma" for h in headers]
            raw_csv_data = _generate_csv_from_rows(raw_rows, headers=raw_headers)

    if stats_result.get("dropped"):
        dropped = stats_result.get("dropped")
        warnings.append(
            f"有 {dropped} 条数据因缺少 σ 或格式被忽略。 / {dropped} data points were ignored due to missing σ or invalid format."
        )
    return StatsResultBundle(
        headers=headers,
        rows=data_rows,
        sigmas=sigma_rows,
        result=display_result,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64=plot_b64,
        csv_data=csv_data,
        raw_csv_data=raw_csv_data,
        warnings=warnings,
        stats_mode=stats_mode,
        mp_precision=mp_precision,
    )
