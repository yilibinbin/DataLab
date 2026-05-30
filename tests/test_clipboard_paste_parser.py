"""Excel-compatible clipboard paste parser — regression tests.

``shared.parsing.parse_clipboard_tabular`` turns a blob of clipboard
text into a list of rows suitable for the manual-data table. Real
scientific users paste out of Excel / Origin / Matlab and expect the
table to understand their locale conventions — US ``1,234.56``,
European ``1.234,56``, Matlab semicolon rows, mixed whitespace, and
so on.

These tests pin the contract for the DataLab desktop's ``_TablePasteFilter``
and the (future) Web-side mirror ``app_web/static/js/paste_parser.js``.
"""

from __future__ import annotations

from shared.parsing import (
    LocaleHint,
    parse_clipboard_tabular,
)


def test_simple_tab_separated_two_columns():
    text = "x\ty\n1\t10\n2\t20\n3\t30"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["x", "y"]
    assert result.rows == [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]


def test_parse_clipboard_tabular_preserves_raw_uncertainty_tokens() -> None:
    result = parse_clipboard_tabular("A B\n4 -0.01161947382(2)\n5 -0.01182004861(4)")

    assert result.headers == ["A", "B"]
    assert result.raw_rows == [
        ["4", "-0.01161947382(2)"],
        ["5", "-0.01182004861(4)"],
    ]
    assert result.rows[0][0] == 4.0
    assert result.rows[0][1] is None


def test_parse_clipboard_tabular_raw_rows_strip_bidi_controls() -> None:
    result = parse_clipboard_tabular("A B\n4 \u202e-0.01161947382(2)\u200b")

    assert result.raw_rows == [["4", "-0.01161947382(2)"]]
    assert result.rows[0][1] is None


def test_comma_separated_us_locale():
    text = "x,y\n1.5,10.25\n2.5,20.75"
    result = parse_clipboard_tabular(text, locale=LocaleHint.US)
    assert result.rows == [[1.5, 10.25], [2.5, 20.75]]


def test_thousand_separators_us_locale():
    """US Excel exports '1,234.56' — comma is a thousands separator."""
    text = "value\n1,234.56\n2,345.67"
    result = parse_clipboard_tabular(text, locale=LocaleHint.US)
    assert result.rows == [[1234.56], [2345.67]]


def test_european_decimal_comma():
    """EU Excel exports '1,5' meaning 1.5."""
    text = "x;y\n1,5;2,75\n3,25;4,125"
    result = parse_clipboard_tabular(text, locale=LocaleHint.EU)
    assert result.rows == [[1.5, 2.75], [3.25, 4.125]]


def test_european_thousand_dot():
    """EU Excel exports '1.234,56' meaning 1234.56."""
    text = "value\n1.234,56\n2.345,67"
    result = parse_clipboard_tabular(text, locale=LocaleHint.EU)
    assert result.rows == [[1234.56], [2345.67]]


def test_scientific_notation():
    text = "k\n1.5e-3\n2.5E+4"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["k"]
    assert result.rows == [[1.5e-3], [2.5e4]]


def test_mixed_whitespace_delimited():
    """Matlab/Octave style: multiple spaces, ragged columns."""
    text = "  1.0    2.0 \n 3.0    4.0"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.0, 2.0], [3.0, 4.0]]


def test_leading_trailing_blank_lines_ignored():
    text = "\n\n1\t2\n3\t4\n\n"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.0, 2.0], [3.0, 4.0]]


def test_header_detection_first_row_non_numeric():
    """First row containing any non-numeric cell → headers."""
    text = "time\tvalue\n0.0\t1.0\n1.0\t2.0"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["time", "value"]
    assert result.rows == [[0.0, 1.0], [1.0, 2.0]]


def test_header_absent_all_numeric_first_row():
    """First row purely numeric → treated as data, synthetic headers."""
    text = "1.0\t2.0\n3.0\t4.0"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["A", "B"]
    assert result.rows == [[1.0, 2.0], [3.0, 4.0]]


