from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from mpmath import mp

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
    lines.extend(_root_table(rows, digits=max(1, int(digits)), language=language))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def _root_table(rows: Sequence[Mapping[str, object]], *, digits: int, language: str) -> list[str]:
    headers = _headers(language)
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\begin{tabular}{lllllll}",
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
                    _number(row.get("value", ""), digits=digits),
                    _number(row.get("uncertainty", ""), digits=digits),
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
        return ["Input row", "Root", "Name", "Value", "Uncertainty", "Backend", "Mode"]
    return ["输入行", "根序号", "名称", "值", "不确定度", "后端", "模式"]


def _number(value: object, *, digits: int) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        return _escape_latex(mp.nstr(mp.mpf(text), n=digits))
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
