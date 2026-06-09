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
