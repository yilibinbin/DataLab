"""Compact ``X.YZ(WW)`` uncertainty notation must degrade gracefully
when the uncertainty is much larger than the value.

Real-world trigger: an ill-conditioned auto-fit can produce a
parameter ``b0`` whose best-estimate is ~1e-18 but whose covariance
gives a 1-sigma uncertainty of ~1e3. The legacy formatter scales
both into the value's exponent (10**-18), which inflates the
uncertainty's integer representation to a 21-digit number — and
the output looks like ``4(1543551156637860...)[\\text{-18}]``,
nominally correct but unreadable.

Fix: detect the magnitude mismatch and fall back to
``value \\pm uncertainty`` notation (or a hybrid that doesn't
embed a 21-digit count of last-digit-units in parentheses).
"""

from __future__ import annotations

import re

import mpmath as mp


def test_compact_form_used_when_uncertainty_smaller_than_value() -> None:
    """The well-conditioned case must still produce ``4.0(15)[\\text{-18}]``."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("4e-18"), mp.mpf("1.5e-18"))
    # Reasonable digit count; not the runaway form.
    assert re.match(r"^\d+(\.\d+)?\(\d{1,3}\)\[\\text\{[+-]?\d+\}\]?$", out), out


def test_compact_form_avoided_when_uncertainty_dominates_value() -> None:
    """Repro of the user's bug: value 4e-18, uncertainty 1.5e3.
    The compact ``4(150000000000000000000)[\\text{-18}]`` is wrong;
    the formatter must fall back to a readable representation."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("4e-18"), mp.mpf("1.5e3"))
    # The pathological form has 18+ digits inside the parens.
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is None or len(paren_match.group(1)) <= 4, (
        f"compact form should not embed huge digit counts in parens: {out!r}"
    )


def test_compact_form_avoided_when_uncertainty_3x_orders_above_value() -> None:
    """Threshold case: 3 orders of magnitude difference (1e-3 vs 1)
    should also trigger the fallback — a 1000:1 uncertainty:value
    ratio means the parenthetical digits would still be unreadable."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("1.0e-3"), mp.mpf("2.5"))
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is None or len(paren_match.group(1)) <= 4, (
        f"3-order mismatch should not produce huge parenthetical: {out!r}"
    )


def test_compact_form_used_when_value_zero_and_uncertainty_finite() -> None:
    """A fitted parameter that came out at exactly 0.0 with a known
    uncertainty must render readably (no division-by-zero / no
    runaway digit count)."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("0"), mp.mpf("1.5e-3"))
    # Whatever shape the formatter picks, it must not be 20-digit garbage.
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is None or len(paren_match.group(1)) <= 4, out
