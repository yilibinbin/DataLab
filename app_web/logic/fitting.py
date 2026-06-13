from __future__ import annotations

import json
from dataclasses import dataclass

import mpmath as mp

from .._security_shim import compile_latex_safe, mpmath_synchronized, validate_latex_engine

from datalab_core.fitting import build_fitting_request, fitting_payload_to_fit_result
from datalab_core.results import ResultStatus
from datalab_core.service_factory import create_core_session_service
from data_extrapolation_latex_latest import (
    _dual_msg,
    _precision_guard,
    calculate_dcolumn_format_for_column,
    format_result_with_uncertainty_latex,
    format_value_for_latex_file,
    siunitx_column_spec,
)
from datalab_latex.sisetup_block import build_sisetup_block
from fitting import (
    build_inverse_series_definition,
    build_polynomial_definition,
    render_fitting_overview,
    summarize_fit_result,
)

from .common import (
    _core_failure_message,
    _encode_b64,
    _format_number,
    _format_with_precision,
    _generate_csv_from_rows,
    _is_checked,
    _latex_to_plain,
    _merged_core_warnings,
    _norm_token,
    _parse_int,
)
from shared.fitting_uncertainty import fit_uncertainty_policy
from shared.uncertainty import parse_uncertainty_format


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
            except Exception:
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


def _normalize_fit_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "polynomial").strip()
    legacy_aliases = {
        "poly": "polynomial",
        "inverse": "inverse_power",
    }
    return legacy_aliases.get(mode, mode)


def _unsupported_fit_mode_error(mode: str) -> ValueError:
    if mode in {"auto", "preset"}:
        return ValueError(
            _dual_msg(
                "旧版自动模式已移除。请选择多项式、倒数幂、Padé、幂律极限或自定义模型。",
                "The legacy automatic mode has been removed. Choose polynomial, inverse-power, Padé, power-limit, or custom fitting.",
            )
        )
    return ValueError(
        _dual_msg(
            f"不支持的拟合模式: {mode}",
            f"Unsupported fitting mode: {mode}",
        )
    )


def _format_fit_rows(
    fit_res,
    expression: str | None,
    mp_precision: int | None = None,
    batch: int = 1,
) -> list[dict[str, object]]:
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

    # Centralized v2/v3-compatible \sisetup{...} block — see helper for
    # the ``\@ifpackagelater`` guard around v3-only ``digit-group-size``.
    lines.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=use_dcolumn,
        ).rstrip("\n")
    )

    _table_caption = caption if caption else f"Fitting Results: {latex_escape(best_label)}"

    lines.extend(
        [
            "\\usepackage{geometry}",
            "\\usepackage{graphicx}",
            "\\geometry{margin=1in}",
            "\\begin{document}",
            "\\sloppy",
            "\\section*{Fitting Results}",
            f"Model: \\texttt{{{latex_escape(best_label)}}}",
            "",
        ]
    )

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
        prepared = []
        value_cells = []
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

        lines.extend(
            [
                "\\bottomrule",
                "\\end{tabular}",
                "\\end{table}",
            ]
        )

    lines.append("\\end{document}")

    return "\n".join(lines)


