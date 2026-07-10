from __future__ import annotations

from collections.abc import Mapping

from shared.latex_escaping import latex_escape as _canonical_latex_escape
from shared.error_propagation_engine import (
    apply_formula_to_data,
    detect_used_error_propagation_inputs,
    error_propagation,
)
from shared.uncertainty import UncertainValue, parse_uncertainty_format

from .expression_engine import format_latex_formula
from .latex_formatting import (
    _format_value_for_latex_file,
    _siunitx_column_spec,
    calculate_dcolumn_format_for_column,
    group_digits_both_sides,
)
from .latex_tables_common import (
    _build_standalone_preamble,
    _estimate_page_geometry,
    _needs_cjk_support,
    _normalize_input_lines,
    _normalize_numeric_token,
    _normalize_table_segments,
    _string_length_hint,
)


def _process_uncertainty_lines(
    lines: list[str], verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    lines = _normalize_input_lines(lines)
    if len(lines) < 2:
        raise ValueError("Input must contain at least a header and one data row")

    header_line = lines[0].strip()
    headers = header_line.split()

    if verbose:
        print("Found headers: {0}".format(headers))
        print("Processing {0} data rows...".format(len(lines) - 1))

    parsed_data: list[list[UncertainValue]] = []

    for line_num, raw_line in enumerate(lines[1:], 2):
        line = raw_line.strip()
        if not line:
            continue

        values = [_normalize_numeric_token(part) for part in line.split()]
        row_data: list[UncertainValue] = []
        for value_str in values:
            try:
                if "(" in value_str or "[" in value_str:
                    uncertain_value = parse_uncertainty_format(value_str)
                else:
                    uncertain_value = UncertainValue(value_str, "0")
                row_data.append(uncertain_value)
            except Exception as e:
                message = f"Cannot parse value '{value_str}' on line {line_num}: {e}"
                if verbose:
                    print(f"Warning: {message}")
                raise ValueError(message) from e

        if row_data:
            parsed_data.append(row_data)
            if verbose:
                print(f"Row {line_num - 1}: Parsed {len(row_data)} values")

    if verbose:
        print("Successfully processed {0} data rows".format(len(parsed_data)))

    return headers, parsed_data


def process_uncertainty_data_file(
    filename: str, verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    """Process a data file containing values with uncertainties in the format 1.23(1)[-2]."""
    with open(filename, "r") as f:
        lines = f.readlines()
    return _process_uncertainty_lines(lines, verbose)


def process_uncertainty_string(
    content: str, verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    """Process an in-memory string that follows the same format as the uncertainty data file."""
    if not content or not content.strip():
        raise ValueError("输入数据为空，无法解析。")
    return _process_uncertainty_lines(content.splitlines(), verbose)


def _process_constants_lines(
    lines: list[str], verbose: bool = False
) -> dict[str, UncertainValue]:
    constants: dict[str, UncertainValue] = {}
    for line_num, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            if verbose:
                print(f"Warning: Invalid format on line {line_num}: {line}")
            continue

        const_name, value_str = parts
        try:
            uncertain_value = parse_uncertainty_format(value_str)
            constants[const_name] = uncertain_value
            if verbose:
                print(f"Loaded constant {const_name}: {uncertain_value}")
        except Exception as e:
            if verbose:
                print(f"Warning: Cannot parse constant '{const_name}' on line {line_num}: {e}")
            continue
    return constants


def process_constants_file(filename: str, verbose: bool = False) -> dict[str, UncertainValue]:
    """Process a constants file containing constant values with uncertainties."""
    try:
        with open(filename, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        if verbose:
            print(f"Constants file '{filename}' not found, proceeding without constants")
        return {}
    return _process_constants_lines(lines, verbose)


def process_constants_string(content: str, verbose: bool = False) -> dict[str, UncertainValue]:
    """Process constants supplied via a string buffer."""
    if not content or not content.strip():
        return {}
    return _process_constants_lines(content.splitlines(), verbose)



def _error_table_row_strings(
    headers: list[str],  # noqa: ARG001 - retained for backward compatibility
    formatted_columns: list[list[str]],
    formatted_result_column: list[str],
    start_row: int,
    end_row: int,
) -> list[str]:
    num_cols = len(formatted_columns)
    rows = []
    for local_index, row_index in enumerate(range(start_row, end_row), 1):
        cells = [str(local_index)]
        for col_idx in range(num_cols):
            cells.append(formatted_columns[col_idx][row_index])
        cells.append(formatted_result_column[row_index])
        rows.append("\t\t\t" + " & ".join(cells) + " \\\\")
    return rows


def _escape_latex_text(value: object) -> str:
    # Delegates to the single canonical implementation (P2-6).
    return _canonical_latex_escape(value)


def _header_label_latex(label: str) -> str:
    text = str(label)
    if len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        return text
    return text.replace("$", "")


def _header_with_unit(label: str, unit: str | None) -> str:
    clean_label = _header_label_latex(label)
    unit_text = str(unit or "").strip()
    if not unit_text:
        return clean_label
    return f"{clean_label}~[\\texttt{{{_escape_latex_text(unit_text)}}}]"


def generate_error_propagation_table(
    headers: list[str],
    parsed_data: list[list[UncertainValue]],
    results: list[UncertainValue],
    constants: dict[str, UncertainValue],
    formula_str: str,
    output_filename: str,
    caption: str | None = None,
    verbose: bool = False,
    use_dcolumn: bool = False,
    table_segments: list[tuple[int, int]] | None = None,
    precision: int | None = None,
    result_uncertainty_digits: int | None = None,
    used_columns: list[str] | None = None,
    latex_group_size: int = 3,
    input_units: Mapping[str, str] | None = None,
    result_unit: str | None = None,
    native_group_width: bool = True,
) -> None:
    """Generate a LaTeX table for error propagation results."""
    # App-side grouping when the engine can't vary the siunitx group WIDTH (non-native) and
    # grouping is on in siunitx (non-dcolumn) mode: pre-group each numeric cell + use plain r
    # columns instead of S columns siunitx would re-group at a fixed 3.
    _group = max(0, int(latex_group_size))
    app_group = (not native_group_width) and (not use_dcolumn) and _group > 0
    if used_columns is None:
        header_indices = list(range(len(headers)))
    else:
        used_set = {name.lower().strip() for name in used_columns if name}
        header_indices = [idx for idx, name in enumerate(headers) if name.lower().strip() in used_set]
        if not header_indices and used_set:
            header_indices = list(range(len(headers)))

    column_lengths = [len(str(max(1, len(parsed_data)))) + 1]
    for idx in header_indices:
        header = headers[idx]
        column_lengths.append(max(4, _string_length_hint(header)))
    column_lengths.append(6)
    formatted_columns: list[list[str]] = [[] for _ in header_indices]
    formatted_result_column: list[str] = []
    for _, (row_data, result) in enumerate(zip(parsed_data, results), 1):
        for out_idx, src_idx in enumerate(header_indices):
            uncertain_value = row_data[src_idx]
            unc_digits = getattr(uncertain_value, "uncertainty_digits", None)
            formatted_value = _format_value_for_latex_file(
                value=uncertain_value.value,
                sigma=uncertain_value.uncertainty,
                use_dcolumn=use_dcolumn,
                latex_input_decimals=precision if precision is not None else None,
                is_input=True,
                latex_group_size=latex_group_size,
                uncertainty_digits=unc_digits,
            )
            formatted_columns[out_idx].append(formatted_value)
            column_lengths[1 + out_idx] = max(column_lengths[1 + out_idx], _string_length_hint(formatted_value))
        result_formatted = _format_value_for_latex_file(
            value=result.value,
            sigma=result.uncertainty,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=precision if precision is not None else None,
            is_input=False,
            latex_group_size=latex_group_size,
            uncertainty_digits=result_uncertainty_digits,
        )
        formatted_result_column.append(result_formatted)
        column_lengths[-1] = max(column_lengths[-1], _string_length_hint(result_formatted))
    if app_group:
        def _wrap(cell: str) -> str:
            # A non-finite value renders as a \multicolumn literal cell; wrapping it
            # in \text{...} is invalid TeX ("Misplaced \omit") — pass it through.
            if "\\multicolumn" in cell:
                return cell
            return "\\text{" + group_digits_both_sides(cell, _group) + "}"
        formatted_columns = [[_wrap(c) for c in col] for col in formatted_columns]
        formatted_result_column = [_wrap(c) for c in formatted_result_column]
    page_w, _ = _estimate_page_geometry(column_lengths, len(parsed_data) + 6)
    cjk_segments = [
        caption if caption else "",
        " ".join(headers),
        " ".join((input_units or {}).values()),
        str(result_unit or ""),
        formula_str or "",
    ]
    if constants:
        cjk_segments.append(" ".join(constants.keys()))
    needs_cjk = _needs_cjk_support(*cjk_segments)
    latex_content = _build_standalone_preamble(
        page_w,
        include_dcolumn=use_dcolumn,
        needs_cjk=needs_cjk,
        latex_group_size=latex_group_size,
        native_group_width=native_group_width,
    )

    header_cols = ["$n$"]
    for src_idx in header_indices:
        h = headers[src_idx]
        unit = (input_units or {}).get(h)
        header_cols.append(f"\\multicolumn{{1}}{{c}}{{{_header_with_unit(h, unit)}}}")
    header_cols.append(f"\\multicolumn{{1}}{{c}}{{{_header_with_unit('Result', result_unit)}}}")
    header_row = "\t\t\t" + " & ".join(header_cols) + " \\\\"

    segments = _normalize_table_segments(len(parsed_data), table_segments)
    for block_index, (start_row, end_row) in enumerate(segments, 1):
        if use_dcolumn:
            data_formats = [
                calculate_dcolumn_format_for_column(
                    col_data[start_row:end_row],
                    f"data_col_{i}",
                )
                for i, col_data in enumerate(formatted_columns)
            ]
            result_format = calculate_dcolumn_format_for_column(
                formatted_result_column[start_row:end_row],
                "result_col",
            )
            table_format = "c " + " ".join(data_formats) + " " + result_format
        elif app_group:
            # Cells are pre-grouped + wrapped in \text{}; plain right-aligned columns.
            table_format = "c " + " ".join(["r"] * len(formatted_columns)) + " r"
        else:
            data_formats = [_siunitx_column_spec(col_data[start_row:end_row]) for col_data in formatted_columns]
            result_format = _siunitx_column_spec(formatted_result_column[start_row:end_row])
            table_format = "c " + " ".join(data_formats) + " " + result_format
        if verbose:
            print(f"LaTeX table formats (block {block_index}/{len(segments)}): {table_format}")

        latex_content.extend(
            [
                "\\begin{table}[!ht]",
                "\t\\centering",
                "\t\\caption{{{0}}}\\label{{tab:error_propagation_{1}}}".format(
                    # Escape the user-supplied caption so LaTeX specials
                    # (_ % & # $) don't break compilation (audit F14); the
                    # fallback is already-formatted LaTeX, so leave it verbatim.
                    _escape_latex_text(caption)
                    if caption
                    else "Error propagation results using formula: $" + format_latex_formula(formula_str) + "$",
                    block_index,
                ),
                "\t\\begin{threeparttable}",
                "\t\t\\begin{{tabular}}{{{0}}}".format(table_format),
                "\t\t\t\\toprule",
                header_row,
                "\t\t\t\\midrule",
            ]
        )

        latex_content.extend(
            _error_table_row_strings(
                headers,
                formatted_columns,
                formatted_result_column,
                start_row,
                end_row,
            )
        )

        latex_content.extend(
            [
                "\t\t\t\\bottomrule",
                "\t\t\\end{tabular}",
                "\t\t\\begin{tablenotes}",
                "\t\t\t\\footnotesize",
                "\t\t\t\\item Formula used: $" + format_latex_formula(formula_str) + "$",
            ]
        )

        if constants:
            latex_content.append("\t\t\t\\item Constants used:")
            for const_name, const_value in constants.items():
                const_unc_digits = getattr(const_value, "uncertainty_digits", None)
                const_formatted = _format_value_for_latex_file(
                    value=const_value.value,
                    sigma=const_value.uncertainty,
                    use_dcolumn=use_dcolumn,
                    latex_input_decimals=precision if precision is not None else None,
                    is_input=True,
                    latex_group_size=latex_group_size,
                    uncertainty_digits=const_unc_digits,
                )
                latex_content.append(f"\t\t\t\\item ${const_name} = {const_formatted}$")

        latex_content.extend(
            [
                "\t\t\\end{tablenotes}",
                "\t\\end{threeparttable}",
                "\\end{table}",
                "",
            ]
        )

    latex_content.append("\\end{document}")

    with open(output_filename, "w") as f:
        f.write("\n".join(latex_content))

    if verbose:
        format_type = "dcolumn format with number spacing" if use_dcolumn else "regular format with spacing"
        print("Error propagation LaTeX table ({0}) written to: {1}".format(format_type, output_filename))
        print("Total rows: {0}".format(len(parsed_data)))



__all__ = [
    "UncertainValue",
    "apply_formula_to_data",
    "detect_used_error_propagation_inputs",
    "error_propagation",
    "generate_error_propagation_table",
    "parse_uncertainty_format",
    "process_constants_file",
    "process_constants_string",
    "process_uncertainty_data_file",
    "process_uncertainty_string",
]
