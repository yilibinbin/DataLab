from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypeAlias

from mpmath import mp

# Anything ``_mp()`` (defined in datalab_latex.expression_engine) is documented
# to accept: a real ``mp.mpf`` (returned as-is), Python int / float, or any
# value whose ``str()`` produces a number string. We name the union so the
# public surface stops looking like a typing escape hatch (``object``) and
# instead matches what the body actually requires.
_MpInput: TypeAlias = "mp.mpf | int | float | str"

from shared.precision import precision_guard as _precision_guard

from extrapolation_methods import (
    PowerLawComputationError,
    PowerLawConfig,
    SequenceAcceleratorConfig,
    SequenceAccelerationError,
    apply_sequence_accelerator,
    extrapolate_power_law,
)

from shared.bilingual import _dual_msg, _split_dual

from .expression_engine import _mp, _normalize_expression, safe_eval
from .latex_formatting import (
    _format_value_for_latex_file,
    _siunitx_column_spec,
    calculate_dcolumn_format_for_column,
    format_result_with_uncertainty_latex,
    format_scientific_latex_decimal,
)
from .latex_tables_common import (
    _apply_aliases,
    _build_standalone_preamble,
    _estimate_page_geometry,
    _needs_cjk_support,
    _normalize_header_to_symbol,
    _normalize_input_lines,
    _normalize_numeric_token,
    _normalize_table_segments,
    _string_length_hint,
)


@dataclass
class ExtrapolationResult:
    """Wrapper for extrapolated values with optional metadata."""

    value: mp.mpf
    uncertainty: mp.mpf
    method: str = "quadratic"
    details: dict[str, mp.mpf | str] = field(default_factory=dict)


@dataclass
class ExtrapolationOptions:
    """Runtime controls for extrapolation."""

    method: str = "quadratic"
    power_law_config: Optional[PowerLawConfig] = None
    uncertainty_column: Optional[str] = None
    mp_precision: Optional[int] = None
    levin_variant: str = "u"
    custom_formula: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    uncertainty_digits: Optional[int] = None

    # New parameters for method-specific configuration
    richardson_p: float = 2.0  # Richardson convergence power exponent
    levin_order: int = 2  # Levin transform order
    levin_weight: str = "default"  # Levin weight function type
    levin_beta: float = 1.0  # Levin beta parameter for reciprocal_beta weight


def compute_extrapolation(
    A: float, B: float, C: float
) -> tuple[float, float]:
    """
    Compute extrapolated value V and uncertainty U using three data points.

    This follows the MATLAB function:
    V = ((C - B)^2) / (B - A) + C
    U = max([abs(V - A), abs(V - B), abs(V - C)])
    """
    if abs(B - A) < 1e-15:
        V = C
        U = max(abs(V - A), abs(V - B), abs(V - C))
        return V, U

    V = ((C - B) ** 2) / (B - A) + C
    U = max(abs(V - A), abs(V - B), abs(V - C))

    return V, U


DEFAULT_THREE_POINT_FORMULA = "((C - B)**2) / (B - A) + C"


