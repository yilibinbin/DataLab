from __future__ import annotations

import copy
import importlib
from pathlib import Path

import pytest

from shared.workspace_schema import compute_workspace_hash


def _minimal_workspace() -> dict[str, object]:
    return {
        "title": "Untitled",
        "current_mode": "fitting",
        "language": "auto",
        "ui": {
            "main_tab": 0,
            "formula_preview": {"fitting.custom.expression": "python"},
        },
        "data": {
            "source_kind": "manual_text",
            "decoded_text": "A B\n1 2",
            "canonical_table": {
                "headers": ["A", "B"],
                "rows": [["1", "2"]],
            },
        },
        "constants": {
            "enabled": True,
            "source_kind": "manual_text",
            "decoded_text": "C 3",
            "canonical_table": {
                "headers": ["name", "value"],
                "rows": [["C", "3"]],
            },
        },
        "config": {
            "common": {
                "precision_digits": 50,
                "display_scientific": True,
                "display_digits": 8,
            },
            "fitting": {
                "model": "custom",
                "expression": "a*x+b",
                "parameter_rows": [
                    {"name": "a", "initial": "1"},
                    {"name": "b", "initial": "0"},
                ],
            },
        },
        "result_snapshot": {"present": False},
    }


def test_workbench_model_module_imports_without_qt_or_legacy_runtime_modules() -> None:
    module = importlib.import_module("datalab_core.workbench_model")

    assert module.WorkbenchModel.__name__ == "WorkbenchModel"


def test_workbench_model_formula_preview_languages_match_render_service_enum() -> None:
    from datalab_core.workbench_model import FORMULA_PREVIEW_LANGUAGES
    from datalab_latex.formula_render_service import InputLanguage

    assert FORMULA_PREVIEW_LANGUAGES == frozenset(language.value for language in InputLanguage)


def test_workbench_model_builds_from_minimal_v1_workspace() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    model = WorkbenchModel.from_v1_workspace(workspace)

    assert model.schema_version == 1
    assert model.current_mode == "fitting"
    assert model.compute["config"]["fitting"]["expression"] == "a*x+b"
    assert model.ui["formula_preview"] == {"fitting.custom.expression": "python"}
    assert model.result_snapshot == {"present": False}


def test_workbench_model_hash_matches_v1_workspace_hash() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    model = WorkbenchModel.from_v1_workspace(workspace)

    assert model.compute_hash() == compute_workspace_hash(workspace)


def test_workbench_model_formula_preview_ui_does_not_affect_compute_hash() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    changed_preview = copy.deepcopy(workspace)
    changed_preview["ui"]["formula_preview"] = {  # type: ignore[index]
        "fitting.custom.expression": "latex",
        "root_solving.equation": "mathematica",
    }

    assert WorkbenchModel.from_v1_workspace(workspace).compute_hash() == WorkbenchModel.from_v1_workspace(
        changed_preview
    ).compute_hash()


def test_workbench_model_rejects_binary_float_in_compute_relevant_fields() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    workspace["config"]["fitting"]["parameter_rows"][0]["initial"] = 1.0  # type: ignore[index]

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workbench_model_can_normalize_legacy_compute_floats_for_readers() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    workspace["config"]["fitting"]["parameter_rows"][0]["initial"] = 1.0  # type: ignore[index]

    model = WorkbenchModel.from_v1_workspace(workspace, allow_legacy_floats=True)

    assert model.compute["config"]["fitting"]["parameter_rows"][0]["initial"] == "1.0"


def test_workbench_model_lenient_ui_omits_malformed_formula_preview() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    workspace["ui"]["formula_preview"] = ["python"]  # type: ignore[index]

    model = WorkbenchModel.from_v1_workspace(workspace, lenient_ui=True)

    assert "formula_preview" not in model.ui


def test_workbench_model_rejects_unknown_formula_preview_language() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    workspace["ui"]["formula_preview"] = {"fitting.custom.expression": "javascript"}  # type: ignore[index]

    with pytest.raises(ValueError, match="Unsupported formula preview language"):
        WorkbenchModel.from_v1_workspace(workspace)


