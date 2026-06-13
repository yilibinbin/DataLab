from __future__ import annotations

from typing import Any


def set_accessible_description(widget: Any, text: str) -> None:
    setter = getattr(widget, "setAccessibleDescription", None)
    if callable(setter):
        setter(text)