def test_cell_with_spaces_around_value():
    text = "  x  \t  y  \n  1.0  \t  2.0  "
    result = parse_clipboard_tabular(text)
    assert result.headers == ["x", "y"]
    assert result.rows == [[1.0, 2.0]]


def test_quoted_csv_cells():
    text = '"name","value"\n"a",1.5\n"b",2.5'
    result = parse_clipboard_tabular(text, locale=LocaleHint.US)
    # "name" / "a" / "b" are non-numeric, so the value column is the only
    # numeric one. Parser still returns rows and leaves non-numeric cells
    # as None (or marks the column non-numeric entirely — pin the contract).
    assert result.headers == ["name", "value"]
    # Non-numeric cells surface as None
    assert result.rows[0][1] == 1.5
    assert result.rows[0][0] is None


def test_empty_cells_preserved_as_none():
    """Missing values in the middle of a row must not shift downstream columns."""
    text = "x\ty\tz\n1\t\t3\n4\t5\t"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.0, None, 3.0], [4.0, 5.0, None]]


def test_ragged_rows_padded_with_none():
    text = "x\ty\tz\n1\t2\n3\t4\t5"
    result = parse_clipboard_tabular(text)
    assert result.rows[0] == [1.0, 2.0, None]
    assert result.rows[1] == [3.0, 4.0, 5.0]


def test_negative_and_positive_signed():
    text = "x\n-1.5\n+2.5\n0"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[-1.5], [2.5], [0.0]]


def test_empty_input_returns_empty_result():
    for empty in ["", "   ", "\n\n\n"]:
        result = parse_clipboard_tabular(empty)
        assert result.headers == []
        assert result.rows == []


def test_garbage_input_does_not_raise():
    """A paste of binary-ish garbage must degrade gracefully."""
    text = "\x00\x01this is not tabular data\x02\x03"
    # Must not raise.
    result = parse_clipboard_tabular(text)
    # The "rows" may be a single row of one non-numeric string — just
    # confirm the function completed.
    assert isinstance(result.rows, list)


def test_locale_autodetection_picks_us_for_dot_decimal():
    """When locale is LocaleHint.AUTO (default), the parser sniffs:
    '1.5' with no comma → US; '1,5' with no dot → EU."""
    text_us = "1.5\n2.5"
    text_eu = "1,5\n2,5"
    assert parse_clipboard_tabular(text_us).rows == [[1.5], [2.5]]
    assert parse_clipboard_tabular(text_eu).rows == [[1.5], [2.5]]


def test_locale_autodetection_prefers_us_for_mixed():
    """A file with both '.' and ',' is ambiguous; pick US to match
    the overwhelming majority of scientific CSV exports."""
    text = "1.5\t1,234.56\n2.5\t2,345.67"
    result = parse_clipboard_tabular(text)
    assert result.rows[0] == [1.5, 1234.56]
    assert result.rows[1] == [2.5, 2345.67]


def test_semicolon_delimiter_eu_style():
    """EU CSV conventionally uses ';' so ',' can be the decimal
    separator. Parser must detect semicolon and parse accordingly."""
    text = "x;y\n1,5;2,75\n3,25;4,125"
    # Even without explicit locale, sniffing should pick EU because
    # semicolon + comma-decimal is unambiguous.
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.5, 2.75], [3.25, 4.125]]


def test_unicode_whitespace_handled():
    """Some apps (Numbers.app, Office on Windows) insert NBSP or
    other unicode whitespace around cells. Parser must treat them
    as plain whitespace."""
    text = "x\ty\n\u00a01.0\u00a0\t\u00a02.0\u00a0"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.0, 2.0]]


def test_dos_line_endings_handled():
    text = "x\ty\r\n1\t2\r\n3\t4\r\n"
    result = parse_clipboard_tabular(text)
    assert result.rows == [[1.0, 2.0], [3.0, 4.0]]


