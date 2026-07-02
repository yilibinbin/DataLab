from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Literal, cast

import pytest

from shared.update_checker import ReleaseAsset, ReleaseInfo


Manifest = dict[str, Any]
ManifestMutation = Callable[[Manifest], None]

SHA_MAC = "0" * 64
SHA_WIN = "1" * 64
TEST_SIGNING_KEY_ID = "test-key"
TEST_PRIVATE_KEY_B64 = "arq5WLNRcnCZW5b+LGSYraZ0boKTF5oCDOo8Wn6jwf4="
TEST_PUBLIC_KEY_B64 = "CSrQ+417vi16q+8rxYk7X6x58RDmkQH0WVq168r2ArU="


@pytest.fixture(autouse=True)
def _use_test_update_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.update_signing as update_signing

    monkeypatch.setattr(
        update_signing,
        "DEFAULT_UPDATE_PUBLIC_KEYS",
        {TEST_SIGNING_KEY_ID: TEST_PUBLIC_KEY_B64},
    )


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
    from shared.update_signing import sign_manifest

    return sign_manifest({
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
    }, private_key_b64=TEST_PRIVATE_KEY_B64, key_id=TEST_SIGNING_KEY_ID)


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


def _resign(data: Manifest) -> Manifest:
    from shared.update_signing import sign_manifest

    return sign_manifest(data, private_key_b64=TEST_PRIVATE_KEY_B64, key_id=TEST_SIGNING_KEY_ID)


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
    if message != "unsupported schema_version":
        manifest = _resign(manifest)

    with pytest.raises(UpdatePayloadError, match=message):
        select_update_payload(
            release=macos_release(),
            manifest=manifest,
            platform_key="macos",
            current_version="2.2.0",
        )


def test_manifest_with_installable_assets_requires_signature() -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    manifest.pop("signature")

    with pytest.raises(UpdatePayloadError, match="signature"):
        select_update_payload(
            release=macos_release(),
            manifest=manifest,
            platform_key="macos",
            current_version="2.2.0",
        )


def test_manifest_signature_detects_tampering() -> None:
    from shared.update_payload import UpdatePayloadError, select_update_payload

    manifest = valid_manifest()
    _macos_asset(manifest)["size_bytes"] = 126

    with pytest.raises(UpdatePayloadError, match="signature"):
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
    manifest = _resign(manifest)

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
    manifest = _resign(manifest)

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
    manifest = _resign(manifest)
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
    manifest = _resign(manifest)

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


class ChunkedFakeResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._offset = 0

    def __enter__(self) -> ChunkedFakeResponse:
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        return False

    def read(self, _size: int = -1) -> bytes:
        if self._offset >= len(self._chunks):
            raise AssertionError("download continued after declared size overflow")
        chunk = self._chunks[self._offset]
        self._offset += 1
        return chunk


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


def test_download_installer_deletes_declared_size_overflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import update_payload
    from shared.update_payload import InstallerAsset, UpdatePayloadError, download_and_verify_installer

    declared_content = b"installer"
    asset = InstallerAsset(
        platform_key="macos",
        name="DataLab-2.3.0-macOS.pkg",
        url="https://example.invalid/mac.pkg",
        sha256=hashlib.sha256(declared_content).hexdigest(),
        size_bytes=len(declared_content),
    )

    def fake_urlopen(_request: Any, _timeout: float) -> ChunkedFakeResponse:
        return ChunkedFakeResponse([declared_content, b"x"])

    monkeypatch.setattr(update_payload, "_urlopen", fake_urlopen)
    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)

    with pytest.raises(UpdatePayloadError, match="size mismatch"):
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


def test_update_lock_replaces_stale_holder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import update_payload
    from shared.update_payload import UpdateCacheLock

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)
    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("stale", encoding="utf-8")
    stale_time = time.time() - 20
    os.utime(lock_path, (stale_time, stale_time))

    with UpdateCacheLock(stale_after_seconds=1):
        assert lock_path.read_text(encoding="utf-8").startswith(f"{os.getpid()}:")

    assert not lock_path.exists()


def test_update_lock_rejects_fresh_holder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import update_payload
    from shared.update_payload import UpdateCacheLock, UpdatePayloadError

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)
    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("fresh", encoding="utf-8")

    with pytest.raises(UpdatePayloadError, match="already in progress"):
        with UpdateCacheLock(stale_after_seconds=60):
            pass

    assert lock_path.read_text(encoding="utf-8") == "fresh"


def test_update_lock_retries_when_stale_lock_disappears_during_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import update_payload
    from shared.update_payload import UpdateCacheLock

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)
    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("stale", encoding="utf-8")

    real_stat = Path.stat
    calls = 0

    def flaky_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        nonlocal calls
        if path == lock_path and calls == 0:
            calls += 1
            lock_path.unlink()
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    with UpdateCacheLock(stale_after_seconds=1):
        assert lock_path.read_text(encoding="utf-8").startswith(f"{os.getpid()}:")

    assert calls == 1


def test_update_lock_does_not_remove_fresh_lock_that_replaces_stale_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared import update_payload
    from shared.update_payload import UpdateCacheLock, UpdatePayloadError

    monkeypatch.setattr(update_payload, "update_cache_dir", lambda: tmp_path)
    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("stale", encoding="utf-8")
    stale_time = time.time() - 20
    os.utime(lock_path, (stale_time, stale_time))

    real_stat = Path.stat
    replaced = False
    stat_calls = 0

    def racing_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        nonlocal replaced, stat_calls
        if path == lock_path:
            stat_calls += 1
        if path == lock_path and stat_calls == 2 and not replaced:
            replaced = True
            stale_stat = real_stat(path, *args, **kwargs)
            lock_path.unlink()
            lock_path.write_text("fresh", encoding="utf-8")
            return stale_stat
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", racing_stat)

    with pytest.raises(UpdatePayloadError, match="already in progress"):
        with UpdateCacheLock(stale_after_seconds=1):
            pass

    assert replaced is True
    assert lock_path.read_text(encoding="utf-8") == "fresh"


def test_urlopen_uses_certifi_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    """The installer download path must verify HTTPS with certifi's CA bundle.

    Regression for audit F8: update_checker._urlopen already builds a
    certifi-backed SSL context, but update_payload._urlopen used a bare
    urllib.request.urlopen with no context. On frozen builds whose default
    OpenSSL context lacks a system CA store, the check path could advertise an
    update the download path could never fetch.
    """
    from shared import update_payload

    seen: dict[str, object] = {}
    fake_context = object()

    class FakeCertifi:
        @staticmethod
        def where() -> str:
            return "/tmp/cacert.pem"

    def fake_create_default_context(*, cafile: str | None = None) -> object:
        seen["cafile"] = cafile
        return fake_context

    def fake_urlopen(request: Any, timeout: float, context: object) -> FakeResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["context"] = context
        return FakeResponse(b"")

    monkeypatch.setattr(update_payload, "certifi", FakeCertifi)
    monkeypatch.setattr(update_payload.ssl, "create_default_context", fake_create_default_context)
    monkeypatch.setattr(update_payload.urllib.request, "urlopen", fake_urlopen)

    request = update_payload.urllib.request.Request("https://example.invalid")
    with update_payload._urlopen(request, 4) as response:
        response.read()

    assert seen == {
        "cafile": "/tmp/cacert.pem",
        "url": "https://example.invalid",
        "timeout": 4,
        "context": fake_context,
    }
