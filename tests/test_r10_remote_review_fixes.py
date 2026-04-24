"""Regression tests for the R10 remote-review follow-up fixes.

Covers the four bug reports surfaced by the deeper remote review after the
initial R10 PR (#2) landed:

- **bug_001** (normal): ``_mp_precision_guard`` in ``app_desktop/workers_core``
  dropped the ``[MIN_MPMATH_DPS, MAX_MPMATH_DPS]`` clamp when it was rewritten
  to delegate to ``shared.precision.precision_guard``. This test locks the
  clamp back in.
- **bug_002** (nit): ``validate_latex_content`` used a literal-substring match
  on ``\\write18`` / ``\\immediate\\write18``. The TeX tokenizer accepts
  arbitrary whitespace between the control word and its argument, so these
  tests exercise the tab / space / newline variants to prove the regex now
  catches them.
- **bug_006** (normal): ``ValueError`` sites that use the bilingual ``" / "``
  convention must use ``_dual_msg`` (or emit a string containing the
  space-slash-space separator) so ``split_dual`` can round-trip it. A broken
  ``"。/ English"`` form leaks the Chinese period into the English half. This
  test enumerates a representative slice of raises and asserts they round
  trip.
- **bug_007** (nit): ``add_security_headers`` no longer emits the dead
  ``datalab_csrf`` cookie. Asserting the ``Set-Cookie`` header does not
  contain ``datalab_csrf=`` documents the intent and prevents regression.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mpmath import mp

from shared.bilingual import split_dual
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS

# Repo root derived from this file's location so the tests work on CI,
# contributors' machines, and any verifier host. Matches the hermetic-path
# convention already used in ``tests/conftest.py``. Hardcoding an absolute
# path (``/Users/...``) would silently defeat the repo-wide "。/" guard on
# every non-author machine, reducing this suite's CI value to zero.
REPO_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------------
# bug_001: worker guard must clamp to [MIN_MPMATH_DPS, MAX_MPMATH_DPS]
# ----------------------------------------------------------------------------


def test_bug001_worker_guard_clamps_below_min():
    """Requesting dps=1 must be raised to MIN_MPMATH_DPS inside the guard."""
    from app_desktop.workers_core import _mp_precision_guard

    original = mp.dps
    try:
        with _mp_precision_guard(1) as effective:
            assert effective >= MIN_MPMATH_DPS
            assert mp.dps == effective
    finally:
        mp.dps = original


def test_bug001_worker_guard_clamps_above_max():
    """Requesting dps far above the cap must be lowered to MAX_MPMATH_DPS."""
    from app_desktop.workers_core import _mp_precision_guard

    original = mp.dps
    # Pick a value comfortably above the 1_000_000 cap; no legitimate caller
    # wants this, but a corrupted config could.
    requested = MAX_MPMATH_DPS + 10_000
    try:
        with _mp_precision_guard(requested) as effective:
            assert effective <= MAX_MPMATH_DPS
            assert mp.dps == effective
    finally:
        mp.dps = original


def test_bug001_worker_guard_restores_dps_on_exit():
    """The guard is a context manager — dps must be restored even on exit."""
    from app_desktop.workers_core import _mp_precision_guard

    baseline = mp.dps
    try:
        with _mp_precision_guard(MIN_MPMATH_DPS + 5):
            pass
        assert mp.dps == baseline
    finally:
        mp.dps = baseline


# ----------------------------------------------------------------------------
# bug_002: validate_latex_content tolerates whitespace in dangerous commands
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        r"\write18{touch /tmp/pwn}",           # baseline substring match
        "\\write 18{touch /tmp/pwn}",         # single space
        "\\write\t18{touch /tmp/pwn}",        # tab
        "\\write\n18{touch /tmp/pwn}",        # newline
        "\\write  18{touch /tmp/pwn}",        # multiple spaces
    ],
)
def test_bug002_write18_whitespace_variants_blocked(payload):
    """Whitespace between \\write and 18 must not bypass the filter."""
    from app_web.latex_security import validate_latex_content

    is_safe, warnings = validate_latex_content(payload)
    assert is_safe is False
    assert warnings, "warnings list should not be empty when blocking"
    # The warning uses the canonical " / " bilingual separator.
    zh, en = split_dual(warnings[0])
    assert zh != en
    assert "write18" in zh
    assert "write18" in en


@pytest.mark.parametrize(
    "payload",
    [
        r"\immediate\write18{id}",             # no whitespace
        "\\immediate \\write 18{id}",         # spaces on both sides
        "\\immediate\t\\write\t18{id}",       # tabs
        "\\immediate\n\\write\n18{id}",       # newlines
    ],
)
def test_bug002_immediate_write18_whitespace_variants_blocked(payload):
    """Whitespace inside \\immediate\\write18 must not bypass the filter."""
    from app_web.latex_security import validate_latex_content

    is_safe, warnings = validate_latex_content(payload)
    assert is_safe is False
    assert warnings


def test_bug002_openout_and_input_pipe_still_blocked():
    """Regression guard: the other dangerous patterns remain detected."""
    from app_web.latex_security import validate_latex_content

    for payload in (r"\openout\myfile=evil.tex", r"\input{|cat /etc/passwd}"):
        is_safe, warnings = validate_latex_content(payload)
        assert is_safe is False, payload
        assert warnings, payload


def test_bug002_benign_text_still_accepted():
    """Whitespace-tolerant regex must not false-positive on benign TeX."""
    from app_web.latex_security import validate_latex_content

    benign = r"A document with \write to a log file, not \write18."
    # "\write18" literal is still caught above; we avoid it here and include
    # a near-miss like `\writefancy` to make sure \b prevents accidental hits.
    is_safe, warnings = validate_latex_content(
        r"Some harmless \writefancy{hello} body with \input{figure.tex}."
    )
    assert is_safe is True
    assert warnings == []


# ----------------------------------------------------------------------------
# bug_006: bilingual separator discipline on raises
# ----------------------------------------------------------------------------


def test_bug006_hp_fitter_weight_raise_uses_canonical_separator():
    """Negative-weight rejection in fit_custom_model uses _dual_msg."""
    from fitting import (
        build_model_specification,
        build_parameter_state,
        fit_custom_model,
    )
    from fitting.hp_fitter import mp as hpfmp

    spec = build_model_specification("a*x + b", ["x"], ["a", "b"])
    state = build_parameter_state(
        {"a": {"initial": 1.0}, "b": {"initial": 0.0}},
        ["a", "b"],
    )

    with pytest.raises(ValueError) as excinfo:
        fit_custom_model(
            spec,
            state,
            variable_data={"x": [hpfmp.mpf(i) for i in range(1, 5)]},
            target_data=[hpfmp.mpf(i) for i in range(1, 5)],
            weights=[1.0, -1.0, 1.0, 1.0],
        )

    msg = str(excinfo.value)
    assert " / " in msg
    zh, en = split_dual(msg)
    assert zh and en
    assert zh != en
    # A correct round trip keeps the Chinese punctuation on the zh side;
    # the broken "。/ " form leaked everything to one half.
    assert "。" in zh


def test_bug006_custom_fitting_param_config_uses_canonical_separator():
    """app_web/logic/fitting custom-params raise uses _dual_msg."""
    # Verify by source inspection because the module wires up many heavy
    # dependencies. The separator itself is what matters: " / " with space
    # on both sides, never "。/".
    fitting_src = (REPO_ROOT / "app_web" / "logic" / "fitting.py").read_text(
        encoding="utf-8"
    )
    assert "参数配置必须为 JSON 对象（key 为参数名）。/ Parameter" not in fitting_src
    # The _dual_msg path is what should be present:
    assert "_dual_msg(" in fitting_src
    assert '"参数配置必须为 JSON 对象（key 为参数名）。"' in fitting_src


def test_bug006_no_broken_chinese_period_slash_anywhere():
    """Repository-wide: no raise or string literal contains \"。/\" (missing space)."""
    import subprocess

    # Use git grep to walk tracked files (fast and avoids venv scans). The
    # cwd must resolve on every host — hardcoding an absolute author path
    # would make the guard silently no-op on CI and contributors' machines.
    result = subprocess.run(
        ["git", "grep", "-n", "--", "。/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [
        line
        for line in result.stdout.splitlines()
        # Skip this very test file so its documentation of the broken form
        # does not trip the regression.
        if "test_r10_remote_review_fixes" not in line
        # Skip the review/backlog docs that describe the historical state.
        and not line.split(":", 1)[0].endswith((".md", ".markdown"))
    ]
    assert hits == [], "Broken bilingual separator reappeared:\n" + "\n".join(hits)


# ----------------------------------------------------------------------------
# bug_007: dead CSRF cookie no longer emitted
# ----------------------------------------------------------------------------


def test_bug007_no_csrf_cookie_in_response_headers(monkeypatch):
    """The Flask after_request hook must not set a datalab_csrf cookie."""
    monkeypatch.setenv("DATALAB_WEB_SECRET", "a" * 64)
    monkeypatch.setenv("DATALAB_DEBUG", "1")

    # Import inside the test so the env vars above take effect on module-load
    # paths that read them.
    from app_web.server import create_app

    app = create_app()
    client = app.test_client()

    # GET any page to trigger after_request.
    response = client.get("/")

    set_cookie_values = response.headers.getlist("Set-Cookie")
    joined = "; ".join(set_cookie_values)
    assert "datalab_csrf=" not in joined, (
        f"dead CSRF cookie reappeared in response: {joined!r}"
    )


def test_bug007_get_csrf_token_docstring_does_not_claim_cookie_mirror():
    """Docstring guardrail — stale 'client-readable mirror' must not return."""
    from app_web.security import get_csrf_token

    doc = (get_csrf_token.__doc__ or "").lower()
    assert "client-readable mirror" not in doc
    # Positive assertion: the reason is documented.
    assert "session" in doc
