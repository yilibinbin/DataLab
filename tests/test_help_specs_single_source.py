from __future__ import annotations

import json


def test_formula_help_public_api_reads_shared_help_specs(monkeypatch, tmp_path):
    import formula_help

    specs_path = tmp_path / "help_specs.json"
    specs_path.write_text(
        json.dumps(
            {
                "formula_help": {
                    "zh": {
                        "plain_content": "测试函数帮助 Sin[x]",
                        "tooltip": "测试函数提示 Sin[x]",
                    },
                    "en": {
                        "plain_content": "Spec function help with Sin[x]",
                        "tooltip": "Spec function tooltip with Sin[x]",
                    },
                },
                "extrapolation_methods": {
                    "power_law": {
                        "zh": {
                            "name": "规格幂律",
                            "description": "规格幂律说明",
                            "parameters": {"x1": "第一个 x 值"},
                        },
                        "en": {
                            "name": "Spec power law",
                            "description": "Spec power law description",
                            "parameters": {"x1": "First x value"},
                        },
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(formula_help, "_candidate_help_specs_paths", lambda: [specs_path])
    formula_help._load_help_specs.cache_clear()

    try:
        assert formula_help.get_method_name("power_law", "zh") == "规格幂律"
        assert formula_help.get_method_name("power_law", "en") == "Spec power law"
        assert formula_help.get_method_description("power_law", "zh") == "规格幂律说明"
        assert formula_help.get_method_description("power_law", "en") == "Spec power law description"
        assert "sin" in formula_help.get_function_help("en").lower()
        assert "sin" in formula_help.get_function_tooltip("en").lower()
        assert formula_help.get_method_parameters("power_law") == [
            {
                "name": "x1",
                "type": "text",
                "description_zh": "第一个 x 值",
                "description_en": "First x value",
            }
        ]
    finally:
        formula_help._load_help_specs.cache_clear()


def test_formula_help_public_api_uses_repository_help_specs():
    from formula_help import get_function_help, get_method_description, get_method_name

    assert get_method_name("power_law", "zh")
    assert get_method_name("power_law", "en")
    assert get_method_description("power_law", "zh")
    assert "sin" in get_function_help("en").lower()
