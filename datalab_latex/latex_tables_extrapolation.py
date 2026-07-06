from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from shared.bilingual import _dual_msg, _split_dual
from shared.formula_defaults import DEFAULT_THREE_POINT_FORMULA
from shared.latex_escaping import latex_escape as _escape_latex_text
from shared.extrapolation_engine import (
    ExtrapolationOptions,
    ExtrapolationResult,
    compute_extrapolation,
    compute_extrapolation_decimal,
    process_data_file as _shared_process_data_file,
    process_data_lines as _shared_process_data_lines,
    process_data_string as _shared_process_data_string,
)
from mpmath import mp

from .expression_engine import _mp, _normalize_expression, safe_eval
from .latex_formatting import (
    _format_value_for_latex_file,
    _siunitx_column_spec,
    calculate_dcolumn_format_for_column,
    format_result_with_uncertainty_latex,
    group_digits_both_sides,
)
from .latex_tables_common import (
    _apply_aliases,
    _build_standalone_preamble,
    _estimate_page_geometry,
    _needs_cjk_support,
    _normalize_header_to_symbol,
    _normalize_table_segments,
    _string_length_hint,
)

# Anything ``_mp()`` (defined in datalab_latex.expression_engine) is documented
# to accept: a real ``mp.mpf`` (returned as-is), Python int / float, or any
# value whose ``str()`` produces a number string. We name the union so the
# public surface stops looking like a typing escape hatch (``object``) and
# instead matches what the body actually requires.
_MpInput: TypeAlias = "mp.mpf | int | float | str"


def format_extrapolation_result_with_num(
    value: _MpInput, uncertainty: _MpInput, uncertainty_digits: int | None = None
) -> str:
    """Format an extrapolation result for LaTeX using \\num{} to allow siunitx parsing."""
    formatted_result = format_result_with_uncertainty_latex(value, uncertainty, uncertainty_digits)

    if "(" in formatted_result and ")" in formatted_result:
        paren_start = formatted_result.find("(")
        paren_end = formatted_result.find(")")

        value_part = formatted_result[:paren_start]
        uncertainty_part = formatted_result[paren_start : paren_end + 1]
        exponent_part = formatted_result[paren_end + 1 :] or ""
        return f"\\num{{{value_part}}}{uncertainty_part}{exponent_part}"

    return f"\\num{{{formatted_result}}}"


DEFAULT_REFERENCE_INDEX = 2
AUTO_REFERENCE_MAX_DIFF_KEY = "auto_max_diff"


def _normalize_method_name(name: str | None) -> str:
    method = (name or "quadratic").strip().lower()
    known = {"quadratic", "power_law", "richardson", "shanks", "wynn_epsilon", "levin_u", "custom"}
    return method if method in known else "quadratic"


ACCELERATOR_METHODS = {"richardson", "shanks", "wynn_epsilon", "levin_u"}
# NOTE: Richardson extrapolation in mpmath needs >= 4 terms to be meaningful; do not treat it as a 3-point method.
THREE_POINT_METHODS = {"quadratic", "power_law"}

_METHOD_DISPLAY_NAMES_ZH = {
    "quadratic": "默认三点公式",
    "power_law": "幂律外推",
    "richardson": "Richardson 序列加速",
    "custom": "自定义公式",
}

_METHOD_DISPLAY_NAMES_EN = {
    "quadratic": "Default three-point formula",
    "power_law": "Power-law extrapolation",
    "richardson": "Richardson acceleration",
    "custom": "Custom formula",
}


def _resolve_reference_index(
    headers: list[str], desired: str | None
) -> int:
    if not headers:
        return 0
    fallback = min(DEFAULT_REFERENCE_INDEX, len(headers) - 1)
    if not desired:
        return fallback
    normalized = desired.strip().lower()
    if not normalized:
        return fallback
    if normalized == AUTO_REFERENCE_MAX_DIFF_KEY:
        return fallback
    lookup = {header.lower(): idx for idx, header in enumerate(headers)}
    if normalized in lookup:
        return lookup[normalized]
    aliases = {chr(ord("a") + idx): idx for idx in range(min(len(headers), 26))}
    if normalized in aliases:
        return aliases[normalized]
    if normalized.isdigit():
        tentative = max(0, int(normalized) - 1)
        return min(tentative, len(headers) - 1)
    return fallback


