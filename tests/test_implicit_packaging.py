from __future__ import annotations

from pathlib import Path
import re


def test_pyinstaller_packaging_collects_sympy() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = (root / "DataLab.spec").read_text(encoding="utf-8")
    mac = (root / "build_mac_data_gui.sh").read_text(encoding="utf-8")
    win = (root / "build_windows_data_gui.ps1").read_text(encoding="utf-8-sig")

    hidden_imports = re.search(r"hiddenimports\s*=\s*\[(?P<body>.*?)\]", spec, re.S)
    assert hidden_imports is not None
    for package in ('"mpmath"', '"sympy"', '"emcee"', '"corner"'):
        assert package in hidden_imports.group("body")

    collect_loop = re.search(r"for\s+_pkg\s+in\s+\(([^)]*)\):", spec)
    assert collect_loop is not None
    for package in ('"mpmath"', '"sympy"', '"emcee"', '"corner"'):
        assert package in collect_loop.group(1)

    assert '--hidden-import "sympy"' in mac
    assert '--collect-all "sympy"' in mac
    assert '"--hidden-import", "sympy"' in win
    assert '"--collect-all", "sympy"' in win
