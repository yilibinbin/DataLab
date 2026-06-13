from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from app_desktop.workbench_specs import (
    MODE_WORKBENCH_SPECS,
    FormulaMount,
    ModeWorkbenchSpec,
    WidgetMount,
)


def test_mode_workbench_specs_are_frozen_descriptors_only() -> None:
    assert is_dataclass(ModeWorkbenchSpec)
    spec = MODE_WORKBENCH_SPECS["fitting"]
    with pytest.raises(FrozenInstanceError):
        spec.mode_key = "changed"  # type: ignore[misc]

    forbidden_types = (QWidget, list, dict, set)
    for mode, mode_spec in MODE_WORKBENCH_SPECS.items():
        for field in fields(mode_spec):
            value = getattr(mode_spec, field.name)
            assert not isinstance(value, forbidden_types), (mode, value)
        for formula in mode_spec.formulas:
            assert isinstance(formula, FormulaMount)
            assert not isinstance(formula.editor_attr, QWidget)
        for mount in mode_spec.parameters + mode_spec.constants + mode_spec.tables:
            assert isinstance(mount, WidgetMount)
            assert not isinstance(mount.widget_attr, QWidget)


def test_mode_workbench_specs_reference_existing_window_attributes(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    expected_page_attrs = {
        "extrapolation": "extrap_box",
        "error": "error_box",
        "fitting": "fit_box",
        "root_solving": "root_box",
        "statistics": "stats_box",
    }
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        assert spec.mode_key == mode
        assert 0 <= spec.mode_stack_index < window.mode_stack.count()
        assert window.mode_stack.widget(spec.mode_stack_index) is getattr(window, expected_page_attrs[mode])
        for attr in spec.required_widget_attrs():
            assert hasattr(window, attr), f"{mode}: {attr}"
    assert sorted(spec.mode_stack_index for spec in MODE_WORKBENCH_SPECS.values()) == list(
        range(window.mode_stack.count())
    )


def test_panels_mode_page_builders_cover_specs_and_order() -> None:
    from app_desktop import panels

    expected_page_attrs = {
        "extrapolation": "extrap_box",
        "error": "error_box",
        "fitting": "fit_box",
        "root_solving": "root_box",
        "statistics": "stats_box",
    }

    assert set(panels._MODE_VIEW_BUILDERS) == set(MODE_WORKBENCH_SPECS)
    assert panels._mode_stack_order() == tuple(
        mode
        for mode, _spec in sorted(
            MODE_WORKBENCH_SPECS.items(),
            key=lambda item: item[1].mode_stack_index,
        )
    )
    for mode, (page_attr, builder) in panels._MODE_VIEW_BUILDERS.items():
        assert page_attr == expected_page_attrs[mode]
        assert callable(builder)


def test_mode_workbench_specs_reuse_bound_schema_keys(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(window, formula.editor_attr)
            button = getattr(window, formula.preview_button_attr)
            assert editor.property("datalab_schema_key") == formula.schema_key
            assert button.property("datalab_schema_key") == formula.schema_key
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(window, mount.widget_attr)
            assert widget.property("datalab_schema_key") == mount.schema_key


def test_workbench_model_path_helpers_are_canonical() -> None:
    from app_desktop.workbench_model_bindings import (
        STATE_ROLE_MODEL_PATHS,
        model_path_for_formula_schema_key,
        model_path_for_schema_key,
        model_path_for_state_role,
    )

    assert STATE_ROLE_MODEL_PATHS == {
        "manual_data_owner": "compute.data",
        "manual_table_editor": "compute.data.canonical_table",
        "manual_text_editor": "compute.data.decoded_text",
        "mode_stack_owner": "compute.current_mode",
        "result_tabs_owner": "ui.result_tabs",
    }
    assert model_path_for_state_role("mode_stack_owner") == "compute.current_mode"
    assert (
        model_path_for_state_role(
            "custom_parameters_owner",
            schema_key="fitting.custom.parameters",
        )
        == "compute.config.fitting.custom.parameters"
    )
    assert model_path_for_schema_key("root.unknowns") == "compute.config.root.unknowns"
    assert (
        model_path_for_formula_schema_key("fitting.implicit.output_expression")
        == "compute.formulas.fitting.implicit.output_expression.raw_text"
    )
    with pytest.raises(KeyError):
        model_path_for_state_role("missing_owner")
    with pytest.raises(ValueError):
        model_path_for_schema_key("")
    with pytest.raises(ValueError):
        model_path_for_formula_schema_key("")


def test_mode_workbench_specs_bind_model_paths(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workbench_model_bindings import (
        MODEL_PATH_PROPERTY,
        model_path_for_formula_schema_key,
        model_path_for_state_role,
    )

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    state_owner_attrs = {
        "manual_box": "manual_data_owner",
        "manual_table": "manual_table_editor",
        "manual_data_edit": "manual_text_editor",
        "mode_stack": "mode_stack_owner",
        "tabs": "result_tabs_owner",
    }
    for attr, state_role in state_owner_attrs.items():
        widget = getattr(window, attr)
        assert widget.property("datalab_state_role") == state_role
        assert widget.property(MODEL_PATH_PROPERTY) == model_path_for_state_role(state_role)

    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(window, formula.editor_attr)
            assert editor.property(MODEL_PATH_PROPERTY) == model_path_for_formula_schema_key(
                formula.schema_key
            )
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(window, mount.widget_attr)
            assert widget.property("datalab_state_role") == mount.state_role
            assert widget.property(MODEL_PATH_PROPERTY) == model_path_for_state_role(
                mount.state_role,
                schema_key=mount.schema_key,
            )


def test_variable_mount_state_widgets_are_not_shared_between_mode_pages() -> None:
    owners: dict[str, str] = {}
    state_roles: dict[str, str] = {}
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        for mount in spec.parameters + spec.constants + spec.tables:
            previous_mode = owners.setdefault(mount.widget_attr, mode)
            assert previous_mode == mode, (
                mount.widget_attr,
                previous_mode,
                mode,
            )
            previous_attr = state_roles.setdefault(mount.state_role, mount.widget_attr)
            assert previous_attr == mount.widget_attr, (
                mount.state_role,
                previous_attr,
                mount.widget_attr,
            )