def _auto_reference_index_max_diff(row_tuple: tuple[mp.mpf, ...], extrapolated_value: mp.mpf) -> int | None:
    """Choose the column index with the largest |extrapolated_value - ref_i|."""
    if not row_tuple:
        return None
    try:
        V = _mp(extrapolated_value)
    except Exception:
        return None
    try:
        if not mp.isfinite(V):
            return None
    except Exception:
        pass
    best_idx: int | None = None
    best_diff: mp.mpf | None = None
    for idx, ref_val in enumerate(row_tuple):
        try:
            if not mp.isfinite(ref_val):
                continue
            diff = mp.fabs(V - ref_val)
            if not mp.isfinite(diff):
                continue
        except Exception:
            continue
        if best_idx is None or (best_diff is not None and diff > best_diff):
            best_idx = idx
            best_diff = diff
    return best_idx


def _reference_label(headers: list[str], index: int) -> str:
    if headers and 0 <= index < len(headers):
        return headers[index]
    return f"列{index + 1}"


def _method_display_name(method: str, lang: str = "zh") -> str:
    """Return a language-specific display name for a method identifier."""
    if lang == "en":
        return _METHOD_DISPLAY_NAMES_EN.get(method, method)
    return _METHOD_DISPLAY_NAMES_ZH.get(method, method)


def _append_option_warning(
    options: ExtrapolationOptions, message: str, verbose: bool
) -> None:
    if not message:
        return
    if message not in options.warnings:
        options.warnings.append(message)
        if verbose:
            print(f"Warning: {message}")


def _maybe_warn_three_point_limit(
    options: ExtrapolationOptions,
    headers: list[str],
    method: str,
    verbose: bool,
) -> None:
    if method not in THREE_POINT_METHODS:
        return
    if len(headers) <= 3:
        return
    extra = len(headers) - 3
    zh_name = _method_display_name(method, "zh")
    en_name = _method_display_name(method, "en")
    message_zh = f"{zh_name} 仅支持三点外推，已忽略多余 {extra} 列。"
    message_en = f"{en_name} only supports three-point extrapolation; ignored {extra} extra column(s)."
    message = f"{message_zh} / {message_en}"
    _append_option_warning(options, message, verbose)


def _result_components(
    entry: ExtrapolationResult | tuple[mp.mpf, mp.mpf],
) -> tuple[mp.mpf, mp.mpf]:
    if isinstance(entry, ExtrapolationResult):
        return entry.value, entry.uncertainty
    return entry


def _evaluate_custom_formula(
    formula: str,
    headers: list[str],
    row_values: tuple[mp.mpf, ...],
    warnings: list[str] | None = None,
) -> mp.mpf:
    """Evaluate the custom extrapolation formula using the same parser as error propagation."""
    normalized_formula = _normalize_expression(formula)
    if not normalized_formula.strip():
        raise ValueError("未提供自定义公式。")

    variables: dict[str, object] = {}
    alias_map: dict[str, str] = {}
    seen: set[str] = set()
    for idx, header in enumerate(headers):
        canonical = _normalize_header_to_symbol(header, idx)
        base = canonical
        counter = 2
        while canonical in seen:
            canonical = f"{base}_{counter}"
            counter += 1
        seen.add(canonical)
        variables[canonical] = row_values[idx]
        alias_map[f"x{idx + 1}"] = canonical

    for alias, pos in (("A", 0), ("B", 1), ("C", 2)):
        if pos < len(headers):
            alias_map[alias] = list(variables.keys())[pos]

    rewritten = _apply_aliases(normalized_formula, alias_map)
    if warnings is not None and rewritten != normalized_formula:
        warnings.append(
            f"自定义公式已重写为使用列名/规范名: {rewritten} / "
            f"Custom formula rewritten to canonical variable names: {rewritten}"
        )
    try:
        return _mp(safe_eval(rewritten, variables))
    except Exception as exc:  # noqa: BLE001
        zh_e, en_e = _split_dual(str(exc))
        raise ValueError(
            _dual_msg(
                f"自定义公式求值失败: {zh_e}",
                f"Failed to evaluate custom formula: {en_e}",
            )
        ) from exc


def _ensure_options(
    options: ExtrapolationOptions | None,
) -> ExtrapolationOptions:
    if isinstance(options, ExtrapolationOptions):
        return options
    return ExtrapolationOptions()


