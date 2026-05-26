from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Literal, cast

import pytest

from shared.update_checker import ReleaseAsset, ReleaseInfo


Manifest = dict[str, Any]
ManifestMutation = Callable[[Manifest], None]

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


def valid_manifest() -> Manifest:
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
                "url": "https://manifest.invalid/mac.pkg",
                "sha256": SHA_MAC,
                "size_bytes": 125,
            },
            "windows-x64": {
                "name": "DataLab-2.3.0-Windows-x64.exe",
                "url": "https://manifest.invalid/win.exe",
                "sha256": SHA_WIN,
                "size_bytes": 140,
            },
        },
    }


def macos_release() -> ReleaseInfo:
    return release_with_assets(
        ReleaseAsset("DataLab-2.3.0-macOS.pkg", "https://example.invalid/mac.pkg", 125),
    )


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


def _macos_asset(data: Manifest) -> Manifest:
    return cast(Manifest, data["assets"]["macos"])


def _bad_schema_version(data: Manifest) -> None:
    data["schema_version"] = 2


def _bad_version(data: Manifest) -> None:
    data["version"] = "9.9.9"


def _bad_sha256(data: Manifest) -> None:
    _macos_asset(data)["sha256"] = "bad"


def _zero_size(data: Manifest) -> None:
    _macos_asset(data)["size_bytes"] = 0


def _missing_platform(data: Manifest) -> None:
    data["assets"].pop("macos")


def _too_new_min_client(data: Manifest) -> None:
    data["min_client_version"] = "9.0.0"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_bad_schema_version, "unsupported schema_version"),
        (_bad_version, "version does not match"),
        (_bad_sha256, "sha256"),
        (_zero_size, "size_bytes"),
        (_missing_platform, "platform"),
        (_too_new_min_client, "too old"),
    ],
)
def test_validate_manifest_rejects_invalid_metadata(
    mutation: ManifestMutation,
    message: str,
) -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    mutation(manifest)

    with pytest.raises(UpdatePayloadError, match=message):
        select_update_payload(
            release=macos_release(),
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


@pytest.mark.parametrize("current_version", ["2.0.0.dev0", "2.0.0rc1"])
def test_min_client_version_respects_prerelease_ordering(current_version: str) -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    manifest["min_client_version"] = "2.0.0"

    with pytest.raises(UpdatePayloadError, match="too old"):
        select_update_payload(
            release=macos_release(),
            manifest=manifest,
            platform_key="macos",
            current_version=current_version,
        )


def test_min_client_version_accepts_post_release_client() -> None:
    from shared.update_payload import select_update_payload

    manifest = valid_manifest()
    manifest["min_client_version"] = "2.0.0"

    payload = select_update_payload(
        release=macos_release(),
        manifest=manifest,
        platform_key="macos",
        current_version="2.0.0.post1",
    )

    assert payload.version == "2.3.0"


@pytest.mark.parametrize(
    ("asset_name", "message"),
    [
        ("", "asset name"),
        ("../evil.pkg", "asset name"),
        ("/tmp/evil.pkg", "asset name"),
        ("DataLab-\x1f.pkg", "asset name"),
        ("DataLab-2.3.0-macOS.exe", "asset suffix"),
    ],
)
def test_manifest_asset_name_is_restricted(asset_name: str, message: str) -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    _macos_asset(manifest)["name"] = asset_name
    release = release_with_assets(ReleaseAsset(asset_name, "https://example.invalid/asset", 125))

    with pytest.raises(UpdatePayloadError, match=message):
        select_update_payload(
            release=release,
            manifest=manifest,
            platform_key="macos",
            current_version="2.2.0",
        )


def test_manifest_release_url_rejects_query_string() -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    manifest["release_url"] = "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0?x=1"

    with pytest.raises(UpdatePayloadError, match="release_url"):
        select_update_payload(
            release=macos_release(),
            manifest=manifest,
            platform_key="macos",
            current_version="2.2.0",
        )


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._offset = 0

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        return False

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._content):
            return b""
        if size is None or size < 0:
            size = len(self._content) - self._offset
        start = self._offset
        end = min(start + size, len(self._content))
        self._offset = end
        return self._content[start:end]


def test_download_installer_verifies_size_and_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    seen: dict[str, object] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["user_agent"] = request.headers.get("User-agent")
        return FakeResponse(content)

    monkeypatch.setattr(update_payload, "_urlopen", fake_urlopen)
    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    path = download_and_verify_installer(asset, timeout=7)

    assert seen == {
        "url": asset.url,
        "timeout": 7,
        "user_agent": "DataLab Update Checker",
    }
    assert path == tmp_path / asset.name
    assert path.read_bytes() == content
    assert not (tmp_path / f"{asset.name}.part").exists()


def test_download_installer_deletes_bad_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import update_payload
    from shared.update_payload import InstallerAsset, UpdatePayloadError, download_and_verify_installer

    asset = InstallerAsset(
        platform_key="macos",
        name="DataLab-2.3.0-macOS.pkg",
        url="https://example.invalid/mac.pkg",
        sha256="0" * 64,
        size_bytes=9,
    )

    def fake_urlopen(_request: Any, _timeout: float) -> FakeResponse:
        return FakeResponse(b"installer")

    monkeypatch.setattr(update_payload, "_urlopen", fake_urlopen)
    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    with pytest.raises(UpdatePayloadError, match="sha256 mismatch"):
        download_and_verify_installer(asset)

    assert not (tmp_path / asset.name).exists()
    assert not (tmp_path / f"{asset.name}.part").exists()


def test_update_lock_rejects_second_holder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import update_payload
    from shared.update_payload import UpdateCacheLock, UpdatePayloadError

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    with UpdateCacheLock():
        with pytest.raises(UpdatePayloadError, match="already in progress"):
            with UpdateCacheLock():
                pass
