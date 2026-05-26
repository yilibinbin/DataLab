"""Update payload manifest validation for installer-based DataLab updates.

This module stays Qt-free so installer metadata and downloads can be tested
without GUI dependencies. Installer launch remains a desktop-layer concern.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit

from shared.update_checker import ReleaseInfo, is_newer_version, normalize_version_tag


UPDATES_MANIFEST_NAME = "updates.json"
MANIFEST_MAX_BYTES = 64 * 1024
MAX_INSTALLER_BYTES = 750 * 1024 * 1024
DEFAULT_DOWNLOAD_TIMEOUT = 30.0
DEFAULT_STALL_TIMEOUT = 30.0

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_PLATFORM_SUFFIXES = {
    "macos": ".pkg",
    "windows-x64": ".exe",
}
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


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


def _split_release_url(url: str) -> SplitResult:
    parts = urlsplit(str(url or "").strip())
    if parts.scheme.lower() != "https":
        raise UpdatePayloadError("release_url must use https")
    if parts.query or parts.fragment:
        raise UpdatePayloadError("release_url must not include query or fragment")
    return parts


def _validate_release_url(manifest_url: str, release_url: str) -> str:
    manifest_parts = _split_release_url(manifest_url)
    release_parts = _split_release_url(release_url)
    if (
        manifest_parts.netloc.lower(),
        manifest_parts.path.rstrip("/"),
    ) != (
        release_parts.netloc.lower(),
        release_parts.path.rstrip("/"),
    ):
        raise UpdatePayloadError("release_url does not match GitHub release")
    return release_url


def _validate_asset_name(platform_key: str, name: str) -> None:
    _validate_asset_basename(name)
    suffix = _PLATFORM_SUFFIXES.get(platform_key)
    if suffix is not None and not name.lower().endswith(suffix):
        raise UpdatePayloadError(f"asset suffix must be {suffix} for {platform_key}")


def _validate_asset_basename(name: str) -> None:
    if not name or name != name.strip():
        raise UpdatePayloadError("asset name is invalid")
    if name in {".", ".."} or "/" in name or "\\" in name or Path(name).is_absolute():
        raise UpdatePayloadError("asset name is invalid")
    if _CONTROL_CHARS_RE.search(name):
        raise UpdatePayloadError("asset name is invalid")


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


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


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
    if min_client and is_newer_version(min_client, current_version):
        raise UpdatePayloadError("client is too old for this update")

    release_url_value = manifest.get("release_url")
    release_url = release.html_url
    if release_url_value is not None:
        release_url = _validate_release_url(str(release_url_value), release.html_url)

    assets = manifest.get("assets")
    if not isinstance(assets, dict) or platform_key not in assets:
        raise UpdatePayloadError(f"platform asset missing: {platform_key}")

    asset_data = assets[platform_key]
    if not isinstance(asset_data, dict):
        raise UpdatePayloadError(f"platform asset must be an object: {platform_key}")

    name = str(asset_data.get("name") or "")
    _validate_asset_name(platform_key, name)

    sha256 = str(asset_data.get("sha256") or "")
    if not _SHA256_RE.fullmatch(sha256):
        raise UpdatePayloadError("sha256 must be 64 hexadecimal characters")

    raw_size = asset_data.get("size_bytes")
    if not isinstance(raw_size, int) or isinstance(raw_size, bool):
        raise UpdatePayloadError("size_bytes must be an integer")
    size_bytes = raw_size
    if size_bytes <= 0 or size_bytes > MAX_INSTALLER_BYTES:
        raise UpdatePayloadError("size_bytes is outside the allowed range")

    url = _asset_url_by_name(release, name)
    return UpdatePayload(
        version=version,
        notes=str(manifest.get("notes") or release.body),
        published_at=str(manifest.get("published_at") or release.published_at),
        release_url=release_url,
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(_DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installer_file(path: Path, asset: InstallerAsset) -> None:
    if not path.is_file():
        raise UpdatePayloadError(f"installer not found: {path}")
    size_bytes = path.stat().st_size
    if size_bytes != asset.size_bytes:
        raise UpdatePayloadError(f"size mismatch: expected {asset.size_bytes}, got {size_bytes}")
    if sha256_file(path).lower() != asset.sha256.lower():
        raise UpdatePayloadError("sha256 mismatch")


def _safe_target_path(cache_dir: Path, name: str) -> Path:
    _validate_asset_basename(name)
    return cache_dir / name


def download_and_verify_installer(
    asset: InstallerAsset,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
) -> Path:
    if asset.size_bytes <= 0 or asset.size_bytes > MAX_INSTALLER_BYTES:
        raise UpdatePayloadError("size_bytes is outside the allowed range")

    cache_dir = update_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = _safe_target_path(cache_dir, asset.name)
    partial = target.with_name(f"{target.name}.part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": "DataLab Update Checker"})

    try:
        bytes_written = 0
        with _urlopen(request, timeout) as response:
            with partial.open("wb") as file:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > MAX_INSTALLER_BYTES:
                        raise UpdatePayloadError("installer exceeds maximum size")
                    file.write(chunk)

        if bytes_written != asset.size_bytes:
            raise UpdatePayloadError(f"size mismatch: expected {asset.size_bytes}, got {bytes_written}")
        verify_installer_file(partial, asset)
        partial.replace(target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def fetch_manifest_for_release(
    release: ReleaseInfo,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
) -> dict[str, Any]:
    url = find_manifest_asset_url(release)
    request = urllib.request.Request(url, headers={"User-Agent": "DataLab Update Checker"})
    with _urlopen(request, timeout) as response:
        return loads_manifest(response.read(MANIFEST_MAX_BYTES + 1))


def resolve_update_payload_for_release(
    release: ReleaseInfo,
    current_version: str,
    platform_key: str | None = None,
) -> UpdatePayload:
    manifest = fetch_manifest_for_release(release)
    return select_update_payload(
        release=release,
        manifest=manifest,
        platform_key=platform_key or current_platform_key(),
        current_version=current_version,
    )


class UpdateCacheLock:
    def __init__(self, stale_after_seconds: int = 6 * 60 * 60) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._path = update_cache_dir() / ".update.lock"
        self._acquired = False

    def __enter__(self) -> UpdateCacheLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            age_seconds = time.time() - self._path.stat().st_mtime
            if age_seconds <= self._stale_after_seconds:
                raise UpdatePayloadError("update already in progress")
            self._path.unlink(missing_ok=True)

        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise UpdatePayloadError("update already in progress") from exc

        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(str(os.getpid()))
        self._acquired = True
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        if self._acquired:
            self._path.unlink(missing_ok=True)
            self._acquired = False
        return False
