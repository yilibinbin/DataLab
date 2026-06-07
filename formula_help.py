#!/usr/bin/env python3
"""
Shared formula help and extrapolation method documentation.

This module is a compatibility facade for desktop and web callers. User-facing
help content lives in ``shared/help_specs.json``.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from data_extrapolation_latex_latest import DEFAULT_THREE_POINT_FORMULA
except Exception:  # pragma: no cover - import failure fallback for minimal tooling
    DEFAULT_THREE_POINT_FORMULA = "(C - B)^2/(B - A) + C"


_FALLBACK_FUNCTION_HELP: dict[str, str] = {
    "zh": "函数帮助暂不可用。",
    "en": "Function help is unavailable.",
}
_FALLBACK_FUNCTION_TOOLTIP: dict[str, str] = {
    "zh": "函数帮助暂不可用。",
    "en": "Function help is unavailable.",
}


def _normalize_lang(lang: str) -> str:
    return "en" if lang == "en" else "zh"


def _candidate_help_specs_paths() -> list[Path]:
    paths: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "shared" / "help_specs.json")

    module_root = Path(__file__).resolve().parent
    paths.append(module_root / "shared" / "help_specs.json")
    paths.append(Path.cwd() / "shared" / "help_specs.json")

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in seen:
            unique_paths.append(path)
            seen.add(resolved)
    return unique_paths


def _substitute_placeholders(value: object) -> object:
    if isinstance(value, str):
        return value.replace("{{DEFAULT_THREE_POINT_FORMULA}}", DEFAULT_THREE_POINT_FORMULA)
    if isinstance(value, dict):
        return {key: _substitute_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_placeholders(item) for item in value]
    return value


@lru_cache(maxsize=1)
def _load_help_specs() -> dict[str, Any]:
    for path in _candidate_help_specs_paths():
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _formula_help_block(lang: str) -> dict[str, Any]:
    specs = _load_help_specs()
    formula_help = _as_dict(specs.get("formula_help"))
    normalized_lang = _normalize_lang(lang)
    block = _as_dict(formula_help.get(normalized_lang))
    if not block and normalized_lang != "zh":
        block = _as_dict(formula_help.get("zh"))
    return _as_dict(_substitute_placeholders(block))


def _method_block(method_key: str, lang: str) -> dict[str, Any]:
    specs = _load_help_specs()
    methods = _as_dict(specs.get("extrapolation_methods"))
    method = _as_dict(methods.get(method_key))
    normalized_lang = _normalize_lang(lang)
    block = _as_dict(method.get(normalized_lang))
    if not block and normalized_lang != "zh":
        block = _as_dict(method.get("zh"))
    return _as_dict(_substitute_placeholders(block))


def _method_parameters(method_key: str) -> list[dict[str, object]]:
    specs = _load_help_specs()
    methods = _as_dict(specs.get("extrapolation_methods"))
    method = _as_dict(methods.get(method_key))
    explicit = method.get("parameter_specs")
    if isinstance(explicit, list):
        return [item for item in explicit if isinstance(item, dict)]

    zh_params = _as_dict(_as_dict(method.get("zh")).get("parameters"))
    en_params = _as_dict(_as_dict(method.get("en")).get("parameters"))
    names = list(dict.fromkeys([*zh_params.keys(), *en_params.keys()]))
    return [
        {
            "name": name,
            "type": "text",
            "description_zh": str(zh_params.get(name, "")),
            "description_en": str(en_params.get(name, "")),
        }
        for name in names
    ]


def _build_extrapolation_methods() -> dict[str, dict[str, object]]:
    specs = _load_help_specs()
    methods = _as_dict(specs.get("extrapolation_methods"))
    compatibility: dict[str, dict[str, object]] = {}
    for method_key, method_value in methods.items():
        if not isinstance(method_key, str):
            continue
        method = _as_dict(method_value)
        zh = _as_dict(_substitute_placeholders(_as_dict(method.get("zh"))))
        en = _as_dict(_substitute_placeholders(_as_dict(method.get("en"))))
        compatibility[method_key] = {
            "name_zh": str(zh.get("name", method_key)),
            "name_en": str(en.get("name", method_key)),
            "description_zh": str(zh.get("description", "")),
            "description_en": str(en.get("description", "")),
            "parameters": _method_parameters(method_key),
        }
    return compatibility


EXTRAPOLATION_METHODS: dict[str, dict[str, object]] = _build_extrapolation_methods()


def get_function_help(lang: str = "zh") -> str:
    """Get function help text in specified language."""
    normalized_lang = _normalize_lang(lang)
    block = _formula_help_block(normalized_lang)
    content = block.get("plain_content") or block.get("content")
    return str(content) if content else _FALLBACK_FUNCTION_HELP[normalized_lang]


def get_function_tooltip(lang: str = "zh") -> str:
    """Get function tooltip text in specified language."""
    normalized_lang = _normalize_lang(lang)
    block = _formula_help_block(normalized_lang)
    tooltip = block.get("tooltip")
    return str(tooltip) if tooltip else _FALLBACK_FUNCTION_TOOLTIP[normalized_lang]


def get_method_description(method_key: str, lang: str = "zh") -> str:
    """Get extrapolation method description."""
    block = _method_block(method_key, lang)
    description = block.get("description", "")
    return str(description) if description else ""


def get_method_name(method_key: str, lang: str = "zh") -> str:
    """Get extrapolation method display name."""
    block = _method_block(method_key, lang)
    name = block.get("name", method_key)
    return str(name) if name else method_key


def get_method_parameters(method_key: str) -> list[dict[str, object]]:
    """Get parameter definitions for a method."""
    return _method_parameters(method_key)