def compute_extrapolation_decimal(
    A: _MpInput, B: _MpInput, C: _MpInput
) -> tuple[mp.mpf, mp.mpf]:
    """High-precision extrapolation mirroring the MATLAB formula using mpmath."""
    a_mp = _mp(A)
    b_mp = _mp(B)
    c_mp = _mp(C)
    if mp.fabs(b_mp - a_mp) < mp.mpf("1e-50"):
        V = c_mp
        U = max(mp.fabs(V - a_mp), mp.fabs(V - b_mp), mp.fabs(V - c_mp))
        return V, U
    diff_CB = c_mp - b_mp
    diff_BA = b_mp - a_mp
    V = (diff_CB * diff_CB) / diff_BA + c_mp
    U = max(mp.fabs(V - a_mp), mp.fabs(V - b_mp), mp.fabs(V - c_mp))
    return V, U


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
    list[ExtrapolationResult | tuple[mp.mpf, mp.mpf]],
]:
    opts = _ensure_options(options)
    method = _normalize_method_name(opts.method)
    with _precision_guard(opts.mp_precision):
        lines = _normalize_input_lines(lines)

        if len(lines) < 2:
            raise ValueError("Input must contain at least a header and one data row")

        header_line = lines[0].strip()
        headers = header_line.split()

        if len(headers) < 3:
            raise ValueError("Header must contain at least 3 column names")

        _maybe_warn_three_point_limit(opts, headers, method, verbose)

        if method in THREE_POINT_METHODS and len(headers) > 3:
            headers = headers[:3]

        desired_reference = (opts.uncertainty_column or "").strip()
        use_auto_max_diff = desired_reference.lower() == AUTO_REFERENCE_MAX_DIFF_KEY
        reference_index = _resolve_reference_index(headers, None if use_auto_max_diff else desired_reference)
        fallback_reference_index = min(DEFAULT_REFERENCE_INDEX, len(headers) - 1) if headers else 0
        accelerator_precision = opts.mp_precision
        levin_variant = opts.levin_variant or "u"
        column_count = len(headers)

        if verbose:
            print("Found headers: {0}".format(headers))
            print("Processing {0} data rows...".format(len(lines) - 1))

        data_rows: list[tuple[mp.mpf, ...]] = []
        extrapolated_results: list[
            ExtrapolationResult | tuple[mp.mpf, mp.mpf]
        ] = []

        for line_num, line in enumerate(lines[1:], 2):
            line = line.strip()
            if not line:
                continue

            values = [_normalize_numeric_token(part) for part in line.split()]

            if len(values) < column_count:
                if verbose:
                    print(
                        "Warning: Line {0} has fewer than {1} values, skipping".format(
                            line_num, column_count
                        )
                    )
                continue

            trimmed_values = values[:column_count]

            try:
                numeric_values = tuple(_mp(token) for token in trimmed_values)
            except ValueError as e:
                if verbose:
                    print("Warning: Cannot parse line {0}: {1}".format(line_num, str(e)))
                continue

            row_tuple = numeric_values
            method_values = row_tuple
            if method in THREE_POINT_METHODS:
                method_values = method_values[:3]
            if len(method_values) < 3:
                if verbose:
                    print(
                        "Warning: Line {0} does not have enough values for the selected method".format(
                            line_num
                        )
                    )
                continue

            try:
                if method == "power_law":
                    if not opts.power_law_config:
                        raise PowerLawComputationError("未提供幂律参数（x1/x2/x3 等），无法计算。")
                    power_result = extrapolate_power_law(opts.power_law_config, method_values[:3])
                    ref_idx = min(reference_index, len(row_tuple) - 1)
                    if use_auto_max_diff:
                        chosen = _auto_reference_index_max_diff(row_tuple, power_result.value)
                        if chosen is None:
                            _append_option_warning(
                                opts,
                                _dual_msg(
                                    "最大差异列：无法自动选择参考列，已回退到默认参考列。",
                                    "Max-diff column: unable to auto-select a reference column; fell back to the default reference column.",
                                ),
                                verbose,
                            )
                            ref_idx = min(fallback_reference_index, len(row_tuple) - 1)
                        else:
                            ref_idx = chosen
                    reference_value = row_tuple[ref_idx]
                    V = power_result.value
                    U = abs(V - reference_value)
                    result_entry = ExtrapolationResult(
                        value=V,
                        uncertainty=U,
                        method="power_law",
                        details={
                            "reference_column": _reference_label(headers, ref_idx),
                            "exponent": power_result.exponent,
                            "amplitude": power_result.amplitude,
                        },
                    )
                elif method in ACCELERATOR_METHODS:
                    precision = accelerator_precision
                    if not precision:
                        raise SequenceAccelerationError("请设置多精度位数以执行该序列加速方法。")
                    accel_config = SequenceAcceleratorConfig(
                        precision=precision,
                        levin_variant=levin_variant,
                    )
                    accel_result = apply_sequence_accelerator(method, method_values, accel_config)
                    ref_idx = min(reference_index, len(row_tuple) - 1)
                    if use_auto_max_diff:
                        chosen = _auto_reference_index_max_diff(row_tuple, accel_result.value)
                        if chosen is None:
                            _append_option_warning(
                                opts,
                                _dual_msg(
                                    "最大差异列：无法自动选择参考列，已回退到默认参考列。",
                                    "Max-diff column: unable to auto-select a reference column; fell back to the default reference column.",
                                ),
                                verbose,
                            )
                            ref_idx = min(fallback_reference_index, len(row_tuple) - 1)
                        else:
                            ref_idx = chosen
                    reference_value = row_tuple[ref_idx]
                    V = accel_result.value
                    U = abs(V - reference_value)
                    result_entry = ExtrapolationResult(
                        value=V,
                        uncertainty=U,
                        method=method,
                        details={
                            "reference_column": _reference_label(headers, ref_idx),
                            **accel_result.metadata,
                        },
                    )
                elif method == "custom":
                    formula = (opts.custom_formula or "").strip()
                    if not formula:
                        raise ValueError("未提供自定义公式。")
                    value = _evaluate_custom_formula(formula, headers, row_tuple, warnings=opts.warnings)
                    V = _mp(value)
                    ref_idx = min(reference_index, len(row_tuple) - 1)
                    if use_auto_max_diff:
                        chosen = _auto_reference_index_max_diff(row_tuple, V)
                        if chosen is None:
                            _append_option_warning(
                                opts,
                                _dual_msg(
                                    "最大差异列：无法自动选择参考列，已回退到默认参考列。",
                                    "Max-diff column: unable to auto-select a reference column; fell back to the default reference column.",
                                ),
                                verbose,
                            )
                            ref_idx = min(fallback_reference_index, len(row_tuple) - 1)
                        else:
                            ref_idx = chosen
                    reference_value = row_tuple[ref_idx]
                    U = mp.fabs(V - reference_value)
                    result_entry = ExtrapolationResult(
                        value=V,
                        uncertainty=U,
                        method="custom",
                        details={
                            "reference_column": _reference_label(headers, ref_idx),
                            "formula": formula,
                        },
                    )
                else:
                    a_val, b_val, c_val = method_values[:3]
                    V, U = compute_extrapolation_decimal(a_val, b_val, c_val)
                    result_entry = ExtrapolationResult(value=V, uncertainty=U, method="quadratic")
            except (PowerLawComputationError, SequenceAccelerationError) as exc:
                if verbose:
                    print("Warning: Cannot extrapolate line {0}: {1}".format(line_num, exc))
                continue

            data_rows.append(row_tuple)
            extrapolated_results.append(result_entry)

            if verbose:
                column_states = ", ".join(
                    f"{_reference_label(headers, idx)}={row_tuple[idx]}" for idx in range(len(row_tuple))
                )
                if method == "power_law":
                    print(
                        "Row {0}: {1} -> E_inf={2}, Δ={3}, p={4}".format(
                            line_num - 1,
                            column_states,
                            V,
                            U,
                            result_entry.details.get("exponent"),
                        )
                    )
                elif method in ACCELERATOR_METHODS:
                    print(
                        "Row {0}: {1} -> {2} limit={3}, Δ={4}".format(
                            line_num - 1,
                            column_states,
                            method,
                            V,
                            U,
                        )
                    )
                else:
                    print(
                        "Row {0}: {1} -> V={2}, U={3}".format(line_num - 1, column_states, V, U)
                    )

        if verbose:
            print("Successfully processed {0} data rows".format(len(data_rows)))

        return headers, data_rows, extrapolated_results


