"""
Unified PDF preview controller with multi-backend support.

Supports GPU-accelerated rendering (WebEngine) with intelligent fallback:
  1. WebEngine (GPU, Chromium PDFium) - fastest on Win/macOS
  2. QtPdf (CPU-optimized, stable fallback)
  3. Raster (PIL→PNG→QPixmap, maximum compatibility)

Features:
  - Async loading with cancellation support
  - LRU cache for raster mode
  - Dark mode support
  - Smooth zoom/scroll on all backends
  - Platform-specific GPU optimizations
"""

import logging
import tempfile
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from collections import OrderedDict
from threading import Lock

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QScrollArea, QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QObject, QThread, QUrl
from PySide6.QtGui import QIcon, QPixmap, QImage, QCursor
from PIL import Image, ImageOps

if TYPE_CHECKING:
    # WebEngine / QtPdf imports live inside the backend ``__init__`` so a
    # PySide6 install without those wheels still imports this module.
    # Mirror them here under TYPE_CHECKING so the optional attributes
    # carry concrete types (rather than ``Any``), restoring the narrowing
    # mypy --strict can do across ``is None`` guards.
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtPdfWidgets import QPdfView
    from PySide6.QtPdf import QPdfDocument

logger = logging.getLogger(__name__)


class PdfRenderMode(Enum):
    """PDF rendering mode selection."""
    AUTO = "auto"           # Automatic fallback: WebEngine > QtPdf > Raster
    GPU_WEBENGINE = "webengine"   # Force WebEngine (GPU)
    COMPATIBLE = "raster"   # Force raster (maximum compatibility)


@dataclass
class PdfCapabilities:
    """Backend capabilities information."""
    gpu_accelerated: bool
    backend_type: str  # "webengine", "qtpdf", "raster"
    supports_native_zoom: bool
    max_render_size: int  # Maximum page dimension before scaling


