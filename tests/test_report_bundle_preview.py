from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from datalab_core.report_bundle import ReportBundleValidationError, write_report_bundle

PNG_BYTES = b"\x89PNG\r\n\x1a\nplot bytes"
PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


def test_report_bundle_preview_reads_valid_bundle_without_importing_workspace(
    tmp_path: Path,
) -> None:
    from app_desktop.report_bundle_preview import load_report_bundle_preview, preview_to_json
    from shared.workspace_io import write_workspace

    workspace_path = tmp_path / "source.datalab"
    write_workspace(workspace_path, _minimal_workspace_manifest(), {})
    target = tmp_path / "report.datalab-report.zip"

    write_report_bundle(
        target,
        semantic_snapshots={
            "statistics": {
                "family": "statistics",
                "kind": "statistics_single",
                "metric_rows": [{"key": "mean", "value": "1.25"}],
            }
        },
        tables={"summary": "metric,value\nmean,1.25\n"},
        latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
        latex_sections={"statistics-section": "\\section{Statistics}\n"},
        plots={"overview": PNG_BYTES},
        pdf=PDF_BYTES,
        sources={"source.datalab": workspace_path.read_bytes()},
        datalab_version="2.7.10",
        created_at="2026-06-26T00:00:00Z",
        language="en",
        export_options={"latex_engine": "tectonic"},
    )

    preview = load_report_bundle_preview(target)

    assert preview.path == target
    assert {row.key: row.value for row in preview.metadata_rows}["compile_status"] == "succeeded"
    assert preview.selected_snapshots[0].attachment_id == "statistics"
    assert preview.selected_snapshots[0].family == "statistics"
    assert preview.selected_snapshots[0].kind == "statistics_single"
    assert preview.latex_report.text.startswith("\\documentclass")
    assert preview.latex_sections[0].path == "latex/sections/statistics-section.tex"
    assert preview.tables[0].text == "metric,value\nmean,1.25\n"
    assert preview.plots[0].path == "plots/overview.png"
    assert preview.pdf is not None
    assert preview.pdf.path == "pdf/report.pdf"
    assert preview.sources[0].path == "sources/source.datalab"
    assert preview.source_workspaces[0].valid is True
    assert preview.source_workspaces[0].title == "Preview source"
    assert preview.openable_source_workspace_ids == ("source.datalab",)

    serialized = json.loads(preview_to_json(preview))
    assert serialized["source_workspaces"][0]["valid"] is True


def test_report_bundle_preview_rejects_malformed_bundle(tmp_path: Path) -> None:
    from app_desktop.report_bundle_preview import load_report_bundle_preview

    target = tmp_path / "not-a-report.zip"
    target.write_bytes(b"not a zip")

    with pytest.raises(ReportBundleValidationError, match="not a valid ZIP"):
        load_report_bundle_preview(target)


def test_report_bundle_preview_marks_invalid_source_workspace_without_failing_bundle(
    tmp_path: Path,
) -> None:
    from app_desktop.report_bundle_preview import load_report_bundle_preview

    target = tmp_path / "report-with-bad-source.datalab-report.zip"
    write_report_bundle(
        target,
        semantic_snapshots={"root": {"family": "root_solving", "kind": "root_solving"}},
        tables={},
        latex_report="Report",
        sources={"source.datalab": b"not a workspace zip"},
    )

    preview = load_report_bundle_preview(target)

    assert preview.sources[0].path == "sources/source.datalab"
    assert preview.source_workspaces[0].valid is False
    assert "valid ZIP" in str(preview.source_workspaces[0].error)
    assert preview.openable_source_workspace_ids == ()


def test_report_bundle_preview_module_has_no_compile_or_workspace_restore_dependencies() -> None:
    module_path = Path(__file__).resolve().parents[1] / "app_desktop" / "report_bundle_preview.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "app_desktop.window_latex_pdf_mixin",
        "app_desktop.workspace_controller",
        "shared.latex_engine",
        "subprocess",
    }
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert imported_modules.isdisjoint(forbidden_modules)
    assert "tectonic_compile_argv" not in source
    assert "restore_workspace" not in source
    assert "write_workspace" not in source


def _minimal_workspace_manifest() -> dict[str, Any]:
    return {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "app": {"name": "DataLab", "version": "2.7.10"},
        "created_at": "2026-06-26T00:00:00Z",
        "updated_at": "2026-06-26T00:00:00Z",
        "workspace": {
            "title": "Preview source",
            "current_mode": "statistics",
            "language": "en",
            "ui": {"main_tab": "results"},
            "data": {
                "source_kind": "manual_table",
                "decoded_text": "value\n1\n2\n",
                "encoding": "utf-8",
                "newline": "lf",
                "original_bytes_sha256": "sha256:44b3872d59b5b9f7b8ad3d32f47f6a89f6a27db53881d156f219c01fde1cb6d1",
                "raw_bytes_path": None,
                "canonical_table": {"headers": ["value"], "rows": [["1"], ["2"]]},
                "sha256": "sha256:44b3872d59b5b9f7b8ad3d32f47f6a89f6a27db53881d156f219c01fde1cb6d1",
            },
            "constants": {"enabled": False},
            "config": {
                "common": {"mpmath_precision": 16, "display_digits": 10},
                "statistics": {"mode": "mean", "value_column": "value"},
            },
            "result_snapshot": {"present": False},
        },
    }
