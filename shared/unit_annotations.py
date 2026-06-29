from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from typing import Any

from . import units as units_backend

UNIT_ANNOTATIONS_SCHEMA = "datalab.units.annotations.v1"
UNIT_ANNOTATIONS_SCHEMA_VERSION = 1

SUPPORTED_UNIT_MODES = {"display_only", "validate_expression"}
ACTIVE_UNIT_MODES = {"validate_expression"}
UNIT_NAMESPACES = ("inputs", "constants", "parameters", "outputs")

_TOP_LEVEL_KEYS = {
    "schema",
    "schema_version",
    "enabled",
    "mode",
    "inputs",
    "constants",
    "parameters",
    "outputs",
    "compatibility",
}
_ANNOTATION_KEYS = {"unit", "label"}
_COMPATIBILITY_KEYS = {"quantity_space", "denominator_semantics", "aggregation_model"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNIT_TEXT_RE = re.compile(r"^[A-Za-z0-9_./*^ ()%+-]+$")
_NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]+")


class UnitAnnotationError(ValueError):
    """Raised when unit annotation config is malformed or unsupported."""


def normalize_unit_annotations(
    raw: Mapping[str, Any] | None,
    *,
    allowed_symbols: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Return a closed, deterministic editable unit annotation payload."""

    if raw is None:
        return _disabled_payload()
    if not isinstance(raw, Mapping):
        raise UnitAnnotationError("unit annotations must be an object")
    _reject_json_floats(raw, path="units")

    unknown = sorted(str(key) for key in raw if key not in _TOP_LEVEL_KEYS)
    if unknown:
        raise UnitAnnotationError(f"unsupported unit annotation field: {unknown[0]}")
    if raw.get("schema", UNIT_ANNOTATIONS_SCHEMA) != UNIT_ANNOTATIONS_SCHEMA:
        raise UnitAnnotationError(f"schema must be {UNIT_ANNOTATIONS_SCHEMA!r}")
    if raw.get("schema_version", UNIT_ANNOTATIONS_SCHEMA_VERSION) != UNIT_ANNOTATIONS_SCHEMA_VERSION:
        raise UnitAnnotationError("schema_version must be 1")

    enabled = _optional_bool(raw.get("enabled"), default=False, field_name="enabled")
    mode = _optional_text(raw.get("mode"), default="display_only", field_name="mode")
    if mode not in SUPPORTED_UNIT_MODES:
        raise UnitAnnotationError(f"unsupported unit mode: {mode}")
    if enabled and mode in ACTIVE_UNIT_MODES and not units_backend.HAS_PINT:
        raise UnitAnnotationError("unit validation requires pint to be installed")

    normalized: dict[str, Any] = {
        "schema": UNIT_ANNOTATIONS_SCHEMA,
        "schema_version": UNIT_ANNOTATIONS_SCHEMA_VERSION,
        "enabled": enabled,
        "mode": mode,
    }
    allowed_lookup = _allowed_symbol_lookup(allowed_symbols)
    for namespace in UNIT_NAMESPACES:
        allowed_for_namespace = None if allowed_symbols is None else allowed_lookup.get(namespace, set())
        normalized[namespace] = _normalize_annotation_map(
            raw.get(namespace),
            namespace=namespace,
            allowed_symbols=allowed_for_namespace,
        )
    compatibility = _normalize_compatibility(raw.get("compatibility"))
    if compatibility:
        normalized["compatibility"] = compatibility
    return normalized


def normalize_display_only_family_units(
    raw: Mapping[str, Any] | None,
    *,
    family: str,
    allowed_symbols: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any] | None:
    """Normalize family unit metadata for display-only slices.

    Root solving, fitting, and statistics do not yet have reviewed active
    dimensional semantics. They may carry labels, but active validation or
    conversion must fail before a numeric calculation can silently continue.
    """

    if raw is None:
        return None
    family_name = _plain_text(family, field_name="family", max_length=64)
    if isinstance(raw, Mapping) and raw.get("enabled") is True:
        raw_mode = raw.get("mode", "display_only")
        if isinstance(raw_mode, str) and raw_mode != "display_only":
            raise UnitAnnotationError(f"{family_name} units only support display_only in this release")
    normalized = normalize_unit_annotations(raw, allowed_symbols=allowed_symbols)
    if normalized.get("enabled") and normalized.get("mode") != "display_only":
        raise UnitAnnotationError(f"{family_name} units only support display_only in this release")
    return normalized


def canonical_unit_symbol_map(
    labels: Iterable[Any],
    *,
    field_name: str = "labels",
    fallback_prefix: str = "field",
) -> dict[str, str]:
    """Map display labels to stable unit annotation identifiers.

    The unit annotation schema intentionally accepts only canonical identifiers.
    Table labels can contain spaces, punctuation, or localized text, so family
    adapters must build a deterministic symbol map before validating units.
    Collisions are rejected because guessing would attach labels to the wrong
    physical quantity.
    """

    prefix = _identifier_text(fallback_prefix, field_name="fallback_prefix")
    result: dict[str, str] = {}
    used: dict[str, str] = {}
    for index, raw_label in enumerate(labels):
        label = _plain_text(raw_label, field_name=f"{field_name}[{index}]", max_length=128)
        if label in result:
            raise UnitAnnotationError(f"{field_name}[{index}] duplicates label {label!r}")
        symbol = _canonical_symbol_from_label(label, prefix=prefix, index=index)
        previous = used.get(symbol)
        if previous is not None:
            raise UnitAnnotationError(
                f"{field_name}[{index}] collides with {previous!r} as canonical symbol {symbol!r}"
            )
        used[symbol] = label
        result[label] = symbol
    return result


def unit_annotation_text(units: Any, namespace: str, key: str) -> str:
    """Return a normalized unit string for one annotation key."""

    if not isinstance(units, Mapping):
        return ""
    annotations = units.get(str(namespace))
    if not isinstance(annotations, Mapping):
        return ""
    annotation = annotations.get(str(key))
    if isinstance(annotation, Mapping):
        value = annotation.get("unit")
    else:
        value = annotation
    return str(value or "").strip()


def first_unit_annotation_text(units: Any, namespace: str, keys: Iterable[Any]) -> str:
    """Return the first non-empty unit annotation for a list of candidate keys."""

    for key in keys:
        text = str(key or "").strip()
        if not text:
            continue
        unit = unit_annotation_text(units, namespace, text)
        if unit:
            return unit
    return ""


def unit_annotations_for_labels(
    units: Any,
    namespace: str,
    labels: Iterable[Any],
    *,
    fallback_prefix: str = "field",
    default_key: str | None = None,
) -> dict[str, str]:
    """Return display-label-to-unit mappings without changing numeric values."""

    unique_labels = list(
        dict.fromkeys(
            str(label or "").strip()
            for label in labels
            if str(label or "").strip()
        )
    )
    if not unique_labels:
        return {}

    try:
        symbol_map = canonical_unit_symbol_map(unique_labels, fallback_prefix=fallback_prefix)
    except UnitAnnotationError:
        symbol_map = {}

    default_unit = unit_annotation_text(units, namespace, default_key) if default_key else ""
    result: dict[str, str] = {}
    for label in unique_labels:
        unit = unit_annotation_text(units, namespace, label)
        if not unit:
            symbol = symbol_map.get(label)
            unit = unit_annotation_text(units, namespace, symbol) if symbol else ""
        if not unit:
            unit = default_unit
        if unit:
            result[label] = unit
    return result


def _canonical_symbol_from_label(label: str, *, prefix: str, index: int) -> str:
    symbol = _NON_IDENTIFIER_RE.sub("_", label).strip("_")
    symbol = re.sub(r"_+", "_", symbol)
    if not symbol:
        symbol = f"{prefix}_{index + 1}"
    if symbol[0].isdigit():
        symbol = f"{prefix}_{symbol}"
    if not _IDENTIFIER_RE.fullmatch(symbol):
        raise UnitAnnotationError(f"label {label!r} cannot be converted to a canonical symbol")
    return symbol


def _disabled_payload() -> dict[str, Any]:
    return {
        "schema": UNIT_ANNOTATIONS_SCHEMA,
        "schema_version": UNIT_ANNOTATIONS_SCHEMA_VERSION,
        "enabled": False,
        "mode": "display_only",
        "inputs": {},
        "constants": {},
        "parameters": {},
        "outputs": {},
    }


def _normalize_annotation_map(
    value: Any,
    *,
    namespace: str,
    allowed_symbols: set[str] | None,
) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise UnitAnnotationError(f"{namespace} annotations must be an object")
    normalized: dict[str, dict[str, str]] = {}
    for raw_key, raw_annotation in sorted(value.items(), key=lambda item: str(item[0])):
        key = _identifier_text(raw_key, field_name=f"{namespace} annotation key")
        if allowed_symbols is not None and key not in allowed_symbols:
            raise UnitAnnotationError(f"{namespace} annotation key {key!r} is not a canonical symbol")
        annotation = _normalize_single_annotation(raw_annotation, namespace=namespace, key=key)
        normalized[key] = annotation
    return normalized


def _normalize_single_annotation(value: Any, *, namespace: str, key: str) -> dict[str, str]:
    if isinstance(value, str):
        value = {"unit": value}
    if not isinstance(value, Mapping):
        raise UnitAnnotationError(f"{namespace}.{key} annotation must be an object")
    unknown = sorted(str(field) for field in value if field not in _ANNOTATION_KEYS)
    if unknown:
        raise UnitAnnotationError(f"unsupported annotation field for {namespace}.{key}: {unknown[0]}")
    unit = _unit_text(value.get("unit"), field_name=f"{namespace}.{key}.unit")
    annotation = {"unit": unit}
    label = value.get("label")
    if label is not None:
        annotation["label"] = _plain_text(label, field_name=f"{namespace}.{key}.label", max_length=128)
    return annotation


def _normalize_compatibility(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise UnitAnnotationError("compatibility must be an object")
    unknown = sorted(str(field) for field in value if field not in _COMPATIBILITY_KEYS)
    if unknown:
        raise UnitAnnotationError(f"unsupported compatibility field: {unknown[0]}")
    normalized: dict[str, str] = {}
    for key in sorted(_COMPATIBILITY_KEYS):
        if key in value:
            normalized[key] = _plain_text(value[key], field_name=f"compatibility.{key}", max_length=64)
    return normalized


def _allowed_symbol_lookup(value: Mapping[str, Iterable[str]] | None) -> dict[str, set[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise UnitAnnotationError("allowed_symbols must be an object")
    lookup: dict[str, set[str]] = {}
    for namespace, symbols in value.items():
        namespace_text = str(namespace)
        if namespace_text not in UNIT_NAMESPACES:
            raise UnitAnnotationError(f"unsupported allowed-symbol namespace: {namespace_text}")
        lookup[namespace_text] = {
            _identifier_text(symbol, field_name=f"{namespace_text} allowed symbol")
            for symbol in symbols
        }
    return lookup


def _optional_bool(value: Any, *, default: bool, field_name: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise UnitAnnotationError(f"{field_name} must be a boolean")
    return value


def _optional_text(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    return _plain_text(value, field_name=field_name, max_length=64)


def _identifier_text(value: Any, *, field_name: str) -> str:
    text = _plain_text(value, field_name=field_name, max_length=64)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise UnitAnnotationError(f"{field_name} must be a canonical identifier")
    return text


def _unit_text(value: Any, *, field_name: str) -> str:
    text = _plain_text(value, field_name=field_name, max_length=128)
    if not _UNIT_TEXT_RE.fullmatch(text):
        raise UnitAnnotationError(f"{field_name} contains unsupported unit characters")
    return text


def _plain_text(value: Any, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise UnitAnnotationError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise UnitAnnotationError(f"{field_name} must not be empty")
    if len(text) > max_length:
        raise UnitAnnotationError(f"{field_name} is too long")
    if any(ord(char) < 32 for char in text):
        raise UnitAnnotationError(f"{field_name} contains control characters")
    return text


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        raise UnitAnnotationError(f"{path} must not contain JSON floats")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_json_floats(key, path=f"{path}.<key>")
            _reject_json_floats(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")
        return
    copy.deepcopy(value)


__all__ = [
    "ACTIVE_UNIT_MODES",
    "SUPPORTED_UNIT_MODES",
    "UNIT_ANNOTATIONS_SCHEMA",
    "UNIT_ANNOTATIONS_SCHEMA_VERSION",
    "UNIT_NAMESPACES",
    "UnitAnnotationError",
    "canonical_unit_symbol_map",
    "normalize_display_only_family_units",
    "normalize_unit_annotations",
    "unit_annotation_text",
    "unit_annotations_for_labels",
]
