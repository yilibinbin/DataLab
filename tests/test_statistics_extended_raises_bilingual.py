"""Structural guard (P1-4): every user-facing raise in the extended-statistics
modules must carry a bilingual message via ``_dual_msg(zh, en)``.

The extended-stats modules (bootstrap / grouped / hypothesis / matrix /
time_series) validate user input and raise ``ValueError`` / ``TypeError`` with
human-readable messages. DataLab's audience is bilingual (中文 / English), and
the locale layer splits error text on ``" / "``; a raise that carries only an
English string shows English to every user regardless of locale.

Rather than trigger each of the ~440 raises behaviourally, this test parses the
modules and asserts that no ``raise`` carries a *bare* string literal — every
message string must be an argument of a ``_dual_msg(...)`` call (or already
contain the ``" / "`` delimiter). That way a newly added English-only raise
fails here immediately instead of shipping to users.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_CORE = Path(__file__).resolve().parents[1] / "datalab_core"
_MODULES = [
    _CORE / "statistics_bootstrap.py",
    _CORE / "statistics_grouped.py",
    _CORE / "statistics_hypothesis.py",
    _CORE / "statistics_matrix.py",
    _CORE / "statistics_time_series.py",
]


def _is_dual_msg_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_dual_msg"
    )


def _string_constants(node: ast.AST) -> list[str]:
    """Collect plain and f-string literal text reachable in ``node``, but do NOT
    descend into ``_dual_msg(...)`` calls — those are the sanctioned bilingual
    wrapper and their inner strings are allowed to be single-language halves."""
    found: list[str] = []

    def walk(inner: ast.AST) -> None:
        if _is_dual_msg_call(inner):
            return  # sanctioned wrapper; its halves are intentional
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            found.append(inner.value)
        elif isinstance(inner, ast.JoinedStr):
            # f-string: gather its literal segments (enough to tell it carries
            # a human message); interpolations are ignored.
            for value in inner.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.append(value.value)
        for child in ast.iter_child_nodes(inner):
            walk(child)

    walk(node)
    return found


def _bare_english_raises(module_path: Path) -> list[str]:
    """Return a description of each raise in ``module_path`` that carries a
    message string outside a ``_dual_msg`` wrapper and without the ``" / "``
    delimiter — i.e. an English-only user-facing message."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        # A raise wrapping _dual_msg directly (raise Err(_dual_msg(...))) is fine;
        # _string_constants already skips _dual_msg subtrees, so any string it
        # still returns is a bare, unwrapped message.
        strings = _string_constants(node.exc)
        message_like = [s for s in strings if s.strip() and " / " not in s]
        # Ignore trivial non-message strings (e.g. a lone format spec); a real
        # message has letters. This keeps the guard focused on human text.
        message_like = [s for s in message_like if any(ch.isalpha() for ch in s)]
        if message_like:
            offenders.append(f"{module_path.name}:{node.lineno} -> {message_like[0]!r}")
    return offenders


@pytest.mark.parametrize("module_path", _MODULES, ids=lambda p: p.name)
def test_extended_statistics_raises_are_bilingual(module_path: Path) -> None:
    offenders = _bare_english_raises(module_path)
    assert not offenders, (
        f"{len(offenders)} raise(s) in {module_path.name} carry an English-only "
        f"message; wrap them in _dual_msg(zh, en):\n" + "\n".join(offenders)
    )