def test_eu_locale_preserves_scientific_notation():
    """HIGH regression: EU mode must NOT corrupt "1.5e-3" by stripping
    the dot. Scientific notation is exponent-delimited and the mantissa
    must be transformed independently."""
    text = "k;val\n1,5;1.5e-3\n2,5;2.5e-4"
    result = parse_clipboard_tabular(text, locale=LocaleHint.EU)
    # First column: EU-style 1,5 → 1.5. Second: scientific 1.5e-3
    # must be preserved, not corrupted to 15e-3 (=0.015).
    assert result.rows == [[1.5, 1.5e-3], [2.5, 2.5e-4]]


def test_has_headers_override_for_row_labels():
    """HIGH regression: when data has a string first column (row
    labels) and no header row, the first-row-non-numeric heuristic
    misfires. Caller override ``has_headers=False`` forces the
    correct parse."""
    text = "controlA\t1.5\t2.3\ncontrolB\t3.5\t4.3"
    result = parse_clipboard_tabular(text, has_headers=False)
    assert result.rows == [
        [None, 1.5, 2.3],   # "controlA" is non-numeric → None
        [None, 3.5, 4.3],
    ]
    # Default behaviour (no override) still treats row 0 as headers —
    # that's the documented heuristic and callers with row-labels must
    # opt out explicitly.
    default = parse_clipboard_tabular(text)
    assert len(default.rows) == 1  # only row 1 as data


def test_has_headers_true_forces_header_row():
    """Symmetric override — numeric first row treated as headers."""
    text = "1\t2\n3\t4\n5\t6"
    result = parse_clipboard_tabular(text, has_headers=True)
    assert result.headers == ["1", "2"]
    assert result.rows == [[3.0, 4.0], [5.0, 6.0]]


def test_infinity_nan_excel_errors_return_none():
    """Excel error cells and Python-style float specials must return
    None — the parser must never emit math.inf or math.nan into the
    downstream float pipeline."""
    text = "x\nInfinity\ninf\n-inf\nNaN\n#NUM!\n#DIV/0!"
    result = parse_clipboard_tabular(text)
    for row in result.rows:
        assert row[0] is None, f"got {row[0]} for disallowed sentinel"


def test_sniff_locale_ambiguous_us_semicolon_needs_explicit_locale():
    """Documented limitation: semicolon-delimited data with 3-digit
    fractional parts (``1,234``) is genuinely ambiguous — could be EU
    decimal (1.234) or US thousands (1234). The sniffer prefers EU
    because ``;`` is the canonical EU CSV delimiter. Callers with
    US-format data must pass ``locale=LocaleHint.US`` explicitly.
    This test pins the ambiguity resolution so a future sniffer
    change is visible."""
    text = "val;count\n1234;1,234\n5678;5,678"
    result_auto = parse_clipboard_tabular(text)
    # AUTO → EU interpretation
    assert result_auto.rows[0][1] == 1.234, (
        "Documented semicolon-wins behaviour: "
        f"expected EU 1.234, got {result_auto.rows[0][1]}"
    )
    # US override gives the alternative reading
    result_us = parse_clipboard_tabular(text, locale=LocaleHint.US)
    assert result_us.rows[0][1] == 1234.0


def test_synthetic_headers_rolls_over_past_26_cols():
    """HIGH regression: panels.py's old ``chr(65 + i)`` would produce
    ``[`` as column 27's name. Confirm the shared parser uses proper
    Excel-style AA rollover."""
    from shared.parsing import _synthetic_headers

    names = _synthetic_headers(30)
    assert names[0] == "A"
    assert names[25] == "Z"
    assert names[26] == "AA"
    assert names[27] == "AB"
    assert names[29] == "AD"
    # None of them should be ASCII punctuation
    assert all(n.isalpha() for n in names)


def test_bom_stripped_from_first_cell():
    """UTF-8 BOM from Excel exports must not survive into header cells."""
    text = "\ufeffx\ty\n1\t2"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["x", "y"]
    assert "\ufeff" not in result.headers[0]


def test_bidi_control_chars_stripped_from_cells():
    """A header like '\u202ESTUFF' visually reads as 'FFUTS' — strip
    the bidi override so spoofed headers don't deceive the user."""
    text = "\u202esalt\tpeppa\n1\t2"
    result = parse_clipboard_tabular(text)
    assert "\u202e" not in result.headers[0]
    assert result.headers[0] == "salt"


