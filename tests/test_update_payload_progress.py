from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import TracebackType

import pytest

from shared.update_payload import DownloadProgress, InstallerAsset, download_and_verify_installer


class ChunkedResponse:
    def __init__(self, payload: bytes, chunk_size: int) -> None:
        self._stream = io.BytesIO(payload)
        self._chunk_size = chunk_size

    def __enter__(self) -> ChunkedResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def read(self, requested: int) -> bytes:
        return self._stream.read(min(requested, self._chunk_size))


def _asset(data: bytes) -> InstallerAsset:
    return InstallerAsset(
        platform_key="macos",
        name="DataLab-test.pkg",
        url="https://example.invalid/DataLab-test.pkg",
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


def test_download_progress_reports_multiple_chunks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = b"abcd" * 2048
    asset = _asset(data)
    events: list[DownloadProgress] = []

    monkeypatch.setattr("shared.update_payload.update_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "shared.update_payload._urlopen",
        lambda request, timeout: ChunkedResponse(data, 1024),
    )

    path = download_and_verify_installer(asset, progress_callback=events.append)

    assert path == tmp_path / asset.name
    assert len(events) >= 3
    assert events[-1].downloaded_bytes == len(data)
    assert events[-1].total_bytes == len(data)
    assert events[-1].fraction == 1.0
    assert events[-1].bytes_per_second > 0


def test_existing_download_call_signature_still_works(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = b"ok"
    asset = _asset(data)

    monkeypatch.setattr("shared.update_payload.update_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "shared.update_payload._urlopen",
        lambda request, timeout: ChunkedResponse(data, 1024),
    )

    assert download_and_verify_installer(asset).is_file()


def test_raising_progress_callback_does_not_abort_or_delete_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data = b"verified installer payload"
    asset = _asset(data)
    target = tmp_path / asset.name
    target.write_bytes(b"pre-existing installer")

    def raising_progress_callback(progress: DownloadProgress) -> None:
        raise RuntimeError("progress sink failed")

    monkeypatch.setattr("shared.update_payload.update_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "shared.update_payload._urlopen",
        lambda request, timeout: ChunkedResponse(data, 4),
    )

    path = download_and_verify_installer(asset, progress_callback=raising_progress_callback)

    assert path == target
    assert target.is_file()
    assert target.read_bytes() == data
