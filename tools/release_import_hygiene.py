"""Release gate for local imports that would fail from a clean checkout.

The checker is static and repository-scoped. Its general scan validates
project-local ``import ...`` and ``from ... import ...`` statements against the
staged Git index. Dynamic import validation is intentionally narrower: it is
used only while proving package ``__init__.py`` facade exports.

Package facade support documents the shapes used in this repo: real definitions
or import-created attributes in ``__init__.py``, literal ``__getattr__(name)``
branches that return a value before raising, dynamic ``_EXPORT_MODULES`` /
``__all__`` maps only when ``__getattr__`` can return from that map, and facade
calls through proven stdlib ``importlib.import_module`` or ``__import__`` names.
This is not a general Python import emulator. Unsupported dynamic patterns
should be covered by ordinary import-smoke tests or made explicit here with
focused regressions; clean import-smoke tests remain the authoritative release
proof for runtime importability.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitMetadataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportIssue:
    importer: str
    line: int
    module: str
    target: str
    status: str

    def format(self) -> str:
        return f"{self.importer}:{self.line}: {self.module} -> {self.target} ({self.status})"


def git_index_python_sources(root: Path = ROOT) -> tuple[set[str], dict[str, str]]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--stage", "--", "*.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise GitMetadataUnavailable(stderr or "git ls-files --stage failed")
    blob_by_path: dict[str, str] = {}
    for entry in result.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if not entry:
            continue
        try:
            metadata, relpath = entry.split("\t", 1)
            _mode, blob_sha, _stage = metadata.split(" ", 2)
        except ValueError as exc:
            raise GitMetadataUnavailable(f"unexpected git ls-files --stage output: {entry!r}") from exc
        blob_by_path[relpath] = blob_sha
    tracked = set(blob_by_path)
    sources: dict[str, str] = {}
    if not blob_by_path:
        return tracked, sources

    sorted_paths = sorted(blob_by_path)
    batch_input = "".join(f"{blob_by_path[path]}\n" for path in sorted_paths).encode("ascii")
    cat_result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input=batch_input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cat_result.returncode != 0:
        stderr = cat_result.stderr.decode("utf-8", "replace").strip()
        raise GitMetadataUnavailable(stderr or "git cat-file --batch failed")

    output = memoryview(cat_result.stdout)
    offset = 0
    for relpath in sorted_paths:
        newline = cat_result.stdout.find(b"\n", offset)
        if newline < 0:
            raise GitMetadataUnavailable(f"missing git cat-file header for {relpath}")
        header = bytes(output[offset:newline]).decode("ascii", "replace")
        offset = newline + 1
        fields = header.split()
        if len(fields) != 3 or fields[1] != "blob":
            raise GitMetadataUnavailable(f"unexpected git cat-file header for {relpath}: {header!r}")
        size = int(fields[2])
        blob = bytes(output[offset : offset + size])
        sources[relpath] = blob.decode("utf-8", "surrogateescape")
        offset += size
        if offset < len(output) and output[offset] == 10:
            offset += 1
    return tracked, sources


def find_import_hygiene_issues(
    root: Path,
    tracked_python_files: set[str],
    *,
    source_texts: dict[str, str] | None = None,
) -> list[ImportIssue]:
    tracked = set(tracked_python_files)
    include_worktree = source_texts is None
    local_roots = _local_import_roots(root, tracked, include_worktree=include_worktree)
    issues: list[ImportIssue] = []

    for relpath in sorted(tracked):
        source_path = root / relpath
        try:
            source_text = (
                source_texts[relpath]
                if source_texts is not None
                else source_path.read_text(encoding="utf-8")
            )
            tree = ast.parse(source_text, filename=relpath)
        except KeyError as exc:
            issues.append(
                ImportIssue(
                    importer=relpath,
                    line=0,
                    module="<parse>",
                    target=relpath,
                    status=f"missing source text: {exc}",
                )
            )
            continue
        except (OSError, SyntaxError) as exc:
            issues.append(
                ImportIssue(
                    importer=relpath,
                    line=getattr(exc, "lineno", 0) or 0,
                    module="<parse>",
                    target=relpath,
                    status=f"unreadable: {exc}",
                )
            )
            continue

        for module, line, required, allow_package_attr in _iter_imported_modules(tree, relpath):
            top_level = module.split(".", 1)[0]
            target = _resolve_module_path(root, tracked, module, include_worktree=include_worktree)
            namespace_target = _resolve_namespace_package_dir(root, tracked, module, include_worktree=include_worktree)
            if source_texts is not None and target is None and namespace_target is None:
                worktree_target = _resolve_module_path(root, tracked, module, include_worktree=True)
                worktree_namespace_target = _resolve_namespace_package_dir(
                    root,
                    tracked,
                    module,
                    include_worktree=True,
                )
                if worktree_target is not None and worktree_target not in tracked:
                    issues.append(
                        ImportIssue(
                            importer=relpath,
                            line=line,
                            module=module,
                            target=worktree_target,
                            status="untracked local module",
                        )
                    )
                    continue
                if worktree_namespace_target is not None and not _is_namespace_package_root(tracked, module):
                    issues.append(
                        ImportIssue(
                            importer=relpath,
                            line=line,
                            module=module,
                            target=worktree_namespace_target,
                            status="untracked local namespace package",
                        )
                    )
                    continue
            if top_level not in local_roots and target is None and namespace_target is None:
                continue
            if top_level not in local_roots and target in tracked:
                continue
            if target is None and namespace_target is not None:
                if _is_namespace_package_root(tracked, module):
                    continue
                issues.append(
                    ImportIssue(
                        importer=relpath,
                        line=line,
                        module=module,
                        target=namespace_target,
                        status="untracked local namespace package",
                    )
                )
                continue
            if target is None:
                if _is_namespace_package_root(tracked, module):
                    continue
                if not required and _parent_module_absent(root, tracked, module, include_worktree=include_worktree):
                    continue
                if not required and _parent_is_module_file(root, tracked, module, include_worktree=include_worktree):
                    continue
                if allow_package_attr and _is_package_defined_export(
                    root,
                    tracked,
                    module,
                    source_texts,
                    include_worktree=include_worktree,
                    before_line=line if _package_init_rel_for_module(module) == relpath else None,
                ):
                    continue
                if allow_package_attr and _is_explicit_package_export(
                    root,
                    tracked,
                    module,
                    source_texts,
                    include_worktree=include_worktree,
                    before_line=line if _package_init_rel_for_module(module) == relpath else None,
                ):
                    continue
                issues.append(
                    ImportIssue(
                        importer=relpath,
                        line=line,
                        module=module,
                        target=_module_to_file_hint(module),
                        status="missing from clean checkout",
                    )
                )
                continue
            if target not in tracked:
                issues.append(
                    ImportIssue(
                        importer=relpath,
                        line=line,
                        module=module,
                        target=target,
                        status="untracked local module",
                    )
                )

        for package_module, line in _iter_star_imported_packages(tree, relpath):
            issues.extend(
                _star_import_hygiene_issues(
                    root,
                    tracked,
                    relpath,
                    package_module,
                    line,
                    local_roots,
                    source_texts,
                    include_worktree=include_worktree,
                )
            )

    return issues


def _local_import_roots(root: Path, tracked: set[str], *, include_worktree: bool = True) -> set[str]:
    roots: set[str] = set()
    for relpath in tracked:
        path = Path(relpath)
        if len(path.parts) == 1 and path.suffix == ".py":
            roots.add(path.stem)
        elif len(path.parts) >= 2 and path.suffix == ".py":
            roots.add(path.parts[0])

    if include_worktree:
        for init_file in root.glob("*/__init__.py"):
            roots.add(init_file.parent.name)
    return roots


def _iter_imported_modules(tree: ast.AST, importer: str) -> list[tuple[str, int, bool, bool]]:
    modules: list[tuple[str, int, bool, bool]] = []
    importer_module = _module_name_from_path(importer)
    importer_path = Path(importer)
    importer_package = (
        importer_module
        if importer_path.stem == "__init__"
        else importer_module.rsplit(".", 1)[0]
        if "." in importer_module
        else ""
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append((alias.name, node.lineno, True, False))
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_import_from(node.module or "", node.level, importer_package)
            if base:
                modules.append((base, node.lineno, True, False))
            for alias in node.names:
                if alias.name == "*":
                    continue
                child = f"{base}.{alias.name}" if base else alias.name
                child_required = node.level > 0 and not node.module
                modules.append((child, node.lineno, child_required, True))

    return modules


def _iter_star_imported_packages(tree: ast.AST, importer: str) -> list[tuple[str, int]]:
    modules: list[tuple[str, int]] = []
    importer_module = _module_name_from_path(importer)
    importer_path = Path(importer)
    importer_package = (
        importer_module
        if importer_path.stem == "__init__"
        else importer_module.rsplit(".", 1)[0]
        if "." in importer_module
        else ""
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not any(alias.name == "*" for alias in node.names):
            continue
        base = _absolute_import_from(node.module or "", node.level, importer_package)
        if base:
            modules.append((base, node.lineno))
    return modules


def _star_import_hygiene_issues(
    root: Path,
    tracked: set[str],
    importer: str,
    package_module: str,
    line: int,
    local_roots: set[str],
    source_texts: dict[str, str] | None,
    *,
    include_worktree: bool = True,
) -> list[ImportIssue]:
    top_level = package_module.split(".", 1)[0]
    package_target = _resolve_module_path(root, tracked, package_module, include_worktree=include_worktree)
    namespace_target = _resolve_namespace_package_dir(root, tracked, package_module, include_worktree=include_worktree)
    if top_level not in local_roots and package_target is None and namespace_target is None:
        return []

    issues: list[ImportIssue] = []
    for export_name in sorted(
        _star_import_export_candidates(
            root,
            tracked,
            package_module,
            source_texts,
            include_worktree=include_worktree,
        )
    ):
        module = f"{package_module}.{export_name}" if package_module else export_name
        target = _resolve_module_path(root, tracked, module, include_worktree=include_worktree)
        namespace_export = _resolve_namespace_package_dir(root, tracked, module, include_worktree=include_worktree)
        if target is not None and target in tracked:
            continue
        if namespace_export is not None and _is_namespace_package_root(tracked, module):
            continue
        if source_texts is not None and target is None and namespace_export is None:
            worktree_target = _resolve_module_path(root, tracked, module, include_worktree=True)
            if worktree_target is not None and worktree_target not in tracked:
                issues.append(
                    ImportIssue(
                        importer=importer,
                        line=line,
                        module=module,
                        target=worktree_target,
                        status="untracked local module",
                    )
                )
                continue
        if _is_package_defined_export(
            root,
            tracked,
            module,
            source_texts,
            include_worktree=include_worktree,
        ) or _is_explicit_package_export(
            root,
            tracked,
            module,
            source_texts,
            include_worktree=include_worktree,
        ):
            continue
        issues.append(
            ImportIssue(
                importer=importer,
                line=line,
                module=module,
                target=target or _module_to_file_hint(module),
                status="missing from clean checkout" if target is None else "untracked local module",
            )
        )
    return issues


def _star_import_export_candidates(
    root: Path,
    tracked: set[str],
    package_module: str,
    source_texts: dict[str, str] | None,
    *,
    include_worktree: bool = True,
) -> set[str]:
    package_init_rel = (Path(*package_module.split(".")) / "__init__.py").as_posix()
    if package_init_rel not in tracked and not (include_worktree and (root / package_init_rel).exists()):
        return set()
    try:
        if source_texts is not None:
            source_text = source_texts.get(package_init_rel)
            if source_text is None:
                return set()
        else:
            source_text = (root / package_init_rel).read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=package_init_rel)
    except (OSError, SyntaxError):
        return set()

    all_exports: set[str] = set()
    mapping_exports: dict[str, set[str]] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    mapping_exports[target.id] = _literal_export_names_from_value(node.value)
                if isinstance(target, ast.Name) and target.id == "__all__":
                    all_exports = _all_exports_from_value(node.value, mapping_exports)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                mapping_exports[node.target.id] = _literal_export_names_from_value(node.value)
                if node.target.id == "__all__":
                    all_exports = _all_exports_from_value(node.value, mapping_exports)
        elif isinstance(node, ast.AugAssign) and _is_all_name(node.target) and isinstance(node.op, ast.Add):
            all_exports.update(_all_exports_from_value(node.value, mapping_exports))
        elif isinstance(node, ast.Expr):
            all_exports.update(_all_mutation_exports(node.value, mapping_exports))
    return all_exports


def _absolute_import_from(module: str, level: int, importer_package: str) -> str:
    if level <= 0:
        return module
    package_parts = importer_package.split(".") if importer_package else []
    if level > len(package_parts) + 1:
        return module
    prefix = package_parts[: len(package_parts) - level + 1]
    parts = [*prefix]
    if module:
        parts.extend(module.split("."))
    return ".".join(part for part in parts if part)


def _module_name_from_path(relpath: str) -> str:
    path = Path(relpath)
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_module_path(root: Path, tracked: set[str], module: str, *, include_worktree: bool = True) -> str | None:
    module_path = Path(*module.split("."))
    file_path = module_path.with_suffix(".py")
    package_path = module_path / "__init__.py"

    candidates = (file_path.as_posix(), package_path.as_posix())
    for candidate in candidates:
        if candidate in tracked:
            return candidate
    if not include_worktree:
        return None
    for candidate in candidates:
        if (root / candidate).exists():
            return candidate
    return None


def _resolve_namespace_package_dir(
    root: Path,
    tracked: set[str],
    module: str,
    *,
    include_worktree: bool = True,
) -> str | None:
    module_dir_rel = Path(*module.split("."))
    prefix = f"{module_dir_rel.as_posix()}/"
    if any(path.startswith(prefix) and path.endswith(".py") for path in tracked):
        return prefix
    if not include_worktree:
        return None
    module_dir = root / module_dir_rel
    if module_dir.is_dir() and any(path.is_file() for path in module_dir.rglob("*.py")):
        return prefix
    return None


def _parent_is_module_file(root: Path, tracked: set[str], module: str, *, include_worktree: bool = True) -> bool:
    parts = module.split(".")
    if len(parts) < 2:
        return False
    parent_file = Path(*parts[:-1]).with_suffix(".py").as_posix()
    return parent_file in tracked or (include_worktree and (root / parent_file).exists())


def _parent_module_absent(root: Path, tracked: set[str], module: str, *, include_worktree: bool = True) -> bool:
    parts = module.split(".")
    if len(parts) < 2:
        return False
    parent_module = ".".join(parts[:-1])
    if _is_namespace_package_root(tracked, parent_module):
        return False
    return _resolve_module_path(root, tracked, parent_module, include_worktree=include_worktree) is None


def _is_namespace_package_root(tracked: set[str], module: str) -> bool:
    prefix = f"{Path(*module.split('.')).as_posix()}/"
    return any(path.startswith(prefix) and path.endswith(".py") for path in tracked)


def _is_explicit_package_export(
    root: Path,
    tracked: set[str],
    module: str,
    source_texts: dict[str, str] | None,
    *,
    include_worktree: bool = True,
    before_line: int | None = None,
) -> bool:
    parts = module.split(".")
    if len(parts) < 2:
        return False
    package_init = Path(*parts[:-1]) / "__init__.py"
    package_init_rel = package_init.as_posix()
    if package_init_rel not in tracked and not (include_worktree and (root / package_init_rel).exists()):
        return False

    exported_name = parts[-1]
    try:
        if source_texts is not None:
            source_text = source_texts.get(package_init_rel)
            if source_text is None:
                return False
        else:
            source_text = (root / package_init_rel).read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=package_init_rel)
    except (OSError, SyntaxError):
        return False

    package_module = ".".join(parts[:-1])
    return exported_name in _explicit_exports_from_package_init(
        tree,
        root,
        tracked,
        package_module,
        exported_name,
        include_worktree=include_worktree,
        before_line=before_line,
    )


def _is_package_defined_export(
    root: Path,
    tracked: set[str],
    module: str,
    source_texts: dict[str, str] | None,
    *,
    include_worktree: bool = True,
    before_line: int | None = None,
) -> bool:
    parts = module.split(".")
    if len(parts) < 2:
        return False
    package_init_rel = (Path(*parts[:-1]) / "__init__.py").as_posix()
    if package_init_rel not in tracked and not (include_worktree and (root / package_init_rel).exists()):
        return False
    try:
        if source_texts is not None:
            source_text = source_texts.get(package_init_rel)
            if source_text is None:
                return False
        else:
            source_text = (root / package_init_rel).read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=package_init_rel)
    except (OSError, SyntaxError):
        return False
    return parts[-1] in _defined_exports_from_package_init(tree, before_line=before_line)


def _explicit_exports_from_package_init(
    tree: ast.AST,
    root: Path,
    tracked: set[str],
    package_module: str,
    exported_name: str,
    *,
    include_worktree: bool = True,
    before_line: int | None = None,
) -> set[str]:
    exports: set[str] = set()
    mapping_exports: dict[str, set[str]] = {}
    mapping_targets: dict[str, dict[str, str]] = {}
    mapping_none_values: dict[str, set[str]] = {}
    dynamic_export_names: set[str] = set()
    dynamic_import_names: set[str] = {"__import__"}
    module_getattr: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    local_roots = _local_import_roots(root, tracked, include_worktree=include_worktree)
    for node in getattr(tree, "body", []):
        if before_line is not None and getattr(node, "lineno", 0) >= before_line:
            break
        if isinstance(node, ast.Assign):
            for target in node.targets:
                exports.update(_assigned_names(target))
                _discard_shadowed_dynamic_import_names(dynamic_import_names, _assigned_names(target))
                if isinstance(target, ast.Name):
                    mapping_exports[target.id] = _literal_export_names_from_value(node.value)
                    mapping_targets[target.id] = _literal_string_mapping(node.value)
                    mapping_none_values[target.id] = _literal_none_mapping_keys(node.value)
            dynamic_export_names.update(_all_exports(node, mapping_exports))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            exports.update(_assigned_names(node.target))
            _discard_shadowed_dynamic_import_names(dynamic_import_names, _assigned_names(node.target))
            if isinstance(node.target, ast.Name):
                mapping_exports[node.target.id] = _literal_export_names_from_value(node.value)
                mapping_targets[node.target.id] = _literal_string_mapping(node.value)
                mapping_none_values[node.target.id] = _literal_none_mapping_keys(node.value)
                if node.target.id == "__all__":
                    dynamic_export_names.update(_all_exports_from_value(node.value, mapping_exports))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            exports.add(node.name)
            _discard_shadowed_dynamic_import_names(dynamic_import_names, {node.name})
            if node.name == "__getattr__":
                module_getattr = node
                dynamic_export_names.update(_module_getattr_literal_exports(node))
        elif isinstance(node, ast.ClassDef):
            exports.add(node.name)
            _discard_shadowed_dynamic_import_names(dynamic_import_names, {node.name})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                exports.add(alias.asname or alias.name.split(".", 1)[0])
                if alias.name == "importlib":
                    dynamic_import_names.add(_dynamic_import_module_alias(alias.asname or alias.name))
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_import_from(node.module or "", node.level, package_module)
            if not base:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if base == "importlib" and alias.name == "import_module":
                    dynamic_import_names.add(alias.asname or alias.name)
                if base == package_module:
                    sibling_module = f"{package_module}.{alias.name}"
                    if (
                        _resolve_module_path(root, tracked, sibling_module, include_worktree=include_worktree) is not None
                        or _resolve_namespace_package_dir(root, tracked, sibling_module, include_worktree=include_worktree)
                        is not None
                    ):
                        exports.add(alias.asname or alias.name)
                elif _resolve_module_path(root, tracked, base, include_worktree=include_worktree) is not None:
                    exports.add(alias.asname or alias.name)
                elif _resolve_namespace_package_dir(root, tracked, base, include_worktree=include_worktree) is not None:
                    child_module = f"{base}.{alias.name}"
                    if (
                        _resolve_module_path(root, tracked, child_module, include_worktree=include_worktree) is not None
                        or _resolve_namespace_package_dir(root, tracked, child_module, include_worktree=include_worktree)
                        is not None
                    ):
                        exports.add(alias.asname or alias.name)
                elif base.split(".", 1)[0] not in local_roots:
                    exports.add(alias.asname or alias.name)
    if module_getattr is not None:
        dynamic_export_names.add(exported_name)
        exports.update(
            name
            for name in dynamic_export_names
            if _module_getattr_supports_name(
                module_getattr,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                dynamic_import_names,
                exports,
                package_module,
                root,
                tracked,
                include_worktree=include_worktree,
            )
        )
    return exports


def _defined_exports_from_package_init(tree: ast.AST, *, before_line: int | None = None) -> set[str]:
    exports: set[str] = set()
    for node in getattr(tree, "body", []):
        if before_line is not None and getattr(node, "lineno", 0) >= before_line:
            break
        if isinstance(node, ast.Assign):
            for target in node.targets:
                exports.update(_assigned_names(target))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            exports.update(_assigned_names(node.target))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            exports.add(node.name)
    return exports


def _module_getattr_literal_exports(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    exports: set[str] = set()
    param_name = _getattr_parameter_name(node)
    for child in node.body:
        if not isinstance(child, ast.If) or not _branch_returns_value(child.body):
            continue
        exports.update(_literal_name_comparisons(child.test, param_name))
    return exports


def _function_argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {arg.arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]}
    if node.args.vararg is not None:
        names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.add(node.args.kwarg.arg)
    return names


class _FunctionLocalBindingVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.dynamic_import_alias_names: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self.names.add(local_name)
            if alias.name == "importlib":
                self.dynamic_import_alias_names.add(local_name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.names.add(local_name)
            if node.level == 0 and node.module == "importlib" and alias.name == "import_module":
                self.dynamic_import_alias_names.add(local_name)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self.names.update(_assigned_names(target))
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.names.update(_assigned_names(node.target))
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.names.update(_assigned_names(node.target))
        self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self.names.update(_assigned_names(node.target))
        self.visit(node.iter)
        for child in [*node.body, *node.orelse]:
            self.visit(child)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.names.update(_assigned_names(node.target))
        self.visit(node.iter)
        for child in [*node.body, *node.orelse]:
            self.visit(child)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.names.update(_assigned_names(item.optional_vars))
        for child in node.body:
            self.visit(child)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.names.update(_assigned_names(item.optional_vars))
        for child in node.body:
            self.visit(child)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.names.add(node.name)
        for child in node.body:
            self.visit(child)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.names.update(_assigned_names(node.target))
        self.visit(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.names.update(_assigned_names(target))


def _function_local_binding_state(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[set[str], set[str], set[str]]:
    visitor = _FunctionLocalBindingVisitor()
    for statement in node.body:
        visitor.visit(statement)
    argument_names = _function_argument_names(node)
    return visitor.names | argument_names, visitor.dynamic_import_alias_names, argument_names


def _initial_importlib_bound_names(
    module_bound_names: set[str],
    function_local_names: set[str],
    initially_bound_names: set[str],
) -> set[str]:
    names: set[str] = set()
    if "importlib" in module_bound_names and "importlib" not in function_local_names:
        names.add("importlib")
    if "importlib" in initially_bound_names:
        names.add("importlib")
    return names


def _dynamic_import_local_names(dynamic_import_names: set[str]) -> set[str]:
    names: set[str] = set()
    for name in dynamic_import_names:
        if name.startswith("__module__:"):
            names.add(name.removeprefix("__module__:"))
        else:
            names.add(name)
    return names


def _discard_shadowed_dynamic_import_names(dynamic_import_names: set[str], bound_names: set[str]) -> None:
    for name in bound_names:
        dynamic_import_names.discard(name)
        dynamic_import_names.discard(_dynamic_import_module_alias(name))


def _apply_dynamic_import_binding_effects(dynamic_import_names: set[str], statement: ast.stmt) -> None:
    if isinstance(statement, ast.ImportFrom):
        bound_names: set[str] = set()
        if statement.level == 0 and statement.module == "importlib":
            for alias in statement.names:
                if alias.name == "import_module":
                    dynamic_import_names.add(alias.asname or alias.name)
                elif alias.name != "*":
                    bound_names.add(alias.asname or alias.name)
        else:
            bound_names.update(alias.asname or alias.name for alias in statement.names if alias.name != "*")
        _discard_shadowed_dynamic_import_names(dynamic_import_names, bound_names)
        return
    if isinstance(statement, ast.Import):
        import_bound_names: set[str] = set()
        for alias in statement.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            if alias.name == "importlib":
                dynamic_import_names.add(_dynamic_import_module_alias(local_name))
            else:
                import_bound_names.add(local_name)
        _discard_shadowed_dynamic_import_names(dynamic_import_names, import_bound_names)
        return
    _discard_shadowed_dynamic_import_names(dynamic_import_names, _statement_bound_names(statement))


def _statement_bound_names(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Assign):
        names: set[str] = set()
        for target in statement.targets:
            names.update(_assigned_names(target))
        return names
    if isinstance(statement, ast.AnnAssign):
        return _assigned_names(statement.target)
    if isinstance(statement, ast.AugAssign):
        return _assigned_names(statement.target)
    if isinstance(statement, ast.Delete):
        delete_names: set[str] = set()
        for target in statement.targets:
            delete_names.update(_assigned_names(target))
        return delete_names
    if isinstance(statement, ast.For | ast.AsyncFor):
        return _assigned_names(statement.target)
    if isinstance(statement, ast.With | ast.AsyncWith):
        with_names: set[str] = set()
        for item in statement.items:
            if item.optional_vars is not None:
                with_names.update(_assigned_names(item.optional_vars))
        return with_names
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {statement.name}
    return set()


def _statement_direct_bound_names(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0] for alias in statement.names}
    if isinstance(statement, ast.ImportFrom):
        return {alias.asname or alias.name for alias in statement.names if alias.name != "*"}
    return _statement_bound_names(statement)


def _mark_bound_dynamic_import_names(unbound_dynamic_import_names: set[str], statement: ast.stmt) -> None:
    unbound_dynamic_import_names.difference_update(_statement_direct_bound_names(statement))


def _apply_importlib_binding_effects(importlib_bound_names: set[str], statement: ast.stmt) -> None:
    if isinstance(statement, ast.Delete):
        for target in statement.targets:
            if "importlib" in _assigned_names(target):
                importlib_bound_names.discard("importlib")
        return
    if "importlib" in _statement_bound_names(statement):
        importlib_bound_names.add("importlib")


def _module_getattr_supports_name(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    dynamic_import_names: set[str],
    module_bound_names: set[str],
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    include_worktree: bool = True,
) -> bool:
    param_name = _getattr_parameter_name(node)
    function_local_names, local_dynamic_alias_names, initially_bound_names = _function_local_binding_state(node)
    current_dynamic_import_names = set(dynamic_import_names)
    _discard_shadowed_dynamic_import_names(current_dynamic_import_names, function_local_names)
    importlib_bound_names = _initial_importlib_bound_names(
        set(module_bound_names),
        function_local_names,
        initially_bound_names,
    )
    unbound_dynamic_import_names = (
        function_local_names
        & (_dynamic_import_local_names(dynamic_import_names) | local_dynamic_alias_names)
        - initially_bound_names
    )
    dynamic_import_mode = _getattr_dynamic_import_mode(node, param_name, current_dynamic_import_names)
    requires_mapped_target = dynamic_import_mode != "none"
    none_for_name: set[str] = set()
    non_none_for_name: set[str] = set()
    targets_for_name: dict[str, str] = {}
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]] = {}
    for statement in node.body:
        none_for_name.update(_assigned_none_for_name(statement, name, mapping_exports, mapping_none_values, param_name))
        non_none_for_name.update(
            _assigned_non_none_for_name(statement, name, mapping_exports, mapping_none_values, param_name)
        )
        targets_for_name.update(
            _assigned_targets_for_name(statement, name, mapping_targets, mapping_none_values, param_name)
        )
        dynamic_import_targets_for_name.update(
            _assigned_dynamic_import_targets_for_name(
                statement,
                name,
                targets_for_name,
                mapping_targets,
                mapping_none_values,
                param_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
            )
        )
        if (
            isinstance(statement, ast.If)
            and _rejecting_guard_matches_name(statement.test, name, mapping_exports, param_name)
            and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name)
        ):
            return False
        if (
            isinstance(statement, ast.If)
            and _guard_can_pass_name(statement.test, name, mapping_exports, param_name)
            and _branch_explicitly_rejects_name(statement.orelse, name, mapping_exports, param_name)
        ):
            return False
        if (
            isinstance(statement, ast.If)
            and _guard_can_pass_name(statement.test, name, mapping_exports, param_name)
            and _branch_return_supports_name(
                statement.orelse,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        ):
            return True
        if (
            isinstance(statement, ast.If)
            and _none_sentinel_guard_matches_name(statement.test, none_for_name)
            and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name)
        ):
            return False
        if (
            isinstance(statement, ast.If)
            and _none_sentinel_guard_can_pass_name(statement.test, non_none_for_name)
            and _branch_explicitly_rejects_name(statement.orelse, name, mapping_exports, param_name)
        ):
            return False
        if (
            isinstance(statement, ast.If)
            and _none_sentinel_guard_can_pass_name(statement.test, non_none_for_name)
            and _branch_return_supports_name(
                statement.orelse,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        ):
            return True
        if (
            isinstance(statement, ast.If)
            and _non_none_sentinel_guard_matches_name(statement.test, non_none_for_name)
            and _branch_return_supports_name(
                statement.body,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        ):
            return True
        if (
            isinstance(statement, ast.If)
            and _condition_matches_name(
                statement.test,
                name,
                mapping_exports,
                param_name,
                none_for_name,
                non_none_for_name,
            )
            and _branch_return_supports_name(
                statement.body,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        ):
            return True
        if isinstance(statement, ast.If) and _guard_matches_name(
            statement.test,
            name,
            mapping_exports,
            param_name,
        ):
            if _branch_return_supports_name(
                statement.body,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            ):
                return True
        if isinstance(statement, ast.If):
            (
                updated_targets,
                updated_dynamic_imports,
                updated_dynamic_import_names,
                updated_unbound_dynamic_import_names,
                updated_importlib_bound_names,
                updated_none_for_name,
                updated_non_none_for_name,
                falls_through,
            ) = _active_branch_fallthrough_state(
                statement,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                include_worktree=include_worktree,
            )
            if falls_through:
                targets_for_name = updated_targets
                dynamic_import_targets_for_name = updated_dynamic_imports
                current_dynamic_import_names = updated_dynamic_import_names
                unbound_dynamic_import_names = updated_unbound_dynamic_import_names
                importlib_bound_names = updated_importlib_bound_names
                none_for_name = updated_none_for_name
                non_none_for_name = updated_non_none_for_name
        elif _compound_falls_through(statement):
            (
                updated_targets,
                updated_dynamic_imports,
                updated_dynamic_import_names,
                updated_unbound_dynamic_import_names,
                updated_importlib_bound_names,
                updated_none_for_name,
                updated_non_none_for_name,
                falls_through,
            ) = _compound_fallthrough_state(
                statement,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                none_for_name,
                non_none_for_name,
                include_worktree=include_worktree,
            )
            if falls_through:
                targets_for_name = updated_targets
                dynamic_import_targets_for_name = updated_dynamic_imports
                current_dynamic_import_names = updated_dynamic_import_names
                unbound_dynamic_import_names = updated_unbound_dynamic_import_names
                importlib_bound_names = updated_importlib_bound_names
                none_for_name = updated_none_for_name
                non_none_for_name = updated_non_none_for_name
        if isinstance(statement, ast.Return) and statement.value is not None:
            return _return_supports_name(
                statement.value,
                name,
                mapping_targets,
                package_module,
                root,
                tracked,
                param_name,
                targets_for_name,
                dynamic_import_targets_for_name,
                current_dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        if isinstance(statement, ast.Raise):
            return False
        _apply_dynamic_import_binding_effects(current_dynamic_import_names, statement)
        _mark_bound_dynamic_import_names(unbound_dynamic_import_names, statement)
        _apply_importlib_binding_effects(importlib_bound_names, statement)
    return False


def _literal_name_comparisons(node: ast.AST, param_name: str) -> set[str]:
    exports: set[str] = set()
    if not isinstance(node, ast.Compare):
        return exports
    if _is_getattr_parameter(node.left, param_name):
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                exports.add(comparator.value)
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(op, ast.Eq) and _is_getattr_parameter(comparator, param_name):
            left = node.left
            if isinstance(left, ast.Constant) and isinstance(left.value, str):
                exports.add(left.value)
    return exports


def _guard_matches_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    return _rejecting_guard_matches_name(node, name, mapping_exports, param_name)


def _membership_test_supports_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    if not isinstance(node, ast.Compare) or not _is_getattr_parameter(node.left, param_name):
        return False
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if not isinstance(op, ast.In):
            continue
        if isinstance(comparator, ast.Name) and name in mapping_exports.get(comparator.id, set()):
            return True
        if name in _literal_export_names_from_value(comparator):
            return True
    return False


def _assigned_none_for_name(
    statement: ast.stmt,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> set[str]:
    assignment = _simple_assignment(statement)
    if assignment is None:
        return set()
    targets, value = assignment
    if not _mapping_get_missing_for_name(value, name, mapping_exports, mapping_none_values, param_name):
        return set()
    names: set[str] = set()
    for target in targets:
        names.update(_assigned_names(target))
    return names


def _assigned_non_none_for_name(
    statement: ast.stmt,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> set[str]:
    assignment = _simple_assignment(statement)
    if assignment is None:
        return set()
    targets, value = assignment
    if not _mapping_get_non_none_for_name(value, name, mapping_exports, mapping_none_values, param_name):
        return set()
    names: set[str] = set()
    for target in targets:
        names.update(_assigned_names(target))
    return names


def _assigned_targets_for_name(
    statement: ast.stmt,
    name: str,
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> dict[str, str]:
    assignment = _simple_assignment(statement)
    if assignment is None:
        return {}
    targets, value = assignment
    target_value = _mapping_get_target_for_name(value, name, mapping_targets, mapping_none_values, param_name)
    if target_value is None:
        return {}
    target_name = _first_assigned_name(targets)
    return {target_name: target_value} if target_name is not None else {}


def _simple_assignment(statement: ast.stmt) -> tuple[list[ast.expr], ast.AST] | None:
    if isinstance(statement, ast.Assign):
        return statement.targets, statement.value
    if isinstance(statement, ast.AnnAssign) and statement.value is not None:
        return [statement.target], statement.value
    return None


def _first_assigned_name(targets: list[ast.expr]) -> str | None:
    for target in targets:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Tuple | ast.List):
            for element in target.elts:
                if isinstance(element, ast.Name):
                    return element.id
    return None


def _mapping_get_target_for_name(
    node: ast.AST,
    name: str,
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> str | None:
    subscript_target = _mapping_subscript_target_for_name(node, name, mapping_targets, mapping_none_values, param_name)
    if subscript_target is not None:
        return subscript_target
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "get" or not isinstance(node.func.value, ast.Name):
        return None
    if len(node.args) not in {1, 2} or node.keywords:
        return None
    if not _is_getattr_parameter(node.args[0], param_name):
        return None
    mapping_name = node.func.value.id
    if name in mapping_none_values.get(mapping_name, set()):
        return None
    target = mapping_targets.get(mapping_name, {}).get(name)
    if target is not None:
        return target
    if len(node.args) == 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        return node.args[1].value
    return None


def _mapping_subscript_target_for_name(
    node: ast.AST,
    name: str,
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> str | None:
    if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
        return None
    if name in mapping_none_values.get(node.value.id, set()):
        return None
    if not _is_getattr_parameter(_subscript_slice(node), param_name):
        return None
    return mapping_targets.get(node.value.id, {}).get(name)


def _subscript_slice(node: ast.Subscript) -> ast.AST:
    return node.slice


def _assigned_dynamic_import_targets_for_name(
    statement: ast.stmt,
    name: str,
    targets_for_name: dict[str, str],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
) -> dict[str, tuple[str | None, str]]:
    assignment = _simple_assignment(statement)
    if assignment is not None:
        targets, value = assignment
        target_name = _first_assigned_name(targets)
    elif isinstance(statement, ast.Expr):
        target_name = f"<dynamic-import:{getattr(statement, 'lineno', 0)}:{getattr(statement, 'col_offset', 0)}>"
        value = statement.value
    else:
        return _compound_dynamic_import_targets_for_name(
            statement,
            name,
            targets_for_name,
            mapping_targets,
            mapping_none_values,
            param_name,
            dynamic_import_names,
            unbound_dynamic_import_names,
            importlib_bound_names,
        )
    if target_name is None:
        return {}
    if _uses_unbound_dynamic_import_name(value, unbound_dynamic_import_names) or _uses_unresolved_dynamic_import_name(
        value,
        dynamic_import_names,
        importlib_bound_names,
    ):
        return {target_name: (None, "unknown")}
    target, mode = _dynamic_import_return_target(value, name, targets_for_name, param_name, dynamic_import_names)
    if target is _NO_DYNAMIC_IMPORT:
        return {}
    if target is None:
        return {target_name: (None, mode)}
    assert isinstance(target, str)
    return {target_name: (target, mode)}


def _compound_dynamic_import_targets_for_name(
    statement: ast.stmt,
    name: str,
    targets_for_name: dict[str, str],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
) -> dict[str, tuple[str | None, str]]:
    dynamic_import_targets: dict[str, tuple[str | None, str]] = {}
    for body in _compound_statement_bodies(statement):
        dynamic_import_targets.update(
            _dynamic_import_targets_for_body(
                body,
                name,
                targets_for_name,
                mapping_targets,
                mapping_none_values,
                param_name,
                dynamic_import_names,
                unbound_dynamic_import_names,
                importlib_bound_names,
            )
        )
    return dynamic_import_targets


def _dynamic_import_targets_for_body(
    body: list[ast.stmt],
    name: str,
    targets_for_name: dict[str, str],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
) -> dict[str, tuple[str | None, str]]:
    body_targets = dict(targets_for_name)
    body_dynamic_import_names = set(dynamic_import_names)
    body_unbound_dynamic_import_names = set(unbound_dynamic_import_names)
    body_importlib_bound_names = set(importlib_bound_names)
    dynamic_import_targets: dict[str, tuple[str | None, str]] = {}
    for child in body:
        body_targets.update(_assigned_targets_for_name(child, name, mapping_targets, mapping_none_values, param_name))
        dynamic_import_targets.update(
            _assigned_dynamic_import_targets_for_name(
                child,
                name,
                body_targets,
                mapping_targets,
                mapping_none_values,
                param_name,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
            )
        )
        _apply_dynamic_import_binding_effects(body_dynamic_import_names, child)
        _mark_bound_dynamic_import_names(body_unbound_dynamic_import_names, child)
        _apply_importlib_binding_effects(body_importlib_bound_names, child)
    return dynamic_import_targets


def _compound_statement_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.For | ast.AsyncFor | ast.While):
        return [statement.body, statement.orelse]
    if isinstance(statement, ast.With | ast.AsyncWith):
        return [statement.body]
    if isinstance(statement, ast.Try):
        return [
            statement.body,
            *(handler.body for handler in statement.handlers),
            statement.orelse,
            statement.finalbody,
        ]
    return []


def _mapping_get_missing_for_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "get" or not isinstance(node.func.value, ast.Name):
        return False
    if len(node.args) not in {1, 2} or node.keywords:
        return False
    if not _is_getattr_parameter(node.args[0], param_name):
        return False
    mapping_name = node.func.value.id
    if name in mapping_none_values.get(mapping_name, set()):
        return True
    if len(node.args) == 2 and not _is_none_literal(node.args[1]):
        return False
    return name not in mapping_exports.get(mapping_name, set())


def _mapping_get_non_none_for_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_none_values: dict[str, set[str]],
    param_name: str,
) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "get" or not isinstance(node.func.value, ast.Name):
        return False
    if len(node.args) not in {1, 2} or node.keywords:
        return False
    if not _is_getattr_parameter(node.args[0], param_name):
        return False
    mapping_name = node.func.value.id
    if name in mapping_none_values.get(mapping_name, set()):
        return False
    if name in mapping_exports.get(mapping_name, set()):
        return True
    return len(node.args) == 2 and not _is_none_literal(node.args[1])


def _none_sentinel_guard_matches_name(node: ast.AST, none_for_name: set[str]) -> bool:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_none_sentinel_guard_matches_name(value, none_for_name) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if isinstance(node.left, ast.Name) and node.left.id in none_for_name:
        return any(_is_none_check(op, comparator) for op, comparator in zip(node.ops, node.comparators, strict=False))
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(comparator, ast.Name) and comparator.id in none_for_name and _is_none_check(op, node.left):
            return True
    return False


def _none_sentinel_guard_can_pass_name(node: ast.AST, non_none_for_name: set[str]) -> bool:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return all(_none_sentinel_guard_can_pass_name(value, non_none_for_name) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if isinstance(node.left, ast.Name) and node.left.id in non_none_for_name:
        return any(_is_none_check(op, comparator) for op, comparator in zip(node.ops, node.comparators, strict=False))
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(comparator, ast.Name) and comparator.id in non_none_for_name and _is_none_check(op, node.left):
                return True
    return False


def _non_none_sentinel_guard_matches_name(node: ast.AST, non_none_for_name: set[str]) -> bool:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return any(_non_none_sentinel_guard_matches_name(value, non_none_for_name) for value in node.values)
        if isinstance(node.op, ast.And):
            return all(_non_none_sentinel_guard_matches_name(value, non_none_for_name) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if isinstance(node.left, ast.Name) and node.left.id in non_none_for_name:
        return any(_is_not_none_check(op, comparator) for op, comparator in zip(node.ops, node.comparators, strict=False))
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(comparator, ast.Name) and comparator.id in non_none_for_name and _is_not_none_check(op, node.left):
            return True
    return False


def _non_none_sentinel_guard_can_pass_name(node: ast.AST, none_for_name: set[str]) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    if isinstance(node.left, ast.Name) and node.left.id in none_for_name:
        return any(_is_not_none_check(op, comparator) for op, comparator in zip(node.ops, node.comparators, strict=False))
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(comparator, ast.Name) and comparator.id in none_for_name and _is_not_none_check(op, node.left):
            return True
    return False


def _is_none_check(op: ast.cmpop, node: ast.AST) -> bool:
    return isinstance(op, ast.Is | ast.Eq) and _is_none_literal(node)


def _is_not_none_check(op: ast.cmpop, node: ast.AST) -> bool:
    return isinstance(op, ast.IsNot | ast.NotEq) and _is_none_literal(node)


def _is_none_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _rejecting_guard_matches_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return any(_rejecting_guard_matches_name(value, name, mapping_exports, param_name) for value in node.values)
        if isinstance(node.op, ast.And):
            return all(_rejecting_guard_matches_name(value, name, mapping_exports, param_name) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if _is_getattr_parameter(node.left, param_name):
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and comparator.value == name:
                return True
            if isinstance(op, ast.In) and _collection_contains_name(comparator, name, mapping_exports):
                return True
            if isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant) and comparator.value != name:
                return True
            if isinstance(op, ast.NotIn) and not _collection_contains_name(comparator, name, mapping_exports):
                return True
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(op, ast.Eq) and _is_getattr_parameter(comparator, param_name):
            left = node.left
            if isinstance(left, ast.Constant) and left.value == name:
                return True
        if isinstance(op, ast.NotEq) and _is_getattr_parameter(comparator, param_name):
            left = node.left
            if isinstance(left, ast.Constant) and left.value != name:
                return True
    return False


def _guard_can_pass_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return all(_guard_can_pass_name(value, name, mapping_exports, param_name) for value in node.values)
        if isinstance(node.op, ast.And):
            return any(_guard_can_pass_name(value, name, mapping_exports, param_name) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if _is_getattr_parameter(node.left, param_name):
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                return comparator.value != name
            if isinstance(op, ast.In):
                return not _collection_contains_name(comparator, name, mapping_exports)
            if isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant):
                return comparator.value == name
            if isinstance(op, ast.NotIn):
                return _collection_contains_name(comparator, name, mapping_exports)
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if isinstance(op, ast.Eq) and _is_getattr_parameter(comparator, param_name):
            left = node.left
            if isinstance(left, ast.Constant):
                return left.value != name
        if isinstance(op, ast.NotEq) and _is_getattr_parameter(comparator, param_name):
            left = node.left
            if isinstance(left, ast.Constant):
                return left.value == name
    return False


def _collection_contains_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
) -> bool:
    if isinstance(node, ast.Name):
        return name in mapping_exports.get(node.id, set())
    return name in _literal_export_names_from_value(node)


def _branch_returns_value(body: list[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, ast.Return):
            return statement.value is not None
        if isinstance(statement, ast.Raise):
            return False
    return False


def _branch_return_supports_name(
    body: list[ast.stmt],
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    inherited_none_for_name: set[str] | None = None,
    inherited_non_none_for_name: set[str] | None = None,
    *,
    requires_mapped_target: bool,
    dynamic_import_mode: str,
    include_worktree: bool = True,
) -> bool:
    branch_dynamic_import_targets = dict(dynamic_import_targets_for_name)
    branch_targets_for_name = dict(targets_for_name)
    branch_dynamic_import_names = set(dynamic_import_names)
    branch_unbound_dynamic_import_names = set(unbound_dynamic_import_names)
    branch_importlib_bound_names = set(importlib_bound_names)
    branch_none_for_name: set[str] = set(inherited_none_for_name or set())
    branch_non_none_for_name: set[str] = set(inherited_non_none_for_name or set())
    for statement in body:
        branch_none_for_name.update(_assigned_none_for_name(statement, name, mapping_exports, mapping_none_values, param_name))
        branch_non_none_for_name.update(
            _assigned_non_none_for_name(statement, name, mapping_exports, mapping_none_values, param_name)
        )
        branch_targets_for_name.update(
            _assigned_targets_for_name(statement, name, mapping_targets, mapping_none_values, param_name)
        )
        branch_dynamic_import_targets.update(
            _assigned_dynamic_import_targets_for_name(
                statement,
                name,
                branch_targets_for_name,
                mapping_targets,
                mapping_none_values,
                param_name,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
            )
        )
        if (
            isinstance(statement, ast.If)
            and _rejecting_guard_matches_name(statement.test, name, mapping_exports, param_name)
            and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name)
        ):
            return False
        if isinstance(statement, ast.If) and _guard_can_pass_name(statement.test, name, mapping_exports, param_name):
            if _branch_explicitly_rejects_name(statement.orelse, name, mapping_exports, param_name):
                return False
            if _branch_return_supports_name(
                statement.orelse,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                branch_none_for_name,
                branch_non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            ):
                return True
        if (
            isinstance(statement, ast.If)
            and _condition_matches_name(
                statement.test,
                name,
                mapping_exports,
                param_name,
                branch_none_for_name,
                branch_non_none_for_name,
            )
            and _branch_return_supports_name(
                statement.body,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                branch_none_for_name,
                branch_non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        ):
            return True
        if isinstance(statement, ast.If) and _guard_matches_name(statement.test, name, mapping_exports, param_name):
            if _branch_return_supports_name(
                statement.body,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                branch_none_for_name,
                branch_non_none_for_name,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            ):
                return True
        if _compound_return_supports_name(
            statement,
            name,
            mapping_exports,
            mapping_targets,
            mapping_none_values,
            package_module,
            root,
            tracked,
            param_name,
            branch_targets_for_name,
            branch_dynamic_import_targets,
            branch_dynamic_import_names,
            branch_unbound_dynamic_import_names,
            branch_importlib_bound_names,
            branch_none_for_name,
            branch_non_none_for_name,
            requires_mapped_target=requires_mapped_target,
            dynamic_import_mode=dynamic_import_mode,
            include_worktree=include_worktree,
        ):
            return True
        if isinstance(statement, ast.If):
            (
                updated_targets,
                updated_dynamic_imports,
                updated_dynamic_import_names,
                updated_unbound_dynamic_import_names,
                updated_importlib_bound_names,
                updated_none_for_name,
                updated_non_none_for_name,
                falls_through,
            ) = _active_branch_fallthrough_state(
                statement,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                branch_none_for_name,
                branch_non_none_for_name,
                include_worktree=include_worktree,
            )
            if falls_through:
                branch_targets_for_name = updated_targets
                branch_dynamic_import_targets = updated_dynamic_imports
                branch_dynamic_import_names = updated_dynamic_import_names
                branch_unbound_dynamic_import_names = updated_unbound_dynamic_import_names
                branch_importlib_bound_names = updated_importlib_bound_names
                branch_none_for_name = updated_none_for_name
                branch_non_none_for_name = updated_non_none_for_name
        elif _compound_falls_through(statement):
            (
                updated_targets,
                updated_dynamic_imports,
                updated_dynamic_import_names,
                updated_unbound_dynamic_import_names,
                updated_importlib_bound_names,
                updated_none_for_name,
                updated_non_none_for_name,
                falls_through,
            ) = _compound_fallthrough_state(
                statement,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                branch_none_for_name,
                branch_non_none_for_name,
                include_worktree=include_worktree,
            )
            if falls_through:
                branch_targets_for_name = updated_targets
                branch_dynamic_import_targets = updated_dynamic_imports
                branch_dynamic_import_names = updated_dynamic_import_names
                branch_unbound_dynamic_import_names = updated_unbound_dynamic_import_names
                branch_importlib_bound_names = updated_importlib_bound_names
                branch_none_for_name = updated_none_for_name
                branch_non_none_for_name = updated_non_none_for_name
        if isinstance(statement, ast.Return):
            if statement.value is None:
                return False
            return _return_supports_name(
                statement.value,
                name,
                mapping_targets,
                package_module,
                root,
                tracked,
                param_name,
                branch_targets_for_name,
                branch_dynamic_import_targets,
                branch_dynamic_import_names,
                branch_unbound_dynamic_import_names,
                branch_importlib_bound_names,
                requires_mapped_target=requires_mapped_target,
                dynamic_import_mode=dynamic_import_mode,
                include_worktree=include_worktree,
            )
        if isinstance(statement, ast.Raise):
            return False
        _apply_dynamic_import_binding_effects(branch_dynamic_import_names, statement)
        _mark_bound_dynamic_import_names(branch_unbound_dynamic_import_names, statement)
        _apply_importlib_binding_effects(branch_importlib_bound_names, statement)
    return False


def _active_branch_fallthrough_state(
    statement: ast.If,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    none_for_name: set[str],
    non_none_for_name: set[str],
    *,
    include_worktree: bool = True,
) -> tuple[dict[str, str], dict[str, tuple[str | None, str]], set[str], set[str], set[str], set[str], set[str], bool]:
    active_body = _active_branch_body_for_name(
        statement,
        name,
        mapping_exports,
        param_name,
        none_for_name,
        non_none_for_name,
    )
    if active_body is None:
        return (
            targets_for_name,
            dynamic_import_targets_for_name,
            dynamic_import_names,
            unbound_dynamic_import_names,
            importlib_bound_names,
            none_for_name,
            non_none_for_name,
            False,
        )
    return _fallthrough_state_for_body(
        active_body,
        name,
        mapping_exports,
        mapping_targets,
        mapping_none_values,
        package_module,
        root,
        tracked,
        param_name,
        targets_for_name,
        dynamic_import_targets_for_name,
        dynamic_import_names,
        unbound_dynamic_import_names,
        importlib_bound_names,
        none_for_name,
        non_none_for_name,
        include_worktree=include_worktree,
    )


def _compound_return_supports_name(
    statement: ast.stmt,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    none_for_name: set[str],
    non_none_for_name: set[str],
    *,
    requires_mapped_target: bool,
    dynamic_import_mode: str,
    include_worktree: bool = True,
) -> bool:
    body_groups = _compound_return_bodies(statement)
    if not body_groups:
        return False

    def body_supports_name(body: list[ast.stmt]) -> bool:
        body_dynamic_import_names = set(dynamic_import_names)
        body_unbound_dynamic_import_names = set(unbound_dynamic_import_names)
        body_importlib_bound_names = set(importlib_bound_names)
        _apply_dynamic_import_binding_effects(body_dynamic_import_names, statement)
        _mark_bound_dynamic_import_names(body_unbound_dynamic_import_names, statement)
        _apply_importlib_binding_effects(body_importlib_bound_names, statement)
        return _branch_return_supports_name(
            body,
            name,
            mapping_exports,
            mapping_targets,
            mapping_none_values,
            package_module,
            root,
            tracked,
            param_name,
            targets_for_name,
            dynamic_import_targets_for_name,
            body_dynamic_import_names,
            body_unbound_dynamic_import_names,
            body_importlib_bound_names,
            none_for_name,
            non_none_for_name,
            requires_mapped_target=requires_mapped_target,
            dynamic_import_mode=dynamic_import_mode,
            include_worktree=include_worktree,
        )

    if isinstance(statement, ast.Try) and not _body_has_direct_return_or_raise(statement.finalbody):
        return_bodies = [body for body in body_groups if _body_contains_return_value(body)]
        return bool(return_bodies) and all(body_supports_name(body) for body in return_bodies)
    return any(body_supports_name(body) for body in body_groups)


def _compound_return_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.For | ast.AsyncFor | ast.While):
        return [statement.body]
    if isinstance(statement, ast.With | ast.AsyncWith):
        return [statement.body]
    if isinstance(statement, ast.Try):
        if _body_has_direct_return_or_raise(statement.finalbody):
            return [statement.finalbody]
        return [
            statement.body,
            *(handler.body for handler in statement.handlers),
            statement.orelse,
        ]
    return []


def _compound_falls_through(statement: ast.stmt) -> bool:
    return bool(_compound_fallthrough_bodies(statement))


def _compound_fallthrough_state(
    statement: ast.stmt,
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    none_for_name: set[str],
    non_none_for_name: set[str],
    *,
    include_worktree: bool = True,
) -> tuple[dict[str, str], dict[str, tuple[str | None, str]], set[str], set[str], set[str], set[str], set[str], bool]:
    body_targets = dict(targets_for_name)
    body_dynamic_imports = dict(dynamic_import_targets_for_name)
    body_dynamic_import_names = set(dynamic_import_names)
    body_unbound_dynamic_import_names = set(unbound_dynamic_import_names)
    body_importlib_bound_names = set(importlib_bound_names)
    body_none_for_name = set(none_for_name)
    body_non_none_for_name = set(non_none_for_name)
    _apply_dynamic_import_binding_effects(body_dynamic_import_names, statement)
    _mark_bound_dynamic_import_names(body_unbound_dynamic_import_names, statement)
    _apply_importlib_binding_effects(body_importlib_bound_names, statement)
    for body in _compound_fallthrough_bodies(statement):
        (
            body_targets,
            body_dynamic_imports,
            body_dynamic_import_names,
            body_unbound_dynamic_import_names,
            body_importlib_bound_names,
            body_none_for_name,
            body_non_none_for_name,
            falls_through,
        ) = _fallthrough_state_for_body(
            body,
            name,
            mapping_exports,
            mapping_targets,
            mapping_none_values,
            package_module,
            root,
            tracked,
            param_name,
            body_targets,
            body_dynamic_imports,
            body_dynamic_import_names,
            body_unbound_dynamic_import_names,
            body_importlib_bound_names,
            body_none_for_name,
            body_non_none_for_name,
            include_worktree=include_worktree,
        )
        if not falls_through:
            return (
                body_targets,
                body_dynamic_imports,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
                body_none_for_name,
                body_non_none_for_name,
                False,
            )
    return (
        body_targets,
        body_dynamic_imports,
        body_dynamic_import_names,
        body_unbound_dynamic_import_names,
        body_importlib_bound_names,
        body_none_for_name,
        body_non_none_for_name,
        True,
    )


def _compound_fallthrough_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.With | ast.AsyncWith):
        return [statement.body]
    if isinstance(statement, ast.Try):
        if _body_has_direct_return_or_raise(statement.finalbody):
            return [statement.finalbody]
        return [statement.body, statement.orelse, statement.finalbody]
    if isinstance(statement, ast.For | ast.AsyncFor) and _loop_iter_guaranteed_nonempty(statement.iter):
        return [statement.body, statement.orelse]
    return []


def _loop_iter_guaranteed_nonempty(node: ast.AST) -> bool:
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return bool(node.elts)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(node.value)
    return False


def _body_has_direct_return_or_raise(body: list[ast.stmt]) -> bool:
    return any(isinstance(statement, ast.Return | ast.Raise) for statement in body)


def _body_contains_return_value(body: list[ast.stmt]) -> bool:
    return any(_statement_contains_return_value(statement) for statement in body)


def _statement_contains_return_value(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Return):
        return statement.value is not None
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return False
    return any(
        isinstance(child, ast.stmt) and _statement_contains_return_value(child)
        for child in ast.iter_child_nodes(statement)
    )


def _active_branch_body_for_name(
    statement: ast.If,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
    none_for_name: set[str],
    non_none_for_name: set[str],
) -> list[ast.stmt] | None:
    if isinstance(statement.test, ast.Constant) and isinstance(statement.test.value, bool):
        return statement.body if statement.test.value else statement.orelse
    if _condition_matches_name(
        statement.test,
        name,
        mapping_exports,
        param_name,
        none_for_name,
        non_none_for_name,
    ):
        return statement.body
    if _condition_can_pass_name(
        statement.test,
        name,
        mapping_exports,
        param_name,
        none_for_name,
        non_none_for_name,
    ):
        return statement.orelse
    return None


def _condition_matches_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
    none_for_name: set[str],
    non_none_for_name: set[str],
) -> bool:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return any(
                _condition_matches_name(value, name, mapping_exports, param_name, none_for_name, non_none_for_name)
                for value in node.values
            )
        if isinstance(node.op, ast.And):
            return all(
                _condition_matches_name(value, name, mapping_exports, param_name, none_for_name, non_none_for_name)
                for value in node.values
            )
    return (
        _truthy_sentinel_guard_matches_name(node, non_none_for_name)
        or _non_none_sentinel_guard_matches_name(node, non_none_for_name)
        or _none_sentinel_guard_matches_name(node, none_for_name)
        or _guard_matches_name(node, name, mapping_exports, param_name)
    )


def _condition_can_pass_name(
    node: ast.AST,
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
    none_for_name: set[str],
    non_none_for_name: set[str],
) -> bool:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return all(
                _condition_can_pass_name(value, name, mapping_exports, param_name, none_for_name, non_none_for_name)
                for value in node.values
            )
        if isinstance(node.op, ast.And):
            return any(
                _condition_can_pass_name(value, name, mapping_exports, param_name, none_for_name, non_none_for_name)
                for value in node.values
            )
    return (
        _truthy_sentinel_guard_can_pass_name(node, none_for_name)
        or _none_sentinel_guard_can_pass_name(node, non_none_for_name)
        or _non_none_sentinel_guard_can_pass_name(node, none_for_name)
        or _guard_can_pass_name(node, name, mapping_exports, param_name)
    )


def _truthy_sentinel_guard_matches_name(node: ast.AST, non_none_for_name: set[str]) -> bool:
    return isinstance(node, ast.Name) and node.id in non_none_for_name


def _truthy_sentinel_guard_can_pass_name(node: ast.AST, none_for_name: set[str]) -> bool:
    return isinstance(node, ast.Name) and node.id in none_for_name


def _fallthrough_state_for_body(
    body: list[ast.stmt],
    name: str,
    mapping_exports: dict[str, set[str]],
    mapping_targets: dict[str, dict[str, str]],
    mapping_none_values: dict[str, set[str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    none_for_name: set[str],
    non_none_for_name: set[str],
    *,
    include_worktree: bool = True,
) -> tuple[dict[str, str], dict[str, tuple[str | None, str]], set[str], set[str], set[str], set[str], set[str], bool]:
    body_targets = dict(targets_for_name)
    body_dynamic_imports = dict(dynamic_import_targets_for_name)
    body_dynamic_import_names = set(dynamic_import_names)
    body_unbound_dynamic_import_names = set(unbound_dynamic_import_names)
    body_importlib_bound_names = set(importlib_bound_names)
    body_none_for_name = set(none_for_name)
    body_non_none_for_name = set(non_none_for_name)
    for child in body:
        body_none_for_name.update(_assigned_none_for_name(child, name, mapping_exports, mapping_none_values, param_name))
        body_non_none_for_name.update(
            _assigned_non_none_for_name(child, name, mapping_exports, mapping_none_values, param_name)
        )
        body_targets.update(_assigned_targets_for_name(child, name, mapping_targets, mapping_none_values, param_name))
        body_dynamic_imports.update(
            _assigned_dynamic_import_targets_for_name(
                child,
                name,
                body_targets,
                mapping_targets,
                mapping_none_values,
                param_name,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
            )
        )
        if isinstance(child, ast.If):
            active_body = _active_branch_body_for_name(
                child,
                name,
                mapping_exports,
                param_name,
                body_none_for_name,
                body_non_none_for_name,
            )
            if active_body is None:
                body_targets_from_body, body_imports_from_body, _, _, _, _, _, _ = _fallthrough_state_for_body(
                    child.body,
                    name,
                    mapping_exports,
                    mapping_targets,
                    mapping_none_values,
                    package_module,
                    root,
                    tracked,
                    param_name,
                    body_targets,
                    body_dynamic_imports,
                    body_dynamic_import_names,
                    body_unbound_dynamic_import_names,
                    body_importlib_bound_names,
                    body_none_for_name,
                    body_non_none_for_name,
                    include_worktree=include_worktree,
                )
                body_targets_from_else, body_imports_from_else, _, _, _, _, _, _ = _fallthrough_state_for_body(
                    child.orelse,
                    name,
                    mapping_exports,
                    mapping_targets,
                    mapping_none_values,
                    package_module,
                    root,
                    tracked,
                    param_name,
                    body_targets,
                    body_dynamic_imports,
                    body_dynamic_import_names,
                    body_unbound_dynamic_import_names,
                    body_importlib_bound_names,
                    body_none_for_name,
                    body_non_none_for_name,
                    include_worktree=include_worktree,
                )
                body_targets.update(body_targets_from_body)
                body_targets.update(body_targets_from_else)
                body_dynamic_imports.update(body_imports_from_body)
                body_dynamic_imports.update(body_imports_from_else)
            else:
                (
                    body_targets,
                    body_dynamic_imports,
                    body_dynamic_import_names,
                    body_unbound_dynamic_import_names,
                    body_importlib_bound_names,
                    body_none_for_name,
                    body_non_none_for_name,
                    falls_through,
                ) = _fallthrough_state_for_body(
                    active_body,
                    name,
                    mapping_exports,
                    mapping_targets,
                    mapping_none_values,
                    package_module,
                    root,
                    tracked,
                    param_name,
                    body_targets,
                    body_dynamic_imports,
                    body_dynamic_import_names,
                    body_unbound_dynamic_import_names,
                    body_importlib_bound_names,
                    body_none_for_name,
                    body_non_none_for_name,
                    include_worktree=include_worktree,
                )
                if not falls_through:
                    return (
                        body_targets,
                        body_dynamic_imports,
                        body_dynamic_import_names,
                        body_unbound_dynamic_import_names,
                        body_importlib_bound_names,
                        body_none_for_name,
                        body_non_none_for_name,
                        False,
                    )
        elif _compound_falls_through(child):
            (
                body_targets,
                body_dynamic_imports,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
                body_none_for_name,
                body_non_none_for_name,
                falls_through,
            ) = _compound_fallthrough_state(
                child,
                name,
                mapping_exports,
                mapping_targets,
                mapping_none_values,
                package_module,
                root,
                tracked,
                param_name,
                body_targets,
                body_dynamic_imports,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
                body_none_for_name,
                body_non_none_for_name,
                include_worktree=include_worktree,
            )
            if not falls_through:
                return (
                    body_targets,
                    body_dynamic_imports,
                    body_dynamic_import_names,
                    body_unbound_dynamic_import_names,
                    body_importlib_bound_names,
                    body_none_for_name,
                    body_non_none_for_name,
                    False,
                )
        if isinstance(child, ast.Return | ast.Raise):
            return (
                body_targets,
                body_dynamic_imports,
                body_dynamic_import_names,
                body_unbound_dynamic_import_names,
                body_importlib_bound_names,
                body_none_for_name,
                body_non_none_for_name,
                False,
            )
        _apply_dynamic_import_binding_effects(body_dynamic_import_names, child)
        _mark_bound_dynamic_import_names(body_unbound_dynamic_import_names, child)
        _apply_importlib_binding_effects(body_importlib_bound_names, child)
    return (
        body_targets,
        body_dynamic_imports,
        body_dynamic_import_names,
        body_unbound_dynamic_import_names,
        body_importlib_bound_names,
        body_none_for_name,
        body_non_none_for_name,
        True,
    )


def _branch_explicitly_rejects_name(
    body: list[ast.stmt],
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    for statement in body:
        if isinstance(statement, ast.Raise):
            return True
        if isinstance(statement, ast.Return):
            return False
        if not isinstance(statement, ast.If):
            continue
        if (
            _rejecting_guard_matches_name(statement.test, name, mapping_exports, param_name)
            and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name)
        ):
            return True
        if _guard_matches_name(statement.test, name, mapping_exports, param_name) and _branch_raises_before_return_for_name(
            statement.body,
            name,
            mapping_exports,
            param_name,
        ):
            return True
        if _guard_can_pass_name(statement.test, name, mapping_exports, param_name) and _branch_explicitly_rejects_name(
            statement.orelse,
            name,
            mapping_exports,
            param_name,
        ):
            return True
    return False


def _return_supports_name(
    return_value: ast.AST,
    name: str,
    mapping_targets: dict[str, dict[str, str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    param_name: str,
    targets_for_name: dict[str, str],
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_names: set[str],
    unbound_dynamic_import_names: set[str],
    importlib_bound_names: set[str],
    *,
    requires_mapped_target: bool,
    dynamic_import_mode: str,
    include_worktree: bool = True,
) -> bool:
    if _uses_unbound_dynamic_import_name(return_value, unbound_dynamic_import_names) or _uses_unresolved_dynamic_import_name(
        return_value,
        dynamic_import_names,
        importlib_bound_names,
    ):
        return False
    target, target_mode = _dynamic_import_return_target(
        return_value,
        name,
        targets_for_name,
        param_name,
        dynamic_import_names,
    )
    if not requires_mapped_target and target is _NO_DYNAMIC_IMPORT and not dynamic_import_targets_for_name:
        return True
    if not _dynamic_import_assignments_valid(
        dynamic_import_targets_for_name,
        dynamic_import_mode,
        package_module,
        root,
        tracked,
        include_worktree=include_worktree,
    ):
        return False
    if target is _NO_DYNAMIC_IMPORT:
        if isinstance(return_value, ast.Name) and return_value.id in dynamic_import_targets_for_name:
            assigned_target, assigned_mode = dynamic_import_targets_for_name[return_value.id]
            return _dynamic_import_target_exists(
                assigned_target,
                assigned_mode,
                dynamic_import_mode,
                package_module,
                root,
                tracked,
                include_worktree=include_worktree,
            )
        return True
    if target is None:
        return False
    assert isinstance(target, str)
    return _dynamic_import_target_exists(
        target,
        target_mode,
        dynamic_import_mode,
        package_module,
        root,
        tracked,
        include_worktree=include_worktree,
    )


def _dynamic_import_assignments_valid(
    dynamic_import_targets_for_name: dict[str, tuple[str | None, str]],
    dynamic_import_mode: str,
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    include_worktree: bool = True,
) -> bool:
    return all(
        _dynamic_import_target_exists(
            target,
            target_mode,
            dynamic_import_mode,
            package_module,
            root,
            tracked,
            include_worktree=include_worktree,
        )
        for target, target_mode in dynamic_import_targets_for_name.values()
    )


def _dynamic_import_target_exists(
    target: str | None,
    target_mode: str,
    fallback_mode: str,
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    include_worktree: bool = True,
) -> bool:
    if target is None:
        return False
    return _target_module_exists(
        target,
        package_module,
        root,
        tracked,
        dynamic_import_mode=target_mode if target_mode != "unknown" else fallback_mode,
        include_worktree=include_worktree,
    )


def _uses_unbound_dynamic_import_name(node: ast.AST, unbound_dynamic_import_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in unbound_dynamic_import_names
    if isinstance(node, ast.Lambda | ast.GeneratorExp):
        return False
    return any(_uses_unbound_dynamic_import_name(child, unbound_dynamic_import_names) for child in ast.iter_child_nodes(node))


def _uses_unresolved_dynamic_import_name(
    node: ast.AST,
    dynamic_import_names: set[str],
    importlib_bound_names: set[str],
) -> bool:
    if isinstance(node, ast.Call) and _is_unresolved_importlib_import_module_call(
        node,
        dynamic_import_names,
        importlib_bound_names,
    ):
        return True
    if isinstance(node, ast.Lambda | ast.GeneratorExp):
        return False
    return any(
        _uses_unresolved_dynamic_import_name(child, dynamic_import_names, importlib_bound_names)
        for child in ast.iter_child_nodes(node)
    )


def _is_unresolved_importlib_import_module_call(
    node: ast.Call,
    dynamic_import_names: set[str],
    importlib_bound_names: set[str],
) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and _dynamic_import_module_alias("importlib") not in dynamic_import_names
        and "importlib" not in importlib_bound_names
    )


def _branch_raises_before_return(body: list[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, ast.Raise):
            return True
        if isinstance(statement, ast.Return):
            return False
    return False


def _branch_raises_before_return_for_name(
    body: list[ast.stmt],
    name: str,
    mapping_exports: dict[str, set[str]],
    param_name: str,
) -> bool:
    for statement in body:
        if isinstance(statement, ast.Raise):
            return True
        if isinstance(statement, ast.Return):
            return False
        if not isinstance(statement, ast.If):
            continue
        if (
            _rejecting_guard_matches_name(statement.test, name, mapping_exports, param_name)
            and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name)
        ):
            return True
        if (
            name in _literal_name_comparisons(statement.test, param_name)
            or _membership_test_supports_name(statement.test, name, mapping_exports, param_name)
        ) and _branch_raises_before_return_for_name(statement.body, name, mapping_exports, param_name):
            return True
        if _guard_can_pass_name(statement.test, name, mapping_exports, param_name) and _branch_raises_before_return_for_name(
            statement.orelse,
            name,
            mapping_exports,
            param_name,
        ):
            return True
    return False


def _getattr_parameter_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    if node.args.posonlyargs:
        return node.args.posonlyargs[0].arg
    if node.args.args:
        return node.args.args[0].arg
    return "name"


def _is_getattr_parameter(node: ast.AST, param_name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == param_name


def _assigned_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Tuple | ast.List):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assigned_names(element))
        return names
    return set()


def _literal_export_names_from_value(node: ast.AST | None) -> set[str]:
    if isinstance(node, ast.Dict):
        return {
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return {
            item.value
            for item in node.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    return set()


def _literal_string_mapping(node: ast.AST | None) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    mapping: dict[str, str] = {}
    for key, value in zip(node.keys, node.values, strict=False):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        string_value = _literal_string_mapping_value(value)
        if string_value is not None:
            mapping[key.value] = string_value
    return mapping


def _literal_string_mapping_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Tuple | ast.List) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _getattr_dynamic_import_mode(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    param_name: str,
    dynamic_import_names: set[str],
) -> str:
    modes: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not _is_dynamic_import_call(child, dynamic_import_names):
            continue
        modes.add(_dynamic_import_call_mode(child, param_name))
    if not modes:
        return "none"
    if modes == {"package"}:
        return "package"
    if modes == {"absolute"}:
        return "absolute"
    if len(modes) == 1:
        mode = next(iter(modes))
        if mode.startswith("package:"):
            return mode
    return "unknown"


def _is_dynamic_import_call(node: ast.Call, dynamic_import_names: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id in dynamic_import_names:
        return True
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and _dynamic_import_module_alias(func.value.id) in dynamic_import_names
    )


def _dynamic_import_module_alias(name: str) -> str:
    return f"__module__:{name}"


def _dynamic_import_call_mode(node: ast.Call, param_name: str) -> str:
    if not node.args:
        return "unknown"
    first = node.args[0]
    if _is_package_prefixed_import_arg(first):
        return "package"
    if (len(node.args) >= 2 or _has_package_keyword(node)) and _is_relative_import_arg(first):
        return _package_argument_mode(node)
    if _is_getattr_parameter(first, param_name) or isinstance(first, ast.Name):
        return "absolute"
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return "unknown" if first.value.startswith(".") else "absolute"
    return "unknown"


def _has_package_keyword(node: ast.Call) -> bool:
    return any(keyword.arg == "package" for keyword in node.keywords)


def _package_argument_mode(node: ast.Call) -> str:
    package_arg: ast.AST | None = node.args[1] if len(node.args) >= 2 else None
    for keyword in node.keywords:
        if keyword.arg == "package":
            package_arg = keyword.value
            break
    if package_arg is None:
        return "unknown"
    if _is_dunder_package_node(package_arg) or _is_dunder_name_node(package_arg):
        return "package"
    if isinstance(package_arg, ast.Constant) and isinstance(package_arg.value, str):
        return f"package:{package_arg.value}"
    return "unknown"


def _is_dunder_package_node(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__package__"


def _is_package_prefixed_import_arg(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        values = node.values
        return (
            len(values) >= 2
            and _is_dunder_name_formatted(values[0])
            and isinstance(values[1], ast.Constant)
            and isinstance(values[1].value, str)
            and values[1].value.startswith(".")
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts = _flatten_string_plus(node)
        return (
            len(parts) >= 2
            and _is_dunder_name_node(parts[0])
            and isinstance(parts[1], ast.Constant)
            and isinstance(parts[1].value, str)
            and parts[1].value.startswith(".")
        )
    return False


def _is_relative_import_arg(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.startswith(".")
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        return isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.startswith(".")
    return False


def _is_dunder_name_formatted(node: ast.AST) -> bool:
    return isinstance(node, ast.FormattedValue) and _is_dunder_name_node(node.value)


def _is_dunder_name_node(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__name__"


_NO_DYNAMIC_IMPORT = object()


def _dynamic_import_return_target(
    node: ast.AST,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
    dynamic_import_names: set[str],
) -> tuple[str | object | None, str]:
    call = _find_dynamic_import_call(node, dynamic_import_names)
    if call is None:
        return _NO_DYNAMIC_IMPORT, "none"
    if not call.args:
        return None, "unknown"
    first = call.args[0]
    mode = _dynamic_import_call_mode(call, param_name)
    if _is_package_prefixed_import_arg(first):
        target = _dynamic_import_package_prefixed_target(first, name, targets_for_name, param_name)
        return target, _dynamic_import_target_mode(call, target, mode)
    if _is_relative_import_arg(first):
        target = _dynamic_import_relative_target(first, name, targets_for_name, param_name)
        return target, _dynamic_import_target_mode(call, target, mode)
    if _is_getattr_parameter(first, param_name):
        return name, _dynamic_import_target_mode(call, name, mode)
    if isinstance(first, ast.Name):
        target = targets_for_name.get(first.id)
        return target, _dynamic_import_target_mode(call, target, mode)
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value, _dynamic_import_target_mode(call, first.value, mode)
    return None, mode


def _dynamic_import_target_mode(node: ast.Call, target: str | None, mode: str) -> str:
    if target is not None and target.startswith(".") and (len(node.args) >= 2 or _has_package_keyword(node)):
        package_mode = _package_argument_mode(node)
        if package_mode != "unknown":
            return package_mode
    return mode


def _find_dynamic_import_call(node: ast.AST, dynamic_import_names: set[str]) -> ast.Call | None:
    if isinstance(node, ast.Call) and _is_dynamic_import_call(node, dynamic_import_names):
        return node
    if isinstance(node, ast.Lambda | ast.GeneratorExp):
        return None
    for child in ast.iter_child_nodes(node):
        call = _find_dynamic_import_call(child, dynamic_import_names)
        if call is not None:
            return call
    return None


def _dynamic_import_package_prefixed_target(
    node: ast.AST,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
) -> str | None:
    if isinstance(node, ast.JoinedStr):
        return _joined_string_dynamic_target(node, name, targets_for_name, param_name, strip_dunder_name=True)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _plus_string_dynamic_target(node, name, targets_for_name, param_name, strip_dunder_name=True)
    return None


def _dynamic_import_relative_target(
    node: ast.AST,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _joined_string_dynamic_target(node, name, targets_for_name, param_name, strip_dunder_name=False)
    return None


def _joined_string_dynamic_target(
    node: ast.JoinedStr,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
    *,
    strip_dunder_name: bool,
) -> str | None:
    parts: list[str] = []
    values = node.values
    if strip_dunder_name and values and _is_dunder_name_formatted(values[0]):
        values = values[1:]
    for value in values:
        part = _dynamic_import_target_part(value, name, targets_for_name, param_name)
        if part is None:
            return None
        parts.append(part)
    target = "".join(parts)
    return _strip_package_prefix_separator(target) if strip_dunder_name else target


def _plus_string_dynamic_target(
    node: ast.BinOp,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
    *,
    strip_dunder_name: bool,
) -> str | None:
    parts = _flatten_string_plus(node)
    if strip_dunder_name and parts and _is_dunder_name_node(parts[0]):
        parts = parts[1:]
    text_parts: list[str] = []
    for part_node in parts:
        part = _dynamic_import_target_part(part_node, name, targets_for_name, param_name)
        if part is None:
            return None
        text_parts.append(part)
    target = "".join(text_parts)
    return _strip_package_prefix_separator(target) if strip_dunder_name else target


def _strip_package_prefix_separator(target: str) -> str | None:
    if not target.startswith("."):
        return None
    stripped = target[1:]
    return None if not stripped or stripped.startswith(".") else stripped


def _flatten_string_plus(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_flatten_string_plus(node.left), *_flatten_string_plus(node.right)]
    return [node]


def _dynamic_import_target_part(
    node: ast.AST,
    name: str,
    targets_for_name: dict[str, str],
    param_name: str,
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.FormattedValue):
        return _dynamic_import_target_part(node.value, name, targets_for_name, param_name)
    if _is_getattr_parameter(node, param_name):
        return name
    if isinstance(node, ast.Name):
        return targets_for_name.get(node.id)
    return None


def _literal_none_mapping_keys(node: ast.AST | None) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    return {
        key.value
        for key, value in zip(node.keys, node.values, strict=False)
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and _is_none_literal(value)
    }


def _mapped_target_exists(
    name: str,
    mapping_targets: dict[str, dict[str, str]],
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    dynamic_import_mode: str,
    include_worktree: bool = True,
) -> bool:
    for targets in mapping_targets.values():
        target = targets.get(name)
        if target is None:
            continue
        return _target_module_exists(
            target,
            package_module,
            root,
            tracked,
            dynamic_import_mode=dynamic_import_mode,
            include_worktree=include_worktree,
        )
    return _target_module_exists(
        name,
        package_module,
        root,
        tracked,
        dynamic_import_mode=dynamic_import_mode,
        include_worktree=include_worktree,
    )


def _target_module_exists(
    target: str,
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    dynamic_import_mode: str,
    include_worktree: bool = True,
) -> bool:
    if not target:
        return False
    candidates: list[str] = []
    if dynamic_import_mode == "unknown":
        return False
    if target.startswith(".") and not _is_package_dynamic_mode(dynamic_import_mode):
        return False
    if _is_package_dynamic_mode(dynamic_import_mode):
        import_package = _dynamic_import_package_base(dynamic_import_mode, package_module)
        resolved = _resolve_relative_dynamic_target(target, import_package) if target.startswith(".") else target
        if resolved is None:
            return False
        candidates.append(resolved if target.startswith(".") else f"{import_package}.{target}" if target else import_package)
    else:
        return _absolute_dynamic_target_exists_or_is_external(
            target,
            package_module,
            root,
            tracked,
            include_worktree=include_worktree,
        )
    return any(
        _resolve_module_path(root, tracked, module, include_worktree=include_worktree) is not None
        or _resolve_namespace_package_dir(root, tracked, module, include_worktree=include_worktree) is not None
        for module in candidates
    )


def _is_package_dynamic_mode(dynamic_import_mode: str) -> bool:
    return dynamic_import_mode == "package" or dynamic_import_mode.startswith("package:")


def _dynamic_import_package_base(dynamic_import_mode: str, package_module: str) -> str:
    if dynamic_import_mode.startswith("package:"):
        return dynamic_import_mode.removeprefix("package:")
    return package_module


def _resolve_relative_dynamic_target(target: str, package_module: str) -> str | None:
    level = len(target) - len(target.lstrip("."))
    suffix = target[level:]
    if level == 0:
        return target
    package_parts = package_module.split(".")
    if level > len(package_parts):
        return None
    base_parts = package_parts[: len(package_parts) - level + 1]
    if not base_parts:
        return suffix or None
    return ".".join([*base_parts, suffix] if suffix else base_parts)


def _absolute_dynamic_target_exists_or_is_external(
    target: str,
    package_module: str,
    root: Path,
    tracked: set[str],
    *,
    include_worktree: bool = True,
) -> bool:
    resolved = _resolve_module_path(root, tracked, target, include_worktree=include_worktree)
    namespace_target = _resolve_namespace_package_dir(root, tracked, target, include_worktree=include_worktree)
    if resolved is not None:
        return resolved in tracked
    if namespace_target is not None:
        return _is_namespace_package_root(tracked, target)

    package_relative_target = f"{package_module}.{target}" if target else package_module
    if (
        _resolve_module_path(root, tracked, package_relative_target, include_worktree=include_worktree) is not None
        or _resolve_namespace_package_dir(root, tracked, package_relative_target, include_worktree=include_worktree)
        is not None
    ):
        return False

    top_level = target.split(".", 1)[0]
    if top_level in _local_import_roots(root, tracked, include_worktree=include_worktree):
        return False
    return _external_module_is_available(target)


def _external_module_is_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _all_exports(node: ast.Assign, mapping_exports: dict[str, set[str]]) -> set[str]:
    if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
        return set()
    return _all_exports_from_value(node.value, mapping_exports)


def _is_all_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _all_mutation_exports(node: ast.AST, mapping_exports: dict[str, set[str]]) -> set[str]:
    if not isinstance(node, ast.Call):
        return set()
    if not isinstance(node.func, ast.Attribute) or not _is_all_name(node.func.value):
        return set()
    if node.keywords:
        return set()
    if node.func.attr == "append" and len(node.args) == 1:
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return {arg.value}
        return set()
    if node.func.attr == "extend" and len(node.args) == 1:
        return _all_exports_from_value(node.args[0], mapping_exports)
    return set()


def _all_exports_from_value(node: ast.AST | None, mapping_exports: dict[str, set[str]]) -> set[str]:
    names = _literal_export_names_from_value(node)
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return names
    if node.func.id not in {"list", "tuple", "set", "sorted"}:
        return names
    if len(node.args) != 1 or node.keywords:
        return names
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        names.update(mapping_exports.get(arg.id, set()))
    mapping_name = _mapping_keys_call_name(arg)
    if mapping_name is not None:
        names.update(mapping_exports.get(mapping_name, set()))
    return names


def _mapping_keys_call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or node.args or node.keywords:
        return None
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "keys":
        return None
    if isinstance(node.func.value, ast.Name):
        return node.func.value.id
    return None


def _package_init_rel_for_module(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2:
        return None
    return (Path(*parts[:-1]) / "__init__.py").as_posix()


def _module_to_file_hint(module: str) -> str:
    return Path(*module.split(".")).with_suffix(".py").as_posix()


def main() -> int:
    try:
        tracked_python_files, source_texts = git_index_python_sources(ROOT)
    except GitMetadataUnavailable as exc:
        print(f"release import hygiene unavailable: {exc}", file=sys.stderr)
        return 2

    issues = find_import_hygiene_issues(ROOT, tracked_python_files, source_texts=source_texts)
    if issues:
        print("Tracked Python imports refer to local modules absent from a clean checkout:", file=sys.stderr)
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        return 1

    print("release import hygiene: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
