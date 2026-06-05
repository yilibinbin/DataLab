"""Backward-compatible desktop GUI entry point.

The full implementation has moved to `app_desktop.main` for maintainability.
This module re-exports the public API so existing imports keep working.
"""

from __future__ import annotations

import multiprocessing

# Frozen multiprocessing workers must be diverted before GUI imports.
multiprocessing.freeze_support()

from app_desktop import main as _main  # noqa: E402

_globals = globals()
_export_names = getattr(_main, "__all__", None)
if _export_names:
    _names = list(_export_names)
else:
    _names = [name for name in _main.__dict__ if not name.startswith("_")]

__all__: list[str] = []
for _name in _names:
    if _name.startswith("_"):
        continue
    if hasattr(_main, _name):
        _globals[_name] = getattr(_main, _name)
        __all__.append(_name)

main = _main.main
if "main" not in __all__:
    __all__.append("main")

del _globals, _export_names, _names, _name, _main


if __name__ == "__main__":
    main()
