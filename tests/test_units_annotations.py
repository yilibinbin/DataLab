from __future__ import annotations

import copy

import pytest

from datalab_core.workbench_model import WorkbenchModel
from shared.unit_annotations import (
    UnitAnnotationError,
    canonical_unit_symbol_map,
    first_unit_annotation_text,
    normalize_display_only_family_units,
    normalize_unit_annotations,
    unit_annotation_text,
    unit_annotations_for_labels,
)
from shared.workspace_schema import WorkspaceValidationError, compute_workspace_hash, validate_manifest


def test_normalize_unit_annotations_display_only_without_pint(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)

    normalized = normalize_unit_annotations(
        {
            "schema": "datalab.units.annotations.v1",
            "schema_version": 1,
            "enabled": True,
            "mode": "display_only",
            "inputs": {"temperature": {"unit": "K", "label": "Temperature"}},
            "constants": {"c": "m/s"},
            "outputs": {"energy": {"unit": "J"}},
            "compatibility": {
                "quantity_space": "energy",
                "denominator_semantics": "independent",
                "aggregation_model": "variance",
            },
        }
    )

    assert normalized == {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"temperature": {"unit": "K", "label": "Temperature"}},
        "constants": {"c": {"unit": "m/s"}},
        "parameters": {},
        "outputs": {"energy": {"unit": "J"}},
        "compatibility": {
            "aggregation_model": "variance",
            "denominator_semantics": "independent",
            "quantity_space": "energy",
        },
    }


def test_validate_expression_units_require_pint(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)

    with pytest.raises(UnitAnnotationError, match="requires pint"):
        normalize_unit_annotations({"enabled": True, "mode": "validate_expression"})


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": True, "mode": "convert_outputs"},
        {"enabled": True, "mode": "display_only", "backend_available": True},
        {"enabled": True, "mode": "display_only", "backend_version": "0.25"},
        {"enabled": True, "mode": "display_only", "diagnostics": []},
        {"enabled": True, "mode": "display_only", "conversions": {}},
        {"enabled": True, "mode": "display_only", "inputs": {"x": {"unit": "m", "extra": "bad"}}},
        {"enabled": True, "mode": "display_only", "inputs": {"x": {"unit": 1.2}}},
    ],
)
def test_unit_annotations_fail_closed_for_unsupported_or_execution_metadata(payload: dict[str, object]) -> None:
    with pytest.raises(UnitAnnotationError):
        normalize_unit_annotations(payload)


def test_unit_annotations_validate_against_canonical_symbols() -> None:
    payload = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"temperature": {"unit": "K"}, "x1": {"unit": "m"}},
    }

    with pytest.raises(UnitAnnotationError, match="canonical symbol"):
        normalize_unit_annotations(payload, allowed_symbols={"inputs": {"temperature"}})

    normalized = normalize_unit_annotations(
        {"enabled": True, "mode": "display_only", "inputs": {"temperature": {"unit": "K"}}},
        allowed_symbols={"inputs": {"temperature"}},
    )
    assert normalized["inputs"] == {"temperature": {"unit": "K"}}


def test_unit_annotations_omitted_allowed_namespace_rejects_entries() -> None:
    with pytest.raises(UnitAnnotationError, match="canonical symbol"):
        normalize_unit_annotations(
            {"enabled": True, "mode": "display_only", "parameters": {"p": "m"}},
            allowed_symbols={"inputs": {"x"}},
        )


def test_display_only_family_units_accept_labels_but_reject_active_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", True)

    normalized = normalize_display_only_family_units(
        {
            "enabled": True,
            "mode": "display_only",
            "inputs": {"Signal": "V"},
            "outputs": {"result": "V"},
        },
        family="statistics",
        allowed_symbols={"inputs": {"Signal"}, "outputs": {"result"}},
    )

    assert normalized is not None
    assert normalized["inputs"] == {"Signal": {"unit": "V"}}
    assert normalized["outputs"] == {"result": {"unit": "V"}}

    with pytest.raises(UnitAnnotationError, match="statistics units only support display_only"):
        normalize_display_only_family_units(
            {"enabled": True, "mode": "validate_expression"},
            family="statistics",
        )
    with pytest.raises(UnitAnnotationError, match="mode must be a string"):
        normalize_display_only_family_units(
            {"enabled": True, "mode": 1},
            family="statistics",
        )


