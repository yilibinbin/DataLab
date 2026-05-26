from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


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


def test_workspace_rejects_future_schema(tmp_path: Path) -> None:
    from shared.workspace_io import write_workspace
    from shared.workspace_schema import WorkspaceValidationError

    manifest = _minimal_manifest()
    manifest["schema_version"] = 99

    with pytest.raises(WorkspaceValidationError, match="schema_version"):
        write_workspace(tmp_path / "bad.datalab", manifest, {})


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
