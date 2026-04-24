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

import pytest

from shared.parsing import (
    LocaleHint,
    parse_clipboard_tabular,
)


def test_simple_tab_separated_two_columns():
    text = "x\ty\n1\t10\n2\t20\n3\t30"
    result = parse_clipboard_tabular(text)
    assert result.headers == ["x", "y"]
    assert result.rows == [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]


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
