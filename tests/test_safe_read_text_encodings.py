"""``_safe_read_text`` accepts more than just UTF-8.

A user reported (Windows): opening a `.tex` file written by an editor
configured for GBK/CP936 raised ``UnicodeDecodeError`` and the
``读取失败`` dialog. LaTeX users on zh-CN Windows boxes routinely
have files in CP936 because that's the local default. The reader
should fall back gracefully across the realistic encoding set.

Order: utf-8 → utf-8-sig (BOM) → gbk → cp936 → latin-1. ``latin-1``
is the universal fallback because it never raises on byte input —
the result may be garbled if the file is in a different encoding,
but a garbled-but-loaded result is strictly better than a hard error
because the user can see something and re-save in a known encoding.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_safe_read_text_handles_utf8(tmp_path: Path) -> None:
    from app_desktop.workers_core import _safe_read_text

    f = tmp_path / "ascii.txt"
    f.write_bytes(b"hello world\n")
    assert _safe_read_text(f) == "hello world\n"


def test_safe_read_text_handles_utf8_with_bom(tmp_path: Path) -> None:
    from app_desktop.workers_core import _safe_read_text

    f = tmp_path / "bom.txt"
    f.write_bytes(b"\xef\xbb\xbf\xe4\xb8\xad\xe6\x96\x87\n")  # BOM + 中文
    out = _safe_read_text(f)
    assert "中文" in out


def test_safe_read_text_handles_gbk(tmp_path: Path) -> None:
    """The reported regression: a .tex file saved as GBK on a zh-CN
    Windows box. The bytes ``0xcd 0xf2`` are GBK for ``万`` and would
    raise ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xcd``."""
    from app_desktop.workers_core import _safe_read_text

    payload = "中文测试\n".encode("gbk")
    f = tmp_path / "gbk.tex"
    f.write_bytes(payload)
    out = _safe_read_text(f)
    assert "中文测试" in out


def test_safe_read_text_falls_back_to_latin1_for_unknown(tmp_path: Path) -> None:
    """Bytes that are valid in neither UTF-8 nor GBK still load — even
    if the result is mis-decoded — so the user sees something rather
    than a fatal error. ``latin-1`` decodes any byte sequence."""
    from app_desktop.workers_core import _safe_read_text

    # 0xff is not a valid first byte in UTF-8 or GBK.
    f = tmp_path / "weird.bin"
    f.write_bytes(bytes(range(256)))
    out = _safe_read_text(f)
    assert isinstance(out, str)
    assert len(out) == 256


def test_safe_read_text_raises_for_missing_file(tmp_path: Path) -> None:
    from app_desktop.workers_core import _safe_read_text

    with pytest.raises(ValueError):
        _safe_read_text(tmp_path / "does_not_exist")
