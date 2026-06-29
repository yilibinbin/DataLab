from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, cast

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


AnalysisSeverity = Literal["info", "warning", "error"]
AnalysisRenderGroup = Literal["metric", "diagnostic", "row_flag", "plot_annotation"]
AnalysisValue = str | int | None
AnalysisRowIndex = str | int | None

_ALLOWED_SEVERITIES = {"info", "warning", "error"}
_ALLOWED_RENDER_GROUPS = {"metric", "diagnostic", "row_flag", "plot_annotation"}
_ROW_FIELDS = {
    "key",
    "label_key",
    "value",
    "uncertainty",
    "source",
    "row_index",
    "method",
    "severity",
    "message_key",
    "render_group",
}


@dataclass(frozen=True)
class AnalysisRow:
    key: str
    label_key: str
    value: AnalysisValue = None
    uncertainty: AnalysisValue = None
    source: str | None = None
    row_index: AnalysisRowIndex = None
    method: str | None = None
    severity: AnalysisSeverity = "info"
    message_key: str | None = None
    render_group: AnalysisRenderGroup = "metric"

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _required_text(self.key, "key"))
        object.__setattr__(self, "label_key", _required_text(self.label_key, "label_key"))
        object.__setattr__(self, "value", _optional_value(self.value, "value"))
        object.__setattr__(self, "uncertainty", _optional_value(self.uncertainty, "uncertainty"))
        object.__setattr__(self, "source", _optional_text(self.source, "source"))
        object.__setattr__(self, "row_index", _optional_row_index(self.row_index, "row_index"))
        object.__setattr__(self, "method", _optional_text(self.method, "method"))
        object.__setattr__(self, "severity", _choice(self.severity, _ALLOWED_SEVERITIES, "severity"))
        object.__setattr__(self, "message_key", _optional_text(self.message_key, "message_key"))
        object.__setattr__(
            self,
            "render_group",
            _choice(self.render_group, _ALLOWED_RENDER_GROUPS, "render_group"),
        )

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "key": self.key,
            "label_key": self.label_key,
            "severity": self.severity,
            "render_group": self.render_group,
        }
        for field_name in ("value", "uncertainty", "source", "row_index", "method", "message_key"):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload


def analysis_row_from_json(payload: Mapping[str, Any]) -> AnalysisRow:
    if not isinstance(payload, Mapping):
        raise TypeError("analysis row payload must be a mapping.")
    unknown = set(payload) - _ROW_FIELDS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"analysis row payload contains unsupported fields: {names}.")
    key = _required_text(payload.get("key"), "key")
    label_key = _required_text(payload.get("label_key"), "label_key")
    value = _optional_value(payload.get("value"), "value")
    uncertainty = _optional_value(payload.get("uncertainty"), "uncertainty")
    source = _optional_text(payload.get("source"), "source")
    row_index = _optional_row_index(payload.get("row_index"), "row_index")
    method = _optional_text(payload.get("method"), "method")
    severity = _severity(payload.get("severity", "info"))
    message_key = _optional_text(payload.get("message_key"), "message_key")
    render_group = _render_group(payload.get("render_group", "metric"))
    return AnalysisRow(
        key=key,
        label_key=label_key,
        value=value,
        uncertainty=uncertainty,
        source=source,
        row_index=row_index,
        method=method,
        severity=severity,
        message_key=message_key,
        render_group=render_group,
    )


def analysis_rows_to_json(rows: Sequence[AnalysisRow]) -> list[dict[str, object]]:
    return [row.to_json() for row in rows]


def analysis_rows_from_json(payload: Any) -> tuple[AnalysisRow, ...]:
    if isinstance(payload, Mapping):
        raise TypeError("analysis rows payload must be a sequence of row mappings, not a mapping.")
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray, memoryview)):
        raise TypeError("analysis rows payload must be a sequence of mappings.")
    return tuple(analysis_row_from_json(row) for row in payload)


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


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None.")
    return value


def _optional_value(value: Any, field_name: str) -> AnalysisValue:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric values as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string, integer, or None.")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    raise TypeError(f"{field_name} must be a string, integer, or None.")


def _optional_row_index(value: Any, field_name: str) -> AnalysisRowIndex:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass row identifiers as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string, integer, or None.")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    raise TypeError(f"{field_name} must be a string, integer, or None.")


def _choice(value: Any, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {choices}.")
    return value


def _severity(value: Any) -> AnalysisSeverity:
    return cast(AnalysisSeverity, _choice(value, _ALLOWED_SEVERITIES, "severity"))


def _render_group(value: Any) -> AnalysisRenderGroup:
    return cast(AnalysisRenderGroup, _choice(value, _ALLOWED_RENDER_GROUPS, "render_group"))
