from __future__ import annotations

from pathlib import Path


def test_readme_has_no_obsolete_references_and_required_files_exist():
    root = Path(__file__).resolve().parents[1]

    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "app_web/logic.py" not in readme
    assert "cd data_draw" not in readme
    assert "IMPLEMENTATION_REPORT.md" not in readme

    expected_files = [
        root / "QUICK_START.md",
        root / "QUICK_START.en.md",
        root / "docs" / "DATALAB_WEB_GUIDE.md",
        root / "docs" / "DATALAB_WEB_GUIDE.en.md",
        root / "docs" / "web" / "deploy.md",
        root / "docs" / "METHODS_THEORY.en.tex",
        root / "docs" / "PROGRAM_FRAMEWORK.en.tex",
    ]
    for path in expected_files:
        assert path.exists(), f"Missing expected doc file: {path}"
