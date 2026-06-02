from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeVar

from mpmath import mp

RootMode = Literal["auto", "scalar", "polynomial", "system", "scan_multiple"]
RootBackend = Literal["scipy", "mpmath"]
RootUncertaintyMethod = Literal["auto", "off", "linear", "monte_carlo", "second_order"]

_K = TypeVar("_K")
_V = TypeVar("_V")


def immutable_mapping(values: Mapping[_K, _V] | None = None) -> Mapping[_K, _V]:
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True)
class RootUnknown:
    name: str
    initial: str = ""
    lower: str = ""
    upper: str = ""
    source: str = "manual"


@dataclass(frozen=True)
class RootInputValue:
    name: str
    value: str


@dataclass(frozen=True)
class RootScanConfig:
    enabled: bool = False
    max_roots: int = 20
    sample_count: int = 200
    residual_tolerance: str = ""
    cluster_tolerance: str = ""


@dataclass(frozen=True)
class RootUncertaintyOptions:
    method: RootUncertaintyMethod = "auto"
    monte_carlo_samples: int = 2000
    monte_carlo_seed: str = ""


@dataclass(frozen=True)
class RootProblem:
    equations: tuple[str, ...]
    unknowns: tuple[RootUnknown, ...]
    known_values: tuple[RootInputValue, ...] = ()
    row_values: Mapping[str, str] = field(default_factory=immutable_mapping)
    constants: Mapping[str, str] = field(default_factory=immutable_mapping)
    mode: RootMode = "auto"
    precision: int = 16
    scan_config: RootScanConfig = field(default_factory=RootScanConfig)
    uncertainty_options: RootUncertaintyOptions = field(default_factory=RootUncertaintyOptions)

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_values", immutable_mapping(self.row_values))
        object.__setattr__(self, "constants", immutable_mapping(self.constants))


@dataclass(frozen=True)
class RootValue:
    name: str
    value: mp.mpf | mp.mpc | complex
    uncertainty: mp.mpf | None = None
    contributions: Mapping[str, mp.mpf] = field(default_factory=immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "contributions", immutable_mapping(self.contributions))


@dataclass(frozen=True)
class RootResult:
    roots: tuple[RootValue, ...]
    backend: RootBackend
    mode: RootMode
    residual_norm: mp.mpf | None = None
    jacobian_condition: mp.mpf | None = None
    warnings: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", immutable_mapping(self.details))


@dataclass(frozen=True)
class RootBatchRowResult:
    row_index: int | None
    source_values: Mapping[str, str] = field(default_factory=immutable_mapping)
    result: RootResult | None = None
    failure: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_values", immutable_mapping(self.source_values))
        if self.result is not None and self.failure is not None:
            raise ValueError("RootBatchRowResult cannot contain both result and failure")


@dataclass(frozen=True)
class RootBatchResult:
    rows: tuple[RootBatchRowResult, ...]
    headers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", immutable_mapping(self.details))
