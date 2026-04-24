from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "rel_path",
    [
        "docs/METHODS_THEORY.en.tex",
        "docs/PROGRAM_FRAMEWORK.en.tex",
    ],
)
def test_english_theory_docs_compile_with_pdflatex(tmp_path: Path, rel_path: str):
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        pytest.skip("pdflatex not available")

    root = Path(__file__).resolve().parents[1]
    src = root / rel_path
    assert src.exists()

    tex_path = tmp_path / src.name
    tex_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"pdflatex failed for {rel_path}:\n{result.stdout}\n{result.stderr}"

    pdf_path = tmp_path / f"{tex_path.stem}.pdf"
    assert pdf_path.exists()
