from __future__ import annotations

import re
from pathlib import Path

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for

from .utils import get_lang, maybe_persist_lang_cookie


bp = Blueprint("docs", __name__)

ROOT = Path(__file__).resolve().parents[2]


DOCS_PAGES: list[dict[str, object]] = [
    {"slug": "index", "title": {"zh": "文档首页", "en": "Index"}},
    {"slug": "guide", "title": {"zh": "使用指南", "en": "Guide"}},
    {"slug": "theory", "title": {"zh": "理论说明", "en": "Theory Notes"}},
    {"slug": "extrapolation", "title": {"zh": "序列外推", "en": "Extrapolation"}},
    {"slug": "uncertainty", "title": {"zh": "误差传递", "en": "Error Propagation"}},
    {"slug": "fitting", "title": {"zh": "拟合", "en": "Fitting"}},
    {"slug": "statistics", "title": {"zh": "统计平均", "en": "Statistics"}},
    {"slug": "export", "title": {"zh": "导出与排版", "en": "Export & Typesetting"}},
    {"slug": "deploy", "title": {"zh": "部署与配置", "en": "Deployment"}},
    {"slug": "faq", "title": {"zh": "常见问题", "en": "FAQ"}},
    {"slug": "roadmap", "title": {"zh": "开发路线图", "en": "Roadmap"}},
]
DOCS_WHITELIST = {p["slug"] for p in DOCS_PAGES}


def _render_markdown(md_text: str) -> str:
    """Render Markdown to HTML with security (escape HTML)."""
    try:
        import mistune

        if hasattr(mistune, "create_markdown"):
            md = mistune.create_markdown(escape=True, plugins=["table", "strikethrough"])
            return md(md_text)
        return mistune.markdown(md_text, escape=True)
    except ImportError:
        try:
            import markdown
            import html

            md_text_escaped = html.escape(md_text)
            return markdown.markdown(md_text_escaped, extensions=["tables", "fenced_code"])
        except ImportError:
            import html

            return f"<pre>{html.escape(md_text)}</pre>"


def _extract_headings(md_text: str) -> list[dict]:
    """Extract headings from Markdown for TOC generation."""
    headings = []
    for line in md_text.split("\n"):
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            heading_id = re.sub(r"[^\w\s-]", "", text.lower())
            heading_id = re.sub(r"[-\s]+", "-", heading_id).strip("-")
            headings.append(
                {
                    "level": level,
                    "text": text,
                    "id": heading_id,
                }
            )
    toc = []
    current_h1 = None
    for heading in headings:
        if heading["level"] == 1:
            current_h1 = {"text": heading["text"], "id": heading["id"], "children": []}
            toc.append(current_h1)
        elif heading["level"] == 2 and current_h1:
            current_h1["children"].append({"text": heading["text"], "id": heading["id"]})
    return toc


@bp.route("/docs")
def docs_index_redirect():
    """Redirect to canonical /docs/ so Markdown relative links work."""
    target = url_for("docs.docs_index")
    if request.query_string:
        try:
            target = f"{target}?{request.query_string.decode('utf-8', 'ignore')}"
        except Exception:
            target = f"{target}?{request.query_string.decode(errors='ignore')}"
    return redirect(target, code=308)


@bp.route("/docs/")
def docs_index():
    """Documentation homepage."""
    return docs_page("index")


@bp.route("/docs/<page>")
@bp.route("/docs/<page>/")
def docs_page(page: str):
    """Render a documentation page from Markdown."""
    lang = get_lang()

    if page not in DOCS_WHITELIST:
        msg = "Documentation page not found." if lang == "en" else "文档页面不存在。"
        resp = make_response(
            render_template(
                "docs.html",
                active_page="docs",
                content=f"<p>{msg}</p>",
                toc=[],
                lang=lang,
                current_page=page,
            )
        )
        return maybe_persist_lang_cookie(resp, lang)

    md_filename = f"{page}.{lang}.md"
    docs_dir = ROOT / "docs" / "web"
    md_path = docs_dir / md_filename

    if not md_path.exists():
        if lang == "en":
            content = (
                "<h2>This page is not available in English yet.</h2>"
                "<p><a href=\"/docs/\">Back to documentation index</a></p>"
            )
        else:
            content = "<p>该章节缺失中文文档。</p><p><a href=\"/docs/\">返回文档首页</a></p>"
        resp = make_response(
            render_template(
                "docs.html",
                active_page="docs",
                content=content,
                toc=[],
                lang=lang,
                current_page=page,
            )
        )
        return maybe_persist_lang_cookie(resp, lang)

    try:
        md_text = md_path.read_text(encoding="utf-8")
        html_content = _render_markdown(md_text)
        toc = _extract_headings(md_text)

        def add_heading_ids(match):
            tag = match.group(1)
            content = match.group(2)
            heading_id = re.sub(r"[^\w\s-]", "", content.lower())
            heading_id = re.sub(r"[-\s]+", "-", heading_id).strip("-")
            return f'<{tag} id="{heading_id}">{content}</{tag}>'

        # \1 (not \\1) — a real backreference to the opening tag; the old \\1 matched the literal
        # text "</\1>" which never occurs, so no heading ids were emitted and every TOC anchor was
        # dead (audit A7).
        html_content = re.sub(r"<(h[123])>(.+?)</\1>", add_heading_ids, html_content)

        page_order = [p["slug"] for p in DOCS_PAGES]
        page_title_map: dict[str, dict[str, str]] = {p["slug"]: dict(p.get("title") or {}) for p in DOCS_PAGES}
        prev_page = None
        next_page = None
        try:
            current_idx = page_order.index(page)
            if current_idx > 0:
                prev_slug = page_order[current_idx - 1]
                prev_page = {"slug": prev_slug, "title": page_title_map.get(prev_slug, {}).get(lang, prev_slug.title())}
            if current_idx < len(page_order) - 1:
                next_slug = page_order[current_idx + 1]
                next_page = {"slug": next_slug, "title": page_title_map.get(next_slug, {}).get(lang, next_slug.title())}
        except (ValueError, IndexError):
            prev_page = None
            next_page = None

        resp = make_response(
            render_template(
                "docs.html",
                active_page="docs",
                content=html_content,
                toc=toc,
                prev_page=prev_page,
                next_page=next_page,
                lang=lang,
                current_page=page,
            )
        )
        return maybe_persist_lang_cookie(resp, lang)
    except Exception:
        msg = "Failed to render documentation." if lang == "en" else "文档渲染失败。"
        resp = make_response(
            render_template(
                "docs.html",
                active_page="docs",
                content=f"<p>{msg}</p>",
                toc=[],
                lang=lang,
                current_page=page,
            )
        )
        return maybe_persist_lang_cookie(resp, lang)


@bp.route("/docs-site")
@bp.route("/docs-site/")
@bp.route("/docs-site/<path:filename>")
def docs_site(filename=None):
    """Legacy endpoint: redirect to embedded docs (MkDocs site removed)."""
    lang = get_lang()
    msg = (
        "The full documentation site has been removed. Please use the embedded docs."
        if lang == "en"
        else "完整文档站功能已移除，请使用内置文档。"
    )
    flash(msg, "info")
    return redirect(url_for("docs.docs_index"))

