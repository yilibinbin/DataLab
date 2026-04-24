"""Statistics helpers extracted from the GUI layer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from mpmath import mp

from data_extrapolation_latex_latest import (
    calculate_dcolumn_format_for_column,
    format_value_for_latex_file,
    _dual_msg,
    siunitx_column_spec,
)


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


def compute_statistics(
    values: Iterable[mp.mpf],
    sigmas: Iterable[mp.mpf | None],
    stats_mode: str,
    use_sample: bool = True,
    use_weighted_variance: bool = True,
) -> dict:
    values_mp = [mp.mpf(v) for v in values]
    sigmas_norm = [mp.mpf(s) if s is not None else None for s in sigmas]
    n = len(values_mp)
    if n == 0:
        raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))
    valid_values: list[mp.mpf] = list(values_mp)

    stats_mode = (stats_mode or "").strip()
    dropped = 0
    effective_n: mp.mpf | None = None
    warnings_list: list[str] = []

    sample_based = use_sample
    # 兼容旧字符串模式：以字符串后缀推断样本/总体
    if stats_mode.endswith("population"):
        sample_based = False
    if stats_mode.endswith("sample"):
        sample_based = True

    if stats_mode in {"mean_sample", "mean_population", "mean"}:  # arithmetic mean
        mean = mp.fsum(values_mp) / n
        if n > 1:
            denom = (n - 1) if sample_based else n
            var = mp.fsum([(v - mean) ** 2 for v in values_mp]) / denom
            std = mp.sqrt(var)
        else:
            std = mp.mpf("0")
        # 均值标准误差：无论样本/总体，分母均使用 sqrt(n)
        denom_se = max(1, n)
        std_mean = std / mp.sqrt(denom_se) if n > 1 else std
        method_label = "Arithmetic mean (sample)" if sample_based else "Arithmetic mean (population)"
    elif stats_mode in {"weighted_sigma", "weighted"}:
        zero_sigma_values: list[mp.mpf] = []
        weights: list[tuple[mp.mpf, mp.mpf]] = []
        used_values: list[mp.mpf] = []
        epsilon = mp.power(10, -max(8, mp.dps // 2))
        for v, s in zip(values_mp, sigmas_norm):
            if s is None:
                dropped += 1
                continue
            if s < 0:
                raise ValueError(
                    _dual_msg(
                        "检测到负的不确定度，数据无效。",
                        "Negative uncertainty encountered; data invalid.",
                    )
                )
            if mp.fabs(s) <= epsilon:
                zero_sigma_values.append(mp.mpf(v))
                continue
            weights.append((mp.mpf(v), mp.mpf("1") / (s * s)))
            used_values.append(mp.mpf(v))
        if zero_sigma_values:
            # 零不确定度视为无限权重；若多值不一致则报告错误
            unique = {mp.nstr(val, 30) for val in zero_sigma_values}
            if len(unique) > 1:
                raise ValueError(
                    _dual_msg(
                        "存在 σ=0 但数值不一致的数据点，无法计算加权平均。",
                        "Conflicting zero-uncertainty points.",
                    )
                )
            anchor = zero_sigma_values[0]
            mean = anchor
            std = mp.mpf("0")
            std_mean = mp.mpf("0")
            method_label = "Weighted mean (σ=0 anchor)"
            effective_n = mp.mpf(len(zero_sigma_values))
            warnings_list.append(
                _dual_msg("检测到 σ=0，按无限权重处理。", "Detected σ=0; treated as infinite weight.")
            )
            return {
                "mean": mean,
                "std_mean": std_mean,
                "std": std,
                "v_min": min(values_mp),
                "v_max": max(values_mp),
                "method_label": method_label,
                "dropped": dropped,
                "effective_n": effective_n,
                "zero_sigma_anchor": True,
                "warnings": warnings_list,
            }
        if not weights:
            raise ValueError(
                _dual_msg(
                    "未找到有效的不确定度，无法进行加权平均。",
                    "No valid uncertainties were found; cannot compute a weighted mean.",
                )
            )
        valid_values = used_values
        W = mp.fsum([w for _, w in weights])
        W2 = mp.fsum([w * w for _, w in weights])
        if not (W > 0) or mp.isnan(W):
            warnings_list.append(
                _dual_msg(
                    "权重总和为 0（或非有限），已回退为算术平均。",
                    "Sum of weights is 0 (or non-finite); fell back to arithmetic mean.",
                )
            )
            mean = mp.fsum(valid_values) / len(valid_values)
            if len(valid_values) > 1:
                denom = (len(valid_values) - 1) if sample_based else len(valid_values)
                var = mp.fsum([(v - mean) ** 2 for v in valid_values]) / denom
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
            }

        mean = mp.fsum([val * w for val, w in weights]) / W
        centered = [(val - mean) for val, _ in weights]
        if use_weighted_variance:
            # 加权方差（样本/总体）：使用加权平方和，样本模式采用有效自由度校正
            if len(weights) > 1:
                numer = mp.fsum([w * (c * c) for (val, w), c in zip(weights, centered)])
                if sample_based and W > 0:
                    # 有效自由度: W - (W2 / W) 参考加权样本方差定义
                    if not (W2 > 0) or mp.isnan(W2):
                        warnings_list.append(
                            _dual_msg(
                                "无法计算加权样本有效自由度（W2<=0 或非有限），未使用样本校正。",
                                "Could not compute effective weighted degrees of freedom (W2<=0 or non-finite); sample correction disabled.",
                            )
                        )
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
                else:
                    denom = W
                var = numer / denom if denom != 0 else mp.mpf("0")
                std = mp.sqrt(var)
            else:
                std = mp.mpf("0")
            # 均值标准误差：对 1/σ^2 加权，标准误差 = sqrt(1 / Σw)
            std_mean = mp.sqrt(mp.mpf("1") / W) if W > 0 else mp.nan
        else:
            # 不加权的方差/标准误差（仅使用有效样本数）
            count_w = len(weights)
            if count_w > 1:
                denom = (count_w - 1) if sample_based else count_w
                var = mp.fsum([c * c for c in centered]) / denom
                std = mp.sqrt(var)
            else:
                std = mp.mpf("0")
            denom_se = max(1, len(weights))
            std_mean = std / mp.sqrt(denom_se) if len(weights) > 0 else std
        method_label = "Weighted mean (sample)" if sample_based else "Weighted mean (population)"
        if not (W2 > 0) or mp.isnan(W2):
            warnings_list.append(
                _dual_msg(
                    "无法计算有效样本数（W2<=0 或非有限）。",
                    "Could not compute effective sample size (W2<=0 or non-finite).",
                )
            )
        elif not mp.almosteq(W2, mp.mpf("0")):
            effective_n = (W * W) / W2
    else:
        raise ValueError(_dual_msg("未知的统计模式。", "Unknown statistics mode."))

    v_min = min(valid_values) if valid_values else mp.nan
    v_max = max(valid_values) if valid_values else mp.nan

    return {
        "mean": mean,
        "std_mean": std_mean,
        "std": std,
        "v_min": v_min,
        "v_max": v_max,
        "method_label": method_label,
        "dropped": dropped,
        "effective_n": effective_n,
        "warnings": warnings_list,
    }


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
