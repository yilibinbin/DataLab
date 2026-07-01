from __future__ import annotations

import pytest

from shared.input_normalization import (
    normalize_constants_state,
    parse_constants_text,
    parse_input_sections,
)


def test_parse_input_sections_data_only() -> None:
    text = """
A B C
1 2 3
4 5 6
"""
    sections = parse_input_sections(text)
    assert not sections.explicit_sections
    assert sections.constants_text == ""
    assert "A B C" in sections.data_text
    assert "4 5 6" in sections.data_text


def test_parse_input_sections_both() -> None:
    text = """
[data]
A B
1 2

[constants]
ALPHA 3.5
BETA = 4.2
"""
    sections = parse_input_sections(text)
    assert sections.explicit_sections
    assert "A B\n1 2" in sections.data_text
    assert "ALPHA 3.5\nBETA = 4.2" in sections.constants_text


def test_parse_input_sections_case_insensitive_and_comments() -> None:
    text = """
# comment
[DATA]
A B
1 2

# another comment
[Constants]
ALPHA = 3.5
"""
    sections = parse_input_sections(text)
    assert sections.explicit_sections
    assert "A B\n1 2" in sections.data_text
    assert "ALPHA = 3.5" in sections.constants_text


def test_parse_input_sections_explicit_sections_preserve_leading_data_lines() -> None:
    text = "# pre-section comment\n\n[data]\nA B\n\n[constants]\nK 1\n"

    sections = parse_input_sections(text)

    assert sections.explicit_sections
    assert sections.data_text == "# pre-section comment\n\nA B\n"
    assert sections.constants_text == "K 1"


def test_parse_input_sections_duplicate_data_header_raises_with_line_number() -> None:
    text = """
[data]
A B
[data]
C D
"""
    with pytest.raises(ValueError) as exc_info:
        parse_input_sections(text)
    message = str(exc_info.value)
    assert "第 4 行" in message
    assert "Line 4" in message
    assert "重复的 [data]" in message
    assert "Duplicate [data]" in message


def test_parse_input_sections_duplicate_constants_header_raises_with_line_number() -> None:
    text = """
[constants]
K 1
[Constants]
R 2
"""
    with pytest.raises(ValueError) as exc_info:
        parse_input_sections(text)
    message = str(exc_info.value)
    assert "第 4 行" in message
    assert "Line 4" in message
    assert "重复的 [constants]" in message
    assert "Duplicate [constants]" in message


def test_parse_input_sections_duplicate_header_raises_across_sections() -> None:
    text = """
[data]
A B
[constants]
K 1
[DATA]
C D
"""
    with pytest.raises(ValueError, match="Line 6.*Duplicate \\[data\\]"):
        parse_input_sections(text)


def test_parse_input_sections_unknown_header_is_legacy_data_without_sections() -> None:
    text = """
[unknown]
some text
[+9]
"""
    sections = parse_input_sections(text)
    assert not sections.explicit_sections
    assert sections.constants_text == ""
    assert "[unknown]" in sections.data_text
    assert "[+9]" in sections.data_text


def test_parse_input_sections_unknown_header_raises_in_explicit_mode() -> None:
    text = """
[data]
A B
[unknown]
1 2
"""
    with pytest.raises(ValueError) as exc_info:
        parse_input_sections(text)
    message = str(exc_info.value)
    assert "第 4 行" in message
    assert "Line 4" in message
    assert "未知的段定义 [unknown]" in message
    assert "Unknown section header [unknown]" in message


def test_parse_input_sections_unknown_header_raises_before_later_section() -> None:
    text = """
[metadata]
legacy note
[data]
A B
"""
    with pytest.raises(ValueError, match="Line 2"):
        parse_input_sections(text)


def test_parse_input_sections_legacy_bracket_uncertainty_lines_remain_data() -> None:
    text = """
Value
1.000(12)[0]
[+9]
[-3]
"""
    sections = parse_input_sections(text)
    assert not sections.explicit_sections
    assert sections.data_text.strip() == "Value\n1.000(12)[0]\n[+9]\n[-3]"
    assert sections.constants_text == ""


def test_parse_constants_text_accepts_space_and_equals_forms() -> None:
    assert parse_constants_text("ALPHA 3.5\nBETA = 4.2") == [
        {"name": "ALPHA", "value": "3.5"},
        {"name": "BETA", "value": "4.2"},
    ]


def test_constants_state_content_driven_validation() -> None:
    # 1. Empty constants is allowed and returns {}
    state = normalize_constants_state(enabled=False, view="table", rows=[])
    assert state.compute_dict(validate=True) == {}

    # 2. Non-empty complete rows returns constants even if enabled=False
    state = normalize_constants_state(
        enabled=False,
        view="table",
        rows=[{"name": "ALPHA", "value": "1.23(4)"}],
    )
    assert state.compute_dict(validate=True) == {"ALPHA": "1.23(4)"}

    # 3. Incomplete rows (e.g. name but no value) does not fail on validate=False
    state = normalize_constants_state(
        enabled=True,
        view="table",
        rows=[{"name": "ALPHA", "value": ""}],
    )
    assert state.compute_dict(validate=False) == {}

    # 4. Incomplete rows raises ValueError on validate=True
    state = normalize_constants_state(
        enabled=True,
        view="table",
        rows=[{"name": "ALPHA", "value": ""}],
    )
    with pytest.raises(ValueError, match="常数 ALPHA 需要数值"):
        state.compute_dict(validate=True)
