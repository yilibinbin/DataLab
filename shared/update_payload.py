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
import ssl
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit

try:
    import certifi
except ModuleNotFoundError:  # pragma: no cover - source installs may rely on system CA
    certifi = None  # type: ignore[assignment]

from shared.update_checker import ReleaseInfo, is_newer_version, normalize_version_tag
from shared.update_signing import (
    UpdateSignatureError,
    has_installable_assets,
    verify_manifest_signature,
)


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
_LOCK_ACQUIRE_ATTEMPTS = 5


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
class DownloadProgress:
    downloaded_bytes: int
    total_bytes: int
    elapsed_seconds: float

    @property
    def fraction(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, max(0.0, self.downloaded_bytes / self.total_bytes))

    @property
    def bytes_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.downloaded_bytes / self.elapsed_seconds


@dataclass(frozen=True)
class UpdatePayload:
    version: str
    notes: str
    published_at: str
    release_url: str
    asset: InstallerAsset


@dataclass(frozen=True)
class _LockSnapshot:
    st_dev: int
    st_ino: int
    st_mtime_ns: int
    content: bytes


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
    # Use certifi's CA bundle like update_checker does, so HTTPS verification
    # works on frozen builds whose default OpenSSL context has no system CA store
    # (otherwise the check path advertises an update the download path can never
    # fetch — audit F8). Integrity is still SHA-256/size-pinned downstream.
    context = ssl.create_default_context(cafile=certifi.where() if certifi is not None else None)
    return urllib.request.urlopen(request, timeout=timeout, context=context)  # noqa: S310


def select_update_payload(
    *,
    release: ReleaseInfo,
    manifest: dict[str, Any],
    platform_key: str,
    current_version: str,
) -> UpdatePayload:
    if manifest.get("schema_version") != 1:
        raise UpdatePayloadError("unsupported schema_version")
    try:
        verify_manifest_signature(
            manifest,
            require_signature=has_installable_assets(manifest),
        )
    except UpdateSignatureError as exc:
        raise UpdatePayloadError(str(exc)) from exc

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


def _notify_download_progress(
    progress_callback: Callable[[DownloadProgress], None] | None,
    progress: DownloadProgress,
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(progress)
    except Exception:
        # Progress callbacks are best-effort; payload validity is checked by
        # byte count and hash verification below.
        return


def download_and_verify_installer(
    asset: InstallerAsset,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    *,
    progress_callback: Callable[[DownloadProgress], None] | None = None,
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
        started_at = time.monotonic()
        with _urlopen(request, timeout) as response:
            with partial.open("wb") as file:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    next_size = bytes_written + len(chunk)
                    if next_size > asset.size_bytes:
                        raise UpdatePayloadError(
                            f"size mismatch: expected {asset.size_bytes}, got more than {asset.size_bytes}"
                        )
                    if next_size > MAX_INSTALLER_BYTES:
                        raise UpdatePayloadError("installer exceeds maximum size")
                    bytes_written = next_size
                    file.write(chunk)
                    _notify_download_progress(
                        progress_callback,
                        DownloadProgress(
                            downloaded_bytes=bytes_written,
                            total_bytes=asset.size_bytes,
                            elapsed_seconds=max(time.monotonic() - started_at, 0.0),
                        ),
                    )

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


def _read_lock_snapshot(path: Path) -> _LockSnapshot:
    stat_result = path.stat()
    return _LockSnapshot(
        st_dev=stat_result.st_dev,
        st_ino=stat_result.st_ino,
        st_mtime_ns=stat_result.st_mtime_ns,
        content=path.read_bytes(),
    )


def _same_lock_snapshot(left: _LockSnapshot, right: _LockSnapshot) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mtime_ns,
        left.content,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mtime_ns,
        right.content,
    )


class UpdateCacheLock:
    def __init__(self, stale_after_seconds: int = 6 * 60 * 60) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._path = update_cache_dir() / ".update.lock"
        self._acquired = False
        self._token = f"{os.getpid()}:{time.time_ns()}"

    def __enter__(self) -> UpdateCacheLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(_LOCK_ACQUIRE_ATTEMPTS):
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                try:
                    observed = _read_lock_snapshot(self._path)
                except FileNotFoundError:
                    continue

                age_seconds = time.time() - (observed.st_mtime_ns / 1_000_000_000)
                if age_seconds <= self._stale_after_seconds:
                    raise UpdatePayloadError("update already in progress") from exc

                try:
                    current = _read_lock_snapshot(self._path)
                except FileNotFoundError:
                    continue
                if not _same_lock_snapshot(observed, current):
                    raise UpdatePayloadError("update already in progress") from exc

                age_seconds = time.time() - (current.st_mtime_ns / 1_000_000_000)
                if age_seconds <= self._stale_after_seconds:
                    raise UpdatePayloadError("update already in progress") from exc

                try:
                    self._path.unlink()
                except FileNotFoundError:
                    continue
                continue
            break
        else:
            raise UpdatePayloadError("update already in progress")

        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(self._token)
        self._acquired = True
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        if self._acquired:
            self._path.unlink(missing_ok=True)
            self._acquired = False
        return False