class PdfRasterRenderThread(QThread):
    """Async render worker for raster backend (PDF -> PIL -> QImage)."""

    rendered = Signal(int, list)  # (job_id, list[QImage])
    cancelled = Signal(int)  # job_id
    error = Signal(int, str)  # (job_id, message)

    def __init__(
        self,
        job_id: int,
        pdf_path: Path,
        *,
        zoom: float,
        dpi: int,
        dark_mode: bool,
        conversion_tool: Optional[tuple[str, str]] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.job_id = int(job_id)
        self.pdf_path = pdf_path
        self.zoom = float(zoom)
        self.dpi = int(dpi)
        self.dark_mode = bool(dark_mode)
        self.conversion_tool = conversion_tool

    def cancel(self) -> None:
        """Request render cancellation."""
        self.requestInterruption()

    @staticmethod
    def _pil_to_qimage(image: Image.Image) -> QImage:
        if image.mode not in ("RGBA", "BGRA"):
            image = image.convert("RGBA")
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        # Detach from the Python buffer so the QImage is safe to pass across threads.
        return qimage.copy()

    def run(self) -> None:
        try:
            if self.isInterruptionRequested():
                self.cancelled.emit(self.job_id)
                return

            from . import pdf_preview_raster as raster_module

            pil_images = raster_module.convert_pdf_to_images(
                self.pdf_path,
                dpi=self.dpi,
                tool=self.conversion_tool,
            )
            qimages: list[QImage] = []
            for img in pil_images:
                if self.isInterruptionRequested():
                    self.cancelled.emit(self.job_id)
                    return
                if self.zoom != 1.0:
                    img = raster_module.apply_zoom_to_image(img, self.zoom)
                if self.dark_mode:
                    img = raster_module.apply_dark_mode_to_image(img)
                qimages.append(self._pil_to_qimage(img))

            if self.isInterruptionRequested():
                self.cancelled.emit(self.job_id)
                return
            self.rendered.emit(self.job_id, qimages)
        except Exception as exc:
            logger.error(f"PDF render error: {exc}")
            self.error.emit(self.job_id, str(exc))


class PdfBackend(ABC):
    """Abstract base for PDF preview backends."""

    @abstractmethod
    def load_pdf(self, pdf_path: Path) -> bool:
        """Load a PDF file. Return True on success."""
        pass

    @abstractmethod
    def set_zoom(self, zoom_factor: float) -> None:
        """Set zoom factor (0.35-4.0)."""
        pass

    @abstractmethod
    def set_dark_mode(self, enabled: bool) -> None:
        """Enable/disable dark mode."""
        pass

    @abstractmethod
    def get_widget(self) -> QWidget:
        """Get the widget for display."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources."""
        pass

    @abstractmethod
    def capabilities(self) -> PdfCapabilities:
        """Return backend capabilities."""
        pass


class WebEngineBackend(PdfBackend):
    """GPU-accelerated WebEngine backend (Chromium PDFium)."""

    def __init__(self) -> None:
        super().__init__()
        self.pdf_path: Optional[Path] = None
        self.zoom_factor = 1.0
        self.dark_mode = False
        self.web_view: Optional["QWebEngineView"] = None
        self._setup_webengine()

    def _setup_webengine(self) -> None:
        """Initialize WebEngine with GPU optimization flags."""
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineSettings

            # Set GPU flags before creating view (only if not already set)
            if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
                flags = (
                    "--disable-gpu=false "
                    "--ignore-gpu-blocklist "
                    "--enable-gpu-rasterization "
                    "--enable-zero-copy"
                )
                # Platform-specific optimizations
                if sys.platform == "win32":
                    flags += " --enable-direct-composition"
                elif sys.platform == "darwin":
                    flags += " --enable-features=Metal"

                os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
                logger.info(f"[pdf] WebEngine GPU flags: {flags}")

            self.web_view = QWebEngineView()
            self.web_view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

            # Enable PDF viewing
            settings = self.web_view.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.PluginsEnabled, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.PdfViewerEnabled, True
            )

            logger.info("[pdf] WebEngine backend initialized")
        except ImportError:
            logger.warning("[pdf] WebEngine not available (QtWebEngineWidgets import failed)")
            self.web_view = None
        except Exception as e:
            logger.warning(f"[pdf] WebEngine init error: {e}")
            self.web_view = None

    def load_pdf(self, pdf_path: Path) -> bool:
        """Load PDF via file:// URL."""
        if not self.web_view:
            return False

        try:
            self.pdf_path = pdf_path
            file_url = QUrl.fromLocalFile(str(pdf_path.resolve()))
            self.web_view.load(file_url)
            logger.info(f"[pdf] WebEngine loaded: {pdf_path}")
            return True
        except Exception as e:
            logger.error(f"[pdf] WebEngine load error: {e}")
            return False

    def set_zoom(self, zoom_factor: float) -> None:
        """Set zoom factor via setZoomFactor."""
        if self.web_view:
            self.zoom_factor = max(0.35, min(4.0, zoom_factor))
            try:
                self.web_view.setZoomFactor(self.zoom_factor)
                logger.debug(f"[pdf] WebEngine zoom: {self.zoom_factor:.2f}")
            except Exception as e:
                logger.warning(f"[pdf] WebEngine zoom error: {e}")

    def set_dark_mode(self, enabled: bool) -> None:
        """Dark mode support via CSS filter (optional)."""
        self.dark_mode = enabled
        if self.web_view and enabled:
            try:
                # Inject CSS for dark mode inversion (optional)
                css_code = (
                    "document.documentElement.style.filter = 'invert(1) hue-rotate(180deg)';"
                )
                self.web_view.page().runJavaScript(css_code)
            except Exception as e:
                logger.debug(f"[pdf] WebEngine dark mode CSS inject error: {e}")

    def get_widget(self) -> QWidget:
        """Return WebEngine view."""
        return self.web_view or QWidget()

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.web_view:
            try:
                self.web_view.stop()
                # Don't delete - let parent handle
            except Exception as e:
                logger.debug(f"[pdf] WebEngine cleanup error: {e}")

    def capabilities(self) -> PdfCapabilities:
        """WebEngine capabilities."""
        return PdfCapabilities(
            gpu_accelerated=self.web_view is not None,
            backend_type="webengine",
            supports_native_zoom=True,
            max_render_size=8192
        )


