from __future__ import annotations

from collections.abc import Mapping, Sequence


def build_report_bundle_latex_report(*, sections: Sequence[Mapping[str, str]], title: str = "DataLab Report Bundle") -> str:
    """Build a small standalone LaTeX report for a DataLab report bundle."""

    lines = [
        r"\documentclass{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{booktabs}",
        r"\usepackage{hyperref}",
        r"\begin{document}",
        rf"\section*{{{_latex_text(title)}}}",
        r"\begin{itemize}",
    ]
    for section in sections:
        section_id = str(section.get("id") or "")
        label = str(section.get("label") or section_id)
        family = str(section.get("family") or "")
        kind = str(section.get("kind") or "")
        lines.append(
            rf"\item {_latex_text(label)} ({_latex_text(family)} / {_latex_text(kind)}): "
            rf"\texttt{{{_latex_text(section_id)}}}"
        )
    lines.extend([r"\end{itemize}", ""])
    for section in sections:
        section_id = str(section.get("id") or "")
        if section_id:
            lines.append(rf"\input{{sections/{_latex_input_name(section_id)}.tex}}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def build_report_bundle_latex_section(section: Mapping[str, str]) -> str:
    section_id = str(section.get("id") or "")
    label = str(section.get("label") or section_id)
    family = str(section.get("family") or "")
    kind = str(section.get("kind") or "")
    created_at = str(section.get("created_at") or "")
    table_path = str(section.get("table_path") or "")
    snapshot_path = str(section.get("snapshot_path") or "")

    lines = [
        rf"\section*{{{_latex_text(label)}}}",
        r"\begin{tabular}{ll}",
        r"\toprule",
        rf"ID & \texttt{{{_latex_text(section_id)}}} \\",
        rf"Family & {_latex_text(family)} \\",
        rf"Kind & {_latex_text(kind)} \\",
        rf"Created & {_latex_text(created_at)} \\",
        rf"Snapshot & \texttt{{{_latex_text(snapshot_path)}}} \\",
    ]
    if table_path:
        lines.append(rf"CSV table & \texttt{{{_latex_text(table_path)}}} \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def _latex_input_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-_") or "section"


def _latex_text(value: str) -> str:
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


__all__ = ["build_report_bundle_latex_report", "build_report_bundle_latex_section"]
