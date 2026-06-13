from __future__ import annotations

import hashlib
import json
import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app_desktop.webengine_spike_contract import (
    WEBENGINE_SPIKE_HOST,
    WEBENGINE_SPIKE_SCHEME,
    WebEngineSecurityError,
    validate_navigation_url,
)


WEBENGINE_ASSET_ROOT = "app_desktop/webengine_assets"


class WebEngineAssetError(ValueError):
    """Raised when a future embedded WebEngine asset manifest is unsafe."""


@dataclass(frozen=True, slots=True)
class WebEngineAssetSpec:
    path: str
    sha256: str | None = None
    bytes: int | None = None
    kind: str = "asset"


@dataclass(frozen=True, slots=True)
class WebEngineAssetEvidence:
    asset_root: str
    specs: tuple[WebEngineAssetSpec, ...]


REQUIRED_WEBENGINE_ASSETS = (
    WebEngineAssetSpec("index.html", kind="entrypoint"),
    WebEngineAssetSpec("app/workbench.css", kind="style"),
    WebEngineAssetSpec("app/workbench.js", kind="script"),
    WebEngineAssetSpec("vendor/katex/katex.min.css", kind="style"),
    WebEngineAssetSpec("vendor/katex/katex.min.js", kind="script"),
    WebEngineAssetSpec("vendor/katex/fonts/KaTeX_Main-Regular.woff2", kind="font"),
)

ALLOWED_ASSET_EVIDENCE_STATUSES = frozenset(
    {
        "missing",
        "provided",
        "not_file",
        "missing_integrity",
        "integrity_mismatch",
    }
)


def validate_asset_manifest(specs: Iterable[WebEngineAssetSpec]) -> tuple[WebEngineAssetSpec, ...]:
    normalized: list[WebEngineAssetSpec] = []
    seen: set[str] = set()
    for spec in specs:
        path = _normalize_asset_path(spec.path)
        if path in seen:
            raise WebEngineAssetError(f"Duplicate WebEngine spike asset path: {path}")
        seen.add(path)
        _validate_integrity_metadata(spec)
        normalized.append(
            WebEngineAssetSpec(
                path,
                sha256=spec.sha256.lower() if spec.sha256 is not None else None,
                bytes=spec.bytes,
                kind=spec.kind,
            )
        )
    return tuple(normalized)