class QtPdfBackend(PdfBackend):
    """QtPdf backend (CPU-optimized, stable)."""

    def __init__(self) -> None:
        super().__init__()
        self.pdf_path: Optional[Path] = None
        self.zoom_factor = 1.0
        self.dark_mode = False
        self.pdf_view: Optional["QPdfView"] = None
        self.pdf_document: Optional["QPdfDocument"] = None
        self._setup_qtpdf()

    def _setup_qtpdf(self) -> None:
        """Initialize QtPdf view."""
        try:
            from PySide6.QtPdfWidgets import QPdfView
            from PySide6.QtPdf import QPdfDocument

            self.pdf_document = QPdfDocument()
            self.pdf_view = QPdfView()
            self.pdf_view.setDocument(self.pdf_document)
            logger.info("[pdf] QtPdf backend initialized")
        except ImportError:
            logger.warning("[pdf] QtPdf not available (import failed)")
            self.pdf_view = None
            self.pdf_document = None
        except Exception as e:
            logger.warning(f"[pdf] QtPdf init error: {e}")
            self.pdf_view = None
            self.pdf_document = None

    def load_pdf(self, pdf_path: Path) -> bool:
        """Load PDF using QtPdf."""
        if not self.pdf_view or not self.pdf_document:
            return False

        try:
            self.pdf_path = pdf_path
            self.pdf_document.load(str(pdf_path))
            status: Any = self.pdf_document.status()
            try:
                from PySide6.QtPdf import QPdfDocument

                null_status: Any = QPdfDocument.Status.Null
                loading_status: Any = QPdfDocument.Status.Loading
                ready_status: Any = QPdfDocument.Status.Ready
                error_status: Any = QPdfDocument.Status.Error
            except Exception:
                null_status, loading_status, ready_status, error_status = 0, 1, 2, 3

            logger.debug(f"[pdf] QtPdf status={status} path={pdf_path}")
            if status == error_status or status == null_status:
                logger.error(f"[pdf] QtPdf load failed (status={status}): {pdf_path}")
                return False
            if status in (loading_status, ready_status):
                logger.info(f"[pdf] QtPdf loaded (status={status}): {pdf_path}")
                return True
            # Unknown status: be conservative but do not treat as an error by default.
            logger.warning(f"[pdf] QtPdf returned unexpected status={status}: {pdf_path}")
            return True
        except Exception as e:
            logger.error(f"[pdf] QtPdf load error: {e}")
            return False

    def set_zoom(self, zoom_factor: float) -> None:
        """Set zoom factor."""
        if self.pdf_view:
            self.zoom_factor = max(0.35, min(4.0, zoom_factor))
            try:
                # QtPdf uses setZoomMode and scaling
                self.pdf_view.setZoomFactor(self.zoom_factor)
                logger.debug(f"[pdf] QtPdf zoom: {self.zoom_factor:.2f}")
            except Exception as e:
                logger.debug(f"[pdf] QtPdf zoom error: {e}")

    def set_dark_mode(self, enabled: bool) -> None:
        """Dark mode support (limited)."""
        self.dark_mode = enabled

    def get_widget(self) -> QWidget:
        """Return QtPdf view."""
        return self.pdf_view or QWidget()

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.pdf_document:
            try:
                # QtPdf auto-cleanup
                pass
            except Exception as e:
                logger.debug(f"[pdf] QtPdf cleanup error: {e}")

    def capabilities(self) -> PdfCapabilities:
        """QtPdf capabilities."""
        return PdfCapabilities(
            gpu_accelerated=False,
            backend_type="qtpdf",
            supports_native_zoom=True,
            max_render_size=4096
        )


