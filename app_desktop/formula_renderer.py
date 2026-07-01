"""Desktop orchestrator for formula preview rendering."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from datalab_latex.formula_render_service import (
    FormulaPreviewMetadata,
    InputLanguage,
    RenderRequest,
    RenderResult,
    render_formula_metadata,
)
from shared.formula_mathtext_png import render_mathtext_png


class FormulaBackend(Protocol):
    def render_formula(self, metadata: FormulaPreviewMetadata, dpi: int, color: str) -> bytes:
        ...


class MathTextPngBackend:
    def render_formula(self, metadata: FormulaPreviewMetadata, dpi: int, color: str) -> bytes:
        return render_mathtext_png(metadata.mathtext, dpi=dpi, color=color)


_DEFAULT_BACKEND = MathTextPngBackend()


def clear_formula_renderer_cache() -> None:
    _render_desktop_preview_cached.cache_clear()


def render_desktop_preview(
    request: RenderRequest,
    backend: FormulaBackend | None = None,
) -> RenderResult:
    """Render a preview using the desktop backend boundary."""
    if backend is None:
        language = InputLanguage(request.language)
        return _render_desktop_preview_cached(
            request.source or "",
            language.value,
            request.lhs,
            int(request.dpi),
            request.color,
        )
    return _render_desktop_preview_uncached(request, backend)


@lru_cache(maxsize=256)
def _render_desktop_preview_cached(
    source: str,
    language_value: str,
    lhs: str | None,
    dpi: int,
    color: str,
) -> RenderResult:
    request = RenderRequest(
        source=source,
        language=InputLanguage(language_value),
        lhs=lhs,
        dpi=dpi,
        color=color,
    )
    return _render_desktop_preview_uncached(request, _DEFAULT_BACKEND)


def _render_desktop_preview_uncached(
    request: RenderRequest,
    backend: FormulaBackend,
) -> RenderResult:
    metadata = render_formula_metadata(request)
    if not metadata.ok:
        return RenderResult(
            ok=False,
            source=metadata.source,
            language=metadata.language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=b"",
            fallback_text=metadata.fallback_text,
            error_message=metadata.error_message,
        )

    try:
        png_bytes = backend.render_formula(
            metadata,
            dpi=int(request.dpi),
            color=request.color,
        )
        return RenderResult(
            ok=True,
            source=metadata.source,
            language=metadata.language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=png_bytes,
            fallback_text=metadata.fallback_text,
        )
    except Exception as exc:  # noqa: BLE001
        return RenderResult(
            ok=False,
            source=metadata.source,
            language=metadata.language,
            latex=metadata.latex,
            mathtext=metadata.mathtext,
            png_bytes=b"",
            fallback_text=metadata.fallback_text,
            error_message=str(exc) or exc.__class__.__name__,
        )
