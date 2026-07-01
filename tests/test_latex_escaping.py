"""P2-6: one canonical latex_escape, used everywhere, with correct single-pass
semantics.

The load-bearing regression: the former web helper used sequential str.replace,
which re-escaped the backslashes its own replacements emitted (``a~b`` ->
``a\\textbackslash{}textasciitilde{}b``). The canonical helper must not, and
every call site must resolve to the same behaviour.
"""

from __future__ import annotations

import pytest

from shared.latex_escaping import latex_escape


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a~b", r"a\textasciitilde{}b"),
        ("x^2", r"x\textasciitilde{}2".replace("textasciitilde", "textasciicircum")),
        ("C_{12}", r"C\_\{12\}"),
        ("50%", r"50\%"),
        ("a&b", r"a\&b"),
        (r"a\b", r"a\textbackslash{}b"),
        ("", ""),
    ],
)
def test_latex_escape_is_correct_single_pass(raw, expected):
    assert latex_escape(raw) == expected


def test_latex_escape_does_not_double_escape_its_own_output():
    # The specific corruption the old web helper produced.
    assert latex_escape("a~b") == r"a\textasciitilde{}b"
    assert "textbackslash" not in latex_escape("a~b")
    assert "textbackslash" not in latex_escape("x^2")


def test_latex_escape_handles_none_and_non_str():
    assert latex_escape(None) == ""
    assert latex_escape(42) == "42"


def test_all_call_sites_use_the_canonical_helper():
    # Every module-level latex-escape helper must delegate to the shared one, so
    # they can't diverge. Verified by identity of behaviour on a probing string.
    probe = r"~^_{}&%$#\ ok"
    from datalab_latex.latex_tables_fitting import latex_escape as fitting_escape
    from datalab_latex.latex_tables_root import _escape_latex as root_escape
    from datalab_latex.latex_tables_error_propagation import _escape_latex_text as ep_escape
    from app_web.security import latex_escape as web_escape

    canonical = latex_escape(probe)
    assert fitting_escape(probe) == canonical
    assert root_escape(probe) == canonical
    assert ep_escape(probe) == canonical
    assert web_escape(probe) == canonical
