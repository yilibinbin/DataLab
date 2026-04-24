from __future__ import annotations

from app_web.latex_security import validate_latex_content


def test_validate_latex_content_rejects_include_path_traversal():
    tex = r"\documentclass{article}\begin{document}\input{./../../etc/passwd}\end{document}"
    ok, warnings = validate_latex_content(tex)
    assert not ok
    assert warnings