class _RasterUiBridge(QObject):
    """Ensure raster render callbacks run on the GUI thread via queued signals."""

    def __init__(self, backend: "RasterBackend", parent: QObject | None = None):
        super().__init__(parent)
        self._backend = backend

    def on_finished(self, job_id: int, qimages: list[QImage]) -> None:
        self._backend._on_render_thread_finished(job_id, qimages)

    def on_error(self, job_id: int, message: str) -> None:
        self._backend._on_render_thread_error(job_id, message)

    def on_cancelled(self, job_id: int) -> None:
        self._backend._on_render_thread_cancelled(job_id)


class RasterBackend(PdfBackend):
    """Raster fallback (PIL/pdftoppm → PNG → QPixmap) with caching."""

    def __init__(self, dpi_base: int = 220) -> None:
        super().__init__()
        self.pdf_path: Optional[Path] = None
        self.zoom_factor = 1.0
        self.dark_mode = False
        self.dpi_base = dpi_base
        self.current_pixmaps: list[QPixmap] = []
        self.current_qimages: list[QImage] = []
        self.render_thread: Optional[PdfRasterRenderThread] = None
        self._render_job_id = 0
        self._active_job_id: int | None = None
        self._render_cache: Dict[tuple[Any, ...], QPixmap] = OrderedDict()
        self._cache_max_size = 32
        self._cache_lock = Lock()
        self.scroll_area = self._create_scroll_area()
        self._ui_bridge = _RasterUiBridge(self, parent=self.scroll_area)
        self.conversion_tool: Optional[tuple[str, str]] = None

    def _create_scroll_area(self) -> QScrollArea:
        """Create scroll area for page display."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setSpacing(10)
        self.container_layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def load_pdf(self, pdf_path: Path) -> bool:
        """Load and render PDF pages asynchronously."""
        if not pdf_path.exists():
            logger.error(f"[pdf] PDF not found: {pdf_path}")
            return False

        self.pdf_path = pdf_path

        # Cancel previous render if running
        if self.render_thread:
            try:
                running = self.render_thread.isRunning()
            except Exception:
                running = False
            if running:
                try:
                    self.render_thread.cancel()
                    self.render_thread.wait(1000)
                except Exception as e:
                    logger.debug(f"[pdf] Thread cancel error: {e}")
        self.render_thread = None

        # Show loading indicator
        self._clear_pages()
        self._show_status_message("Rendering PDF...")

        self._render_job_id += 1
        self._active_job_id = self._render_job_id

        dpi = int(round(self.dpi_base * self.zoom_factor * 1.5))
        dpi = max(150, min(450, dpi))
        thread = PdfRasterRenderThread(
            self._active_job_id,
            pdf_path,
            zoom=self.zoom_factor,
            dpi=dpi,
            dark_mode=self.dark_mode,
            conversion_tool=self.conversion_tool,
            parent=self.scroll_area,
        )
        thread.rendered.connect(self._ui_bridge.on_finished)
        thread.error.connect(self._ui_bridge.on_error)
        thread.cancelled.connect(self._ui_bridge.on_cancelled)
        thread.finished.connect(thread.deleteLater)
        self.render_thread = thread
        thread.start()

        logger.info(f"[pdf] Raster loading: {pdf_path}")
        return True

    def _on_render_thread_finished(self, job_id: int, qimages: list[QImage]) -> None:
        """Handle render completion (GUI thread)."""
        if self._active_job_id is None or int(job_id) != int(self._active_job_id):
            return
        if self.render_thread and getattr(self.render_thread, "job_id", None) == int(job_id):
            self.render_thread = None
        self.current_qimages = list(qimages or [])
        pixmaps = [QPixmap.fromImage(img) for img in self.current_qimages]
        self._on_render_finished(pixmaps)

    def _on_render_thread_error(self, job_id: int, message: str) -> None:
        if self._active_job_id is None or int(job_id) != int(self._active_job_id):
            return
        if self.render_thread and getattr(self.render_thread, "job_id", None) == int(job_id):
            self.render_thread = None
        self._on_render_error(message)

    def _on_render_thread_cancelled(self, job_id: int) -> None:
        if self._active_job_id is None or int(job_id) != int(self._active_job_id):
            return
        if self.render_thread and getattr(self.render_thread, "job_id", None) == int(job_id):
            self.render_thread = None
        logger.info("[pdf] Raster render cancelled")

    def _on_render_finished(self, pixmaps: list[QPixmap]) -> None:
        """Handle render completion."""
        self._clear_pages()
        self.current_pixmaps = pixmaps
        for i, pixmap in enumerate(pixmaps, 1):
            label = QLabel()
            label.setPixmap(pixmap)
            label.setScaledContents(False)
            self.container_layout.insertWidget(
                i - 1,
                self._create_page_widget(i, label),
                0,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )
        self._ensure_trailing_stretch()
        logger.info(f"[pdf] Raster render finished: {len(pixmaps)} pages")

    def _on_render_error(self, error_msg: str) -> None:
        """Handle render error."""
        self._clear_pages()
        self.current_pixmaps = []
        self.current_qimages = []
        self._show_status_message(f"Render error: {error_msg}")
        logger.error(f"[pdf] Raster render error: {error_msg}")

    def _create_page_widget(self, page_num: int, image_label: QLabel) -> QWidget:
        """Create widget for a single page with page number."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(f"Page {page_num}")
        title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(title)
        layout.addWidget(image_label)
        return widget

    def _clear_pages(self) -> None:
        """Clear all page widgets."""
        while self.container_layout.count() > 0:
            item = self.container_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._ensure_trailing_stretch()

    def _ensure_trailing_stretch(self) -> None:
        """Keep a stretch item at the end so pages stay top-aligned."""
        if self.container_layout.count() == 0:
            self.container_layout.addStretch()
            return
        last_item = self.container_layout.itemAt(self.container_layout.count() - 1)
        if last_item is None or last_item.spacerItem() is None:
            self.container_layout.addStretch()

    def _show_status_message(self, message: str) -> None:
        """Display a transient status label without reusing deleted widgets."""
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.container_layout.insertWidget(0, label)
        self._ensure_trailing_stretch()

    def set_zoom(self, zoom_factor: float) -> None:
        """Set zoom and re-render."""
        self.zoom_factor = max(0.35, min(4.0, zoom_factor))
        if self.pdf_path:
            self.load_pdf(self.pdf_path)  # Re-render with new zoom
        logger.debug(f"[pdf] Raster zoom: {self.zoom_factor:.2f}")

    def set_dark_mode(self, enabled: bool) -> None:
        """Enable dark mode (invert colors)."""
        if self.dark_mode != enabled:
            self.dark_mode = enabled
            # Re-render if PDF loaded
            if self.pdf_path:
                self.load_pdf(self.pdf_path)
            logger.debug(f"[pdf] Raster dark mode: {enabled}")

    def get_widget(self) -> QWidget:
        """Return scroll area."""
        return self.scroll_area

    def cleanup(self) -> None:
        """Cancel rendering and cleanup."""
        if self.render_thread:
            try:
                running = self.render_thread.isRunning()
            except Exception:
                running = False
            if running:
                try:
                    self.render_thread.cancel()
                    self.render_thread.wait(2000)
                except Exception:
                    pass
        self.render_thread = None
        self._clear_pages()

    def capabilities(self) -> PdfCapabilities:
        """Raster capabilities."""
        return PdfCapabilities(
            gpu_accelerated=False,
            backend_type="raster",
            supports_native_zoom=False,
            max_render_size=2048
        )


