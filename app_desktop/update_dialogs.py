"""Plain-text update dialog messages for DataLab desktop."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from shared.update_checker import format_release_notes_for_dialog
from shared.update_payload import UpdatePayload


@dataclass(frozen=True)
class UpdateDialogTitles:
    available: str
    manual_update_required: str
    check_failed: str
    up_to_date: str
    update_failed: str


def build_update_titles(lang: str) -> UpdateDialogTitles:
    if lang == "en":
        return UpdateDialogTitles(
            available="Update Available",
            manual_update_required="Manual Update Required",
            check_failed="Update Check Failed",
            up_to_date="Up To Date",
            update_failed="Update Failed",
        )
    return UpdateDialogTitles(
        available="发现新版本",
        manual_update_required="需要手动更新",
        check_failed="检查更新失败",
        up_to_date="已是最新版本",
        update_failed="更新失败",
    )


def _platform_label(platform_key: str) -> str:
    if platform_key == "macos":
        return "macOS"
    if platform_key == "windows-x64":
        return "Windows x64"
    raise ValueError(f"Unsupported update platform: {platform_key}")


def _platform_warning(platform_key: str, lang: str) -> str:
    if platform_key == "macos":
        if lang == "en":
            return "macOS security prompt may appear."
        return "macOS 可能显示安全提示。"
    if platform_key == "windows-x64":
        if lang == "en":
            return "Windows may show an administrator prompt."
        return "Windows 可能显示管理员授权提示。"
    raise ValueError(f"Unsupported update platform: {platform_key}")


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        size = ceil(size_bytes / (1024 * 1024) * 100) / 100
        return f"{size:.2f} MB"
    if size_bytes >= 1024:
        size = ceil(size_bytes / 1024 * 100) / 100
        return f"{size:.2f} KB"
    return f"{size_bytes} B"


def build_update_message(
    payload: UpdatePayload,
    current_version: str,
    lang: str,
    was_skipped: bool = False,
) -> str:
    notes = format_release_notes_for_dialog(payload.notes)
    platform = _platform_label(payload.asset.platform_key)
    warning = _platform_warning(payload.asset.platform_key, lang)
    size = _format_size(payload.asset.size_bytes)
    if lang == "en":
        skipped = "\n\nYou previously skipped this version." if was_skipped else ""
        return (
            f"Version {payload.version} is available. Current version: {current_version}.\n\n"
            f"Published: {payload.published_at}\n"
            f"Platform: {platform}\n"
            f"Installer: {payload.asset.name} ({size})\n"
            f"Release: {payload.release_url}\n\n"
            f"Release notes:\n{notes}\n\n"
            f"{warning} "
            "DataLab will close after the installer starts."
            f"{skipped}"
        )

    skipped = "\n\n此前已跳过此版本。" if was_skipped else ""
    return (
        f"发现新版本 {payload.version}，当前版本为 {current_version}。\n\n"
        f"发布时间：{payload.published_at}\n"
        f"适用系统：{platform}\n"
        f"安装包：{payload.asset.name} ({size})\n"
        f"发布页面：{payload.release_url}\n\n"
        f"本次更新内容：\n{notes}\n\n"
        f"{warning} 安装器启动后 DataLab 将关闭。"
        f"{skipped}"
    )


def build_post_update_notice(
    *,
    version: str,
    notes: str,
    url: str,
    published_at: str,
    lang: str,
) -> str:
    formatted_notes = format_release_notes_for_dialog(notes)
    if lang == "en":
        published = f"Published: {published_at}\n" if published_at else ""
        release = f"Release: {url}\n\n" if url else "\n"
        return (
            f"DataLab has been updated to version {version}.\n\n"
            f"{published}"
            f"{release}"
            f"Release notes:\n{formatted_notes}"
        )

    published = f"发布时间：{published_at}\n" if published_at else ""
    release = f"发布页面：{url}\n\n" if url else "\n"
    return (
        f"DataLab 已更新到版本 {version}。\n\n"
        f"{published}"
        f"{release}"
        f"本次更新内容：\n{formatted_notes}"
    )
