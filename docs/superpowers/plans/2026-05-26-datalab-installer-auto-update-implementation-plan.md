# DataLab Installer Auto Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build DataLab's confirmed installer-based update flow: opt-in/manual checks, `updates.json` metadata, installer download with size/SHA-256 verification, code-owned installer commands, update dialogs, and macOS/Windows release asset generation.

**Architecture:** Keep GitHub release lookup in `shared.update_checker`, add one Qt-free `shared.update_payload` module for manifest lookup/validation/download/hash/cache locking, add `app_desktop.update_installer` for platform command construction and launch, and add `app_desktop.update_controller` for UI state, preferences, dialogs, and startup checks. Packaging scripts produce installer artifacts and `updates.json`; auto-install only runs when metadata, hash, size, and platform requirements pass.

**Tech Stack:** Python 3, PySide6, QSettings, urllib, hashlib, file locking with atomic lock files, pytest, PyInstaller, `pkgbuild`/`productbuild`, Inno Setup.

---

## Scope And Sequencing

This plan supersedes `docs/superpowers/plans/2026-05-26-datalab-update-check-improvements.md`. That earlier plan covered an update-checker prompt; this plan implements the confirmed installer-based updater from `docs/superpowers/specs/2026-05-26-datalab-installer-auto-update-design.md`.

First implementation target is a fully tested updater core that is safe even before signed production certificates exist. If signing/notarization assets are not available in the local environment, packaging tasks must still generate unsigned artifacts for test builds but mark them as non-auto-installable unless the signing gate passes.

## File Structure

- Modify `shared/update_checker.py`
  - Add `size` to `ReleaseAsset`.
  - Add safe release-note formatting used by dialogs.
- Create `shared/update_payload.py`
  - Parse and validate `updates.json`.
  - Select platform asset.
  - Fetch manifest only from GitHub release asset list.
  - Download installer with size cap and timeout.
  - Verify size and SHA-256.
  - Manage update cache path and lock file.
- Modify `shared/settings_store.py`
  - Add `Update/` namespace and typed bool/string helpers.
  - Add update preference/state/cache keys.
- Create `shared/update_preferences.py`
  - Persist opt-in, skipped version, last checked timestamp, last seen version, cached release notes.
  - Implement 24-hour throttle and clock-skew behavior.
- Create `app_desktop/update_installer.py`
  - Construct platform installer commands in code.
  - Reject wrong extensions and remote-controlled argv.
  - Re-verify size/SHA-256 immediately before launch.
- Create `app_desktop/update_dialogs.py`
  - Build bilingual plain-text update, failure, skipped-version, and post-update messages.
- Create `app_desktop/update_controller.py`
  - Implement update state machine and UI orchestration.
  - Keep automatic offline failures quiet.
  - Prevent re-entrant checks/downloads in one process.
- Modify `app_desktop/panels.py`
  - Add Help menu `自动更新` / `Automatic Updates` checkable action.
- Modify `app_desktop/window.py`
  - Instantiate controller, delegate update actions, schedule startup check.
- Create `tools/generate_updates_manifest.py`
  - Generate `updates.json` from built installer assets, version, release URL, and notes.
- Modify `build_mac_data_gui.sh`
  - Add optional `.pkg` build step and manifest generation hook.
- Modify `build_windows_data_gui.ps1`
  - Add optional Inno Setup packaging and manifest generation hook.
- Create `packaging/windows/DataLab.iss`
  - Inno Setup installer script with safe close/restart behavior.
- Modify `CHANGELOG.md`
  - Add public-facing note for installer-based updater once implementation is complete.

## Task 1: Extend GitHub Release Metadata

**Files:**
- Modify: `shared/update_checker.py`
- Modify: `tests/test_update_checker.py`

- [ ] **Step 1: Add failing test for release asset size and release-note formatting**

Append to `tests/test_update_checker.py`:

```python
def test_fetch_latest_release_parses_asset_size(monkeypatch) -> None:
    from shared import update_checker

    def fake_urlopen(request, *, timeout):
        return _fake_response(
            {
                "tag_name": "v2.3.0",
                "name": "DataLab v2.3.0",
                "html_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
                "body": "Release notes",
                "published_at": "2026-05-26T00:00:00Z",
                "assets": [
                    {
                        "name": "updates.json",
                        "browser_download_url": "https://example.invalid/updates.json",
                        "size": 1024,
                    }
                ],
            }
        )

    monkeypatch.setattr(update_checker, "_urlopen", fake_urlopen)

    release = update_checker.fetch_latest_release(timeout=3)

    assert release.assets[0].name == "updates.json"
    assert release.assets[0].size == 1024


def test_format_release_notes_for_dialog_plain_text_and_truncates() -> None:
    from shared.update_checker import format_release_notes_for_dialog

    body = "# Changes\n<script>alert(1)</script>\nFixed <b>updates</b>\n" + ("x" * 5000)

    formatted = format_release_notes_for_dialog(body, max_chars=80)

    assert "<script>" not in formatted
    assert "<b>" not in formatted
    assert "Fixed updates" in formatted
    assert len(formatted) <= 80
    assert formatted.endswith("...")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/test_update_checker.py::test_fetch_latest_release_parses_asset_size tests/test_update_checker.py::test_format_release_notes_for_dialog_plain_text_and_truncates
```

Expected: FAIL because `ReleaseAsset.size` and `format_release_notes_for_dialog` do not exist.

- [ ] **Step 3: Implement release asset size and formatter**

In `shared/update_checker.py`, add imports:

```python
import html
```

Update `ReleaseAsset`:

```python
@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    browser_download_url: str
    size: int = 0
```

Update `_release_from_payload` asset construction:

```python
        ReleaseAsset(
            name=str(asset.get("name") or ""),
            browser_download_url=str(asset.get("browser_download_url") or ""),
            size=int(asset.get("size") or 0),
        )
```

Add formatter after `_release_from_payload`:

```python
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def format_release_notes_for_dialog(body: str, *, max_chars: int = 4000) -> str:
    text = html.unescape(body or "")
    text = _HTML_TAG_RE.sub("", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = "\n".join(lines).strip()
    if not text:
        return "No release notes were provided."
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest -q tests/test_update_checker.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/update_checker.py tests/test_update_checker.py
git commit -m "feat: parse update release assets"
```

## Task 2: Update Payload Manifest Validation

**Files:**
- Create: `shared/update_payload.py`
- Create: `tests/test_update_payload.py`

- [ ] **Step 1: Write failing manifest validation tests**

Create `tests/test_update_payload.py`:

```python
from __future__ import annotations

import json

import pytest

from shared.update_checker import ReleaseAsset, ReleaseInfo


SHA_MAC = "0" * 64
SHA_WIN = "1" * 64


def release_with_assets(*assets: ReleaseAsset) -> ReleaseInfo:
    return ReleaseInfo(
        tag_name="v2.3.0",
        name="DataLab v2.3.0",
        version="2.3.0",
        html_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        body="Release notes",
        published_at="2026-05-26T00:00:00Z",
        assets=assets,
    )


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "min_client_version": "2.2.0",
        "version": "2.3.0",
        "published_at": "2026-05-26T00:00:00Z",
        "release_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        "notes": "Added installer updates.",
        "assets": {
            "macos": {
                "name": "DataLab-2.3.0-macOS.pkg",
                "sha256": SHA_MAC,
                "size_bytes": 125,
            },
            "windows-x64": {
                "name": "DataLab-2.3.0-Windows-x64.exe",
                "sha256": SHA_WIN,
                "size_bytes": 140,
            },
        },
    }


def test_validate_manifest_selects_platform_asset_from_release_assets() -> None:
    from shared.update_payload import select_update_payload

    release = release_with_assets(
        ReleaseAsset("updates.json", "https://example.invalid/updates.json", 512),
        ReleaseAsset("DataLab-2.3.0-macOS.pkg", "https://example.invalid/mac.pkg", 125),
        ReleaseAsset("DataLab-2.3.0-Windows-x64.exe", "https://example.invalid/win.exe", 140),
    )

    payload = select_update_payload(
        release=release,
        manifest=valid_manifest(),
        platform_key="macos",
        current_version="2.2.0",
    )

    assert payload.version == "2.3.0"
    assert payload.asset.name == "DataLab-2.3.0-macOS.pkg"
    assert payload.asset.url == "https://example.invalid/mac.pkg"
    assert payload.asset.sha256 == SHA_MAC
    assert payload.asset.size_bytes == 125


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda data: data.update({"schema_version": 2}), "unsupported schema_version"),
        (lambda data: data.update({"version": "9.9.9"}), "version does not match"),
        (lambda data: data["assets"]["macos"].update({"sha256": "bad"}), "sha256"),
        (lambda data: data["assets"]["macos"].update({"size_bytes": 0}), "size_bytes"),
        (lambda data: data["assets"].pop("macos"), "platform"),
        (lambda data: data.update({"min_client_version": "9.0.0"}), "too old"),
    ],
)
def test_validate_manifest_rejects_invalid_metadata(mutation, message) -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    mutation(manifest)
    release = release_with_assets(
        ReleaseAsset("DataLab-2.3.0-macOS.pkg", "https://example.invalid/mac.pkg", 125),
    )

    with pytest.raises(UpdatePayloadError, match=message):
        select_update_payload(
            release=release,
            manifest=manifest,
            platform_key="macos",
            current_version="2.2.0",
        )


def test_manifest_asset_name_must_exist_in_github_release_assets() -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    release = release_with_assets(
        ReleaseAsset("other.pkg", "https://example.invalid/other.pkg", 125),
    )

    with pytest.raises(UpdatePayloadError, match="asset not found"):
        select_update_payload(
            release=release,
            manifest=valid_manifest(),
            platform_key="macos",
            current_version="2.2.0",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_payload.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'shared.update_payload'`.

- [ ] **Step 3: Implement manifest validation**

Create `shared/update_payload.py` with:

```python
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
    pass


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


def _version_key(version: str) -> tuple[int, ...]:
    parts = normalize_version_tag(version).split(".")
    values: list[int] = []
    for part in parts[:3]:
        match = re.match(r"^(\d+)", part)
        values.append(int(match.group(1)) if match else 0)
    while len(values) < 3:
        values.append(0)
    return tuple(values)


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
    release_url = str(manifest.get("release_url") or release.html_url)
    if _norm_url(release_url) != _norm_url(release.html_url):
        raise UpdatePayloadError("release_url does not match GitHub release")
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or platform_key not in assets:
        raise UpdatePayloadError(f"platform asset missing: {platform_key}")
    asset_data = assets[platform_key]
    if not isinstance(asset_data, dict):
        raise UpdatePayloadError(f"platform asset must be an object: {platform_key}")
    name = str(asset_data.get("name") or "")
    sha256 = str(asset_data.get("sha256") or "")
    if not _SHA256_RE.match(sha256):
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
        asset=InstallerAsset(platform_key, name, url, sha256, size_bytes),
    )


def update_cache_dir() -> Path:
    if platform.system().lower() == "darwin":
        return Path.home() / "Library" / "Caches" / "DataLab" / "Updates"
    if platform.system().lower() == "windows":
        root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(root) / "DataLab" / "Updates"
    return Path(tempfile.gettempdir()) / "DataLab" / "Updates"
```

- [ ] **Step 4: Run manifest tests**

Run:

```bash
pytest -q tests/test_update_payload.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/update_payload.py tests/test_update_payload.py
git commit -m "feat: validate update payload metadata"
```

## Task 3: Update Payload Download, Hash, And Lock

**Files:**
- Modify: `shared/update_payload.py`
- Modify: `tests/test_update_payload.py`

- [ ] **Step 1: Add failing download/hash/lock tests**

Append to `tests/test_update_payload.py`:

```python
import hashlib
from pathlib import Path


def test_download_installer_verifies_size_and_sha(tmp_path, monkeypatch) -> None:
    from shared import update_payload
    from shared.update_payload import InstallerAsset, download_and_verify_installer

    content = b"installer"
    sha = hashlib.sha256(content).hexdigest()
    asset = InstallerAsset(
        platform_key="macos",
        name="DataLab-2.3.0-macOS.pkg",
        url="https://example.invalid/mac.pkg",
        sha256=sha,
        size_bytes=len(content),
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, size=-1):
            return content if size < 0 else content[:size]

    monkeypatch.setattr(update_payload, "_urlopen", lambda request, timeout: FakeResponse())
    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    path = download_and_verify_installer(asset)

    assert path == tmp_path / asset.name
    assert path.read_bytes() == content


def test_download_installer_deletes_bad_sha(tmp_path, monkeypatch) -> None:
    from shared import update_payload
    from shared.update_payload import InstallerAsset, UpdatePayloadError, download_and_verify_installer

    asset = InstallerAsset(
        platform_key="macos",
        name="DataLab-2.3.0-macOS.pkg",
        url="https://example.invalid/mac.pkg",
        sha256="0" * 64,
        size_bytes=9,
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, size=-1):
            return b"installer"

    monkeypatch.setattr(update_payload, "_urlopen", lambda request, timeout: FakeResponse())
    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    with pytest.raises(UpdatePayloadError, match="sha256 mismatch"):
        download_and_verify_installer(asset)

    assert not list(tmp_path.glob("*.pkg"))


def test_update_lock_rejects_second_holder(tmp_path, monkeypatch) -> None:
    from shared import update_payload
    from shared.update_payload import UpdatePayloadError, UpdateCacheLock

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    with UpdateCacheLock():
        with pytest.raises(UpdatePayloadError, match="already in progress"):
            with UpdateCacheLock():
                pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_payload.py::test_download_installer_verifies_size_and_sha tests/test_update_payload.py::test_download_installer_deletes_bad_sha tests/test_update_lock_rejects_second_holder
```

Expected: FAIL because download and lock APIs do not exist.

- [ ] **Step 3: Implement download, hash, reverify, and lock**

Add to `shared/update_payload.py`:

```python
import hashlib
import time
import urllib.request


def _urlopen(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installer_file(path: Path, asset: InstallerAsset) -> None:
    if not path.is_file():
        raise UpdatePayloadError(f"installer not found: {path}")
    size = path.stat().st_size
    if size != asset.size_bytes:
        raise UpdatePayloadError(f"size mismatch: expected {asset.size_bytes}, got {size}")
    actual = sha256_file(path)
    if actual.lower() != asset.sha256.lower():
        raise UpdatePayloadError("sha256 mismatch")


def _safe_target_path(cache_dir: Path, name: str) -> Path:
    if "/" in name or "\\" in name or name in {"", ".", ".."}:
        raise UpdatePayloadError(f"unsafe asset name: {name!r}")
    return cache_dir / name


def download_and_verify_installer(
    asset: InstallerAsset,
    *,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
) -> Path:
    cache_dir = update_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = _safe_target_path(cache_dir, asset.name)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": "DataLab Update Checker"})
    try:
        with _urlopen(request, timeout=timeout) as response:
            data = response.read()
        if len(data) != asset.size_bytes:
            raise UpdatePayloadError(f"size mismatch: expected {asset.size_bytes}, got {len(data)}")
        if len(data) > MAX_INSTALLER_BYTES:
            raise UpdatePayloadError("installer exceeds maximum size")
        partial.write_bytes(data)
        verify_installer_file(partial, asset)
        partial.replace(target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def fetch_manifest_for_release(release: ReleaseInfo, *, timeout: float = DEFAULT_DOWNLOAD_TIMEOUT) -> dict[str, Any]:
    url = find_manifest_asset_url(release)
    request = urllib.request.Request(url, headers={"User-Agent": "DataLab Update Checker"})
    with _urlopen(request, timeout=timeout) as response:
        return loads_manifest(response.read(MANIFEST_MAX_BYTES + 1))


def resolve_update_payload_for_release(
    release: ReleaseInfo,
    *,
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
    def __init__(self, *, stale_after_seconds: int = 6 * 60 * 60) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._path = update_cache_dir() / ".update.lock"
        self._acquired = False

    def __enter__(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            age = time.time() - self._path.stat().st_mtime
            if age <= self._stale_after_seconds:
                raise UpdatePayloadError("update already in progress")
            self._path.unlink(missing_ok=True)
        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise UpdatePayloadError("update already in progress") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        self._acquired = True
        return self

    def __exit__(self, *_):
        if self._acquired:
            self._path.unlink(missing_ok=True)
            self._acquired = False
        return False
```

- [ ] **Step 4: Run payload tests**

Run:

```bash
pytest -q tests/test_update_payload.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/update_payload.py tests/test_update_payload.py
git commit -m "feat: download and verify update installers"
```

## Task 4: Update Preferences And Settings Keys

**Files:**
- Modify: `shared/settings_store.py`
- Create: `shared/update_preferences.py`
- Create: `tests/test_update_preferences.py`

- [ ] **Step 1: Write failing preference tests**

Create `tests/test_update_preferences.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class FakeSettings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def value(self, key: str, default=None):
        return self.values.get(key, default)

    def setValue(self, key: str, value: object) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)

    def sync(self) -> None:
        return None

    def status(self):
        return 0


def test_update_preferences_default_off_and_throttled() -> None:
    from shared.settings_store import SettingsStore
    from shared.update_preferences import AUTO_CHECK_INTERVAL, UpdatePreferences

    prefs = UpdatePreferences(SettingsStore(store=FakeSettings()))
    now = datetime(2026, 5, 26, 12, tzinfo=timezone.utc)

    assert prefs.auto_update_enabled() is False
    assert prefs.should_auto_check(now) is False

    prefs.set_auto_update_enabled(True)
    assert prefs.should_auto_check(now) is True

    prefs.mark_checked(now)
    assert prefs.should_auto_check(now + AUTO_CHECK_INTERVAL - timedelta(seconds=1)) is False
    assert prefs.should_auto_check(now + AUTO_CHECK_INTERVAL + timedelta(seconds=1)) is True


def test_update_preferences_future_clock_allows_one_rewrite() -> None:
    from shared.settings_store import SettingsStore
    from shared.update_preferences import UpdatePreferences

    prefs = UpdatePreferences(SettingsStore(store=FakeSettings()))
    now = datetime(2026, 5, 26, 12, tzinfo=timezone.utc)
    prefs.set_auto_update_enabled(True)
    prefs.mark_checked(now + timedelta(days=2))

    assert prefs.should_auto_check(now) is True


def test_update_preferences_skip_and_cached_release_notes() -> None:
    from shared.settings_store import SettingsStore
    from shared.update_preferences import UpdatePreferences

    prefs = UpdatePreferences(SettingsStore(store=FakeSettings()))
    prefs.skip_version("2.3.0")
    prefs.cache_release_notes("2.3.0", "notes", "https://example.invalid/release", "2026-05-26T00:00:00Z")

    assert prefs.is_skipped("2.3.0") is True
    assert prefs.is_skipped("2.4.0") is False
    assert prefs.cached_release_notes().version == "2.3.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_preferences.py
```

Expected: FAIL because settings bool/string helpers and `shared.update_preferences` do not exist.

- [ ] **Step 3: Add SettingsStore helpers and keys**

In `shared/settings_store.py`, add `Update/` to `_ALLOWED_KEY_PREFIXES`, then add bool/string methods to `SettingsStore`:

```python
    def save_bool(self, key: str, value: bool) -> None:
        _validate_key(key)
        try:
            self._store.setValue(key, bool(value))
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.save_bool(%s) raised: %s", key, exc)
        self._check_status("save_bool", key)

    def load_bool(self, key: str, default: bool = False) -> bool:
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_bool(%s) failed: %s", key, exc)
            return default
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int):
            return bool(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    def save_string(self, key: str, value: str | None) -> None:
        _validate_key(key)
        try:
            if value is None:
                self._store.remove(key)
            else:
                self._store.setValue(key, str(value))
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.save_string(%s) raised: %s", key, exc)
        self._check_status("save_string", key)

    def load_string(self, key: str, default: str = "") -> str:
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_string(%s) failed: %s", key, exc)
            return default
        if raw is None:
            return default
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)
```

Add constants:

```python
KEY_UPDATE_AUTO_ENABLED = "Update/prefs/auto_update_enabled"
KEY_UPDATE_SKIPPED_VERSION = "Update/prefs/skipped_version"
KEY_UPDATE_LAST_CHECKED_AT = "Update/state/last_checked_at"
KEY_UPDATE_LAST_SEEN_VERSION = "Update/state/last_seen_current_version"
KEY_UPDATE_CACHE_VERSION = "Update/cache/release_version"
KEY_UPDATE_CACHE_NOTES = "Update/cache/release_notes"
KEY_UPDATE_CACHE_URL = "Update/cache/release_url"
KEY_UPDATE_CACHE_PUBLISHED_AT = "Update/cache/release_published_at"
```

- [ ] **Step 4: Implement preferences**

