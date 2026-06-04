from dataclasses import FrozenInstanceError

import pytest

from shared.ui_schema import (
    ChoiceSpec,
    FormFieldSpec,
    FormSectionSpec,
    LocalizedText,
    PlotBudget,
    VisibilityRule,
)


def test_localized_text_uses_chinese_by_default_and_english_when_requested() -> None:
    text = LocalizedText(zh="公式：", en="Formula:")

    assert text.for_lang("zh") == "公式："
    assert text.for_lang("en") == "Formula:"
    assert text.for_lang("auto") == "公式："


def test_visibility_rule_supports_equals_in_not_equals_and_all() -> None:
    rule = VisibilityRule.all(
        VisibilityRule.equals("method", "levin_u"),
        VisibilityRule.in_set("fit_model", {"custom", "self_consistent"}),
        VisibilityRule.not_equals("fit_model", "builtin"),
    )

    assert rule.evaluate({"method": "levin_u", "fit_model": "custom"}) is True
    assert rule.evaluate({"method": "levin_u", "fit_model": "builtin"}) is False
    assert rule.evaluate({"method": "richardson", "fit_model": "custom"}) is False


def test_form_field_spec_exposes_placeholder_tooltip_and_required_marker() -> None:
    spec = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        placeholder=LocalizedText("例如 A*x + B", "e.g. A*x + B"),
        tooltip=LocalizedText("输入 y=f(x,p) 形式", "Enter y=f(x,p) form"),
        required=True,
    )

    assert spec.key == "fitting.custom.expression"
    assert spec.widget_kind == "textarea"
    assert spec.label.for_lang("en") == "Model expression:"
    assert spec.placeholder.for_lang("zh") == "例如 A*x + B"
    assert spec.tooltip.for_lang("en") == "Enter y=f(x,p) form"
    assert spec.required is True


def test_choice_spec_keeps_backend_value_stable() -> None:
    choice = ChoiceSpec(value="scalar", label=LocalizedText("标量", "Scalar"))

    assert choice.value == "scalar"
    assert choice.label.for_lang("en") == "Scalar"


def test_plot_budget_defaults_match_phase_one_limits() -> None:
    budget = PlotBudget()

    assert budget.max_grid_points == 300
    assert budget.max_monte_carlo_curves == 100
    assert budget.max_batch_rows == 25
    assert budget.max_images_per_run == 25


def test_schema_specs_are_frozen_and_normalize_sequences_to_tuples() -> None:
    choices = [ChoiceSpec(value="scalar", label=LocalizedText("标量", "Scalar"))]
    field = FormFieldSpec(
        key="root.mode",
        widget_kind="select",
        label=LocalizedText("求解模式：", "Solve mode:"),
        choices=choices,
    )

    choices.append(ChoiceSpec(value="system", label=LocalizedText("方程组", "System")))

    assert isinstance(field.choices, tuple)
    assert [choice.value for choice in field.choices] == ["scalar"]
    with pytest.raises(FrozenInstanceError):
        setattr(field, "key", "changed")

    fields = [field]
    section = FormSectionSpec(key="root", title=LocalizedText("求根", "Root solving"), fields=fields)
    fields.clear()

    assert isinstance(section.fields, tuple)
    assert [item.key for item in section.fields] == ["root.mode"]


def test_visibility_rule_in_set_materializes_iterables() -> None:
    values = (item for item in ("custom", "self_consistent"))
    rule = VisibilityRule.in_set("fit_model", values)

    assert rule.values == ("custom", "self_consistent")
    assert rule.evaluate({"fit_model": "custom"}) is True


def test_ui_specs_reexports_new_schema_types() -> None:
    from shared.ui_specs import FormFieldSpec, LocalizedText, VisibilityRule

    assert FormFieldSpec.__name__ == "FormFieldSpec"
    assert LocalizedText("中", "En").for_lang("en") == "En"
    assert VisibilityRule.equals("mode", "root").evaluate({"mode": "root"}) is True


def test_ui_specs_preserves_existing_formula_help_compatibility_names() -> None:
    import shared.ui_specs as ui_specs

    assert hasattr(ui_specs, "EXTRAPOLATION_METHODS")
    assert callable(ui_specs.get_method_parameters)
