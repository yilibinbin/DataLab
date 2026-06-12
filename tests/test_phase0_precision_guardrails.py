from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATHS = (
    "app_desktop",
    "app_web",
    "cli",
    "datalab_core",
    "datalab_latex",
    "extrapolation_methods",
    "fitting",
    "root_solving",
    "shared",
)
PRECISION_OWNER = ROOT / "shared" / "precision.py"


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for rel_path in PRODUCTION_PATHS:
        path = ROOT / rel_path
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        files.extend(
            candidate
            for candidate in path.rglob("*.py")
            if not candidate.name.startswith("test_")
        )
    return sorted(files)


def _is_mp_dps_target(node: ast.AST) -> bool:
    if not isinstance(node, ast.Attribute) or node.attr != "dps":
        return False
    value = node.value
    if isinstance(value, ast.Name):
        return value.id == "mp"
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "mp"
        and isinstance(value.value, ast.Name)
        and value.value.id == "mp"
    )


def _iter_assignment_targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    if isinstance(node, ast.AugAssign):
        return [node.target]
    return []


def test_production_code_does_not_use_mpmath_workdps() -> None:
    offenders: list[str] = []
    for path in _production_python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "workdps"
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_production_code_only_precision_owner_assigns_mp_dps() -> None:
    offenders: list[str] = []
    for path in _production_python_files():
        if path == PRECISION_OWNER:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if any(_is_mp_dps_target(target) for target in _iter_assignment_targets(node)):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_desktop_shell_modules_avoid_runtime_mpmath_imports() -> None:
    """GUI construction/rendering modules should not import mpmath just for labels or annotations."""
    guarded_paths = (
        ROOT / "app_desktop" / "panels.py",
        ROOT / "app_desktop" / "window_fitting_residuals_mixin.py",
    )
    offenders: list[str] = []
    for path in guarded_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mpmath" or alias.name.startswith("mpmath."):
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "mpmath" or node.module.startswith("mpmath."):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []
