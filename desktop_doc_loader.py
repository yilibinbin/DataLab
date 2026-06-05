from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Literal, TypedDict

DocLang = Literal["zh", "en"]
_DOC_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class DesktopDocManifestEntry(TypedDict):
    slug: str
    title_zh: str
    title_en: str


def get_resource_root() -> Path:
    """
    Resolve the runtime resource root for both dev and PyInstaller builds.

    - PyInstaller (frozen): use sys._MEIPASS
    - Dev: use the project root (directory containing this file)
    """

    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        try:
            return Path(meipass).resolve()
        except Exception:
            return Path(meipass)
    return Path(__file__).resolve().parent


def _desktop_docs_dir(resource_root: Path) -> Path:
    return resource_root / "docs" / "desktop"


def _normalize_lang(lang: str | DocLang) -> DocLang:
    lang_value = str(lang).strip().lower()
    return "en" if lang_value.startswith("en") else "zh"


def _missing_placeholder(lang: DocLang) -> str:
    return "该章节缺失中文文档。" if lang == "zh" else "This page is not available in English yet."


def _is_valid_doc_slug(slug: str) -> bool:
    """
    Desktop docs are stored as a flat list of files under docs/desktop/.

    Prevent path traversal by restricting slugs to: [A-Za-z0-9][A-Za-z0-9_-]*
    """

    slug_value = str(slug or "")
    if not slug_value:
        return False
    if len(slug_value) > 128:
        return False
    return bool(_DOC_SLUG_RE.fullmatch(slug_value))


def load_desktop_doc(page_slug: str, lang: DocLang) -> str:
    """
    Load a desktop documentation page.

    Files are loaded from:
      <resource_root>/docs/desktop/<page_slug>.<lang>.md

    No cross-language fallback is allowed.
    """

    normalized_lang = _normalize_lang(lang)
    slug = (page_slug or "").strip()
    missing = _missing_placeholder(normalized_lang)
    if not slug:
        return missing
    if not _is_valid_doc_slug(slug):
        return missing

    docs_dir = _desktop_docs_dir(get_resource_root())
    path = docs_dir / f"{slug}.{normalized_lang}.md"
    try:
        docs_dir_resolved = docs_dir.resolve(strict=False)
        path_resolved = path.resolve(strict=False)
        if docs_dir_resolved != path_resolved and docs_dir_resolved not in path_resolved.parents:
            return missing
    except Exception:
        # Slug validation prevents traversal; ignore resolve issues.
        pass
    try:
        if not path.is_file():
            return missing
        return path.read_text(encoding="utf-8")
    except Exception:
        return missing


def _default_manifest() -> list[DesktopDocManifestEntry]:
    return [
        {"slug": "index", "title_zh": "桌面文档首页", "title_en": "Index"},
        {"slug": "guide", "title_zh": "使用指南", "title_en": "User Guide"},
        {"slug": "extrapolation", "title_zh": "序列外推", "title_en": "Extrapolation"},
        {"slug": "uncertainty", "title_zh": "误差传递", "title_en": "Error Propagation"},
        {"slug": "fitting", "title_zh": "拟合", "title_en": "Fitting"},
        {"slug": "root-solving", "title_zh": "求根", "title_en": "Root Solving"},
        {"slug": "statistics", "title_zh": "统计平均", "title_en": "Statistics"},
        {"slug": "export", "title_zh": "导出与排版", "title_en": "Export & Typesetting"},
        {"slug": "deploy", "title_zh": "部署、打包与发布", "title_en": "Deployment & Release"},
        {"slug": "roadmap", "title_zh": "开发路线图", "title_en": "Roadmap"},
        {"slug": "faq", "title_zh": "常见问题", "title_en": "FAQ"},
    ]


def load_desktop_manifest() -> list[DesktopDocManifestEntry]:
    """
    Load the docs navigation manifest for the desktop application.

    The manifest file is expected at:
      <resource_root>/docs/desktop/manifest.json
    """

    path = _desktop_docs_dir(get_resource_root()) / "manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            entries: list[DesktopDocManifestEntry] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug") or "").strip()
                if not slug or not _is_valid_doc_slug(slug):
                    continue
                title_zh = str(item.get("title_zh") or "").strip() or "未命名章节"
                title_en = str(item.get("title_en") or "").strip() or slug
                entries.append({"slug": slug, "title_zh": title_zh, "title_en": title_en})
            if entries:
                return entries
    except Exception:
        pass
    return _default_manifest()
