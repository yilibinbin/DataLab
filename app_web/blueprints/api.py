from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, current_app, request

from data_extrapolation_latex_latest import DEFAULT_THREE_POINT_FORMULA
from formula_help import get_function_help, get_method_description
from shared.ui_specs import (
    EXTRAPOLATION_METHOD_SPECS,
    METHOD_DISPLAY_ORDER,
    get_parameter_visibility_rules,
)
from shared.ui_schema import FormFieldSpec


bp = Blueprint("api", __name__)

ROOT = Path(__file__).resolve().parents[2]


def form_field_to_api_payload(field: FormFieldSpec, *, lang: str = "zh") -> dict[str, object]:
    payload: dict[str, object] = {
        "name": field.key,
        "type": field.widget_kind,
        "widget_type": field.widget_kind,
        "label": field.label.for_lang(lang),
        "default": field.default_value,
        "default_value": field.default_value,
        "tooltip": field.tooltip.for_lang(lang),
        "optional": not field.required,
    }

    placeholder = field.placeholder.for_lang(lang)
    if placeholder:
        payload["placeholder"] = placeholder

    if field.widget_kind == "select":
        payload["options"] = [(choice.label.for_lang(lang), choice.value) for choice in field.choices]

    if field.widget_kind == "number":
        payload.update(
            {
                "min": field.metadata.get("min_value"),
                "max": field.metadata.get("max_value"),
                "step": field.metadata.get("step", 0.1),
                "decimals": field.metadata.get("decimals", 2),
                "number_type": field.metadata.get("number_type", "float"),
            }
        )

    if field.widget_kind == "textarea":
        payload["min_height"] = field.metadata.get("min_height", 80)
        payload["resizable"] = field.metadata.get("resizable", True)

    return payload


@bp.route("/api/ui-specs", methods=["GET"])
def api_ui_specs():
    """Provide complete UI specifications to frontend."""
    lang = request.args.get("lang", "zh")

    methods_data = []
    for key in METHOD_DISPLAY_ORDER:
        if key in EXTRAPOLATION_METHOD_SPECS:
            spec = EXTRAPOLATION_METHOD_SPECS[key]
            methods_data.append(
                {
                    "key": key,
                    "name": spec.get_name(lang),
                }
            )

    param_specs: dict[str, list[dict[str, object]]] = {}
    for key in METHOD_DISPLAY_ORDER:
        if key not in EXTRAPOLATION_METHOD_SPECS:
            continue

        method_spec = EXTRAPOLATION_METHOD_SPECS[key]
        param_specs[key] = []

        for group in method_spec.parameter_groups:
            for param in group.fields:
                param_specs[key].append(form_field_to_api_payload(param, lang=lang))

    visibility_rules = get_parameter_visibility_rules()

    return current_app.response_class(
        response=json.dumps(
            {
                "methods": methods_data,
                "param_specs": param_specs,
                "visibility_rules": visibility_rules,
            },
            ensure_ascii=False,
        ),
        status=200,
        mimetype="application/json",
    )


@bp.route("/api/function-help", methods=["GET"])
def api_function_help():
    """Provide function help text for custom formulas."""
    lang = request.args.get("lang", "zh")
    content = get_function_help(lang)

    return current_app.response_class(
        response=json.dumps(
            {
                "content": content,
                "title": "可用函数" if lang == "zh" else "Available Functions",
            },
            ensure_ascii=False,
        ),
        status=200,
        mimetype="application/json",
    )


@bp.route("/api/method-help/<method_key>", methods=["GET"])
def api_method_help(method_key: str):
    """Provide method-specific help text."""
    lang = request.args.get("lang", "zh")

    if method_key not in EXTRAPOLATION_METHOD_SPECS:
        return current_app.response_class(
            response=json.dumps({"error": "Method not found"}, ensure_ascii=False),
            status=404,
            mimetype="application/json",
        )

    content = get_method_description(method_key, lang)
    title = EXTRAPOLATION_METHOD_SPECS[method_key].get_name(lang)

    return current_app.response_class(
        response=json.dumps({"content": content, "title": title}, ensure_ascii=False),
        status=200,
        mimetype="application/json",
    )


@bp.route("/api/help_specs", methods=["GET"])
def api_help_specs():
    """Provide comprehensive help specifications for interactive help system."""
    lang = request.args.get("lang", "zh")
    if lang not in {"zh", "en"}:
        lang = "zh"

    help_specs_path = ROOT / "shared" / "help_specs.json"
    try:
        help_specs = json.loads(help_specs_path.read_text(encoding="utf-8"))

        def _substitute_placeholders(obj: object) -> object:
            if isinstance(obj, str):
                return obj.replace("{{DEFAULT_THREE_POINT_FORMULA}}", DEFAULT_THREE_POINT_FORMULA)
            if isinstance(obj, dict):
                return {k: _substitute_placeholders(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_substitute_placeholders(v) for v in obj]
            return obj

        def _as_dict(value: object) -> dict:
            return value if isinstance(value, dict) else {}

        def _placeholder_en(title: str, content: str) -> dict:
            return {"title": title, "content": content}

        def _method_placeholder_en(method_key: str) -> dict:
            return {
                "name": method_key,
                "description": "Documentation coming soon.",
                "parameters": {},
                "use_cases": "",
            }

        formula_help_map = _as_dict(help_specs.get("formula_help", {}))
        formula_help = _as_dict(formula_help_map.get(lang))
        if not formula_help:
            if lang == "en":
                formula_help = _placeholder_en("Available Functions", "Documentation coming soon.")
            else:
                formula_help = _as_dict(formula_help_map.get("zh")) or _as_dict(formula_help_map.get("en"))
        formula_help = _as_dict(_substitute_placeholders(formula_help))

        extrapolation_methods: dict[str, dict] = {}
        for method_key, method_data in _as_dict(help_specs.get("extrapolation_methods", {})).items():
            method_map = _as_dict(method_data)
            method_block = _as_dict(method_map.get(lang))
            if not method_block:
                method_block = (
                    _method_placeholder_en(method_key)
                    if lang == "en"
                    else (_as_dict(method_map.get("zh")) or _as_dict(method_map.get("en")))
                )
            extrapolation_methods[method_key] = _as_dict(_substitute_placeholders(method_block))

        return current_app.response_class(
            response=json.dumps(
                {
                    "formula_help": formula_help,
                    "extrapolation_methods": extrapolation_methods,
                },
                ensure_ascii=False,
            ),
            status=200,
            mimetype="application/json",
        )
    except Exception as exc:
        return current_app.response_class(
            response=json.dumps({"error": f"Failed to load help specs: {str(exc)}"}, ensure_ascii=False),
            status=500,
            mimetype="application/json",
        )
