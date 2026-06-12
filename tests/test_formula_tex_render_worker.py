from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image


def _png_bytes() -> bytes:
    image = Image.new("RGBA", (16, 8), (255, 255, 255, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_tex_renderer_uses_existing_engine_without_auto_install(monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    import app_desktop.formula_tex_render_worker as worker

    calls: dict[str, Any] = {"compile": 0, "raster": 0}

    monkeypatch.setattr(
        worker.latex_engine,
        "resolve_engine",
        lambda engine: EngineChoice(path=f"/fake/{engine}", source="system"),
    )
    monkeypatch.setattr(
        worker.latex_engine,
        "ensure_tectonic_installed",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("auto-install must not run")),
    )

    def fake_compile(*, tex_path: Path, engine_path: str, engine: str, timeout_seconds: float) -> Path:
        calls["compile"] += 1
        assert tex_path.name == "formula.tex"
        assert engine_path == "/fake/tectonic"
        assert engine == "tectonic"
        assert timeout_seconds == 3.0
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.7\n")
        return pdf_path

    def fake_raster(pdf_path: Path, *, dpi: int, max_pages: int) -> list[Image.Image]:
        calls["raster"] += 1
        assert pdf_path.name == "formula.pdf"
        assert dpi == 144
        assert max_pages == 1
        return [Image.open(io.BytesIO(_png_bytes())).convert("RGBA")]

    monkeypatch.setattr(worker, "_compile_formula_document", fake_compile)
    monkeypatch.setattr(worker.pdf_preview_raster, "convert_pdf_to_images", fake_raster)
    worker.clear_formula_tex_render_cache()

    result = worker.render_latex_to_png_bytes(
        worker.TexRenderRequest(latex=r"\frac{1}{2}", engine="tectonic", dpi=144, timeout_seconds=3.0)
    )

    assert result.ok is True
    assert result.png_bytes.startswith(b"\x89PNG")
    assert result.engine_path == "/fake/tectonic"
    assert calls == {"compile": 1, "raster": 1}


def test_tex_renderer_missing_engine_fails_without_network(monkeypatch: Any) -> None:
    import app_desktop.formula_tex_render_worker as worker

    monkeypatch.setattr(worker.latex_engine, "resolve_engine", lambda _engine: None)
    monkeypatch.setattr(
        worker.latex_engine,
        "ensure_tectonic_installed",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("auto-install must not run")),
    )

    result = worker.render_latex_to_png_bytes(worker.TexRenderRequest(latex=r"x^2", engine="tectonic"))

    assert result.ok is False
    assert result.cancelled is False
    assert "unavailable" in result.error_message.lower()


def test_tex_renderer_cancel_before_start_skips_compile(monkeypatch: Any) -> None:
    import app_desktop.formula_tex_render_worker as worker

    monkeypatch.setattr(worker, "_compile_formula_document", lambda **_kwargs: (_ for _ in ()).throw(AssertionError))

    result = worker.render_latex_to_png_bytes(
        worker.TexRenderRequest(latex=r"x^2"),
        should_cancel=lambda: True,
    )

    assert result.ok is False
    assert result.cancelled is True


def test_tex_renderer_cancel_after_compile_skips_raster(monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    import app_desktop.formula_tex_render_worker as worker

    checks = {"count": 0}
    monkeypatch.setattr(
        worker.latex_engine,
        "resolve_engine",
        lambda engine: EngineChoice(path=f"/fake/{engine}", source="system"),
    )

    def fake_compile(**kwargs: Any) -> Path:
        tex_path = kwargs["tex_path"]
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.7\n")
        return pdf_path

    def should_cancel() -> bool:
        checks["count"] += 1
        return checks["count"] >= 2

    monkeypatch.setattr(worker, "_compile_formula_document", fake_compile)
    monkeypatch.setattr(
        worker.pdf_preview_raster,
        "convert_pdf_to_images",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("raster must not run after cancel")),
    )
    worker.clear_formula_tex_render_cache()

    result = worker.render_latex_to_png_bytes(
        worker.TexRenderRequest(latex=r"x^2"),
        should_cancel=should_cancel,
    )

    assert result.ok is False
    assert result.cancelled is True
    assert checks["count"] == 2


def test_tex_renderer_cache_skips_duplicate_compile(monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    import app_desktop.formula_tex_render_worker as worker

    calls = {"compile": 0}
    monkeypatch.setattr(
        worker.latex_engine,
        "resolve_engine",
        lambda engine: EngineChoice(path=f"/fake/{engine}", source="system"),
    )

    def fake_compile(**kwargs: Any) -> Path:
        calls["compile"] += 1
        tex_path = kwargs["tex_path"]
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.7\n")
        return pdf_path

    monkeypatch.setattr(worker, "_compile_formula_document", fake_compile)
    monkeypatch.setattr(
        worker.pdf_preview_raster,
        "convert_pdf_to_images",
        lambda _path, *, dpi, max_pages: [Image.open(io.BytesIO(_png_bytes())).convert("RGBA")],
    )
    worker.clear_formula_tex_render_cache()
    request = worker.TexRenderRequest(latex=r"x^2", engine="pdflatex", dpi=120)

    first = worker.render_latex_to_png_bytes(request)
    second = worker.render_latex_to_png_bytes(request)

    assert first.ok is True
    assert second.ok is True
    assert second.from_cache is True
    assert calls["compile"] == 1


def test_tex_renderer_cache_distinguishes_resolved_engine_path(monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    import app_desktop.formula_tex_render_worker as worker

    paths = ["/fake/tectonic-a", "/fake/tectonic-b"]
    calls = {"compile": 0}

    def fake_resolve(engine: str) -> EngineChoice:
        return EngineChoice(path=paths.pop(0), source="system")

    def fake_compile(**kwargs: Any) -> Path:
        calls["compile"] += 1
        tex_path = kwargs["tex_path"]
        pdf_path = tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.7\n")
        return pdf_path

    monkeypatch.setattr(worker.latex_engine, "resolve_engine", fake_resolve)
    monkeypatch.setattr(worker, "_compile_formula_document", fake_compile)
    monkeypatch.setattr(
        worker.pdf_preview_raster,
        "convert_pdf_to_images",
        lambda _path, *, dpi, max_pages: [Image.open(io.BytesIO(_png_bytes())).convert("RGBA")],
    )
    worker.clear_formula_tex_render_cache()
    request = worker.TexRenderRequest(latex=r"x^2", engine="tectonic", dpi=120)

    first = worker.render_latex_to_png_bytes(request)
    second = worker.render_latex_to_png_bytes(request)

    assert first.ok is True
    assert second.ok is True
    assert second.from_cache is False
    assert calls["compile"] == 2


def test_tex_compile_argv_is_sandboxed_and_network_free() -> None:
    import app_desktop.formula_tex_render_worker as worker

    tex_path = Path("/tmp/datalab-formula/formula.tex")
    tectonic_argv = worker._build_compile_argv("/usr/bin/tectonic", "tectonic", tex_path)
    pdflatex_argv = worker._build_compile_argv("/usr/bin/pdflatex", "pdflatex", tex_path)

    assert tectonic_argv[0] == "/usr/bin/tectonic"
    assert "--only-cached" in tectonic_argv
    assert "--" in tectonic_argv
    assert all("install" not in part.lower() for part in tectonic_argv)
    assert pdflatex_argv[0] == "/usr/bin/pdflatex"
    assert "-no-shell-escape" in pdflatex_argv
    assert str(tex_path.name) in pdflatex_argv


def test_tex_compile_process_terminates_child_on_communicate_error(monkeypatch: Any, tmp_path: Path) -> None:
    import app_desktop.formula_tex_render_worker as worker

    class FakeProcess:
        pid = 12345
        returncode: int | None = None
        alive = True

        def communicate(self, *, timeout: float) -> tuple[str, str]:
            raise OSError("pipe failure")

        def poll(self) -> int | None:
            return None if self.alive else self.returncode

    process = FakeProcess()
    calls: dict[str, object] = {}

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return process

    def fake_terminate(target: FakeProcess) -> None:
        calls["terminated"] = target
        target.alive = False
        target.returncode = -15

    monkeypatch.setattr(worker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(worker, "_terminate_process_group", fake_terminate)

    with pytest.raises(OSError, match="pipe failure"):
        worker._run_compile_process(["latex", "formula.tex"], cwd=tmp_path, timeout_seconds=1.0)

    assert calls["terminated"] is process
