"""Qt-free LaTeX generator for fitting reports/tables.

This module builds LaTeX output without importing Qt, so it can be unit-tested and reused from both GUI and tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import mpmath as mp

from data_extrapolation_latex_latest import (
    calculate_dcolumn_format_for_column,
    format_value_for_latex_file,
    siunitx_column_spec,
)
from datalab_latex.sisetup_block import build_sisetup_block
from fitting.diagnostic_formatting import build_fitting_diagnostic_latex_entries
from fitting.hp_fitter import FitResult
from shared.unit_annotations import unit_annotation_text, unit_annotations_for_labels


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


def build_fit_latex_preamble(
    *, use_dcolumn: bool, digits: int, latex_group_size: int, native_group_width: bool = True
) -> list[str]:
    # max(0, ...) not max(1, ...): group_size 0 must stay 0 so build_sisetup_block emits the
    # "no grouping" body (group-digits = false). max(1,..) forced 0→1 → grouping stayed ON,
    # contradicting the UI's "0 = 不分组" (dual-model review F1).
    group_size = max(0, int(latex_group_size))
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
    # native_group_width True → emit siunitx digit-group-size (native S-column variable-width
    # grouping); False (bundled Tectonic) → don't (cells are pre-grouped app-side).
    emit_dgs = bool(native_group_width and not use_dcolumn and group_size > 0)
    lines.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=use_dcolumn,
            emit_digit_group_size=emit_dgs,
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
    units: Mapping[str, Any] | None = None,
    native_group_width: bool = True,
) -> list[str]:
    from datalab_latex.latex_formatting import group_digits_both_sides

    default_unc_digits = default_uncertainty_digits
    variable_pairs = variable_pairs or []
    target_column = (target_column or "").strip()
    # App-side grouping when the engine can't vary the siunitx group WIDTH (non-native) and
    # grouping is on in siunitx (non-dcolumn) mode: pre-group each value cell + use a plain r
    # column instead of an S column siunitx would re-group at a fixed 3.
    _group = max(0, int(latex_group_size))
    app_group = (not native_group_width) and (not use_dcolumn) and _group > 0

    def _maybe_group(cell: str) -> str:
        if app_group and "\\multicolumn" not in cell and "\\text" not in cell:
            return "\\text{" + group_digits_both_sides(cell, _group) + "}"
        return cell

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
        return _maybe_group(
            format_value_for_latex_file(
                mp.mpf(val),
                sigma,
                use_dcolumn=use_dcolumn,
                latex_input_decimals=digits,
                is_input=is_input,
                latex_group_size=latex_group_size,
                uncertainty_digits=sigma_digits,
            )
        )

    def _format_key(key: str) -> str:
        if "\\" in key or "$" in key or "^" in key:
            return key
        return latex_escape(key)

    def _target_unit() -> str:
        if target_column:
            mapped = unit_annotations_for_labels(
                units,
                "outputs",
                [target_column],
                fallback_prefix="output",
                default_key="result",
            )
            unit = mapped.get(target_column, "")
            if unit:
                return unit
        return unit_annotation_text(units, "outputs", "result")

    target_idx = headers.index(target_column) if target_column in headers else 0
    index_lookup = {name: headers.index(name) for name in headers}
    x_idx = index_lookup.get(variable_pairs[0][1], 0) if variable_pairs else 0
    output_unit = _target_unit()
    parameter_units = unit_annotations_for_labels(
        units,
        "parameters",
        fit_result.params.keys(),
        fallback_prefix="parameter",
    )

    table_rows: list[tuple[str, str, str]] = []
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
        table_rows.append((label, val_text, output_unit))

    for name, value in fit_result.params.items():
        total_err = (fit_result.param_errors_total or fit_result.param_errors).get(name, mp.mpf("0"))
        val_text = _format_cell_value(value, total_err, is_input=False)
        parameter_unit = parameter_units.get(name, "")
        table_rows.append((f"Param {name}", val_text, parameter_unit))
        sys_err = (fit_result.param_errors_sys or {}).get(name)
        if sys_err and not mp.almosteq(sys_err, mp.mpf("0")):
            stat_err = (fit_result.param_errors_stat or {}).get(name, total_err)
            stat_text = _format_cell_value(stat_err, None, is_input=False)
            sys_text = _format_cell_value(sys_err, None, is_input=False)
            # Split stat and sys errors into two separate rows
            table_rows.append((f"{name} stat", stat_text, parameter_unit))
            table_rows.append((f"{name} sys", sys_text, parameter_unit))

    metrics = [
        ("$\\chi^2$", fit_result.chi2),
        ("Reduced $\\chi^2$", fit_result.reduced_chi2),
        ("AIC", fit_result.aic),
        ("BIC", fit_result.bic),
        ("$R^2$", fit_result.r2),
        ("RMSE", fit_result.rmse),
    ]
    for label, value in metrics:
        val_text = _maybe_group(format_value_for_latex_file(
            mp.mpf(value),
            None,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=digits,
            is_input=True,
            latex_group_size=latex_group_size,
        ))
        row_unit = output_unit if label == "RMSE" else ""
        table_rows.append((label, val_text, row_unit))

    def _format_diagnostic_value(value: object) -> str:
        return _maybe_group(format_value_for_latex_file(
            mp.mpf(value),
            None,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=digits,
            is_input=True,
            latex_group_size=latex_group_size,
        ))

    diagnostic_entries, diagnostic_warnings = build_fitting_diagnostic_latex_entries(
        fit_result,
        format_value=_format_diagnostic_value,
        escape_text=latex_escape,
    )
    table_rows.extend((key, value, "") for key, value in diagnostic_entries)
    diagnostic_warning_lines = [f"Diagnostic warning: {warning}\\\\" for warning in diagnostic_warnings]

    lines: list[str] = []
    if batch_index is not None:
        # Always use English for LaTeX output
        lines.append(f"\\subsection*{{Fit Results: Batch {batch_index}}}")

    implicit_equation = str(fit_result.details.get("equation") or "").strip()
    implicit_output = str(fit_result.details.get("output_expression") or "").strip()
    if implicit_equation:
        lines.append(f"Implicit equation: \\texttt{{{latex_escape(implicit_equation)}}}\\\\")
    if implicit_output:
        lines.append(f"Implicit output: \\texttt{{{latex_escape(implicit_output)}}}\\\\")

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
        solver_details.append(f"Solver: \\texttt{{{latex_escape(str(optimizer_backend))}}}")
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
    lines.extend(diagnostic_warning_lines)

    value_cells = [val for _, val, _unit in table_rows]
    if use_dcolumn:
        numeric_spec = calculate_dcolumn_format_for_column(value_cells, "fit_values")
    elif app_group:
        # Cells are pre-grouped + wrapped in \text{}; a plain right-aligned column.
        numeric_spec = "r"
    else:
        numeric_spec = siunitx_column_spec(value_cells)
    include_unit_column = any(unit for _key, _val, unit in table_rows)
    col_spec = f"l l {numeric_spec}" if include_unit_column else f"l {numeric_spec}"

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
            (
                "Entry & Unit & \\multicolumn{1}{c}{Value} \\\\"
                if include_unit_column
                else "Entry &  \\multicolumn{1}{c}{Value} \\\\"
            ),
            "\\midrule",
        ]
    )
    for key, val, unit in table_rows:
        if include_unit_column:
            lines.append(f"{_format_key(key)} & {latex_escape(unit)} & {val} \\\\")
        else:
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
