from __future__ import annotations

import pytest
from mpmath import mp

from extrapolation_methods.accelerators import (
    SequenceAcceleratorConfig,
    SequenceAccelerationError,
    apply_sequence_accelerator,
)
from extrapolation_methods.power_law import (
    PowerLawComputationError,
    PowerLawConfig,
    extrapolate_power_law,
)


def test_sequence_acceleration_error_is_bilingual() -> None:
    with pytest.raises(SequenceAccelerationError) as excinfo:
        apply_sequence_accelerator("shanks", [mp.mpf("1"), mp.mpf("2")], SequenceAcceleratorConfig(precision=30))
    assert " / " in str(excinfo.value)


def test_power_law_error_is_bilingual() -> None:
    with pytest.raises(PowerLawComputationError) as excinfo:
        extrapolate_power_law(PowerLawConfig(x_values=[3, 4, 5]), [mp.mpf("1"), mp.mpf("2")])
    assert " / " in str(excinfo.value)

