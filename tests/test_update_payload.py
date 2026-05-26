from __future__ import annotations

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
    ("mutation", "message"),
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
