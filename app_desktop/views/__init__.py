from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS
from app_desktop.workbench_specs import ModeKey, ModeWorkbenchSpec, ResultAdapterKey


@dataclass(frozen=True, slots=True)
class ModeViewDescriptor:
    """Future per-mode view boundary derived from the workbench spec."""

    mode_key: ModeKey
    spec: ModeWorkbenchSpec

    @property
    def mode_stack_index(self) -> int:
        return self.spec.mode_stack_index

    @property
    def result_adapter_key(self) -> ResultAdapterKey:
        return self.spec.result_adapter_key

    @property
    def required_widget_attrs(self) -> tuple[str, ...]:
        return self.spec.required_widget_attrs()


_MODE_VIEW_DESCRIPTORS: dict[ModeKey, ModeViewDescriptor] = {
    mode: ModeViewDescriptor(mode_key=mode, spec=spec)
    for mode, spec in MODE_WORKBENCH_SPECS.items()
}


def mode_view_descriptors() -> Mapping[ModeKey, ModeViewDescriptor]:
    return dict(_MODE_VIEW_DESCRIPTORS)


def descriptor_for_mode(mode: ModeKey) -> ModeViewDescriptor:
    return _MODE_VIEW_DESCRIPTORS[mode]


__all__ = [
    "ModeViewDescriptor",
    "descriptor_for_mode",
    "mode_view_descriptors",
]
