from __future__ import annotations

from pathlib import Path


EXAMPLE_NAMES = {
    "extrapolation.datalab",
    "error-propagation.datalab",
    "statistics.datalab",
    "fitting.datalab",
}


def _source_paths(manifest: dict) -> set[str]:
    paths = set(manifest.get("examples", {}).get("source_files", []))
    workspace = manifest["workspace"]
    for section_name in ("data", "constants"):
        section = workspace.get(section_name) or {}
        source_path = section.get("source_path")
        if source_path:
            paths.add(source_path)
    return paths


def test_canonical_example_workspaces_exist_and_open():
    from shared.workspace_io import read_workspace

    root = Path("examples/workspaces")
    found = {path.name for path in root.glob("*.datalab")}
    assert found == EXAMPLE_NAMES

    for name in EXAMPLE_NAMES:
        loaded = read_workspace(root / name)
        assert loaded.manifest["schema_version"]
        assert loaded.manifest["config"]
        assert loaded.manifest["data"]


def test_build_examples_is_deterministic():
    from tools.generate_example_workspaces import build_examples

    assert build_examples() == build_examples()


def test_example_generator_records_checked_in_source_files():
    from tools.generate_example_workspaces import build_examples

    manifests = build_examples()

    assert _source_paths(manifests["extrapolation.datalab"]) == {"examples/extrapolation_richardson.txt"}
    assert _source_paths(manifests["error-propagation.datalab"]) == {
        "examples/error_propagation.txt",
        "examples/constants.txt",
    }
    assert _source_paths(manifests["statistics.datalab"]) == {"examples/statistics_weighted.txt"}
    assert _source_paths(manifests["fitting.datalab"]) == {"examples/fitting_powerlaw.txt"}


def test_fitting_example_contains_required_variants():
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/fitting.datalab"))
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert {"custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"} <= set(variants)
