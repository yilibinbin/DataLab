import subprocess
import sys

import pytest

from app_desktop.formula_renderer import (
    clear_formula_renderer_cache,
    render_desktop_preview,
)
from datalab_latex.formula_render_service import (
    FormulaPreviewMetadata,
    InputLanguage,
    RenderRequest,
    clear_formula_render_cache,
)


@pytest.fixture(autouse=True)
def clear_renderer_caches():
    clear_formula_renderer_cache()
    clear_formula_render_cache()
    yield
    clear_formula_renderer_cache()
    clear_formula_render_cache()


def test_desktop_renderer_boundary_import_purity() -> None:
    code = (
        "import sys\n"
        "from app_desktop.formula_renderer import render_desktop_preview\n"
        "assert 'matplotlib' not in sys.modules\n"
        "assert not any(m.startswith('PySide6.QtWebEngine') for m in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Import purity failed: {result.stderr}"


class FailingMockBackend:
    def render_formula(self, metadata: FormulaPreviewMetadata, dpi: int, color: str) -> bytes:
        raise ValueError("Backend failed")


def test_render_desktop_preview_backend_failure_fallback() -> None:
    request = RenderRequest(source="x^2", language="datalab")
    result = render_desktop_preview(request, backend=FailingMockBackend())
    assert not result.ok
    assert result.png_bytes == b""
    assert result.error_message == "Backend failed"
    assert result.fallback_text == "x^2"
    assert "x^{2}" in result.latex


def test_render_desktop_preview_success() -> None:
    request = RenderRequest(source="x^2", language="datalab")
    result = render_desktop_preview(request)
    assert result.ok
    assert result.png_bytes.startswith(b"\x89PNG")
    assert result.fallback_text == "x^2"


def test_render_desktop_preview_cache_avoids_metadata_and_png_rerender(monkeypatch: pytest.MonkeyPatch) -> None:
    import app_desktop.formula_renderer as renderer

    calls: dict[str, int] = {"metadata": 0, "png": 0}

    def fake_metadata(request: RenderRequest) -> FormulaPreviewMetadata:
        calls["metadata"] += 1
        return FormulaPreviewMetadata(
            ok=True,
            source=request.source,
            language=InputLanguage(request.language),
            latex="x^{2}",
            mathtext="$x^{2}$",
            fallback_text=request.source,
        )

    def fake_png(mathtext: str, *, dpi: int, color: str) -> bytes:
        calls["png"] += 1
        assert mathtext == "$x^{2}$"
        assert dpi == 160
        assert color == "#111827"
        return b"\x89PNG\r\n\x1a\nfake"

    monkeypatch.setattr(renderer, "render_formula_metadata", fake_metadata)
    monkeypatch.setattr(renderer, "render_mathtext_png", fake_png)

    request = RenderRequest(source="x^2", language="datalab")
    first = render_desktop_preview(request)
    second = render_desktop_preview(request)

    assert first.ok
    assert second.ok
    assert calls == {"metadata": 1, "png": 1}


def test_render_desktop_preview_injected_backend_bypasses_warm_default_cache() -> None:
    class CountingBackend:
        calls = 0

        def render_formula(self, metadata: FormulaPreviewMetadata, dpi: int, color: str) -> bytes:
            self.calls += 1
            return b"\x89PNG\r\n\x1a\ncustom"

    request = RenderRequest(source="x^2", language="datalab")
    assert render_desktop_preview(request).ok

    backend = CountingBackend()
    injected = render_desktop_preview(request, backend=backend)

    assert injected.ok
    assert injected.png_bytes == b"\x89PNG\r\n\x1a\ncustom"
    assert backend.calls == 1


def test_render_desktop_preview_injected_backend_does_not_populate_default_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.formula_renderer as renderer

    calls: dict[str, int] = {"png": 0}

    class CustomBackend:
        def render_formula(self, metadata: FormulaPreviewMetadata, dpi: int, color: str) -> bytes:
            return b"\x89PNG\r\n\x1a\ncustom"

    def fake_png(mathtext: str, *, dpi: int, color: str) -> bytes:
        calls["png"] += 1
        return b"\x89PNG\r\n\x1a\ndefault"

    monkeypatch.setattr(renderer, "render_mathtext_png", fake_png)

    request = RenderRequest(source="x^2", language="datalab")
    injected = render_desktop_preview(request, backend=CustomBackend())
    default = render_desktop_preview(request)

    assert injected.png_bytes == b"\x89PNG\r\n\x1a\ncustom"
    assert default.png_bytes == b"\x89PNG\r\n\x1a\ndefault"
    assert calls["png"] == 1


def test_clear_formula_renderer_cache_forces_rerender(monkeypatch: pytest.MonkeyPatch) -> None:
    import app_desktop.formula_renderer as renderer

    calls: dict[str, int] = {"png": 0}

    def fake_png(mathtext: str, *, dpi: int, color: str) -> bytes:
        calls["png"] += 1
        return b"\x89PNG\r\n\x1a\n" + str(calls["png"]).encode("ascii")

    monkeypatch.setattr(renderer, "render_mathtext_png", fake_png)

    request = RenderRequest(source="x^2", language="datalab")
    first = render_desktop_preview(request)
    second = render_desktop_preview(request)
    clear_formula_renderer_cache()
    third = render_desktop_preview(request)

    assert first.png_bytes == second.png_bytes
    assert third.png_bytes != first.png_bytes
    assert calls["png"] == 2
