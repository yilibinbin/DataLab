from __future__ import annotations

import ast
import re
from pathlib import Path


PACKAGING_EXCLUDE_ENTRYPOINTS = {
    "DataLab.spec": ("spec", "excludes"),
    "build_mac_data_gui.sh": ("shell", "QT_EXCLUDES"),
    "build_windows_data_gui.ps1": ("powershell", "qtExcludes"),
}


REQUIRED_WEBENGINE_EXCLUDES = (
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
)


def packaging_qt_excludes(repo_root: Path) -> dict[str, list[str]]:
    repo_root = Path(repo_root)
    excludes: dict[str, list[str]] = {}
    for filename, (kind, name) in PACKAGING_EXCLUDE_ENTRYPOINTS.items():
        path = repo_root / filename
        if kind == "spec":
            excludes[filename] = spec_excludes(path)
        elif kind == "shell":
            excludes[filename] = shell_array_values(path, name)
        elif kind == "powershell":
            excludes[filename] = powershell_array_values(path, name)
        else:  # pragma: no cover - defensive for future entrypoint kinds.
            raise ValueError(f"Unsupported packaging exclude parser kind: {kind}")
    return excludes


def exclude_sync_status(excludes: dict[str, list[str]]) -> dict[str, object]:
    entry_sets = {name: set(values) for name, values in excludes.items()}
    reference_name = "DataLab.spec"
    reference = entry_sets.get(reference_name, set())
    synchronized = all(values == reference for values in entry_sets.values())
    duplicates = {
        name: sorted({value for value in values if values.count(value) > 1})
        for name, values in excludes.items()
    }
    missing_from_reference = {
        name: sorted(reference - values)
        for name, values in entry_sets.items()
        if name != reference_name
    }
    extra_vs_reference = {
        name: sorted(values - reference)
        for name, values in entry_sets.items()
        if name != reference_name
    }
    webengine_required = set(REQUIRED_WEBENGINE_EXCLUDES)
    webengine_excluded = all(webengine_required.issubset(values) for values in entry_sets.values())
    return {
        "synchronized": synchronized,
        "duplicates": duplicates,
        "missing_from_reference": missing_from_reference,
        "extra_vs_reference": extra_vs_reference,
        "webengine_excluded": webengine_excluded,
    }


def spec_excludes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = getattr(node.func, "id", None)
        if func_name != "Analysis":
            continue
        for keyword in node.keywords:
            if keyword.arg != "excludes":
                continue
            if not isinstance(keyword.value, ast.List):
                raise AssertionError("DataLab.spec Analysis(excludes=...) must stay a literal list")
            values = []
            for item in keyword.value.elts:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    raise AssertionError("DataLab.spec excludes must contain literal strings only")
                values.append(item.value)
            return values
    raise AssertionError("DataLab.spec does not define Analysis(excludes=...)")


def shell_array_values(path: Path, name: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*\((?P<body>.*?)^\s*\)", text, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"{path.name} does not define {name}=(")
    return quoted_values(strip_line_comments(match.group("body"), "#"))


def powershell_array_values(path: Path, name: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^\s*\${re.escape(name)}\s*=\s*@\((?P<body>.*?)^\s*\)", text, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"{path.name} does not define ${name} = @(")
    return quoted_values(strip_line_comments(match.group("body"), "#"))


def strip_line_comments(text: str, marker: str) -> str:
    lines = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        kept_chars: list[str] = []
        for char in line:
            if escaped:
                kept_chars.append(char)
                escaped = False
                continue
            if char == "\\":
                kept_chars.append(char)
                escaped = True
                continue
            if char in {"'", '"'}:
                quote = None if quote == char else char if quote is None else quote
                kept_chars.append(char)
                continue
            if char == marker and quote is None:
                break
            kept_chars.append(char)
        lines.append("".join(kept_chars))
    return "\n".join(lines)


def quoted_values(text: str) -> list[str]:
    pattern = r"""(?P<quote>["'])(?P<value>[^"']+)(?P=quote)"""
    return [match.group("value") for match in re.finditer(pattern, text)]


__all__ = [
    "PACKAGING_EXCLUDE_ENTRYPOINTS",
    "REQUIRED_WEBENGINE_EXCLUDES",
    "exclude_sync_status",
    "packaging_qt_excludes",
    "powershell_array_values",
    "quoted_values",
    "shell_array_values",
    "spec_excludes",
    "strip_line_comments",
]
