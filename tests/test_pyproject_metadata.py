"""Phase 4 #22 — pyproject.toml schema regression tests.

Pin the project metadata contract so a future edit can't drop an
extra, the CLI entry point, or the mypy strict-on-core rule without
a visible failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# tomllib stdlib on 3.11+. Backport via tomli on earlier, but we
# require 3.11 so skip the fallback.
if sys.version_info < (3, 11):  # pragma: no cover
    pytest.skip("pyproject tests require Python 3.11+", allow_module_level=True)
import tomllib  # noqa: E402


_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def _pyproject() -> dict:
    if not _PYPROJECT.exists():
        pytest.skip("pyproject.toml not present yet")
    with open(_PYPROJECT, "rb") as fh:
        return tomllib.load(fh)


def test_pyproject_declares_project_table(_pyproject):
    assert "project" in _pyproject
    project = _pyproject["project"]
    assert project["name"] == "datalab"
    assert project["requires-python"].startswith(">=3.")


def test_pyproject_declares_core_dependencies(_pyproject):
    deps = _pyproject["project"]["dependencies"]
    required = {"Pillow", "mpmath", "sympy", "matplotlib", "pyyaml"}
    for pkg in required:
        assert any(
            d.lower().startswith(pkg.lower())
            for d in deps
        ), f"core dependency {pkg} missing from pyproject"


def test_pyproject_declares_desktop_extra(_pyproject):
    extras = _pyproject["project"]["optional-dependencies"]
    assert "desktop" in extras
    assert any("PySide6" in d for d in extras["desktop"])


def test_pyproject_declares_web_extra(_pyproject):
    extras = _pyproject["project"]["optional-dependencies"]
    assert "web" in extras
    deps = extras["web"]
    assert any("Flask" in d for d in deps)
    assert any("waitress" in d.lower() for d in deps)


def test_pyproject_declares_optional_extras(_pyproject):
    """pint, emcee, flask-socketio — the Phase 3 scaffolded extras."""
    extras = _pyproject["project"]["optional-dependencies"]
    assert "units" in extras
    assert "mcmc" in extras
    assert "collab" in extras
    assert any("pint" in d.lower() for d in extras["units"])
    assert any("emcee" in d.lower() for d in extras["mcmc"])
    assert any("flask-socketio" in d.lower() for d in extras["collab"])


def test_pyproject_declares_test_extra(_pyproject):
    extras = _pyproject["project"]["optional-dependencies"]
    assert "test" in extras
    deps = extras["test"]
    assert any("pytest" in d.lower() for d in deps)
    assert any("pytest-qt" in d.lower() for d in deps)


def test_pyproject_declares_datalab_cli_entry_point(_pyproject):
    scripts = _pyproject["project"].get("scripts", {})
    assert "datalab" in scripts, "CLI console script missing"
    assert scripts["datalab"] == "cli.main:main"


def test_pyproject_declares_mypy_strict_on_core(_pyproject):
    """Phase 4 #23 — mypy strict on shared, fitting, extrapolation,
    datalab_latex."""
    mypy_config = _pyproject.get("tool", {}).get("mypy", {})
    overrides = mypy_config.get("overrides", [])
    strict_modules: list[str] = []
    for override in overrides:
        if override.get("strict") is True:
            strict_modules.extend(override.get("module", []))
    required = [
        "shared.*",
        "fitting.*",
        "extrapolation_methods.*",
        "datalab_latex.*",
    ]
    for mod in required:
        assert mod in strict_modules, (
            f"mypy strict override missing for {mod}"
        )


def test_pyproject_declares_pytest_config(_pyproject):
    pytest_config = _pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert "testpaths" in pytest_config
    assert pytest_config["testpaths"] == ["tests"]


def test_pyproject_packages_exclude_tests(_pyproject):
    """Installed package must not include tests/ — would ship test
    fixtures to end users."""
    pkg_find = (
        _pyproject.get("tool", {})
        .get("setuptools", {})
        .get("packages", {})
        .get("find", {})
    )
    excluded = pkg_find.get("exclude", [])
    assert any("tests" in item for item in excluded)
