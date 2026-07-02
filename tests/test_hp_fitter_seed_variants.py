"""Direct tests for fitting.hp_fitter seed-variant generators.

_generate_seed_variants produces the deterministic compatibility set;
_generate_seed_variants_fallback produces the extra set (with dedup) used only
when the compatibility set fails.
"""

from __future__ import annotations

from mpmath import mp

from fitting.hp_fitter import (
    _generate_seed_variants,
    _generate_seed_variants_fallback,
)


def _seed(*values: str) -> tuple[mp.mpf, ...]:
    return tuple(mp.mpf(v) for v in values)


class TestGenerateSeedVariants:
    def test_empty_seed(self) -> None:
        assert _generate_seed_variants(()) == [()]

    def test_single_seed_count(self) -> None:
        # Original + plus + minus per parameter = 1 + 2*n.
        variants = _generate_seed_variants(_seed("4"))
        assert len(variants) == 3

    def test_original_seed_first(self) -> None:
        seed = _seed("4")
        assert _generate_seed_variants(seed)[0] == seed

    def test_scale_factor_nonzero_value(self) -> None:
        # delta = |value| * 0.25 -> for 4, delta = 1.0 -> {5, 3}.
        variants = _generate_seed_variants(_seed("4"))
        shifted = {v[0] for v in variants}
        assert mp.mpf("5") in shifted
        assert mp.mpf("3") in shifted

    def test_zero_value_uses_half_delta(self) -> None:
        # For a zero seed, delta = 0.5 -> {0.5, -0.5}.
        variants = _generate_seed_variants(_seed("0"))
        shifted = {v[0] for v in variants}
        assert mp.mpf("0.5") in shifted
        assert mp.mpf("-0.5") in shifted

    def test_multi_param_only_one_axis_perturbed(self) -> None:
        seed = _seed("4", "8")
        variants = _generate_seed_variants(seed)
        # 1 + 2*2 variants.
        assert len(variants) == 5
        # Each perturbed variant differs from the seed in exactly one slot.
        for variant in variants[1:]:
            diffs = sum(1 for a, b in zip(variant, seed) if a != b)
            assert diffs == 1


class TestGenerateSeedVariantsFallback:
    def test_empty_seed(self) -> None:
        assert _generate_seed_variants_fallback(()) == [()]

    def test_overall_scaling_present(self) -> None:
        variants = _generate_seed_variants_fallback(_seed("4"))
        assert _seed("2") in variants   # 4 * 0.5
        assert _seed("8") in variants   # 4 * 2.0

    def test_dedup_on_zero_seed(self) -> None:
        # A zero seed scales to itself for every factor -> all-zero variant
        # must appear only once after dedup.
        variants = _generate_seed_variants_fallback(_seed("0"))
        zero_variant = _seed("0")
        assert variants.count(zero_variant) == 1

    def test_dedup_preserves_order_and_uniqueness(self) -> None:
        variants = _generate_seed_variants_fallback(_seed("4", "8"))
        keys = [tuple(mp.nstr(v, 60) for v in variant) for variant in variants]
        assert len(keys) == len(set(keys))

    def test_single_seed_never_empty(self) -> None:
        assert _generate_seed_variants_fallback(_seed("1")) != []
