from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from mpmath import mp

from datalab_latex.latex_formatting import (
    calculate_dcolumn_format_for_column,
    format_value_for_latex_file,
    siunitx_column_spec,
)
from datalab_latex.sisetup_block import build_sisetup_block


def write_root_latex(
    *,
    output_path: str,
    rows: Sequence[Mapping[str, object]],
    caption: str | None = None,
    digits: int = 16,
    group_size: int = 3,
    include_dcolumn: bool = False,
    language: str = "zh",
) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_root_latex_document(
            rows=rows,
            caption=caption,
            digits=digits,
            group_size=group_size,
            include_dcolumn=include_dcolumn,
            language=language,
        ),
        encoding="utf-8",
    )
    return path


def build_root_latex_document(
    *,
    rows: Sequence[Mapping[str, object]],
    caption: str | None = None,
    digits: int = 16,
    group_size: int = 3,
    include_dcolumn: bool = False,
    language: str = "zh",
) -> str:
    lines = [
        "\\documentclass{article}",
        "\\usepackage[UTF8]{ctex}" if language == "zh" else "",
        "\\usepackage{booktabs}",
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
            language=language,
            include_dcolumn=include_dcolumn,
        )
    )
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def _root_table(
    rows: Sequence[Mapping[str, object]],
    *,
    digits: int,
    language: str,
    include_dcolumn: bool,
) -> list[str]:
    headers = _headers(language)
    value_cells = [
        _number_with_uncertainty(row.get("value", ""), row.get("uncertainty", ""), digits=digits, include_dcolumn=False)
        for row in rows
    ]
    value_spec = calculate_dcolumn_format_for_column(value_cells, "root_value") if rows and include_dcolumn else "l"
    if rows and not include_dcolumn:
        value_spec = siunitx_column_spec(value_cells)
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\begin{{tabular}}{{lll{value_spec}ll}}",
        "\\toprule",
        " & ".join(_escape_latex(header) for header in headers) + r" \\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    _escape_latex(_text(row.get("input_row_index", ""))),
                    _escape_latex(_text(row.get("root_index", ""))),
                    _escape_latex(_text(row.get("name", ""))),
                    _number_with_uncertainty(
                        row.get("value", ""),
                        row.get("uncertainty", ""),
                        digits=digits,
                        include_dcolumn=include_dcolumn,
                    ),
                    _escape_latex(_text(row.get("backend", ""))),
                    _escape_latex(_text(row.get("mode", ""))),
                ]
            )
            + r" \\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return lines


def _headers(language: str) -> list[str]:
    if language == "en":
        return ["Input row", "Root", "Name", "Value", "Backend", "Mode"]
    return ["输入行", "根序号", "名称", "值", "后端", "模式"]


def _number_with_uncertainty(value: object, uncertainty: object, *, digits: int, include_dcolumn: bool) -> str:
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
            uncertainty_digits=3,
            zero_uncertainty_mantissa_decimals=max(1, digits - 1),
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
