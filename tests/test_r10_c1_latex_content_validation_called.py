"""R10 C1 regression: validate_latex_content must run before subprocess.

Before this fix, validate_latex_content was defined but never called from any
production path; dangerous LaTeX primitives like \\write18 would reach the
subprocess call site, relying solely on -no-shell-escape. This test asserts
the pre-subprocess content filter is live.
"""

from __future__ import annotations

from unittest.mock import patch


from app_web import latex_security


def test_write18_is_blocked_before_subprocess_run():
    """A tex body containing \\write18 must NOT invoke subprocess.run."""
    warnings: list[str] = []
    tex_text = r"\documentclass{article}\begin{document}\write18{id}\end{document}"

    with patch("app_web.latex_security.subprocess.run") as mock_run:
        result = latex_security.compile_latex_safe(tex_text, "pdflatex", warnings, "testdoc")

    assert result is None, "compile_latex_safe should refuse the dangerous input"
    assert mock_run.call_count == 0, (
        "subprocess.run was called even though the LaTeX body contains \\write18. "
        "validate_latex_content must run before subprocess.run."
    )
    # Bilingual warning must be present
    assert any(" / " in w for w in warnings), (
        f"Expected bilingual warning containing ' / ', got: {warnings!r}"
    )


def test_path_traversal_input_is_blocked_before_subprocess_run():
    """A tex body containing \\input{../etc/passwd} must NOT invoke subprocess.run."""
    warnings: list[str] = []
    tex_text = r"\input{../../etc/passwd}"

    with patch("app_web.latex_security.subprocess.run") as mock_run:
        result = latex_security.compile_latex_safe(tex_text, "pdflatex", warnings, "testdoc")

    assert result is None
    assert mock_run.call_count == 0, (
        "subprocess.run was called with path-traversal \\input — "
        "validate_latex_content must block before spawning the LaTeX engine."
    )


def test_benign_tex_still_reaches_subprocess():
    """Regression guard: normal input must still compile (run reaches subprocess)."""
    warnings: list[str] = []
    tex_text = r"\documentclass{article}\begin{document}Hello.\end{document}"

    with patch("app_web.latex_security.subprocess.run") as mock_run:
        # Simulate a successful compile by crafting a minimal CompletedProcess-like return.
        # The function also inspects tex_path.with_suffix('.pdf').exists(), which will be False
        # in this mock, so we expect None return but subprocess WAS called.
        mock_run.return_value = type("CP", (), {"stdout": "", "stderr": "", "returncode": 0})()
        latex_security.compile_latex_safe(tex_text, "pdflatex", warnings, "testdoc")

    assert mock_run.call_count == 1, (
        "Benign tex must still reach subprocess.run; the filter must not over-block."
    )
