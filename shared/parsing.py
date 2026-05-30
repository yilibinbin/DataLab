"""Shared text-parsing primitives used across DataLab.

Two families of helpers live here so neither the desktop GUI nor the
LaTeX export layer has to reach across module boundaries for a purely
syntactic parser:

1. **Clipboard-tabular parser** — ``parse_clipboard_tabular`` handles
   data pasted from Excel / Numbers / Origin / Matlab across locales:

   - US: ``1,234.56`` (comma thousands, dot decimal)
   - EU: ``1.234,56`` (dot thousands, comma decimal)
   - Scientific: ``1.5e-3`` / ``2.5E+4``
   - Matlab: spaces, semicolons, ragged columns
   - Numbers.app / Office on Windows: NBSP around cells

   Returns a ``ParseResult`` with headers and rows. Non-numeric cells
   come back as ``None`` rather than being dropped — callers decide
   whether to surface or skip them. ``MAX_CLIPBOARD_CHARS`` caps input
   size so an accidental multi-gigabyte paste cannot freeze the UI.

2. **Name/value tokenizer** — ``parse_name_value_pairs`` is the shared
   ``# comment`` / blank-line tolerant splitter used by the constants
   text view, the error-propagation parser, and any future feature that
   wants the same "one ``name value`` per line" syntax.

This module is import-safe from headless contexts; it has no Qt
dependency so the web front-end can run the same logic via pyodide or
via a parallel JS port.
"""

from __future__ import annotations

import csv as _csv
import enum
import io as _io
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

__all__ = [
    "LocaleHint",
    "MAX_CLIPBOARD_CHARS",
    "ParseResult",
    "parse_clipboard_tabular",
    "parse_name_value_pairs",
]


# 2 MB cap on clipboard text. A scientific CSV with 100k rows × 4 cols
# × 10 chars/cell ≈ 4 MB, so 2 MB is cautious; if a workflow legitimately
# needs more, the raw CSV import path is a better fit than copy-paste.
MAX_CLIPBOARD_CHARS = 2_000_000

# Hard caps on the output grid. A whitespace-delimited 2 MB paste could
# produce ~1 M columns; Qt would block for seconds setting that many
# header items. 4 096 columns × 100 000 rows keeps the UI responsive
# even for the pathological clipboard contents a user might accidentally
# paste (e.g., dumping a memoized array repr).
MAX_ROWS = 100_000
MAX_COLS = 4_096

# Bidi / zero-width format characters that could visually spoof a header
# ("ABC" displayed as "CBA" via U+202E) without affecting numeric parsing.
# Stripped on every cell. Kept as a module-level compiled pattern so the
# per-cell loop doesn't pay per-call compilation cost.
_BIDI_CONTROL_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]"
)

# Pre-compiled locale-sniffing regexes. Compiling at import keeps the
# 2 MB full-text scan from paying re-compilation overhead every paste.
_RE_EU_THOUSANDS_DECIMAL = re.compile(r"\d\.\d{3},\d")
_RE_COMMA_DIGIT = re.compile(r"\d,\d")
_RE_DOT_DECIMAL = re.compile(r"\d\.\d")
_RE_BARE_COMMA_DECIMAL = re.compile(r"\d,\d(?:\d)?(?!\d)")
_RE_THOUSANDS_COMMA = re.compile(r"\d,\d{3}(?:[.,]|\D|$)")
_RE_SCIENTIFIC = re.compile(r"^([+-]?[\d.,]+)([eE][+-]?\d+)$")
_RE_DOT_TRIPLES_ONLY = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})+")
_RE_COMMA_DECIMAL_1_2 = re.compile(r",\d{1,2}(?:$|[^\d])")
_RE_COMMA_TRIPLES = re.compile(r",\d{3}(?:[.,]|$|[^\d])")


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
    raw_rows: list[list[str]] = field(default_factory=list)


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
    """Collapse all unicode/ASCII whitespace from cell edges AND remove
    bidi / zero-width format chars from anywhere in the cell.

    The bidi strip defends against visually-deceptive header spoofing
    (``&#x202E;ABC`` would render as ``CBA`` in the Qt header without
    distinguishing the hijacked-order column from a legitimate one).
    Numeric cells with embedded zero-width chars would already fail
    ``_NUMERIC_RE``, so the strip here also protects header display
    fidelity."""
    without_bidi = _BIDI_CONTROL_RE.sub("", cell)
    return without_bidi.strip().strip(_UNICODE_SPACES).strip()


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
    return bool(_RE_COMMA_DIGIT.search(text))


