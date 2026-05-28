from __future__ import annotations

import pytest

from app_desktop.update_dialogs import build_update_message, build_update_titles
from shared.update_payload import InstallerAsset, UpdatePayload


def _payload(platform_key: str) -> UpdatePayload:
    suffix = "pkg" if platform_key == "macos" else "exe"
    return UpdatePayload(
        version="2.2.2",
        notes="## Summary\n- Fix update dialogs\n",
        published_at="2026-05-28T01:00:00Z",
        release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.2.2",
        asset=InstallerAsset(
            platform_key=platform_key,
            name=f"DataLab-2.2.2-{platform_key}.{suffix}",
            url="https://example.invalid/installer",
            sha256="0" * 64,
            size_bytes=67_827_102,
        ),
    )


def test_update_titles_are_localized() -> None:
    assert build_update_titles("zh").available == "发现新版本"
    assert build_update_titles("zh").update_failed == "更新失败"
    assert build_update_titles("en").available == "Update Available"
    assert build_update_titles("en").update_failed == "Update Failed"


def test_zh_message_only_mentions_selected_platform() -> None:
    message = build_update_message(_payload("macos"), "2.2.1", "zh")

    assert "发现新版本 2.2.2，当前版本为 2.2.1。" in message
    assert "适用系统：macOS" in message
    assert "安装包：DataLab-2.2.2-macos.pkg (64.69 MB)" in message
    assert "Windows x64" not in message
    assert "macOS 可能显示安全提示" in message


def test_en_message_only_mentions_selected_platform() -> None:
    message = build_update_message(_payload("windows-x64"), "2.2.1", "en")

    assert "Version 2.2.2 is available. Current version: 2.2.1." in message
    assert "Platform: Windows x64" in message
    assert "Installer: DataLab-2.2.2-windows-x64.exe (64.69 MB)" in message
    assert "macOS security prompt" not in message
    assert "Windows may show an administrator prompt" in message


def test_unknown_platform_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported update platform"):
        build_update_message(_payload("linux-x64"), "2.2.1", "en")
