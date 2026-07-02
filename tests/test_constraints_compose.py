"""Edge-case tests for fitting.constraints.ParameterState.compose().

Covers bounds clamping, fixed values, dependent-expression resolution,
cycle/missing-dependency detection, and the length-mismatch guard added so a
short/long free-parameter vector fails loudly instead of silently truncating.
"""

from __future__ import annotations

import pytest
from mpmath import mp

from fitting.constraints import DependentDefinition, ParameterState


def _state(**kwargs: object) -> ParameterState:
    defaults: dict[str, object] = {
        "free_params": ["a"],
        "bounds": {},
        "initial_guess": {"a": mp.mpf("1")},
        "fixed_values": {},
        "dependent_defs": {},
    }
    defaults.update(kwargs)
    return ParameterState(**defaults)  # type: ignore[arg-type]


class TestComposeBasics:
    def test_maps_free_params(self) -> None:
        state = _state(free_params=["a", "b"], bounds={})
        result = state.compose((mp.mpf("2"), mp.mpf("3")))
        assert result == {"a": mp.mpf("2"), "b": mp.mpf("3")}

    def test_lower_bound_clamps(self) -> None:
        state = _state(bounds={"a": (mp.mpf("0"), None)})
        assert state.compose((mp.mpf("-5"),))["a"] == mp.mpf("0")

    def test_upper_bound_clamps(self) -> None:
        state = _state(bounds={"a": (None, mp.mpf("10"))})
        assert state.compose((mp.mpf("50"),))["a"] == mp.mpf("10")

    def test_fixed_values_merged(self) -> None:
        state = _state(fixed_values={"c": mp.mpf("7")})
        result = state.compose((mp.mpf("1"),))
        assert result["c"] == mp.mpf("7")


class TestComposeDependent:
    def test_dependent_resolved(self) -> None:
        definition = DependentDefinition(
            evaluate=lambda p: p["a"] * mp.mpf("2"),
            dependencies=("a",),
            partials={},
        )
        state = _state(dependent_defs={"d": definition})
        result = state.compose((mp.mpf("3"),))
        assert result["d"] == mp.mpf("6")

    def test_unresolvable_dependency_raises(self) -> None:
        # Depends on a name that never becomes available -> KeyError forever.
        definition = DependentDefinition(
            evaluate=lambda p: p["missing"],
            dependencies=("missing",),
            partials={},
        )
        state = _state(dependent_defs={"d": definition})
        with pytest.raises(ValueError, match="Cyclic or unresolved"):
            state.compose((mp.mpf("1"),))


class TestComposeLengthMismatch:
    def test_too_few_values_raises(self) -> None:
        state = _state(free_params=["a", "b"], initial_guess={"a": mp.mpf("1"), "b": mp.mpf("1")})
        with pytest.raises(ValueError, match="length mismatch"):
            state.compose((mp.mpf("1"),))

    def test_too_many_values_raises(self) -> None:
        state = _state(free_params=["a"], initial_guess={"a": mp.mpf("1")})
        with pytest.raises(ValueError, match="length mismatch"):
            state.compose((mp.mpf("1"), mp.mpf("2")))

    def test_message_is_bilingual(self) -> None:
        state = _state(free_params=["a", "b"], initial_guess={"a": mp.mpf("1"), "b": mp.mpf("1")})
        with pytest.raises(ValueError) as excinfo:
            state.compose(())
        # _dual_msg joins with " / "; both halves must be present.
        assert " / " in str(excinfo.value)

    def test_exact_length_ok(self) -> None:
        state = _state(free_params=["a", "b"], initial_guess={"a": mp.mpf("1"), "b": mp.mpf("1")})
        result = state.compose((mp.mpf("5"), mp.mpf("6")))
        assert result == {"a": mp.mpf("5"), "b": mp.mpf("6")}
