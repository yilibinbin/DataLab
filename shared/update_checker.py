"""GitHub Release update checks for DataLab.

The desktop GUI uses this module from its Help menu, but the code is kept Qt-free
so version comparison and network parsing remain easy to test offline.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - kept for interpreter drift
    tomllib = None  # type: ignore[assignment]


REPOSITORY_URL = "https://github.com/yilibinbin/DataLab"
RELEASES_URL = f"{REPOSITORY_URL}/releases"
LATEST_RELEASE_API_URL = "https://api.github.com/repos/yilibinbin/DataLab/releases/latest"

UpdateStatus = Literal["update-available", "up-to-date", "unavailable"]


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    browser_download_url: str


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    name: str
    version: str
    html_url: str
    body: str
    published_at: str
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class UpdateCheckResult:
    status: UpdateStatus
    current_version: str
    latest_version: str | None = None
    release: ReleaseInfo | None = None
    error: str | None = None

    @property
    def update_available(self) -> bool:
        return self.status == "update-available"


def normalize_version_tag(version_or_tag: str) -> str:
    """Return a comparable version string from tags like ``v2.0.0``."""
    text = str(version_or_tag or "").strip()
    if text.startswith("refs/tags/"):
        text = text.removeprefix("refs/tags/")
    if text[:1].lower() == "v":
        text = text[1:]
    return text.strip()


def _suffix_rank(suffix: str) -> tuple[int, int]:
    suffix = suffix.lower()
    match = re.search(r"(\d+)", suffix)
    serial = int(match.group(1)) if match else 0
    if not suffix:
        return (4, 0)
    if "post" in suffix:
        return (5, serial)
    if "rc" in suffix:
        return (3, serial)
    if "beta" in suffix or re.search(r"(^|[.\-_])b\d*", suffix):
        return (2, serial)
    if "alpha" in suffix or re.search(r"(^|[.\-_])a\d*", suffix):
        return (1, serial)
    if "dev" in suffix:
        return (0, serial)
    return (0, serial)


def _version_key(version_or_tag: str) -> tuple[int, int, int, int, int, str]:
    version = normalize_version_tag(version_or_tag).split("+", 1)[0]
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?([A-Za-z0-9.\-_]*)?$", version)
    if not match:
        return (0, 0, 0, 0, 0, version)
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    rank, serial = _suffix_rank(match.group(4) or "")
    return (major, minor, patch, rank, serial, "")


def is_newer_version(latest_version_or_tag: str, current_version_or_tag: str) -> bool:
    return _version_key(latest_version_or_tag) > _version_key(current_version_or_tag)


def current_version() -> str:
    """Return the DataLab version, preferring bundled/source metadata."""
    if tomllib is None:
        try:
            return metadata.version("datalab")
        except metadata.PackageNotFoundError:
            return "0.0.0"

    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "pyproject.toml")
    candidates.append(Path(__file__).resolve().parent.parent / "pyproject.toml")

    for pyproject in candidates:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        return str(data.get("project", {}).get("version", "0.0.0"))

    try:
        return metadata.version("datalab")
    except metadata.PackageNotFoundError:
        pass
    return "0.0.0"


def _release_from_payload(payload: dict[str, Any]) -> ReleaseInfo:
    tag_name = str(payload.get("tag_name") or "")
    assets = tuple(
        ReleaseAsset(
            name=str(asset.get("name") or ""),
            browser_download_url=str(asset.get("browser_download_url") or ""),
        )
        for asset in payload.get("assets", []) or []
        if isinstance(asset, dict)
    )
    return ReleaseInfo(
        tag_name=tag_name,
        name=str(payload.get("name") or tag_name),
        version=normalize_version_tag(tag_name),
        html_url=str(payload.get("html_url") or RELEASES_URL),
        body=str(payload.get("body") or ""),
        published_at=str(payload.get("published_at") or ""),
        assets=assets,
    )


def _urlopen(request: urllib.request.Request, *, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed GitHub API URL


def fetch_latest_release(*, timeout: float = 10.0) -> ReleaseInfo:
    """Fetch and parse the latest non-draft, non-prerelease GitHub Release."""
    request = urllib.request.Request(
        LATEST_RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DataLab Update Checker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub latest-release response is not a JSON object")
    return _release_from_payload(payload)


def check_for_updates(
    *,
    current_version: str | None = None,
    timeout: float = 10.0,
) -> UpdateCheckResult:
    """Return update status; network/API failures become ``unavailable``."""
    version = current_version if current_version is not None else globals()["current_version"]()
    try:
        release = fetch_latest_release(timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - user-facing update check should degrade gracefully
        return UpdateCheckResult(
            status="unavailable",
            current_version=version,
            error=str(exc) or type(exc).__name__,
        )

    status: UpdateStatus = (
        "update-available" if is_newer_version(release.version, version) else "up-to-date"
    )
    return UpdateCheckResult(
        status=status,
        current_version=version,
        latest_version=release.version,
        release=release,
    )
