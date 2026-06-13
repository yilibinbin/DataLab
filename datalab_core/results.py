from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ._payload import normalize_json_payload


class ResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EMPTY = "empty"


class ResultKind(str, Enum):
    TABLE = "table"
    TEXT = "text"
    PLOT = "plot"
    ARTIFACTS = "artifacts"
    COMPOSITE = "composite"


@dataclass(frozen=True)
class ResultEnvelope:
    kind: ResultKind
    status: ResultStatus
    payload: Mapping[str, Any] = field(default_factory=dict)
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            kind = self.kind if isinstance(self.kind, ResultKind) else ResultKind(str(self.kind))
        except ValueError as exc:
            raise ValueError(f"Unsupported result kind: {self.kind!r}.") from exc
        object.__setattr__(self, "kind", kind)
        try:
            status = self.status if isinstance(self.status, ResultStatus) else ResultStatus(str(self.status))
        except ValueError as exc:
            raise ValueError(f"Unsupported result status: {self.status!r}.") from exc
        object.__setattr__(self, "status", status)
        payload = normalize_json_payload(self.payload, path="payload")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping.")
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "logs", _normalize_text_tuple(self.logs, field_name="logs"))
        object.__setattr__(
            self,
            "warnings",
            _normalize_text_tuple(self.warnings, field_name="warnings"),
        )


def _normalize_text_tuple(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string.")
    normalized = tuple(values)
    for index, value in enumerate(normalized):
        if not isinstance(value, str):
            raise TypeError(f"{field_name}[{index}] must be a string.")
    return normalized
