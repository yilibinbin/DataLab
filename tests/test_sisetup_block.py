"""Single source of truth for ``\\sisetup{...}`` emission.

Background
----------

DataLab emits LaTeX for fits, statistics, and error-propagation tables.
Every emitted document loads ``siunitx`` and writes a ``\\sisetup{...}``
preamble block to control number formatting (decimal grouping,
uncertainty rendering, etc.).

Until now the preamble was duplicated across five sites:

- ``datalab_latex/latex_tables_common.py``
- ``statistics_utils.py`` (twice)
- ``app_desktop/fitting_latex_writer.py``
- ``app_web/logic/fitting.py``

A user reported their compile failing with ``LaTeX3 Error: The key
'siunitx/digit-group-size' is unknown`` — that key only exists in
siunitx v3 (TeX Live 2020+). On older installs (siunitx v2) the key
is rejected and the document fails to compile.

Fix
---

Centralize the block in ``datalab_latex.sisetup_block.build_sisetup_block``
and emit a v2/v3-compatible ``\\sisetup`` plus a ``\\@ifpackagelater``
guard for the v3-only ``digit-group-size`` key. v2 falls back to the
hard-coded "every 3 digits" siunitx default.

These tests pin:
- The block has the universally-valid keys at the top.
- The v3-only key is wrapped in a feature-detection guard.
- All five legacy emitters route through the helper.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# build_sisetup_block — public API


def test_block_returns_string_with_sisetup_open_and_close() -> None:
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=3, include_dcolumn=False)
    assert "\\sisetup{" in block
    # Closing brace on its own line so editors see well-formed nesting
    assert "\n}" in block


def test_block_uses_group_minimum_digits_for_v2_compat() -> None:
    """siunitx v2 has no ``digit-group-size`` key; use the v2-safe
    ``group-minimum-digits`` to control when grouping kicks in."""
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=3, include_dcolumn=False)
    assert "group-minimum-digits = 3" in block


def test_block_groups_integer_part_not_only_decimals() -> None:
    """When grouping is enabled it must group the INTEGER part (thousands
    separators) — the common case. ``group-digits = decimal`` grouped only the
    fractional digits, so 12345678.00 rendered as 12345678.00 (integer ungrouped),
    which users saw as 'grouping does nothing'. ``group-digits = all`` groups both
    the integer and decimal parts (12 345 678.00)."""
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=3, include_dcolumn=False)
    assert "group-digits = all" in block
    assert "group-digits = decimal" not in block


def test_block_wraps_v3_key_in_ifpackagelater_guard() -> None:
    """``digit-group-size`` is a siunitx-v3 key but the activation
    history is messy: siunitx 3.0.49 (the version Tectonic bundles,
    date 2022-02-15) defines the key in source yet rejects
    ``\\sisetup{digit-group-size = N}`` at runtime. Working dispatch
    only lands in later 3.x releases (verified on 3.4.14, date
    2025-07-09).

    Cutoff therefore pinned to **2024/01/01** — empirically:
    Tectonic-bundled 3.0.49 evaluates as earlier (override skipped,
    siunitx falls back to its default of 3 → still compiles) and TeX
    Live 2025 v3.4.14 evaluates as later (override fires, requested
    size honoured).

    Earlier cutoff revisions (2020/01/01, 2020/02/08) bracketed
    Tectonic's siunitx and re-introduced the user-reported error.

    The wrapper is plain ``\\makeatletter ... \\makeatother`` — NOT
    additionally wrapped in ``\\begingroup ... \\endgroup`` because
    TeX groups scope ``\\sisetup``'s package-state assignments and
    would silently revert the override at ``\\endgroup`` time.
    """
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=4, include_dcolumn=False)
    assert "digit-group-size = 4" in block
    assert "@ifpackagelater" in block
    # The cutoff date is the load-bearing detail — assert it exactly
    # so a future "let's bump it earlier for some reason" change has
    # to consciously update this test and acknowledge the Tectonic
    # regression risk.
    assert "2024/01/01" in block
    assert r"\makeatletter" in block
    assert r"\makeatother" in block
    # \begingroup must NOT appear — it would scope the \sisetup
    # assignment and silently negate the override at \endgroup time.
    assert r"\begingroup" not in block, (
        "begingroup wrap regresses siunitx v3 group-size override; see "
        "round-2 codex finding"
    )
    assert r"\endgroup" not in block


def test_block_omits_v3_key_when_group_size_matches_v2_default() -> None:
    """The v2 default group size is 3; emitting the v3-only override
    when the user requested 3 too is just churn."""
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=3, include_dcolumn=False)
    # group-minimum-digits = 3 stays (v2-safe); digit-group-size
    # is unnecessary because both v2 and v3 default to size 3.
    assert "digit-group-size" not in block


def test_block_dcolumn_branch_skips_grouping() -> None:
    """The dcolumn branch keeps ``group-digits = false`` to defer to
    dcolumn's column-spec for alignment — no grouping options."""
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=3, include_dcolumn=True)
    assert "group-digits = false" in block
    assert "digit-group-size" not in block


def test_block_group_size_zero_disables_grouping() -> None:
    from datalab_latex.sisetup_block import build_sisetup_block

    block = build_sisetup_block(group_size=0, include_dcolumn=False)
    assert "group-digits = false" in block


# ---------------------------------------------------------------------------
# Migration: every legacy emitter must route through the helper.
# These tests guard against future drift.


def test_latex_tables_common_uses_helper() -> None:
    text = _read("datalab_latex/latex_tables_common.py")
    assert "build_sisetup_block" in text, (
        "datalab_latex/latex_tables_common.py must use build_sisetup_block "
        "instead of duplicating the sisetup body inline"
    )


def test_statistics_utils_uses_helper() -> None:
    text = _read("statistics_utils.py")
    assert "build_sisetup_block" in text, (
        "statistics_utils.py must use build_sisetup_block (was emitting "
        "two near-duplicate copies inline)"
    )


def test_fitting_latex_writer_uses_helper() -> None:
    text = _read("app_desktop/fitting_latex_writer.py")
    assert "build_sisetup_block" in text


def test_web_fitting_logic_uses_helper() -> None:
    text = _read("app_web/logic/fitting.py")
    assert "build_sisetup_block" in text


def test_no_more_raw_digit_group_size_outside_helper() -> None:
    """The bug was that 5 places emitted ``digit-group-size = N`` as a
    hard-coded f-string. Once the helper centralizes the v3 guard, no
    other source file in the repo (outside the helper itself + comment
    references like this docstring) should still emit that key.

    We grep for the *emitted* form ``digit-group-size = `` (with the
    equals + space) so explanatory comments and docstrings are not
    flagged as drift.
    """
    import subprocess

    result = subprocess.run(
        [
            "grep", "-rn", "--include=*.py",
            "-e", "digit-group-size = ",  # emitted form, not commentary
            str(REPO_ROOT / "app_desktop"),
            str(REPO_ROOT / "app_web"),
            str(REPO_ROOT / "datalab_latex"),
            str(REPO_ROOT / "shared"),
            str(REPO_ROOT / "statistics_utils.py"),
        ],
        capture_output=True, text=True,
    )
    matches = [
        line for line in result.stdout.splitlines()
        if "sisetup_block.py" not in line  # the central helper is allowed
    ]
    assert not matches, (
        "Hard-coded digit-group-size emit found outside the central helper:\n"
        + "\n".join(matches)
    )