def test_display_only_family_units_allow_disabled_config_without_pint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)

    normalized = normalize_display_only_family_units(
        {"enabled": False, "mode": "validate_expression"},
        family="fitting",
    )

    assert normalized is not None
    assert normalized["enabled"] is False
    assert normalized["mode"] == "validate_expression"


def test_canonical_unit_symbol_map_normalizes_and_rejects_ambiguous_labels() -> None:
    assert canonical_unit_symbol_map(["Signal (V)", "2nd value"]) == {
        "Signal (V)": "Signal_V",
        "2nd value": "field_2nd_value",
    }
    assert canonical_unit_symbol_map(["温度", "压力"]) == {
        "温度": "field_1",
        "压力": "field_2",
    }

    with pytest.raises(UnitAnnotationError, match="duplicates label"):
        canonical_unit_symbol_map(["Signal", "Signal"])

    with pytest.raises(UnitAnnotationError, match="collides"):
        canonical_unit_symbol_map(["A-B", "A_B"])


def test_unit_annotation_display_helpers_resolve_direct_canonical_and_default_units() -> None:
    units = normalize_display_only_family_units(
        {
            "enabled": True,
            "mode": "display_only",
            "outputs": {
                "x": {"unit": "m"},
                "Root_value": {"unit": "s"},
                "result": {"unit": "J"},
            },
        },
        family="root_solving",
    )

    assert unit_annotation_text(units, "outputs", "x") == "m"
    assert first_unit_annotation_text(units, "outputs", ("", "missing", "x", "y")) == "m"
    assert first_unit_annotation_text(units, "outputs", ("missing", "")) == ""
    assert unit_annotations_for_labels(
        units,
        "outputs",
        ["x", "Root value", "missing"],
        fallback_prefix="root",
        default_key="result",
    ) == {"x": "m", "Root value": "s", "missing": "J"}


def test_workspace_hash_includes_editable_unit_config_but_not_result_snapshot_units() -> None:
    baseline = _workspace()
    with_units = _workspace()
    with_units["config"]["error"]["units"] = normalize_unit_annotations(
        {"enabled": True, "mode": "display_only", "inputs": {"x": {"unit": "m"}}}
    )

    assert compute_workspace_hash(baseline) != compute_workspace_hash(with_units)

    rendered_only = copy.deepcopy(baseline)
    rendered_only["result_snapshot"] = {"units": {"backend_available": True, "diagnostics": ["cached"]}}
    assert compute_workspace_hash(baseline) == compute_workspace_hash(rendered_only)


def test_workbench_model_round_trips_error_units_config_without_execution_metadata() -> None:
    workspace = _workspace()
    units_config = normalize_unit_annotations(
        {"enabled": True, "mode": "display_only", "inputs": {"distance": {"unit": "m"}}}
    )
    workspace["config"]["error"]["units"] = units_config

    model = WorkbenchModel.from_v1_workspace(workspace)
    restored = model.to_v1_workspace()

    assert restored["config"]["error"]["units"] == units_config
    assert "backend_available" not in restored["config"]["error"]["units"]
    assert model.compute_hash() == compute_workspace_hash(restored)
    with pytest.raises(TypeError):
        model.compute["config"]["error"]["formula"] = "mutated"  # type: ignore[index]


