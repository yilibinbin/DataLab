"""Desktop multiprocessing entrypoints must route frozen workers early.

Auto-fit uses ``multiprocessing`` with the ``spawn`` start method. In a
PyInstaller-frozen GUI app, child worker processes re-enter the executable; if
``freeze_support()`` does not run before GUI imports, those workers can create
extra DataLab windows instead of running the multiprocessing worker payload.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _top_level_event_order(path: str, protected_import_roots: set[str]) -> list[tuple[str, int]]:
    source_path = REPO_ROOT / path
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    events: list[tuple[str, int]] = []

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "freeze_support":
                events.append(("freeze_support", node.lineno))
            elif isinstance(func, ast.Name) and func.id == "freeze_support":
                events.append(("freeze_support", node.lineno))
            continue

        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in protected_import_roots:
                    events.append(("protected_import", node.lineno))
                    break
            continue

        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in protected_import_roots:
                events.append(("protected_import", node.lineno))

    return events


def _assert_freeze_support_before_gui_imports(
    path: str,
    protected_import_roots: set[str],
) -> None:
    events = _top_level_event_order(path, protected_import_roots)
    freeze_lines = [lineno for event, lineno in events if event == "freeze_support"]
    import_lines = [lineno for event, lineno in events if event == "protected_import"]

    assert freeze_lines, (
        f"{path} must call multiprocessing.freeze_support() at module top-level "
        "so frozen auto-fit worker processes do not launch the GUI."
    )
    assert import_lines, f"{path} test expected at least one protected GUI import."
    assert min(freeze_lines) < min(import_lines), (
        f"{path} must call multiprocessing.freeze_support() before importing "
        "GUI modules; event order was {events!r}."
    )


def test_root_gui_shim_calls_freeze_support_before_app_desktop_import() -> None:
    _assert_freeze_support_before_gui_imports(
        "data_extrapolation_gui.py",
        {"app_desktop", "PySide6"},
    )


def test_app_desktop_main_calls_freeze_support_before_qt_imports() -> None:
    _assert_freeze_support_before_gui_imports(
        "app_desktop/main.py",
        {"PySide6"},
    )
