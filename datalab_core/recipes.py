from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .jobs import JobMode

RECIPE_SCHEMA = "datalab.recipe.v1"
RECIPE_SCHEMA_VERSION = 1
RECIPE_APPLY_SCHEMA = "datalab.recipe.apply.v1"
RECIPE_APPLY_SCHEMA_VERSION = 1

MAX_RECIPE_BYTES = 512 * 1024
MAX_NESTING_DEPTH = 16
MAX_ITEMS_PER_LEVEL = 256
MAX_INPUT_ROLES = 64
MAX_PLACEHOLDERS = 128
MAX_LOCALIZED_TEXT_LENGTH = 4096

RECIPE_INPUT_NAMESPACES = ("data", "constants", "parameters", "unknowns", "variables")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RECIPE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_LOCALE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
_PLACEHOLDER_RE = re.compile(
    r"^\$\{inputs\.(data|constants|parameters|unknowns|variables)\.([A-Za-z_][A-Za-z0-9_]*)\}$"
)

_TOP_LEVEL_KEYS = {
    "schema",
    "schema_version",
    "id",
    "title",
    "description",
    "family",
    "workflow_mode",
    "inputs",
    "configuration",
    "exports",
    "examples",
}
_APPLY_TOP_LEVEL_KEYS = {"schema", "schema_version", "recipe_id", "bindings"}
_INPUT_TOP_LEVEL_KEYS = set(RECIPE_INPUT_NAMESPACES)
_DATA_INPUT_KEYS = {"required_columns"}
_ROLE_DECLARATION_KEYS = {"id", "suggested_name", "role", "type", "description"}
_ROLE_TYPES = {
    "number",
    "number_with_uncertainty",
    "text",
    "category",
}
_DATA_ROLES = {"value", "sigma", "weight", "group", "time", "x", "y"}
_EXPORT_KEYS = {"latex", "plots", "report_bundle"}
_EXAMPLE_KEYS = {"workspace"}
_CONFIGURATION_TOP_LEVEL_KEYS = {"statistics", "error", "root_solving", "fitting"}
_STATISTICS_CONFIG_KEYS = {"value_column", "sigma_column", "mode"}
_STATISTICS_COLUMN_FIELDS = {"value_column", "sigma_column"}
_STATISTICS_MODES = {"mean", "mean_sample", "mean_population", "descriptive", "weighted_sigma"}
_ERROR_CONFIG_KEYS = {"formula", "method", "order", "mc_samples", "mc_seed", "collect_monte_carlo_distribution"}
_ERROR_METHODS = {"taylor", "monte_carlo"}
_EXPRESSION_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_DEFAULT_ERROR_MC_SAMPLES = 5000
_ROOT_CONFIG_KEYS = {"equations", "mode", "unknowns", "uncertainty_options"}
_ROOT_MODES = {"auto", "scalar", "polynomial", "system", "scan_multiple"}
_ROOT_UNKNOWN_KEYS = {"name", "initial", "lower", "upper", "source"}
_ROOT_UNKNOWN_SOURCES = {"manual", "detected"}
_ROOT_UNCERTAINTY_KEYS = {"method", "taylor_order", "monte_carlo_samples", "monte_carlo_seed"}
_ROOT_UNCERTAINTY_METHODS = {"off", "taylor", "monte_carlo"}
_FITTING_CONFIG_KEYS = {
    "model",
    "expression",
    "variables",
    "target_column",
    "weighted",
    "constraints_enabled",
    "parameter_rows",
}
_FITTING_MODELS = {"custom"}
_FITTING_VARIABLE_KEYS = {"name", "column"}
_FITTING_PARAMETER_KEYS = {"name", "initial", "fixed", "min", "max"}


class RecipeValidationError(ValueError):
    """Raised when a declarative recipe or apply request is malformed."""


@dataclass(frozen=True)
class WorkflowRoute:
    family: str
    workflow_mode: str
    current_mode: str
    config_section: str
    job_mode: JobMode
    result_family: str
    accepted_binding_namespaces: frozenset[str]


@dataclass(frozen=True)
class RecipeBindingResolution:
    apply_request: Mapping[str, Any] | None
    diagnostics: tuple[Mapping[str, str], ...]

    @property
    def is_complete(self) -> bool:
        return self.apply_request is not None and not self.diagnostics


_WORKFLOW_ROUTES: dict[tuple[str, str], WorkflowRoute] = {
    ("statistics", "statistics.standard"): WorkflowRoute(
        family="statistics",
        workflow_mode="statistics.standard",
        current_mode="statistics",
        config_section="statistics",
        job_mode=JobMode.STATISTICS,
        result_family="statistics",
        accepted_binding_namespaces=frozenset({"data"}),
    ),
    ("error", "error.standard"): WorkflowRoute(
        family="error",
        workflow_mode="error.standard",
        current_mode="error",
        config_section="error",
        job_mode=JobMode.UNCERTAINTY,
        result_family="uncertainty",
        accepted_binding_namespaces=frozenset({"data"}),
    ),
    ("root_solving", "root.standard"): WorkflowRoute(
        family="root_solving",
        workflow_mode="root.standard",
        current_mode="root_solving",
        config_section="root_solving",
        job_mode=JobMode.ROOT_SOLVING,
        result_family="root_solving",
        accepted_binding_namespaces=frozenset({"data"}),
    ),
    ("fitting", "fitting.custom"): WorkflowRoute(
        family="fitting",
        workflow_mode="fitting.custom",
        current_mode="fitting",
        config_section="fitting",
        job_mode=JobMode.FITTING,
        result_family="fitting",
        accepted_binding_namespaces=frozenset({"data"}),
    ),
}


def recipe_workflow_route(family: str, workflow_mode: str) -> WorkflowRoute:
    try:
        return _WORKFLOW_ROUTES[(family, workflow_mode)]
    except KeyError as exc:
        raise RecipeValidationError(f"unsupported recipe workflow: {family}.{workflow_mode}") from exc


def loads_recipe_json(data: str | bytes | bytearray) -> dict[str, Any]:
    payload = _loads_json_payload(data, kind="recipe")
    return normalize_recipe(payload)


