from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .archive_validation import (
    ArchiveMemberRule,
    ArchiveValidationError,
    ArchiveValidationPolicy,
    normalize_archive_member_name,
    validate_archive_members,
    validate_archive_payloads,
)
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
_WORKSPACE_ARCHIVE_POLICY = ArchiveValidationPolicy(
    rules=(
        ArchiveMemberRule(
            exact_path="manifest.json",
            max_file_bytes=MAX_MANIFEST_BYTES,
            file_size_error="manifest exceeds size limit",
        ),
        ArchiveMemberRule(
            prefix="attachments/plots/",
            required_suffix=".png",
            max_count=MAX_PLOT_ATTACHMENTS,
            max_file_bytes=MAX_PLOT_BYTES,
            count_error="too many plot attachments",
            file_size_error="plot attachment exceeds size limit: {name}",
            suffix_error="plot attachment must be png: {name}",
        ),
        ArchiveMemberRule(
            prefix="attachments/sources/",
            max_count=MAX_SOURCE_ATTACHMENTS,
            max_file_bytes=MAX_SOURCE_BYTES,
            count_error="too many source attachments",
            file_size_error="source attachment exceeds size limit: {name}",
        ),
    ),
    total_uncompressed_bytes=MAX_TOTAL_UNCOMPRESSED_BYTES,
    total_size_error="workspace exceeds total uncompressed size limit",
)


@dataclass(frozen=True)
class WorkspaceReadResult:
    manifest: dict[str, Any]
    attachments: dict[str, bytes]


def _normalize_archive_name(name: str) -> str:
    try:
        return normalize_archive_member_name(name, _WORKSPACE_ARCHIVE_POLICY)
    except ArchiveValidationError as exc:
        raise WorkspaceValidationError(str(exc)) from exc


def _validate_zip_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    try:
        normalized = validate_archive_members(zf, _WORKSPACE_ARCHIVE_POLICY)
    except ArchiveValidationError as exc:
        raise WorkspaceValidationError(str(exc)) from exc
    if "manifest.json" not in normalized:
        raise WorkspaceValidationError("workspace must contain exactly one manifest.json")
    return normalized


def _load_and_validate(path: Path) -> WorkspaceReadResult:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            members = _validate_zip_members(zf)
            manifest_bytes = _read_zip_member(zf, members["manifest.json"])
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkspaceValidationError("manifest must be valid UTF-8 JSON") from exc
            manifest, expected_paths, hash_validator = _validated_manifest_dispatch(manifest)
            attachments: dict[str, bytes] = {}
            for archive_name in expected_paths:
                normalized = _normalize_archive_name(archive_name)
                if normalized not in members:
                    raise WorkspaceValidationError(f"missing attachment: {normalized}")
                attachments[normalized] = _read_zip_member(zf, members[normalized])
            try:
                validate_archive_payloads(
                    attachments,
                    hash_hook=lambda payloads: hash_validator(manifest, dict(payloads)),
                )
            except ArchiveValidationError as exc:
                raise WorkspaceValidationError(str(exc)) from exc
            return WorkspaceReadResult(manifest=manifest, attachments=attachments)
    except zipfile.BadZipFile as exc:
        raise WorkspaceValidationError("workspace is not a valid ZIP file") from exc


def _read_zip_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    try:
        return zf.read(info)
    except (RuntimeError, NotImplementedError, zipfile.BadZipFile, OSError, EOFError) as exc:
        raise WorkspaceValidationError(f"unreadable archive entry: {info.filename}") from exc


def _validated_manifest_dispatch(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], set[str], Any]:
    if manifest.get("schema") == "datalab.workspace.v2" or manifest.get("schema_version") == 2:
        from datalab_core import workspace_v2

        try:
            workspace_v2.validate_manifest(manifest)
            compatible = workspace_v2.to_compatible_manifest(manifest)
        except TypeError as exc:
            raise WorkspaceValidationError(str(exc)) from exc
        return compatible, collect_manifest_attachment_paths(compatible), validate_manifest_attachment_hashes

    validate_manifest(manifest)
    return manifest, collect_manifest_attachment_paths(manifest), validate_manifest_attachment_hashes


def read_workspace(path: str | Path) -> WorkspaceReadResult:
    return _load_and_validate(Path(path))


def _deterministic_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
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
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as zf:
                zf.writestr(
                    _deterministic_zip_info("manifest.json"),
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
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
