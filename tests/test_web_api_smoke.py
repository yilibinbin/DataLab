from __future__ import annotations

import json
import os
import subprocess
import sys

from app_web.server import create_app
from shared.formula_defaults import DEFAULT_THREE_POINT_FORMULA


def test_api_ui_specs_smoke():
    app = create_app()
    client = app.test_client()

    resp = client.get("/api/ui-specs?lang=en")
    assert resp.status_code == 200
    payload = json.loads(resp.data.decode("utf-8"))
    assert "methods" in payload
    assert "param_specs" in payload
    assert "visibility_rules" in payload
    assert payload["methods"]
    assert {method["key"] for method in payload["methods"]} >= {"power_law", "richardson", "levin_u", "custom"}
    assert {"power_law", "richardson", "levin_u", "custom"} <= set(payload["param_specs"])

    custom_formula = payload["param_specs"]["custom"][0]
    assert custom_formula["name"] == "custom_formula"
    assert custom_formula["type"] == "textarea"
    assert custom_formula["widget_type"] == "textarea"
    assert custom_formula["default"] == "(C - B)^2/(B - A) + C"
    assert custom_formula["default_value"] == "(C - B)^2/(B - A) + C"
    assert custom_formula["placeholder"]
    assert custom_formula["tooltip"]
    assert custom_formula["min_height"] == 80

    variant = payload["param_specs"]["levin_u"][0]
    assert variant["name"] == "variant"
    assert variant["type"] == "select"
    assert variant["options"] == [
        ["u (most common)", "u"],
        ["t (series)", "t"],
        ["v (integrals)", "v"],
    ]

    # order / weight / beta removed (audit F4): mpmath's mp.levin honors only the
    # variant, so it is the sole levin_u parameter the web spec exposes.
    assert [spec["name"] for spec in payload["param_specs"]["levin_u"]] == ["variant"]
    # richardson has no tunable knobs (mp.richardson takes only the sequence).
    assert payload["param_specs"]["richardson"] == []


def test_api_function_help_smoke_bilingual():
    app = create_app()
    client = app.test_client()

    zh = client.get("/api/function-help?lang=zh")
    assert zh.status_code == 200
    zh_payload = json.loads(zh.data.decode("utf-8"))
    assert zh_payload.get("title") == "可用函数"
    assert isinstance(zh_payload.get("content"), str)

    en = client.get("/api/function-help?lang=en")
    assert en.status_code == 200
    en_payload = json.loads(en.data.decode("utf-8"))
    assert en_payload.get("title") == "Available Functions"
    assert isinstance(en_payload.get("content"), str)


def test_api_help_specs_substitutes_default_formula_placeholder():
    app = create_app()
    client = app.test_client()

    resp = client.get("/api/help_specs?lang=en")
    assert resp.status_code == 200
    payload = json.loads(resp.data.decode("utf-8"))
    dumped = json.dumps(payload, ensure_ascii=False)
    assert DEFAULT_THREE_POINT_FORMULA in dumped


def test_api_method_help_smoke_bilingual():
    app = create_app()
    client = app.test_client()

    zh = client.get("/api/method-help/power_law?lang=zh")
    assert zh.status_code == 200
    zh_payload = json.loads(zh.data.decode("utf-8"))
    assert zh_payload.get("title")
    assert "幂律" in zh_payload.get("content", "")

    en = client.get("/api/method-help/power_law?lang=en")
    assert en.status_code == 200
    en_payload = json.loads(en.data.decode("utf-8"))
    assert en_payload.get("title")
    assert "power" in en_payload.get("content", "").lower()


def test_api_method_help_not_found_returns_404():
    app = create_app()
    client = app.test_client()

    resp = client.get("/api/method-help/not-a-method?lang=en")
    assert resp.status_code == 404


def test_schema_help_metadata_endpoints_do_not_import_desktop_or_compute_stack():
    script = """
import sys

from app_web.server import create_app

app = create_app()
app.config["TESTING"] = True
client = app.test_client()

for path in (
    "/api/ui-specs?lang=en",
    "/api/function-help?lang=en",
    "/api/help_specs?lang=en",
    "/api/method-help/power_law?lang=en",
):
    response = client.get(path)
    if response.status_code != 200:
        raise SystemExit(f"{path} returned {response.status_code}")

forbidden_prefixes = (
    "app_desktop",
    "PySide6",
    "matplotlib.pyplot",
    "data_extrapolation_latex_latest",
    "datalab_latex.latex_tables_extrapolation",
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
    env["DATALAB_WEB_SECRET"] = "web-schema-help-import-test-secret"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"
