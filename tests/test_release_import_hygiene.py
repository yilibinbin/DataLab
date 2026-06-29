from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.release_import_hygiene import (
    GitMetadataUnavailable,
    find_import_hygiene_issues,
    git_index_python_sources,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_import_hygiene_flags_untracked_project_local_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg.local_helper import VALUE\n", encoding="utf-8")
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.local_helper -> pkg/local_helper.py (untracked local module)"
    ]


def test_release_import_hygiene_flags_untracked_top_level_local_module(tmp_path: Path) -> None:
    (tmp_path / "consumer.py").write_text("import local_helper\n", encoding="utf-8")
    (tmp_path / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "consumer.py:1: local_helper -> local_helper.py (untracked local module)"
    ]


def test_release_import_hygiene_index_mode_flags_untracked_top_level_local_module(tmp_path: Path) -> None:
    (tmp_path / "consumer.py").write_text("# staged source differs\n", encoding="utf-8")
    (tmp_path / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "consumer.py",
        },
        source_texts={
            "consumer.py": "import local_helper\n",
        },
    )

    assert [issue.format() for issue in issues] == [
        "consumer.py:1: local_helper -> local_helper.py (untracked local module)"
    ]


def test_release_import_hygiene_flags_untracked_top_level_namespace_package(tmp_path: Path) -> None:
    namespace = tmp_path / "local_ns"
    namespace.mkdir()
    (namespace / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text("import local_ns\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "consumer.py:1: local_ns -> local_ns/ (untracked local namespace package)"
    ]


def test_release_import_hygiene_flags_missing_project_local_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("import pkg.missing_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_missing_from_package_import_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import missing_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_missing_relative_init_import(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from .missing_helper import VALUE\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/__init__.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_missing_relative_init_sibling_import(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from . import missing_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/__init__.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_allows_relative_init_sibling_exported_attribute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "VERSION = '1.0'\n"
        "from . import VERSION\n",
        encoding="utf-8",
    )

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_flags_relative_init_attribute_used_before_definition(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from . import VERSION\n"
        "VERSION = '1.0'\n",
        encoding="utf-8",
    )

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/__init__.py:1: pkg.VERSION -> pkg/VERSION.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_all_does_not_mask_missing_relative_sibling_import(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['missing_helper']\n"
        "from . import missing_helper\n",
        encoding="utf-8",
    )

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/__init__.py:2: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_untracked_namespace_local_module(tmp_path: Path) -> None:
    namespace = tmp_path / "tools"
    namespace.mkdir()
    (namespace / "consumer.py").write_text("import tools.local_helper\n", encoding="utf-8")
    (namespace / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "tools/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "tools/consumer.py:1: tools.local_helper -> tools/local_helper.py (untracked local module)"
    ]


def test_release_import_hygiene_flags_missing_namespace_local_module(tmp_path: Path) -> None:
    namespace = tmp_path / "tools"
    namespace.mkdir()
    (namespace / "consumer.py").write_text("import tools.missing_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "tools/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "tools/consumer.py:1: tools.missing_helper -> tools/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_missing_namespace_from_import_module(tmp_path: Path) -> None:
    namespace = tmp_path / "tools"
    namespace.mkdir()
    (namespace / "consumer.py").write_text("from tools import missing_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "tools/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "tools/consumer.py:1: tools.missing_helper -> tools/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_allows_dotted_namespace_package_import(tmp_path: Path) -> None:
    namespace = tmp_path / "pkg" / "sub"
    namespace.mkdir(parents=True)
    (namespace / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text("import pkg.sub\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "consumer.py",
            "pkg/sub/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_does_not_treat_imported_symbols_as_modules(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg.local_helper import VALUE\n", encoding="utf-8")
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_flags_required_child_below_module_file(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg.helper.child import VALUE\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.helper.child -> pkg/helper/child.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_flags_import_module_path_that_is_only_package_attribute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("EXPORTED = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("import pkg.EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_allows_package_level_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("EXPORTED = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_allows_external_reexported_package_attribute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from math import sqrt as EXPORTED\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_bare_annotation_is_not_package_export(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("EXPORTED: int\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_annotation_with_value_is_package_export(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("EXPORTED: int = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_allows_relative_alias_export_for_tracked_sibling_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from . import helper as public_helper\n", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import public_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_allows_relative_alias_export_for_namespace_sibling(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    helper = package / "helper"
    helper.mkdir(parents=True)
    (package / "__init__.py").write_text("from . import helper as public_helper\n", encoding="utf-8")
    (helper / "child.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import public_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper/child.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_allows_relative_submodule_alias_from_namespace_package(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    helper_dir = package / "sub"
    helper_dir.mkdir(parents=True)
    (package / "__init__.py").write_text("from .sub import helper as public_helper\n", encoding="utf-8")
    (helper_dir / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import public_helper\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/sub/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_allows_dynamic_all_mapping_facade_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_mapping_facade_requires_tracked_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_aliased_dynamic_import_requires_tracked_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module as _import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return _import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_local_aliased_dynamic_import_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    from importlib import import_module as _import_module\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return _import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_mapping_facade_allows_tracked_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_subscript_mapping_facade_allows_tracked_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORTS = {'EXPORTED': ('local_helper', 'VALUE')}\n"
        "__all__ = list(_EXPORTS)\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORTS:\n"
        "        module_name, attr_name = _EXPORTS[name]\n"
        "        return getattr(import_module(f'{__name__}.{module_name}'), attr_name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_subscript_mapping_facade_requires_tracked_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORTS = {'EXPORTED': ('missing_helper', 'VALUE')}\n"
        "__all__ = list(_EXPORTS)\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORTS:\n"
        "        module_name, attr_name = _EXPORTS[name]\n"
        "        return getattr(import_module(f'{__name__}.{module_name}'), attr_name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_subscript_mapping_facade_rejects_non_module_first_tuple_slot(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORTS = {'EXPORTED': (None, 'local_helper')}\n"
        "__all__ = list(_EXPORTS)\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORTS:\n"
        "        module_name, attr_name = _EXPORTS[name]\n"
        "        return getattr(import_module(f'{__name__}.{module_name}'), attr_name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_assigned_before_return_requires_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    module = import_module(f'{__name__}.{module_name}')\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_assigned_before_return_allows_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    module = import_module(f'{__name__}.{module_name}')\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_import_assigned_in_sentinel_branch_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        module = import_module(f'{__name__}.{module_name}')\n"
        "    else:\n"
        "        raise AttributeError(name)\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_assigned_in_sentinel_branch_allows_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        module = import_module(f'{__name__}.{module_name}')\n"
        "    else:\n"
        "        raise AttributeError(name)\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_import_assigned_in_literal_branch_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        module = import_module(f'{__name__}.missing_helper')\n"
        "    else:\n"
        "        raise AttributeError(name)\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_assigned_in_nested_active_branch_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if name == 'EXPORTED':\n"
        "        if module_name is not None:\n"
        "            module = import_module(f'{__name__}.{module_name}')\n"
        "        return module\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_after_unknown_nested_branch_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if name == 'EXPORTED':\n"
        "        if name.startswith('_'):\n"
        "            raise AttributeError(name)\n"
        "        module = import_module(f'{__name__}.{module_name}')\n"
        "    else:\n"
        "        raise AttributeError(name)\n"
        "    return module\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_inside_constant_branch_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    if True:\n"
        "        import_module(f'{__name__}.{module_name}')\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_inside_for_loop_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        for _ in [0]:\n"
        "            import_module(f'{__name__}.missing_helper')\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_inside_with_requires_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from contextlib import nullcontext\n"
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        with nullcontext():\n"
        "            import_module(f'{__name__}.missing_helper')\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_inside_try_requires_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        try:\n"
        "            import_module(f'{__name__}.missing_helper')\n"
        "        finally:\n"
        "            pass\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_non_importlib_import_module_method_is_not_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "class Loader:\n"
        "    def import_module(self, name):\n"
        "        return 1\n"
        "loader = Loader()\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return loader.import_module(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_importlib_attribute_dynamic_import_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "import importlib\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return importlib.import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_shadowed_importlib_attribute_method_is_not_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "class Loader:\n"
        "    def import_module(self, name):\n"
        "        return 1\n"
        "importlib = Loader()\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return importlib.import_module(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_later_local_importlib_binding_makes_earlier_attribute_unbound(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "class Loader:\n"
        "    def import_module(self, value):\n"
        "        return 1\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return importlib.import_module('not_real')\n"
        "    importlib = Loader()\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_local_importlib_shadow_object_bound_before_use_is_not_dynamic(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "class Loader:\n"
        "    def import_module(self, value):\n"
        "        return 1\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        importlib = Loader()\n"
        "        return importlib.import_module(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_importlib_attribute_requires_actual_importlib_binding(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return importlib.import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_function_local_import_module_shadow_is_not_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    import_module = lambda value: 1\n"
        "    if name == 'EXPORTED':\n"
        "        return import_module('not_real')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_function_local_importlib_shadow_is_not_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "import importlib\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    class Loader:\n"
        "        def import_module(self, value):\n"
        "            return 1\n"
        "    importlib = Loader()\n"
        "    if name == 'EXPORTED':\n"
        "        return importlib.import_module('not_real')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_positional_only_getattr_parameter_is_supported(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(attr, /):\n"
        "    if attr == 'EXPORTED':\n"
        "        return 1\n"
        "    raise AttributeError(attr)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_nested_branch_inherits_local_dynamic_import_alias(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name in __all__:\n"
        "        from importlib import import_module as imp\n"
        "        if name == 'EXPORTED':\n"
        "            return imp(f'{__name__}.missing_helper')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_later_local_shadow_makes_earlier_import_module_unbound(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return import_module('math')\n"
        "    import_module = lambda value: 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_later_delete_makes_earlier_import_module_unbound(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return import_module('math')\n"
        "    del import_module\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_later_local_import_alias_does_not_apply_before_import_statement(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return imp(f'{__name__}.missing_helper')\n"
        "    from importlib import import_module as imp\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_return_inside_with_supports_export(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from contextlib import nullcontext\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        with nullcontext():\n"
        "            return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_return_inside_try_supports_export(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        try:\n"
        "            return 1\n"
        "        finally:\n"
        "            pass\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_return_inside_for_supports_export(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        for _ in [0]:\n"
        "            return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_lambda_return_does_not_execute_nested_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return lambda: import_module(f'{__name__}.missing_helper')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_generator_return_does_not_execute_nested_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return (import_module(f'{__name__}.missing_helper') for _ in [0])\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_unbound_local_alias_assignment_before_return_is_rejected(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        module = imp(f'{__name__}.missing_helper')\n"
        "        return module\n"
        "    from importlib import import_module as imp\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_active_branch_fallthrough_preserves_non_none_sentinel(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORT_MODULES:\n"
        "        module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        return import_module(f'{__name__}.{module_name}')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_compound_fallthrough_preserves_local_dynamic_alias(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from contextlib import nullcontext\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        with nullcontext():\n"
        "            from importlib import import_module as imp\n"
        "        return imp(f'{__name__}.local_helper')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_compound_body_preserves_local_importlib_shadow_object(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from contextlib import nullcontext\n"
        "class Loader:\n"
        "    def import_module(self, name):\n"
        "        return 1\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        with nullcontext():\n"
        "            importlib = Loader()\n"
        "            module = importlib.import_module(name)\n"
        "        return module\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_try_return_alternatives_do_not_share_local_importlib_binding(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "class Loader:\n"
        "    def import_module(self, name):\n"
        "        return 1\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        try:\n"
        "            importlib = Loader()\n"
        "            return 1\n"
        "        except Exception:\n"
        "            return importlib.import_module('not_real')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_relative_variable_target_with_package_argument_is_package_relative(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': '.local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(module_name, package=__name__)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_annotated_dynamic_import_assignment_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        module: object = import_module(f'{__name__}.missing_helper')\n"
        "        return module\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_annotated_mapping_target_allows_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name: str | None = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_double_dot_relative_target_with_package_argument_is_valid(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    subpackage = package / "sub"
    subpackage.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (subpackage / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return import_module('..helper', package=__name__)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg.sub import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper.py",
            "pkg/sub/__init__.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_try_return_overridden_by_finally_raise_is_rejected(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        try:\n"
        "            return 1\n"
        "        finally:\n"
        "            raise AttributeError(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_aliased_importlib_attribute_dynamic_import_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "import importlib as _importlib\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return _importlib.import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_absolute_dynamic_import_allows_external_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'math'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(module_name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_local_import_module_function_is_not_dynamic_import(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def import_module(name):\n"
        "    return 1\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return import_module(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_truthy_sentinel_guard_allows_tracked_dynamic_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name:\n"
        "        return import_module(f'{__name__}.{module_name}')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_combined_non_none_and_literal_guard_allows_tracked_dynamic_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None and name == 'EXPORTED':\n"
        "        return import_module(f'{__name__}.{module_name}')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_package_prefixed_dynamic_mapping_rejects_empty_target(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': ''}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        return import_module(f'{__name__}.{module_name}')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_bare_dynamic_mapping_rejects_empty_target_without_crashing(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': ''}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        return import_module(module_name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_package_keyword_dynamic_mapping_rejects_empty_target_without_crashing(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': ''}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        return import_module(module_name, package=__name__)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_executed_dynamic_import_assignment_requires_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    import_module(f'{__name__}.{module_name}')\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_assigned_dynamic_import_before_constant_return_requires_tracked_module(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    module = import_module(f'{__name__}.{module_name}')\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_executed_dynamic_import_assignment_allows_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    import_module(f'{__name__}.{module_name}')\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_positive_non_none_guard_allows_tracked_dynamic_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is not None:\n"
        "        return import_module(f'{__name__}.{module_name}')\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_mapping_facade_allows_tuple_mapped_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': ('local_helper', 'VALUE')}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name, attr_name = _EXPORT_MODULES.get(name)\n"
        "    return getattr(import_module(f'{__name__}.{module_name}'), attr_name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_import_name_target_requires_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    return import_module(f'{__name__}.{name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_import_name_target_allows_tracked_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    return import_module(f'{__name__}.{name}')\n",
        encoding="utf-8",
    )
    (package / "EXPORTED.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/EXPORTED.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_mapping_facade_allows_package_relative_dotted_target(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    sub = package / "sub"
    sub.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'sub.helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (sub / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/sub/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_bare_dynamic_mapping_import_is_absolute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    sub = package / "sub"
    sub.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'sub.helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(module_name)\n",
        encoding="utf-8",
    )
    (sub / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/sub/helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_bare_dynamic_name_import_is_absolute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    return import_module(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_bare_dynamic_mapping_rejects_relative_target(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': '.local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(module_name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_name_concat_without_dot_is_not_package_relative(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(__name__ + module_name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_name_concat_with_dot_is_package_relative(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(__name__ + '.' + module_name)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_relative_dynamic_import_with_package_keyword_is_package_relative(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'.{module_name}', package=__name__)\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_relative_dynamic_import_with_string_package_uses_that_package(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    other_package = tmp_path / "otherpkg"
    other_package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'.{module_name}', package='otherpkg')\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (other_package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
            "otherpkg/__init__.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_package_prefixed_dynamic_mapping_rejects_double_dot_target(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': '.local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "local_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/local_helper.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_allows_literal_all_with_getattr_membership_facade(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORTS:\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_membership_branch_must_return_value(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name in _EXPORTS:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_negative_membership_guard_rejects_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'OTHER': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name not in _EXPORTS:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_and_negative_literal_guard_rejects_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name != 'OTHER' and name != 'ALSO_OTHER':\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_and_negative_literal_guard_allows_matching_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['OTHER']\n"
        "def __getattr__(name):\n"
        "    if name != 'OTHER' and name != 'ALSO_OTHER':\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import OTHER\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_negative_literal_guard_allows_matching_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name != 'EXPORTED':\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_true_negative_literal_guard_allows_other_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name != 'OTHER':\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_elif_literal_export_allows_matching_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'OTHER':\n"
        "        return 1\n"
        "    elif name == 'EXPORTED':\n"
        "        return 2\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_elif_rejecting_branch_rejects_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'OTHER':\n"
        "        return 1\n"
        "    elif name == 'EXPORTED':\n"
        "        raise AttributeError(name)\n"
        "    return 2\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_nested_rejecting_branch_rejects_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name != 'OTHER':\n"
        "        if name == 'EXPORTED':\n"
        "            raise AttributeError(name)\n"
        "        return 1\n"
        "    return 2\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_literal_export_obeys_prior_negative_guard(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def __getattr__(name):\n"
        "    if name != 'OTHER':\n"
        "        raise AttributeError(name)\n"
        "    if name == 'EXPORTED':\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_mapping_get_sentinel_rejects_missing_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'OTHER': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_mapping_get_sentinel_allows_present_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_mapping_facade_does_not_require_all(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_mapping_get_none_default_rejects_missing_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'OTHER': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name, None)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_mapping_get_none_value_rejects_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': None}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name, None)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_mapping_get_non_none_default_still_rejects_none_value(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': None}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name, 'fallback')\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_mapping_get_none_else_allows_present_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    else:\n"
        "        return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_or_negative_membership_guard_rejects_missing_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'OTHER': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name not in _EXPORTS or name.startswith('_'):\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_or_none_sentinel_rejects_missing_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'OTHER': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORTS.get(name)\n"
        "    if module_name is None or name.startswith('_'):\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_or_literal_rejects_matching_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED' or name.startswith('_'):\n"
        "        raise AttributeError(name)\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_getattr_negative_membership_else_allows_present_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name not in _EXPORTS:\n"
        "        raise AttributeError(name)\n"
        "    else:\n"
        "        return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_or_negative_else_allows_present_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORTS = {'EXPORTED': 'local_helper'}\n"
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name not in _EXPORTS or name != 'EXPORTED':\n"
        "        raise AttributeError(name)\n"
        "    else:\n"
        "        return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_negative_literal_else_allows_matching_name(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    if name != 'EXPORTED':\n"
        "        raise AttributeError(name)\n"
        "    else:\n"
        "        return 1\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_getattr_accepts_non_name_parameter(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['EXPORTED']\n"
        "def __getattr__(attr):\n"
        "    if attr == 'EXPORTED':\n"
        "        return 1\n"
        "    raise AttributeError(attr)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_dynamic_all_mapping_requires_returning_getattr(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_all_mapping_rejects_nested_only_return(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    def nested():\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_dynamic_all_mapping_rejects_unrelated_name_return(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'EXPORTED': 'local_helper'}\n"
        "__all__ = list(_EXPORT_MODULES)\n"
        "def __getattr__(name):\n"
        "    if name == 'OTHER':\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_allows_literal_getattr_facade_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        return 1\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_rejects_getattr_branch_that_only_raises(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def __getattr__(name):\n"
        "    if name == 'EXPORTED':\n"
        "        raise AttributeError(name)\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_all_does_not_create_package_attribute(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__: list[str] = ['EXPORTED']\n"
        "def __getattr__(name):\n"
        "    raise AttributeError(name)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import EXPORTED\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_star_import_validates_all_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("__all__ = ['missing_helper']\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_star_import_allows_tracked_all_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("__all__ = ['helper']\n", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_star_import_validates_all_mapping_keys_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from importlib import import_module\n"
        "_EXPORT_MODULES = {'EXPORTED': 'missing_helper'}\n"
        "__all__ = list(_EXPORT_MODULES.keys())\n"
        "def __getattr__(name):\n"
        "    module_name = _EXPORT_MODULES.get(name)\n"
        "    if module_name is None:\n"
        "        raise AttributeError(name)\n"
        "    return import_module(f'{__name__}.{module_name}')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_star_import_allows_tracked_all_mapping_keys_module(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "_EXPORT_MODULES = {'helper': 'helper'}\n"
        "__all__ = list(_EXPORT_MODULES.keys())\n",
        encoding="utf-8",
    )
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
            "pkg/helper.py",
        },
    )

    assert issues == []


def test_release_import_hygiene_star_import_tracks_all_augassign_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = []\n"
        "__all__ += ['missing_helper']\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_star_import_tracks_all_append_and_extend_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = []\n"
        "__all__.append('missing_one')\n"
        "__all__.extend(['missing_two'])\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_one -> pkg/missing_one.py (missing from clean checkout)",
        "pkg/consumer.py:1: pkg.missing_two -> pkg/missing_two.py (missing from clean checkout)",
    ]


def test_release_import_hygiene_star_import_reassignment_replaces_previous_all_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "__all__ = ['stale_missing']\n"
        "__all__ = ['missing_helper']\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text("from pkg import *\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_uses_provided_source_texts_for_clean_index_candidate(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("# worktree differs from index candidate\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
        source_texts={
            "pkg/__init__.py": "",
            "pkg/consumer.py": "import pkg.missing_helper\n",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/consumer.py:1: pkg.missing_helper -> pkg/missing_helper.py (missing from clean checkout)"
    ]


def test_release_import_hygiene_index_mode_ignores_worktree_only_package_exports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("__all__ = ['EXPORTED']\n", encoding="utf-8")
    (package / "consumer.py").write_text("# staged source differs\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "pkg/__init__.py",
            "pkg/consumer.py",
        },
        source_texts={
            "pkg/consumer.py": "from pkg import EXPORTED\n",
        },
    )

    assert [issue.format() for issue in issues] == [
        "pkg/__init__.py:0: <parse> -> pkg/__init__.py (missing source text: 'pkg/__init__.py')",
        "pkg/consumer.py:1: pkg.EXPORTED -> pkg/EXPORTED.py (missing from clean checkout)",
    ]


def test_release_import_hygiene_index_mode_ignores_worktree_only_namespace_init(tmp_path: Path) -> None:
    namespace = tmp_path / "tools"
    namespace.mkdir()
    (namespace / "__init__.py").write_text("# untracked worktree-only file\n", encoding="utf-8")
    (namespace / "consumer.py").write_text("# worktree differs from index candidate\n", encoding="utf-8")
    (namespace / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    issues = find_import_hygiene_issues(
        tmp_path,
        {
            "tools/consumer.py",
            "tools/helper.py",
        },
        source_texts={
            "tools/consumer.py": "from tools import helper\n",
            "tools/helper.py": "VALUE = 1\n",
        },
    )

    assert issues == []


def test_release_import_hygiene_current_tracked_python_imports_are_clean() -> None:
    try:
        tracked_python_files, source_texts = git_index_python_sources(ROOT)
    except GitMetadataUnavailable as exc:
        pytest.skip(f"Git metadata unavailable for release import hygiene guard: {exc}")

    issues = find_import_hygiene_issues(ROOT, tracked_python_files, source_texts=source_texts)

    assert issues == [], "Tracked Python imports are not clean-checkout safe:\n" + "\n".join(
        issue.format() for issue in issues
    )


@pytest.mark.parametrize(
    "module_name",
    [
        "datalab_latex.formula_render_service",
        "app_desktop.formula_preview",
        "app_desktop.formula_renderer",
        "shared.formula_export",
        "shared.formula_latex_export",
        "shared.expression_registry",
    ],
)
def test_release_formula_export_registry_import_smoke(module_name: str) -> None:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
