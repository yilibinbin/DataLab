from __future__ import annotations

from desktop_doc_loader import load_desktop_doc, load_desktop_manifest


def test_desktop_docs_manifest_entries_have_zh_and_en_pages():
    entries = load_desktop_manifest()
    assert entries

    zh_missing = "该章节缺失中文文档。"
    en_missing = "This page is not available in English yet."
    for entry in entries:
        slug = entry["slug"]
        zh = load_desktop_doc(slug, "zh")
        en = load_desktop_doc(slug, "en")
        assert zh and zh != zh_missing
        assert en and en != en_missing
