"""Canonical LaTeX text escaping (P2-6).

DataLab escapes user text for LaTeX table captions, headers, labels, and web
output. Before consolidation there were ~5 near-duplicate helpers; most used a
correct single-pass char map, but the web copy used sequential ``str.replace``,
which double-escaped the backslashes its own replacements introduced — e.g.
``a~b`` became ``a\\textbackslash{}textasciitilde{}b`` instead of
``a\\textasciitilde{}b``. This module is the one correct implementation; all
call sites route through it so escaping can never diverge again.

``str.translate`` applies the map in a single pass, so a backslash emitted for
one input character is never re-escaped — the property the ``str.replace`` loop
lacked.
"""

from __future__ import annotations

# The canonical special-character map. ``\`` maps to ``\textbackslash{}`` (not
# ``\\``) so escaped text is safe in ordinary LaTeX text mode; ``~`` and ``^``
# use the text-mode command forms for the same reason.
_LATEX_SPECIAL_ESCAPES = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


def latex_escape(text: object) -> str:
    """Escape LaTeX special characters in ``text`` for safe use in text mode.

    Accepts any object (coerced via ``str``); ``None`` becomes an empty string.
    Single-pass, so replacements are never re-escaped.
    """
    if text is None:
        return ""
    return str(text).translate(_LATEX_SPECIAL_ESCAPES)
