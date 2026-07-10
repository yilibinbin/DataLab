"""Custom-mode params-JSON error-path tests (CR-2, twin of the self_consistent CR-1).

The custom branch's non-dict params check used to sit inside the JSON-parse
try/except, so its bilingual ValueError was caught and re-wrapped into a doubled
'汉语 / English / 汉语 / English' message that breaks the locale layer's single
' / ' split. These tests pin the corrected behavior: exactly one ' / ' per error.
"""

from __future__ import annotations

import pytest

from app_web.logic.fitting import _run_fit

_DATA_TEXT = "x y\n1 3\n2 5\n3 7\n"


def _run_custom(params_text: str) -> None:
    _run_fit(
        _DATA_TEXT,
        {
            "fit_mode": "custom",
            "fit_custom_expr": "a*x + b",
            "fit_custom_params": params_text,
            "fit_x_column": "x",
            "fit_target_column": "y",
            "fit_mp_precision": "50",
        },
    )


def test_custom_non_dict_params_gives_single_bilingual_message() -> None:
    with pytest.raises(ValueError) as exc_info:
        _run_custom("[1, 2]")  # valid JSON, but not an object
    assert str(exc_info.value).count(" / ") == 1


def test_custom_params_json_syntax_error_is_wrapped_once() -> None:
    with pytest.raises(ValueError) as exc_info:
        _run_custom("{bad json")
    message = str(exc_info.value)
    assert message.count(" / ") == 1
    # The wrap identifies the failing stage in both languages.
    assert "自定义模型解析失败" in message
    assert "Failed to parse custom model" in message
