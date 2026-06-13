from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

import app_web.blueprints.api as api_module
from app_web.server import create_app
from datalab_latex.formula_render_service import (
    InputLanguage,
    RenderRequest,
    render_formula_metadata,
)
import datalab_latex.formula_render_service as formula_service


ROOT = Path(__file__).resolve().parents[1]
FULL_GUI_PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-06-10-datalab-full-gui-rearchitecture-plan.md"
)


def test_web_formula_resources_characterize_remote_katex_adapter_and_shared_service_script():
    template = (ROOT / "app_web" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )

    assert "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" in template
    assert "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js" in template
    assert "js/formula-preview.js" in template
    assert "crossorigin=\"anonymous\"" in template


def test_remote_katex_assets_keep_embedded_webengine_no_go_documented() -> None:
    template = (ROOT / "app_web" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    full_gui_plan = FULL_GUI_PLAN.read_text(encoding="utf-8")

    assert "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" in template
    assert "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js" in template
    assert "must become local/offline resources before any embedded" in full_gui_plan
    assert "No WebEngine, WebChannel, remote assets" in full_gui_plan
    assert "default NO-GO" in full_gui_plan


def test_web_formula_preview_js_is_thin_shared_service_adapter():
    script = (ROOT / "app_web" / "static" / "js" / "formula-preview.js").read_text(
        encoding="utf-8"
    )

    assert "/api/formula-preview" in script
    assert "fetch(" in script
    assert "katex.render" in script
    assert "custom_formula" in script
    assert "fit_custom_expr" in script
    assert "error_formula" in script
    assert "CONVERSIONS" not in script
    assert "function toLatex" not in script
    assert "payload.status" not in script
    assert "XMLHttpRequest" not in script
    assert "import(" not in script


def test_web_formula_preview_placeholder_style_is_css_owned():
    script = (ROOT / "app_web" / "static" / "js" / "formula-preview.js").read_text(
        encoding="utf-8"
    )
    stylesheet = (ROOT / "app_web" / "static" / "style.css").read_text(
        encoding="utf-8"
    )

    assert "formula-preview-placeholder" in script
    assert "<span style=" not in script
    assert ".formula-preview .formula-preview-placeholder" in stylesheet


def test_web_formula_preview_api_matches_shared_render_service_metadata():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    cases = [
        {"source": "sqrt(x)/(a+b)", "language": "datalab", "lhs": "y"},
        {"source": "sqrt(x)/(a+b)", "language": "python", "lhs": ""},
        {"source": "Sqrt[x]/(a+b)", "language": "mathematica", "lhs": ""},
        {"source": r"\frac{\sqrt{x}}{a+b}", "language": "latex", "lhs": None},
        {"source": r"\input{secret}", "language": "latex", "lhs": None},
    ]
    for case in cases:
        query = urlencode({k: v for k, v in case.items() if v is not None})
        response = client.get(f"/api/formula-preview?{query}")

        assert response.status_code == 200
        payload = json.loads(response.data.decode("utf-8"))
        expected = render_formula_metadata(
            RenderRequest(
                source=case["source"],
                language=InputLanguage(case["language"]),
                lhs=case.get("lhs") or None,
            )
        )
        assert payload == {
            "ok": expected.ok,
            "source": expected.source,
            "language": expected.language.value,
            "latex": expected.latex,
            "mathtext": expected.mathtext,
            "fallback_text": expected.fallback_text,
            "error_message": expected.error_message,
        }


def test_web_formula_preview_api_does_not_render_png(monkeypatch):
    def fail_png_render(*_args, **_kwargs) -> bytes:
        raise AssertionError("web metadata endpoint must not render PNG bytes")

    monkeypatch.setattr(formula_service, "_render_mathtext_png", fail_png_render)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get(
        "/api/formula-preview?"
        + urlencode({"source": "sqrt(x)/(a+b)", "language": "datalab"})
    )

    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["latex"]
    assert "png" not in payload


def test_web_formula_preview_api_stays_metadata_only_and_qt_free_in_clean_process():
    script = r"""
import json
import sys

from app_web.server import create_app

app = create_app()
app.config["TESTING"] = True
client = app.test_client()
response = client.get("/api/formula-preview?source=sqrt(x)&language=datalab&lhs=y")
if response.status_code != 200:
    raise SystemExit(f"unexpected status: {response.status_code}")
payload = json.loads(response.data.decode("utf-8"))
if not payload.get("ok") or not payload.get("latex"):
    raise SystemExit(f"unexpected payload: {payload!r}")
forbidden_prefixes = (
    "matplotlib.pyplot",
    "PySide6",
    "PySide6.QtWidgets",
    "app_desktop",
    "app_desktop.formula_preview",
    "data_extrapolation_latex_latest",
    "datalab_latex.latex_tables_extrapolation",
    "datalab_latex.latex_formatting",
    "mpmath",
    "sympy",
    "app_web.logic.error_propagation",
    "app_web.logic.extrapolation",
    "app_web.logic.fitting",
    "app_web.logic.root_solving",
    "app_web.logic.statistics",
    "fitting",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""

    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "formula-preview-test-secret"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_web_formula_preview_api_rejects_unknown_language_without_rendering():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/formula-preview?source=x&language=not-a-language")

    assert response.status_code == 400
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["ok"] is False
    assert payload["language"] == "not-a-language"
    assert "Unsupported formula preview language" in payload["error_message"]


def test_web_formula_preview_api_rejects_unknown_language_before_render_service(
    monkeypatch,
):
    def fail_render_service(*_args, **_kwargs):
        raise AssertionError("unsupported languages must not enter render service")

    monkeypatch.setattr(api_module, "render_formula_metadata", fail_render_service)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/formula-preview?source=x&language=not-a-language")

    assert response.status_code == 400
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["ok"] is False
    assert payload["latex"] == ""
    assert payload["mathtext"] == ""


def test_web_formula_preview_api_reports_shared_service_preview_errors():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    cases = [
        ("", "Formula is empty."),
        ("sqrt(x", "Unbalanced expression."),
        (r"\input{secret}", "Unsafe LaTeX command"),
        (r"\begin{document}x\end{document}", "Unsafe LaTeX environment"),
    ]
    for source, expected_message in cases:
        response = client.get(
            "/api/formula-preview?"
            + urlencode({"source": source, "language": "datalab"})
        )

        assert response.status_code == 200
        payload = json.loads(response.data.decode("utf-8"))
        assert payload["ok"] is False
        assert payload["latex"] == ""
        assert payload["mathtext"] == ""
        assert payload["fallback_text"] == source
        assert expected_message in payload["error_message"]