def loads_recipe_apply_json(
    data: str | bytes | bytearray,
    *,
    recipe_id: str | None = None,
    declared_roles: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    payload = _loads_json_payload(data, kind="recipe apply request")
    return normalize_recipe_apply_request(payload, recipe_id=recipe_id, declared_roles=declared_roles)


def normalize_recipe(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RecipeValidationError("recipe must be a JSON object")
    _enforce_resource_limits(raw, path="recipe")
    _reject_json_floats(raw, path="recipe")
    _reject_unknown_keys(raw, _TOP_LEVEL_KEYS, path="recipe")

    schema = _optional_text(raw.get("schema"), default=RECIPE_SCHEMA, field_name="schema", max_length=64)
    if schema != RECIPE_SCHEMA:
        raise RecipeValidationError(f"schema must be {RECIPE_SCHEMA!r}")
    schema_version = _optional_int(raw.get("schema_version"), default=RECIPE_SCHEMA_VERSION, field_name="schema_version")
    if schema_version != RECIPE_SCHEMA_VERSION:
        raise RecipeValidationError("schema_version must be 1")

    recipe_id = _recipe_id_text(raw.get("id"), field_name="id")
    title = _localized_text(raw.get("title"), field_name="title", required=True)
    description = _localized_text(raw.get("description"), field_name="description", required=False)
    family = _plain_text(raw.get("family"), field_name="family", max_length=64)
    workflow_mode = _plain_text(raw.get("workflow_mode"), field_name="workflow_mode", max_length=128)
    route = recipe_workflow_route(family, workflow_mode)

    inputs = _normalize_inputs(raw.get("inputs"))
    _reject_unsupported_input_namespaces(inputs, route=route)
    declared_roles = declared_recipe_roles_from_inputs(inputs)
    configuration = _normalize_configuration(raw.get("configuration"), route=route, declared_roles=declared_roles)
    exports = _normalize_exports(raw.get("exports"))
    examples = _normalize_examples(raw.get("examples"))

    return {
        "schema": RECIPE_SCHEMA,
        "schema_version": RECIPE_SCHEMA_VERSION,
        "id": recipe_id,
        "title": title,
        "description": description,
        "family": route.family,
        "workflow_mode": route.workflow_mode,
        "inputs": inputs,
        "configuration": configuration,
        "exports": exports,
        "examples": examples,
    }


def normalize_recipe_apply_request(
    raw: Mapping[str, Any],
    *,
    recipe_id: str | None = None,
    declared_roles: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RecipeValidationError("recipe apply request must be a JSON object")
    _enforce_resource_limits(raw, path="recipe_apply")
    _reject_json_floats(raw, path="recipe_apply")
    _reject_unknown_keys(raw, _APPLY_TOP_LEVEL_KEYS, path="recipe_apply")

    schema = _optional_text(
        raw.get("schema"),
        default=RECIPE_APPLY_SCHEMA,
        field_name="schema",
        max_length=64,
    )
    if schema != RECIPE_APPLY_SCHEMA:
        raise RecipeValidationError(f"schema must be {RECIPE_APPLY_SCHEMA!r}")
    schema_version = _optional_int(
        raw.get("schema_version"),
        default=RECIPE_APPLY_SCHEMA_VERSION,
        field_name="schema_version",
    )
    if schema_version != RECIPE_APPLY_SCHEMA_VERSION:
        raise RecipeValidationError("schema_version must be 1")

    apply_recipe_id = _recipe_id_text(raw.get("recipe_id"), field_name="recipe_id")
    if recipe_id is not None and apply_recipe_id != recipe_id:
        raise RecipeValidationError("recipe_id does not match the recipe being applied")
    role_lookup = _declared_role_lookup(declared_roles)
    bindings = _normalize_apply_bindings(raw.get("bindings"), declared_roles=role_lookup)
    return {
        "schema": RECIPE_APPLY_SCHEMA,
        "schema_version": RECIPE_APPLY_SCHEMA_VERSION,
        "recipe_id": apply_recipe_id,
        "bindings": bindings,
    }


def declared_recipe_roles(recipe: Mapping[str, Any]) -> dict[str, set[str]]:
    inputs = recipe.get("inputs") if isinstance(recipe, Mapping) else None
    if not isinstance(inputs, Mapping):
        raise RecipeValidationError("recipe.inputs must be an object")
    return declared_recipe_roles_from_inputs(inputs)


def declared_recipe_roles_from_inputs(inputs: Mapping[str, Any]) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {namespace: set() for namespace in RECIPE_INPUT_NAMESPACES}
    data = inputs.get("data") if isinstance(inputs, Mapping) else None
    if isinstance(data, Mapping):
        for role in data.get("required_columns") or []:
            if isinstance(role, Mapping) and isinstance(role.get("id"), str):
                roles["data"].add(role["id"])
    for namespace in ("constants", "parameters", "unknowns", "variables"):
        value = inputs.get(namespace) if isinstance(inputs, Mapping) else None
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
            for role in value:
                if isinstance(role, Mapping) and isinstance(role.get("id"), str):
                    roles[namespace].add(role["id"])
    return roles


def resolve_recipe_bindings(
    recipe: Mapping[str, Any],
    *,
    data_columns: Sequence[str],
    apply_request: Mapping[str, Any] | None = None,
) -> RecipeBindingResolution:
    normalized_recipe = normalize_recipe(recipe)
    columns = _normalize_data_columns(data_columns)
    column_counts = Counter(columns)
    declared = declared_recipe_roles(normalized_recipe)
    supplied = (
        normalize_recipe_apply_request(
            apply_request,
            recipe_id=str(normalized_recipe["id"]),
            declared_roles=declared,
        )
        if apply_request is not None
        else _empty_apply_request(str(normalized_recipe["id"]))
    )
    supplied_data = supplied["bindings"]["inputs"]["data"]
    if not isinstance(supplied_data, Mapping):
        raise RecipeValidationError("bindings.inputs.data must be an object")

    diagnostics: list[dict[str, str]] = []
    resolved_data: dict[str, dict[str, str]] = {}
    required_columns = normalized_recipe["inputs"]["data"]["required_columns"]
    for role in required_columns:
        if not isinstance(role, Mapping):
            continue
        role_id = str(role["id"])
        supplied_binding = supplied_data.get(role_id)
        if isinstance(supplied_binding, Mapping):
            column_id = str(supplied_binding.get("column_id") or "")
            column_count = column_counts.get(column_id, 0)
            if column_count == 0:
                diagnostics.append(
                    _binding_diagnostic(
                        code="binding_column_missing",
                        role=role_id,
                        message=f"Bound column is not available: {column_id}",
                    )
                )
                continue
            if column_count > 1:
                diagnostics.append(
                    _binding_diagnostic(
                        code="binding_column_ambiguous",
                        role=role_id,
                        message=f"Bound column is ambiguous: {column_id}",
                        suggested_name=column_id,
                    )
                )
                continue
            resolved_data[role_id] = {"kind": "data_column", "column_id": column_id}
            continue
        suggested = str(role.get("suggested_name") or "")
        if suggested and column_counts.get(suggested, 0) == 1:
            resolved_data[role_id] = {"kind": "data_column", "column_id": suggested}
            continue
        if suggested and column_counts.get(suggested, 0) > 1:
            diagnostics.append(
                _binding_diagnostic(
                    code="binding_column_ambiguous",
                    role=role_id,
                    message=f"Suggested column is ambiguous: {suggested}",
                    suggested_name=suggested,
                )
            )
            continue
        diagnostics.append(
            _binding_diagnostic(
                code="binding_required",
                role=role_id,
                message=f"Column binding is required for recipe role: {role_id}",
                suggested_name=suggested,
            )
        )

    if diagnostics:
        return RecipeBindingResolution(apply_request=None, diagnostics=tuple(diagnostics))
    completed = normalize_recipe_apply_request(
        {
            "schema": RECIPE_APPLY_SCHEMA,
            "schema_version": RECIPE_APPLY_SCHEMA_VERSION,
            "recipe_id": normalized_recipe["id"],
            "bindings": {"inputs": {"data": resolved_data}},
        },
        recipe_id=str(normalized_recipe["id"]),
        declared_roles=declared,
    )
    return RecipeBindingResolution(apply_request=completed, diagnostics=())


def build_recipe_workspace_patch(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    headers: Sequence[str] | None = None,
    data_headers: Sequence[str] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> dict[str, Any]:
    resolved_headers = _patch_headers(headers=headers, data_headers=data_headers)
    if resolved_headers is None:
        raise RecipeValidationError("headers are required before applying a recipe workspace patch")
    if rows is None:
        raise RecipeValidationError("rows are required before applying a recipe workspace patch")
    patch = _build_recipe_workspace_config_patch(
        recipe,
        apply_request,
        data_headers=resolved_headers,
    )
    route = _route_for_recipe(recipe)
    if route.config_section == "statistics":
        _build_statistics_requests_from_patch(
            recipe,
            patch,
            headers=resolved_headers,
            rows=rows,
            sigma_rows=sigma_rows,
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        )
    elif route.config_section == "root_solving":
        _build_root_solving_request_from_patch(
            recipe,
            patch,
            headers=resolved_headers,
            rows=rows,
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        )
    elif route.config_section == "fitting":
        _build_fitting_request_from_patch(
            recipe,
            patch,
            headers=resolved_headers,
            rows=rows,
            sigma_rows=sigma_rows,
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        )
    elif route.config_section == "error":
        _build_uncertainty_request_from_patch(
            recipe,
            patch,
            headers=resolved_headers,
            rows=rows,
            sigma_rows=sigma_rows,
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        )
    else:
        raise RecipeValidationError(f"unsupported recipe config section: {route.config_section}")
    return patch


def _build_recipe_workspace_config_patch(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    data_headers: Sequence[str],
) -> dict[str, Any]:
    normalized_recipe = normalize_recipe(recipe)
    resolution = resolve_recipe_bindings(
        normalized_recipe,
        data_columns=data_headers,
        apply_request=apply_request,
    )
    if not resolution.is_complete:
        raise RecipeValidationError(_unresolved_binding_error(resolution.diagnostics))
    normalized_apply = resolution.apply_request
    if normalized_apply is None:
        raise RecipeValidationError("recipe bindings are unresolved")
    _require_apply_bindings_for_required_roles(normalized_recipe, normalized_apply)
    route = recipe_workflow_route(str(normalized_recipe["family"]), str(normalized_recipe["workflow_mode"]))
    if route.config_section == "statistics":
        section_config = _resolved_statistics_config(normalized_recipe, normalized_apply)
    elif route.config_section == "error":
        section_config = _resolved_error_config(normalized_recipe, normalized_apply)
    elif route.config_section == "root_solving":
        section_config = _resolved_root_solving_config(normalized_recipe, normalized_apply)
    elif route.config_section == "fitting":
        section_config = _resolved_fitting_config(normalized_recipe, normalized_apply)
    else:
        raise RecipeValidationError(f"unsupported recipe config section: {route.config_section}")
    return {
        "current_mode": route.current_mode,
        "config": {route.config_section: section_config},
    }


def build_recipe_statistics_requests(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> tuple[Any, ...]:
    patch = _build_recipe_workspace_config_patch(recipe, apply_request, data_headers=headers)
    return _build_statistics_requests_from_patch(
        recipe,
        patch,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
    )


def build_recipe_uncertainty_request(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    patch = _build_recipe_workspace_config_patch(recipe, apply_request, data_headers=headers)
    return _build_uncertainty_request_from_patch(
        recipe,
        patch,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
    )


def build_recipe_root_solving_request(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    patch = _build_recipe_workspace_config_patch(recipe, apply_request, data_headers=headers)
    return _build_root_solving_request_from_patch(
        recipe,
        patch,
        headers=headers,
        rows=rows,
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
    )


def build_recipe_fitting_request(
    recipe: Mapping[str, Any],
    apply_request: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    patch = _build_recipe_workspace_config_patch(recipe, apply_request, data_headers=headers)
    return _build_fitting_request_from_patch(
        recipe,
        patch,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
    )


def _build_statistics_requests_from_patch(
    recipe: Mapping[str, Any],
    patch: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> tuple[Any, ...]:
    statistics = patch["config"]["statistics"]
    if not isinstance(statistics, Mapping):
        raise RecipeValidationError("recipe statistics config did not resolve to an object")
    from .statistics import build_multi_column_statistics_requests

    requests = build_multi_column_statistics_requests(
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        value_columns=str(statistics["value_column"]),
        sigma_col=str(statistics.get("sigma_column") or "") or None,
        stats_mode=str(statistics["mode"]),
        use_sample=bool(statistics["sample"]),
        use_weighted_variance=bool(statistics["weighted_variance"]),
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
        request_id_prefix=f"recipe-{normalized_recipe_id(recipe)}",
    )
    return cast(tuple[Any, ...], requests)


def _build_uncertainty_request_from_patch(
    recipe: Mapping[str, Any],
    patch: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    error_config = patch["config"]["error"]
    if not isinstance(error_config, Mapping):
        raise RecipeValidationError("recipe error config did not resolve to an object")
    from .uncertainty import build_uncertainty_request

    return build_uncertainty_request(
        headers=headers,
        rows=rows,
        formula=str(error_config["formula"]),
        uncertainty_rows=sigma_rows,
        constants={},
        propagation_method=str(error_config["method"]),
        propagation_order=_optional_int_from_config(error_config.get("order"), default=1, field_name="config.error.order"),
        mc_samples=_optional_int_or_none_from_config(
            error_config.get("mc_samples"),
            field_name="config.error.mc_samples",
        ),
        mc_seed=_optional_int_or_none_from_config(
            error_config.get("mc_seed"),
            field_name="config.error.mc_seed",
        ),
        collect_monte_carlo_distribution=bool(error_config.get("collect_monte_carlo_distribution", False)),
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
        request_id=f"recipe-{normalized_recipe_id(recipe)}",
    )


def _build_root_solving_request_from_patch(
    recipe: Mapping[str, Any],
    patch: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    root_config = patch["config"]["root_solving"]
    if not isinstance(root_config, Mapping):
        raise RecipeValidationError("recipe root_solving config did not resolve to an object")
    from .root_solving import build_root_solving_request

    return build_root_solving_request(
        equations=_root_config_equations(root_config),
        unknown_rows=_root_config_unknowns(root_config),
        data_headers=headers,
        data_rows=rows,
        constants_enabled=False,
        constants_rows=(),
        mode=str(root_config["mode"]),
        scan_config={},
        uncertainty_options=_root_config_uncertainty_options(root_config),
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
        request_id=f"recipe-{normalized_recipe_id(recipe)}",
    )


def _build_fitting_request_from_patch(
    recipe: Mapping[str, Any],
    patch: Mapping[str, Any],
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
) -> Any:
    fitting_config = patch["config"]["fitting"]
    if not isinstance(fitting_config, Mapping):
        raise RecipeValidationError("recipe fitting config did not resolve to an object")
    from .fitting import build_fitting_request

    variable_map = _fitting_variable_map(fitting_config)
    parameter_config = _fitting_parameter_config(fitting_config)
    return build_fitting_request(
        model_type=str(fitting_config["model"]),
        headers=headers,
        data_rows=rows,
        variable_map=variable_map,
        target_column=str(fitting_config["target_column"]),
        model_expr=str(fitting_config["expression"]),
        sigma_rows=sigma_rows,
        parameter_config=parameter_config,
        parameter_names=tuple(parameter_config),
        weighted=bool(fitting_config.get("weighted", False)),
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
        request_id=f"recipe-{normalized_recipe_id(recipe)}",
    )


def _patch_headers(
    *,
    headers: Sequence[str] | None,
    data_headers: Sequence[str] | None,
) -> Sequence[str] | None:
    if headers is not None and data_headers is not None:
        raise RecipeValidationError("pass either headers or data_headers, not both")
    return headers if headers is not None else data_headers


def normalized_recipe_id(recipe: Mapping[str, Any]) -> str:
    return str(normalize_recipe(recipe)["id"])


def _route_for_recipe(recipe: Mapping[str, Any]) -> WorkflowRoute:
    normalized = normalize_recipe(recipe)
    return recipe_workflow_route(str(normalized["family"]), str(normalized["workflow_mode"]))


def _normalize_data_columns(value: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("data_columns must be a sequence of column names")
    return tuple(
        _plain_text(column, field_name=f"data_columns[{index}]", max_length=512)
        for index, column in enumerate(value)
    )


def _empty_apply_request(recipe_id: str) -> dict[str, Any]:
    return {
        "schema": RECIPE_APPLY_SCHEMA,
        "schema_version": RECIPE_APPLY_SCHEMA_VERSION,
        "recipe_id": recipe_id,
        "bindings": {"inputs": {"data": {}}},
    }


def _binding_diagnostic(
    *,
    code: str,
    role: str,
    message: str,
    suggested_name: str = "",
) -> dict[str, str]:
    diagnostic = {
        "namespace": "data",
        "role": role,
        "code": code,
        "message": message,
    }
    if suggested_name:
        diagnostic["suggested_name"] = suggested_name
    return diagnostic


def _unresolved_binding_error(diagnostics: Sequence[Mapping[str, str]]) -> str:
    roles = sorted(
        diagnostic.get("role", "")
        for diagnostic in diagnostics
        if diagnostic.get("role")
    )
    if not roles:
        return "recipe bindings are unresolved"
    return f"recipe bindings are unresolved: {', '.join(roles)}"


def _resolved_statistics_config(recipe: Mapping[str, Any], apply_request: Mapping[str, Any]) -> dict[str, Any]:
    statistics = recipe["configuration"]["statistics"]
    if not isinstance(statistics, Mapping):
        raise RecipeValidationError("recipe statistics config is invalid")
    value_column = _bound_data_column(statistics.get("value_column"), apply_request, field_name="value_column")
    sigma_column = (
        _bound_data_column(statistics.get("sigma_column"), apply_request, field_name="sigma_column")
        if statistics.get("sigma_column") is not None
        else ""
    )
    return {
        "mode": str(statistics["mode"]),
        "value_column": value_column,
        "value_columns": [value_column],
        "sigma_column": sigma_column,
        "sample": True,
        "weighted_variance": True,
    }


def _resolved_error_config(recipe: Mapping[str, Any], apply_request: Mapping[str, Any]) -> dict[str, Any]:
    error = recipe["configuration"]["error"]
    if not isinstance(error, Mapping):
        raise RecipeValidationError("recipe error config is invalid")
    formula = _resolve_formula_data_roles(str(error["formula"]), apply_request)
    _validate_error_formula_against_bound_columns(formula, apply_request)
    return {
        "formula": formula,
        "method": str(error["method"]),
        "order": int(error["order"]),
        "mc_samples": int(error["mc_samples"]),
        "mc_seed": "" if error.get("mc_seed") is None else str(error["mc_seed"]),
        "collect_monte_carlo_distribution": bool(error.get("collect_monte_carlo_distribution", False)),
    }


def _resolved_root_solving_config(recipe: Mapping[str, Any], apply_request: Mapping[str, Any]) -> dict[str, Any]:
    root = recipe["configuration"]["root_solving"]
    if not isinstance(root, Mapping):
        raise RecipeValidationError("recipe root_solving config is invalid")
    equations = [_resolve_formula_data_roles(equation, apply_request) for equation in root["equations"]]
    unknowns = _root_config_unknowns(root)
    _validate_root_equations_against_bound_columns(equations, unknowns=unknowns, apply_request=apply_request)
    return {
        "schema": 1,
        "equations": "\n".join(equations),
        "mode": str(root["mode"]),
        "unknowns": [dict(row) for row in unknowns],
        "uncertainty_options": dict(root["uncertainty_options"]),
    }


def _resolved_fitting_config(recipe: Mapping[str, Any], apply_request: Mapping[str, Any]) -> dict[str, Any]:
    fitting = recipe["configuration"]["fitting"]
    if not isinstance(fitting, Mapping):
        raise RecipeValidationError("recipe fitting config is invalid")
    variables = [
        {
            "name": str(row["name"]),
            "column": _bound_data_column_placeholder(
                row.get("column"),
                apply_request,
                field_name=f"configuration.fitting.variables[{index}].column",
            ),
        }
        for index, row in enumerate(fitting["variables"])
        if isinstance(row, Mapping)
    ]
    target_column = _bound_data_column_placeholder(
        fitting.get("target_column"),
        apply_request,
        field_name="configuration.fitting.target_column",
    )
    return {
        "model": str(fitting["model"]),
        "expression": str(fitting["expression"]),
        "target_column": target_column,
        "weighted": bool(fitting.get("weighted", False)),
        "mcmc_refine": False,
        "variables": variables,
        "constraints_enabled": bool(fitting.get("constraints_enabled", False)),
        "parameter_rows": [dict(row) for row in fitting["parameter_rows"]],
        "parameter_orphans": [],
        "comparison_candidates": "",
        "custom_constants": {
            "enabled": False,
            "rows": [],
            "view": "table",
            "text": "",
            "numeric_mode": "uncertainty",
        },
        "implicit": {},
    }


def _require_apply_bindings_for_required_roles(recipe: Mapping[str, Any], apply_request: Mapping[str, Any]) -> None:
    inputs = recipe.get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise RecipeValidationError("recipe.inputs must be an object")
    data_inputs = inputs.get("data", {})
    if not isinstance(data_inputs, Mapping):
        raise RecipeValidationError("recipe.inputs.data must be an object")
    required_columns = data_inputs.get("required_columns", ())
    apply_inputs = apply_request.get("bindings", {}).get("inputs", {})
    if not isinstance(apply_inputs, Mapping):
        raise RecipeValidationError("bindings.inputs must be an object")
    data_bindings = apply_inputs.get("data", {})
    if not isinstance(data_bindings, Mapping):
        raise RecipeValidationError("bindings.inputs.data must be an object")
    for role in required_columns:
        if isinstance(role, Mapping):
            role_id = str(role.get("id") or "")
            if role_id and role_id not in data_bindings:
                raise RecipeValidationError(f"missing binding for required data role: {role_id}")


def _bound_data_column(value: Any, apply_request: Mapping[str, Any], *, field_name: str) -> str:
    namespace, role = _placeholder(value, field_name=f"configuration.statistics.{field_name}")
    if namespace != "data":
        raise RecipeValidationError(f"configuration.statistics.{field_name} must bind a data role")
    return _bound_data_role(role, apply_request)


def _bound_data_column_placeholder(value: Any, apply_request: Mapping[str, Any], *, field_name: str) -> str:
    namespace, role = _placeholder(value, field_name=field_name)
    if namespace != "data":
        raise RecipeValidationError(f"{field_name} must bind a data role")
    return _bound_data_role(role, apply_request)


def _bound_data_role(role: str, apply_request: Mapping[str, Any]) -> str:
    inputs = apply_request.get("bindings", {}).get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise RecipeValidationError("bindings.inputs must be an object")
    data = inputs.get("data", {})
    if not isinstance(data, Mapping):
        raise RecipeValidationError("bindings.inputs.data must be an object")
    binding = data.get(role)
    if not isinstance(binding, Mapping):
        raise RecipeValidationError(f"missing binding for data role: {role}")
    if binding.get("kind") != "data_column":
        raise RecipeValidationError(f"unsupported binding kind for data role: {role}")
    return _plain_text(binding.get("column_id"), field_name=f"bindings.inputs.data.{role}.column_id", max_length=512)


def _apply_request_data_column_map(apply_request: Mapping[str, Any]) -> dict[str, str]:
    inputs = apply_request.get("bindings", {}).get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise RecipeValidationError("bindings.inputs must be an object")
    data = inputs.get("data", {})
    if not isinstance(data, Mapping):
        raise RecipeValidationError("bindings.inputs.data must be an object")
    resolved: dict[str, str] = {}
    for role, binding in data.items():
        role_id = _identifier_text(role, field_name="bindings.inputs.data.<role>")
        if not isinstance(binding, Mapping):
            raise RecipeValidationError(f"bindings.inputs.data.{role_id} must be an object")
        if binding.get("kind") != "data_column":
            raise RecipeValidationError(f"unsupported binding kind for data role: {role_id}")
        column_id = _plain_text(
            binding.get("column_id"),
            field_name=f"bindings.inputs.data.{role_id}.column_id",
            max_length=512,
        )
        resolved[role_id] = column_id
    return resolved


def _resolve_formula_data_roles(formula: str, apply_request: Mapping[str, Any]) -> str:
    role_to_column = _apply_request_data_column_map(apply_request)
    for role, column in role_to_column.items():
        _identifier_text(column, field_name=f"bindings.inputs.data.{role}.column_id")

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        return role_to_column.get(token, token)

    return _EXPRESSION_IDENTIFIER_RE.sub(replace, formula)


def _validate_error_formula_role_scope(formula: str, *, declared_roles: Mapping[str, set[str]]) -> None:
    data_roles = tuple(sorted(declared_roles.get("data", set())))
    try:
        from shared.computation_inputs import SymbolCategories, classify_expression_symbols, validate_symbol_classification

        classification = classify_expression_symbols(
            (formula,),
            SymbolCategories(data_columns=data_roles),
        )
        validate_symbol_classification(classification)
    except ValueError as exc:
        raise RecipeValidationError(f"configuration.error.formula is invalid: {exc}") from exc


def _validate_error_formula_against_bound_columns(formula: str, apply_request: Mapping[str, Any]) -> None:
    columns = tuple(_apply_request_data_column_map(apply_request).values())
    try:
        from shared.computation_inputs import SymbolCategories, classify_expression_symbols, validate_symbol_classification

        classification = classify_expression_symbols(
            (formula,),
            SymbolCategories(data_columns=columns),
        )
        validate_symbol_classification(classification)
    except ValueError as exc:
        raise RecipeValidationError(f"resolved error formula is invalid: {exc}") from exc


def _root_config_equations(config: Mapping[str, Any]) -> tuple[str, ...]:
    raw = config.get("equations")
    if isinstance(raw, str):
        equations = tuple(line.strip() for line in raw.splitlines() if line.strip())
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, memoryview)):
        equations = tuple(str(item).strip() for item in raw if str(item).strip())
    else:
        equations = ()
    if not equations:
        raise RecipeValidationError("recipe root_solving equations did not resolve to any equation")
    return equations


def _root_config_unknowns(config: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    raw = config.get("unknowns")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("recipe root_solving unknowns did not resolve to a list")
    unknowns: list[dict[str, str]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"recipe root_solving unknowns[{index}] is invalid")
        unknowns.append(
            {
                "name": str(row.get("name") or ""),
                "initial": str(row.get("initial") or ""),
                "lower": str(row.get("lower") or ""),
                "upper": str(row.get("upper") or ""),
                "source": str(row.get("source") or "manual"),
            }
        )
    if not unknowns:
        raise RecipeValidationError("recipe root_solving unknowns did not resolve to any unknown")
    return tuple(unknowns)


def _root_config_uncertainty_options(config: Mapping[str, Any]) -> dict[str, object]:
    raw = config.get("uncertainty_options")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise RecipeValidationError("recipe root_solving uncertainty_options did not resolve to an object")
    return dict(raw)


def _fitting_variable_map(config: Mapping[str, Any]) -> dict[str, str]:
    raw = config.get("variables")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("recipe fitting variables did not resolve to a list")
    variable_map: dict[str, str] = {}
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"recipe fitting variables[{index}] is invalid")
        variable_map[str(row.get("name") or "")] = str(row.get("column") or "")
    if not variable_map:
        raise RecipeValidationError("recipe fitting variables did not resolve to any variable")
    return variable_map


def _fitting_parameter_config(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    constraints_enabled = bool(config.get("constraints_enabled", False))
    raw = config.get("parameter_rows")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("recipe fitting parameter_rows did not resolve to a list")
    parameter_config: dict[str, dict[str, str]] = {}
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"recipe fitting parameter_rows[{index}] is invalid")
        name = str(row.get("name") or "")
        entry = {"initial": str(row.get("initial") or "")}
        if constraints_enabled:
            for key in ("fixed", "min", "max"):
                value = str(row.get(key) or "")
                if value:
                    entry[key] = value
        parameter_config[name] = {key: value for key, value in entry.items() if value}
    if not parameter_config:
        raise RecipeValidationError("recipe fitting parameter_rows did not resolve to any parameter")
    return parameter_config


def _validate_root_equation_role_scope(
    equations: Sequence[str],
    *,
    unknowns: Sequence[Mapping[str, str]],
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> None:
    data_roles = tuple(sorted(declared_roles.get("data", set())))
    unknown_names = tuple(str(row.get("name") or "") for row in unknowns)
    try:
        from shared.computation_inputs import SymbolCategories, classify_expression_symbols, validate_symbol_classification

        classification = classify_expression_symbols(
            equations,
            SymbolCategories(
                data_columns=data_roles,
                unknowns=unknown_names,
            ),
        )
        validate_symbol_classification(classification)
    except ValueError as exc:
        raise RecipeValidationError(
            f"configuration.{route.config_section}.equations are invalid: {exc}"
        ) from exc


def _validate_root_equations_against_bound_columns(
    equations: Sequence[str],
    *,
    unknowns: Sequence[Mapping[str, str]],
    apply_request: Mapping[str, Any],
) -> None:
    columns = tuple(_apply_request_data_column_map(apply_request).values())
    for role, column in _apply_request_data_column_map(apply_request).items():
        _identifier_text(column, field_name=f"bindings.inputs.data.{role}.column_id")
    unknown_names = tuple(str(row.get("name") or "") for row in unknowns)
    try:
        from shared.computation_inputs import SymbolCategories, classify_expression_symbols, validate_symbol_classification

        classification = classify_expression_symbols(
            equations,
            SymbolCategories(
                data_columns=columns,
                unknowns=unknown_names,
            ),
        )
        validate_symbol_classification(classification)
    except ValueError as exc:
        raise RecipeValidationError(f"resolved root_solving equations are invalid: {exc}") from exc


def _loads_json_payload(data: str | bytes | bytearray, *, kind: str) -> Any:
    if isinstance(data, str):
        raw_bytes = data.encode("utf-8")
        text = data
    elif isinstance(data, bytes | bytearray):
        raw_bytes = bytes(data)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecipeValidationError(f"{kind} must be UTF-8 JSON") from exc
    else:
        raise RecipeValidationError(f"{kind} must be a JSON string or bytes")
    if len(raw_bytes) > MAX_RECIPE_BYTES:
        raise RecipeValidationError(f"{kind} exceeds the {MAX_RECIPE_BYTES} byte limit")
    try:
        _reject_excessive_raw_json_nesting(text, kind=kind)
        return json.loads(
            text,
            object_pairs_hook=_object_pairs_no_duplicates,
            parse_int=_parse_json_int,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except RecipeValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RecipeValidationError(f"{kind} must be valid JSON within resource limits") from exc


def _object_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise RecipeValidationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _reject_json_number(value: str) -> None:
    raise RecipeValidationError(f"JSON floats and non-finite numbers are not allowed: {value}")


def _parse_json_int(value: str) -> int:
    if len(value) > 64:
        raise RecipeValidationError("JSON integer is too long")
    try:
        return int(value)
    except ValueError as exc:
        raise RecipeValidationError("JSON integer is invalid") from exc


def _reject_excessive_raw_json_nesting(text: str, *, kind: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "[{":
            depth += 1
            if depth > MAX_NESTING_DEPTH:
                raise RecipeValidationError(f"{kind} exceeds maximum nesting depth")
        elif char in "]}":
            depth -= 1


def _normalize_inputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("inputs must be an object")
    _reject_unknown_keys(value, _INPUT_TOP_LEVEL_KEYS, path="inputs")

    data = value.get("data")
    if not isinstance(data, Mapping):
        raise RecipeValidationError("inputs.data must be an object")
    _reject_unknown_keys(data, _DATA_INPUT_KEYS, path="inputs.data")
    required_columns = _normalize_role_declarations(
        data.get("required_columns"),
        namespace="data",
        allowed_roles=_DATA_ROLES,
        required=True,
    )

    role_count = len(required_columns)
    normalized: dict[str, Any] = {"data": {"required_columns": required_columns}}
    for namespace in ("constants", "parameters", "unknowns", "variables"):
        declarations = _normalize_role_declarations(
            value.get(namespace, []),
            namespace=namespace,
            allowed_roles=None,
            required=False,
        )
        role_count += len(declarations)
        normalized[namespace] = declarations
    if role_count > MAX_INPUT_ROLES:
        raise RecipeValidationError(f"declared input roles exceed the {MAX_INPUT_ROLES} role limit")
    return normalized


def _reject_unsupported_input_namespaces(inputs: Mapping[str, Any], *, route: WorkflowRoute) -> None:
    for namespace in RECIPE_INPUT_NAMESPACES:
        declarations = inputs.get(namespace, [])
        if namespace in route.accepted_binding_namespaces or not declarations:
            continue
        raise RecipeValidationError(
            f"{route.family}.{route.workflow_mode} does not accept inputs.{namespace} declarations"
        )


def _normalize_role_declarations(
    value: Any,
    *,
    namespace: str,
    allowed_roles: set[str] | None,
    required: bool,
) -> list[dict[str, str]]:
    if value is None:
        value = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError(f"inputs.{namespace} role declarations must be a list")
    if required and not value:
        raise RecipeValidationError(f"inputs.{namespace} must declare at least one role")
    if len(value) > MAX_INPUT_ROLES:
        raise RecipeValidationError(f"inputs.{namespace} declares too many roles")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        path = f"inputs.{namespace}[{index}]"
        if not isinstance(item, Mapping):
            raise RecipeValidationError(f"{path} must be an object")
        _reject_unknown_keys(item, _ROLE_DECLARATION_KEYS, path=path)
        role_id = _identifier_text(item.get("id"), field_name=f"{path}.id")
        if role_id in seen:
            raise RecipeValidationError(f"duplicate role id in inputs.{namespace}: {role_id}")
        seen.add(role_id)
        entry = {"id": role_id}
        suggested_name = item.get("suggested_name")
        if suggested_name is not None:
            entry["suggested_name"] = _plain_text(
                suggested_name,
                field_name=f"{path}.suggested_name",
                max_length=256,
            )
        role = item.get("role")
        if role is not None:
            role_text = _plain_text(role, field_name=f"{path}.role", max_length=64)
            if allowed_roles is not None and role_text not in allowed_roles:
                raise RecipeValidationError(f"unsupported {namespace} role: {role_text}")
            entry["role"] = role_text
        role_type = item.get("type")
        if role_type is not None:
            type_text = _plain_text(role_type, field_name=f"{path}.type", max_length=64)
            if type_text not in _ROLE_TYPES:
                raise RecipeValidationError(f"unsupported {namespace} role type: {type_text}")
            entry["type"] = type_text
        description = item.get("description")
        if description is not None:
            entry["description"] = _plain_text(
                description,
                field_name=f"{path}.description",
                max_length=MAX_LOCALIZED_TEXT_LENGTH,
            )
        normalized.append(entry)
    return normalized


def _normalize_configuration(
    value: Any,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("configuration must be an object")
    _reject_unknown_keys(value, _CONFIGURATION_TOP_LEVEL_KEYS, path="configuration")
    for section in value:
        if section != route.config_section:
            raise RecipeValidationError(
                f"configuration.{section} is not valid for {route.family}.{route.workflow_mode}"
            )
    if route.config_section == "error":
        return {"error": _normalize_error_configuration(value.get("error"), route=route, declared_roles=declared_roles)}
    if route.config_section == "root_solving":
        return {
            "root_solving": _normalize_root_solving_configuration(
                value.get("root_solving"),
                route=route,
                declared_roles=declared_roles,
            )
        }
    if route.config_section == "fitting":
        return {
            "fitting": _normalize_fitting_configuration(
                value.get("fitting"),
                route=route,
                declared_roles=declared_roles,
            )
        }
    if route.config_section != "statistics":
        raise RecipeValidationError(f"unsupported config section: {route.config_section}")
    statistics = value.get("statistics")
    if not isinstance(statistics, Mapping):
        raise RecipeValidationError("configuration.statistics must be an object")
    _reject_unknown_keys(statistics, _STATISTICS_CONFIG_KEYS, path="configuration.statistics")
    if "value_column" not in statistics:
        raise RecipeValidationError("configuration.statistics.value_column is required")
    mode = _plain_text(statistics.get("mode"), field_name="configuration.statistics.mode", max_length=64)
    if mode not in _STATISTICS_MODES:
        raise RecipeValidationError(f"unsupported statistics mode: {mode}")

    normalized_statistics: dict[str, str] = {"mode": mode}
    for field in _STATISTICS_COLUMN_FIELDS:
        if field not in statistics:
            continue
        namespace, role = _placeholder(
            statistics[field],
            field_name=f"configuration.statistics.{field}",
        )
        _validate_placeholder_binding(namespace, role, route=route, declared_roles=declared_roles)
        normalized_statistics[field] = f"${{inputs.{namespace}.{role}}}"
    if mode == "weighted_sigma" and "sigma_column" not in normalized_statistics:
        raise RecipeValidationError("configuration.statistics.sigma_column is required for weighted_sigma")
    return {"statistics": normalized_statistics}


def _normalize_error_configuration(
    value: Any,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("configuration.error must be an object")
    _reject_unknown_keys(value, _ERROR_CONFIG_KEYS, path="configuration.error")
    formula = _plain_text(
        value.get("formula"),
        field_name="configuration.error.formula",
        max_length=MAX_LOCALIZED_TEXT_LENGTH,
    )
    _validate_error_formula_role_scope(formula, declared_roles=declared_roles)
    method = _optional_text(
        value.get("method"),
        default="taylor",
        field_name="configuration.error.method",
        max_length=64,
    )
    if method not in _ERROR_METHODS:
        raise RecipeValidationError(f"unsupported error propagation method: {method}")
    order = _optional_int(value.get("order"), default=1, field_name="configuration.error.order")
    if method == "taylor" and order not in {1, 2}:
        raise RecipeValidationError("configuration.error.order must be 1 or 2 for Taylor propagation")
    if order < 1:
        raise RecipeValidationError("configuration.error.order must be positive")
    mc_samples = _optional_int(
        value.get("mc_samples"),
        default=_DEFAULT_ERROR_MC_SAMPLES,
        field_name="configuration.error.mc_samples",
    )
    if mc_samples < 100:
        raise RecipeValidationError("configuration.error.mc_samples must be at least 100")
    mc_seed = (
        _optional_int(value.get("mc_seed"), default=0, field_name="configuration.error.mc_seed")
        if value.get("mc_seed") is not None
        else None
    )
    collect_distribution = _optional_bool(
        value.get("collect_monte_carlo_distribution"),
        default=False,
        field_name="configuration.error.collect_monte_carlo_distribution",
    )
    return {
        "formula": formula,
        "method": method,
        "order": order,
        "mc_samples": mc_samples,
        "mc_seed": mc_seed,
        "collect_monte_carlo_distribution": collect_distribution,
    }


def _normalize_root_solving_configuration(
    value: Any,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("configuration.root_solving must be an object")
    _reject_unknown_keys(value, _ROOT_CONFIG_KEYS, path="configuration.root_solving")
    equations = _normalize_root_equations(value.get("equations"))
    mode = _optional_text(
        value.get("mode"),
        default="scalar",
        field_name="configuration.root_solving.mode",
        max_length=64,
    )
    if mode not in _ROOT_MODES:
        raise RecipeValidationError(f"unsupported root solving mode: {mode}")
    unknowns = _normalize_root_unknowns(value.get("unknowns"))
    uncertainty_options = _normalize_root_uncertainty_options(value.get("uncertainty_options"))
    _validate_root_equation_role_scope(
        equations,
        unknowns=unknowns,
        route=route,
        declared_roles=declared_roles,
    )
    return {
        "equations": equations,
        "mode": mode,
        "unknowns": unknowns,
        "uncertainty_options": uncertainty_options,
    }


def _normalize_root_equations(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_equations = [line.strip() for line in value.splitlines() if line.strip()]
        equations = [
            _plain_text(
                equation,
                field_name=f"configuration.root_solving.equations[{index}]",
                max_length=MAX_LOCALIZED_TEXT_LENGTH,
            )
            for index, equation in enumerate(raw_equations)
        ]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        equations = [
            _plain_text(
                equation,
                field_name=f"configuration.root_solving.equations[{index}]",
                max_length=MAX_LOCALIZED_TEXT_LENGTH,
            )
            for index, equation in enumerate(value)
        ]
    else:
        raise RecipeValidationError("configuration.root_solving.equations must be a string or list of strings")
    if not equations:
        raise RecipeValidationError("configuration.root_solving.equations must not be empty")
    return equations


def _normalize_root_unknowns(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("configuration.root_solving.unknowns must be a list")
    if not value:
        raise RecipeValidationError("configuration.root_solving.unknowns must not be empty")
    unknowns: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        path = f"configuration.root_solving.unknowns[{index}]"
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"{path} must be an object")
        _reject_unknown_keys(row, _ROOT_UNKNOWN_KEYS, path=path)
        name = _identifier_text(row.get("name"), field_name=f"{path}.name")
        if name in seen:
            raise RecipeValidationError(f"duplicate root unknown: {name}")
        seen.add(name)
        source = _optional_text(row.get("source"), default="manual", field_name=f"{path}.source", max_length=64)
        if source not in _ROOT_UNKNOWN_SOURCES:
            raise RecipeValidationError(f"unsupported root unknown source: {source}")
        unknowns.append(
            {
                "name": name,
                "initial": _optional_root_numeric_text(row.get("initial"), field_name=f"{path}.initial"),
                "lower": _optional_root_numeric_text(row.get("lower"), field_name=f"{path}.lower"),
                "upper": _optional_root_numeric_text(row.get("upper"), field_name=f"{path}.upper"),
                "source": source,
            }
        )
    return unknowns


def _optional_root_numeric_text(value: Any, *, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RecipeValidationError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        return ""
    if len(text) > 512:
        raise RecipeValidationError(f"{field_name} is too long")
    if any(ord(char) < 32 for char in text):
        raise RecipeValidationError(f"{field_name} contains control characters")
    if "${" in text:
        raise RecipeValidationError(f"{field_name} must not contain recipe placeholders")
    return text


def _normalize_root_uncertainty_options(value: Any) -> dict[str, object]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise RecipeValidationError("configuration.root_solving.uncertainty_options must be an object")
    _reject_unknown_keys(value, _ROOT_UNCERTAINTY_KEYS, path="configuration.root_solving.uncertainty_options")
    method = _optional_text(
        value.get("method"),
        default="taylor",
        field_name="configuration.root_solving.uncertainty_options.method",
        max_length=64,
    )
    if method not in _ROOT_UNCERTAINTY_METHODS:
        raise RecipeValidationError(f"unsupported root uncertainty method: {method}")
    taylor_order = _optional_int(
        value.get("taylor_order"),
        default=1,
        field_name="configuration.root_solving.uncertainty_options.taylor_order",
    )
    if taylor_order not in {1, 2}:
        raise RecipeValidationError("configuration.root_solving.uncertainty_options.taylor_order must be 1 or 2")
    monte_carlo_samples = _optional_int(
        value.get("monte_carlo_samples"),
        default=2000,
        field_name="configuration.root_solving.uncertainty_options.monte_carlo_samples",
    )
    if monte_carlo_samples < 100:
        raise RecipeValidationError(
            "configuration.root_solving.uncertainty_options.monte_carlo_samples must be at least 100"
        )
    monte_carlo_seed = _optional_root_numeric_text(
        value.get("monte_carlo_seed"),
        field_name="configuration.root_solving.uncertainty_options.monte_carlo_seed",
    )
    return {
        "method": method,
        "taylor_order": taylor_order,
        "monte_carlo_samples": monte_carlo_samples,
        "monte_carlo_seed": monte_carlo_seed,
    }


def _normalize_fitting_configuration(
    value: Any,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("configuration.fitting must be an object")
    _reject_unknown_keys(value, _FITTING_CONFIG_KEYS, path="configuration.fitting")
    model = _optional_text(
        value.get("model"),
        default="custom",
        field_name="configuration.fitting.model",
        max_length=64,
    )
    if model not in _FITTING_MODELS:
        raise RecipeValidationError(f"unsupported fitting model: {model}")
    expression = _plain_text(
        value.get("expression"),
        field_name="configuration.fitting.expression",
        max_length=MAX_LOCALIZED_TEXT_LENGTH,
    )
    variables = _normalize_fitting_variables(value.get("variables"), route=route, declared_roles=declared_roles)
    target_namespace, target_role = _placeholder(
        value.get("target_column"),
        field_name="configuration.fitting.target_column",
    )
    _validate_placeholder_binding(target_namespace, target_role, route=route, declared_roles=declared_roles)
    weighted = _optional_bool(value.get("weighted"), default=False, field_name="configuration.fitting.weighted")
    constraints_enabled = _optional_bool(
        value.get("constraints_enabled"),
        default=False,
        field_name="configuration.fitting.constraints_enabled",
    )
    parameter_rows = _normalize_fitting_parameter_rows(value.get("parameter_rows"))
    variable_names = [row["name"] for row in variables]
    parameter_names = _infer_recipe_fitting_parameter_names(expression, variable_names)
    _validate_fitting_parameter_rows(
        parameter_rows,
        parameter_names=parameter_names,
        constraints_enabled=constraints_enabled,
    )
    _validate_fitting_model_configuration(
        expression,
        variable_names=variable_names,
        parameter_names=[row["name"] for row in parameter_rows],
    )
    return {
        "model": model,
        "expression": expression,
        "variables": variables,
        "target_column": f"${{inputs.{target_namespace}.{target_role}}}",
        "weighted": weighted,
        "constraints_enabled": constraints_enabled,
        "parameter_rows": parameter_rows,
    }


def _normalize_fitting_variables(
    value: Any,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("configuration.fitting.variables must be a list")
    if not value:
        raise RecipeValidationError("configuration.fitting.variables must not be empty")
    variables: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        path = f"configuration.fitting.variables[{index}]"
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"{path} must be an object")
        _reject_unknown_keys(row, _FITTING_VARIABLE_KEYS, path=path)
        name = _identifier_text(row.get("name"), field_name=f"{path}.name")
        if name in seen:
            raise RecipeValidationError(f"duplicate fitting variable: {name}")
        seen.add(name)
        namespace, role = _placeholder(row.get("column"), field_name=f"{path}.column")
        _validate_placeholder_binding(namespace, role, route=route, declared_roles=declared_roles)
        variables.append({"name": name, "column": f"${{inputs.{namespace}.{role}}}"})
    return variables


def _normalize_fitting_parameter_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("configuration.fitting.parameter_rows must be a list")
    if not value:
        raise RecipeValidationError("configuration.fitting.parameter_rows must not be empty")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        path = f"configuration.fitting.parameter_rows[{index}]"
        if not isinstance(row, Mapping):
            raise RecipeValidationError(f"{path} must be an object")
        _reject_unknown_keys(row, _FITTING_PARAMETER_KEYS, path=path)
        name = _identifier_text(row.get("name"), field_name=f"{path}.name")
        if name in seen:
            raise RecipeValidationError(f"duplicate fitting parameter: {name}")
        seen.add(name)
        rows.append(
            {
                "name": name,
                "initial": _optional_root_numeric_text(row.get("initial"), field_name=f"{path}.initial"),
                "fixed": _optional_root_numeric_text(row.get("fixed"), field_name=f"{path}.fixed"),
                "min": _optional_root_numeric_text(row.get("min"), field_name=f"{path}.min"),
                "max": _optional_root_numeric_text(row.get("max"), field_name=f"{path}.max"),
            }
        )
    return rows


def _infer_recipe_fitting_parameter_names(expression: str, variable_names: Sequence[str]) -> list[str]:
    from fitting.model_parser import infer_parameter_names, reserved_expression_names

    reserved = {name.lower() for name in variable_names}
    reserved |= reserved_expression_names()
    expression_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)
    has_parameter_token = any(token.lower() not in reserved for token in expression_tokens)
    if not has_parameter_token:
        return []
    return cast(list[str], infer_parameter_names(expression, variable_names, [], constants=[]))


def _validate_fitting_parameter_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    parameter_names: Sequence[str],
    constraints_enabled: bool,
) -> None:
    if not parameter_names:
        raise RecipeValidationError("configuration.fitting.expression must contain at least one fit parameter")
    actual = [str(row.get("name") or "") for row in rows]
    missing = [name for name in parameter_names if name not in actual]
    extra = [name for name in actual if name not in parameter_names]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("extra: " + ", ".join(extra))
        raise RecipeValidationError(
            "configuration.fitting.parameter_rows must match inferred parameters"
            + (f" ({'; '.join(details)})" if details else "")
        )
    for row in rows:
        name = str(row.get("name") or "")
        if not str(row.get("initial") or "").strip():
            raise RecipeValidationError(f"configuration.fitting.parameter_rows.{name}.initial is required")
        constraint_values = [str(row.get(key) or "").strip() for key in ("fixed", "min", "max")]
        if not constraints_enabled and any(constraint_values):
            raise RecipeValidationError(
                f"configuration.fitting.parameter_rows.{name} has constraints while constraints_enabled is false"
            )


def _validate_fitting_model_configuration(
    expression: str,
    *,
    variable_names: Sequence[str],
    parameter_names: Sequence[str],
) -> None:
    try:
        _validate_expression_syntax(expression, field_name="configuration.fitting.expression")
        from fitting.model_parser import build_model_specification

        build_model_specification(expression, variable_names, parameter_names, {})
    except ValueError as exc:
        raise RecipeValidationError(f"configuration.fitting.expression is invalid: {exc}") from exc


def _validate_expression_syntax(expression: str, *, field_name: str) -> None:
    import ast

    from shared.expression_engine import _normalize_expression

    try:
        ast.parse(_normalize_expression(expression), mode="eval")
    except (SyntaxError, RecursionError, MemoryError) as exc:
        raise RecipeValidationError(f"{field_name} is invalid: {exc}") from exc


def _normalize_exports(value: Any) -> dict[str, bool]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise RecipeValidationError("exports must be an object")
    _reject_unknown_keys(value, _EXPORT_KEYS, path="exports")
    normalized = {key: False for key in sorted(_EXPORT_KEYS)}
    for key, raw in value.items():
        if not isinstance(raw, bool):
            raise RecipeValidationError(f"exports.{key} must be a boolean")
        normalized[str(key)] = raw
    return normalized


def _normalize_examples(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise RecipeValidationError("examples must be a list")
    if len(value) > MAX_ITEMS_PER_LEVEL:
        raise RecipeValidationError("examples contains too many items")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        path = f"examples[{index}]"
        if not isinstance(item, Mapping):
            raise RecipeValidationError(f"{path} must be an object")
        _reject_unknown_keys(item, _EXAMPLE_KEYS, path=path)
        workspace = _safe_relative_resource(item.get("workspace"), field_name=f"{path}.workspace")
        if not workspace.endswith(".datalab"):
            raise RecipeValidationError(f"{path}.workspace must reference a .datalab workspace")
        normalized.append({"workspace": workspace})
    return normalized


def _normalize_apply_bindings(
    value: Any,
    *,
    declared_roles: Mapping[str, set[str]] | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeValidationError("bindings must be an object")
    _reject_unknown_keys(value, {"inputs"}, path="bindings")
    inputs = value.get("inputs")
    if not isinstance(inputs, Mapping):
        raise RecipeValidationError("bindings.inputs must be an object")
    _reject_unknown_keys(inputs, set(RECIPE_INPUT_NAMESPACES), path="bindings.inputs")
    normalized_inputs: dict[str, Any] = {namespace: {} for namespace in RECIPE_INPUT_NAMESPACES}
    for namespace, raw_bindings in inputs.items():
        namespace_text = str(namespace)
        if not isinstance(raw_bindings, Mapping):
            raise RecipeValidationError(f"bindings.inputs.{namespace_text} must be an object")
        normalized_inputs[namespace_text] = _normalize_namespace_bindings(
            raw_bindings,
            namespace=namespace_text,
            declared_roles=declared_roles.get(namespace_text, set()) if declared_roles is not None else None,
        )
    return {"inputs": normalized_inputs}


def _normalize_namespace_bindings(
    value: Mapping[str, Any],
    *,
    namespace: str,
    declared_roles: set[str] | None,
) -> dict[str, dict[str, str]]:
    if len(value) > MAX_INPUT_ROLES:
        raise RecipeValidationError(f"bindings.inputs.{namespace} contains too many bindings")
    normalized: dict[str, dict[str, str]] = {}
    for raw_role, raw_binding in sorted(value.items(), key=lambda item: str(item[0])):
        role = _identifier_text(raw_role, field_name=f"bindings.inputs.{namespace}.<role>")
        if declared_roles is not None and role not in declared_roles:
            raise RecipeValidationError(f"binding references undeclared {namespace} role: {role}")
        if not isinstance(raw_binding, Mapping):
            raise RecipeValidationError(f"bindings.inputs.{namespace}.{role} must be an object")
        if namespace == "data":
            normalized[role] = _normalize_data_column_binding(raw_binding, field_name=f"bindings.inputs.data.{role}")
        else:
            raise RecipeValidationError(f"bindings for inputs.{namespace} are not supported in this release")
    return normalized


def _normalize_data_column_binding(value: Mapping[str, Any], *, field_name: str) -> dict[str, str]:
    _reject_unknown_keys(value, {"kind", "column_id"}, path=field_name)
    kind = _plain_text(value.get("kind"), field_name=f"{field_name}.kind", max_length=64)
    if kind != "data_column":
        raise RecipeValidationError(f"{field_name}.kind must be 'data_column'")
    column_id = _plain_text(value.get("column_id"), field_name=f"{field_name}.column_id", max_length=512)
    _reject_url_or_path_traversal(column_id, field_name=f"{field_name}.column_id")
    return {"kind": kind, "column_id": column_id}


def _placeholder(value: Any, *, field_name: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise RecipeValidationError(f"{field_name} must be a placeholder string")
    match = _PLACEHOLDER_RE.fullmatch(value.strip())
    if not match:
        if "${" in value:
            raise RecipeValidationError(f"{field_name} must be a whole-field recipe placeholder")
        raise RecipeValidationError(f"{field_name} must be a recipe placeholder")
    return match.group(1), match.group(2)


def _validate_placeholder_binding(
    namespace: str,
    role: str,
    *,
    route: WorkflowRoute,
    declared_roles: Mapping[str, set[str]],
) -> None:
    if namespace not in route.accepted_binding_namespaces:
        raise RecipeValidationError(f"{route.family}.{route.workflow_mode} does not accept inputs.{namespace} bindings")
    if role not in declared_roles.get(namespace, set()):
        raise RecipeValidationError(f"placeholder references undeclared inputs.{namespace} role: {role}")


def _declared_role_lookup(value: Mapping[str, Iterable[str]] | None) -> dict[str, set[str]] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RecipeValidationError("declared_roles must be an object")
    lookup: dict[str, set[str]] = {namespace: set() for namespace in RECIPE_INPUT_NAMESPACES}
    for raw_namespace, raw_roles in value.items():
        namespace = str(raw_namespace)
        if namespace not in RECIPE_INPUT_NAMESPACES:
            raise RecipeValidationError(f"unsupported declared role namespace: {namespace}")
        lookup[namespace] = {_identifier_text(role, field_name=f"declared_roles.{namespace}") for role in raw_roles}
    return lookup


def _localized_text(value: Any, *, field_name: str, required: bool) -> dict[str, str]:
    if value is None:
        if required:
            raise RecipeValidationError(f"{field_name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise RecipeValidationError(f"{field_name} must be a localized text object")
    if not value:
        if required:
            raise RecipeValidationError(f"{field_name} must not be empty")
        return {}
    if len(value) > MAX_ITEMS_PER_LEVEL:
        raise RecipeValidationError(f"{field_name} has too many localized entries")
    normalized: dict[str, str] = {}
    for raw_locale, raw_text in sorted(value.items(), key=lambda item: str(item[0])):
        locale = _plain_text(raw_locale, field_name=f"{field_name}.<locale>", max_length=16)
        if not _LOCALE_RE.fullmatch(locale):
            raise RecipeValidationError(f"{field_name} locale must be a simple locale identifier")
        text = _plain_text(raw_text, field_name=f"{field_name}.{locale}", max_length=MAX_LOCALIZED_TEXT_LENGTH)
        normalized[locale] = text
    return normalized


def _optional_text(value: Any, *, default: str, field_name: str, max_length: int) -> str:
    if value is None:
        return default
    return _plain_text(value, field_name=field_name, max_length=max_length)


def _plain_text(value: Any, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise RecipeValidationError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise RecipeValidationError(f"{field_name} must not be empty")
    if len(text) > max_length:
        raise RecipeValidationError(f"{field_name} is too long")
    if any(ord(char) < 32 for char in text):
        raise RecipeValidationError(f"{field_name} contains control characters")
    if "${" in text:
        raise RecipeValidationError(f"{field_name} must not contain recipe placeholders")
    return text


def _identifier_text(value: Any, *, field_name: str) -> str:
    text = _plain_text(value, field_name=field_name, max_length=64)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise RecipeValidationError(f"{field_name} must be an ASCII identifier")
    return text


def _recipe_id_text(value: Any, *, field_name: str) -> str:
    text = _plain_text(value, field_name=field_name, max_length=64)
    if not _RECIPE_ID_RE.fullmatch(text):
        raise RecipeValidationError(f"{field_name} must be an ASCII recipe id")
    return text


def _optional_int(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecipeValidationError(f"{field_name} must be an integer")
    parsed: int = value
    return parsed


def _optional_bool(value: Any, *, default: bool, field_name: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise RecipeValidationError(f"{field_name} must be a boolean")
    return value


def _optional_int_from_config(value: Any, *, default: int, field_name: str) -> int:
    parsed = _optional_int_or_none_from_config(value, field_name=field_name)
    return default if parsed is None else parsed


def _optional_int_or_none_from_config(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RecipeValidationError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError as exc:
            raise RecipeValidationError(f"{field_name} must be an integer") from exc
    raise RecipeValidationError(f"{field_name} must be an integer")


def _safe_relative_resource(value: Any, *, field_name: str) -> str:
    text = _plain_text(value, field_name=field_name, max_length=512)
    _reject_url_or_path_traversal(text, field_name=field_name)
    if text.startswith("/") or text.startswith("~") or re.match(r"^[A-Za-z]:/", text):
        raise RecipeValidationError(f"{field_name} must be a relative resource path")
    if "\\" in text:
        raise RecipeValidationError(f"{field_name} must use forward-slash resource paths")
    return text


def _reject_url_or_path_traversal(text: str, *, field_name: str) -> None:
    lowered = text.lower()
    if "://" in lowered or lowered.startswith(("http:", "https:", "file:")):
        raise RecipeValidationError(f"{field_name} must not be a URL")
    normalized = text.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("~") or re.match(r"^[A-Za-z]:/", normalized):
        raise RecipeValidationError(f"{field_name} must not be an absolute path")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise RecipeValidationError(f"{field_name} must not contain path traversal")


def _reject_unknown_keys(value: Mapping[Any, Any], allowed: set[str], *, path: str) -> None:
    for key in value:
        if not isinstance(key, str):
            raise RecipeValidationError(f"{path} keys must be strings")
        if key not in allowed:
            raise RecipeValidationError(f"unsupported field at {path}: {key}")


def _enforce_resource_limits(value: Any, *, path: str) -> None:
    counter = {"placeholders": 0}
    _check_resource_node(value, path=path, depth=0, counter=counter)


def _check_resource_node(value: Any, *, path: str, depth: int, counter: dict[str, int]) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise RecipeValidationError(f"{path} exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS_PER_LEVEL:
            raise RecipeValidationError(f"{path} has too many object keys")
        for key, item in value.items():
            _check_resource_node(key, path=f"{path}.<key>", depth=depth + 1, counter=counter)
            _check_resource_node(item, path=f"{path}.{key}", depth=depth + 1, counter=counter)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        if len(value) > MAX_ITEMS_PER_LEVEL:
            raise RecipeValidationError(f"{path} has too many array items")
        for index, item in enumerate(value):
            _check_resource_node(item, path=f"{path}[{index}]", depth=depth + 1, counter=counter)
        return
    if isinstance(value, str):
        if len(value) > MAX_LOCALIZED_TEXT_LENGTH:
            raise RecipeValidationError(f"{path} text is too long")
        counter["placeholders"] += value.count("${inputs.")
        if counter["placeholders"] > MAX_PLACEHOLDERS:
            raise RecipeValidationError(f"recipe exceeds the {MAX_PLACEHOLDERS} placeholder limit")


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        raise RecipeValidationError(f"JSON floats are not allowed at {path}; pass numeric values as strings")
    if isinstance(value, (str, int)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_json_floats(key, path=f"{path}.<key>")
            _reject_json_floats(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")
        return
    raise RecipeValidationError(f"unsupported JSON value type at {path}: {type(value).__name__}")


__all__ = [
    "MAX_INPUT_ROLES",
    "MAX_ITEMS_PER_LEVEL",
    "MAX_LOCALIZED_TEXT_LENGTH",
    "MAX_NESTING_DEPTH",
    "MAX_PLACEHOLDERS",
    "MAX_RECIPE_BYTES",
    "RECIPE_APPLY_SCHEMA",
    "RECIPE_APPLY_SCHEMA_VERSION",
    "RECIPE_INPUT_NAMESPACES",
    "RECIPE_SCHEMA",
    "RECIPE_SCHEMA_VERSION",
    "RecipeValidationError",
    "RecipeBindingResolution",
    "WorkflowRoute",
    "build_recipe_fitting_request",
    "build_recipe_root_solving_request",
    "build_recipe_uncertainty_request",
    "build_recipe_statistics_requests",
    "build_recipe_workspace_patch",
    "declared_recipe_roles",
    "declared_recipe_roles_from_inputs",
    "loads_recipe_apply_json",
    "loads_recipe_json",
    "normalize_recipe",
    "normalize_recipe_apply_request",
    "normalized_recipe_id",
    "recipe_workflow_route",
    "resolve_recipe_bindings",
]
