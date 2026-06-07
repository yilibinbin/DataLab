from __future__ import annotations

import json

from app_web.server import create_app
from data_extrapolation_latex_latest import DEFAULT_THREE_POINT_FORMULA


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

    beta = payload["param_specs"]["levin_u"][3]
    assert beta["name"] == "beta"
    assert beta["optional"] is True
    assert beta["number_type"] == "float"
    assert beta["min"] == 0.01


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