def _sniff_locale(text: str) -> LocaleHint:
    """Pick US vs EU based on the overall paste content.

    EU signals (first matching rule wins):
    - ``1.234,56``-style dot-triples-then-comma-decimal (unambiguous
      German CSV).
    - Semicolon delimiter + bare comma-decimal pattern anywhere and no
      dot-between-digits. Semicolon is the canonical EU CSV delimiter
      so its presence resolves the ``1,234`` ambiguity (3 digits after
      comma) toward the EU reading.
    - Bare ``1,X`` with 1 or 2 digits after the comma, no US
      thousands-comma pattern (``1,234`` with exactly 3 digits) and
      no dot-between-digits. 1-2 digit suffix locks in "this is a
      decimal", not thousands.

    Default: US. A file with mixed scientific notation (``1.5e-3``)
    and EU decimals cannot be unambiguously classified — the caller
    should pass an explicit ``locale`` argument in that case.
    """
    # Sniffing cost is bounded: we sample at most 50k chars. Locale is
    # consistent across a file, so a prefix is representative.
    sample = text[:50_000]
    # "1.234,56" — dot-triples followed by comma-decimal is unambiguous
    if _RE_EU_THOUSANDS_DECIMAL.search(sample):
        return LocaleHint.EU

    has_comma_digits = _RE_COMMA_DIGIT.search(sample) is not None
    has_dot_decimal = _RE_DOT_DECIMAL.search(sample) is not None
    # A dot-triples pattern (``1.234``) could be EU thousands OR a
    # US decimal with 3 fractional digits. It resolves to EU only when
    # accompanied by bare-comma evidence. We use the ``\d\.\d{3}(?!\d)``
    # form so ``1.2345`` (4+ fractional digits — clearly a US decimal)
    # doesn't count.
    has_dot_triples = re.search(r"\d\.\d{3}(?!\d)", sample) is not None

    # Bare comma-decimal 1-2 digits after comma. Distinguishes from
    # thousands commas (exactly 3 digits after).
    has_bare_decimal = _RE_BARE_COMMA_DECIMAL.search(sample) is not None
    has_thousands_comma = _RE_THOUSANDS_COMMA.search(sample) is not None

    # Semicolon + any comma-decimal digit run → EU. The semicolon
    # delimiter is the tiebreaker for the 1,234 ambiguity.
    if ";" in sample and has_comma_digits and not has_dot_decimal:
        return LocaleHint.EU

    # Mixed EU evidence: bare-comma-decimal AND dot-triples-pattern
    # (i.e., "1,5\t1.234" style) — treat as EU thousands + EU decimal.
    # The bare-comma constraint (1-2 digits, not 3) rules out the
    # US-looking "1,234" thousands pattern.
    if has_bare_decimal and not has_thousands_comma and has_dot_triples:
        return LocaleHint.EU

    # Bare "1,5" (1-2 digits after comma) without thousands-comma or
    # dot-decimal elsewhere.
    if has_bare_decimal and not has_thousands_comma and not has_dot_decimal:
        return LocaleHint.EU
    return LocaleHint.US


