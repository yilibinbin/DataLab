from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("flask")


@pytest.fixture
def client() -> Any:
    from app_web.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_docs_redirects_to_canonical_trailing_slash_and_preserves_query(client: Any) -> None:
    response = client.get("/docs?lang=en", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["Location"] == "/docs/?lang=en"


def test_docs_index_renders_embedded_markdown(client: Any) -> None:
    response = client.get("/docs/?lang=en")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DataLab Web Documentation" in html
    assert 'data-i18n="docs.title"' in html
    assert "This page is not available in English yet." not in html
    assert "datalab_lang=en" in response.headers.get("Set-Cookie", "")


def test_docs_language_cookie_controls_subsequent_docs_pages(client: Any) -> None:
    first = client.get("/docs/?lang=en")
    assert first.status_code == 200
    assert "datalab_lang=en" in first.headers.get("Set-Cookie", "")

    response = client.get("/docs/guide")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DataLab Web User Guide" in html
    assert "This guide explains how to use DataLab Web" in html
    assert "本指南介绍如何使用 DataLab Web" not in html


def test_docs_query_language_overrides_existing_cookie(client: Any) -> None:
    first = client.get("/docs/?lang=en")
    assert "datalab_lang=en" in first.headers.get("Set-Cookie", "")

    response = client.get("/docs/guide?lang=zh")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DataLab Web 使用指南" in html
    assert "本指南介绍如何使用 DataLab Web" in html
    assert "This guide explains how to use DataLab Web" not in html
    assert "datalab_lang=zh" in response.headers.get("Set-Cookie", "")


def test_docs_default_language_is_chinese_without_query_or_cookie(client: Any) -> None:
    response = client.get("/docs/guide")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DataLab Web 使用指南" in html
    assert "本指南介绍如何使用 DataLab Web" in html
    assert "This guide explains how to use DataLab Web" not in html
    assert "datalab_lang=" not in response.headers.get("Set-Cookie", "")


def test_docs_page_renders_named_markdown_and_navigation(client: Any) -> None:
    response = client.get("/docs/guide?lang=en")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DataLab Web User Guide" in html
    assert "How do I reference columns?" in html
    assert 'class="nav-link prev"' in html
    assert 'class="nav-link next"' in html
    assert "datalab_lang=en" in response.headers.get("Set-Cookie", "")


def test_docs_headings_get_ids_so_toc_anchors_resolve(client: Any) -> None:
    """The heading-id injection must actually run so the TOC in-page links resolve; the old
    `</\\1>` literal-backslash regex never matched and emitted no ids (audit A7)."""
    import re

    response = client.get("/docs/guide?lang=en")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    heading_ids = set(re.findall(r'<h[123]\s+id="([^"]+)"', html))
    assert heading_ids, "no heading id= attributes were emitted (TOC anchors would be dead)"
    # Every TOC anchor (href="#slug") must point at a heading id that exists on the page.
    toc_targets = set(re.findall(r'href="#([^"]+)"', html))
    assert toc_targets, "expected a table of contents with anchor links"
    assert toc_targets <= heading_ids, (
        f"TOC anchors without a matching heading id: {sorted(toc_targets - heading_ids)}"
    )


def test_docs_unknown_page_returns_friendly_not_found_page(client: Any) -> None:
    response = client.get("/docs/not-a-page?lang=en")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Documentation page not found." in html
    assert "DataLab Web User Guide" not in html
    assert "datalab_lang=en" in response.headers.get("Set-Cookie", "")


@pytest.mark.parametrize("path", ["/docs-site?lang=en", "/docs-site/legacy/page?lang=en"])
def test_legacy_docs_site_routes_redirect_to_embedded_docs(client: Any, path: str) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "/docs/"
