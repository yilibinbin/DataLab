"""P2-1: the uv.lock reproducibility pin must be committed and cover the
scientific stack.

Version drift in mpmath/sympy/numpy/scipy silently changes numerical results,
so a numerical tool needs a locked reference resolution checked into the repo.
These tests fail loudly if the lockfile is removed or stops pinning a load-
bearing dependency; CI additionally runs `uv lock --check` to catch drift from
pyproject.toml.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_LOCK = _ROOT / "uv.lock"

_REQUIRED_PACKAGES = ("mpmath", "sympy", "numpy", "scipy", "matplotlib")


def test_lockfile_exists():
    assert _LOCK.is_file(), "uv.lock (the reproducibility pin) is missing"


def test_lockfile_is_tracked_by_git():
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "uv.lock"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "uv.lock must be committed, not gitignored"


@pytest.mark.parametrize("package", _REQUIRED_PACKAGES)
def test_lockfile_pins_scientific_stack(package):
    text = _LOCK.read_text(encoding="utf-8")
    assert f'name = "{package}"' in text, f"{package} not pinned in uv.lock"


def test_lockfile_pins_exact_versions():
    # A lock must pin versions (version = "..."), not just names.
    text = _LOCK.read_text(encoding="utf-8")
    assert 'version = "' in text
