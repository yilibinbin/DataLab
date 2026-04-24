from __future__ import annotations

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PIL import Image


def test_raster_backend_ui_updates_on_main_thread(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QThread

    from shared.pdf_preview import RasterBackend
    from shared import pdf_preview_raster

    main_thread = QThread.currentThread()

    def fake_convert_pdf_to_images(pdf_path: Path, dpi: int, tool=None):
        return [Image.new("RGB", (16, 16), color=(255, 255, 255))]

    monkeypatch.setattr(pdf_preview_raster, "convert_pdf_to_images", fake_convert_pdf_to_images)

    backend = RasterBackend()
    qtbot.addWidget(backend.get_widget())

    called_thread_ids: list[object] = []
    original_on_render_finished = backend._on_render_finished

    def wrapped(pixmaps):
        called_thread_ids.append(QThread.currentThread())
        original_on_render_finished(pixmaps)

    backend._on_render_finished = wrapped  # type: ignore[assignment]

    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DataLab test\n")

    assert backend.load_pdf(pdf_path)

    qtbot.waitUntil(lambda: len(backend.current_pixmaps) == 1, timeout=5000)
    assert called_thread_ids and called_thread_ids[0] == main_thread

    backend.cleanup()


def test_raster_backend_repeat_load_and_view_updates_do_not_reuse_deleted_labels(qtbot, monkeypatch, tmp_path):
    from shared.pdf_preview import RasterBackend
    from shared import pdf_preview_raster

    render_calls: list[int] = []

    def fake_convert_pdf_to_images(pdf_path: Path, dpi: int, tool=None):
        render_calls.append(dpi)
        return [Image.new("RGB", (16, 16), color=(255, 255, 255))]

    monkeypatch.setattr(pdf_preview_raster, "convert_pdf_to_images", fake_convert_pdf_to_images)

    backend = RasterBackend()
    qtbot.addWidget(backend.get_widget())

    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DataLab test\n")

    assert backend.load_pdf(pdf_path)
    qtbot.waitUntil(lambda: len(render_calls) >= 1 and backend.render_thread is None, timeout=5000)

    assert backend.load_pdf(pdf_path)
    qtbot.waitUntil(lambda: len(render_calls) >= 2 and backend.render_thread is None, timeout=5000)

    backend.set_zoom(1.5)
    qtbot.waitUntil(lambda: len(render_calls) >= 3 and backend.render_thread is None, timeout=5000)

    backend.set_dark_mode(True)
    qtbot.waitUntil(lambda: len(render_calls) >= 4 and backend.render_thread is None, timeout=5000)

    backend.cleanup()
