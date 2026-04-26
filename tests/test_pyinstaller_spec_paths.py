"""``DataLab.spec`` must stay portable across checkouts.

PyInstaller regenerates the spec on every build by default; the
generated form contains absolute paths derived from wherever the
build last ran. If a developer accidentally commits that
auto-generated form, every other clone (CI, sibling tree, fresh
checkout) breaks because the spec references a directory that
doesn't exist on the new machine.

Codex's adversarial review caught this exact regression — these
tests pin the relative-path discipline so the next regeneration
can't quietly re-introduce the user-specific absolute paths.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "DataLab.spec"


def _spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def test_spec_file_exists() -> None:
    assert SPEC_PATH.is_file(), (
        f"DataLab.spec missing at repo root: {SPEC_PATH}. "
        "Build scripts pass --name DataLab so the spec is regenerated "
        "in place; if it's been deleted, regenerate it from a build."
    )


def test_spec_does_not_hardcode_user_specific_paths() -> None:
    """No absolute paths under ``/Users/...`` (macOS), ``/home/...``
    (Linux), or ``C:\\Users\\...`` (Windows). All paths must derive
    from ``Path(__file__).resolve().parent`` so the spec works on
    whatever checkout location PyInstaller is invoked from."""
    text = _spec_text()
    forbidden_patterns = [
        r"/Users/[A-Za-z0-9_.-]+/",       # macOS home
        r"/home/[A-Za-z0-9_.-]+/",         # Linux home
        r"C:\\\\Users\\\\[A-Za-z0-9_.-]+\\\\",  # Windows home (escaped)
    ]
    bad_lines: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        # Skip comment lines — they document why the rule exists and
        # may legitimately mention user-home paths as anti-examples.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for pat in forbidden_patterns:
            if re.search(pat, line):
                bad_lines.append(f"  line {lineno}: {line.rstrip()}")
                break
    assert not bad_lines, (
        "DataLab.spec contains user-specific absolute paths — these "
        "break a fresh clone / CI / sibling-tree build. Replace with "
        "Path(__file__).resolve().parent-relative construction:\n"
        + "\n".join(bad_lines)
    )


def test_spec_uses_pathlib_relative_anchor() -> None:
    """Positive contract: the spec must derive its root from
    ``__file__`` or ``SPECPATH`` so PyInstaller can run it from any
    location."""
    text = _spec_text()
    assert (
        "__file__" in text or "SPECPATH" in text
    ), (
        "DataLab.spec must compute paths from __file__ / SPECPATH "
        "rather than hard-coding them. Use ``PROJECT_ROOT = "
        "Path(globals().get('SPECPATH') or Path(__file__).resolve().parent)``."
    )


def test_spec_compiles_to_valid_python() -> None:
    """The spec is executed by PyInstaller as Python; a syntax error
    in the regenerated form would surface only at build time on
    whichever platform regenerated it. Catch it here."""
    import ast

    ast.parse(_spec_text(), filename=str(SPEC_PATH))
