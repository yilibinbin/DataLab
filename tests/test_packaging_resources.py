from __future__ import annotations

import ast
from pathlib import Path


def _spec_source() -> str:
    return Path("DataLab.spec").read_text(encoding="utf-8")


def test_pyinstaller_spec_bundles_desktop_docs_and_example_workspaces() -> None:
    source = _spec_source()

    assert '(_rel("docs", "desktop"), "docs/desktop")' in source
    assert '(_rel("examples", "workspaces"), "examples/workspaces")' in source
    assert '(_rel("shared", "help_specs.json"), "shared")' in source


def test_pyinstaller_spec_has_no_private_absolute_resource_paths() -> None:
    tree = ast.parse(_spec_source(), filename="DataLab.spec")
    string_values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]

    assert not any(value.startswith("/Users/") for value in string_values)
    assert not any("localhost" in value.lower() for value in string_values)