def process_data_file(
    filename: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[
    list[str],
    list[tuple[mp.mpf, ...]],
    list[ExtrapolationResult | tuple[mp.mpf, mp.mpf]],
]:
    """Process a data file and perform extrapolation on each row."""
    with open(filename, "r") as f:
        lines = f.readlines()
    return _process_data_lines(lines, verbose, options=options)


def process_data_string(
    content: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[
    list[str],
    list[tuple[mp.mpf, ...]],
    list[ExtrapolationResult | tuple[mp.mpf, mp.mpf]],
]:
    """Process an in-memory string and perform extrapolation on each row."""
    if not content or not content.strip():
        raise ValueError("输入数据为空，无法解析。")
    return _process_data_lines(content.splitlines(), verbose, options=options)


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
    headers: list[str],
    data_rows: list[tuple[mp.mpf, ...]],
    extrapolated_results: list[ExtrapolationResult | tuple[mp.mpf, mp.mpf]],
    output_filename: str,
    caption: str | None = None,
    precision: int | None = None,
    verbose: bool = False,
    use_dcolumn: bool = False,
    table_segments: list[tuple[int, int]] | None = None,
    result_uncertainty_digits: int | None = None,
    latex_group_size: int = 3,
) -> None:
    """Generate a LaTeX table with the data and extrapolation results."""
    latex_content: list[str] = []

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
        )
    )

    header_cells = [
        "\\multicolumn{{1}}{{c}}{{{0}}}".format(headers[idx] if idx < len(headers) else f"列{idx + 1}")
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

