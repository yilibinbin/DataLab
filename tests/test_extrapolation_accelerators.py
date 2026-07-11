from __future__ import annotations

import pytest
from mpmath import mp

from data_extrapolation_latex_latest import ExtrapolationOptions, process_data_string
from extrapolation_methods.accelerators import (
    SequenceAcceleratorConfig,
    SequenceAccelerationError,
    apply_sequence_accelerator,
)


def _build_row(values: list[mp.mpf], digits: int = 50) -> str:
    return " ".join(mp.nstr(v, digits) for v in values)


def test_richardson_requires_at_least_four_terms():
    with mp.workdps(80):
        seq = [mp.mpf("1.5"), mp.mpf("1.25"), mp.mpf("1.125")]
        with pytest.raises(SequenceAccelerationError):
            apply_sequence_accelerator("richardson", seq, SequenceAcceleratorConfig(precision=80))


@pytest.mark.parametrize("precision", [80.0, True, "80"])
def test_sequence_accelerator_rejects_non_integer_precision(
    precision: object,
) -> None:
    seq = [mp.mpf("1"), mp.mpf("0.5"), mp.mpf("0.25")]

    with pytest.raises(TypeError, match="precision must be an integer"):
        apply_sequence_accelerator(
            "shanks",
            seq,
            SequenceAcceleratorConfig(precision=precision),  # type: ignore[arg-type]
        )


def test_richardson_extrapolation_converges_with_more_terms():
    # Use a smooth 1/n^2 tail so Richardson can extrapolate meaningfully with >= 4 terms.
    with mp.workdps(80):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, 9)]  # 8 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + _build_row(terms) + "\n"

        opts = ExtrapolationOptions(method="richardson", mp_precision=80)
        parsed_headers, rows, results = process_data_string(data_text, verbose=False, options=opts)

        assert parsed_headers == headers
        assert len(rows) == 1
        assert len(results) == 1
        res = results[0]
        assert mp.fabs(res.value - limit) < mp.mpf("1e-2")


@pytest.mark.parametrize("method", ["shanks", "wynn_epsilon"])
def test_shanks_family_converges_on_geometric_tail(method: str):
    # s_n = 1 + 2^{-n} -> 1. Shanks/Wynn should converge rapidly.
    with mp.workdps(80):
        limit = mp.mpf("1")
        terms = [limit + mp.power(2, -n) for n in range(1, 7)]  # 6 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + _build_row(terms) + "\n"

        opts = ExtrapolationOptions(method=method, mp_precision=80)
        _, _, results = process_data_string(data_text, verbose=False, options=opts)
        assert results
        res = results[0]
        assert mp.fabs(res.value - limit) < mp.mpf("1e-20")


@pytest.mark.parametrize("variant", ["u", "t", "v"])
def test_levin_variants_run_and_converge(variant: str):
    # Same geometric tail; Levin variants should be close to the limit with enough terms.
    with mp.workdps(80):
        limit = mp.mpf("1")
        terms = [limit + mp.power(2, -n) for n in range(1, 7)]
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + _build_row(terms) + "\n"

        opts = ExtrapolationOptions(method="levin_u", levin_variant=variant, mp_precision=80)
        _, _, results = process_data_string(data_text, verbose=False, options=opts)
        assert results
        res = results[0]
        assert mp.fabs(res.value - limit) < mp.mpf("1e-2")


def test_shanks_diagnostics_use_proper_convergents_not_junk_auxiliary():
    """In mpmath's Wynn-epsilon table the odd columns are non-convergent auxiliary entries that
    diverge to huge junk. The cancellation/error diagnostics must derive from the proper convergent
    difference |last[-1]-last[-3]|, never from the junk last[-2] (audit A6)."""
    from extrapolation_methods.accelerators import _run_shanks

    with mp.workdps(30):
        seq6 = [sum(mp.mpf("4") * (-1) ** k / (2 * k + 1) for k in range(n)) for n in range(1, 7)]
        result = _run_shanks(seq6, "shanks")
        # The 6-input last row has a junk auxiliary ~82; the diagnostic must be the small convergent
        # gap, and equal the error_estimate (both from the same proper source).
        ci = result.metadata["cancellation_indicator"]
        assert ci < mp.mpf("1"), f"cancellation_indicator {ci} is the junk auxiliary, not a convergent gap"
        assert result.metadata["error_estimate"] == ci

        # A 3-input sequence yields a 2-element last row (one convergent + one junk aux) — there is
        # no previous convergent, so neither diagnostic is emitted (consumers fall back sanely).
        seq3 = [mp.mpf("4"), mp.mpf("4") - mp.mpf("4") / 3, mp.mpf("4") - mp.mpf("4") / 3 + mp.mpf("4") / 5]
        result3 = _run_shanks(seq3, "shanks")
        assert "cancellation_indicator" not in result3.metadata
        assert "error_estimate" not in result3.metadata
        assert result3.value is not None  # the extrapolated value is still produced