def _parse_numeric(cell: str, locale: LocaleHint) -> Optional[float]:
    """Convert one cell to a float or return None on failure.

    ``locale`` must be resolved before calling — ``LocaleHint.AUTO``
    is treated as ``US`` (the ``AUTO`` branch exists at the public
    ``parse_clipboard_tabular`` boundary only). Passing ``AUTO`` to
    this private helper is a programming error that the ``US``
    fallback masks; callers outside this module should route through
    ``parse_clipboard_tabular``.

    Scientific notation (``1.5e-3``, ``2.5E+4``) is detected and
    protected before locale transformation — otherwise EU-mode's
    "remove dots" pass would corrupt ``1.5e-3`` into ``15e-3`` (a
    factor-of-100 silent data-corruption bug, HIGH finding from
    code-reviewer).

    Under EU rules, a cell with ONE dot is treated per the dot-triples
    heuristic: if the text looks like ``1.234`` (dot followed by
    exactly 3 digits with no comma), it's a thousands separator
    (strip dot). Otherwise the dot is a US-bleed-through decimal and
    we keep it — this preserves ``1.5e-3`` as scientific notation
    even under EU mode.
    """
    s = _strip_whitespace(cell)
    if not s:
        return None

    # Split off the exponent if present. Mantissa gets locale
    # transformation; exponent is always ASCII digits + optional sign.
    m = _RE_SCIENTIFIC.match(s)
    if m:
        mantissa, exponent = m.group(1), m.group(2)
    else:
        mantissa, exponent = s, ""

    if locale == LocaleHint.EU:
        if "," in mantissa:
            # EU decimal comma present: strip dot-thousands then swap
            # comma for decimal. "1.234,56" → "1234.56".
            candidate = mantissa.replace(".", "").replace(",", ".") + exponent
        elif _RE_DOT_TRIPLES_ONLY.fullmatch(mantissa):
            # Dot-triples-only "1.234.567" is a thousands-separated
            # integer: strip dots. "1.234" → "1234".
            candidate = mantissa.replace(".", "") + exponent
        else:
            # Lone dot looks like a US-bleed-through decimal
            # ("1.5", "1.5e-3" mantissa). Keep as-is so EU mode
            # doesn't corrupt scientific notation.
            candidate = mantissa + exponent
    else:  # US or AUTO falling back to US
        # Remove comma thousands separators only if they look like
        # thousands (comma followed by exactly 3 digits). A lone
        # comma-decimal ("1,5") is EU bleed-through under US mode —
        # documented tradeoff: callers with EU-formatted data should
        # pass locale=LocaleHint.EU.
        if _RE_COMMA_DECIMAL_1_2.search(mantissa) and not _RE_COMMA_TRIPLES.search(
            mantissa
        ):
            # Looks like decimal-comma, not thousands — keep.
            candidate = mantissa + exponent
        else:
            candidate = mantissa.replace(",", "") + exponent

    if not _NUMERIC_RE.match(candidate.replace(" ", "")):
        # Pre-reject non-numeric patterns so exponent-like typos don't
        # produce inf or spurious conversions. Also rejects ``Infinity``,
        # ``inf``, ``NaN``, ``#NUM!``, ``#DIV/0!`` etc. — a scientific
        # user pasting Excel error cells gets ``None`` back, not a
        # numeric sentinel.
        return None
    try:
        value = float(candidate)
    except (TypeError, ValueError):
        return None
    # Defense-in-depth: ``float("1e999")`` returns inf; the regex
    # shouldn't allow that but be explicit.
    import math

    if math.isinf(value) or math.isnan(value):
        return None
    return value


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
    has_headers: Optional[bool] = None,
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
    has_headers:
        ``None`` (default) uses the first-row-non-numeric heuristic.
        Pass ``True`` / ``False`` when the caller knows the shape —
        e.g., when data has a first-column label like ``"controlA"``
        followed by numeric columns, the heuristic would mis-detect
        row 0 as headers. Callers with authoritative knowledge (a
        toolbar toggle, a file format hint) should pass the override.
    """
    if not text:
        return ParseResult()

    # Truncate before any further work so a pathological paste can't
    # hang the UI or allocate gigabytes of intermediate strings.
    # Cut at the last full newline so we don't leave a half-parsed
    # trailing row (Codex-found HIGH: truncation mid-cell could turn
    # "3\t456\t7" into "3\t45" → [3.0, 45.0], silently wrong-valued).
    if len(text) > MAX_CLIPBOARD_CHARS:
        text = text[:MAX_CLIPBOARD_CHARS]
        last_newline = text.rfind("\n")
        if last_newline > 0:
            text = text[:last_newline]

    # Strip UTF-8 BOM emitted by Excel / LibreOffice Calc — otherwise
    # the first header cell becomes ``"\ufeffx"`` which fails string
    # comparison against ``"x"`` in downstream consumers (e.g., the
    # expression engine matching column names to formula variables).
    if text and text[0] == "\ufeff":
        text = text.lstrip("\ufeff")

    text = _normalise_line_endings(text)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return ParseResult()
    # Hard cap on line count — prevents a million-row paste from
    # bottoming out Qt's row allocation path.
    if len(lines) > MAX_ROWS:
        lines = lines[:MAX_ROWS]

    # Resolve locale up front — individual row parsers must agree.
    effective_locale = locale if locale != LocaleHint.AUTO else _sniff_locale(text)

    delim = _detect_delimiter(lines[0])
    rows_raw = [_split_row(ln, delim) for ln in lines]
    if not rows_raw:
        return ParseResult()

    # Pad ragged rows to the max column count so downstream consumers
    # (the manual-input table) see a rectangular grid — missing cells
    # become ``None``. Cap at MAX_COLS so a pathological paste
    # (a 2 MB blob of space-separated numbers on one line) can't
    # create a million-column Qt grid that locks the UI for seconds.
    max_cols = max(len(r) for r in rows_raw)
    if max_cols > MAX_COLS:
        rows_raw = [r[:MAX_COLS] for r in rows_raw]
        max_cols = MAX_COLS
    rows_padded = [r + [""] * (max_cols - len(r)) for r in rows_raw]

    # Header detection: first row is a header unless every cell parses
    # as a number (in which case it's all-data with synthetic headers).
    # The caller can override via ``has_headers`` to force the right
    # behaviour for ambiguous layouts (e.g., row-label data with a
    # string first column and no header row).
    if has_headers is None:
        has_headers = not _row_is_all_numeric(rows_padded[0], effective_locale)
    if not has_headers:
        headers = _synthetic_headers(max_cols)
        data_rows_raw = [[_strip_whitespace(cell) for cell in row] for row in rows_padded]
    else:
        headers = [_strip_whitespace(c) or synth
                   for c, synth in zip(rows_padded[0], _synthetic_headers(max_cols))]
        data_rows_raw = [[_strip_whitespace(cell) for cell in row] for row in rows_padded[1:]]

    # Parse every data cell.
    data_rows: list[list[Optional[float]]] = []
    for raw_row in data_rows_raw:
        parsed_row: list[Optional[float]] = []
        for cell in raw_row:
            parsed_row.append(_parse_numeric(cell, effective_locale))
        data_rows.append(parsed_row)

    return ParseResult(headers=headers, rows=data_rows, raw_rows=data_rows_raw)


def parse_name_value_pairs(text_or_lines: str | Iterable[str]) -> list[tuple[str, str]]:
    """Split a free-form constants text block into ``(name, value)`` tuples.

    Rules, shared by every caller:

    - Lines are ``.strip()``-ed before inspection.
    - Blank lines are skipped.
    - Lines beginning with ``#`` are treated as comments and skipped.
    - Each remaining line is split on whitespace once (``split(None, 1)``);
      the first token becomes the name, the remainder becomes the value.
    - Lines that do not split into exactly two tokens are silently dropped
      here — it is the caller's responsibility to warn the user if that
      matters (``_process_constants_lines`` does, with ``verbose=True``).

    Accepts either a single ``str`` (which is ``splitlines()``-ed) or any
    iterable of line strings, so callers that already hold a ``list`` of
    lines (``file.readlines()``) don't pay for a re-join.
    """
    if isinstance(text_or_lines, str):
        lines: Iterable[str] = text_or_lines.splitlines()
    else:
        lines = text_or_lines

    pairs: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs
