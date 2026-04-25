"""Pin Task 7.3 progress: a fixed allowlist of modules in the
core layer (``shared/`` + ``fitting/``) must report zero mypy
``--strict`` errors. The list grows one PR at a time as Phase 7
sweeps through the remaining 25+ files.

When this test fails, either:
1. the new code in one of the listed modules has a type error
   (fix the type, NOT the test); or
2. you removed a module from the allowlist intentionally — drop
   it from ``MYPY_CLEAN_MODULES`` below and document why in the
   PR description.

Do NOT bypass with ``# type: ignore`` — that defeats the strict
gate. If a third-party library has no stubs and the module needs
one, add it to the ``[[tool.mypy.overrides]]`` block in
``pyproject.toml`` for that specific module instead.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Phase 7 #23 batch 1 — the smallest files in the core layer.
# Each subsequent PR appends to this list as the corresponding
# files are cleaned. Once every core-layer module is covered the
# test will be the canonical "core layer is mypy --strict clean"
# guard.
MYPY_CLEAN_MODULES: tuple[str, ...] = (
    "shared/precision.py",
    "shared/logging_setup.py",
    "shared/crash_reporter.py",
    "shared/ui_keyguards.py",
    "fitting/__init__.py",
    "extrapolation_methods/accelerators.py",
    "datalab_latex/derivatives.py",
    "fitting/constraints.py",
    "fitting/model_parser.py",
    "fitting/hp_fitter.py",
    "datalab_latex/latex_formatting.py",
    "datalab_latex/expression_engine.py",
    "datalab_latex/latex_tables.py",
    "fitting/auto_models.py",
    "datalab_latex/latex_tables_extrapolation.py",
    "datalab_latex/latex_tables_error_propagation.py",
    "shared/caching.py",
    "shared/presets.py",
    "shared/ui_specs.py",
    "shared/units.py",
    "fitting/report.py",
    "fitting/model_selector.py",
    "fitting/mcmc_fitter.py",
    "extrapolation_methods/power_law.py",
)


def _normalise(p: str) -> str:
    """Canonical posix-style path key for cross-platform comparison.

    mypy emits paths using the platform's native separator
    (``shared/precision.py`` on POSIX, ``shared\\precision.py`` on
    Windows). Convert both sides of the comparison to forward
    slashes so the allowlist match works on every CI runner.
    """
    return p.replace("\\", "/")


# Pre-computed canonical forms of the allowlist for fast lookup.
# Use both the literal entry ("shared/precision.py") AND its
# basename suffix ("precision.py") — the allowlist comparison
# accepts a path that ENDS WITH any of these, so absolute paths
# emitted by mypy on some runners (or when --show-absolute-path is
# active) still match correctly.
_NORMALISED_ALLOWLIST = frozenset(_normalise(m) for m in MYPY_CLEAN_MODULES)


def _path_in_allowlist(path: str) -> bool:
    """True if ``path`` (any prefix-style path mypy might emit) is
    one of the allowlisted modules.

    Accepts:
    - exact match: ``shared/precision.py``
    - absolute prefix: ``/Users/x/repo/shared/precision.py``
    - Windows-absolute: ``C:\\repo\\shared\\precision.py``

    Always normalises to forward slashes first.
    """
    norm = _normalise(path)
    return any(
        norm == entry or norm.endswith("/" + entry)
        for entry in _NORMALISED_ALLOWLIST
    )


def _extract_path(error_line: str) -> str | None:
    """Pull the file path off a mypy ``path:line: error: ...`` line.

    Handles Windows drive letters by splitting on ``": error:"`` —
    that exact substring never appears in path components. Returns
    ``None`` if the line doesn't look like a mypy error line.
    """
    # mypy's format: ``<path>:<lineno>: error: <message>``.
    head, sep, _ = error_line.partition(": error:")
    if not sep:
        return None
    # ``head`` is now ``<path>:<lineno>`` (or ``<path>:<lineno>:<col>``
    # if --show-column-numbers). Strip line/column numerics from the
    # right. Walk from the right, peeling off all-digit segments.
    parts = head.split(":")
    while len(parts) > 1 and parts[-1].strip().isdigit():
        parts.pop()
    return ":".join(parts) if parts else None


def test_allowlisted_modules_exist() -> None:
    """Drift guard: every entry in ``MYPY_CLEAN_MODULES`` must
    resolve to a real file on disk.

    Without this check, renaming or deleting an allowlisted module
    would silently let the strict gate pass — mypy would emit zero
    errors for paths it never reads, the allowlist filter would see
    no matches, and ``own_errors`` would stay empty. This test
    catches the rename/delete drift directly so the strict gate
    fails loudly when the allowlist falls out of sync with the
    file tree.
    """
    repo_root = Path(__file__).resolve().parents[1]
    missing = [m for m in MYPY_CLEAN_MODULES if not (repo_root / m).is_file()]
    if missing:
        raise AssertionError(
            "MYPY_CLEAN_MODULES references nonexistent files; rename/"
            "delete drift will silently let the strict gate pass. "
            "Update the allowlist:\n  "
            + "\n  ".join(missing)
        )


@pytest.mark.slow
@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not installed; run `pip install -e \".[typing]\"`",
)
def test_mypy_strict_zero_errors_on_allowlist() -> None:
    """Run ``mypy --strict`` on the allowlist; assert no errors are
    reported in those files. Errors in OTHER files (cascading
    follows) are tolerated for now — they get cleaned PR-by-PR.

    Marked ``slow`` because the mypy subprocess takes 2-6 seconds —
    skip during fast-feedback loops with ``pytest -m "not slow"``.

    Environment note: this test inherits the parent's full
    ``os.environ``. A stale ``MYPYPATH`` or ``MYPY_CACHE_DIR``
    pointing at type-stub overrides in another project could
    cause a false failure. The ``--no-incremental`` flag below
    rules out mypy's own cache, but a custom ``MYPYPATH`` would
    still take effect. If you see odd CI failures with no
    obvious source, check those env vars first.
    """
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable, "-m", "mypy",
        "--strict",
        "--no-incremental",
        *MYPY_CLEAN_MODULES,
    ]
    result = subprocess.run(
        cmd, cwd=repo_root, capture_output=True, text=True, check=False,
    )
    # Sanity guard: mypy returns 0 on success and 1 on any reported
    # error; anything else (2 = bad config, etc.) means the test
    # itself is broken — fail loudly rather than silently passing.
    if result.returncode not in (0, 1):
        pytest.fail(
            f"mypy crashed (rc={result.returncode}) — test is broken:\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    own_errors: list[str] = []
    for line in result.stdout.splitlines():
        if not line or ": error:" not in line:
            continue
        path = _extract_path(line)
        if path is None:
            continue
        if _path_in_allowlist(path):
            own_errors.append(line)
    if own_errors:
        formatted = "\n".join(own_errors)
        pytest.fail(
            "mypy --strict reported errors in the allowlisted modules:\n\n"
            + formatted
            + "\n\nFix the types instead of adding `# type: ignore`. "
            "Full mypy output:\n\n"
            + result.stdout
            + (("\n--- stderr ---\n" + result.stderr) if result.stderr else "")
        )
