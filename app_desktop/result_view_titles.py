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
    zh, en = _COMPACT_RESULT_VIEW_TITLES.get(
        view_key,
        (
            DESKTOP_RESULT_VIEWS[view_key].title.zh,
            DESKTOP_RESULT_VIEWS[view_key].title.en,
        ),
    )
    return zh if lang == "zh" else en


def result_view_tooltip(view_key: str, lang: str) -> str:
    return DESKTOP_RESULT_VIEWS[view_key].title.for_lang(lang)
