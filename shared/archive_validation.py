from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


class ArchiveValidationError(ValueError):
    """Raised when an archive member is unsafe or violates a validation policy."""


@dataclass(frozen=True)
class ArchiveMemberRule:
    exact_path: str | None = None
    prefix: str | None = None
    required_suffix: str | None = None
    max_count: int | None = None
    max_file_bytes: int | None = None
    max_combined_bytes: int | None = None
    count_error: str | None = None
    file_size_error: str | None = None
    combined_size_error: str | None = None
    suffix_error: str | None = None

    def __post_init__(self) -> None:
        if (self.exact_path is None) == (self.prefix is None):
            raise ValueError("archive member rule must define exactly one of exact_path or prefix")

    @property
    def label(self) -> str:
        return self.exact_path if self.exact_path is not None else str(self.prefix)

    def matches(self, name: str) -> bool:
        if self.exact_path is not None:
            return name == self.exact_path
        return name.startswith(str(self.prefix))


@dataclass(frozen=True)
class ArchiveValidationPolicy:
    rules: tuple[ArchiveMemberRule, ...]
    total_uncompressed_bytes: int | None = None
    unsafe_path_error: str = "unsafe archive path: {raw!r}"
    unsupported_path_error: str = "unsupported archive path: {raw!r}"
    duplicate_error: str = "duplicate archive entry: {name}"
    symlink_error: str = "symlink entries are not allowed: {name}"
    directory_error: str = "directory entries are not allowed: {name}"
    total_size_error: str = "archive exceeds total uncompressed size limit"
    encrypted_error: str = "encrypted archive entries are not allowed: {name}"
    compression_error: str = "unsupported archive compression method: {name}"


ArchivePayloadHook = Callable[[Mapping[str, bytes]], None]
_SUPPORTED_COMPRESSION_METHODS = {
    zipfile.ZIP_STORED,
    zipfile.ZIP_DEFLATED,
    getattr(zipfile, "ZIP_BZIP2", -1),
    getattr(zipfile, "ZIP_LZMA", -1),
}


def normalize_archive_member_name(name: str, policy: ArchiveValidationPolicy) -> str:
    raw = name.replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("\\"):
        raise ArchiveValidationError(policy.unsafe_path_error.format(raw=name))
    if len(raw) >= 2 and raw[1] == ":":
        raise ArchiveValidationError(policy.unsafe_path_error.format(raw=name))
    raw_parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ArchiveValidationError(policy.unsafe_path_error.format(raw=name))
    normalized = posixpath.normpath(raw)
    parts = normalized.split("/")
    if normalized in {"", "."} or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveValidationError(policy.unsafe_path_error.format(raw=name))
    if _matching_rule(normalized, policy) is None:
        raise ArchiveValidationError(policy.unsupported_path_error.format(raw=name))
    return normalized


def validate_archive_members(
    zf: zipfile.ZipFile,
    policy: ArchiveValidationPolicy,
) -> dict[str, zipfile.ZipInfo]:
    normalized: dict[str, zipfile.ZipInfo] = {}
    counts: dict[ArchiveMemberRule, int] = {}
    combined_sizes: dict[ArchiveMemberRule, int] = {}
    total_size = 0

    for info in zf.infolist():
        if info.is_dir():
            raise ArchiveValidationError(policy.directory_error.format(name=info.filename, raw=info.filename))
        name = normalize_archive_member_name(info.filename, policy)
        if name in normalized:
            raise ArchiveValidationError(policy.duplicate_error.format(name=name, raw=info.filename))
        if _is_symlink(info):
            raise ArchiveValidationError(policy.symlink_error.format(name=name, raw=info.filename))
        if _is_encrypted(info):
            raise ArchiveValidationError(policy.encrypted_error.format(name=name, raw=info.filename))
        if info.compress_type not in _SUPPORTED_COMPRESSION_METHODS:
            raise ArchiveValidationError(policy.compression_error.format(name=name, raw=info.filename))

        total_size += info.file_size
        if policy.total_uncompressed_bytes is not None and total_size > policy.total_uncompressed_bytes:
            raise ArchiveValidationError(policy.total_size_error.format(name=name, raw=info.filename))

        rule = _matching_rule(name, policy)
        if rule is None:
            raise ArchiveValidationError(policy.unsupported_path_error.format(raw=info.filename))
        _validate_rule_limits(rule, name, info.file_size, counts, combined_sizes)
        normalized[name] = info

    return normalized


def validate_archive_payloads(
    attachments: Mapping[str, bytes],
    *,
    hash_hook: ArchivePayloadHook | None = None,
) -> None:
    """Run schema-owned payload/hash validation through the archive boundary."""

    if hash_hook is None:
        return
    hash_hook(MappingProxyType(dict(attachments)))


def _matching_rule(name: str, policy: ArchiveValidationPolicy) -> ArchiveMemberRule | None:
    for rule in policy.rules:
        if rule.matches(name):
            return rule
    return None


def _validate_rule_limits(
    rule: ArchiveMemberRule,
    name: str,
    file_size: int,
    counts: dict[ArchiveMemberRule, int],
    combined_sizes: dict[ArchiveMemberRule, int],
) -> None:
    if rule.required_suffix is not None and not name.endswith(rule.required_suffix):
        message = rule.suffix_error or "archive entry has unsupported suffix: {name}"
        raise ArchiveValidationError(message.format(name=name, prefix=rule.label))

    count = counts.get(rule, 0) + 1
    counts[rule] = count
    if rule.max_count is not None and count > rule.max_count:
        message = rule.count_error or "too many archive entries for prefix: {prefix}"
        raise ArchiveValidationError(message.format(name=name, prefix=rule.label))

    if rule.max_file_bytes is not None and file_size > rule.max_file_bytes:
        message = rule.file_size_error or "archive entry exceeds size limit: {name}"
        raise ArchiveValidationError(message.format(name=name, prefix=rule.label))

    combined = combined_sizes.get(rule, 0) + file_size
    combined_sizes[rule] = combined
    if rule.max_combined_bytes is not None and combined > rule.max_combined_bytes:
        message = rule.combined_size_error or "archive entries exceed combined size limit for prefix: {prefix}"
        raise ArchiveValidationError(message.format(name=name, prefix=rule.label))


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)
