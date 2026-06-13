from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shipping_desktop_sources_do_not_import_webengine_stack() -> None:
    from tools.webengine_shipping_import_guard import (
        shipping_source_paths,
        webengine_import_violations,
    )

    violations = webengine_import_violations(shipping_source_paths(ROOT))

    assert violations == []


def test_shipping_import_guard_reports_forbidden_imports(tmp_path: Path) -> None:
    from tools.webengine_shipping_import_guard import webengine_import_violations

    bad = tmp_path / "bad_shipping_module.py"
    bad.write_text(
        "\n".join(
            [
                "from shared.pdf_preview import PdfPreviewController",
                "from PySide6.QtWebEngineWidgets import QWebEngineView",
                "import PySide6.QtWebChannel",
            ]
        ),
        encoding="utf-8",
    )

    violations = webengine_import_violations([bad])

    assert [
        (violation.module, violation.line)
        for violation in violations
    ] == [
        ("shared.pdf_preview", 1),
        ("PySide6.QtWebEngineWidgets", 2),
        ("PySide6.QtWebChannel", 3),
    ]
    assert all(violation.path == bad for violation in violations)


def test_shipping_import_guard_ignores_non_forbidden_import_prefixes(tmp_path: Path) -> None:
    from tools.webengine_shipping_import_guard import webengine_import_violations

    safe = tmp_path / "safe_shipping_module.py"
    safe.write_text(
        "\n".join(
            [
                "from shared import pdf_preview_raster",
                "from app_desktop.webengine_spike_assets import inspect_offline_assets",
                "import PySide6.QtWidgets",
            ]
        ),
        encoding="utf-8",
    )

    assert webengine_import_violations([safe]) == []