def inspect_offline_assets(
    repo_root: Path,
    *,
    specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
    asset_root: str = WEBENGINE_ASSET_ROOT,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    asset_root_path = _normalize_asset_path(asset_root)
    base_dir = (root / Path(*asset_root_path.split("/"))).resolve(strict=False)
    _require_under_root(base_dir, root)

    rows = [
        _inspect_asset(base_dir, spec)
        for spec in validate_asset_manifest(specs)
    ]
    provided_count = sum(row["status"] == "provided" for row in rows)
    missing_count = sum(row["status"] == "missing" for row in rows)
    invalid_count = len(rows) - provided_count - missing_count
    return {
        "asset_root": asset_root_path,
        "runtime_network_allowed": False,
        "required_count": len(rows),
        "provided_count": provided_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "passed": bool(rows) and provided_count == len(rows) and invalid_count == 0,
        "assets": rows,
    }


def build_asset_evidence_template(
    *,
    generated_at: str | None = None,
    specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
    asset_root: str = WEBENGINE_ASSET_ROOT,
) -> dict[str, Any]:
    timestamp = _timestamp(generated_at)
    asset_root_path = _normalize_asset_path(asset_root)
    return {
        "generated_at": timestamp,
        "asset_root": asset_root_path,
        "assets": [
            {
                "path": spec.path,
                "kind": spec.kind,
                "status": "missing",
            }
            for spec in validate_asset_manifest(specs)
        ],
    }


def build_materialized_asset_manifest(
    repo_root: Path,
    *,
    generated_at: str | None = None,
    specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
    asset_root: str = WEBENGINE_ASSET_ROOT,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    asset_root_path = _normalize_asset_path(asset_root)
    base_dir = (root / Path(*asset_root_path.split("/"))).resolve(strict=False)
    _require_under_root(base_dir, root)

    rows = []
    for spec in validate_asset_manifest(specs):
        row = {
            "path": spec.path,
            "kind": spec.kind,
            "status": "missing",
        }
        path = (base_dir / Path(*spec.path.split("/"))).resolve(strict=False)
        _require_under_root(path, base_dir)
        if path.is_file():
            data = path.read_bytes()
            row.update(
                {
                    "status": "provided",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )
        elif path.exists():
            row["status"] = "not_file"
        rows.append(row)
    return {
        "generated_at": _timestamp(generated_at),
        "asset_root": asset_root_path,
        "assets": rows,
    }


def load_asset_evidence(
    path: Path,
    *,
    required_specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
) -> WebEngineAssetEvidence:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WebEngineAssetError("WebEngine asset evidence payload must be a JSON object")

    asset_root = _normalize_asset_path(payload.get("asset_root", WEBENGINE_ASSET_ROOT))
    rows = payload.get("assets")
    if not isinstance(rows, list):
        raise WebEngineAssetError("WebEngine asset evidence must contain an assets list")

    required = validate_asset_manifest(required_specs)
    required_by_path = {spec.path: spec for spec in required}
    specs_by_path: dict[str, WebEngineAssetSpec] = {}
    for index, row in enumerate(rows):
        spec = _asset_spec_from_evidence_row(
            row,
            index=index,
            required_by_path=required_by_path,
        )
        if spec.path in specs_by_path:
            raise WebEngineAssetError(f"Duplicate WebEngine asset evidence row: {spec.path}")
        specs_by_path[spec.path] = spec

    missing = [spec.path for spec in required if spec.path not in specs_by_path]
    if missing:
        raise WebEngineAssetError(
            "WebEngine asset evidence manifest must cover every required asset path; "
            f"missing: {', '.join(missing)}"
        )

    return WebEngineAssetEvidence(
        asset_root=asset_root,
        specs=validate_asset_manifest(specs_by_path[spec.path] for spec in required),
    )


def build_asset_serving_contract_summary(
    *,
    specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
    asset_root: str = WEBENGINE_ASSET_ROOT,
) -> dict[str, Any]:
    manifest = validate_asset_manifest(specs)
    return {
        "scheme": WEBENGINE_SPIKE_SCHEME,
        "host": WEBENGINE_SPIKE_HOST,
        "entrypoint_url": f"{WEBENGINE_SPIKE_SCHEME}://{WEBENGINE_SPIKE_HOST}/",
        "asset_root": _normalize_asset_path(asset_root),
        "url_validation": "app_desktop.webengine_spike_contract.validate_navigation_url",
        "strict_manifest_only": True,
        "requires_integrity": True,
        "required_paths": [spec.path for spec in manifest],
    }


def resolve_asset_url(
    repo_root: Path,
    url: str,
    *,
    specs: Iterable[WebEngineAssetSpec] = REQUIRED_WEBENGINE_ASSETS,
    asset_root: str = WEBENGINE_ASSET_ROOT,
) -> dict[str, Any]:
    relative_path = _relative_asset_path_from_url(url)
    manifest = {spec.path: spec for spec in validate_asset_manifest(specs)}
    spec = manifest.get(relative_path)
    if spec is None:
        raise WebEngineAssetError(f"URL is not listed in the WebEngine spike asset manifest: {url!r}")

    root = Path(repo_root).resolve()
    asset_root_path = _normalize_asset_path(asset_root)
    base_dir = (root / Path(*asset_root_path.split("/"))).resolve(strict=False)
    _require_under_root(base_dir, root)

    row = _inspect_asset(base_dir, spec)
    if row["status"] != "provided":
        raise WebEngineAssetError(
            f"WebEngine spike asset is not available for serving: {relative_path} ({row['status']})"
        )
    return {
        "relative_path": relative_path,
        "filesystem_path": str((base_dir / Path(*relative_path.split("/"))).resolve(strict=False)),
        "content_type": _content_type_for_asset(relative_path, spec.kind),
        "sha256": row["sha256"],
        "bytes": row["bytes"],
        "kind": spec.kind,
    }


def _inspect_asset(base_dir: Path, spec: WebEngineAssetSpec) -> dict[str, Any]:
    path = base_dir / Path(*spec.path.split("/"))
    resolved = path.resolve(strict=False)
    _require_under_root(resolved, base_dir)

    row: dict[str, Any] = {
        "path": spec.path,
        "kind": spec.kind,
        "status": "missing",
        "expected_sha256": spec.sha256,
        "expected_bytes": spec.bytes,
    }
    if not resolved.exists():
        return row
    if not resolved.is_file():
        row["status"] = "not_file"
        return row

    data = resolved.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    actual_bytes = len(data)
    row.update({"sha256": actual_sha256, "bytes": actual_bytes})

    missing_integrity = [
        name
        for name, value in (
            ("sha256", spec.sha256),
            ("bytes", spec.bytes),
        )
        if value is None
    ]
    if missing_integrity:
        row["status"] = "missing_integrity"
        row["missing_integrity"] = missing_integrity
        return row

    mismatches = []
    if spec.sha256 != actual_sha256:
        mismatches.append("sha256")
    if spec.bytes != actual_bytes:
        mismatches.append("bytes")
    if mismatches:
        row["status"] = "integrity_mismatch"
        row["mismatches"] = mismatches
        return row

    row["status"] = "provided"
    return row


def _asset_spec_from_evidence_row(
    row: Any,
    *,
    index: int,
    required_by_path: dict[str, WebEngineAssetSpec],
) -> WebEngineAssetSpec:
    if not isinstance(row, dict):
        raise WebEngineAssetError(f"WebEngine asset evidence row {index} must be a JSON object")

    path_value = row.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise WebEngineAssetError(f"WebEngine asset evidence row {index} must have a non-empty path")
    path = _normalize_asset_path(path_value)
    required = required_by_path.get(path)
    if required is None:
        raise WebEngineAssetError(f"WebEngine asset evidence row {index} contains unknown asset path: {path}")

    status = row.get("status")
    if status not in ALLOWED_ASSET_EVIDENCE_STATUSES:
        raise WebEngineAssetError(f"Invalid WebEngine asset evidence status for {path}: {status!r}")

    kind = row.get("kind", required.kind)
    if kind != required.kind:
        raise WebEngineAssetError(
            f"WebEngine asset evidence kind for {path} must be {required.kind!r}, got {kind!r}"
        )

    sha256 = row.get("sha256")
    bytes_value = row.get("bytes")
    if status == "provided":
        if sha256 is None or bytes_value is None:
            raise WebEngineAssetError(f"Provided WebEngine asset evidence for {path} requires sha256 and bytes")
        if not isinstance(sha256, str):
            raise WebEngineAssetError(f"Invalid sha256 metadata for {path!r}")
        if not isinstance(bytes_value, int) or isinstance(bytes_value, bool):
            raise WebEngineAssetError(f"Invalid byte-size metadata for {path!r}")
        return WebEngineAssetSpec(path, sha256=sha256, bytes=bytes_value, kind=kind)

    if sha256 is not None or bytes_value is not None:
        raise WebEngineAssetError(
            f"Non-provided WebEngine asset evidence row for {path} must not include integrity metadata"
        )
    return WebEngineAssetSpec(path, kind=kind)


def _timestamp(generated_at: str | None) -> str:
    if generated_at is not None:
        return generated_at
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_asset_path_from_url(url: str) -> str:
    try:
        path = validate_navigation_url(url)
    except WebEngineSecurityError as exc:
        raise WebEngineAssetError(str(exc)) from exc
    if path == "/":
        return "index.html"
    return _normalize_asset_path(path.removeprefix("/"))


def _content_type_for_asset(path: str, kind: str) -> str:
    suffix = Path(path).suffix.lower()
    if kind == "entrypoint" or suffix == ".html":
        return "text/html; charset=utf-8"
    if kind == "style" or suffix == ".css":
        return "text/css; charset=utf-8"
    if kind == "script" or suffix == ".js":
        return "text/javascript; charset=utf-8"
    if kind == "font" or suffix == ".woff2":
        return "font/woff2"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".png":
        return "image/png"
    return "application/octet-stream"


def _normalize_asset_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise WebEngineAssetError("WebEngine spike asset path must be a non-empty string")
    if "\\" in path or "\x00" in path or "%" in path:
        raise WebEngineAssetError(f"Unsafe WebEngine spike asset path: {path!r}")
    if path.startswith("/") or path.startswith("//"):
        raise WebEngineAssetError(f"Asset path must be relative: {path!r}")

    parts = urlsplit(path)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise WebEngineAssetError(f"Asset path must be a plain relative path: {path!r}")
    if any(ord(char) < 32 for char in path):
        raise WebEngineAssetError(f"Asset path contains control characters: {path!r}")

    normalized = posixpath.normpath(path)
    if normalized in {".", ".."} or normalized.startswith("../"):
        raise WebEngineAssetError(f"Path traversal is not allowed: {path!r}")
    if normalized != path:
        raise WebEngineAssetError(f"Asset path must be normalized: {path!r}")
    return normalized


def _validate_integrity_metadata(spec: WebEngineAssetSpec) -> None:
    if spec.sha256 is not None:
        lowered = spec.sha256.lower()
        if len(lowered) != 64 or any(char not in "0123456789abcdef" for char in lowered):
            raise WebEngineAssetError(f"Invalid sha256 metadata for {spec.path!r}")
    if spec.bytes is not None and spec.bytes < 0:
        raise WebEngineAssetError(f"Invalid byte-size metadata for {spec.path!r}")


def _require_under_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WebEngineAssetError(f"Resolved asset path escapes asset root: {path}") from exc


__all__ = [
    "REQUIRED_WEBENGINE_ASSETS",
    "WEBENGINE_ASSET_ROOT",
    "WebEngineAssetError",
    "WebEngineAssetEvidence",
    "WebEngineAssetSpec",
    "build_asset_evidence_template",
    "build_asset_serving_contract_summary",
    "build_materialized_asset_manifest",
    "inspect_offline_assets",
    "load_asset_evidence",
    "resolve_asset_url",
    "validate_asset_manifest",
]
