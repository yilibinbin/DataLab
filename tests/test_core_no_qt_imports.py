from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_MODULES = (
    "PySide6",
    "app_desktop",
    "app_web",
    "data_extrapolation_latex_latest",
    "datalab_latex",
    "matplotlib",
    "shared.settings_store",
    "shared.presets",
    "shared.ui_keyguards",
    "shared.pdf_preview",
    "shared.pdf_preview_raster",
    "shared.pdf_preview_integration",
    "shared.latex_engine",
    "statistics_utils",
)

STATIC_FORBIDDEN_MODULES = FORBIDDEN_MODULES


def test_datalab_core_import_keeps_qt_and_impure_shared_modules_out() -> None:
    """Future core package must stay UI-neutral in a clean interpreter."""

    probe = f"""
from __future__ import annotations

import importlib.util
import json
import sys

forbidden = {FORBIDDEN_MODULES!r}

if importlib.util.find_spec("datalab_core") is None:
    print(json.dumps({{"status": "missing"}}))
    raise SystemExit(0)

import datalab_core
import datalab_core.jobs
import datalab_core.results
import datalab_core.service_factory
import datalab_core.session
import datalab_core.statistics
import datalab_core.extrapolation
import datalab_core.uncertainty
import datalab_core.root_solving
import datalab_core.fitting
import datalab_core.workbench_model

assert datalab_core.jobs is datalab_core.jobs
assert datalab_core.results is datalab_core.results
assert datalab_core.service_factory is datalab_core.service_factory
assert datalab_core.session is datalab_core.session
assert datalab_core.statistics is datalab_core.statistics
assert datalab_core.extrapolation is datalab_core.extrapolation
assert datalab_core.uncertainty is datalab_core.uncertainty
assert datalab_core.root_solving is datalab_core.root_solving
assert datalab_core.fitting is datalab_core.fitting
assert datalab_core.workbench_model is datalab_core.workbench_model

loaded = sorted(
    name
    for name in sys.modules
    if any(name == forbidden_name or name.startswith(forbidden_name + ".") for forbidden_name in forbidden)
)
print(json.dumps({{"status": "present", "loaded": loaded}}, sort_keys=True))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    if payload["status"] == "missing":
        pytest.skip("datalab_core has not been introduced yet.")

    assert payload["loaded"] == []


def test_datalab_core_has_no_float_constructor_conversions() -> None:
    """Core service/model code must not downcast numeric values to binary floats."""

    violations: list[str] = []
    for path in sorted((REPO_ROOT / "datalab_core").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
                rel_path = path.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_datalab_core_static_imports_stay_headless() -> None:
    """Core modules must not hide adapter/UI imports inside function bodies."""

    violations: list[str] = []
    for path in sorted((REPO_ROOT / "datalab_core").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module_name: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    if _is_forbidden_core_import(module_name):
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:{module_name}")
                continue
            if isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                module_name = node.module
                if _is_forbidden_core_import(module_name):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:{module_name}")

    assert violations == []


def _is_forbidden_core_import(module_name: str) -> bool:
    return any(
        module_name == forbidden or module_name.startswith(forbidden + ".")
        for forbidden in STATIC_FORBIDDEN_MODULES
    )
