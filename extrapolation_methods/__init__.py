"""Extrapolation method utilities used by the GUI build."""

from .power_law import (
    PowerLawConfig,
    PowerLawResult,
    PowerLawComputationError,
    extrapolate_power_law,
)
from .accelerators import (
    SequenceAcceleratorConfig,
    SequenceAcceleratorResult,
    SequenceAccelerationError,
    apply_sequence_accelerator,
)

__all__ = [
    "PowerLawConfig",
    "PowerLawResult",
    "PowerLawComputationError",
    "extrapolate_power_law",
    "SequenceAcceleratorConfig",
    "SequenceAcceleratorResult",
    "SequenceAccelerationError",
    "apply_sequence_accelerator",
]
