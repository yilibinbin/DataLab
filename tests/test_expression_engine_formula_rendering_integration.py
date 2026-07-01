from __future__ import annotations


def test_expression_engine_delegates_latex_formatting_to_render_service(monkeypatch) -> None:
    import datalab_latex.formula_render_service as service
    from datalab_latex.expression_engine import format_latex_formula

    calls: list[str] = []

    def fake_format(source: str) -> str:
        calls.append(source)
        return "SERVICE_LATEX"

    monkeypatch.setattr(service, "format_formula_latex", fake_format)

    assert format_latex_formula("x^2 + 1") == "SERVICE_LATEX"
    assert calls == ["x^2 + 1"]


def test_desktop_formula_preview_delegates_png_rendering_to_render_service(monkeypatch, qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    import app_desktop.formula_preview as preview
    import datalab_latex.formula_render_service as service

    calls: list[service.RenderRequest] = []

    def fake_render(request: service.RenderRequest) -> service.RenderResult:
        calls.append(request)
        return service.RenderResult(
            ok=False,
            source=request.source,
            language=request.language,
            latex="",
            mathtext="",
            png_bytes=b"",
            fallback_text=request.source,
            error_message="forced fallback",
        )

    monkeypatch.setattr(preview, "render_desktop_preview", fake_render)
    label = QLabel()
    qtbot.addWidget(label)

    preview.update_formula_preview(label, "x^2 + 1", lhs="y")

    assert calls
    assert calls[0].source == "x^2 + 1"
    assert calls[0].lhs == "y"
    assert label.text() == "x^2 + 1"


def test_desktop_formula_preview_active_path_has_no_legacy_regex_converter(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    import app_desktop.formula_preview as preview

    assert not hasattr(preview, "_convert_expression")
    label = QLabel()
    qtbot.addWidget(label)

    preview.update_formula_preview(label, "x^2 + 1")

    assert label.pixmap() is not None
    assert not label.pixmap().isNull()