Create `shared/update_preferences.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared.settings_store import (
    KEY_UPDATE_AUTO_ENABLED,
    KEY_UPDATE_CACHE_NOTES,
    KEY_UPDATE_CACHE_PUBLISHED_AT,
    KEY_UPDATE_CACHE_URL,
    KEY_UPDATE_CACHE_VERSION,
    KEY_UPDATE_LAST_CHECKED_AT,
    KEY_UPDATE_LAST_SEEN_VERSION,
    KEY_UPDATE_SKIPPED_VERSION,
    SettingsStore,
)

AUTO_CHECK_INTERVAL = timedelta(hours=24)
FUTURE_CLOCK_SKEW_ALLOWANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class CachedReleaseNotes:
    version: str
    notes: str
    url: str
    published_at: str


def _parse_utc(text: str) -> datetime | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class UpdatePreferences:
    def __init__(self, settings: SettingsStore | None = None) -> None:
        self._settings = settings or SettingsStore()

    def auto_update_enabled(self) -> bool:
        return self._settings.load_bool(KEY_UPDATE_AUTO_ENABLED, default=False)

    def set_auto_update_enabled(self, enabled: bool) -> None:
        self._settings.save_bool(KEY_UPDATE_AUTO_ENABLED, enabled)

    def should_auto_check(self, now: datetime) -> bool:
        if not self.auto_update_enabled():
            return False
        last = _parse_utc(self._settings.load_string(KEY_UPDATE_LAST_CHECKED_AT, default=""))
        now = now.astimezone(timezone.utc)
        if last is None:
            return True
        if last - now > FUTURE_CLOCK_SKEW_ALLOWANCE:
            return True
        return now - last >= AUTO_CHECK_INTERVAL

    def mark_checked(self, when: datetime) -> None:
        self._settings.save_string(KEY_UPDATE_LAST_CHECKED_AT, _format_utc(when))

    def skip_version(self, version: str) -> None:
        self._settings.save_string(KEY_UPDATE_SKIPPED_VERSION, version)

    def is_skipped(self, version: str) -> bool:
        return self._settings.load_string(KEY_UPDATE_SKIPPED_VERSION, default="") == version

    def cache_release_notes(self, version: str, notes: str, url: str, published_at: str) -> None:
        self._settings.save_string(KEY_UPDATE_CACHE_VERSION, version)
        self._settings.save_string(KEY_UPDATE_CACHE_NOTES, notes)
        self._settings.save_string(KEY_UPDATE_CACHE_URL, url)
        self._settings.save_string(KEY_UPDATE_CACHE_PUBLISHED_AT, published_at)

    def cached_release_notes(self) -> CachedReleaseNotes | None:
        version = self._settings.load_string(KEY_UPDATE_CACHE_VERSION, default="")
        if not version:
            return None
        return CachedReleaseNotes(
            version=version,
            notes=self._settings.load_string(KEY_UPDATE_CACHE_NOTES, default=""),
            url=self._settings.load_string(KEY_UPDATE_CACHE_URL, default=""),
            published_at=self._settings.load_string(KEY_UPDATE_CACHE_PUBLISHED_AT, default=""),
        )

    def consume_version_changed_notice(self, current_version: str) -> bool:
        previous = self._settings.load_string(KEY_UPDATE_LAST_SEEN_VERSION, default="")
        self._settings.save_string(KEY_UPDATE_LAST_SEEN_VERSION, current_version)
        return bool(current_version and previous != current_version)
```

- [ ] **Step 5: Run preference tests**

Run:

```bash
pytest -q tests/test_update_preferences.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shared/settings_store.py shared/update_preferences.py tests/test_update_preferences.py
git commit -m "feat: persist update preferences"
```

## Task 5: Platform Installer Backend

**Files:**
- Create: `app_desktop/update_installer.py`
- Create: `tests/test_update_installer.py`

- [ ] **Step 1: Write failing installer tests**

Create `tests/test_update_installer.py`:

```python
from __future__ import annotations

import hashlib

import pytest


def write_installer(path, content=b"installer"):
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)


def test_windows_installer_command_is_constructed_in_code(tmp_path, monkeypatch) -> None:
    from app_desktop.update_installer import launch_installer

    path = tmp_path / "DataLab.exe"
    sha, size = write_installer(path)
    launched: list[list[str]] = []

    monkeypatch.setattr("app_desktop.update_installer.platform.system", lambda: "Windows")
    monkeypatch.setattr("app_desktop.update_installer.subprocess.Popen", lambda argv: launched.append(argv))

    result = launch_installer(path, platform_key="windows-x64", expected_sha256=sha, expected_size=size)

    assert result.launched is True
    assert launched == [[str(path), "/VERYSILENT", "/NORESTART"]]


def test_macos_installer_command_is_constructed_in_code(tmp_path, monkeypatch) -> None:
    from app_desktop.update_installer import launch_installer

    path = tmp_path / "DataLab.pkg"
    sha, size = write_installer(path)
    launched: list[list[str]] = []

    monkeypatch.setattr("app_desktop.update_installer.platform.system", lambda: "Darwin")
    monkeypatch.setattr("app_desktop.update_installer.subprocess.Popen", lambda argv: launched.append(argv))

    result = launch_installer(path, platform_key="macos", expected_sha256=sha, expected_size=size)

    assert result.launched is True
    assert launched == [["/usr/sbin/installer", "-pkg", str(path), "-target", "/"]]


def test_installer_rejects_wrong_extension_and_bad_hash(tmp_path, monkeypatch) -> None:
    from app_desktop.update_installer import InstallerLaunchError, launch_installer

    path = tmp_path / "DataLab.txt"
    sha, size = write_installer(path)

    monkeypatch.setattr("app_desktop.update_installer.platform.system", lambda: "Windows")

    with pytest.raises(InstallerLaunchError, match="extension"):
        launch_installer(path, platform_key="windows-x64", expected_sha256=sha, expected_size=size)

    exe = tmp_path / "DataLab.exe"
    write_installer(exe)
    with pytest.raises(InstallerLaunchError, match="sha256"):
        launch_installer(exe, platform_key="windows-x64", expected_sha256="0" * 64, expected_size=size)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_installer.py
```

Expected: FAIL because `app_desktop.update_installer` does not exist.

- [ ] **Step 3: Implement installer backend**

Create `app_desktop/update_installer.py`:

```python
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shared.update_payload import UpdatePayloadError, sha256_file


class InstallerLaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallerLaunchResult:
    launched: bool
    argv: tuple[str, ...]


def _verify(path: Path, expected_sha256: str, expected_size: int) -> None:
    if not path.is_file():
        raise InstallerLaunchError(f"installer not found: {path}")
    if path.stat().st_size != expected_size:
        raise InstallerLaunchError("installer size mismatch")
    if sha256_file(path).lower() != expected_sha256.lower():
        raise InstallerLaunchError("installer sha256 mismatch")


def _argv(path: Path, platform_key: str) -> list[str]:
    system = platform.system()
    if platform_key == "windows-x64" and system == "Windows":
        if path.suffix.lower() != ".exe":
            raise InstallerLaunchError("windows installer extension must be .exe")
        return [str(path), "/VERYSILENT", "/NORESTART"]
    if platform_key == "macos" and system == "Darwin":
        if path.suffix.lower() != ".pkg":
            raise InstallerLaunchError("macOS installer extension must be .pkg")
        return ["/usr/sbin/installer", "-pkg", str(path), "-target", "/"]
    raise InstallerLaunchError(f"platform mismatch: {system}/{platform_key}")


def launch_installer(
    path: Path,
    *,
    platform_key: str,
    expected_sha256: str,
    expected_size: int,
) -> InstallerLaunchResult:
    path = Path(path)
    try:
        _verify(path, expected_sha256, expected_size)
    except UpdatePayloadError as exc:
        raise InstallerLaunchError(str(exc)) from exc
    argv = _argv(path, platform_key)
    try:
        subprocess.Popen(argv)  # noqa: S603 - argv is code-constructed and path was verified.
    except OSError as exc:
        raise InstallerLaunchError(f"failed to launch installer: {exc}") from exc
    return InstallerLaunchResult(launched=True, argv=tuple(argv))
```

- [ ] **Step 4: Run installer tests**

Run:

```bash
pytest -q tests/test_update_installer.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app_desktop/update_installer.py tests/test_update_installer.py
git commit -m "feat: add platform update installer launcher"
```

## Task 6: Dialog Text And Controller State Machine

**Files:**
- Create: `app_desktop/update_dialogs.py`
- Create: `app_desktop/update_controller.py`
- Create: `tests/test_update_controller.py`