class PdfPreviewController(QObject):
    """Unified PDF preview controller with intelligent backend selection."""

    # Signals
    pdf_loaded = Signal(Path)
    pdf_load_failed = Signal(str)
    backend_changed = Signal(str)  # backend type name
    render_mode_changed = Signal(str)  # PdfRenderMode

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.current_pdf_path: Optional[Path] = None
        self.zoom_factor = 1.0
        self.dark_mode = False
        self.render_mode = PdfRenderMode.AUTO

        # Initialize backends
        self.webengine_backend: WebEngineBackend = WebEngineBackend()
        self.qtpdf_backend: QtPdfBackend = QtPdfBackend()
        self.raster_backend: RasterBackend = RasterBackend()

        self.current_backend: Optional[PdfBackend] = None
        self.current_backend_name = "none"

        self._select_best_backend()

    def _select_best_backend(self) -> None:
        """Select best available backend based on mode and availability."""
        if self.render_mode == PdfRenderMode.GPU_WEBENGINE:
            # Force WebEngine
            if getattr(self.webengine_backend, "web_view", None) is not None:
                self.current_backend = self.webengine_backend
                self.current_backend_name = "webengine"
                logger.info("[pdf] Selected backend: WebEngine (forced)")
                return
            else:
                logger.warning("[pdf] WebEngine forced but not available, falling back to QtPdf")

        elif self.render_mode == PdfRenderMode.COMPATIBLE:
            # Force Raster
            self.current_backend = self.raster_backend
            self.current_backend_name = "raster"
            logger.info("[pdf] Selected backend: Raster (forced)")
            return

        # AUTO mode: try WebEngine > QtPdf > Raster
        if getattr(self.webengine_backend, "web_view", None) is not None:
            self.current_backend = self.webengine_backend
            self.current_backend_name = "webengine"
            logger.info("[pdf] Selected backend: WebEngine")
        elif getattr(self.qtpdf_backend, "pdf_view", None) is not None and getattr(self.qtpdf_backend, "pdf_document", None) is not None:
            self.current_backend = self.qtpdf_backend
            self.current_backend_name = "qtpdf"
            logger.info("[pdf] Selected backend: QtPdf")
        else:
            self.current_backend = self.raster_backend
            self.current_backend_name = "raster"
            logger.info("[pdf] Selected backend: Raster (fallback)")

        self.backend_changed.emit(self.current_backend_name)

    def set_render_mode(self, mode: PdfRenderMode) -> None:
        """Change render mode and reselect backend."""
        if self.render_mode != mode:
            self.render_mode = mode
            self._select_best_backend()
            # Reload current PDF if any
            if self.current_pdf_path:
                self.load_pdf(self.current_pdf_path)
            self.render_mode_changed.emit(mode.value)

    def load_pdf(self, pdf_path: Path) -> bool:
        """Load PDF using current backend."""
        if not self.current_backend:
            logger.error("[pdf] No backend available")
            self.pdf_load_failed.emit("No rendering backend available")
            return False

        try:
            success = self.current_backend.load_pdf(pdf_path)
            if success:
                self.current_pdf_path = pdf_path
                self.pdf_loaded.emit(pdf_path)
                logger.info(f"[pdf] PDF loaded via {self.current_backend_name}: {pdf_path}")
                return True
            else:
                # Fallback to next backend
                logger.warning(f"[pdf] {self.current_backend_name} failed, trying fallback")
                return self._fallback_load_pdf(pdf_path)
        except Exception as e:
            logger.error(f"[pdf] Load error: {e}")
            self.pdf_load_failed.emit(str(e))
            return False

    def _fallback_load_pdf(self, pdf_path: Path) -> bool:
        """Try fallback backends."""
        backends_to_try: list[PdfBackend] = []

        if self.current_backend_name != "webengine":
            backends_to_try.append(self.webengine_backend)
        if self.current_backend_name != "qtpdf":
            backends_to_try.append(self.qtpdf_backend)
        if self.current_backend_name != "raster":
            backends_to_try.append(self.raster_backend)

        for backend in backends_to_try:
            try:
                self._prime_backend_state(backend)
                if backend.load_pdf(pdf_path):
                    self.current_backend = backend
                    cap = backend.capabilities()
                    self.current_backend_name = cap.backend_type
                    self.current_pdf_path = pdf_path
                    if cap.backend_type != "raster":
                        backend.set_zoom(self.zoom_factor)
                        backend.set_dark_mode(self.dark_mode)
                    self.backend_changed.emit(self.current_backend_name)
                    self.pdf_loaded.emit(pdf_path)
                    logger.info(f"[pdf] Fallback to {cap.backend_type} succeeded")
                    return True
            except Exception as e:
                logger.debug(f"[pdf] Fallback attempt failed: {e}")
                continue

        self.pdf_load_failed.emit("All backends failed")
        return False

    def _prime_backend_state(self, backend: PdfBackend) -> None:
        """Copy controller view state onto a candidate backend before loading."""
        clamped_zoom = max(0.35, min(4.0, self.zoom_factor))
        if hasattr(backend, "zoom_factor"):
            setattr(backend, "zoom_factor", clamped_zoom)
        if hasattr(backend, "dark_mode"):
            setattr(backend, "dark_mode", self.dark_mode)

    def set_zoom(self, zoom_factor: float) -> None:
        """Set zoom factor on current backend."""
        self.zoom_factor = zoom_factor
        if self.current_backend:
            self.current_backend.set_zoom(zoom_factor)

    def set_dark_mode(self, enabled: bool) -> None:
        """Toggle dark mode on current backend."""
        self.dark_mode = enabled
        if self.current_backend:
            self.current_backend.set_dark_mode(enabled)

    def get_widget(self) -> QWidget:
        """Get display widget for layout."""
        if self.current_backend:
            return self.current_backend.get_widget()
        empty = QWidget()
        empty.setLayout(QVBoxLayout())
        return empty

    def capabilities(self) -> PdfCapabilities:
        """Get current backend capabilities."""
        if self.current_backend:
            return self.current_backend.capabilities()
        return PdfCapabilities(False, "none", False, 0)

    def cleanup(self) -> None:
        """Clean up all resources."""
        try:
            self.webengine_backend.cleanup()
            self.qtpdf_backend.cleanup()
            self.raster_backend.cleanup()
            logger.info("[pdf] Controller cleaned up")
        except Exception as e:
            logger.error(f"[pdf] Cleanup error: {e}")


