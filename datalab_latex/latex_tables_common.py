from __future__ import annotations

import re

from .sisetup_block import build_sisetup_block


def _normalize_input_lines(lines: list[str]) -> list[str]:
    """Strip trailing whitespace and leading blank lines."""
    trimmed = [line.rstrip() for line in lines]
    start = 0
    while start < len(trimmed) and not trimmed[start].strip():
        start += 1
    return trimmed[start:]


UNICODE_MINUS_SIGNS = {
    "\u2212",  # minus sign
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\uFF0D",  # fullwidth hyphen minus
    "\u2010",  # hyphen
    "\uFE58",  # small em dash
    "\uFE63",  # small hyphen-minus
    "\u2012",  # figure dash
}
UNICODE_PLUS_SIGNS = {
    "\uFF0B",  # fullwidth plus
    "\uFE62",  # small plus
}


def _normalize_numeric_token(token: str) -> str:
    """Replace Unicode minus/plus characters with ASCII equivalents."""
    result = token.strip()
    for ch in UNICODE_MINUS_SIGNS:
        result = result.replace(ch, "-")
    for ch in UNICODE_PLUS_SIGNS:
        result = result.replace(ch, "+")
    return result


def _string_length_hint(text: str | None) -> int:
    if not text:
        return 0
    cleaned = str(text)
    cleaned = cleaned.replace("\\,", "").replace(" ", "")
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = cleaned.replace("[", "").replace("]", "")
    return max(1, len(cleaned))


def _estimate_page_geometry(column_lengths: list[int], num_rows: int) -> tuple[float, float]:
    total_chars = sum(max(length, 4) for length in column_lengths) + 6
    width = min(max(8.0, 0.6 + total_chars * 0.085), 18.0)
    base_height = 0.8 + (num_rows + 3) * 0.19
    height = min(max(9.0, base_height), 13.5)
    return width, height


_CJK_CHAR_PATTERN = re.compile(
    r"[\u3040-\u30FF\u31F0-\u31FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF66-\uFF9F\uFF00-\uFFEF]"
)


def _contains_cjk_characters(text: str | None) -> bool:
    """Return True if the text contains CJK characters."""
    if not text:
        return False
    return bool(_CJK_CHAR_PATTERN.search(str(text)))


def _needs_cjk_support(*segments: str) -> bool:
    """Check a collection of text fragments for any CJK characters."""
    for segment in segments:
        if _contains_cjk_characters(segment):
            return True
    return False


def _build_standalone_preamble(
    width_in: float,
    *,
    include_dcolumn: bool = False,
    needs_cjk: bool = False,
    latex_group_size: int = 3,
) -> list[str]:
    """Return a minimal standalone LaTeX preamble tuned for fast compilation.

    Args:
        latex_group_size: Group size for grouping digits (0 = no grouping)
    """
    group_size = max(0, int(latex_group_size))
    doc_class = "\\documentclass[varwidth={0:.2f}in,border=12pt]{{standalone}}".format(width_in)
    preamble = [doc_class]
    if needs_cjk:
        preamble.extend(
            [
                "\\usepackage{fontspec}",
                "\\usepackage{xeCJK}",
            ]
        )
    else:
        preamble.append("\\usepackage[utf8]{inputenc}")

    preamble.extend(
        [
            "\\usepackage{amsmath}",
            "\\usepackage{array}",
            "\\usepackage{booktabs}",
            "\\usepackage{threeparttable}",
        ]
    )

    if include_dcolumn:
        preamble.append("\\usepackage{dcolumn}")
    preamble.append("\\usepackage{siunitx}")

    preamble.append("")

    if include_dcolumn:
        preamble.extend(
            [
                "% Configure dcolumn for decimal point alignment",
                "\\newcolumntype{d}[1]{D{.}{.}{#1}}",
                "",
            ]
        )

    # Centralized v2/v3-compatible \sisetup{...} body. The helper emits
    # a guard around the siunitx-v3-only ``digit-group-size`` key so
    # documents still compile against older TeX Live distributions where
    # siunitx v2 is the default. (Was 5 near-duplicate inline copies
    # before — removing them all keeps the format drift-free.)
    preamble.append(
        build_sisetup_block(
            group_size=group_size,
            include_dcolumn=include_dcolumn,
        ).rstrip("\n")
    )
    preamble.append("")

    preamble.extend(
        [
            "\\begin{document}",
            "",
            "\\centering",
        ]
    )

    return preamble


def _normalize_table_segments(total_rows: int, table_segments: list[tuple[int, int]] | None) -> list[tuple[int, int]]:
    if total_rows <= 0:
        return []
    if not table_segments:
        return [(0, total_rows)]
    normalized: list[tuple[int, int]] = []
    last_end = 0
    ordered = sorted(table_segments, key=lambda pair: pair[0])
    for start, end in ordered:
        start = max(0, min(start, total_rows))
        end = max(start, min(end, total_rows))
        if start != last_end or end <= start:
            return [(0, total_rows)]
        normalized.append((start, end))
        last_end = end
    if normalized[-1][1] != total_rows:
        return [(0, total_rows)]
    return normalized


def _normalize_header_to_symbol(header: str, index: int) -> str:
    """Convert a column header to a safe Python identifier, ensuring uniqueness."""
    base = re.sub(r"[^0-9A-Za-z_]", "_", header.strip()) or f"col_{index+1}"
    if base[0].isdigit():
        base = f"c_{base}"
    base = base.strip("_") or f"col_{index+1}"
    return base


def _apply_aliases(formula: str, alias_map: dict[str, str]) -> str:
    """Replace alias tokens (e.g., x1) with canonical variable names."""
    result = formula
    # replace longer aliases first to avoid partial overlaps
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        target = alias_map[alias]
        pattern = r"\b" + re.escape(alias) + r"\b"
        result = re.sub(pattern, target, result)
    return result