- [ ] **Step 1: Write failing controller tests**

Create `tests/test_update_controller.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from shared.update_checker import ReleaseInfo, UpdateCheckResult
from shared.update_payload import InstallerAsset, UpdatePayload


class FakePreferences:
    def __init__(self) -> None:
        self.enabled = False
        self.checked = False
        self.skipped: set[str] = set()
        self.cached: list[tuple[str, str, str, str]] = []

    def auto_update_enabled(self):
        return self.enabled

    def set_auto_update_enabled(self, enabled):
        self.enabled = enabled

    def should_auto_check(self, now):
        return self.enabled

    def mark_checked(self, now):
        self.checked = True

    def is_skipped(self, version):
        return version in self.skipped

    def skip_version(self, version):
        self.skipped.add(version)

    def cache_release_notes(self, version, notes, url, published_at):
        self.cached.append((version, notes, url, published_at))


class FakeWindow:
    def __init__(self) -> None:
        self.questions: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []
        self.opened: list[str] = []
        self.exited = False

    def is_english(self):
        return False

    def ask_update(self, title, message, *, was_skipped=False):
        self.questions.append(message)
        return "update"

    def warning(self, title, message):
        self.warnings.append(message)

    def information(self, title, message):
        self.infos.append(message)

    def open_url(self, url):
        self.opened.append(url)

    def exit_for_update(self):
        self.exited = True


def release() -> ReleaseInfo:
    return ReleaseInfo(
        tag_name="v2.3.0",
        name="DataLab v2.3.0",
        version="2.3.0",
        html_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        body="Release body",
        published_at="2026-05-26T00:00:00Z",
        assets=(),
    )


def payload() -> UpdatePayload:
    return UpdatePayload(
        version="2.3.0",
        notes="Installer updater notes",
        published_at="2026-05-26T00:00:00Z",
        release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        asset=InstallerAsset("macos", "DataLab.pkg", "https://example.invalid/pkg", "0" * 64, 10),
    )


def test_manual_update_available_runs_download_and_launch(tmp_path) -> None:
    from app_desktop.update_controller import UpdateController

    window = FakeWindow()
    installer = tmp_path / "DataLab.pkg"
    installer.write_bytes(b"installer")
    launched = []
    controller = UpdateController(
        window,
        preferences=FakePreferences(),
        check_for_updates=lambda: UpdateCheckResult("update-available", "2.2.0", "2.3.0", release()),
        resolve_payload=lambda release, current_version: payload(),
        download_installer=lambda asset: installer,
        launch_installer=lambda path, asset: launched.append((path, asset)) or True,
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()

    assert "Installer updater notes" in window.questions[0]
    assert launched == [(installer, payload().asset)]
    assert window.exited is True


def test_auto_offline_failure_is_quiet_and_marks_checked() -> None:
    from app_desktop.update_controller import UpdateController

    window = FakeWindow()
    prefs = FakePreferences()
    prefs.enabled = True
    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: UpdateCheckResult("unavailable", "2.2.0", error="offline"),
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.maybe_auto_check()

    assert window.warnings == []
    assert prefs.checked is True


def test_reentrant_update_check_is_rejected() -> None:
    from app_desktop.update_controller import UpdateController, UpdateState

    window = FakeWindow()
    controller = UpdateController(window, preferences=FakePreferences())
    controller.state = UpdateState.DOWNLOADING

    controller.check_now()

    assert "already in progress" in window.warnings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_controller.py
```

Expected: FAIL because controller/dialog modules do not exist.

- [ ] **Step 3: Implement dialog helpers**

Create `app_desktop/update_dialogs.py`:

```python
from __future__ import annotations

from shared.update_checker import format_release_notes_for_dialog
from shared.update_payload import UpdatePayload


def build_update_message(payload: UpdatePayload, current_version: str, *, lang: str, was_skipped: bool = False) -> str:
    notes = format_release_notes_for_dialog(payload.notes)
    skipped = "\n\n此前已跳过此版本。" if was_skipped and lang == "zh" else ""
    skipped_en = "\n\nYou previously skipped this version." if was_skipped and lang == "en" else ""
    if lang == "en":
        return (
            f"Version {payload.version} is available. Current version: {current_version}.\n\n"
            f"Published: {payload.published_at}\n"
            f"Installer: {payload.asset.name} ({payload.asset.size_bytes} bytes)\n"
            f"Release: {payload.release_url}\n\n"
            f"Release notes:\n{notes}\n\n"
            "OS security or administrator prompts may appear. DataLab will close after the installer starts."
            f"{skipped_en}"
        )
    return (
        f"发现新版本 {payload.version}，当前版本为 {current_version}。\n\n"
        f"发布时间：{payload.published_at}\n"
        f"安装包：{payload.asset.name}（{payload.asset.size_bytes} bytes）\n"
        f"发布页面：{payload.release_url}\n\n"
        f"本次更新内容：\n{notes}\n\n"
        "系统可能显示安全或管理员授权提示。安装器启动后 DataLab 将关闭。"
        f"{skipped}"
    )
```

- [ ] **Step 4: Implement controller**

Create `app_desktop/update_controller.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from shared.update_checker import RELEASES_URL, UpdateCheckResult, check_for_updates
from shared.update_payload import UpdateCacheLock, UpdatePayload, UpdatePayloadError, download_and_verify_installer, resolve_update_payload_for_release
from shared.update_preferences import UpdatePreferences

from app_desktop.update_dialogs import build_update_message
from app_desktop.update_installer import InstallerLaunchError, launch_installer as launch_platform_installer


class UpdateState(Enum):
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    LAUNCHING = "launching"


@dataclass
class UpdateController:
    window: object
    preferences: object | None = None
    check_for_updates: Callable[[], UpdateCheckResult] = check_for_updates
    resolve_payload: Callable[[object, str], UpdatePayload] | None = None
    download_installer: Callable[[object], Path] = download_and_verify_installer
    launch_installer: Callable[[Path, object], bool] | None = None
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    state: UpdateState = UpdateState.IDLE

    def __post_init__(self) -> None:
        if self.preferences is None:
            self.preferences = UpdatePreferences()
        if self.launch_installer is None:
            self.launch_installer = self._launch_platform

    def auto_update_enabled(self) -> bool:
        return self.preferences.auto_update_enabled()

    def set_auto_update_enabled(self, enabled: bool) -> None:
        self.preferences.set_auto_update_enabled(enabled)

    def check_now(self) -> None:
        if self.state is not UpdateState.IDLE:
            self.window.warning("Update", "An update operation is already in progress.")
            return
        self._run_check(manual=True)

    def maybe_auto_check(self) -> None:
        if self.state is not UpdateState.IDLE:
            return
        if not self.preferences.should_auto_check(self.now()):
            return
        self._run_check(manual=False)

    def _run_check(self, *, manual: bool) -> None:
        self.state = UpdateState.CHECKING
        try:
            result = self.check_for_updates()
            if not manual:
                self.preferences.mark_checked(self.now())
            self._handle_result(result, manual=manual)
        finally:
            if self.state is not UpdateState.DOWNLOADING and self.state is not UpdateState.LAUNCHING:
                self.state = UpdateState.IDLE

    def _handle_result(self, result: UpdateCheckResult, *, manual: bool) -> None:
        if result.status == "unavailable":
            if manual:
                self.window.warning("Update Check Failed", f"Unable to check for updates: {result.error}\n\n{RELEASES_URL}")
            return
        if result.status != "update-available" or result.release is None:
            if manual:
                self.window.information("Up To Date", f"Version {result.current_version} is already up to date.")
            return
        try:
            payload = self._resolve_payload(result.release, result.current_version)
        except UpdatePayloadError as exc:
            if manual:
                self.window.warning("Manual Update Required", f"Automatic installation is unavailable: {exc}\n\n{result.release.html_url}")
            return
        was_skipped = self.preferences.is_skipped(payload.version)
        if was_skipped and not manual:
            return
        message = build_update_message(payload, result.current_version, lang=self._lang(), was_skipped=was_skipped)
        choice = self.window.ask_update("Update Available", message, was_skipped=was_skipped)
        if choice == "skip":
            self.preferences.skip_version(payload.version)
            return
        if choice != "update":
            return
        self._download_and_launch(payload)

    def _resolve_payload(self, release, current_version: str) -> UpdatePayload:
        if self.resolve_payload is not None:
            return self.resolve_payload(release, current_version)
        return resolve_update_payload_for_release(release, current_version=current_version)

    def _download_and_launch(self, payload: UpdatePayload) -> None:
        self.state = UpdateState.DOWNLOADING
        try:
            with UpdateCacheLock():
                path = self.download_installer(payload.asset)
                self.preferences.cache_release_notes(payload.version, payload.notes, payload.release_url, payload.published_at)
                self.state = UpdateState.LAUNCHING
                launched = self.launch_installer(path, payload.asset)
        except (UpdatePayloadError, InstallerLaunchError, OSError) as exc:
            self.state = UpdateState.IDLE
            self.window.warning("Update Failed", str(exc))
            return
        if launched:
            self.window.exit_for_update()

    def _launch_platform(self, path: Path, asset) -> bool:
        launch_platform_installer(
            path,
            platform_key=asset.platform_key,
            expected_sha256=asset.sha256,
            expected_size=asset.size_bytes,
        )
        return True

    def _lang(self) -> str:
        return "en" if self.window.is_english() else "zh"
```

