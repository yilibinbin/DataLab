from __future__ import annotations

import subprocess
import sys
import textwrap


def test_mode_view_descriptors_cover_workbench_specs_without_duplicate_source() -> None:
    from app_desktop.views import descriptor_for_mode, mode_view_descriptors
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    descriptors = mode_view_descriptors()

    assert set(descriptors) == set(MODE_WORKBENCH_SPECS)
    for mode, spec in MODE_WORKBENCH_SPECS.items():
        descriptor = descriptors[mode]
        assert descriptor is descriptor_for_mode(mode)
        assert descriptor.spec is spec
        assert descriptor.mode_key == mode
        assert descriptor.mode_stack_index == spec.mode_stack_index
        assert descriptor.result_adapter_key == spec.result_adapter_key
        assert descriptor.required_widget_attrs == spec.required_widget_attrs()


def test_app_desktop_views_import_is_lightweight() -> None:
    code = textwrap.dedent(
        """
        import sys
        import app_desktop.views
        forbidden = [
            "PySide6",
            "PySide6.QtWidgets",
            "app_desktop.panels",
            "app_desktop.window",
        ]
        loaded = [name for name in forbidden if name in sys.modules]
        if loaded:
            raise SystemExit("forbidden imports: " + ", ".join(loaded))
        """
    )

    subprocess.run([sys.executable, "-c", code], check=True)
