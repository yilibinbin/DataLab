"""Division-by-zero in safe_eval surfaces as the contracted ValueError.

The expression engine's error contract is ValueError-only, but the '/' and
'%' binary operators raise ZeroDivisionError on a zero divisor. These tests
pin the wrapping so callers (which catch ValueError) keep working.
"""
from __future__ import annotations

import pytest

from shared.expression_engine import safe_eval


@pytest.mark.parametrize("expr", ["1/0", "1%0"])
def test_zero_divisor_raises_valueerror_not_zerodivision(expr: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        safe_eval(expr, {})
    assert not isinstance(excinfo.value, ZeroDivisionError)


@pytest.mark.parametrize("expr", ["1/0", "1%0"])
def test_zero_divisor_message_is_bilingual(expr: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        safe_eval(expr, {})
    message = str(excinfo.value)
    zh, _, en = message.partition(" / ")
    assert zh, "missing Chinese half of bilingual message"
    assert en, "missing English half of bilingual message"


def test_zero_divisor_via_variable() -> None:
    with pytest.raises(ValueError):
        safe_eval("a/b", {"a": 1, "b": 0})
