from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from typing import Any, cast

import pytest

from shared.archive_validation import (
    ArchiveMemberRule,
    ArchiveValidationError,
    ArchiveValidationPolicy,
    validate_archive_members,
    validate_archive_payloads,
)


def _policy(
    *,
    report_count: int | None = 2,
    report_file_bytes: int | None = 8,
    report_combined_bytes: int | None = None,
    total_bytes: int | None = 32,
) -> ArchiveValidationPolicy:
    return ArchiveValidationPolicy(
        rules=(
            ArchiveMemberRule(exact_path="manifest.json", max_file_bytes=16),
            ArchiveMemberRule(
                prefix="reports/",
                required_suffix=".json",
                max_count=report_count,
                max_file_bytes=report_file_bytes,
                max_combined_bytes=report_combined_bytes,
                count_error="too many reports",
                file_size_error="report too large: {name}",
                combined_size_error="reports combined too large",
                suffix_error="report must be json: {name}",
            ),
            ArchiveMemberRule(prefix="sources/", max_count=1, max_file_bytes=16),
        ),
        total_uncompressed_bytes=total_bytes,
    )


def _archive_bytes(
    entries: Iterable[tuple[str, bytes]],
    *,
    symlinks: Iterable[str] = (),
    directories: Iterable[str] = (),
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        for name in directories:
            zf.writestr(name, b"")
        for name, payload in entries:
            info = zipfile.ZipInfo(name)
            if name in symlinks:
                info.create_system = 3
                info.external_attr = 0o120777 << 16
            zf.writestr(info, payload)
    return buffer.getvalue()


def _patch_zip_headers(
    data: bytes,
    *,
    flag_bits: int | None = None,
    compression_method: int | None = None,
    target_name: str | None = None,
) -> bytes:
    patched = bytearray(data)

    def patch_headers(signature: bytes, flag_offset: int, method_offset: int, name_len_offset: int, extra_len_offset: int, name_offset: int) -> None:
        start = 0
        while True:
            index = patched.find(signature, start)
            if index < 0:
                return
            name_len = int.from_bytes(patched[index + name_len_offset : index + name_len_offset + 2], "little")
            extra_len = int.from_bytes(patched[index + extra_len_offset : index + extra_len_offset + 2], "little")
            name = bytes(patched[index + name_offset : index + name_offset + name_len]).decode("utf-8")
            if target_name is None or name == target_name:
                if flag_bits is not None:
                    patched[index + flag_offset : index + flag_offset + 2] = flag_bits.to_bytes(2, "little")
                if compression_method is not None:
                    patched[index + method_offset : index + method_offset + 2] = compression_method.to_bytes(2, "little")
            start = index + name_offset + name_len + extra_len

    patch_headers(b"PK\x03\x04", 6, 8, 26, 28, 30)
    patch_headers(b"PK\x01\x02", 8, 10, 28, 30, 46)
    return bytes(patched)


def _validate(data: bytes, policy: ArchiveValidationPolicy | None = None) -> dict[str, zipfile.ZipInfo]:
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        return validate_archive_members(zf, policy or _policy())


def test_archive_validation_accepts_supported_members_and_normalizes_separators() -> None:
    members = _validate(_archive_bytes([("manifest.json", b"{}"), ("reports\\one.json", b"1234")]))

    assert sorted(members) == ["manifest.json", "reports/one.json"]


@pytest.mark.parametrize(
    "entry_name",
    [
        "/absolute.json",
        "../manifest.json",
        "C:/temp/report.json",
        "reports/../evil.json",
        "reports//one.json",
        "reports/./one.json",
    ],
)
def test_archive_validation_rejects_unsafe_paths(entry_name: str) -> None:
    data = _archive_bytes([("manifest.json", b"{}"), (entry_name, b"x")])

    with pytest.raises(ArchiveValidationError, match="unsafe archive path"):
        _validate(data)


def test_archive_validation_rejects_unsupported_prefix() -> None:
    data = _archive_bytes([("manifest.json", b"{}"), ("assets/report.json", b"x")])

    with pytest.raises(ArchiveValidationError, match="unsupported archive path"):
        _validate(data)


def test_archive_validation_rejects_duplicate_entries() -> None:
    with pytest.warns(UserWarning, match="Duplicate name"):
        data = _archive_bytes([("manifest.json", b"{}"), ("manifest.json", b"{}")])

    with pytest.raises(ArchiveValidationError, match="duplicate archive entry: manifest.json"):
        _validate(data)


def test_archive_validation_rejects_symlink_entries() -> None:
    data = _archive_bytes([("manifest.json", b"{}"), ("reports/one.json", b"target")], symlinks=["reports/one.json"])

    with pytest.raises(ArchiveValidationError, match="symlink entries are not allowed: reports/one.json"):
        _validate(data)


def test_archive_validation_rejects_encrypted_entries() -> None:
    data = _patch_zip_headers(
        _archive_bytes([("manifest.json", b"{}"), ("reports/one.json", b"target")]),
        flag_bits=0x1,
        target_name="reports/one.json",
    )

    with pytest.raises(ArchiveValidationError, match="encrypted archive entries are not allowed: reports/one.json"):
        _validate(data)


def test_archive_validation_rejects_unsupported_compression_methods() -> None:
    data = _patch_zip_headers(
        _archive_bytes([("manifest.json", b"{}"), ("reports/one.json", b"target")]),
        compression_method=99,
        target_name="reports/one.json",
    )

    with pytest.raises(ArchiveValidationError, match="unsupported archive compression method: reports/one.json"):
        _validate(data)


def test_archive_validation_rejects_directory_entries() -> None:
    data = _archive_bytes([("manifest.json", b"{}")], directories=["reports/"])

    with pytest.raises(ArchiveValidationError, match="directory entries are not allowed: reports/"):
        _validate(data)


def test_archive_validation_rejects_required_suffix_mismatch() -> None:
    data = _archive_bytes([("manifest.json", b"{}"), ("reports/one.txt", b"x")])

    with pytest.raises(ArchiveValidationError, match="report must be json: reports/one.txt"):
        _validate(data)


def test_archive_validation_rejects_per_prefix_count_overage() -> None:
    data = _archive_bytes(
        [
            ("manifest.json", b"{}"),
            ("reports/one.json", b"1"),
            ("reports/two.json", b"2"),
            ("reports/three.json", b"3"),
        ]
    )

    with pytest.raises(ArchiveValidationError, match="too many reports"):
        _validate(data)


def test_archive_validation_rejects_per_file_byte_overage() -> None:
    data = _archive_bytes([("manifest.json", b"{}"), ("reports/one.json", b"123456789")])

    with pytest.raises(ArchiveValidationError, match="report too large: reports/one.json"):
        _validate(data)


def test_archive_validation_rejects_per_prefix_combined_byte_overage() -> None:
    data = _archive_bytes(
        [
            ("manifest.json", b"{}"),
            ("reports/one.json", b"123456"),
            ("reports/two.json", b"abcdef"),
        ]
    )

    with pytest.raises(ArchiveValidationError, match="reports combined too large"):
        _validate(data, _policy(report_file_bytes=8, report_combined_bytes=10))


def test_archive_validation_rejects_total_uncompressed_byte_overage() -> None:
    data = _archive_bytes([("manifest.json", b"{}"), ("reports/one.json", b"1234")])

    with pytest.raises(ArchiveValidationError, match="archive exceeds total uncompressed size limit"):
        _validate(data, _policy(total_bytes=5))


def test_archive_validation_runs_payload_hash_hook_with_read_only_snapshot() -> None:
    captured: dict[str, bytes] = {}

    def hook(payloads: object) -> None:
        captured.update(cast(dict[str, bytes], dict(cast(Any, payloads))))
        with pytest.raises(TypeError):
            cast(Any, payloads)["reports/one.json"] = b"mutated"

    attachments = {"reports/one.json": b"abc"}

    validate_archive_payloads(attachments, hash_hook=hook)
    attachments["reports/one.json"] = b"changed"

    assert captured == {"reports/one.json": b"abc"}
