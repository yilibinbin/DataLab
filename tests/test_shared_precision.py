"""Unit tests for shared.precision internals and precision_guard.

Covers _coerce_int edge cases, precision_guard clamping/validation, and the
probability/confidence-level validation helpers.
"""

from __future__ import annotations

import pytest
from mpmath import mp

from shared.precision import (
    MAX_MPMATH_DPS,
    MIN_MPMATH_DPS,
    _coerce_int,
    _validate_confidence_level,
    _validate_probability,
    precision_guard,
)


class TestCoerceInt:
    def test_plain_int(self) -> None:
        assert _coerce_int(42) == 42

    def test_numeric_string(self) -> None:
        assert _coerce_int("30") == 30

    def test_float_truncates(self) -> None:
        assert _coerce_int(3.9) == 3

    def test_inf_returns_none(self) -> None:
        # int(float('inf')) raises OverflowError -> None.
        assert _coerce_int(float("inf")) is None

    def test_neg_inf_returns_none(self) -> None:
        assert _coerce_int(float("-inf")) is None

    def test_nan_returns_none(self) -> None:
        # int(float('nan')) raises ValueError -> None.
        assert _coerce_int(float("nan")) is None

    def test_non_numeric_string_returns_none(self) -> None:
        assert _coerce_int("not-a-number") is None

    def test_non_numeric_object_returns_none(self) -> None:
        assert _coerce_int(object()) is None

    def test_none_returns_none(self) -> None:
        assert _coerce_int(None) is None


class TestPrecisionGuardBasic:
    def test_none_dps_keeps_precision(self) -> None:
        previous = mp.dps
        with precision_guard(None) as active:
            assert active == previous
            assert mp.dps == previous
        assert mp.dps == previous

    def test_invalid_dps_keeps_precision(self) -> None:
        previous = mp.dps
        with precision_guard("garbage") as active:  # type: ignore[arg-type]
            assert active == previous
            assert mp.dps == previous
        assert mp.dps == previous

    def test_inf_dps_keeps_precision(self) -> None:
        previous = mp.dps
        with precision_guard(float("inf")) as active:  # type: ignore[arg-type]
            assert active == previous
        assert mp.dps == previous

    def test_sets_and_restores(self) -> None:
        previous = mp.dps
        target = previous + 25
        with precision_guard(target) as active:
            assert active == target
            assert mp.dps == target
        assert mp.dps == previous

    def test_restores_on_exception(self) -> None:
        previous = mp.dps
        with pytest.raises(RuntimeError):
            with precision_guard(previous + 10):
                assert mp.dps == previous + 10
                raise RuntimeError("boom")
        assert mp.dps == previous

    def test_dps_one_floored_to_one(self) -> None:
        # Default clamp_min is 1; dps=1 stays 1 (never below 1).
        previous = mp.dps
        with precision_guard(1) as active:
            assert active == 1
            assert mp.dps == 1
        assert mp.dps == previous


class TestPrecisionGuardClamping:
    def test_clamp_min_raises_floor(self) -> None:
        previous = mp.dps
        with precision_guard(5, clamp_min=MIN_MPMATH_DPS) as active:
            assert active == MIN_MPMATH_DPS
        assert mp.dps == previous

    def test_clamp_max_caps_ceiling(self) -> None:
        previous = mp.dps
        with precision_guard(10_000, clamp_max=50) as active:
            assert active == 50
        assert mp.dps == previous

    def test_value_within_bounds_unchanged(self) -> None:
        previous = mp.dps
        with precision_guard(75, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS) as active:
            assert active == 75
        assert mp.dps == previous

    def test_clamp_min_greater_than_clamp_max_wins_min(self) -> None:
        # clamp_min is applied first (max), clamp_max second (min); when
        # clamp_min > clamp_max the min() collapses to clamp_max.
        previous = mp.dps
        with precision_guard(100, clamp_min=200, clamp_max=50) as active:
            assert active == 50
        assert mp.dps == previous

    @pytest.mark.parametrize(
        "dps,clamp_min,clamp_max,expected",
        [
            (5, 10, 100, 10),      # below floor
            (10, 10, 100, 10),     # exactly floor
            (55, 10, 100, 55),     # interior
            (100, 10, 100, 100),   # exactly ceiling
            (500, 10, 100, 100),   # above ceiling
        ],
    )
    def test_clamp_boundaries_parametrized(
        self, dps: int, clamp_min: int, clamp_max: int, expected: int
    ) -> None:
        previous = mp.dps
        with precision_guard(dps, clamp_min=clamp_min, clamp_max=clamp_max) as active:
            assert active == expected
            assert mp.dps == expected
        assert mp.dps == previous


class TestValidateProbability:
    def test_interior_value(self) -> None:
        assert _validate_probability("0.5") == mp.mpf("0.5")

    @pytest.mark.parametrize("bad", ["0", "1", "-0.1", "1.5"])
    def test_out_of_range_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _validate_probability(bad)


class TestValidateConfidenceLevel:
    def test_interior_value(self) -> None:
        assert _validate_confidence_level("0.95") == mp.mpf("0.95")

    @pytest.mark.parametrize("bad", ["0", "1", "-0.2", "2"])
    def test_out_of_range_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _validate_confidence_level(bad)