def create_pdf_toolbar(controller: PdfPreviewController, parent: QWidget) -> QHBoxLayout:
    """Create PDF toolbar with mode selection and controls."""
    toolbar = QHBoxLayout()

    # Rendering mode selector
    mode_label = QLabel("Render Mode:")
    mode_combo = QComboBox()
    mode_combo.addItem("Auto", PdfRenderMode.AUTO)
    mode_combo.addItem("GPU (WebEngine)", PdfRenderMode.GPU_WEBENGINE)
    mode_combo.addItem("Compatible (Raster)", PdfRenderMode.COMPATIBLE)
    mode_combo.setCurrentIndex(0)

    def on_mode_changed(index: int) -> None:
        mode = mode_combo.itemData(index)
        controller.set_render_mode(mode)

    mode_combo.currentIndexChanged.connect(on_mode_changed)
    toolbar.addWidget(mode_label)
    toolbar.addWidget(mode_combo)

    toolbar.addSpacing(20)

    # Backend info label
    backend_label = QLabel("Backend: Loading...")
    def on_backend_changed(backend_name: str) -> None:
        backend_label.setText(f"Backend: {backend_name.upper()}")
    controller.backend_changed.connect(on_backend_changed)
    toolbar.addWidget(backend_label)

    toolbar.addStretch()

    return toolbar
