"""Update payload manifest validation for installer-based DataLab updates.

This module stays Qt-free so installer metadata can be tested without GUI
dependencies. It validates release metadata only; download, hashing, locking,
and installer launch are intentionally left to later tasks.
"""

from __future__ import annotations

import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from shared.update_checker import ReleaseInfo, normalize_version_tag


UPDATES_MANIFEST_NAME = "updates.json"
MANIFEST_MAX_BYTES = 64 * 1024
MAX_INSTALLER_BYTES = 750 * 1024 * 1024
DEFAULT_DOWNLOAD_TIMEOUT = 30.0
DEFAULT_STALL_TIMEOUT = 30.0

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class UpdatePayloadError(ValueError):
    """Raised when update payload metadata is missing, unsafe, or unsupported."""


@dataclass(frozen=True)
class InstallerAsset:
    platform_key: str
    name: str
    url: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class UpdatePayload:
    version: str
    notes: str
    published_at: str
    release_url: str
    asset: InstallerAsset


def current_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return "macos"
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return "windows-x64"
    raise UpdatePayloadError(f"unsupported platform: {system}/{machine}")


def _norm_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def _version_key(version: str) -> tuple[int, int, int]:
    parts = normalize_version_tag(version).split(".")
    values: list[int] = []
    for part in parts[:3]:
        match = re.match(r"^(\d+)", part)
        values.append(int(match.group(1)) if match else 0)
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def _asset_url_by_name(release: ReleaseInfo, name: str) -> str:
    for asset in release.assets:
        if asset.name == name:
            return asset.browser_download_url
    raise UpdatePayloadError(f"asset not found in release: {name}")


def find_manifest_asset_url(release: ReleaseInfo) -> str:
    return _asset_url_by_name(release, UPDATES_MANIFEST_NAME)


def loads_manifest(raw: bytes) -> dict[str, Any]:
    if len(raw) > MANIFEST_MAX_BYTES:
        raise UpdatePayloadError("updates.json exceeds size limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdatePayloadError(f"invalid updates.json: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdatePayloadError("updates.json must be an object")
    return data


def select_update_payload(
    *,
    release: ReleaseInfo,
    manifest: dict[str, Any],
    platform_key: str,
    current_version: str,
) -> UpdatePayload:
    if manifest.get("schema_version") != 1:
        raise UpdatePayloadError("unsupported schema_version")

    version = normalize_version_tag(str(manifest.get("version") or ""))
    if version != normalize_version_tag(release.tag_name):
        raise UpdatePayloadError("manifest version does not match release tag")

    min_client = str(manifest.get("min_client_version") or "").strip()
    if min_client and _version_key(current_version) < _version_key(min_client):
        raise UpdatePayloadError("client is too old for this update")

    release_url_value = manifest.get("release_url")
    if release_url_value is not None and _norm_url(str(release_url_value)) != _norm_url(
        release.html_url
    ):
        raise UpdatePayloadError("release_url does not match GitHub release")

    assets = manifest.get("assets")
    if not isinstance(assets, dict) or platform_key not in assets:
        raise UpdatePayloadError(f"platform asset missing: {platform_key}")

    asset_data = assets[platform_key]
    if not isinstance(asset_data, dict):
        raise UpdatePayloadError(f"platform asset must be an object: {platform_key}")

    name = str(asset_data.get("name") or "")
    sha256 = str(asset_data.get("sha256") or "")
    if not _SHA256_RE.fullmatch(sha256):
        raise UpdatePayloadError("sha256 must be 64 hexadecimal characters")

    try:
        size_bytes = int(asset_data.get("size_bytes"))
    except (TypeError, ValueError) as exc:
        raise UpdatePayloadError("size_bytes must be an integer") from exc
    if size_bytes <= 0 or size_bytes > MAX_INSTALLER_BYTES:
        raise UpdatePayloadError("size_bytes is outside the allowed range")

    url = _asset_url_by_name(release, name)
    return UpdatePayload(
        version=version,
        notes=str(manifest.get("notes") or release.body),
        published_at=str(manifest.get("published_at") or release.published_at),
        release_url=release.html_url,
        asset=InstallerAsset(
            platform_key=platform_key,
            name=name,
            url=url,
            sha256=sha256,
            size_bytes=size_bytes,
        ),
    )


def update_cache_dir() -> Path:
    if platform.system().lower() == "darwin":
        return Path.home() / "Library" / "Caches" / "DataLab" / "Updates"
    if platform.system().lower() == "windows":
        root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(root) / "DataLab" / "Updates"
    return Path(tempfile.gettempdir()) / "DataLab" / "Updates"