def test_workbench_model_normalizes_raw_error_units_config() -> None:
    workspace = _workspace()
    workspace["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"distance": "m"},
    }

    model = WorkbenchModel.from_v1_workspace(workspace)

    assert model.to_v1_workspace()["config"]["error"]["units"]["inputs"] == {
        "distance": {"unit": "m"}
    }
    with pytest.raises(TypeError):
        model.compute["config"]["error"]["formula"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize("family", ["root_solving", "fitting", "statistics"])
def test_workbench_model_normalizes_display_only_family_units_config(family: str) -> None:
    workspace = _workspace()
    workspace["config"][family] = {
        "units": {
            "enabled": True,
            "mode": "display_only",
            "outputs": {"result": "m"},
        }
    }

    model = WorkbenchModel.from_v1_workspace(workspace)

    assert model.to_v1_workspace()["config"][family]["units"]["outputs"] == {
        "result": {"unit": "m"}
    }
    with pytest.raises(TypeError):
        model.compute["config"][family]["units"]["outputs"]["result"] = {"unit": "cm"}  # type: ignore[index]


@pytest.mark.parametrize("family", ["root_solving", "fitting", "statistics"])
def test_workbench_model_rejects_active_family_units_config(
    family: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", True)
    workspace = _workspace()
    workspace["config"][family] = {"units": {"enabled": True, "mode": "validate_expression"}}

    with pytest.raises(TypeError, match=rf"config\.{family}\.units is invalid"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workbench_model_compute_remains_immutable_without_units() -> None:
    model = WorkbenchModel.from_v1_workspace(_workspace())

    with pytest.raises(TypeError):
        model.compute["config"]["error"]["formula"] = "mutated"  # type: ignore[index]


def test_workbench_model_rejects_invalid_editable_error_units_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)
    workspace = _workspace()
    workspace["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "validate_expression",
    }

    with pytest.raises(TypeError, match="config.error.units is invalid"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workbench_model_rejects_error_units_execution_metadata() -> None:
    workspace = _workspace()
    workspace["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "display_only",
        "backend_available": True,
    }

    with pytest.raises(TypeError, match="config.error.units is invalid"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workbench_model_legacy_float_path_does_not_cleanse_unit_config_floats() -> None:
    workspace = _workspace()
    workspace["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"distance": {"unit": 1.2}},
    }

    with pytest.raises(TypeError, match="config.error.units is invalid"):
        WorkbenchModel.from_v1_workspace(workspace, allow_legacy_floats=True)


@pytest.mark.parametrize("family", ["root_solving", "fitting", "statistics"])
def test_workbench_model_legacy_float_path_does_not_cleanse_family_unit_config_floats(
    family: str,
) -> None:
    workspace = _workspace()
    workspace["config"][family] = {
        "units": {
            "enabled": True,
            "mode": "display_only",
            "outputs": {"result": {"unit": 1.2}},
        }
    }

    with pytest.raises(TypeError, match=rf"config\.{family}\.units is invalid"):
        WorkbenchModel.from_v1_workspace(workspace, allow_legacy_floats=True)


def test_workbench_model_unit_config_does_not_cleanse_other_float_keys() -> None:
    workspace = _workspace()
    workspace["data"] = {1.2: "bad-key"}
    workspace["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"distance": "m"},
    }

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workspace_manifest_validation_checks_error_units_config() -> None:
    manifest = _manifest(_workspace())
    manifest["workspace"]["config"]["error"]["units"] = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"distance": "m"},
    }

    validate_manifest(manifest)

    manifest["workspace"]["config"]["error"]["units"]["diagnostics"] = []
    with pytest.raises(WorkspaceValidationError, match="workspace.config.error.units"):
        validate_manifest(manifest)


@pytest.mark.parametrize("family", ["root_solving", "fitting", "statistics"])
def test_workspace_manifest_validation_checks_display_only_family_units_config(family: str) -> None:
    manifest = _manifest(_workspace())
    manifest["workspace"]["config"][family] = {
        "units": {
            "enabled": True,
            "mode": "display_only",
            "outputs": {"result": "m"},
        }
    }

    validate_manifest(manifest)

    manifest["workspace"]["config"][family]["units"]["mode"] = "validate_expression"
    with pytest.raises(WorkspaceValidationError, match=rf"workspace.config.{family}.units"):
        validate_manifest(manifest)


def _workspace() -> dict[str, object]:
    return {
        "current_mode": "error",
        "data": {"source_kind": "manual", "manual_text": "x\n1"},
        "constants": {"source_kind": "manual", "manual_text": ""},
        "config": {"common": {}, "error": {"formula": "x"}},
        "result_snapshot": {},
    }


def _manifest(workspace: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "workspace": workspace,
    }
