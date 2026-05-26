"""Plain-text update dialog messages for DataLab desktop."""

from __future__ import annotations

from shared.update_checker import format_release_notes_for_dialog
from shared.update_payload import UpdatePayload


def build_update_message(
    payload: UpdatePayload,
    current_version: str,
    lang: str,
    was_skipped: bool = False,
) -> str:
    notes = format_release_notes_for_dialog(payload.notes)
    if lang == "en":
        skipped = "\n\nYou previously skipped this version." if was_skipped else ""
        return (
            f"Version {payload.version} is available. Current version: {current_version}.\n\n"
            f"Published: {payload.published_at}\n"
            f"Installer: {payload.asset.name} ({payload.asset.size_bytes} bytes)\n"
            f"Release: {payload.release_url}\n\n"
            f"Release notes:\n{notes}\n\n"
            "OS security or administrator prompts may appear. "
            "DataLab will close after the installer starts."
            f"{skipped}"
        )

    skipped = "\n\n此前已跳过此版本。" if was_skipped else ""
    return (
        f"发现新版本 {payload.version}，当前版本为 {current_version}。\n\n"
        f"发布时间：{payload.published_at}\n"
        f"安装包：{payload.asset.name}（{payload.asset.size_bytes} bytes）\n"
        f"发布页面：{payload.release_url}\n\n"
        f"本次更新内容：\n{notes}\n\n"
        "系统可能显示安全或管理员授权提示。安装器启动后 DataLab 将关闭。"
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
