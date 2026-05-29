from __future__ import annotations

from pathlib import Path


EXAMPLE_NAMES = {
    "extrapolation.datalab",
    "error-propagation.datalab",
    "statistics.datalab",
    "fitting.datalab",
}


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


def test_fitting_example_contains_required_variants():
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/fitting.datalab"))
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert {"custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"} <= set(variants)
