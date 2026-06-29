from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModeKey = Literal["extrapolation", "error", "fitting", "root_solving", "statistics"]
ResultAdapterKey = Literal["tabular", "text", "plot", "latex", "pdf", "none"]


@dataclass(frozen=True, slots=True)
class FormulaMount:
    editor_attr: str
    preview_button_attr: str
    schema_key: str
    lhs: str | None = None


@dataclass(frozen=True, slots=True)
class WidgetMount:
    widget_attr: str
    schema_key: str
    role: str
    state_role: str
    companion_attrs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModeWorkbenchSpec:
    mode_key: ModeKey
    mode_stack_index: int
    formulas: tuple[FormulaMount, ...] = ()
    parameters: tuple[WidgetMount, ...] = ()
    constants: tuple[WidgetMount, ...] = ()
    tables: tuple[WidgetMount, ...] = ()
    result_adapter_key: ResultAdapterKey = "tabular"

    def required_widget_attrs(self) -> tuple[str, ...]:
        attrs: list[str] = []
        for formula in self.formulas:
            attrs.extend((formula.editor_attr, formula.preview_button_attr))
        for mount in self.parameters + self.constants + self.tables:
            attrs.append(mount.widget_attr)
            attrs.extend(mount.companion_attrs)
        return tuple(dict.fromkeys(attrs))


MODE_WORKBENCH_SPECS: dict[ModeKey, ModeWorkbenchSpec] = {
    "extrapolation": ModeWorkbenchSpec(
        mode_key="extrapolation",
        mode_stack_index=0,
        formulas=(
            FormulaMount(
                "custom_formula_edit",
                "custom_formula_preview_button",
                "extrapolation.custom.formula",
            ),
        ),
        result_adapter_key="tabular",
    ),
    "error": ModeWorkbenchSpec(
        mode_key="error",
        mode_stack_index=1,
        formulas=(
            FormulaMount(
                "formula_edit",
                "error_formula_preview_button",
                "error.formula",
            ),
        ),
        constants=(),
        result_adapter_key="tabular",
    ),
    "fitting": ModeWorkbenchSpec(
        mode_key="fitting",
        mode_stack_index=2,
        formulas=(
            FormulaMount(
                "fit_expr_edit",
                "fit_formula_preview_button",
                "fitting.custom.expression",
                lhs="y",
            ),
            FormulaMount(
                "implicit_equation_edit",
                "implicit_equation_preview_button",
                "fitting.implicit.equation",
            ),
            FormulaMount(
                "implicit_output_edit",
                "implicit_output_preview_button",
                "fitting.implicit.output_expression",
                lhs="y",
            ),
        ),
        parameters=(
            WidgetMount(
                "custom_params_table",
                "fitting.custom.parameters",
                "parameters",
                "custom_parameters_owner",
                companion_attrs=("custom_param_header_widget", "custom_constraints_checkbox"),
            ),
            WidgetMount(
                "implicit_params_table",
                "fitting.implicit.parameters",
                "parameters",
                "implicit_parameters_owner",
                companion_attrs=("implicit_param_header_widget", "implicit_constraints_checkbox"),
            ),
        ),
        constants=(),
        result_adapter_key="tabular",
    ),
    "root_solving": ModeWorkbenchSpec(
        mode_key="root_solving",
        mode_stack_index=3,
        formulas=(
            FormulaMount(
                "root_equations_edit",
                "root_formula_preview_button",
                "root.equations",
                lhs="F",
            ),
        ),
        tables=(
            WidgetMount(
                "root_unknowns_table",
                "root.unknowns",
                "unknowns",
                "root_unknowns_owner",
                companion_attrs=("root_unknown_header_widget",),
            ),
        ),
        constants=(),
        result_adapter_key="tabular",
    ),
    "statistics": ModeWorkbenchSpec(
        mode_key="statistics",
        mode_stack_index=4,
        result_adapter_key="tabular",
    ),
}
