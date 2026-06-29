from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from datalab_core.recipes import (
    RecipeValidationError,
    build_recipe_workspace_patch,
    normalize_recipe,
    resolve_recipe_bindings,
)
from datalab_core.recipe_provenance import build_recipe_provenance

from .workspace_controller import (
    apply_error_config_to_window,
    apply_fitting_config_to_window,
    apply_root_config_to_window,
    apply_statistics_config_to_window,
)


@dataclass(frozen=True)
class RecipeInputPreview:
    role_id: str
    suggested_name: str
    role: str
    type: str
    description: str
    bound_column: str


@dataclass(frozen=True)
class RecipePreview:
    recipe_id: str
    title: str
    description: str
    family: str
    workflow_mode: str
    required_inputs: tuple[RecipeInputPreview, ...]
    exports: Mapping[str, bool]
    diagnostics: tuple[Mapping[str, str], ...]
    apply_request: Mapping[str, Any] | None


def build_recipe_preview(
    recipe: Mapping[str, Any],
    *,
    data_columns: Sequence[str],
    lang: str = "en",
    apply_request: Mapping[str, Any] | None = None,
) -> RecipePreview:
    normalized = normalize_recipe(recipe)
    resolution = resolve_recipe_bindings(
        normalized,
        data_columns=data_columns,
        apply_request=apply_request,
    )
    return RecipePreview(
        recipe_id=str(normalized["id"]),
        title=_localized(normalized.get("title"), lang=lang),
        description=_localized(normalized.get("description"), lang=lang),
        family=str(normalized["family"]),
        workflow_mode=str(normalized["workflow_mode"]),
        required_inputs=_input_previews(normalized, resolution.apply_request),
        exports=dict(normalized.get("exports") or {}),
        diagnostics=resolution.diagnostics,
        apply_request=resolution.apply_request,
    )


def apply_recipe_to_window(
    window: Any,
    recipe: Mapping[str, Any],
    *,
    apply_request: Mapping[str, Any] | None = None,
    data_columns: Sequence[str] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> dict[str, Any]:
    if (data_columns is None) != (rows is None):
        raise RecipeValidationError("data_columns and rows must be provided together")
    if data_columns is None or rows is None:
        data_columns, rows, collected_sigma_rows = _collect_window_dataset(window, precision_digits)
        if sigma_rows is None:
            sigma_rows = collected_sigma_rows
    resolved_precision = (
        precision_digits
        if precision_digits is not None
        else _widget_int(getattr(window, "mpmath_precision_spin", None), 16)
    )
    resolved_uncertainty_digits = (
        uncertainty_digits
        if uncertainty_digits is not None
        else _widget_int(getattr(window, "uncertainty_digits_spin", None), 1)
    )
    if apply_request is None:
        preview = build_recipe_preview(recipe, data_columns=data_columns)
        if preview.apply_request is None:
            raise RecipeValidationError(_diagnostic_summary(preview.diagnostics))
        apply_request = preview.apply_request

    patch = build_recipe_workspace_patch(
        recipe,
        apply_request,
        headers=data_columns,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=resolved_precision,
        uncertainty_digits=resolved_uncertainty_digits,
    )
    previous_suppression = bool(getattr(window, "_suppress_recipe_provenance_modified", False))
    window._suppress_recipe_provenance_modified = True
    try:
        _apply_recipe_patch_to_window(window, patch)
    finally:
        window._suppress_recipe_provenance_modified = previous_suppression
    normalized_recipe = normalize_recipe(recipe)
    config = patch.get("config")
    if not isinstance(config, Mapping):
        raise RecipeValidationError("recipe patch config is invalid")
    window._workspace_provenance = {
        "recipe": build_recipe_provenance(
            recipe_id=str(normalized_recipe["id"]),
            recipe_schema_version=int(normalized_recipe["schema_version"]),
            recipe_payload=normalized_recipe,
            apply_request=apply_request,
            generated_config=config,
        )
    }
    return patch


def _input_previews(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any] | None,
) -> tuple[RecipeInputPreview, ...]:
    bound_data = _bound_data_columns(apply_request)
    required_columns = recipe["inputs"]["data"]["required_columns"]
    previews: list[RecipeInputPreview] = []
    for role in required_columns:
        if not isinstance(role, Mapping):
            continue
        role_id = str(role["id"])
        previews.append(
            RecipeInputPreview(
                role_id=role_id,
                suggested_name=str(role.get("suggested_name") or ""),
                role=str(role.get("role") or ""),
                type=str(role.get("type") or ""),
                description=str(role.get("description") or ""),
                bound_column=bound_data.get(role_id, ""),
            )
        )
    return tuple(previews)