def test_workbench_model_lenient_ui_omits_unknown_formula_preview_language() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    workspace["ui"]["formula_preview"] = {"fitting.custom.expression": "javascript"}  # type: ignore[index]

    model = WorkbenchModel.from_v1_workspace(workspace, lenient_ui=True)

    assert "formula_preview" not in model.ui


def test_workbench_model_to_v1_workspace_returns_plain_copy() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    model = WorkbenchModel.from_v1_workspace(workspace)
    exported = model.to_v1_workspace()

    assert exported == workspace
    exported["config"]["fitting"]["expression"] = "changed"  # type: ignore[index]
    assert model.compute["config"]["fitting"]["expression"] == "a*x+b"


def test_workbench_model_builds_from_v1_manifest() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    workspace = _minimal_workspace()
    manifest = {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "workspace": workspace,
    }
    model = WorkbenchModel.from_v1_manifest(manifest)

    assert model.current_mode == "fitting"
    assert model.compute_hash() == compute_workspace_hash(workspace)


def test_workbench_model_rejects_invalid_v1_manifest() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    manifest = {
        "schema": "datalab.workspace.v1",
        "schema_version": 2,
        "workspace": _minimal_workspace(),
    }

    with pytest.raises(ValueError, match="schema_version"):
        WorkbenchModel.from_v1_manifest(manifest)


def test_workbench_model_builds_from_bundled_example_workspaces() -> None:
    from datalab_core.workbench_model import WorkbenchModel
    from shared.workspace_io import read_workspace

    for path in sorted(Path("examples/workspaces").glob("*.datalab")):
        manifest = read_workspace(path).manifest
        model = WorkbenchModel.from_v1_manifest(manifest)
        workspace = manifest["workspace"]

        assert model.current_mode == workspace["current_mode"], path.name
        assert model.compute_hash() == compute_workspace_hash(workspace), path.name


def test_workbench_model_exposes_formula_preview_language_state_as_copy() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    model = WorkbenchModel.from_v1_workspace(_minimal_workspace())
    languages = model.formula_preview_languages

    assert languages == {"fitting.custom.expression": "python"}
    languages["fitting.custom.expression"] = "mathematica"
    assert model.formula_preview_language("fitting.custom.expression") == "python"


def test_workbench_model_updates_formula_preview_language_immutably() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    model = WorkbenchModel.from_v1_workspace(_minimal_workspace())
    updated = model.with_formula_preview_language("root_solving.equation", "mathematica")

    assert updated is not model
    assert model.formula_preview_language("root_solving.equation") is None
    assert updated.formula_preview_language("root_solving.equation") == "mathematica"
    assert updated.compute_hash() == model.compute_hash()


def test_workbench_model_removes_formula_preview_language_without_hash_change() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    model = WorkbenchModel.from_v1_workspace(_minimal_workspace())
    removed = model.without_formula_preview_language("fitting.custom.expression")

    assert removed.formula_preview_languages == {}
    assert "formula_preview" not in removed.to_v1_workspace()["ui"]
    assert removed.compute_hash() == model.compute_hash()


@pytest.mark.parametrize(
    ("schema_key", "language"),
    [
        ("", "python"),
        ("fitting.custom.expression", ""),
        (1, "python"),
        ("fitting.custom.expression", 1),
    ],
)
def test_workbench_model_rejects_invalid_formula_preview_language_updates(
    schema_key: object,
    language: object,
) -> None:
    from datalab_core.workbench_model import WorkbenchModel

    model = WorkbenchModel.from_v1_workspace(_minimal_workspace())

    with pytest.raises(TypeError, match="formula preview"):
        model.with_formula_preview_language(schema_key, language)  # type: ignore[arg-type]


def test_workbench_model_rejects_unknown_formula_preview_language_updates() -> None:
    from datalab_core.workbench_model import WorkbenchModel

    model = WorkbenchModel.from_v1_workspace(_minimal_workspace())

    with pytest.raises(ValueError, match="Unsupported formula preview language"):
        model.with_formula_preview_language("fitting.custom.expression", "javascript")
