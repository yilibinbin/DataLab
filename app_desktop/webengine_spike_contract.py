from __future__ import annotations

import json
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit


WEBENGINE_SPIKE_SCHEME = "datalab-workbench"
WEBENGINE_SPIKE_HOST = "app"
MAX_BRIDGE_PAYLOAD_BYTES = 64 * 1024
MAX_BRIDGE_PAYLOAD_DEPTH = 8

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "path",
        "file",
        "filePath",
        "filename",
        "destinationPath",
        "sourcePath",
        "command",
        "cmd",
        "shell",
        "exec",
        "executable",
        "subprocess",
        "cwd",
        "env",
    }
)


class WebEngineSecurityError(ValueError):
    """Raised when a proposed WebEngine spike bridge action violates policy."""


@dataclass(frozen=True, slots=True)
class BridgeMethodSpec:
    required_keys: frozenset[str] = frozenset()
    optional_keys: frozenset[str] = frozenset()

    @property
    def allowed_keys(self) -> frozenset[str]:
        return self.required_keys | self.optional_keys


ALLOWED_BRIDGE_METHODS = MappingProxyType(
    {
        "workspace.openDialog": BridgeMethodSpec(),
        "workspace.save": BridgeMethodSpec(optional_keys=frozenset({"snapshotId"})),
        "workspace.saveAsDialog": BridgeMethodSpec(optional_keys=frozenset({"snapshotId"})),
        "job.submit": BridgeMethodSpec(
            required_keys=frozenset({"mode", "inputs"}),
            optional_keys=frozenset({"options", "requestId"}),
        ),
        "job.cancel": BridgeMethodSpec(required_keys=frozenset({"requestId"})),
        "job.status": BridgeMethodSpec(required_keys=frozenset({"requestId"})),
        "examples.list": BridgeMethodSpec(),
        "docs.open": BridgeMethodSpec(required_keys=frozenset({"topic"})),
        "updates.check": BridgeMethodSpec(optional_keys=frozenset({"manual"})),
        "export.result": BridgeMethodSpec(
            required_keys=frozenset({"format"}),
            optional_keys=frozenset({"kind", "resultId"}),
        ),
    }
)


def build_content_security_policy() -> str:
    directives = (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'none'",
    )
    return "; ".join(directives)


def validate_navigation_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != WEBENGINE_SPIKE_SCHEME:
        raise WebEngineSecurityError(f"Unsupported WebEngine spike URL scheme: {parts.scheme!r}")
    if parts.netloc != WEBENGINE_SPIKE_HOST:
        raise WebEngineSecurityError(f"Unsupported WebEngine spike host: {parts.netloc!r}")
    if parts.query or parts.fragment:
        raise WebEngineSecurityError("Query strings and fragments are not allowed in spike asset URLs")

    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        raise WebEngineSecurityError("Spike asset URL path must be absolute and canonical")
    normalized = posixpath.normpath(path)
    if normalized == ".":
        normalized = "/"
    if normalized != path or normalized.startswith("/../") or normalized == "/..":
        raise WebEngineSecurityError("Path traversal is not allowed in spike asset URLs")
    return normalized


def validate_bridge_call(method: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    spec = ALLOWED_BRIDGE_METHODS.get(method)
    if spec is None:
        raise WebEngineSecurityError(f"Bridge method is not allowed: {method!r}")
    if not isinstance(payload, Mapping):
        raise WebEngineSecurityError("Bridge payload must be a JSON object")

    payload_keys = set(payload)
    unknown_keys = payload_keys - spec.allowed_keys
    if unknown_keys:
        raise WebEngineSecurityError(f"Unsupported payload keys for {method}: {sorted(unknown_keys)}")
    missing_keys = spec.required_keys - payload_keys
    if missing_keys:
        raise WebEngineSecurityError(f"Missing payload keys for {method}: {sorted(missing_keys)}")

    _reject_forbidden_keys(payload)
    _validate_payload_depth(payload, depth=0)
    normalized = _json_roundtrip(payload)
    _validate_method_specific_values(method, normalized)
    return normalized


def _json_roundtrip(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise WebEngineSecurityError("Bridge payload must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_BRIDGE_PAYLOAD_BYTES:
        raise WebEngineSecurityError("Bridge payload exceeds maximum size")
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - defensive after Mapping check.
        raise WebEngineSecurityError("Bridge payload must decode to a JSON object")
    return decoded


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_PAYLOAD_KEYS:
                raise WebEngineSecurityError(f"Bridge payload key is forbidden: {key}")
            _reject_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child)


def _validate_payload_depth(value: Any, *, depth: int) -> None:
    if depth > MAX_BRIDGE_PAYLOAD_DEPTH:
        raise WebEngineSecurityError("Bridge payload is too deeply nested")
    if isinstance(value, Mapping):
        for child in value.values():
            _validate_payload_depth(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_payload_depth(child, depth=depth + 1)


def _validate_method_specific_values(method: str, payload: dict[str, Any]) -> None:
    if "requestId" in payload:
        _validate_identifier("requestId", payload["requestId"])
    if method == "job.submit":
        _validate_identifier("mode", payload.get("mode"))
        if not isinstance(payload.get("inputs"), dict):
            raise WebEngineSecurityError("job.submit inputs must be a JSON object")
        options = payload.get("options")
        if options is not None and not isinstance(options, dict):
            raise WebEngineSecurityError("job.submit options must be a JSON object")
    elif method == "docs.open":
        _validate_topic(payload.get("topic"))
    elif method == "updates.check":
        manual = payload.get("manual")
        if manual is not None and not isinstance(manual, bool):
            raise WebEngineSecurityError("updates.check manual must be a boolean")
    elif method == "export.result":
        _validate_identifier("format", payload.get("format"))
        if "kind" in payload:
            _validate_identifier("kind", payload.get("kind"))
        if "resultId" in payload:
            _validate_identifier("resultId", payload.get("resultId"))
    elif method in {"workspace.save", "workspace.saveAsDialog"} and "snapshotId" in payload:
        _validate_identifier("snapshotId", payload.get("snapshotId"))


def _validate_identifier(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise WebEngineSecurityError(f"{name} must be a short non-empty string")
    if any(char in value for char in ("/", "\\", ":", "\x00")):
        raise WebEngineSecurityError(f"{name} must not contain path separators or scheme characters")


def _validate_topic(value: Any) -> None:
    _validate_identifier("topic", value)
    if value in {".", ".."} or ".." in value:
        raise WebEngineSecurityError("topic must not contain path traversal")


__all__ = [
    "ALLOWED_BRIDGE_METHODS",
    "BridgeMethodSpec",
    "FORBIDDEN_PAYLOAD_KEYS",
    "MAX_BRIDGE_PAYLOAD_BYTES",
    "MAX_BRIDGE_PAYLOAD_DEPTH",
    "WEBENGINE_SPIKE_HOST",
    "WEBENGINE_SPIKE_SCHEME",
    "WebEngineSecurityError",
    "build_content_security_policy",
    "validate_bridge_call",
    "validate_navigation_url",
]
