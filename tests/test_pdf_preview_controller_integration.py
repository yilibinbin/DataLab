from __future__ import annotations

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path


class _DummySignal:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._callbacks: list[object] = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        self.calls.append(args)
        for callback in list(self._callbacks):
            callback(*args)


def test_pdf_preview_controller_fallback_updates_state_and_emits_signal(tmp_path) -> None:
    from shared.pdf_preview import PdfPreviewController

    class FakeBackend:
        def __init__(self, name: str, result: bool) -> None:
            self.name = name
            self.result = result
            self.zoom_factor = None
            self.dark_mode = None
            self.load_state: list[tuple[object, object]] = []

        def load_pdf(self, pdf_path: Path) -> bool:
            self.load_state.append((self.zoom_factor, self.dark_mode))
            return self.result

        def capabilities(self):
            class Cap:
                def __init__(self, backend_type: str) -> None:
                    self.backend_type = backend_type

            return Cap(self.name)

        def set_zoom(self, zoom_factor: float) -> None:
            self.zoom_factor = zoom_factor

        def set_dark_mode(self, enabled: bool) -> None:
            self.dark_mode = enabled

    controller = PdfPreviewController.__new__(PdfPreviewController)
    controller.current_backend_name = "webengine"
    controller.current_backend = None
    controller.current_pdf_path = None
    controller.zoom_factor = 1.75
    controller.dark_mode = True
    controller.backend_changed = _DummySignal()
    controller.pdf_load_failed = _DummySignal()
    controller.pdf_loaded = _DummySignal()
    controller.webengine_backend = FakeBackend("webengine", False)
    controller.qtpdf_backend = FakeBackend("qtpdf", False)
    controller.raster_backend = FakeBackend("raster", True)

    pdf_path = tmp_path / "fallback.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DataLab test\n")

    assert controller._fallback_load_pdf(pdf_path) is True
    assert controller.current_backend is controller.raster_backend
    assert controller.current_backend_name == "raster"
    assert controller.current_pdf_path == pdf_path
    assert controller.pdf_loaded.calls == [(pdf_path,)]
    assert controller.backend_changed.calls == [("raster",)]
    assert controller.raster_backend.load_state == [(1.75, True)]


def test_pdf_preview_integration_swaps_preview_widget_on_backend_change(qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

    from shared import pdf_preview_integration as integration_module

    class FakeController:
        def __init__(self, parent_widget: QWidget) -> None:
            self.parent_widget = parent_widget
            self.backend_changed = _DummySignal()
            self.pdf_loaded = _DummySignal()
            self._widgets = {
                "webengine": QLabel("webengine"),
                "raster": QLabel("raster"),
            }
            self._current = "webengine"

        def get_widget(self) -> QWidget:
            return self._widgets[self._current]

        def set_render_mode(self, mode) -> None:
            self._current = "raster"
            self.backend_changed.emit("raster")

        def capabilities(self):
            class Cap:
                backend_type = "raster"
                gpu_accelerated = False
                supports_native_zoom = False

            return Cap()

        def load_pdf(self, pdf_path: Path) -> bool:
            return True

        def set_zoom(self, zoom_factor: float) -> None:
            return None

        def set_dark_mode(self, enabled: bool) -> None:
            return None

        def cleanup(self) -> None:
            return None

    monkeypatch.setattr(integration_module, "PdfPreviewController", FakeController)
    monkeypatch.setattr(integration_module, "create_pdf_toolbar", lambda controller, parent: QHBoxLayout())

    parent = QWidget()
    qtbot.addWidget(parent)
    integration = integration_module.PdfPreviewIntegration(parent)
    qtbot.addWidget(integration.get_widget())

    original_widget = integration.preview_widget
    assert isinstance(original_widget, QLabel)
    assert original_widget.text() == "webengine"

    integration.set_render_mode("raster")

    assert integration.preview_widget is integration.controller.get_widget()
    assert integration.preview_widget is not original_widget
    assert isinstance(integration.preview_widget, QLabel)
    assert integration.preview_widget.text() == "raster"
    assert integration.main_layout.indexOf(integration.preview_widget) >= 0
