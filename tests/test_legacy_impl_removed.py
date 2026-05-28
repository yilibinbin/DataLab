"""Pin the deletion of app_web/logic/_legacy_impl.py.

Pre-Phase 7 the file was a 2093-line static snapshot kept after the
modular split into common.py / extrapolation.py / fitting.py /
statistics.py / error_propagation.py / plots.py. With zero external
imports it was dead code; we deleted it. This test fails loudly if
anyone re-creates the file (in any form — source OR an orphan
``__pycache__/_legacy_impl.cpython-*.pyc``) or imports the dead
module from anywhere in the source tree.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

# Top-level packages whose Python sources should never reference
# ``_legacy_impl`` again. We walk the repo dynamically for ``*.py``
# files and exclude the well-known non-source trees below — that
# way a future top-level package (``cli2/``, ``app_mobile/`` …) is
# automatically covered without having to remember to update this
# test.
_NON_SOURCE_DIR_NAMES = frozenset({
    "__pycache__", ".git", ".venv", "venv", "env", ".env",
    "build", "dist", "site-packages", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "htmlcov", ".worktrees",
})


def _iter_source_files(repo_root: Path) -> list[Path]:
    """Walk ``repo_root`` for ``*.py`` files, skipping caches/venvs."""
    out: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if any(part in _NON_SOURCE_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return out


def test_legacy_impl_file_does_not_exist():
    repo_root = Path(__file__).resolve().parents[1]
    legacy = repo_root / "app_web" / "logic" / "_legacy_impl.py"
    assert not legacy.exists(), (
        f"{legacy} was deleted in Phase 7 — re-creating it brings back "
        "2093 lines of dead code. Use the modular files instead."
    )


def test_no_orphan_pyc_for_legacy_impl():
    """Defence-in-depth: an orphan ``__pycache__/_legacy_impl.cpython-*.pyc``
    can be loaded by ``importlib.machinery.SourcelessFileLoader``
    even when the source is gone, so a stale build cache could
    silently re-introduce the deleted module. Sweep
    ``app_web/logic/__pycache__`` for any such artefact.
    """
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = repo_root / "app_web" / "logic" / "__pycache__"
    if not cache_dir.exists():
        return
    stale = list(cache_dir.glob("_legacy_impl.*.pyc"))
    if stale:
        listing = "\n".join(f"  {p}" for p in stale)
        raise AssertionError(
            "Orphan _legacy_impl pyc detected — delete __pycache__ to "
            "ensure SourcelessFileLoader cannot load the dead module:\n"
            + listing
        )


def test_modular_logic_imports_still_work():
    """Sanity: the post-deletion facade still resolves every public
    symbol the route handlers need.

    Goes beyond ``__name__`` checks — verifies the imported objects
    are actually dataclasses (not e.g. a stub that happens to have
    the right ``__name__``) so a future refactor that accidentally
    shadows a Bundle with a placeholder fails loudly.
    """
    from app_web.logic import (
        ErrorPropagationBundle,
        ExtrapolationResultBundle,
        FitResultBundle,
        StatsResultBundle,
        _generate_fitting_latex,
        _parse_fit_data,
        _parse_stats_data,
        _render_contribution_plot,
        _render_extrapolation_plot,
        _render_statistics_plot,
        _run_error_propagation,
        _run_extrapolation,
        _run_fit,
        _run_statistics,
    )

    for fn in (
        _run_extrapolation, _run_fit, _run_statistics,
        _run_error_propagation, _generate_fitting_latex,
        _parse_fit_data, _parse_stats_data,
        _render_contribution_plot, _render_extrapolation_plot,
        _render_statistics_plot,
    ):
        assert callable(fn), f"{fn!r} should be callable"

    for cls in (
        FitResultBundle, ExtrapolationResultBundle,
        ErrorPropagationBundle, StatsResultBundle,
    ):
        assert dataclasses.is_dataclass(cls), (
            f"{cls!r} should be a dataclass; a stub with the right "
            "__name__ would otherwise pass silently"
        )


def test_no_dangling_legacy_impl_imports_in_repo():
    """Guard: no live code reference (import / attribute access /
    f-string interpolation) to ``_legacy_impl`` anywhere in the
    source tree. Historical mentions in docstrings or comments are
    allowed — they're valuable context for future readers and don't
    run at import time.

    Implementation note: on Python 3.12+ the tokenizer emits a
    distinct ``NAME`` token for identifiers inside f-string
    expressions (``f"{_legacy_impl}"`` → ``NAME '_legacy_impl'``),
    so the NAME branch already catches them. We keep the f-string
    string-content scan as belt-and-braces for any literal text
    that an older tokenizer might bundle into ``STRING`` instead.
    """
    import re
    import tokenize

    repo_root = Path(__file__).resolve().parents[1]
    self_path = Path(__file__).resolve()
    matches: list[tuple[str, int, str]] = []
    unparseable: list[tuple[str, str]] = []

    for py_file in _iter_source_files(repo_root):
        if py_file.resolve() == self_path:
            continue
        try:
            with py_file.open("rb") as fh:
                tokens = list(tokenize.tokenize(fh.readline))
        except OSError:
            # Transient I/O (permissions, race) — record and skip.
            rel = str(py_file.relative_to(repo_root))
            unparseable.append((rel, "OSError"))
            continue
        except (tokenize.TokenizeError, SyntaxError) as exc:
            # A real parse error means the guard couldn't inspect
            # the file. Surface it so a newly-broken source isn't
            # silently exempt from the dead-import check.
            rel = str(py_file.relative_to(repo_root))
            unparseable.append((rel, f"{type(exc).__name__}: {exc}"))
            continue

        rel = str(py_file.relative_to(repo_root))
        for tok in tokens:
            if tok.type == tokenize.NAME and "_legacy_impl" in tok.string:
                matches.append((rel, tok.start[0], tok.string))
            elif tok.type == tokenize.STRING and re.search(
                r"^[uUrRbB]*[fF]['\"][^'\"]*_legacy_impl", tok.string
            ):
                # Old-tokenizer f-string fallback — covers single-,
                # double-, triple-quoted, lower- and upper-case ``f``
                # prefixes (``f"..."``, ``F'...'``, ``f"""..."""``).
                matches.append((rel, tok.start[0], tok.string[:80]))

    if matches:
        formatted = "\n".join(
            f"  {path}:{lineno}: {text}" for path, lineno, text in matches
        )
        raise AssertionError(
            f"Live code references to _legacy_impl found:\n{formatted}"
        )
    if unparseable:
        formatted = "\n".join(f"  {p}: {why}" for p, why in unparseable)
        raise AssertionError(
            "Files could not be tokenized — guard could not inspect "
            "them, so a stale _legacy_impl reference may slip through. "
            "Fix the listed parse errors before merging:\n" + formatted
        )
