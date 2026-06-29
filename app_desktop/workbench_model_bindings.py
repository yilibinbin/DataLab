from __future__ import annotations

from typing import Any


MODEL_PATH_PROPERTY = "datalab_model_path"

STATE_ROLE_MODEL_PATHS: dict[str, str] = {
    "input_constants_owner": "compute.constants",
    "manual_data_owner": "compute.data",
    "manual_table_editor": "compute.data.canonical_table",
    "manual_text_editor": "compute.data.decoded_text",
    "mode_stack_owner": "compute.current_mode",
    "result_tabs_owner": "ui.result_tabs",
}


def bind_model_path(widget: Any, model_path: str) -> None:
    setter = getattr(widget, "setProperty", None)
    if callable(setter):
        setter(MODEL_PATH_PROPERTY, model_path)


def model_path_for_state_role(role: str, *, schema_key: str | None = None) -> str:
    if role in STATE_ROLE_MODEL_PATHS:
        return STATE_ROLE_MODEL_PATHS[role]
    if schema_key:
        return model_path_for_schema_key(schema_key)
    raise KeyError(f"No model path registered for state role {role!r}.")


def model_path_for_schema_key(schema_key: str) -> str:
    if not schema_key:
        raise ValueError("schema_key must not be empty.")
    return f"compute.config.{schema_key}"


def model_path_for_formula_schema_key(schema_key: str) -> str:
    if not schema_key:
        raise ValueError("schema_key must not be empty.")
    return f"compute.formulas.{schema_key}.raw_text"
