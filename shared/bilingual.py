"""Single-source bilingual message helpers.

DataLab's user-facing strings follow a ``中文 / English`` convention so the UI
locale layer can split on ``" / "`` and render the active language. Having
multiple copies of ``_dual_msg``/``_split_dual`` across modules makes it easy
for the separator convention to drift (e.g. missing space before ``/``). This
module is the single source of truth — every other module should import from
here rather than redefining the helpers locally.
"""

from __future__ import annotations

__all__ = ["_dual_msg", "_split_dual", "dual_msg", "split_dual"]


def dual_msg(zh: str, en: str) -> str:
    """Join a Chinese and English message with the canonical separator.

    The separator must be ``" / "`` (space-slash-space) so the locale layer
    can round-trip it via :func:`split_dual`.
    """
    return f"{zh} / {en}"


def split_dual(text: str) -> tuple[str, str]:
    """Return ``(zh, en)`` for a bilingual string; fall back to ``(text, text)``."""
    if " / " in text:
        left, right = text.split(" / ", 1)
        return left.strip(), right.strip()
    return text, text


# Keep the leading-underscore aliases for backwards compatibility with the
# many modules that imported ``_dual_msg`` / ``_split_dual`` directly before
# centralization.
_dual_msg = dual_msg
_split_dual = split_dual
