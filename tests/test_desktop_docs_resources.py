from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_docs_manifest_pages_resolve_in_development_tree() -> None:
    from desktop_doc_loader import load_desktop_doc, load_desktop_manifest

    manifest = load_desktop_manifest()
    assert manifest
    for entry in manifest:
        for lang, placeholder in (
            ("zh", "该章节缺失中文文档。"),
            ("en", "This page is not available in English yet."),
        ):
            content = load_desktop_doc(entry["slug"], lang)
            assert content.strip(), (entry["slug"], lang)
            assert content != placeholder


def test_docs_and_example_workspaces_resolve_under_pyinstaller_meipass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from desktop_doc_loader import load_desktop_doc, load_desktop_manifest
    from examples.catalog import EXAMPLE_NAMES

    resource_root = tmp_path / "meipass"
    shutil.copytree(Path("docs") / "desktop", resource_root / "docs" / "desktop")
    shutil.copytree(Path("examples") / "workspaces", resource_root / "examples" / "workspaces")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(resource_root), raising=False)

    manifest = load_desktop_manifest()
    assert [entry["slug"] for entry in manifest]
    for entry in manifest:
        assert load_desktop_doc(entry["slug"], "en").strip()
        assert load_desktop_doc(entry["slug"], "zh").strip()

    from app_desktop.window import list_example_menu_entries, list_example_workspaces

    assert [path.name for path in list_example_workspaces()] == list(EXAMPLE_NAMES)
    assert [entry.filename for entry in list_example_menu_entries()] == list(EXAMPLE_NAMES)


def test_formula_preview_docs_explain_syntax_modes_and_high_fidelity_preview() -> None:
    from desktop_doc_loader import load_desktop_doc

    guide_zh = load_desktop_doc("guide", "zh")
    guide_en = load_desktop_doc("guide", "en")
    fitting_zh = load_desktop_doc("fitting", "zh")
    fitting_en = load_desktop_doc("fitting", "en")
    examples_readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")

    assert "预览语法" in guide_zh
    assert "Preview syntax" in guide_en
    assert "高保真 LaTeX" in guide_zh
    assert "High-fidelity LaTeX" in guide_en
    assert "不会改变计算" in guide_zh
    assert "does not change computation" in guide_en

    assert "自洽隐式模型" in fitting_zh
    assert "self-consistent/implicit models" in fitting_en
    assert "预览语法" in fitting_zh
    assert "preview syntax" in fitting_en

    assert "formula preview syntax" in examples_readme
    assert "高保真 LaTeX" in examples_readme
