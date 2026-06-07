from shared.ui_schema import FormFieldSpec, FormSectionSpec, PlotSpec, ResultViewSpec
from shared.ui_specs import (
    DESKTOP_FORM_SECTIONS,
    DESKTOP_PLOT_SPECS,
    DESKTOP_RESULT_VIEWS,
    ERROR_FORMULA_FIELD,
    EXTRAPOLATION_METHOD_SPECS,
)


def test_error_formula_field_uses_direct_form_schema() -> None:
    assert isinstance(ERROR_FORMULA_FIELD, FormFieldSpec)
    assert ERROR_FORMULA_FIELD.key == "error.formula"
    assert ERROR_FORMULA_FIELD.label.for_lang("zh")
    assert ERROR_FORMULA_FIELD.label.for_lang("en")
    assert ERROR_FORMULA_FIELD.placeholder.for_lang("zh")
    assert ERROR_FORMULA_FIELD.placeholder.for_lang("en")
    assert ERROR_FORMULA_FIELD.tooltip.for_lang("zh")
    assert ERROR_FORMULA_FIELD.tooltip.for_lang("en")


def test_desktop_form_sections_contains_core_sections() -> None:
    expected = {
        "input",
        "extrapolation",
        "error",
        "fitting",
        "root_solving",
        "statistics",
        "options",
    }

    assert expected <= set(DESKTOP_FORM_SECTIONS)
    assert all(isinstance(DESKTOP_FORM_SECTIONS[key], FormSectionSpec) for key in expected)


def test_desktop_result_views_contains_core_result_types() -> None:
    expected = {"result.numeric", "result.image", "result.latex", "result.pdf"}

    assert expected <= set(DESKTOP_RESULT_VIEWS)
    assert "result.log" in DESKTOP_RESULT_VIEWS
    assert all(isinstance(DESKTOP_RESULT_VIEWS[key], ResultViewSpec) for key in expected)
    assert [field.key for field in DESKTOP_RESULT_VIEWS["result.numeric"].controls] == [
        "results.display.scientific",
        "results.display.decimal_places",
        "results.export.csv",
    ]
    assert {
        field.key for field in DESKTOP_RESULT_VIEWS["result.image"].controls
    } >= {"results.image.zoom_percent", "results.image.export", "results.image.page"}
    assert {
        field.key for field in DESKTOP_RESULT_VIEWS["result.latex"].controls
    } >= {"results.latex.open", "results.latex.save", "latex.compile", "latex.engine"}
    assert {
        field.key for field in DESKTOP_RESULT_VIEWS["result.pdf"].controls
    } >= {"pdf.zoom_percent", "pdf.zoom_in", "pdf.zoom_out", "pdf.zoom_reset"}


def test_desktop_plot_specs_contains_shared_registry_keys() -> None:
    expected = {
        "input",
        "extrapolation",
        "error",
        "fitting",
        "root_solving",
        "statistics",
        "options",
        "result.numeric",
        "result.image",
        "result.log",
        "result.latex",
        "result.pdf",
    }

    assert expected <= set(DESKTOP_PLOT_SPECS)
    assert all(isinstance(DESKTOP_PLOT_SPECS[key], PlotSpec) for key in expected)


def test_method_specs_are_backed_by_form_sections_and_fields() -> None:
    levin_group = EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0]

    assert isinstance(levin_group, FormSectionSpec)
    assert all(isinstance(field, FormFieldSpec) for field in levin_group.fields)
    assert [field.key for field in levin_group.fields] == ["variant", "order", "weight", "beta"]


def test_legacy_widget_classes_do_not_drive_public_runtime_metadata() -> None:
    import shared.ui_specs as ui_specs

    legacy_names = {
        "WidgetSpec",
        "TextWidgetSpec",
        "NumberWidgetSpec",
        "SelectWidgetSpec",
        "TextAreaWidgetSpec",
        "ParameterGroupSpec",
    }

    assert legacy_names.isdisjoint(set(ui_specs.__all__))
    assert all(not hasattr(ui_specs, name) for name in legacy_names)


def test_shared_package_does_not_reexport_legacy_widget_aliases() -> None:
    import shared

    legacy_names = {
        "WidgetSpec",
        "TextWidgetSpec",
        "NumberWidgetSpec",
        "SelectWidgetSpec",
        "TextAreaWidgetSpec",
        "ParameterGroupSpec",
    }

    assert legacy_names.isdisjoint(set(shared.__all__))
    assert all(not hasattr(shared, name) for name in legacy_names)
