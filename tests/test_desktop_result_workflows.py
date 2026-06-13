from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_csv_export_enabled_after_result_data_exists(window: Any) -> None:
    assert not window.export_csv_btn.isEnabled()

    window._set_csv_data(
        [{"index": 1, "value": "2.0", "uncertainty": "0.1"}],
        ["index", "value", "uncertainty"],
        suggestion="results.csv",
    )

    assert window.export_csv_btn.isEnabled()


def test_latex_save_writes_expected_source_to_temp_path(window: Any, tmp_path: Path) -> None:
    target = tmp_path / "result.tex"
    source = "\\documentclass{article}\n\\begin{document}\nSaved source\n\\end{document}\n"
    window.current_latex_path = target
    window.latex_edit.setPlainText(source)

    saved = window._persist_latex_editor(silent=True)

    assert saved == target
    assert target.read_text(encoding="utf-8") == source


def test_pdf_preview_accepts_mocked_renderer_and_fixture_path(window: Any, tmp_path: Path, monkeypatch: Any) -> None:
    Image = pytest.importorskip("PIL.Image")
    pdf_path = tmp_path / "fixture.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% fake fixture for mocked preview\n")

    def fake_generate_pdf_base_images(path: Path) -> bool:
        assert path == pdf_path
        window.pdf_base_images = [Image.new("RGBA", (20, 12), (255, 255, 255, 255))]
        return True

    monkeypatch.setattr(window, "_generate_pdf_base_images", fake_generate_pdf_base_images)

    assert window._render_pdf_preview(pdf_path, force_reload=True)
    assert window.last_pdf_path == pdf_path
    assert window.pdf_base_images
    assert "fixture.pdf" in window.pdf_status_label.text()


def test_image_zoom_and_page_controls_preserve_result_plot_bytes(window: Any, tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(PNG_1X1)
    second.write_bytes(PNG_1X1)

    window._set_image_list("fit", [first, second])
    assert window.result_plot_bytes == PNG_1X1

    window.result_plot_zoom_spin.setValue(125)
    assert window.result_plot_bytes == PNG_1X1
    assert window.result_plot_zoom > 1.0

    window.result_plot_page_spin.setValue(2)
    assert window.result_plot_bytes == PNG_1X1
    assert window.result_plot_page_spin.value() == 2