@mpmath_synchronized
def _run_fit(data_text: str, form) -> FitResultBundle:
    mp_precision = _parse_int(form.get("fit_mp_precision")) or 80
    log_scale = (form.get("fit_log_scale") or "").strip().lower()
    fit_mode = _normalize_fit_mode(form.get("fit_mode"))
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

    sigma_list: list[mp.mpf | None] | None = None
    if sigma_column:
        sigma_list = _column_series(headers, rows, sigma_column)
    else:
        target_idx = headers.index(target_column)
        collected: list[mp.mpf | None] = []
        for sig_row in sigma_rows:
            entry = sig_row[target_idx] if target_idx < len(sig_row) else None
            collected.append(mp.mpf(entry) if entry is not None else None)
        if any(val is not None for val in collected):
            sigma_list = collected

    fit_weights: list[mp.mpf] | None = None
    if sigma_list:
        uncertainty_policy = fit_uncertainty_policy(sigma_list, weighted=use_weights)
        fit_weights = list(uncertainty_policy.weights) if uncertainty_policy.weights is not None else None
    elif use_weights:
        fit_uncertainty_policy([], weighted=True)
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
        model_expr = ""
        parameter_config: dict[str, dict[str, object]] | None = None
        parameter_names: list[str] | None = None
        template_expr: str | None = None
        template_params: dict[str, object] | None = None
        variable_map = {"x": x_column}

        if fit_mode == "polynomial":
            definition = build_polynomial_definition(max(1, poly_degree))
            best_label = definition.label
        elif fit_mode == "inverse_power":
            definition = build_inverse_series_definition(inv_min, inv_max)
            best_label = definition.label
        elif fit_mode == "power_limit":
            template_expr, params_cfg = _power_limit_template()
            template_params = dict(params_cfg)
            best_label = "幂律极限模型 / Power-law limit model"
        elif fit_mode == "pade":
            payload = _pade_template(pade_m, pade_n)
            if not payload:
                raise ValueError(_dual_msg("Padé 参数无效。", "Invalid Padé parameters."))
            template_expr, params_cfg = payload
            template_params = dict(params_cfg)
            best_label = f"Padé({pade_m}|{pade_n})"
        elif fit_mode == "custom":
            if not custom_expr:
                raise ValueError(
                    _dual_msg(
                        "自定义模型需要表达式。",
                        "Custom fitting requires a model expression.",
                    )
                )
            try:
                params_cfg = json.loads(custom_params_text) if str(custom_params_text).strip() else {}
                if not isinstance(params_cfg, dict):
                    raise ValueError(
                        _dual_msg(
                            "参数配置必须为 JSON 对象（key 为参数名）。",
                            "Parameter config must be a JSON object.",
                        )
                    )
                normalized_cfg: dict[str, dict[str, object]] = {}
                for name, conf in params_cfg.items():
                    if isinstance(conf, dict):
                        normalized_cfg[str(name)] = conf
                    else:
                        normalized_cfg[str(name)] = {"initial": conf}
                parameter_config = normalized_cfg
                parameter_names = list(normalized_cfg.keys())
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"自定义模型解析失败: {exc}",
                        f"Failed to parse custom model: {exc}",
                    )
                ) from exc
            model_expr = custom_expr
            variable_map = dict(var_mapping) if var_mapping else {"x": x_column}
            best_label = "自定义模型 / Custom model"
        else:
            raise _unsupported_fit_mode_error(fit_mode)

        request = build_fitting_request(
            model_type=fit_mode,
            headers=headers,
            data_rows=rows,
            variable_map=variable_map,
            target_column=target_column,
            model_expr=model_expr,
            sigma_rows=sigma_rows,
            sigma_series=sigma_list,
            parameter_config=parameter_config,
            parameter_names=parameter_names,
            template_expr=template_expr,
            template_params=template_params,
            poly_degree=max(1, poly_degree),
            inverse_min=inv_min,
            inverse_max=inv_max,
            pade_m=pade_m,
            pade_n=pade_n,
            weighted=use_weights,
            label=best_label,
            weights=fit_weights,
            precision_digits=mp_precision,
            uncertainty_digits=result_digits,
            request_id="web-fitting",
        )
        core_result = create_core_session_service().submit(request)
        if core_result.status is not ResultStatus.SUCCEEDED:
            raise ValueError(_core_failure_message(core_result.payload, "Fitting failed."))
        fit_res = fitting_payload_to_fit_result(core_result.payload["fit_result"])
        warnings.extend(_merged_core_warnings(core_result.payload, core_result.warnings))
        expression_for_csv = str(core_result.payload.get("expression") or model_expr)
        params = _collect_params(fit_res)
        metrics = _collect_metrics(fit_res)
        summary_text = summarize_fit_result(fit_res)
        plot_b64 = _render_plot(fit_res)

    csv_data = None
    if fit_res:
        fit_rows = _format_fit_rows(fit_res, expression_for_csv, mp_precision)
        if fit_rows:
            csv_headers = ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"]
            csv_data = _generate_csv_from_rows(fit_rows, headers=csv_headers)

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
