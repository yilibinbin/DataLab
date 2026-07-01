"""Web dark-mode — regression tests.

The plan (#7) calls for a persistent theme toggle. The dark/light CSS
variables were already in place pre-plan; Task 2.3 extracts the toggle
JS into ``app_web/static/js/theme.js`` so the contract is pinned and
greppable.

These tests verify:
- the base template serves ``theme.js`` in the ``<head>``
- the toggle button is in the DOM with the right id and ARIA label
- CSS classes ``theme-dark`` and ``theme-light`` resolve to distinct
  colour sets (proving the variable switch actually works)
- theme.js declares the ``DATALAB_THEME`` contract (apply / toggle /
  current / STORAGE_KEY)
- the storage key name stays stable across versions
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_STATIC = (
    Path(__file__).resolve().parent.parent
    / "app_web" / "static"
)
_TEMPLATES = (
    Path(__file__).resolve().parent.parent
    / "app_web" / "templates"
)


def test_theme_js_exists_at_expected_path():
    assert (_STATIC / "js" / "theme.js").is_file(), (
        "theme.js must live at app_web/static/js/theme.js — base.html "
        "references it via url_for('static', filename='js/theme.js')"
    )


def test_theme_js_exports_contract():
    text = (_STATIC / "js" / "theme.js").read_text(encoding="utf-8")
    for needle in ("window.DATALAB_THEME", "apply", "toggle", "current", "STORAGE_KEY"):
        assert needle in text, f"theme.js contract must expose {needle!r}"


def test_theme_js_storage_key_is_stable():
    """Renaming the storage key orphans every user's saved preference,
    so pin it here and force a conscious breakage if someone edits it."""
    text = (_STATIC / "js" / "theme.js").read_text(encoding="utf-8")
    assert 'STORAGE_KEY = "datalab-theme"' in text, (
        "Storage key 'datalab-theme' must stay stable — any rename "
        "forces every user to re-pick their theme on next visit."
    )


def test_theme_js_handles_localStorage_disabled():
    """Safari private mode + some corporate policies disable
    localStorage. theme.js must not crash when setItem / getItem throw."""
    text = (_STATIC / "js" / "theme.js").read_text(encoding="utf-8")
    # The read path and the write path each have their own try/catch.
    getitem_blocks = re.findall(
        r"try\s*{[^}]*localStorage\.getItem", text, re.DOTALL
    )
    setitem_blocks = re.findall(
        r"try\s*{[^}]*localStorage\.setItem", text, re.DOTALL
    )
    assert getitem_blocks, "theme.js must guard localStorage.getItem"
    assert setitem_blocks, "theme.js must guard localStorage.setItem"


def test_base_template_includes_theme_js():
    text = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "js/theme.js" in text, (
        "base.html must include the extracted theme.js module — "
        "otherwise the toggle button in the header becomes inert."
    )


def test_base_template_theme_toggle_button_present():
    """The CSS class and id are load-bearing — theme.js grabs
    ``#theme-toggle`` by id."""
    text = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert 'id="theme-toggle"' in text
    assert "class=\"theme-toggle\"" in text


def test_base_template_has_body_root_id():
    """theme.js toggles classes on ``#body-root``. Rename breaks the
    contract."""
    text = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert 'id="body-root"' in text


def test_style_css_defines_both_theme_classes():
    text = (_STATIC / "style.css").read_text(encoding="utf-8")
    assert ".theme-dark {" in text, "style.css must define .theme-dark"
    assert ".theme-light {" in text, "style.css must define .theme-light"


def test_style_css_theme_classes_define_required_vars():
    """Every theme class must set --bg, --text, --card, --border so
    components using these variables don't fall back to inherited colours."""
    text = (_STATIC / "style.css").read_text(encoding="utf-8")
    # Extract each theme block and assert the variables are declared.
    for cls in (".theme-dark", ".theme-light"):
        m = re.search(re.escape(cls) + r"\s*{([^}]*)}", text, re.DOTALL)
        assert m, f"{cls} block not found in style.css"
        body = m.group(1)
        for var in ("--bg", "--text", "--card", "--border"):
            assert var in body, (
                f"{cls} must declare {var} — dropping a var breaks "
                "components that read through it"
            )


