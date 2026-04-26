"""Compact ``X.YZ(WW)`` uncertainty notation must produce
siunitx-S-column-compatible output even when the uncertainty
dominates the value.

Real-world trigger: an ill-conditioned auto-fit can produce a
parameter ``b0`` whose best-estimate is ~1e-18 but whose covariance
gives a 1-sigma uncertainty of ~1e3. Pre-fix the formatter scaled
both into the value's exponent (10**-18), which inflated the
uncertainty's integer representation to a 21-digit number — output
looked like ``4(1543551156637860)[\\text{-18}]``.

A first attempt fixed it by emitting ``value \\pm uncertainty``,
but ``\\pm`` is a math-mode command that an siunitx ``S`` column
rejects with ``Missing $ inserted``. The current implementation
instead anchors the displayed exponent to the **uncertainty** when
it dominates, so the parenthetical stays bounded AND the output
remains pure siunitx parenthetical syntax (no math-mode escapes).
"""

from __future__ import annotations

import re

import mpmath as mp


def test_compact_form_used_when_uncertainty_smaller_than_value() -> None:
    """The well-conditioned case must produce normal compact form."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("4e-18"), mp.mpf("1.5e-18"))
    assert re.match(r"^\d+(\.\d+)?\(\d{1,3}\)\[\\text\{[+-]?\d+\}\]?$", out), out


def test_pathological_uncertainty_emits_siunitx_compatible_parenthetical() -> None:
    """Repro of the user's bug: value 4e-18, uncertainty 1.5e3.

    The output MUST:
    1. NOT contain ``\\pm`` (math-mode, rejected in S column).
    2. NOT have a 20-digit parenthetical integer.
    3. BE valid siunitx parenthetical syntax — i.e. ``digits(int)``
       optionally followed by ``[\\text{...}]``.
    """
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("4e-18"), mp.mpf("1.5e3"))

    assert "\\pm" not in out, f"\\pm rejected by siunitx S column: {out!r}"
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is not None, f"missing parenthetical: {out!r}"
    assert len(paren_match.group(1)) <= 4, (
        f"parenthetical must stay bounded: {out!r}"
    )
    # Pure siunitx form: digits, then ``(int)``, optionally
    # followed by ``[\text{exp}]``. No spaces, no ``\pm``.
    assert re.fullmatch(
        r"-?\d+(\.\d+)?\(\d+\)(\[\\text\{[+-]?\d+\}\])?", out
    ), f"output is not siunitx parenthetical syntax: {out!r}"


def test_pathological_anchors_exponent_to_uncertainty() -> None:
    """Concretely: with value 4e-18 and uncertainty 1.5e3, the
    displayed exponent must be the uncertainty's (+3), not the
    value's (-18). The value rounds to 0 at that scale; that is the
    correct visual indication that the uncertainty dominates."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(
        mp.mpf("4e-18"), mp.mpf("1.5e3"), 1
    )
    assert "+3" in out, f"expected uncertainty's +3 exponent: {out!r}"
    assert "-18" not in out, (
        f"value's -18 exponent must not leak through when uncertainty "
        f"dominates: {out!r}"
    )


def test_three_orders_mismatch_anchors_to_uncertainty() -> None:
    """Threshold: 3 orders of magnitude difference (1e-3 vs 1) also
    triggers the uncertainty anchor."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("1.0e-3"), mp.mpf("2.5"))
    assert "\\pm" not in out
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is not None and len(paren_match.group(1)) <= 4, out


def test_value_zero_uncertainty_finite_emits_compact_form() -> None:
    """A fitted parameter that came out at exactly 0.0 with a known
    uncertainty must render in pure siunitx parenthetical (no ``\\pm``)."""
    from datalab_latex.latex_formatting import format_result_with_uncertainty_latex

    out = format_result_with_uncertainty_latex(mp.mpf("0"), mp.mpf("1.5e-3"))
    assert "\\pm" not in out
    # Value=0 paired with uncertainty=1.5e-3 → anchor to uncertainty's
    # exponent so the form stays in scientific brackets if non-zero.
    paren_match = re.search(r"\(([0-9]+)\)", out)
    assert paren_match is not None, out
    assert len(paren_match.group(1)) <= 4, out
