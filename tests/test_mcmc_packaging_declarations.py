"""Pin MCMC dependencies in every install / packaging surface.

emcee and corner are imported lazily through ``HAS_EMCEE`` guards in
``fitting.mcmc_fitter``. That lazy guard is good for graceful
degradation — but it's bad for static tooling: pip-resolution reading
``web_requirements.txt`` and PyInstaller's import-graph analyzer both
miss them unless they're declared explicitly.

Without this test the bundled .app would silently lose MCMC support
again the next time someone tweaks the spec. Pin it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# requirements files


def _pointer_extras(filename: str) -> set[str]:
    """Return the set of extras from a requirements file's `-e .[a,b]` pointer,
    ignoring comment lines (so a comment mentioning 'mcmc' can't false-pass)."""
    import re

    for raw in _read(filename).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"-e \.\[([a-z,]+)\]$", line)
        if match:
            return set(match.group(1).split(","))
    return set()


def test_gui_requirements_pulls_in_mcmc() -> None:
    """Desktop pip install must pull in MCMC deps. Since P2-2 the requirements
    files are thin pointers to pyproject extras, so the MCMC deps come via the
    [mcmc] extra (whose contents are pinned by
    test_pyproject_mcmc_extra_declares_emcee_and_corner)."""
    assert "mcmc" in _pointer_extras("gui_requirements.txt"), (
        "gui_requirements.txt must point at the [mcmc] extra"
    )


def test_gui_requirements_pulls_in_scipy_via_core() -> None:
    # scipy is a core dependency, so any `-e .[...]` pointer installs it — assert
    # the file IS such a pointer, and that core declares scipy.
    assert _pointer_extras("gui_requirements.txt"), "gui_requirements.txt must be an -e .[...] pointer"
    assert '"scipy>=' in _read("pyproject.toml"), "pyproject core deps must include scipy"


def test_web_requirements_pulls_in_scipy_via_core() -> None:
    assert _pointer_extras("web_requirements.txt"), "web_requirements.txt must be an -e .[...] pointer"
    assert '"scipy>=' in _read("pyproject.toml"), "pyproject core deps must include scipy"


def test_pyproject_core_dependencies_declare_scipy() -> None:
    text = _read("pyproject.toml")
    assert '"scipy>=' in text, "pyproject.toml core dependencies must include scipy"


def test_web_requirements_pulls_in_mcmc() -> None:
    """Web pip install must also pull in MCMC deps so the web 'Refine with MCMC'
    toggle actually works. Delivered via the [mcmc] extra since P2-2."""
    assert "mcmc" in _pointer_extras("web_requirements.txt"), (
        "web_requirements.txt must point at the [mcmc] extra"
    )


def test_pyproject_mcmc_extra_declares_emcee_and_corner() -> None:
    """The opt-in [mcmc] extra must keep listing both libs.

    Skipped (rather than ``FileNotFoundError``-ed) when the project
    happens to be on a revision without ``pyproject.toml`` — earlier
    DataLab branches used ``setup.py`` + ``requirements.txt`` only,
    and bisecting through those revisions shouldn't blow up CI.
    """
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("pyproject.toml absent in this revision")
    text = _read("pyproject.toml")
    assert '"emcee>=3.1"' in text or "'emcee>=3.1'" in text, (
        "pyproject.toml [mcmc] extra must list emcee"
    )
    assert '"corner>=2.2"' in text or "'corner>=2.2'" in text, (
        "pyproject.toml [mcmc] extra must list corner"
    )


# ---------------------------------------------------------------------------
# PyInstaller build scripts — hidden-imports / collect-all


def test_mac_build_script_declares_numeric_and_mcmc_hidden_imports() -> None:
    """build_mac_data_gui.sh must pass ``--hidden-import emcee`` and
    ``--hidden-import corner`` so PyInstaller doesn't drop them from
    the bundle just because they're imported lazily."""
    text = _read("build_mac_data_gui.sh")
    assert '--hidden-import "scipy"' in text, (
        "build_mac_data_gui.sh must --hidden-import scipy for precision-16 fitting/root solving"
    )
    assert '--collect-all "scipy"' in text, (
        "build_mac_data_gui.sh must --collect-all scipy so frozen apps can use SciPy"
    )
    assert "--hidden-import" in text and "emcee" in text, (
        "build_mac_data_gui.sh must --hidden-import emcee"
    )
    assert "corner" in text, "build_mac_data_gui.sh must --hidden-import corner"
    # collect-all guarantees lazy backends land in the bundle too
    assert "--collect-all" in text, (
        "build_mac_data_gui.sh must --collect-all the MCMC libs to "
        "include their lazy submodules"
    )


def test_windows_build_script_declares_numeric_and_mcmc_hidden_imports() -> None:
    text = _read("build_windows_data_gui.ps1")
    assert '"--hidden-import", "scipy"' in text, (
        "build_windows_data_gui.ps1 must declare scipy as hidden import"
    )
    assert '"--collect-all", "scipy"' in text, (
        "build_windows_data_gui.ps1 must --collect-all scipy"
    )
    assert '"--hidden-import", "emcee"' in text, (
        "build_windows_data_gui.ps1 must declare emcee as hidden import"
    )
    assert '"--hidden-import", "corner"' in text, (
        "build_windows_data_gui.ps1 must declare corner as hidden import"
    )
    assert '"--collect-all", "emcee"' in text, (
        "build_windows_data_gui.ps1 must --collect-all emcee"
    )
    assert '"--collect-all", "corner"' in text, (
        "build_windows_data_gui.ps1 must --collect-all corner"
    )
