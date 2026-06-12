from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
V2_FIXTURE = Path("tests/fixtures/workspaces/model_native_v2_minimal.datalab")


def _minimal_manifest() -> dict[str, object]:
    return {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "app": {"name": "DataLab", "version": "2.0.2"},
        "created_at": "2026-05-26T00:00:00Z",
        "updated_at": "2026-05-26T00:00:00Z",
        "workspace": {
            "title": "Untitled",
            "current_mode": "fitting",
            "language": "auto",
            "ui": {"main_tab": "results"},
            "data": {
                "source_kind": "manual_table",
                "decoded_text": "A\tB\n1\t2\n",
                "encoding": "utf-8",
                "newline": "lf",
                "original_bytes_sha256": "sha256:59b4f9834e1e702bb8f170788a3e6ebddfd7d06c01d841a6b611e6fdab8c0f9e",
                "raw_bytes_path": None,
                "canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]},
                "sha256": "sha256:59b4f9834e1e702bb8f170788a3e6ebddfd7d06c01d841a6b611e6fdab8c0f9e",
            },
            "constants": {"enabled": False},
            "config": {
                "common": {"mpmath_precision": 16, "display_digits": 10},
                "fitting": {"model": "custom", "expression": "A*x + B"},
            },
            "result_snapshot": {"present": False},
        },
    }


def _minimal_v2_manifest() -> dict[str, object]:
    return {
        "schema": "datalab.workspace.v2",
        "schema_version": 2,
        "app": {"name": "DataLab", "version": "2.0.2"},
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
        "model": {
            "title": "V2 Case",
            "current_mode": "root_solving",
            "language": "en",
            "compute": {
                "data": {
                    "source_kind": "manual_table",
                    "decoded_text": "A\tB\n1\t2\n",
                    "canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]},
                },
                "constants": {"enabled": False},
                "config": {
                    "root_solving": {
                        "equations": "x^2 - A",
                        "mode": "scalar",
                        "unknowns": [{"name": "x", "initial": "1", "lower": "0", "upper": "2"}],
                    }
                },
            },
            "ui": {"formula_preview": {"root_solving.equations": "latex"}},
            "result_snapshot": {"present": False},
        },
    }


