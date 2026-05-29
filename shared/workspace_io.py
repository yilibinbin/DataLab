from __future__ import annotations

import json
import os
import posixpath
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .workspace_schema import (
    MAX_MANIFEST_BYTES,
    MAX_PLOT_ATTACHMENTS,
    MAX_PLOT_BYTES,
    MAX_SOURCE_ATTACHMENTS,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    WorkspaceValidationError,
    collect_manifest_attachment_paths,
    validate_manifest,
    validate_manifest_attachment_hashes,
)

_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = 0o100644 << 16


@dataclass(frozen=True)
class WorkspaceReadResult:
    manifest: dict[str, Any]
    attachments: dict[str, bytes]


def _normalize_archive_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("\\"):
        raise WorkspaceValidationError(f"unsafe archive path: {name!r}")
    if len(raw) >= 2 and raw[1] == ":":
        raise WorkspaceValidationError(f"unsafe archive path: {name!r}")
    raw_parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise WorkspaceValidationError(f"unsafe archive path: {name!r}")
    normalized = posixpath.normpath(raw)
    parts = normalized.split("/")
    if normalized in {"", "."} or any(part in {"", ".", ".."} for part in parts):
        raise WorkspaceValidationError(f"unsafe archive path: {name!r}")
    if normalized == "manifest.json":
        return normalized
    if normalized.startswith("attachments/sources/") or normalized.startswith("attachments/plots/"):
        return normalized
    raise WorkspaceValidationError(f"unsupported archive path: {name!r}")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _validate_zip_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    normalized: dict[str, zipfile.ZipInfo] = {}
    manifest_count = 0
    plot_count = 0
    source_count = 0
    total_size = 0
    for info in zf.infolist():
        name = _normalize_archive_name(info.filename)
        if name in normalized:
            raise WorkspaceValidationError(f"duplicate archive entry: {name}")
        if _is_symlink(info):
            raise WorkspaceValidationError(f"symlink entries are not allowed: {name}")
        if info.is_dir():
            raise WorkspaceValidationError(f"directory entries are not allowed: {name}")
        total_size += info.file_size
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise WorkspaceValidationError("workspace exceeds total uncompressed size limit")
        if name == "manifest.json":
            manifest_count += 1
            if info.file_size > MAX_MANIFEST_BYTES:
                raise WorkspaceValidationError("manifest exceeds size limit")
        elif name.startswith("attachments/plots/"):
            plot_count += 1
            if not name.endswith(".png"):
                raise WorkspaceValidationError(f"plot attachment must be png: {name}")
            if info.file_size > MAX_PLOT_BYTES:
                raise WorkspaceValidationError(f"plot attachment exceeds size limit: {name}")
        elif name.startswith("attachments/sources/"):
            source_count += 1
            if info.file_size > MAX_SOURCE_BYTES:
                raise WorkspaceValidationError(f"source attachment exceeds size limit: {name}")
        normalized[name] = info
    if manifest_count != 1:
        raise WorkspaceValidationError("workspace must contain exactly one manifest.json")
    if plot_count > MAX_PLOT_ATTACHMENTS:
        raise WorkspaceValidationError("too many plot attachments")
    if source_count > MAX_SOURCE_ATTACHMENTS:
        raise WorkspaceValidationError("too many source attachments")
    return normalized


def _load_and_validate(path: Path) -> WorkspaceReadResult:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            members = _validate_zip_members(zf)
            manifest_bytes = zf.read(members["manifest.json"])
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkspaceValidationError("manifest must be valid UTF-8 JSON") from exc
            validate_manifest(manifest)
            expected_paths = collect_manifest_attachment_paths(manifest)
            attachments: dict[str, bytes] = {}
            for archive_name in expected_paths:
                normalized = _normalize_archive_name(archive_name)
                if normalized not in members:
                    raise WorkspaceValidationError(f"missing attachment: {normalized}")
                attachments[normalized] = zf.read(members[normalized])
            validate_manifest_attachment_hashes(manifest, attachments)
            return WorkspaceReadResult(manifest=manifest, attachments=attachments)
    except zipfile.BadZipFile as exc:
        raise WorkspaceValidationError("workspace is not a valid ZIP file") from exc


def read_workspace(path: str | Path) -> WorkspaceReadResult:
    return _load_and_validate(Path(path))


def _deterministic_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = _ZIP_FILE_MODE
    return info


def write_workspace(
    path: str | Path,
    manifest: dict[str, Any],
    attachments: dict[str, bytes] | None = None,
) -> None:
    target = Path(path)
    validate_manifest(manifest)
    attachments = dict(attachments or {})
    expected_paths = collect_manifest_attachment_paths(manifest)
    normalized_attachments: dict[str, bytes] = {}
    for name, data in attachments.items():
        normalized = _normalize_archive_name(name)
        if normalized not in expected_paths:
            raise WorkspaceValidationError(f"unlisted attachment: {normalized}")
        if not isinstance(data, bytes):
            raise WorkspaceValidationError(f"attachment must be bytes: {normalized}")
        normalized_attachments[normalized] = data
    missing = expected_paths.difference(normalized_attachments)
    if missing:
        raise WorkspaceValidationError(f"missing attachment: {sorted(missing)[0]}")
    validate_manifest_attachment_hashes(manifest, normalized_attachments)

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as raw:
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                zf.writestr(
                    _deterministic_zip_info("manifest.json"),
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                )
                for name in sorted(normalized_attachments):
                    zf.writestr(_deterministic_zip_info(name), normalized_attachments[name])
            raw.flush()
            os.fsync(raw.fileno())
        _load_and_validate(Path(tmp_name))
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
