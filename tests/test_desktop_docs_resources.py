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
    shutil.copytree(Path("examples") / "recipes", resource_root / "examples" / "recipes")

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

    from app_desktop.resources import resolve_resource_path
    from datalab_core.recipes import loads_recipe_json

    recipe = resolve_resource_path("examples/recipes/statistics-mean-basic.json")
    assert recipe is not None
    assert loads_recipe_json(recipe.read_text(encoding="utf-8"))["id"] == "statistics-mean-basic"


def test_formula_preview_docs_explain_single_rendered_preview() -> None:
    from desktop_doc_loader import load_desktop_doc

    guide_zh = load_desktop_doc("guide", "zh")
    guide_en = load_desktop_doc("guide", "en")
    fitting_zh = load_desktop_doc("fitting", "zh")
    fitting_en = load_desktop_doc("fitting", "en")
    examples_readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")

    assert "公式预览" in guide_zh
    assert "Formula Preview" in guide_en
    assert "DataLab/Mathematica 兼容语法" in guide_zh
    assert "DataLab/Mathematica-compatible syntax" in guide_en
    assert "渲染为 LaTeX 风格的数学公式" in guide_zh
    assert "renders the current expression as\nLaTeX-style math" in guide_en
    assert "不会\n改变计算配置" in guide_zh
    assert "does not change computation input" in guide_en
    assert "预览语法" not in guide_zh
    assert "Preview syntax" not in guide_en
    assert "高保真 LaTeX" not in guide_zh
    assert "High-fidelity LaTeX" not in guide_en

    assert "自洽隐式模型" in fitting_zh
    assert "self-consistent/implicit models" in fitting_en
    assert "预览按钮" in fitting_zh
    assert "preview syntax" not in fitting_en

    assert "formula rendering" in examples_readme
    assert "High-fidelity LaTeX" not in examples_readme


def test_input_docs_explain_content_driven_sectioned_constants() -> None:
    from desktop_doc_loader import load_desktop_doc

    guide_zh = load_desktop_doc("guide", "zh")
    guide_en = load_desktop_doc("guide", "en")
    root_zh = load_desktop_doc("root-solving", "zh")
    root_en = load_desktop_doc("root-solving", "en")
    examples_readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")

    for content in (guide_zh, root_zh, examples_readme):
        assert "[data]" in content
        assert "[constants]" in content
    assert "非空常数会" in guide_zh
    assert "空白常数会被忽略" in root_zh
    assert "关闭常数设置" not in guide_zh
    assert "默认关闭" not in root_zh

    for content in (guide_en, root_en, examples_readme):
        assert "[data]" in content
        assert "[constants]" in content
    assert "Non-empty constants" in guide_en
    assert "blank constants are ignored" in root_en
    assert "Disabled constants" not in guide_en
    assert "disabled by default" not in root_en
