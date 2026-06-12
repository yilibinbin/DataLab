from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ._payload import normalize_json_payload, validate_optional_int


class JobMode(str, Enum):
    EXTRAPOLATION = "extrapolation"
    UNCERTAINTY = "uncertainty"
    STATISTICS = "statistics"
    FITTING = "fitting"
    ROOT_SOLVING = "root_solving"


@dataclass(frozen=True)
class JobOptions:
    precision_digits: int | None = None
    uncertainty_digits: int | None = None
    parallel: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "precision_digits",
            validate_optional_int(self.precision_digits, field_name="options.precision_digits"),
        )
        object.__setattr__(
            self,
            "uncertainty_digits",
            validate_optional_int(self.uncertainty_digits, field_name="options.uncertainty_digits"),
        )
        parallel = normalize_json_payload(self.parallel, path="options.parallel")
        if not isinstance(parallel, Mapping):
            raise TypeError("options.parallel must be a mapping.")
        object.__setattr__(self, "parallel", parallel)


@dataclass(frozen=True)
class ComputeJobRequest:
    mode: JobMode
    inputs: Mapping[str, Any]
    options: JobOptions = field(default_factory=JobOptions)
    request_id: str = ""

    def __post_init__(self) -> None:
        try:
            mode = self.mode if isinstance(self.mode, JobMode) else JobMode(str(self.mode))
        except ValueError as exc:
            raise ValueError(f"Unsupported job mode: {self.mode!r}.") from exc
        object.__setattr__(self, "mode", mode)
        inputs = normalize_json_payload(self.inputs, path="inputs")
        if not isinstance(inputs, Mapping):
            raise TypeError("inputs must be a mapping.")
        object.__setattr__(self, "inputs", inputs)
        if not isinstance(self.request_id, str):
            raise TypeError("request_id must be a string.")
