from __future__ import annotations

from shared.ui_specs import DESKTOP_RESULT_VIEWS


_COMPACT_RESULT_VIEW_TITLES: dict[str, tuple[str, str]] = {
    "result.numeric": ("数值", "Data"),
    "result.image": ("图像", "Image"),
    "result.log": ("日志", "Log"),
    "result.latex": ("TeX", "TeX"),
    "result.pdf": ("PDF", "PDF"),
}


def result_view_tab_title(view_key: str, lang: str) -> str:
    compact_title = _COMPACT_RESULT_VIEW_TITLES.get(view_key)
    if compact_title is not None:
        zh, en = compact_title
    else:
        view_spec = DESKTOP_RESULT_VIEWS.get(view_key)
        if view_spec is None:
            raise ValueError(_unknown_result_view_message(view_key))
        zh, en = view_spec.title.zh, view_spec.title.en
    return zh if lang == "zh" else en


def result_view_tooltip(view_key: str, lang: str) -> str:
    view_spec = DESKTOP_RESULT_VIEWS.get(view_key)
    if view_spec is None:
        raise ValueError(_unknown_result_view_message(view_key))
    return view_spec.title.for_lang(lang)


def _unknown_result_view_message(view_key: str) -> str:
    available = ", ".join(sorted(DESKTOP_RESULT_VIEWS))
    return f"Unknown result view key {view_key!r}. Available keys: {available}"
