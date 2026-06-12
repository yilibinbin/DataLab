from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FORBIDDEN_SHIPPING_IMPORTS = (
    "shared.pdf_preview",
    "shared.pdf_preview_integration",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
)


@dataclass(frozen=True, slots=True)
class ImportViolation:
    path: Path
    line: int
    module: str


def shipping_source_paths(repo_root: Path) -> list[Path]:
    root = Path(repo_root)
    sources = [root / "data_extrapolation_gui.py"]
    app_desktop = root / "app_desktop"
    if app_desktop.exists():
        sources.extend(sorted(app_desktop.rglob("*.py")))
    return [path for path in sources if path.exists()]


def webengine_import_violations(paths: Iterable[Path]) -> list[ImportViolation]:
    violations: list[ImportViolation] = []
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_import(alias.name):
                        violations.append(ImportViolation(Path(path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = _absolute_import_from_module(node)
                if module and _is_forbidden_import(module):
                    violations.append(ImportViolation(Path(path), node.lineno, module))
    return sorted(violations, key=lambda item: (str(item.path), item.line, item.module))


def _absolute_import_from_module(node: ast.ImportFrom) -> str | None:
    if node.level:
        return None
    return node.module


def _is_forbidden_import(module: str) -> bool:
    return any(module == forbidden or module.startswith(forbidden + ".") for forbidden in FORBIDDEN_SHIPPING_IMPORTS)


__all__ = [
    "FORBIDDEN_SHIPPING_IMPORTS",
    "ImportViolation",
    "shipping_source_paths",
    "webengine_import_violations",
]
