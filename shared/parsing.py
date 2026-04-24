"""Clipboard-tabular-data parser for DataLab's manual-input table.

Real users copy from Excel / Numbers / Origin / Matlab and expect the
manual-input table to "just work" across locales:

- US: ``1,234.56`` (comma thousands, dot decimal)
- EU: ``1.234,56`` (dot thousands, comma decimal)
- Scientific: ``1.5e-3`` / ``2.5E+4``
- Matlab: spaces, semicolons, ragged columns
- Numbers.app / Office on Windows: NBSP around cells

``parse_clipboard_tabular`` returns a ``ParseResult`` with headers and
rows. Non-numeric cells come back as ``None`` rather than being dropped
— callers decide whether to surface or skip them.

Hard limits:
- ``MAX_CLIPBOARD_CHARS`` caps input size to prevent an accidental
  multi-gigabyte paste from freezing the UI.

This module is import-safe from headless contexts; it has no Qt
dependency so the web front-end (Phase 2 Task 2.2 sub-task) can run
the same logic via pyodide or via a parallel JS port.
"""

from __future__ import annotations

import csv as _csv
import enum
import io as _io
import re
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "LocaleHint",
    "MAX_CLIPBOARD_CHARS",
    "ParseResult",
    "parse_clipboard_tabular",
]


# 2 MB cap on clipboard text. A scientific CSV with 100k rows × 4 cols
# × 10 chars/cell ≈ 4 MB, so 2 MB is cautious; if a workflow legitimately
# needs more, the raw CSV import path is a better fit than copy-paste.
MAX_CLIPBOARD_CHARS = 2_000_000


class LocaleHint(enum.Enum):
    """Which number-format convention to apply.

    - ``AUTO``: sniff from the data (default for paste flows).
    - ``US``: comma=thousand, dot=decimal.
    - ``EU``: dot=thousand, comma=decimal.
    """

    AUTO = "auto"
    US = "us"
    EU = "eu"


@dataclass
class ParseResult:
    headers: list[str] = field(default_factory=list)
    rows: list[list[Optional[float]]] = field(default_factory=list)


# Unicode whitespace that Office/Numbers embed around cells. We strip
# all of these before numeric conversion.
_UNICODE_SPACES = "\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"

_NUMERIC_RE = re.compile(
    r"""^
    [+-]?                    # optional sign
    (?:\d+(?:[.,]\d+)?       # integer part with optional decimal
       |\.\d+                # or pure decimal .5
    )
    (?:[eE][+-]?\d+)?        # optional exponent
    $""",
    re.VERBOSE,
)


def _strip_whitespace(cell: str) -> str:
    """Collapse all unicode/ASCII whitespace from cell edges."""
    return cell.strip().strip(_UNICODE_SPACES).strip()


def _normalise_line_endings(text: str) -> str:
    """Convert \\r\\n and bare \\r into plain \\n."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _detect_delimiter(first_line: str) -> str:
    """Pick the delimiter for a row. Priority: tab > semicolon > comma >
    whitespace. Tab is canonical for cross-app paste."""
    if "\t" in first_line:
        return "\t"
    if ";" in first_line:
        return ";"
    # Comma is ambiguous — might be a decimal comma in EU locale. If
    # the line has both comma and any digits touching a comma, prefer
    # whitespace (then the row-wise parser picks the decimal properly).
    if "," in first_line and not _looks_like_eu_decimal(first_line):
        return ","
    return "WS"  # sentinel for whitespace.split()


def _looks_like_eu_decimal(text: str) -> bool:
    """Heuristic: if ``,`` appears between digits with NO dot anywhere
    in the line, it's probably an EU decimal separator."""
    if "," not in text:
        return False
    if "." in text:
        # Mixed — decide elsewhere with _sniff_locale.
        return False
    return bool(re.search(r"\d,\d", text))


def _sniff_locale(text: str) -> LocaleHint:
    """Pick US vs EU based on the overall paste content.

    Rules (in priority order):
    - If semicolon delimiter is present and commas appear between
      digits, it's EU (classic German CSV).
    - If any ``1.234,56``-style pattern is present, it's EU.
    - Default: US.
    """
    if ";" in text and re.search(r"\d,\d", text):
        return LocaleHint.EU
    # "1.234,56" — dot followed by 3 digits followed by comma followed by decimals
    if re.search(r"\d\.\d{3},\d", text):
        return LocaleHint.EU
    # Bare "1,5" with no dots anywhere in any digit run
    if re.search(r"\d,\d", text) and not re.search(r"\d\.\d", text):
        return LocaleHint.EU
    return LocaleHint.US


def _parse_numeric(cell: str, locale: LocaleHint) -> Optional[float]:
    """Convert one cell to a float or return None on failure."""
    s = _strip_whitespace(cell)
    if not s:
        return None

    if locale == LocaleHint.EU:
        # Remove dot thousands separators, swap comma for decimal.
        # "1.234,56" → "1234.56"; "1,5" → "1.5"; "1.234" → "1234".
        # Careful: a lone "." in EU is a thousands mark so "1.234" → 1234.
        # But "1.5" (US bleed-through) — we treat it as "15" under EU
        # rules, which is wrong but deterministic. Callers who paste
        # a mixed file should pass locale=LocaleHint.US or AUTO.
        candidate = s.replace(".", "").replace(",", ".")
    else:  # US or AUTO falling back to US
        # Remove comma thousands separators.
        # "1,234.56" → "1234.56". "1,5" → "15" (wrong but US).
        candidate = s.replace(",", "")

    if not _NUMERIC_RE.match(candidate.replace(" ", "")):
        # Pre-reject non-numeric patterns so exponent-like typos don't
        # produce inf or spurious conversions.
        return None
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def _split_row(row_text: str, delimiter: str) -> list[str]:
    """Split one row by the detected delimiter.

    Whitespace-delimited rows need special handling — ``str.split()``
    collapses consecutive spaces, which is what Matlab users expect.
    Other delimiters use ``csv.reader`` for proper quote handling.
    """
    if delimiter == "WS":
        return row_text.split()
    if delimiter in ("\t", ";"):
        return row_text.split(delimiter)
    # comma: use csv.reader for quoted-cell support
    reader = _csv.reader(_io.StringIO(row_text), delimiter=delimiter)
    try:
        return next(reader, row_text.split(delimiter))
    except _csv.Error:
        return row_text.split(delimiter)


def _row_is_all_numeric(row: list[str], locale: LocaleHint) -> bool:
    """Decide whether a row looks like data (all cells parse as float)
    or a header (at least one non-numeric cell)."""
    parsed = [_parse_numeric(cell, locale) for cell in row]
    return all(v is not None for v in parsed) and bool(parsed)


def _synthetic_headers(n: int) -> list[str]:
    """Excel-style placeholders ``A, B, C, …, Z, AA, AB, …`` for
    header-less input."""
    out = []
    for i in range(n):
        name = ""
        idx = i
        while True:
            name = chr(ord("A") + (idx % 26)) + name
            idx = idx // 26 - 1
            if idx < 0:
                break
        out.append(name)
    return out


def parse_clipboard_tabular(
    text: str,
    locale: LocaleHint = LocaleHint.AUTO,
) -> ParseResult:
    """Parse a chunk of clipboard text into a headers + rows result.

    The return is always a fully-resolved ``ParseResult`` — failures
    degrade to empty lists or ``None`` cells rather than raising.

    Parameters
    ----------
    text:
        Clipboard string. Line endings are normalised; trimmed to
        ``MAX_CLIPBOARD_CHARS``.
    locale:
        ``LocaleHint.AUTO`` sniffs from the data; ``US``/``EU`` force
        a specific convention.
    """
    if not text:
        return ParseResult()

    # Truncate before any further work so a pathological paste can't
    # hang the UI or allocate gigabytes of intermediate strings.
    if len(text) > MAX_CLIPBOARD_CHARS:
        text = text[:MAX_CLIPBOARD_CHARS]

    text = _normalise_line_endings(text)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return ParseResult()

    # Resolve locale up front — individual row parsers must agree.
    effective_locale = locale if locale != LocaleHint.AUTO else _sniff_locale(text)

    delim = _detect_delimiter(lines[0])
    rows_raw = [_split_row(ln, delim) for ln in lines]
    if not rows_raw:
        return ParseResult()

    # Pad ragged rows to the max column count so downstream consumers
    # (the manual-input table) see a rectangular grid — missing cells
    # become ``None``.
    max_cols = max(len(r) for r in rows_raw)
    rows_padded = [r + [""] * (max_cols - len(r)) for r in rows_raw]

    # Header detection: first row is a header unless every cell parses
    # as a number (in which case it's all-data with synthetic headers).
    first_is_numeric = _row_is_all_numeric(rows_padded[0], effective_locale)
    if first_is_numeric:
        headers = _synthetic_headers(max_cols)
        data_rows_raw = rows_padded
    else:
        headers = [_strip_whitespace(c) or synth
                   for c, synth in zip(rows_padded[0], _synthetic_headers(max_cols))]
        data_rows_raw = rows_padded[1:]

    # Parse every data cell.
    data_rows: list[list[Optional[float]]] = []
    for raw_row in data_rows_raw:
        parsed_row: list[Optional[float]] = []
        for cell in raw_row:
            parsed_row.append(_parse_numeric(cell, effective_locale))
        data_rows.append(parsed_row)

    return ParseResult(headers=headers, rows=data_rows)