- [ ] **Step 5: Run controller tests**

Run:

```bash
pytest -q tests/test_update_controller.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app_desktop/update_dialogs.py app_desktop/update_controller.py tests/test_update_controller.py
git commit -m "feat: add update controller state machine"
```

## Task 7: Wire Desktop Menu And Window

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window.py`
- Modify: `tests/test_desktop_update_menu.py`

- [ ] **Step 1: Add failing static wiring tests**

Append to `tests/test_desktop_update_menu.py`:

```python
def test_help_menu_exposes_auto_update_toggle() -> None:
    text = (ROOT / "app_desktop" / "panels.py").read_text(encoding="utf-8")

    assert 'QAction("自动更新", self)' in text
    assert "auto_update_action.setCheckable(True)" in text
    assert "auto_update_action.setChecked(self._update_controller.auto_update_enabled())" in text
    assert "auto_update_action.toggled.connect(self._set_auto_update_enabled)" in text
    assert 'self._register_text(auto_update_action, "自动更新", "Automatic Updates", "setText")' in text


def test_window_delegates_update_flow_to_controller() -> None:
    text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")

    assert "from app_desktop.update_controller import UpdateController" in text
    assert "self._update_controller = UpdateController(self)" in text
    assert "self._update_controller.check_now()" in text
    assert "self._update_controller.set_auto_update_enabled" in text
    assert "self._update_controller.maybe_auto_check" in text
    assert "exit_for_update" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_desktop_update_menu.py
```

Expected: FAIL because menu/controller wiring is absent.

- [ ] **Step 3: Wire Help menu**

In `app_desktop/panels.py`, after the existing `update_action` block, add:

```python
    auto_update_action = QAction("自动更新", self)
    auto_update_action.setMenuRole(QAction.NoRole)
    auto_update_action.setCheckable(True)
    auto_update_action.setChecked(self._update_controller.auto_update_enabled())
    auto_update_action.toggled.connect(self._set_auto_update_enabled)
    help_menu.addAction(auto_update_action)
    self._register_text(auto_update_action, "自动更新", "Automatic Updates", "setText")
```

- [ ] **Step 4: Wire window adapters**

In `app_desktop/window.py`, import:

```python
from PySide6.QtCore import QTimer
from app_desktop.update_controller import UpdateController
```

In `ExtrapolationWindow.__init__`, before `build_ui(self)`, add:

```python
        self._update_controller = UpdateController(self)
```

After initial UI setup, add:

```python
        QTimer.singleShot(1500, self._update_controller.maybe_auto_check)
```

Replace `_check_for_updates` body with:

```python
    def _check_for_updates(self, _checked: bool = False):
        self._update_controller.check_now()
