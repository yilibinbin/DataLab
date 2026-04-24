from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PIL")

from PIL import Image


def test_convert_pdftoppm_loads_multiple_pages(monkeypatch, tmp_path) -> None:
    from shared import pdf_preview_raster as raster

    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DataLab test\n")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    Image.new("RGBA", (8, 8), color=(255, 0, 0, 255)).save(out_dir / "page-1.png")
    Image.new("RGBA", (8, 8), color=(0, 255, 0, 255)).save(out_dir / "page-2.png")

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, capture_output, timeout, text, check):  # noqa: ARG001
        captured_cmds.append(list(cmd))
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr(raster.subprocess, "run", fake_run)

    images = raster._convert_pdftoppm(
        pdf_path,
        out_dir,
        dpi=120,
        max_pages=None,
        pdftoppm_path="pdftoppm",
    )
    assert len(images) == 2
    assert captured_cmds and "-singlefile" not in captured_cmds[0]