def _write_workspace_archive(
    path: Path,
    manifest: dict[str, object],
    attachments: dict[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
        for name, payload in sorted((attachments or {}).items()):
            zf.writestr(name, payload)


def test_workspace_write_read_round_trip_with_plot_attachment(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace, write_workspace
    from shared.workspace_schema import sha256_bytes

    manifest = _minimal_manifest()
    manifest["workspace"]["result_snapshot"] = {  # type: ignore[index]
        "present": True,
        "kind": "fit_single",
        "result_of_hash": "sha256:placeholder",
        "snapshot_only": True,
        "stale": False,
        "markdown": "result",
        "log": "done",
        "csv": {"headers": ["name"], "rows": [{"name": "A"}]},
        "latex_source": "\\begin{table}\\end{table}",
        "plots": [
            {
                "path": "attachments/plots/plot-001.png",
                "role": "primary",
                "order": 0,
                "title": "Plot",
                "format": "png",
                "sha256": sha256_bytes(PNG_BYTES),
            }
        ],
    }

    target = tmp_path / "analysis.datalab"
    write_workspace(target, manifest, {"attachments/plots/plot-001.png": PNG_BYTES})

    loaded = read_workspace(target)
    assert loaded.manifest["workspace"]["title"] == "Untitled"
    assert loaded.attachments["attachments/plots/plot-001.png"] == PNG_BYTES


def test_workspace_writer_uses_byte_stable_archive_layout(tmp_path: Path) -> None:
    from shared.workspace_io import write_workspace

    target = tmp_path / "stable.datalab"
    write_workspace(target, _minimal_manifest(), {})

    with zipfile.ZipFile(target) as zf:
        manifest_info = zf.getinfo("manifest.json")
        manifest_text = zf.read("manifest.json").decode("utf-8")

    assert manifest_info.compress_type == zipfile.ZIP_STORED
    assert json.loads(manifest_text) == _minimal_manifest()
    assert manifest_text == json.dumps(
        _minimal_manifest(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def test_workspace_rejects_future_schema(tmp_path: Path) -> None:
    from shared.workspace_io import write_workspace
    from shared.workspace_schema import WorkspaceValidationError

    manifest = _minimal_manifest()
    manifest["schema_version"] = 99

    with pytest.raises(WorkspaceValidationError, match="schema_version"):
        write_workspace(tmp_path / "bad.datalab", manifest, {})


def test_workspace_read_dispatches_v2_manifest_through_public_zip_path(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace

    target = tmp_path / "v2.datalab"
    _write_workspace_archive(target, _minimal_v2_manifest())

    loaded = read_workspace(target)

    assert loaded.manifest["schema"] == "datalab.workspace.v2"
    assert loaded.manifest["schema_version"] == 2
    assert loaded.manifest["workspace"]["title"] == "V2 Case"
    assert loaded.manifest["workspace"]["current_mode"] == "root_solving"
    assert loaded.manifest["workspace"]["config"]["root_solving"]["mode"] == "scalar"
    assert loaded.manifest["workspace"]["ui"]["formula_preview"] == {"root_solving.equations": "latex"}


def test_workspace_read_dispatches_v2_attachments_and_validates_hashes(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError, sha256_bytes

    manifest = _minimal_v2_manifest()
    manifest["model"]["result_snapshot"] = {  # type: ignore[index]
        "present": True,
        "plots": [
            {
                "path": "attachments/plots/plot-001.png",
                "format": "png",
                "sha256": sha256_bytes(PNG_BYTES),
            }
        ],
    }
    target = tmp_path / "v2-plot.datalab"
    _write_workspace_archive(target, manifest, {"attachments/plots/plot-001.png": PNG_BYTES})

    loaded = read_workspace(target)
    assert loaded.attachments["attachments/plots/plot-001.png"] == PNG_BYTES

    manifest["model"]["result_snapshot"]["plots"][0]["sha256"] = "sha256:bad"  # type: ignore[index]
    bad_target = tmp_path / "v2-bad-plot.datalab"
    _write_workspace_archive(bad_target, manifest, {"attachments/plots/plot-001.png": PNG_BYTES})

    with pytest.raises(WorkspaceValidationError, match="hash"):
        read_workspace(bad_target)


def test_workspace_writer_remains_v1_only_by_default(tmp_path: Path) -> None:
    from shared.workspace_io import write_workspace
    from shared.workspace_schema import WorkspaceValidationError

    with pytest.raises(WorkspaceValidationError, match="schema"):
        write_workspace(tmp_path / "v2-writer-disabled.datalab", _minimal_v2_manifest(), {})


def test_v2_fixture_reads_through_public_io_path() -> None:
    from shared.workspace_io import read_workspace

    loaded = read_workspace(V2_FIXTURE)

    assert loaded.manifest["schema"] == "datalab.workspace.v2"
    assert loaded.manifest["schema_version"] == 2
    assert loaded.manifest["workspace"]["title"] == "Model-native v2 fixture"
    assert loaded.manifest["workspace"]["current_mode"] == "fitting"
    assert loaded.manifest["workspace"]["config"]["fitting"]["expression"] == "a*x"
    assert loaded.manifest["workspace"]["ui"]["formula_preview"] == {
        "fitting.custom.expression": "latex"
    }
    assert loaded.attachments["attachments/plots/plot-001.png"].startswith(b"\x89PNG")


def test_v2_fixture_compatible_workspace_matches_core_adapter() -> None:
    from datalab_core import workspace_v2
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import compute_workspace_hash

    loaded = read_workspace(V2_FIXTURE)
    expected_workspace = workspace_v2.to_v1_workspace(loaded.manifest)

    assert loaded.manifest["workspace"] == expected_workspace
    assert compute_workspace_hash(loaded.manifest["workspace"]).startswith("sha256:")


def test_workspace_read_v2_rejects_compute_json_floats_as_validation_error(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError

    manifest = _minimal_v2_manifest()
    manifest["model"]["compute"]["config"]["common"] = {"precision_digits": 32.0}  # type: ignore[index]
    target = tmp_path / "v2-float.datalab"
    _write_workspace_archive(target, manifest)

    with pytest.raises(WorkspaceValidationError, match="JSON floats"):
        read_workspace(target)


def test_workspace_read_v2_formula_preview_ui_does_not_change_compute_hash(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import compute_workspace_hash

    left = _minimal_v2_manifest()
    right = _minimal_v2_manifest()
    left["model"]["ui"] = {"formula_preview": {"fitting.custom.expression": "latex"}}  # type: ignore[index]
    right["model"]["ui"] = {"formula_preview": {"fitting.custom.expression": "python"}}  # type: ignore[index]
    left_path = tmp_path / "left.datalab"
    right_path = tmp_path / "right.datalab"
    _write_workspace_archive(left_path, left)
    _write_workspace_archive(right_path, right)

    left_workspace = read_workspace(left_path).manifest["workspace"]
    right_workspace = read_workspace(right_path).manifest["workspace"]

    assert compute_workspace_hash(left_workspace) == compute_workspace_hash(right_workspace)


def test_workspace_read_v2_source_attachments_share_path_and_hash_validation(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError, sha256_bytes

    source_bytes = b"x\ty\n1\t2\n"
    manifest = _minimal_v2_manifest()
    data = manifest["model"]["compute"]["data"]  # type: ignore[index]
    data["raw_bytes_path"] = "attachments/sources/data.tsv"
    data["original_bytes_sha256"] = sha256_bytes(source_bytes)
    target = tmp_path / "v2-source.datalab"
    _write_workspace_archive(target, manifest, {"attachments/sources/data.tsv": source_bytes})

    loaded = read_workspace(target)
    assert loaded.attachments["attachments/sources/data.tsv"] == source_bytes

    data["original_bytes_sha256"] = "sha256:bad"
    bad_target = tmp_path / "v2-bad-source.datalab"
    _write_workspace_archive(bad_target, manifest, {"attachments/sources/data.tsv": source_bytes})

    with pytest.raises(WorkspaceValidationError, match="source attachment hash mismatch"):
        read_workspace(bad_target)


def test_workspace_read_v2_still_rejects_hostile_paths_before_schema_dispatch(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError

    target = tmp_path / "v2-hostile.datalab"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("manifest.json", json.dumps(_minimal_v2_manifest()).encode("utf-8"))
        zf.writestr("attachments/plots/../evil.png", b"x")

    with pytest.raises(WorkspaceValidationError, match="unsafe archive path"):
        read_workspace(target)


@pytest.mark.parametrize(
    "entry_name",
    [
        "/absolute/manifest.json",
        "../manifest.json",
        "attachments/plots/../evil.png",
        "C:/temp/evil.png",
        "attachments/unknown/file.bin",
    ],
)
def test_workspace_rejects_hostile_paths(tmp_path: Path, entry_name: str) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError

    target = tmp_path / "hostile.datalab"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr(entry_name, b"x")

    with pytest.raises(WorkspaceValidationError):
        read_workspace(target)


def test_workspace_rejects_duplicate_manifest(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace
    from shared.workspace_schema import WorkspaceValidationError

    target = tmp_path / "duplicate.datalab"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("manifest.json", "{}")

    with pytest.raises(WorkspaceValidationError, match="manifest"):
        read_workspace(target)


def test_workspace_rejects_bad_plot_hash(tmp_path: Path) -> None:
    from shared.workspace_io import write_workspace
    from shared.workspace_schema import WorkspaceValidationError

    manifest = _minimal_manifest()
    manifest["workspace"]["result_snapshot"] = {  # type: ignore[index]
        "present": True,
        "plots": [
            {
                "path": "attachments/plots/plot-001.png",
                "format": "png",
                "sha256": "sha256:bad",
            }
        ],
    }

    with pytest.raises(WorkspaceValidationError, match="hash"):
        write_workspace(tmp_path / "bad-plot.datalab", manifest, {"attachments/plots/plot-001.png": PNG_BYTES})


def test_workspace_hash_ignores_display_only_fields() -> None:
    from shared.workspace_schema import compute_workspace_hash

    left = _minimal_manifest()["workspace"]
    right = _minimal_manifest()["workspace"]
    left["config"]["common"]["display_digits"] = 10  # type: ignore[index]
    right["config"]["common"]["display_digits"] = 40  # type: ignore[index]

    assert compute_workspace_hash(left) == compute_workspace_hash(right)

    right["config"]["common"]["mpmath_precision"] = 80  # type: ignore[index]
    assert compute_workspace_hash(left) != compute_workspace_hash(right)


def test_workspace_atomic_save_keeps_previous_file_on_validation_failure(tmp_path: Path) -> None:
    from shared.workspace_io import read_workspace, write_workspace
    from shared.workspace_schema import WorkspaceValidationError

    target = tmp_path / "analysis.datalab"
    write_workspace(target, _minimal_manifest(), {})
    before = target.read_bytes()

    bad = _minimal_manifest()
    bad["schema_version"] = 2
    with pytest.raises(WorkspaceValidationError):
        write_workspace(target, bad, {})

    assert target.read_bytes() == before
    assert read_workspace(target).manifest["schema_version"] == 1
