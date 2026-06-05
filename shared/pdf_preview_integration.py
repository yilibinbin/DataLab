"""
Integration adapter for PDF preview controller with existing UI.

This module provides the bridge between the new PdfPreviewController
and the existing MainWindow PDF preview area.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from .pdf_preview import PdfPreviewController, PdfRenderMode, create_pdf_toolbar

logger = logging.getLogger(__name__)


class PdfPreviewIntegration:
    """
    Adapter for integrating PdfPreviewController into MainWindow.

    Replaces the old PDF preview system while maintaining API compatibility.
    """

    def __init__(self, parent_widget: QWidget, dpi_base: int = 220):
        """
        Initialize PDF preview integration.

        Args:
            parent_widget: Parent widget (usually the tab or container)
            dpi_base: Base DPI for raster rendering
        """
        self.parent = parent_widget
        self.controller = PdfPreviewController(parent_widget)
        self.dpi_base = dpi_base

        # Build UI
        self.main_container = QWidget()
        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Add toolbar
        self.toolbar_layout = create_pdf_toolbar(self.controller, parent_widget)
        self.main_layout.addLayout(self.toolbar_layout)

        # Add preview widget
        self.preview_widget = self.controller.get_widget()
        self.main_layout.addWidget(self.preview_widget)
        self.controller.backend_changed.connect(self._sync_preview_widget)

        # Internal state
        self._current_pdf_path: Optional[Path] = None
        self.pdf_zoom = 1.0

    def get_widget(self) -> QWidget:
        """Get the main container widget."""
        return self.main_container

    def load_pdf(self, pdf_path: Path) -> bool:
        """
        Load and display a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            True on success
        """
        if not pdf_path.exists():
            logger.error(f"[pdf] PDF not found: {pdf_path}")
            return False

        self._current_pdf_path = pdf_path
        success = self.controller.load_pdf(pdf_path)

        if success:
            logger.info(f"[pdf] PDF loaded: {pdf_path}")
        else:
            logger.error(f"[pdf] Failed to load: {pdf_path}")

        return success

    def set_zoom(self, zoom_factor: float) -> None:
        """
        Set zoom factor (0.35 to 4.0).

        Args:
            zoom_factor: Zoom factor (1.0 = 100%)
        """
        self.pdf_zoom = max(0.35, min(4.0, zoom_factor))
        self.controller.set_zoom(self.pdf_zoom)
        logger.debug(f"[pdf] Zoom set to {self.pdf_zoom:.2f}")

    def zoom_in(self, factor: float = 1.25) -> None:
        """Increase zoom."""
        self.set_zoom(self.pdf_zoom * factor)

    def zoom_out(self, factor: float = 0.75) -> None:
        """Decrease zoom."""
        self.set_zoom(self.pdf_zoom * factor)

    def reset_zoom(self) -> None:
        """Reset zoom to 100%."""
        self.set_zoom(1.0)

    def set_dark_mode(self, enabled: bool) -> None:
        """Enable/disable dark mode."""
        self.controller.set_dark_mode(enabled)
        logger.debug(f"[pdf] Dark mode: {enabled}")

    def set_render_mode(self, mode: str) -> None:
        """
        Set rendering mode.

        Args:
            mode: "auto", "webengine", or "raster"
        """
        mode_map = {
            "auto": PdfRenderMode.AUTO,
            "webengine": PdfRenderMode.GPU_WEBENGINE,
            "raster": PdfRenderMode.COMPATIBLE,
        }

        pdf_mode = mode_map.get(mode.lower(), PdfRenderMode.AUTO)
        self.controller.set_render_mode(pdf_mode)
        logger.info(f"[pdf] Render mode set to: {mode}")

    def _sync_preview_widget(self, *_args: object) -> None:
        """Keep the mounted preview widget in sync with controller backend switches."""
        new_widget = self.controller.get_widget()
        if new_widget is self.preview_widget:
            return

        index = self.main_layout.indexOf(self.preview_widget)
        if index < 0:
            index = self.main_layout.count()
        else:
            self.main_layout.removeWidget(self.preview_widget)
            self.preview_widget.setParent(None)

        self.preview_widget = new_widget
        self.main_layout.insertWidget(index, self.preview_widget)

    def clear(self) -> None:
        """Clear the current PDF preview."""
        self._current_pdf_path = None
        self.pdf_zoom = 1.0
        logger.debug("[pdf] Preview cleared")

    def cleanup(self) -> None:
        """Clean up resources."""
        self.controller.cleanup()
        logger.info("[pdf] Integration cleaned up")

    def get_current_pdf_path(self) -> Optional[Path]:
        """Get the currently loaded PDF path."""
        return self._current_pdf_path

    def get_current_zoom(self) -> float:
        """Get the current zoom factor."""
        return self.pdf_zoom

    def get_backend_info(self) -> dict[str, object]:
        """Get information about the current backend."""
        cap = self.controller.capabilities()
        return {
            "backend": cap.backend_type,
            "gpu_accelerated": cap.gpu_accelerated,
            "supports_native_zoom": cap.supports_native_zoom,
        }


def create_pdf_controls_panel(integration: PdfPreviewIntegration) -> QWidget:
    """
    Create a control panel for PDF preview.

    Returns: QWidget containing zoom controls and mode selector
    """
    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(5, 5, 5, 5)

    # Zoom controls
    zoom_out_btn = QPushButton("−")
    zoom_out_btn.setMaximumWidth(40)
    zoom_out_btn.clicked.connect(lambda: integration.zoom_out(0.8))

    zoom_label = QLabel(f"Zoom: {integration.get_current_zoom() * 100:.0f}%")

    zoom_in_btn = QPushButton("+")
    zoom_in_btn.setMaximumWidth(40)
    zoom_in_btn.clicked.connect(lambda: integration.zoom_in(1.25))

    reset_zoom_btn = QPushButton("Reset")
    reset_zoom_btn.setMaximumWidth(60)
    reset_zoom_btn.clicked.connect(integration.reset_zoom)

    layout.addWidget(zoom_out_btn)
    layout.addWidget(zoom_label, stretch=0)
    layout.addWidget(zoom_in_btn)
    layout.addWidget(reset_zoom_btn)
    layout.addStretch()

    # Update zoom label when changed
    def update_zoom_label() -> None:
        zoom_label.setText(f"Zoom: {integration.get_current_zoom() * 100:.0f}%")

    integration.controller.pdf_loaded.connect(update_zoom_label)

    return panel
