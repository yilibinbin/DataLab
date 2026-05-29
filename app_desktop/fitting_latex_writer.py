"""Qt-free LaTeX generator for fitting reports/tables.

This module builds LaTeX output without importing Qt, so it can be unit-tested and reused from both GUI and tests.
"""

from __future__ import annotations

from pathlib import Path

import mpmath as mp

from data_extrapolation_latex_latest import (
    calculate_dcolumn_format_for_column,
    format_value_for_latex_file,
    siunitx_column_spec,
)
from datalab_latex.sisetup_block import build_sisetup_block
from fitting.hp_fitter import FitResult


def latex_escape(text: str) -> str:
    mapping = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
        "\\": "\\textbackslash{}",
    }
    return "".join(mapping.get(ch, ch) for ch in str(text))


def _latex_escape_text(value: str) -> str:
    return latex_escape(value)


def build_fit_latex_preamble(*, use_dcolumn: bool, digits: int, latex_group_size: int) -> list[str]:
    group_size = max(1, int(latex_group_size))
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
        "\\usepackage{booktabs}",
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
    lines.extend(
        [
            "\\usepackage{geometry}",
            "\\usepackage{graphicx}",
            "\\geometry{margin=1in}",
            "\\begin{document}",
            "\\sloppy",
            "\\section*{Fitting Report}",
        ]
    )
    return lines


