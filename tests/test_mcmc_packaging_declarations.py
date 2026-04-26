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

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# requirements files


def test_gui_requirements_declares_emcee_and_corner() -> None:
    """Desktop pip install must pull in MCMC deps."""
    text = _read("gui_requirements.txt")
    assert "emcee" in text, "gui_requirements.txt must list emcee"
    assert "corner" in text, "gui_requirements.txt must list corner"


def test_web_requirements_declares_emcee_and_corner() -> None:
    """Web pip install must also pull in MCMC deps so the web 'Refine
    with MCMC' toggle actually works (was missing pre-Phase-7-followup,
    silent feature-loss on web deployments)."""
    text = _read("web_requirements.txt")
    assert "emcee" in text, "web_requirements.txt must list emcee"
    assert "corner" in text, "web_requirements.txt must list corner"


def test_pyproject_mcmc_extra_declares_emcee_and_corner() -> None:
    """The opt-in [mcmc] extra must keep listing both libs."""
    text = _read("pyproject.toml")
    assert '"emcee>=3.1"' in text or "'emcee>=3.1'" in text, (
        "pyproject.toml [mcmc] extra must list emcee"
    )
    assert '"corner>=2.2"' in text or "'corner>=2.2'" in text, (
        "pyproject.toml [mcmc] extra must list corner"
    )


# ---------------------------------------------------------------------------
# PyInstaller build scripts — hidden-imports / collect-all


def test_mac_build_script_declares_mcmc_hidden_imports() -> None:
    """build_mac_data_gui.sh must pass ``--hidden-import emcee`` and
    ``--hidden-import corner`` so PyInstaller doesn't drop them from
    the bundle just because they're imported lazily."""
    text = _read("build_mac_data_gui.sh")
    assert "--hidden-import" in text and "emcee" in text, (
        "build_mac_data_gui.sh must --hidden-import emcee"
    )
    assert "corner" in text, "build_mac_data_gui.sh must --hidden-import corner"
    # collect-all guarantees lazy backends land in the bundle too
    assert "--collect-all" in text, (
        "build_mac_data_gui.sh must --collect-all the MCMC libs to "
        "include their lazy submodules"
    )


def test_windows_build_script_declares_mcmc_hidden_imports() -> None:
    text = _read("build_windows_data_gui.ps1")
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