def test_max_rows_cap():
    """A paste with a million rows must be truncated at MAX_ROWS."""
    from shared.parsing import MAX_ROWS

    lines = ["1\t2"] * (MAX_ROWS + 1000)
    text = "\n".join(lines)
    result = parse_clipboard_tabular(text)
    assert len(result.rows) <= MAX_ROWS


def test_max_cols_cap():
    """A single-row paste of millions of whitespace-separated values
    must not create a million-column grid."""
    from shared.parsing import MAX_COLS

    text = " ".join(["1"] * (MAX_COLS + 500))
    result = parse_clipboard_tabular(text)
    # First row is treated as headers (all numeric → synthetic);
    # the test only needs to assert the column count doesn't exceed
    # the cap.
    assert len(result.headers) <= MAX_COLS


def test_mixed_eu_bare_comma_plus_dot_triples_sniffs_eu():
    """Codex HIGH regression: '1,5\\t1.234' (bare comma-decimal + a
    dot-triples pattern) must sniff EU — otherwise the dot-triples
    disqualifies the bare-comma rule and US-fallback corrupts '1,5'
    into 15.0."""
    text = "1,5\t1.234\n2,5\t2.345"
    result = parse_clipboard_tabular(text)
    # EU parse: 1,5 → 1.5; 1.234 (dot-triples) → 1234.0
    assert result.rows == [[1.5, 1234.0], [2.5, 2345.0]], (
        f"Mixed EU data must sniff EU. Got: {result.rows}"
    )


def test_mid_row_truncation_drops_incomplete_tail():
    """Codex HIGH regression: cutting at MAX_CLIPBOARD_CHARS mid-cell
    must not leave a numerically-valid-but-wrong trailing row. The
    parser truncates to the last full newline after the cut."""
    from shared.parsing import MAX_CLIPBOARD_CHARS

    # Build a payload that forces the cap to cut inside a row. The
    # header + full good rows fill MAX_CLIPBOARD_CHARS exactly, then
    # we append a row whose first cell is plausibly-numeric but whose
    # second cell would get truncated mid-digits.
    good_row = "1\t2\n"  # 4 bytes
    header = "a\tb\n"    # 4 bytes
    n_good = (MAX_CLIPBOARD_CHARS - len(header)) // len(good_row) + 10
    base = header + good_row * n_good
    # Trailing "3\t456789" is incomplete (no \n). Its mid-cell cut
    # would give e.g. "3\t45" which parses as [3.0, 45.0] — wrong.
    broken_tail = "3\t456789"
    text = base + broken_tail
    assert len(text) > MAX_CLIPBOARD_CHARS, (
        f"Test setup error: text {len(text)} must exceed cap "
        f"{MAX_CLIPBOARD_CHARS}"
    )
    result = parse_clipboard_tabular(text)
    # Every remaining row must match the good-row template. A mid-row
    # truncation would produce a [3.0, 45.0] (or similar) row.
    for row in result.rows:
        assert row == [1.0, 2.0], (
            f"Truncated paste produced unexpected row {row}; "
            "mid-cell truncation must be dropped, not silently parsed."
        )


def test_very_large_input_size_capped():
    """An enormous paste (> ~10 MB) should be truncated rather than
    allocate unbounded memory. Pin the contract — a production user
    rarely pastes > 100k rows."""
    from shared.parsing import MAX_CLIPBOARD_CHARS

    # 100k rows × 4 cols × ~10 chars/cell ≈ 4 MB; above that we expect
    # the parser to refuse or truncate.
    assert MAX_CLIPBOARD_CHARS >= 1_000_000
    text = "1\t2\n" * (MAX_CLIPBOARD_CHARS // 4 + 1000)
    # Must not hang / OOM; must not raise.
    result = parse_clipboard_tabular(text)
    assert isinstance(result.rows, list)
    assert len(result.rows) > 0