def build_fit_latex_block(
    *,
    headers: list[str],
    rows: list[tuple[mp.mpf, ...]],
    sigma_rows: list[tuple[object | None, ...]],
    fit_result: FitResult,
    expression: str,
    substituted: str,
    image_path: Path | None,
    use_dcolumn: bool,
    digits: int,
    latex_group_size: int = 3,
    batch_index: int | None = None,
    target_column: str = "",
    variable_pairs: list[tuple[str, str]] | None = None,
    caption_text: str | None = None,
    default_uncertainty_digits: int | None = None,
    cleaned_substituted: str | None = None,
) -> list[str]:
    default_unc_digits = default_uncertainty_digits
    variable_pairs = variable_pairs or []
    target_column = (target_column or "").strip()

    def _format_cell_value(val: mp.mpf, sigma_obj, *, is_input: bool) -> str:
        sigma_digits = None if is_input else default_unc_digits
        sigma = sigma_obj
        if sigma_obj is not None and hasattr(sigma_obj, "uncertainty_digits"):
            sigma_digits = getattr(sigma_obj, "uncertainty_digits", None) or sigma_digits
        if sigma_obj is not None and hasattr(sigma_obj, "uncertainty"):
            try:
                sigma = sigma_obj.uncertainty
            except Exception:
                sigma = sigma_obj
        if sigma is not None:
            try:
                sigma = mp.mpf(sigma)
            except Exception:
                sigma = None
        return format_value_for_latex_file(
            mp.mpf(val),
            sigma,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=digits,
            is_input=is_input,
            latex_group_size=latex_group_size,
            uncertainty_digits=sigma_digits,
        )

    def _format_key(key: str) -> str:
        if "\\" in key or "$" in key or "^" in key:
            return key
        return latex_escape(key)

    target_idx = headers.index(target_column) if target_column in headers else 0
    index_lookup = {name: headers.index(name) for name in headers}
    x_idx = index_lookup.get(variable_pairs[0][1], 0) if variable_pairs else 0

    table_rows: list[tuple[str, str]] = []
    for idx, row in enumerate(rows):
        sigma_obj = None
        if sigma_rows and idx < len(sigma_rows) and target_idx < len(sigma_rows[idx]):
            sigma_obj = sigma_rows[idx][target_idx]
        val_text = _format_cell_value(row[target_idx], sigma_obj, is_input=True)
        if variable_pairs:
            parts = []
            for var, col in variable_pairs:
                col_idx = index_lookup.get(col)
                if col_idx is None or col_idx >= len(row):
                    continue
                # Try to show x uncertainties with their own digits
                x_sigma = None
                if sigma_rows and idx < len(sigma_rows) and col_idx < len(sigma_rows[idx]):
                    x_sigma = sigma_rows[idx][col_idx]
                x_unc_val = None
                if x_sigma is not None:
                    try:
                        x_unc_val = mp.mpf(getattr(x_sigma, "uncertainty", x_sigma))
                    except Exception:
                        x_unc_val = None
                if x_unc_val is not None and not mp.almosteq(x_unc_val, mp.mpf("0")):
                    x_val_text = _format_cell_value(row[col_idx], x_sigma, is_input=True)
                else:
                    x_val_text = mp.nstr(row[col_idx], digits)
                parts.append(f"{var}={x_val_text}")
            coord = ", ".join(parts) if parts else f"x={mp.nstr(row[x_idx], digits)}"
            label = f"({coord})"
        else:
            label = f"Input x={mp.nstr(row[x_idx], digits)}"
        table_rows.append((label, val_text))

    for name, value in fit_result.params.items():
        total_err = (fit_result.param_errors_total or fit_result.param_errors).get(name, mp.mpf("0"))
        val_text = _format_cell_value(value, total_err, is_input=False)
        table_rows.append((f"Param {name}", val_text))
        sys_err = (fit_result.param_errors_sys or {}).get(name)
        if sys_err and not mp.almosteq(sys_err, mp.mpf("0")):
            stat_err = (fit_result.param_errors_stat or {}).get(name, total_err)
            stat_text = _format_cell_value(stat_err, None, is_input=False)
            sys_text = _format_cell_value(sys_err, None, is_input=False)
            # Split stat and sys errors into two separate rows
            table_rows.append((f"{name} stat", stat_text))
            table_rows.append((f"{name} sys", sys_text))

    metrics = [
        ("$\\chi^2$", fit_result.chi2),
        ("Reduced $\\chi^2$", fit_result.reduced_chi2),
        ("AIC", fit_result.aic),
        ("BIC", fit_result.bic),
        ("$R^2$", fit_result.r2),
        ("RMSE", fit_result.rmse),
    ]
    for label, value in metrics:
        val_text = format_value_for_latex_file(
            mp.mpf(value),
            None,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=digits,
            is_input=True,
            latex_group_size=latex_group_size,
        )
        table_rows.append((label, val_text))

    lines: list[str] = []
    if batch_index is not None:
        # Always use English for LaTeX output
        lines.append(f"\\subsection*{{Fit Results: Batch {batch_index}}}")

    implicit_equation = str(fit_result.details.get("equation") or "").strip()
    implicit_output = str(fit_result.details.get("output_expression") or "").strip()
    if implicit_equation:
        lines.append(f"Implicit equation: \\texttt{{{_latex_escape_text(implicit_equation)}}}\\\\")
    if implicit_output:
        lines.append(f"Implicit output: \\texttt{{{_latex_escape_text(implicit_output)}}}\\\\")

    cleaned_expr = (expression or "").strip().replace("**", "^")
    cleaned_sub = cleaned_substituted
    if cleaned_sub is None:
        cleaned_sub = (substituted or "").strip().replace("**", "^")

    if cleaned_expr:
        lines.append(f"Model: $ {cleaned_expr} $\\\\")
    if cleaned_sub:
        lines.append(f"With params: $ {cleaned_sub} $")

    solver_details: list[str] = []
    optimizer_backend = fit_result.details.get("optimizer_backend") or fit_result.details.get("optimizer")
    if optimizer_backend:
        solver_details.append(f"Solver: \\texttt{{{_latex_escape_text(str(optimizer_backend))}}}")
    if "scipy_safety_passed" in fit_result.details:
        status = "passed" if bool(fit_result.details.get("scipy_safety_passed")) else "not used"
        solver_details.append(f"SciPy precision check: {status}")
    if "precision" in fit_result.details:
        solver_details.append(f"Precision: {latex_escape(str(fit_result.details.get('precision')))}")
    seed_tried = fit_result.details.get("seed_variants_tried")
    seed_succeeded = fit_result.details.get("seed_variants_succeeded")
    if seed_tried is not None or seed_succeeded is not None:
        solver_details.append(
            "Seed variants: "
            f"{latex_escape(str(seed_succeeded if seed_succeeded is not None else '-'))}/"
            f"{latex_escape(str(seed_tried if seed_tried is not None else '-'))}"
        )
    if solver_details:
        lines.append("\\\\ ".join(solver_details))

    value_cells = [val for _, val in table_rows]
    if use_dcolumn:
        numeric_spec = calculate_dcolumn_format_for_column(value_cells, "fit_values")
    else:
        numeric_spec = siunitx_column_spec(value_cells)
    col_spec = f"l {numeric_spec}"

    caption_base = caption_text
    # Always use English for LaTeX output
    caption_text = caption_base if caption_base else "Fit results"
    batch_suffix = f" (Batch {batch_index})" if batch_index is not None else ""

    lines.extend(
        [
            "",
            "\\begin{table}[h]",
            "\\centering",
            f"\\caption{{{latex_escape(caption_text + batch_suffix)}}}",
            f"\\begin{{tabular}}{{{col_spec}}}",
            "\\toprule",
            "Entry &  \\multicolumn{1}{c}{Value} \\\\",
            "\\midrule",
        ]
    )
    for key, val in table_rows:
        lines.append(f"{_format_key(key)} & {val} \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
        ]
    )
    lines.append("")
    return lines
