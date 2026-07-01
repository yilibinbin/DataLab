"""P2-2: the requirements*.txt files must stay thin pointers to pyproject
extras, so the two dependency sources can't drift.

Before P2-2, each requirements file was a hand-maintained package list that
could (and did) diverge from pyproject's [project.optional-dependencies] — e.g.
requirements-test.txt didn't even list pytest. Now each file is a single
`-e .[extras]` line; this test fails if a raw pinned dependency is re-added.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

_REQUIREMENTS_FILES = [
    "gui_requirements.txt",
    "web_requirements.txt",
    "requirements-test.txt",
    "requirements-docs.txt",
]

# Every extra any requirements file points at must be defined in pyproject.
_EXTRA_LINE = re.compile(r"^-e \.\[([a-z,]+)\]$")


def _pyproject_extras() -> set[str]:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[project.optional-dependencies]", 1)[1]
    block = block.split("\n[", 1)[0]
    return set(re.findall(r"^([A-Za-z0-9_-]+) = \[", block, re.MULTILINE))


@pytest.mark.parametrize("filename", _REQUIREMENTS_FILES)
def test_requirements_file_is_a_thin_pointer(filename):
    lines = [
        line.strip()
        for line in (_ROOT / filename).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    # Exactly one non-comment line, and it must be an `-e .[extras]` pointer.
    assert len(lines) == 1, f"{filename} should have a single `-e .[extras]` line, got {lines}"
    assert _EXTRA_LINE.match(lines[0]), (
        f"{filename} must be a `-e .[extras]` pointer to pyproject, not raw pins: {lines[0]}"
    )


@pytest.mark.parametrize("filename", _REQUIREMENTS_FILES)
def test_pointed_extras_exist_in_pyproject(filename):
    lines = [
        line.strip()
        for line in (_ROOT / filename).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    match = _EXTRA_LINE.match(lines[0])
    assert match
    extras = match.group(1).split(",")
    defined = _pyproject_extras()
    for extra in extras:
        assert extra in defined, f"{filename} points at undefined extra [{extra}]"
