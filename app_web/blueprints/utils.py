from __future__ import annotations

from flask import request


def _normalize_lang(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower()
    if value in {"zh", "zh-cn", "zh_cn", "cn"}:
        return "zh"
    if value in {"en", "en-us", "en_us"}:
        return "en"
    return None


def get_lang(default: str = "zh") -> str:
    """Resolve language in a stable order: query param > cookie > default."""
    query_lang = _normalize_lang(request.args.get("lang"))
    if query_lang:
        return query_lang
    cookie_lang = _normalize_lang(request.cookies.get("datalab_lang"))
    if cookie_lang:
        return cookie_lang
    return default


def maybe_persist_lang_cookie(response, lang: str):
    """Persist docs language so Markdown relative links remain in the same language."""
    try:
        query_lang = _normalize_lang(request.args.get("lang"))
        if query_lang:
            response.set_cookie(
                "datalab_lang",
                query_lang,
                max_age=60 * 60 * 24 * 365,
                path="/",
                samesite="Lax",
            )
    except Exception:
        pass
    return response