```

Add window adapter methods near `_check_for_updates`:

```python
    def _set_auto_update_enabled(self, checked: bool) -> None:
        self._update_controller.set_auto_update_enabled(bool(checked))

    def is_english(self) -> bool:
        return self._is_en()

    def ask_update(self, title: str, message: str, *, was_skipped: bool = False) -> str:
        box = QMessageBox(self)
        box.setWindowTitle(self._tr("发现新版本", "Update Available"))
        box.setText(message)
        update_btn = box.addButton(self._tr("立即更新", "Update Now"), QMessageBox.AcceptRole)
        later_btn = box.addButton(self._tr("稍后", "Later"), QMessageBox.RejectRole)
        skip_btn = box.addButton(self._tr("跳过此版本", "Skip This Version"), QMessageBox.DestructiveRole)
        box.setDefaultButton(update_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked == update_btn:
            return "update"
        if clicked == skip_btn:
            return "skip"
        if clicked == later_btn:
            return "later"
        return "later"

    def warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def information(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def exit_for_update(self) -> None:
        QApplication.quit()
```

- [ ] **Step 5: Run desktop update menu tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_update_menu.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app_desktop/panels.py app_desktop/window.py tests/test_desktop_update_menu.py
git commit -m "feat: wire installer update UI"
```

## Task 8: Manifest Generation Tool

**Files:**
- Create: `tools/generate_updates_manifest.py`
- Create: `tests/test_generate_updates_manifest.py`

- [ ] **Step 1: Write failing manifest generator tests**

Create `tests/test_generate_updates_manifest.py`:

```python
from __future__ import annotations

import hashlib
import json


def test_generate_updates_manifest_writes_size_and_sha(tmp_path) -> None:
    from tools.generate_updates_manifest import generate_manifest

    mac = tmp_path / "DataLab-2.3.0-macOS.pkg"
    win = tmp_path / "DataLab-2.3.0-Windows-x64.exe"
    mac.write_bytes(b"mac")
    win.write_bytes(b"win")

    manifest = generate_manifest(
        version="2.3.0",
        release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        notes="Release notes",
        macos_pkg=mac,
        windows_exe=win,
        published_at="2026-05-26T00:00:00Z",
        min_client_version="2.2.0",
    )

    assert manifest["schema_version"] == 1
    assert manifest["assets"]["macos"]["sha256"] == hashlib.sha256(b"mac").hexdigest()
    assert manifest["assets"]["macos"]["size_bytes"] == 3
    assert "install_args" not in manifest["assets"]["windows-x64"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/test_generate_updates_manifest.py
```

Expected: FAIL because generator does not exist.

- [ ] **Step 3: Implement generator**

Create `tools/generate_updates_manifest.py`:

```python
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def generate_manifest(
    *,
    version: str,
    release_url: str,
    notes: str,
    macos_pkg: Path | None,
    windows_exe: Path | None,
    published_at: str,
    min_client_version: str,
) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    if macos_pkg is not None:
        assets["macos"] = _asset(Path(macos_pkg))
    if windows_exe is not None:
        assets["windows-x64"] = _asset(Path(windows_exe))
    return {
        "schema_version": 1,
        "min_client_version": min_client_version,
        "version": version,
        "published_at": published_at,
        "release_url": release_url,
        "notes": notes,
        "assets": assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--notes-file", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--min-client-version", required=True)
    parser.add_argument("--macos-pkg")
    parser.add_argument("--windows-exe")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = generate_manifest(
        version=args.version,
        release_url=args.release_url,
        notes=Path(args.notes_file).read_text(encoding="utf-8"),
        macos_pkg=Path(args.macos_pkg) if args.macos_pkg else None,
        windows_exe=Path(args.windows_exe) if args.windows_exe else None,
        published_at=args.published_at,
        min_client_version=args.min_client_version,
    )
    Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run generator tests**

Run:

```bash
pytest -q tests/test_generate_updates_manifest.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_updates_manifest.py tests/test_generate_updates_manifest.py
git commit -m "feat: generate update manifest"
```

## Task 9: macOS PKG Packaging Hook

**Files:**
- Modify: `build_mac_data_gui.sh`
- Create: `tests/test_update_packaging_scripts.py`

- [ ] **Step 1: Write failing macOS packaging script test**

Create `tests/test_update_packaging_scripts.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mac_build_script_has_optional_pkg_packaging() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")

    assert "DATALAB_BUILD_PKG" in text
    assert "pkgbuild" in text
    assert "productbuild" in text
    assert "DataLab-${APP_VERSION}-macOS.pkg" in text
    assert "Developer ID Installer" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/test_update_packaging_scripts.py::test_mac_build_script_has_optional_pkg_packaging
```

Expected: FAIL because the script has no `.pkg` packaging hook.

- [ ] **Step 3: Add optional `.pkg` packaging hook**

Near the end of `build_mac_data_gui.sh`, after PyInstaller creates `dist/DataLab.app`, add:

```bash
APP_VERSION="$("$PYTHON_BIN" - <<'PY'
import tomllib
from pathlib import Path
data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

if [[ "${DATALAB_BUILD_PKG:-0}" == "1" ]]; then
  PKG_ROOT="$BUILD_ROOT/pkgroot"
  PKG_COMPONENT="$BUILD_ROOT/DataLab-component.pkg"
  PKG_OUTPUT="$PROJECT_ROOT/dist/DataLab-${APP_VERSION}-macOS.pkg"
  rm -rf "$PKG_ROOT"
  mkdir -p "$PKG_ROOT/Applications"
  ditto "$PROJECT_ROOT/dist/DataLab.app" "$PKG_ROOT/Applications/DataLab.app"
  PKGBUILD_ARGS=(--root "$PKG_ROOT" --identifier "org.datalab.desktop" --version "$APP_VERSION" --install-location "/" "$PKG_COMPONENT")
  if [[ -n "${DATALAB_MAC_INSTALLER_IDENTITY:-}" ]]; then
    PKGBUILD_ARGS=(--sign "$DATALAB_MAC_INSTALLER_IDENTITY" "${PKGBUILD_ARGS[@]}")
    echo "[info] Signing pkg with Developer ID Installer identity: $DATALAB_MAC_INSTALLER_IDENTITY"
  else
    echo "[warn] DATALAB_MAC_INSTALLER_IDENTITY is not set; pkg is not auto-installable."
    echo "[warn] Expected identity format: Developer ID Installer: Your Name (TEAMID)"
  fi
  pkgbuild "${PKGBUILD_ARGS[@]}"
  productbuild --package "$PKG_COMPONENT" "$PKG_OUTPUT"
  echo "[done] macOS pkg: $PKG_OUTPUT"
fi
```

- [ ] **Step 4: Run packaging script test**

Run:

```bash
pytest -q tests/test_update_packaging_scripts.py::test_mac_build_script_has_optional_pkg_packaging
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add build_mac_data_gui.sh tests/test_update_packaging_scripts.py
git commit -m "feat: add macOS pkg packaging hook"
```

## Task 10: Windows Inno Packaging Hook

**Files:**
- Create: `packaging/windows/DataLab.iss`
- Modify: `build_windows_data_gui.ps1`
- Modify: `tests/test_update_packaging_scripts.py`

- [ ] **Step 1: Add failing Windows packaging tests**

Append to `tests/test_update_packaging_scripts.py`:

```python
def test_windows_build_script_has_inno_packaging_hook() -> None:
    text = (ROOT / "build_windows_data_gui.ps1").read_text(encoding="utf-8-sig")

    assert "BuildInnoInstaller" in text
    assert "ISCC.exe" in text
    assert "DataLab-{#AppVersion}-Windows-x64" in (ROOT / "packaging" / "windows" / "DataLab.iss").read_text(encoding="utf-8")


def test_inno_script_uses_safe_close_behavior() -> None:
    text = (ROOT / "packaging" / "windows" / "DataLab.iss").read_text(encoding="utf-8")

    assert "CloseApplications=yes" in text
    assert "RestartApplications=no" in text
    assert "PrivilegesRequired=admin" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_update_packaging_scripts.py::test_windows_build_script_has_inno_packaging_hook tests/test_update_packaging_scripts.py::test_inno_script_uses_safe_close_behavior
```

Expected: FAIL because Inno script and hook do not exist.

- [ ] **Step 3: Add Inno Setup script**

Create `packaging/windows/DataLab.iss`:

```ini
#define AppName "DataLab"
#define AppVersion GetEnv("DATALAB_APP_VERSION")
#define SourceDir GetEnv("DATALAB_WINDOWS_DIST_DIR")
#define OutputDir GetEnv("DATALAB_WINDOWS_INSTALLER_DIR")

[Setup]
AppId={{F3A4E4F0-3D4B-4C3D-A7F9-DATALAB00001}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\DataLab
DefaultGroupName=DataLab
OutputDir={#OutputDir}
OutputBaseFilename=DataLab-{#AppVersion}-Windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
UninstallDisplayName=DataLab

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DataLab"; Filename: "{app}\DataLab.exe"
Name: "{autodesktop}\DataLab"; Filename: "{app}\DataLab.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\DataLab.exe"; Description: "Launch DataLab"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 4: Add PowerShell hook**

In `build_windows_data_gui.ps1`, add parameters:

```powershell
    [switch]$BuildInnoInstaller,
    [string]$InnoSetupPath = ""
```

After PyInstaller output is built, add:

```powershell
if ($BuildInnoInstaller.IsPresent) {
    $pyprojectText = Get-Content -Path (Join-Path $projectRoot "pyproject.toml") -Raw
    if ($pyprojectText -notmatch 'version\s*=\s*"([^"]+)"') {
        throw "Unable to read project version from pyproject.toml"
    }
    $env:DATALAB_APP_VERSION = $Matches[1]
    $env:DATALAB_WINDOWS_DIST_DIR = Join-Path $distDir "DataLab"
    $env:DATALAB_WINDOWS_INSTALLER_DIR = $distDir
    $iscc = $InnoSetupPath
    if (-not $iscc) {
        $candidate = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) {
            $iscc = $candidate
        } else {
            $iscc = "ISCC.exe"
        }
    }
    Invoke-WithArgs @($iscc) @((Join-Path $projectRoot "packaging\windows\DataLab.iss"))
}
```

- [ ] **Step 5: Run packaging tests**

Run:

```bash
pytest -q tests/test_update_packaging_scripts.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packaging/windows/DataLab.iss build_windows_data_gui.ps1 tests/test_update_packaging_scripts.py
git commit -m "feat: add Windows Inno installer packaging"
```

## Task 11: Focused Integration And Static Safety Tests

**Files:**
- Modify only if failures expose issues:
  - `shared/update_payload.py`
  - `app_desktop/update_controller.py`
  - `app_desktop/update_installer.py`
  - packaging scripts

- [ ] **Step 1: Run focused updater tests**

Run:

```bash
pytest -q tests/test_update_checker.py tests/test_update_payload.py tests/test_update_preferences.py tests/test_update_installer.py tests/test_update_controller.py tests/test_desktop_update_menu.py tests/test_generate_updates_manifest.py tests/test_update_packaging_scripts.py
```

Expected: PASS.

- [ ] **Step 2: Run Qt offscreen desktop neighbors**

Run:

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_update_menu.py tests/test_desktop_about_dialog.py tests/test_desktop_workspace_menu.py tests/test_gui_shim_exports.py
```

Expected: PASS.

- [ ] **Step 3: Compile touched modules**

Run:

```bash
python -m compileall -q shared app_desktop tools data_extrapolation_gui.py
```

Expected: exits 0 with no output.

- [ ] **Step 4: Static safety scan**

Run:

```bash
rg -n "<remote-argv-or-private-path-regex>" shared app_desktop tools packaging docs/superpowers/specs/2026-05-26-datalab-installer-auto-update-design.md
```

Expected: no unsafe updater findings. Existing historical local-only planning files are outside this scan.

- [ ] **Step 5: Commit fixes if any**

If any fixes were required:

```bash
git add shared app_desktop tools packaging tests build_mac_data_gui.sh build_windows_data_gui.ps1
git commit -m "fix: polish installer update integration"
```

If no fixes were required, do not create an empty commit.

## Task 12: Local Packaging Smoke Tests

**Files:**
- No source edits expected.

- [ ] **Step 1: Build macOS app without pkg**

Run:

```bash
./build_mac_data_gui.sh
```

Expected: `dist/DataLab.app` exists and launches.

- [ ] **Step 2: Build macOS pkg when local signing prerequisites are available**

Run:

```bash
DATALAB_BUILD_PKG=1 ./build_mac_data_gui.sh
```

Expected:
- If `DATALAB_MAC_INSTALLER_IDENTITY` is set and valid, the generated `dist/DataLab-${VERSION}-macOS.pkg` is signed.
- If the identity is absent, the pkg may be created but is not auto-installable; record that signing gate is not satisfied.

- [ ] **Step 3: Generate manifest from local assets**

Run:

```bash
VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
python tools/generate_updates_manifest.py \
  --version "$VERSION" \
  --release-url "https://github.com/yilibinbin/DataLab/releases/tag/vTEST" \
  --notes-file CHANGELOG.md \
  --published-at "2026-05-26T00:00:00Z" \
  --min-client-version "2.2.0" \
  --macos-pkg "dist/DataLab-${VERSION}-macOS.pkg" \
  --output "dist/updates.json"
```

Expected: `dist/updates.json` contains `size_bytes`, `sha256`, and no installer arguments.

- [ ] **Step 4: Windows packaging on remote host**

Run from macOS after syncing source to the Windows build machine:

```bash
ssh <windows-builder> "powershell -NoProfile -ExecutionPolicy Bypass -File <checkout>\\build_windows_data_gui.ps1 -BuildInnoInstaller"
```

Expected:
- PyInstaller app directory is produced.
- If Inno Setup is installed, `DataLab-${VERSION}-Windows-x64.exe` is produced.
- If code-signing certificate is unavailable, record that the installer is not auto-installable for public release.

- [ ] **Step 5: Do not publish auto-installable release until signing gates pass**

Expected: Release checklist explicitly records whether macOS notarization and Windows Authenticode signing passed. If either fails, upload can still include assets for manual download, but `updates.json` must omit that platform or the app must fall back to release page for that platform.

## Task 13: Full Verification And Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/TEST_MATRIX.md` if it exists and tracks release tests.

- [ ] **Step 1: Add changelog entry**

Add a public-facing changelog bullet:

```markdown
- Added a user-authorized installer-based update flow with release-note prompts, offline-friendly automatic checks, installer integrity verification, and platform installer packaging hooks.
```

- [ ] **Step 2: Add release test matrix note**

If `docs/TEST_MATRIX.md` exists, add:

```markdown
### Installer Update Release Gate

- macOS `.pkg` is signed and notarized before auto-installable release status.
- Windows Inno installer is Authenticode-signed before auto-installable release status.
- `updates.json` contains only metadata, size, and SHA-256 values; installer arguments are constructed by application code.
- Offline startup performs no network request unless automatic updates were enabled.
```

- [ ] **Step 3: Run full verification**

Run:

```bash
python -m compileall -q shared app_desktop tools data_extrapolation_gui.py
QT_QPA_PLATFORM=offscreen pytest -q
```

Expected: full suite passes, with existing skips/warnings only.

- [ ] **Step 4: Public wording scan**

Run:

```bash
rg -n "<private-or-local-release-wording-regex>" CHANGELOG.md docs README.md app_desktop shared tools packaging
```

Expected: no new public-facing private/local wording. If existing non-public planning files match, exclude them from the release commit.

- [ ] **Step 5: Commit docs**

```bash
git add CHANGELOG.md docs/TEST_MATRIX.md
git commit -m "docs: document installer update release gate"
```

If `docs/TEST_MATRIX.md` does not exist, omit it from `git add`.

## Final Review Gate

- [ ] Request code review using `superpowers:requesting-code-review`.
- [ ] Ask reviewers to focus on:
  - trust model and signing gate;
  - no manifest-controlled argv;
  - no startup network when auto updates are off;
  - cache lock and re-entrancy behavior;
  - download size/hash verification;
  - PyInstaller shim/export regressions;
  - packaging scripts not leaking local paths.
- [ ] Address accepted review findings.
- [ ] Re-run focused tests and compile checks after fixes.

## Final Verification Commands

```bash
pytest -q tests/test_update_checker.py tests/test_update_payload.py tests/test_update_preferences.py tests/test_update_installer.py tests/test_update_controller.py tests/test_desktop_update_menu.py tests/test_generate_updates_manifest.py tests/test_update_packaging_scripts.py
QT_QPA_PLATFORM=offscreen pytest -q tests/test_desktop_update_menu.py tests/test_desktop_about_dialog.py tests/test_desktop_workspace_menu.py tests/test_gui_shim_exports.py
python -m compileall -q shared app_desktop tools data_extrapolation_gui.py
QT_QPA_PLATFORM=offscreen pytest -q
```

## Self-Review Checklist

- [ ] Spec coverage: every confirmed spec section maps to at least one task.
- [ ] Trust model: plan does not claim SHA-256 proves authenticity.
- [ ] Command safety: no manifest-controlled installer argv exists in snippets.
- [ ] Offline behavior: startup auto check is opt-in only.
- [ ] Public wording: release docs exclude local paths, SSH hosts, and temporary-machine details.