def _bound_data_columns(apply_request: Mapping[str, Any] | None) -> dict[str, str]:
    if apply_request is None:
        return {}
    inputs = apply_request.get("bindings", {}).get("inputs", {})
    data = inputs.get("data", {}) if isinstance(inputs, Mapping) else {}
    if not isinstance(data, Mapping):
        return {}
    bound: dict[str, str] = {}
    for role, binding in data.items():
        if isinstance(binding, Mapping) and binding.get("kind") == "data_column":
            bound[str(role)] = str(binding.get("column_id") or "")
    return bound


def _localized(value: Any, *, lang: str) -> str:
    if not isinstance(value, Mapping) or not value:
        return ""
    for key in (lang, lang.split("_", 1)[0], lang.split("-", 1)[0], "en", "zh"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text
    for text in value.values():
        if isinstance(text, str) and text.strip():
            return text
    return ""


def _collect_window_dataset(
    window: Any,
    precision_digits: int | None,
) -> tuple[Sequence[str], Sequence[Sequence[Any]], Sequence[Sequence[Any | None]] | None]:
    collector = getattr(window, "_collect_fitting_dataset", None)
    if not callable(collector):
        raise RecipeValidationError("window cannot provide recipe input data")
    headers, rows, sigma_rows = collector(
        precision_hint=(
            precision_digits
            if precision_digits is not None
            else _widget_int(getattr(window, "mpmath_precision_spin", None), 16)
        )
    )
    return headers, rows, sigma_rows


def _apply_recipe_patch_to_window(window: Any, patch: Mapping[str, Any]) -> None:
    mode = str(patch.get("current_mode") or "")
    config = patch.get("config")
    if not isinstance(config, Mapping):
        raise RecipeValidationError("recipe patch config is invalid")
    config_section, section_config = _validated_patch_section(mode, config)
    if mode:
        _set_combo_data(getattr(window, "mode_combo", None), mode)
        mode_change = getattr(window, "_on_mode_change", None)
        if callable(mode_change):
            mode_change()
    if config_section == "statistics":
        apply_statistics_config_to_window(window, section_config)
    elif config_section == "error":
        apply_error_config_to_window(window, section_config)
    elif config_section == "root_solving":
        apply_root_config_to_window(window, section_config)
    elif config_section == "fitting":
        apply_fitting_config_to_window(window, section_config)
    else:
        raise RecipeValidationError(f"recipe patch mode is unsupported: {mode}")
    dirty_marker = getattr(window, "_mark_workspace_dirty", None)
    if callable(dirty_marker):
        dirty_marker()
    elif hasattr(window, "_workspace_dirty"):
        window._workspace_dirty = True


def _validated_patch_section(mode: str, config: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    if mode == "statistics":
        statistics = config.get("statistics")
        if not isinstance(statistics, Mapping):
            raise RecipeValidationError("recipe patch statistics config is invalid")
        return "statistics", statistics
    if mode == "error":
        error = config.get("error")
        if not isinstance(error, Mapping):
            raise RecipeValidationError("recipe patch error config is invalid")
        return "error", error
    if mode == "root_solving":
        root_solving = config.get("root_solving")
        if not isinstance(root_solving, Mapping):
            raise RecipeValidationError("recipe patch root_solving config is invalid")
        return "root_solving", root_solving
    if mode == "fitting":
        fitting = config.get("fitting")
        if not isinstance(fitting, Mapping):
            raise RecipeValidationError("recipe patch fitting config is invalid")
        return "fitting", fitting
    raise RecipeValidationError(f"recipe patch mode is unsupported: {mode}")


def _set_combo_data(combo: Any, value: str) -> None:
    if combo is None:
        return
    index = combo.findData(value) if hasattr(combo, "findData") else -1
    if index < 0 and hasattr(combo, "findText"):
        index = combo.findText(value)
    if index >= 0 and hasattr(combo, "setCurrentIndex"):
        combo.setCurrentIndex(index)


def _widget_int(widget: Any, default: int) -> int:
    if widget is None or not hasattr(widget, "value"):
        return default
    try:
        return int(widget.value())
    except (TypeError, ValueError, OverflowError):
        return default


def _diagnostic_summary(diagnostics: Sequence[Mapping[str, str]]) -> str:
    if not diagnostics:
        return "recipe bindings are unresolved"
    return "; ".join(str(diagnostic.get("message") or diagnostic) for diagnostic in diagnostics)


__all__ = [
    "RecipeInputPreview",
    "RecipePreview",
    "apply_recipe_to_window",
    "build_recipe_preview",
]
