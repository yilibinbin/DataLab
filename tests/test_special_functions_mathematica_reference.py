"""Cross-validate DataLab's special-function evaluation against
Mathematica's arbitrary-precision reference values.

DataLab parses user-supplied Mathematica-style formulas (``Sin[x]``,
``Erf[x]``, ``Hyp2f1[a,b,c,z]`` …) via
``datalab_latex.expression_engine.safe_eval``. The whitelist behind
that parser binds each spelling to an mpmath function. This test
verifies that mpmath's answer agrees with Mathematica's at 30+
significant digits — the strongest possible numerical-correctness
check for the formula evaluator.

Why this test matters
---------------------

The mypy --strict cleanup (Phase 7 #23) verified type contracts but
did NOT verify numerical answers. Without a Mathematica or scipy
crosscheck, a silent regression in mpmath itself, or in DataLab's
function dispatch (e.g. an off-by-one in the ``hyp1f1`` argument
order), would slip through every type check and every unit test that
only verifies "function returns a number".

How to regenerate ground truth
------------------------------

Requires Mathematica (wolframscript) on PATH. From the repo root::

    cd tests/fixtures/mathematica_reference/special_functions
    wolframscript -file generate.wls > ground_truth.json

The committed JSON is sufficient for CI; only regeneration needs
Mathematica. Tests load the JSON directly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from mpmath import mp

from datalab_latex.expression_engine import safe_eval


_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "mathematica_reference"
    / "special_functions"
    / "ground_truth.json"
)


def _load_cases() -> list[dict]:
    """Load the Mathematica ground-truth cases.

    The JSON is committed and does not require Mathematica at test
    time. Each case is::

        {"id": "Sin[1]", "function": "Sin", "args": [1],
         "value": "0.84147...", "context": "trig"}

    where ``value`` is a 50-digit decimal string straight from
    Mathematica's ``N[..., 50]``.
    """
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data["cases"])


def _format_arg(arg: object) -> str:
    """Render a JSON arg as a DataLab-side expression fragment.

    Numbers go through unchanged (so ``1`` becomes ``"1"``); symbolic
    strings (``"Pi/4"``, ``"1/2"``) are pasted verbatim so the
    expression engine sees the same fraction Mathematica evaluated.
    """
    if isinstance(arg, str):
        return arg
    if isinstance(arg, bool):
        # bool is a subclass of int — handle first to avoid a confusing
        # "True" rendering. None of our cases need bools, but be safe.
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return repr(arg)
    raise TypeError(f"unsupported arg type: {type(arg).__name__}")


def _safe_id(case: dict) -> str:
    """pytest's ``-k`` filter treats ``[`` ``]`` ``,`` ``/`` as
    character-class delimiters, so a raw id like ``"Sin[1]"``
    can't be filtered with ``pytest -k "Sin[1]"``. Replace those
    with underscores so the IDs survive ``-k`` filtering while
    staying readable in the report (``Sin_1_`` instead of
    ``Hyp2f1[1/2,1,3/2,1/4]``)."""
    raw = case["id"]
    return raw.translate(str.maketrans("[],/ ", "_____"))


@pytest.mark.parametrize("case", _load_cases(), ids=_safe_id)
def test_special_function_matches_mathematica(case: dict) -> None:
    """For every whitelisted function, DataLab must agree with
    Mathematica to ≥30 significant digits.

    The expression is built from the case's ``function`` + ``args``
    (e.g. ``Hyp2f1[1/2, 1, 3/2, 1/4]``) and fed to
    ``safe_eval`` exactly as a user-typed formula would be. The
    expected value is loaded from the Mathematica-generated JSON
    fixture.

    The 30-digit threshold (``rel_eps=1e-30``) is well below the
    50-digit precision both sides compute at, so any disagreement
    larger than mpmath's quoted tolerance fails loudly.
    """
    function = case["function"]
    args = case["args"]
    expression = f"{function}[{', '.join(_format_arg(a) for a in args)}]"

    # Match the precision Mathematica generated at, then add a small
    # buffer so the comparison itself doesn't introduce rounding.
    # ``mp.mpf(decimal_string)`` MUST be parsed inside the elevated
    # dps context — otherwise mpmath truncates to the global default
    # (~15 sig digits) before we ever get to the comparison.
    with mp.workdps(60):
        expected = mp.mpf(case["value"])
        actual = mp.mpf(safe_eval(expression, {}))
        assert mp.almosteq(
            actual, expected, rel_eps=mp.mpf("1e-30"), abs_eps=mp.mpf("1e-30")
        ), (
            f"DataLab {expression} = {mp.nstr(actual, 35)} disagrees with "
            f"Mathematica reference {mp.nstr(expected, 35)} "
            f"(diff = {mp.nstr(actual - expected, 10)})"
        )


def test_fixture_covers_every_whitelisted_function() -> None:
    """Drift guard: when a new function is added to
    ``expression_engine._ALLOWED_FUNCTIONS``, this test fails until
    a corresponding case is added to ``ground_truth.json``.

    Without this guard, a maintainer could whitelist a new function
    (say ``Erfc``), bind it to mpmath, and never notice that the
    cross-check has zero coverage of it.
    """
    from datalab_latex.expression_engine import _ALLOWED_FUNCTIONS

    cases = _load_cases()
    covered = {c["function"] for c in cases}
    missing = set(_ALLOWED_FUNCTIONS.keys()) - covered

    # ``Ln`` is an alias for ``Log`` — a single Mathematica reference
    # entry covers both spellings, so don't require a duplicate case.
    missing.discard("Ln")

    assert not missing, (
        "ground_truth.json missing cases for whitelisted functions: "
        + ", ".join(sorted(missing))
        + ". Add entries to "
        "tests/fixtures/mathematica_reference/special_functions/generate.wls "
        "and regenerate."
    )
