"""Statistics helpers extracted from the GUI layer."""

from __future__ import annotations

from pathlib import Path

from mpmath import mp

from datalab_core.statistics_compute import compute_statistics as compute_statistics


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


def _format_table_value(
    value: mp.mpf,
    sigma: mp.mpf | None,
    digits: int,
    use_dcolumn: bool,
    uncertainty_digits: int | None = None,
    *,
    is_input: bool = True,
    group_size: int = 3,
) -> tuple[str, bool]:
    """Return (text, needs_multicolumn)."""
    from data_extrapolation_latex_latest import format_value_for_latex_file

    # Normalize sigma to mp.mpf while preserving digits hint if provided
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
    text = format_value_for_latex_file(
        value,
        sigma,
        use_dcolumn=use_dcolumn,
        latex_input_decimals=digits,
        is_input=is_input,
        latex_group_size=group_size,
        uncertainty_digits=sigma_digits,
    )
    return text, False

def generate_statistics_latex(
    value_col: str,
    data_rows: list[tuple[mp.mpf, ...]],
    sigma_rows: list[tuple[mp.mpf | None, ...]],
    result: dict,
    digits: int,
    tex_path: str,
    use_dcolumn: bool,
    uncertainty_digits: int | None = None,
    caption: str | None = None,
    latex_group_size: int = 3,
):
    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec
    from datalab_latex.sisetup_block import build_sisetup_block

    group_size = max(1, int(latex_group_size))
    num_cols = len(data_rows[0]) if data_rows else 0
    formatted_columns: list[list[str]] = [[] for _ in range(num_cols)]
    for row_idx, row in enumerate(data_rows):
        for col_idx in range(num_cols):
            value = row[col_idx] if col_idx < len(row) else mp.mpf("0")
            sigma = None
            if sigma_rows and row_idx < len(sigma_rows) and col_idx < len(sigma_rows[row_idx]):
                sigma = sigma_rows[row_idx][col_idx]
            cell, _ = _format_table_value(
                value,
                sigma,
                digits,
                use_dcolumn,
                uncertainty_digits,
                is_input=True,
                group_size=group_size,
            )
            formatted_columns[col_idx].append(cell)

    if use_dcolumn:
        num_specs = [
            calculate_dcolumn_format_for_column(formatted_columns[i], f"stats_data_col_{i}")
            for i in range(num_cols)
        ]
    else:
        num_specs = [siunitx_column_spec(formatted_columns[i]) for i in range(num_cols)]
    data_col_spec = "l" + ("" if not num_specs else " " + " ".join(num_specs))

    summary_rows: list[tuple[str, str]] = []
    summary_rows.append(
        (
            "Mean",
            _format_table_value(
                result["mean"],
                result["std_mean"],
                digits,
                use_dcolumn,
                uncertainty_digits,
                is_input=False,
                group_size=group_size,
            )[0],
        )
    )
    summary_rows.extend(
        [
            (
                "Std. error",
                _format_table_value(
                    result["std_mean"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
            (
                "Min",
                _format_table_value(
                    result["v_min"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
            (
                "Max",
                _format_table_value(
                    result["v_max"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
        ]
    )
    if not mp.isnan(result.get("std", mp.nan)):
        summary_rows.append(
            (
                "Std. dev.",
                _format_table_value(
                    result["std"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            )
        )

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
        "\\usepackage{geometry}",
        "\\usepackage{graphicx}",
    ]
    if use_dcolumn:
        lines.append("\\usepackage{dcolumn}")
        lines.append("\\newcolumntype{d}[1]{D{.}{.}{#1}}")
    lines.append("\\usepackage{siunitx}")

    # v2/v3-compatible \sisetup{...} block. ``digit-group-size`` was a
    # siunitx-v3-only key whose hard-coded use here broke compiles
    # against older TeX Live installs; the helper now emits a
    # ``\@ifpackagelater`` guard so v2 falls back to the safe default.
    lines.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=use_dcolumn,
        ).rstrip("\n")
    )

    title = f"Statistical Summary ({latex_escape(result.get('method_label', ''))})"
    table_caption = caption if caption else f"Statistical summary for {latex_escape(value_col)}"
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            f"\\section*{{{title}}}",
            f"Value column: \\texttt{{{latex_escape(value_col)}}}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{table_caption}}}",
            f"\\begin{{tabular}}{{{data_col_spec}}}",
            "\\toprule",
            "Entry & " + " & ".join(
                f"\\multicolumn{{1}}{{c}}{{{latex_escape(value_col) if num_cols == 1 else 'Col {}'.format(i + 1)}}}"
                for i in range(num_cols)
            ) + " \\\\",
            "\\midrule",
        ]
    )
    for idx in range(len(data_rows)):
        row_cells = [formatted_columns[col_idx][idx] for col_idx in range(num_cols)]
        lines.append(f"Input row {idx + 1} & " + " & ".join(row_cells) + " \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

    # Summary table (single numeric column)
    if use_dcolumn:
        summary_num_spec = calculate_dcolumn_format_for_column(
            [val for _, val in summary_rows],
            "stats_summary",
        )
    else:
        summary_num_spec = siunitx_column_spec([val for _, val in summary_rows])
    summary_col_spec = f"l {summary_num_spec}"
    lines.extend(
        [
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{table_caption} (Summary)}}",
            f"\\begin{{tabular}}{{{summary_col_spec}}}",
            "\\toprule",
            "Entry & \\multicolumn{1}{c}{Value} \\\\",
            "\\midrule",
        ]
    )
    for key, val in summary_rows:
        lines.append(f"{latex_escape(key)} & {val} \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", "\\end{document}"])

    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)


def generate_statistics_latex_batches(
    value_col: str,
    batches: list[dict],
    digits: int,
    tex_path: str,
    use_dcolumn: bool,
    caption: str | None = None,
    uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
):
    from data_extrapolation_latex_latest import calculate_dcolumn_format_for_column, siunitx_column_spec
    from datalab_latex.sisetup_block import build_sisetup_block

    group_size = max(1, int(latex_group_size))
    def _build_block(batch_idx: int, rows, sigma_rows, result, caption_text: str):
        num_cols = len(rows[0]) if rows else 0
        formatted_columns: list[list[str]] = [[] for _ in range(num_cols)]
        for row_idx, row in enumerate(rows):
            for col_idx in range(num_cols):
                value = row[col_idx] if col_idx < len(row) else mp.mpf("0")
                sigma = None
                if sigma_rows and row_idx < len(sigma_rows) and col_idx < len(sigma_rows[row_idx]):
                    sigma = sigma_rows[row_idx][col_idx]
                cell, _ = _format_table_value(
                    value,
                    sigma,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )
                formatted_columns[col_idx].append(cell)

        if use_dcolumn:
            num_specs = [
                calculate_dcolumn_format_for_column(formatted_columns[i], f"stats_batch_{batch_idx}_col_{i}")
                for i in range(num_cols)
            ]
        else:
            num_specs = [siunitx_column_spec(formatted_columns[i]) for i in range(num_cols)]
        data_col_spec = "l" + ("" if not num_specs else " " + " ".join(num_specs))

        summary_rows: list[tuple[str, str]] = [
            (
                "Mean",
                _format_table_value(
                    result["mean"],
                    result["std_mean"],
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=False,
                    group_size=group_size,
                )[0],
            ),
            (
                "Std. error",
                _format_table_value(
                    result["std_mean"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
            (
                "Min",
                _format_table_value(
                    result["v_min"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
            (
                "Max",
                _format_table_value(
                    result["v_max"],
                    None,
                    digits,
                    use_dcolumn,
                    uncertainty_digits,
                    is_input=True,
                    group_size=group_size,
                )[0],
            ),
        ]
        if not mp.isnan(result.get("std", mp.nan)):
            summary_rows.append(
                (
                    "Std. dev.",
                    _format_table_value(
                        result["std"],
                        None,
                        digits,
                        use_dcolumn,
                        uncertainty_digits,
                        is_input=True,
                        group_size=group_size,
                    )[0],
                )
            )

        lines_block = [
            f"\\subsection*{{Statistics: Batch {batch_idx}}}",
            f"Value column: \\texttt{{{latex_escape(value_col)}}}",
            "",
            "\\begin{table}[!ht]",
            "\\centering",
            f"\\caption{{{caption_text}}}",
            f"\\begin{{tabular}}{{{data_col_spec}}}",
            "\\toprule",
            "Entry & " + " & ".join(
                f"\\multicolumn{{1}}{{c}}{{{latex_escape(value_col) if num_cols == 1 else 'Col {}'.format(i + 1)}}}"
                for i in range(num_cols)
            ) + " \\\\",
            "\\midrule",
        ]
        for idx in range(len(rows)):
            row_cells = [formatted_columns[col_idx][idx] for col_idx in range(num_cols)]
            lines_block.append(f"Input row {idx + 1} & " + " & ".join(row_cells) + " \\\\")
        lines_block.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

        if use_dcolumn:
            summary_num_spec = calculate_dcolumn_format_for_column(
                [val for _, val in summary_rows],
                f"stats_batch_{batch_idx}_summary",
            )
        else:
            summary_num_spec = siunitx_column_spec([val for _, val in summary_rows])
        summary_col_spec = f"l {summary_num_spec}"
        lines_block.extend(
            [
                "\\begin{table}[!ht]",
                "\\centering",
                f"\\caption{{{caption_text} (Summary)}}",
                f"\\begin{{tabular}}{{{summary_col_spec}}}",
                "\\toprule",
                "Entry & \\multicolumn{1}{c}{Value} \\\\",
                "\\midrule",
            ]
        )
        for key, val in summary_rows:
            lines_block.append(f"{latex_escape(key)} & {val} \\\\")
        lines_block.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
        return lines_block

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
        "\\usepackage{geometry}",
        "\\usepackage{graphicx}",
    ]
    if use_dcolumn:
        lines.append("\\usepackage{dcolumn}")
        lines.append("\\newcolumntype{d}[1]{D{.}{.}{#1}}")
    lines.append("\\usepackage{siunitx}")

    # v2/v3-compatible \sisetup{...} block (see top-of-file note).
    lines.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=use_dcolumn,
        ).rstrip("\n")
    )

    title = f"Statistical Summary ({latex_escape(value_col)})"
    base_caption = caption if caption else f"Statistical summary for {latex_escape(value_col)}"
    lines.extend(
        [
            "\\geometry{margin=1in}",
            "\\begin{document}",
            f"\\section*{{{latex_escape(title)}}}",
        ]
    )
    for batch in batches:
        idx = batch.get("index") or (len(lines))
        rows = batch.get("rows", [])
        sigma_rows = batch.get("sigma_rows", [])
        result = batch.get("result", {})
        caption_text = f"{base_caption} (Batch {idx})"
        lines.extend(_build_block(idx, rows, sigma_rows, result, caption_text))
    lines.append("\\end{document}")
    Path(tex_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(tex_path)