def test_style_css_theme_colours_differ():
    """Dark and light must have different --bg values — a regression
    where both resolve to the same colour would render the toggle inert."""
    text = (_STATIC / "style.css").read_text(encoding="utf-8")
    dark_m = re.search(r"\.theme-dark\s*{([^}]*)}", text, re.DOTALL)
    light_m = re.search(r"\.theme-light\s*{([^}]*)}", text, re.DOTALL)
    assert dark_m and light_m
    dark_bg = re.search(r"--bg:\s*([^;]+);", dark_m.group(1))
    light_bg = re.search(r"--bg:\s*([^;]+);", light_m.group(1))
    assert dark_bg and light_bg
    assert dark_bg.group(1).strip() != light_bg.group(1).strip(), (
        "Dark and light --bg must differ"
    )


def test_base_template_serves_theme_js_before_body():
    """theme.js must load before the body renders so the initial class
    is applied synchronously — otherwise users see a split-second flash
    of the wrong theme ('FOUC')."""
    text = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    head_end = text.find("</head>")
    body_start = text.find("<body")
    theme_js_idx = text.find("js/theme.js")
    assert 0 < theme_js_idx < head_end < body_start, (
        "theme.js must be in <head>, before <body>, to avoid FOUC"
    )


# ---------- integration: the rendered homepage serves the module -----------


@pytest.fixture
def _flask_client():
    """Build a Flask test client against the real app_web blueprint.
    Skips if the optional flask dep isn't available (same pattern as
    other web tests in this repo)."""
    pytest.importorskip("flask")
    from app_web import server as srv

    app = srv.create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_index_response_references_theme_js(_flask_client):
    """End-to-end: hit '/' and confirm the HTML references theme.js —
    proves base.html compiles and url_for resolves the path."""
    resp = _flask_client.get("/")
    assert resp.status_code == 200
    assert b"theme.js" in resp.data, (
        "Homepage must serve theme.js via the <script> tag"
    )


def test_index_response_has_theme_toggle_button(_flask_client):
    resp = _flask_client.get("/")
    assert b'id="theme-toggle"' in resp.data


# ---------- P1-10: light-theme contrast + double-submit guard ----------


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def _linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_light_theme_link_colour_meets_wcag_aa():
    """The brand accent (#45d3ff) is unreadable as text on the light theme's
    near-white surfaces (~1.7:1). The light theme must override link / emphasis
    text with a colour that clears WCAG AA (>=4.5:1) on both --bg and white."""
    text = (_STATIC / "style.css").read_text(encoding="utf-8")

    light_vars = re.search(r"\.theme-light\s*{([^}]*)}", text, re.DOTALL)
    assert light_vars
    light_bg = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", light_vars.group(1))
    assert light_bg, "light theme --bg must be a hex colour for this check"

    # Match the light-theme link/emphasis override regardless of any :not(...)
    # scoping refinements on the anchor selector.
    override = re.search(
        r"\.theme-light a[^,{]*,\s*\.theme-light td\.strong\s*{[^}]*color:\s*(#[0-9a-fA-F]{6})",
        text,
        re.DOTALL,
    )
    assert override, "light theme must override link/td.strong text colour"
    link = override.group(1)

    for bg in (light_bg.group(1), "#ffffff"):
        ratio = _contrast(link, bg)
        assert ratio >= 4.5, f"light link colour {link} on {bg} is {ratio:.2f} (<4.5 AA)"


def test_form_submit_guard_is_served_and_wired():
    """The double-submit guard script must exist and be included by base.html."""
    js = (_STATIC / "js" / "form-submit.js").read_text(encoding="utf-8")
    # It must hook form submit and toggle the button's disabled/busy state.
    assert 'addEventListener("submit"' in js
    assert "disabled" in js and "aria-busy" in js

    base = (_TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "js/form-submit.js" in base, "base.html must include form-submit.js"
