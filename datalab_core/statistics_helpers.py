"""Shared option-parsing helpers for the statistics service modules.

These strict parsers reject non-bool / non-string inputs. Frontend payloads
already normalize checkbox and text controls to real booleans and strings
(see ``app_web/logic/common._is_checked`` and the desktop mixin's
``bool(...)`` / ``str(...)`` coercions), so no production caller relies on the
older string-variant acceptance (``"true"``/``"1"``).
"""

from __future__ import annotations

from typing import Any

from shared.bilingual import _dual_msg


def _bool_option(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(_dual_msg("布尔统计选项必须是布尔值。", "boolean statistics options must be booleans."))
    return value


def _string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是字符串。", f"{field_name} must be a string."))
    return value.strip() or default
