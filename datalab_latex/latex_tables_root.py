from __future__ import annotations

from collections.abc import Mapping, Sequence

from mpmath import mp

from datalab_latex.latex_formatting import (
    calculate_dcolumn_format_for_column,
    format_value_for_latex_file,
    siunitx_column_spec,
)
from datalab_latex.sisetup_block import build_sisetup_block


def build_root_latex_document(
    *,
    rows: Sequence[Mapping[str, object]],
    caption: str | None = None,
    digits: int = 16,
    uncertainty_digits: int = 1,
    group_size: int = 3,
    include_dcolumn: bool = False,
    language: str = "zh",
    root_units: Mapping[str, str] | None = None,
) -> str:
    lines = [
        "\\documentclass{article}",
        "\\usepackage[UTF8]{ctex}" if language == "zh" else "",
        "\\usepackage{booktabs}",
        "\\usepackage{dcolumn}" if include_dcolumn else "",
        "\\newcolumntype{d}[1]{D{.}{.}{#1}}" if include_dcolumn else "",
        "\\usepackage{siunitx}",
        build_sisetup_block(group_size=group_size, include_dcolumn=include_dcolumn).rstrip(),
        "\\begin{document}",
    ]
    lines = [line for line in lines if line]
    if caption:
        lines.append(f"\\section*{{{_escape_latex(caption)}}}")
    lines.extend(
        _root_table(
            rows,
            digits=max(1, int(digits)),
            uncertainty_digits=max(1, int(uncertainty_digits)),
            group_size=max(0, int(group_size)),
            language=language,
            include_dcolumn=include_dcolumn,
            root_units=root_units,
        )
    )
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def _root_table(
    rows: Sequence[Mapping[str, object]],
    *,
    digits: int,
    uncertainty_digits: int,
    group_size: int,
    language: str,
    include_dcolumn: bool,
    root_units: Mapping[str, str] | None,
) -> list[str]:
    include_unit_column = bool(root_units)
    include_failure_column = any(_text(row.get("failure", "")).strip() for row in rows)
    headers = _headers(
        language,
        include_unit_column=include_unit_column,
        include_failure_column=include_failure_column,
    )
    value_cells = [
        _number_with_uncertainty(
            row.get("value", ""),
            row.get("uncertainty", ""),
            digits=digits,
            uncertainty_digits=uncertainty_digits,
            group_size=group_size,
            include_dcolumn=False,
        )
        for row in rows
    ]
    value_spec = calculate_dcolumn_format_for_column(value_cells, "root_value") if rows and include_dcolumn else "l"
    if rows and not include_dcolumn:
        value_spec = siunitx_column_spec(value_cells)
    header_cells = [_escape_latex(header) for header in headers]
    value_header_index = 4 if include_unit_column else 3
    header_cells[value_header_index] = "\\multicolumn{1}{c}{" + header_cells[value_header_index] + "}"
    leading_spec = "llll" if include_unit_column else "lll"
    trailing_spec = "lll" if include_failure_column else "ll"
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\begin{{tabular}}{{{leading_spec}{value_spec}{trailing_spec}}}",
        "\\toprule",
        " & ".join(header_cells) + r" \\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    _escape_latex(_text(row.get("input_row_index", ""))),
                    _escape_latex(_text(row.get("root_index", ""))),
                    _escape_latex(_text(row.get("name", ""))),
                    *(
                        [_escape_latex(_root_unit_for_row(row, root_units))]
                        if include_unit_column
                        else []
                    ),
                    _number_with_uncertainty(
                        row.get("value", ""),
                        row.get("uncertainty", ""),
                        digits=digits,
                        uncertainty_digits=uncertainty_digits,
                        group_size=group_size,
                        include_dcolumn=include_dcolumn,
                    ),
                    _escape_latex(_text(row.get("backend", ""))),
                    _escape_latex(_text(row.get("mode", ""))),
                    *(
                        [_escape_latex(_text(row.get("failure", "")))]
                        if include_failure_column
                        else []
                    ),
                ]
            )
            + r" \\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return lines


def _headers(
    language: str,
    *,
    include_unit_column: bool = False,
    include_failure_column: bool = False,
) -> list[str]:
    if language == "en":
        headers = ["Input row", "Root", "Name", "Value", "Backend", "Mode"]
        if include_unit_column:
            headers.insert(3, "Unit")
        if include_failure_column:
            headers.append("Failure")
        return headers
    headers = ["输入行", "根序号", "名称", "值", "后端", "模式"]
    if include_unit_column:
        headers.insert(3, "单位")
    if include_failure_column:
        headers.append("失败原因")
    return headers


def _root_unit_for_row(row: Mapping[str, object], root_units: Mapping[str, str] | None) -> str:
    if not root_units:
        return ""
    return str(root_units.get(_text(row.get("name", "")), "") or "")


def _number_with_uncertainty(
    value: object,
    uncertainty: object,
    *,
    digits: int,
    uncertainty_digits: int,
    group_size: int,
    include_dcolumn: bool,
) -> str:
    text = _text(value)
    if not text:
        return ""
    sigma_text = _text(uncertainty).strip()
    try:
        sigma = mp.mpf(sigma_text) if sigma_text else None
        return format_value_for_latex_file(
            mp.mpf(text),
            sigma,
            use_dcolumn=include_dcolumn,
            latex_input_decimals=None,
            is_input=False,
            uncertainty_digits=uncertainty_digits,
            zero_uncertainty_mantissa_decimals=max(1, digits - 1),
            latex_group_size=group_size,
        )
    except Exception:
        return _escape_latex(text)


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _escape_latex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)