def _process_data_lines(
    lines: list[str],
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[
    list[str],
    list[tuple[mp.mpf, ...]],
    list[ExtrapolationResult],
]:
    return _shared_process_data_lines(lines, verbose=verbose, options=options)


def process_data_file(
    filename: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[
    list[str],
    list[tuple[mp.mpf, ...]],
    list[ExtrapolationResult],
]:
    """Process a data file and perform extrapolation on each row."""
    return _shared_process_data_file(filename, verbose=verbose, options=options)


def process_data_string(
    content: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[
    list[str],
    list[tuple[mp.mpf, ...]],
    list[ExtrapolationResult],
]:
    """Process an in-memory string and perform extrapolation on each row."""
    return _shared_process_data_string(content, verbose=verbose, options=options)


def _append_extrapolation_table_block(
    latex_content: list[str],
    headers: list[str],
    column_count: int,
    formatted_data_columns: list[list[str]],
    formatted_result_strings: list[str],
    data_format_block: str,
    result_format: str,
    caption: str | None,
    header_row: str,
    block_index: int,
    total_blocks: int,
    start_row: int,
    end_row: int,
) -> None:
    latex_content.append("\\begin{table}[!ht]")
    base_caption = caption if caption else "Extrapolation results table"
    caption_text = f"{base_caption} (Part {block_index})" if total_blocks > 1 else base_caption
    # Escape user-supplied caption text before embedding in \caption{} so LaTeX
    # specials (& _ $ # % ~ ^ ...) can't break the compile or inject commands —
    # mirrors the error-propagation table (audit R3 D1).
    caption_text = _escape_latex_text(caption_text)
    label = "tab:extrapolation" if block_index == 1 else f"tab:extrapolation-{block_index}"
    latex_content.append(f"\\caption{{{caption_text}}}\\label{{{label}}}")
    latex_content.append("\\begin{threeparttable}")
    latex_content.append(
        "\\begin{tabular*}{\\textwidth}{@{\\extracolsep{\\fill}} c "
        + data_format_block
        + " "
        + result_format
        + "}"
    )
    latex_content.append("\\toprule")
    latex_content.append(header_row)
    for local_index, row_index in enumerate(range(start_row, end_row), 1):
        data_cells = [formatted_data_columns[col_idx][row_index] for col_idx in range(column_count)]
        result_formatted = formatted_result_strings[row_index]
        row = "{0} & {1} & {2} \\\\".format(local_index, " & ".join(data_cells), result_formatted)
        latex_content.append(row)
    latex_content.extend(
        [
            "\\bottomrule",
            "\\end{tabular*}",
            "\\begin{tablenotes}",
            "\\footnotesize",
            "\\item \\hspace{-1em}\\textit{Note:} Default table layout",
            "\\end{tablenotes}",
            "\\end{threeparttable}",
            "\\end{table}",
            "",
        ]
    )


def generate_latex_table(
    headers: Sequence[str],
    data_rows: Sequence[tuple[mp.mpf, ...]],
    extrapolated_results: Sequence[ExtrapolationResult | tuple[mp.mpf, mp.mpf]],
    output_filename: str,
    caption: str | None = None,
    precision: int | None = None,
    verbose: bool = False,
    use_dcolumn: bool = False,
    table_segments: list[tuple[int, int]] | None = None,
    result_uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
    native_group_width: bool = True,
) -> None:
    """Generate a LaTeX table with the data and extrapolation results."""
    headers = list(headers)
    data_rows = list(data_rows)
    extrapolated_results = list(extrapolated_results)
    latex_content: list[str] = []
    # App-side grouping when the engine can't vary the siunitx group WIDTH (non-native) and
    # grouping is on in siunitx (non-dcolumn) mode: pre-group each numeric cell + use plain r
    # columns instead of S columns siunitx would re-group at a fixed 3.
    _group = max(0, int(latex_group_size))
    app_group = (not native_group_width) and (not use_dcolumn) and _group > 0

    column_count = len(headers)
    formatted_data_columns: list[list[str]] = [[] for _ in range(column_count)]
    formatted_result_strings: list[str] = []
    column_lengths = [len(str(max(1, len(data_rows)))) + 1]
    latex_input_decimals = precision if precision is not None else None

    for row_values, result_entry in zip(data_rows, extrapolated_results):
        if len(row_values) < column_count:
            raise ValueError("数据列数量与表头不一致，无法生成 LaTeX 表格。")
        for col_idx in range(column_count):
            value = _mp(row_values[col_idx])
            formatted = _format_value_for_latex_file(
                value=value,
                sigma=None,
                use_dcolumn=use_dcolumn,
                latex_input_decimals=latex_input_decimals,
                is_input=True,
                latex_group_size=latex_group_size,
            )
            formatted_data_columns[col_idx].append(formatted)

        value, sigma = _result_components(result_entry)
        result_formatted = _format_value_for_latex_file(
            value=_mp(value),
            sigma=_mp(sigma),
            use_dcolumn=use_dcolumn,
            latex_input_decimals=latex_input_decimals,
            is_input=False,
            latex_group_size=latex_group_size,
            uncertainty_digits=result_uncertainty_digits,
        )
        formatted_result_strings.append(result_formatted)

    if app_group:
        def _wrap(cell: str) -> str:
            return "\\text{" + group_digits_both_sides(cell, _group) + "}"
        formatted_data_columns = [[_wrap(c) for c in col] for col in formatted_data_columns]
        formatted_result_strings = [_wrap(c) for c in formatted_result_strings]

    for col_strings in formatted_data_columns:
        column_lengths.append(max((_string_length_hint(s) for s in col_strings), default=6))
    column_lengths.append(max((_string_length_hint(s) for s in formatted_result_strings), default=8))

    num_table_rows = len(data_rows) + 6
    page_w, _ = _estimate_page_geometry(column_lengths, num_table_rows)
    cjk_segments = [caption if caption else "", " ".join(headers)]
    needs_cjk = _needs_cjk_support(*cjk_segments)
    latex_content.extend(
        _build_standalone_preamble(
            page_w,
            include_dcolumn=use_dcolumn,
            needs_cjk=needs_cjk,
            latex_group_size=latex_group_size,
            native_group_width=native_group_width,
        )
    )

    header_cells = [
        # Escape user-supplied column headers before embedding (audit R3 D2).
        "\\multicolumn{{1}}{{c}}{{{0}}}".format(
            _escape_latex_text(headers[idx] if idx < len(headers) else f"列{idx + 1}")
        )
        for idx in range(column_count)
    ]
    header_row = "$n$ & " + " & ".join(header_cells) + " & \\multicolumn{1}{c}{Extrap.} \\\\\\hline"
    segments = _normalize_table_segments(len(data_rows), table_segments)
    for block_index, (start_row, end_row) in enumerate(segments, 1):
        if use_dcolumn:
            data_formats = [
                calculate_dcolumn_format_for_column(
                    formatted_data_columns[col_idx][start_row:end_row],
                    f"extrapolation_data_{col_idx}",
                )
                for col_idx in range(column_count)
            ]
            data_format_block = " ".join(data_formats)
            result_format = calculate_dcolumn_format_for_column(
                formatted_result_strings[start_row:end_row],
                f"extrapolation_result_{block_index}",
            )
        elif app_group:
            # Cells are pre-grouped + wrapped in \text{}; plain right-aligned columns.
            data_format_block = " ".join(["r"] * column_count)
            result_format = "r"
        else:
            data_formats = [
                _siunitx_column_spec(formatted_data_columns[col_idx][start_row:end_row])
                for col_idx in range(column_count)
            ]
            data_format_block = " ".join(data_formats)
            result_format = _siunitx_column_spec(formatted_result_strings[start_row:end_row])
        _append_extrapolation_table_block(
            latex_content,
            headers,
            column_count,
            formatted_data_columns,
            formatted_result_strings,
            data_format_block,
            result_format,
            caption,
            header_row,
            block_index,
            len(segments),
            start_row,
            end_row,
        )
    latex_content.append("\\end{document}")

    with open(output_filename, "w") as f:
        f.write("\n".join(latex_content))

    if verbose:
        print("LaTeX table written to: {0}".format(output_filename))
        print("Total rows: {0}".format(len(data_rows)))


__all__ = [
    "DEFAULT_THREE_POINT_FORMULA",
    "ExtrapolationOptions",
    "ExtrapolationResult",
    "compute_extrapolation",
    "compute_extrapolation_decimal",
    "format_extrapolation_result_with_num",
    "generate_latex_table",
    "process_data_file",
    "process_data_string",
]
